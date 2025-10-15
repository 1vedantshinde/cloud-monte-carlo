# app/utils.py
import os, json, uuid, time

# Base data directory structure (used for local job processing)
BASE_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
JOBS_DIR = os.path.join(BASE_DATA, "jobs")
PROCESSING_DIR = os.path.join(BASE_DATA, "processing")
STATUS_DIR = os.path.join(BASE_DATA, "status")
RESULTS_DIR = os.path.join(BASE_DATA, "results")

def ensure_dirs():
    """
    Ensure that all necessary local directories exist.
    Even though AWS (S3/DynamoDB) stores final data,
    these folders are used for temporary job queueing.
    """
    for d in (JOBS_DIR, PROCESSING_DIR, STATUS_DIR, RESULTS_DIR):
        os.makedirs(d, exist_ok=True)

def new_job_id():
    """Generate a unique job ID."""
    return uuid.uuid4().hex

def job_file_path(job_id):
    return os.path.join(JOBS_DIR, f"{job_id}.json")

def processing_file_path(job_id):
    return os.path.join(PROCESSING_DIR, f"{job_id}.json")

def status_file_path(job_id):
    return os.path.join(STATUS_DIR, f"{job_id}.json")

def result_file_path(job_id):
    return os.path.join(RESULTS_DIR, f"{job_id}.json")

def write_json(path, obj):
    """Write a dictionary to JSON file."""
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def read_json(path):
    """Read a JSON file into a Python object."""
    with open(path, "r") as f:
        return json.load(f)

