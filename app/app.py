# app/app.py
import os
import time
import json
import threading
from decimal import Decimal
from flask import Flask, render_template, request, jsonify, send_from_directory
from utils import (
    ensure_dirs, new_job_id, job_file_path, processing_file_path,
    status_file_path, result_file_path, write_json, read_json
)
from simulation import run_simulation
import matplotlib.pyplot as plt
import boto3

# --- AWS setup ---
S3_BUCKET = os.environ.get("S3_BUCKET", "cloud-sim-results-vs")
s3 = boto3.client("s3", region_name="eu-north-1")
dynamodb = boto3.resource("dynamodb", region_name="eu-north-1")
DDB_TABLE_NAME = os.environ.get("DDB_TABLE", "cloud_sim_jobs")
table = dynamodb.Table(DDB_TABLE_NAME)

# --- Ensure local directories ---
ensure_dirs()

# --- Flask setup ---
app = Flask(__name__, template_folder="templates", static_folder="static")

# --- Config ---
MAX_SAMPLES = 1000
ALLOWED_MATERIALS = ["Aluminum", "Lead", "Water"]
ALLOWED_THICKNESSES = [0.1, 0.5, 1.0, 2.0]
ALLOWED_PARTICLES = ["Photon", "Electron"]

# --- Web endpoints ---

@app.route("/")
def index():
    return render_template(
        "index.html",
        materials=ALLOWED_MATERIALS,
        thicknesses=ALLOWED_THICKNESSES,
        particles=ALLOWED_PARTICLES
    )

@app.route("/api/submit", methods=["POST"])
def submit():
    payload = request.get_json(force=True)

    # validate inputs
    material = payload.get("material")
    thickness = float(payload.get("thickness", 1.0))
    samples = int(payload.get("samples", 100))
    parallel = bool(payload.get("parallel", False))

    if material not in ALLOWED_MATERIALS:
        return jsonify({"error": "invalid material"}), 400
    if thickness not in ALLOWED_THICKNESSES:
        return jsonify({"error": "invalid thickness"}), 400
    if samples <= 0 or samples > MAX_SAMPLES:
        return jsonify({"error": "samples out of allowed range"}), 400

    # create job ID
    job_id = new_job_id()
    created_at = time.time()

    job_obj = {
        "job_id": job_id,
        "material": material,
        "thickness": thickness,
        "samples": samples,
        "parallel": parallel,
        "created_at": created_at
    }
    write_json(job_file_path(job_id), job_obj)

    # write initial status
    status = {"job_id": job_id, "status": "queued", "created_at": created_at}
    write_json(status_file_path(job_id), status)

    # store job metadata in DynamoDB (convert floats to Decimal)
    try:
        table.put_item(Item={
            "job_id": job_id,
            "material": material,
            "thickness": Decimal(str(thickness)),
            "samples": Decimal(str(samples)),
            "parallel": str(parallel),
            "created_at": Decimal(str(created_at))
        })
    except Exception as e:
        print(f"⚠️ DynamoDB write failed for {job_id}: {e}")

    return jsonify({"job_id": job_id}), 202

@app.route("/api/status/<job_id>")
def status(job_id):
    path = status_file_path(job_id)
    if not os.path.exists(path):
        return jsonify({"error": "job not found"}), 404
    return jsonify(read_json(path))

@app.route("/api/result/<job_id>")
def get_result(job_id):
    rpath = result_file_path(job_id)
    if not os.path.exists(rpath):
        return jsonify({"error": "result not available"}), 404
    return jsonify(read_json(rpath))

@app.route("/results/<path:filename>")
def results_files(filename):
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "..", "data", "results"),
        filename
    )

# --- Worker thread ---

def worker_loop(poll_interval=2):
    print("Worker started, polling for jobs...")
    jobs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jobs")
    processing_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "processing")
    status_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "status")
    results_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "results")

    while True:
        try:
            files = [f for f in os.listdir(jobs_dir) if f.endswith(".json")]
            if not files:
                time.sleep(poll_interval)
                continue

            # pick oldest job
            files.sort(key=lambda fn: os.path.getctime(os.path.join(jobs_dir, fn)))
            jobfile = files[0]
            jobpath = os.path.join(jobs_dir, jobfile)
            jobid = jobfile.replace(".json", "")
            procpath = os.path.join(processing_dir, jobfile)

            # move to processing
            os.rename(jobpath, procpath)

            # update status
            write_json(os.path.join(status_dir, f"{jobid}.json"), {
                "job_id": jobid,
                "status": "running",
                "start_time": time.time()
            })

            # read job
            job = read_json(procpath)
            params = {
                "material": job["material"],
                "thickness": job["thickness"],
                "samples": job["samples"]
            }
            parallel = job.get("parallel", False)

            # run simulation
            result, fig = run_simulation(params, parallel=parallel)

            # save plot
            png_path = os.path.join(results_dir, f"{jobid}.png")
            try:
                if fig is not None:
                    fig.savefig(png_path)
            except Exception:
                # fallback minimal plot
                try:
                    import matplotlib.pyplot as plt
                    plt.figure(figsize=(4,2))
                    plt.title("Plot generation failed")
                    plt.savefig(png_path)
                    plt.close()
                except:
                    pass

            # save result JSON
            result_meta = dict(result)
            result_meta["job_id"] = jobid
            result_meta["plot"] = f"/results/{jobid}.png"
            result_meta["completed_at"] = time.time()
            write_json(os.path.join(results_dir, f"{jobid}.json"), result_meta)

            # upload to S3
            try:
                s3.upload_file(png_path, S3_BUCKET, f"results/{jobid}.png")
                s3.upload_file(os.path.join(results_dir, f"{jobid}.json"), S3_BUCKET, f"results/{jobid}.json")
                print(f"Uploaded {jobid} results to s3://{S3_BUCKET}/results/")
            except Exception as e:
                print(f"⚠️ S3 upload failed for {jobid}: {e}")

            # update status
            write_json(os.path.join(status_dir, f"{jobid}.json"), {
                "job_id": jobid,
                "status": "done",
                "completed_at": time.time()
            })

            # remove processing file
            os.remove(procpath)

        except Exception as e:
            print("Worker error:", e)
            time.sleep(poll_interval)

def start_worker():
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

# --- Main ---
if __name__ == "__main__":
    start_worker()
    app.run(debug=True, host="0.0.0.0", port=5000)
