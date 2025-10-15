# app/simulation.py
import time, math, os, json
import numpy as np
from multiprocessing import Pool, cpu_count
import matplotlib.pyplot as plt

# small lookup of attenuation coefficients (mu in 1/mm) for demo only
# THESE VALUES ARE DEMONSTRATIVE — not accurate physical constants.
MATERIAL_MU = {
    "Aluminum": 0.15,  # per mm (toy values)
    "Lead": 1.2,
    "Water": 0.08
}

def single_chunk_sim(samples, mu, thickness, rng_seed=None):
    """
    Run `samples` Monte Carlo trials and return summary:
      transmitted_count, path_lengths (array)
    Model: sample free-path ~ Exponential(rate=mu). If free-path > thickness -> transmitted.
    """
    if rng_seed is not None:
        rng = np.random.default_rng(rng_seed)
    else:
        rng = np.random.default_rng()
    # sample free paths: exponential with mean 1/mu
    if mu <= 0:
        # avoid zero division
        paths = np.full(samples, np.inf)
    else:
        paths = rng.exponential(scale=1.0/mu, size=samples)
    transmitted = np.count_nonzero(paths > thickness)
    return int(transmitted), paths

def run_simulation(params, parallel=False, n_workers=None, progress_callback=None):
    """
    params: dict with keys:
      - material: string (must be in MATERIAL_MU)
      - thickness: float (mm)
      - samples: int
      - seed: optional int for reproducibility
    Returns a dict result (including histogram data).
    """
    start = time.time()
    material = params.get("material", "Aluminum")
    thickness = float(params.get("thickness", 1.0))
    samples = int(params.get("samples", 500))
    seed = params.get("seed", None)

    if material not in MATERIAL_MU:
        raise ValueError("Unknown material")
    mu = float(MATERIAL_MU[material])

    # parallel splitting
    if parallel:
        cpu_avail = cpu_count()
        if n_workers is None:
            n_workers = min(4, max(1, cpu_avail))  # cap to 4 for demo safety
        # split samples across workers as evenly as possible
        chunks = []
        base = samples // n_workers
        rem = samples % n_workers
        offset_seed = seed or np.random.SeedSequence().entropy
        for i in range(n_workers):
            cnt = base + (1 if i < rem else 0)
            if cnt > 0:
                chunks.append((cnt, mu, thickness, int(offset_seed) + i))
        # run in multiprocessing pool
        transmitted_total = 0
        all_paths = []
        with Pool(processes=len(chunks)) as p:
            results = p.starmap(single_chunk_sim, chunks)
        for transmitted, paths in results:
            transmitted_total += transmitted
            all_paths.append(paths)
        if len(all_paths):
            all_paths = np.concatenate(all_paths)
        else:
            all_paths = np.array([])
    else:
        transmitted_total, all_paths = single_chunk_sim(samples, mu, thickness, rng_seed=seed)

    transmitted_fraction = transmitted_total / float(samples)

    # Build histogram of path lengths (coarse bins)
    bins = np.linspace(0, max(thickness * 2, np.percentile(all_paths, 95) if all_paths.size else thickness), 20)
    counts, edges = np.histogram(all_paths, bins=bins)

    # generate a small plot saved as PNG bytes (or file)
    plot_path = None
    try:
        fig = plt.figure(figsize=(6,3))
        plt.hist(all_paths, bins=bins)
        plt.axvline(thickness, color='red', linestyle='--', label='thickness')
        plt.title(f'Path lengths (material={material}, thickness={thickness}mm)')
        plt.xlabel('path length (mm)')
        plt.legend()
        plt.tight_layout()
        # save to file by caller (we do not assume file path here)
        plot_path = fig
        plt.close(fig)
    except Exception:
        plot_path = None

    runtime = time.time() - start

    result = {
        "material": material,
        "thickness": thickness,
        "samples": samples,
        "transmitted": int(transmitted_total),
        "transmitted_fraction": transmitted_fraction,
        "bins": edges.tolist(),
        "counts": counts.tolist(),
        "runtime_seconds": runtime,
        "parallel_used": bool(parallel),
        "workers": n_workers if parallel else 1,
    }
    return result, plot_path
