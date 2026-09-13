#!/usr/bin/env python3
"""Terrella Asset Service — FastAPI backend implementing backend/CONTRACT.md v1.

Binds 127.0.0.1:18810 (TLS terminated by Caddy at https://jillvanc.studio/terrella/*).
Single-worker FIFO job queue drives the /root/asset-pipeline scripts via subprocess.
State persists in /root/terrella-assets/{jobs.json,catalog.json} across restarts.
"""
import copy
import hmac
import json
import os
import queue
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE = Path("/root/terrella-assets")
SEEDS = BASE / "seeds"
ASSETS = BASE / "assets"
WORK = BASE / "work"
JOBS_FILE = BASE / "jobs.json"
CATALOG_FILE = BASE / "catalog.json"
TOKEN_FILE = BASE / "service.token"
ENV_FILE = BASE / "service.env"

PIPE = Path("/root/asset-pipeline")
PIPE_PY = str(PIPE / "venv" / "bin" / "python")
PIPE_SCRIPTS = PIPE

FPS, DURATION, WIDTH, HEIGHT = 30, 6.0, 720, 1280

# stage -> (progress_lo, progress_hi) per CONTRACT.md
WEIGHTS = {
    "concept": (0.02, 0.10),
    "cutout": (0.10, 0.15),
    "three_d": (0.15, 0.60),
    "textures": (0.60, 0.65),
    "qa": (0.65, 0.70),
    "video_day": (0.70, 0.80),
    "video_night": (0.80, 0.90),
    "poster": (0.90, 0.92),
    "stylize_day": (0.92, 0.96),
    "stylize_night": (0.96, 0.99),
}
ASSET_FILES = {"day.mp4": "video/mp4", "night.mp4": "video/mp4",
               "poster.jpg": "image/jpeg", "model.glb": "model/gltf-binary"}

app = FastAPI(title="Terrella Asset Service", version="1.0")

TRELLIS_RETRIES = 3
QUOTA_WAIT_S = 300

_lock = threading.RLock()
_catalog = {"version": 0, "assets": []}
_jobs = {}          # job_id -> job dict
_queue = queue.Queue()
_cancel = set()     # job ids flagged for cancellation


def norm_key(name: str, country: str) -> str:
    """key = f"{name},{country}" trimmed, whitespace collapsed, lowercase (CONTRACT.md)."""
    fix = lambda s: " ".join((s or "").strip().split())
    return f"{fix(name)},{fix(country)}".lower()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def save_jobs():
    with _lock:
        _atomic_write_jobs = {jid: dict(j) for jid, j in _jobs.items()}
    _atomic_write_safe(BASE / "jobs.json", {"jobs": _atomic_write_jobs})


def _atomic_write_safe(path: Path, data):
    # Unique tmp per call: a fixed name races between the worker and API
    # threads (os.replace then fails with ENOENT and kills the worker).
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def load_state():
    global _catalog
    try:
        _catalog = json.loads((BASE / "catalog.json").read_text())
    except Exception:
        _catalog = {"version": 0, "assets": []}
    try:
        raw = json.loads((BASE / "jobs.json").read_text()).get("jobs", {})
    except Exception:
        raw = {}
    for jid, j in raw.items():
        if j["status"] in ("queued", "generating"):
            if j["status"] == "generating":
                j["status"] = "error"
                j["error"] = "interrupted by service restart"
                j["stage"] = None
            else:
                _queue.put(jid)  # requeue surviving queued work
        _jobs[jid] = j
    save_jobs()


def save_catalog():
    with _lock:
        _atomic_write_safe(BASE / "catalog.json", _catalog)


def public_job(j) -> dict:
    return {
        "job_id": j["job_id"], "key": j["key"], "status": j["status"],
        "progress": round(j["progress"], 4), "stage": j["stage"],
        "error": j["error"], "asset": j["asset"],
    }


def auth(authorization: str | None = Header(None)):
    try:
        token = TOKEN_FILE.read_text().strip()
    except Exception:
        raise HTTPException(401, "unauthorized")
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "unauthorized")


# --------------------------------------------------------------------------- #
# Pipeline execution
# --------------------------------------------------------------------------- #

def sub_env():
    env = os.environ.copy()
    env["PYOPENGL_PLATFORM"] = "egl"
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def set_stage(j, stage):
    lo, hi = WEIGHTS[stage]
    with _lock:
        j["stage"], j["progress"] = stage, lo
    save_jobs()


def run_step(argv, cwd=PIPE_SCRIPTS):
    return subprocess.run(argv, cwd=cwd, env=sub_env(),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def fail(j, msg, log):
    with _lock:
        j["status"], j["error"], j["stage"] = "error", msg, None
    tail = "\n".join(log.splitlines()[-25:])
    print(f"[job {j['job_id']}] FAILED {msg}\n{tail}", flush=True)
    save_jobs()


def run_trellis_timer(j, work):
    """step2 with timer-based progress 0.10 -> 0.60 over its typical ~180 s.

    ZeroGPU quota errors (anonymous fallback when the HF token is missing or
    exhausted) are retried with a wait instead of failing the job — the
    anonymous quota replenishes over time.
    """
    lo, hi = WEIGHTS["three_d"]
    outdir = work / "trellis"
    outdir.mkdir(parents=True, exist_ok=True)
    argv = [PIPE_PY, str(PIPE_SCRIPTS / "step2_trellis.py"),
            str(work / "cutout.png"), str(outdir)]
    for attempt in range(TRELLIS_RETRIES + 1):
        p = subprocess.Popen(argv, cwd=PIPE_SCRIPTS, env=sub_env(),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        t0 = time.time()
        while p.poll() is None:
            time.sleep(2)
            frac = min(1.0, (time.time() - t0) / 180.0)
            with _lock:
                j["progress"] = lo + (hi - lo) * frac
            save_jobs()
        log = p.stdout.read() or ""
        if p.returncode == 0:
            break
        if "ZeroGPU quota" in log and attempt < TRELLIS_RETRIES:
            print(f"[job {j['job_id']}] ZeroGPU quota hit — retry "
                  f"{attempt + 1}/{TRELLIS_RETRIES} in {QUOTA_WAIT_S}s", flush=True)
            time.sleep(QUOTA_WAIT_S)
            continue
        fail(j, "three_d (TRELLIS) failed", log)
        return None
    glb = outdir / "trellis_out.glb"
    if not glb.exists():
        fail(j, "three_d produced no GLB", "")
        return None
    return glb


def run_videos_and_poster(j, work):
    """step7 renders day + night + poster; stdout STAGE markers drive progress."""
    lo, hi = WEIGHTS["video_day"]
    argv = [PIPE_PY, str(PIPE_SCRIPTS / "step7_video.py"),
            str(work / "model.glb"), str(work)]
    p = subprocess.Popen(argv, cwd=PIPE_SCRIPTS, env=sub_env(),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert p.stdout is not None
    for line in p.stdout:
        line = line.strip()
        if line.startswith("STAGE "):
            stage = {"render_day": "video_day", "encode_day": "video_day",
                     "render_night": "video_night", "encode_night": "video_night",
                     "poster": "poster"}.get(line.split()[1])
            if stage:
                set_stage(j, stage)
    log_tail = []
    rc = p.wait()
    if rc != 0:
        fail(j, "video/poster rendering failed", f"exit {rc}")
        return False
    for f in ("day.mp4", "night.mp4", "poster.jpg"):
        if not (work / f).exists():
            fail(j, f"missing output {f}", "")
            return False
    return True


def run_job(jid):
    j = _jobs.get(jid)
    if not j or j["status"] != "queued":
        return
    key = j["key"]
    work = WORK / key
    work.mkdir(parents=True, exist_ok=True)
    seed_glb = SEEDS / f"{key}.glb"
    with _lock:
        j["status"] = "generating"
    save_jobs()
    print(f"[job {jid}] start key={key} mode={'seeded' if seed_glb.exists() else 'full'}", flush=True)

    def cancelled():
        return jid in _cancel or j.get("status") not in ("generating", "queued")

    try:
        if seed_glb.exists():
            # Seeded mode: texture-fix -> qa -> video_day -> video_night -> poster -> publish
            src = seed_glb
        else:
            src_png = SEEDS / f"{key}.png"
            if not src_png.exists():
                # Self-contained 2D concept generation (Wikipedia facts +
                # FLUX.1-schnell Space, pollinations fallback). Persisted to
                # seeds/ so the concept is auditable and reusable.
                set_stage(j, "concept")
                r = run_step([PIPE_PY, str(PIPE_SCRIPTS / "step0_concept.py"),
                              str(src_png), j["name"], j["country"]])
                if cancelled():
                    return
                if r.returncode != 0 or not src_png.exists():
                    fail(j, "2D concept generation failed", r.stdout)
                    return
                j["concept"] = str(src_png)
                save_jobs()
            set_stage(j, "cutout")
            r = run_step([PIPE_PY, str(PIPE_SCRIPTS / "step1_cutout.py"), str(src_png), str(work / "cutout.png")])
            if cancelled():
                return
            if r.returncode != 0:
                fail(j, "cutout failed", r.stdout)
                return
            src = run_trellis_timer(j, work)
            if cancelled():
                return
            if src is None:
                return

        # textures: re-encode WebP textures to JPEG for Filament
        set_stage(j, "textures")
        r = run_step([PIPE_PY, str(PIPE_SCRIPTS / "step3_fix_glb.py"), str(src), str(work / "model.glb")])
        if cancelled():
            return
        if r.returncode != 0:
            fail(j, "texture fix failed", r.stdout)
            return

        # qa
        set_stage(j, "qa")
        r = run_step([PIPE_PY, str(PIPE_SCRIPTS / "step4_qa.py"), str(work / "model.glb"), str(work / "qa")])
        if cancelled():
            return
        if r.returncode != 0:
            fail(j, "qa failed", r.stdout)
            return

        # video_day + video_night + poster (one step7 run, STAGE markers bump progress)
        if not run_videos_and_poster(j, work):
            return
        if cancelled():
            return

        # stylize: AI I2V pass over the rendered clips (Hunyuan-1.5). This stage
        # is best-effort — on any failure the plain orbit clips stay and the job
        # still publishes (stylization must never break asset delivery).
        for variant in ("day", "night"):
            if cancelled():
                return
            set_stage(j, f"stylize_{variant}")
            src, dst = work / f"{variant}.mp4", work / f"{variant}_styl.mp4"
            r = run_step([PIPE_PY, str(PIPE_SCRIPTS / "step8_stylize.py"),
                          str(src), str(dst), "--variant", variant])
            if r.returncode == 0 and dst.exists() and dst.stat().st_size > 100_000:
                os.replace(dst, src)
                print(f"[job {jid}] stylized {variant}", flush=True)
            else:
                dst.unlink(missing_ok=True)
                print(f"[job {jid}] stylize {variant} skipped: {r.stdout[-200:]}", flush=True)

        # publish
        dest = ASSETS / key
        dest.mkdir(parents=True, exist_ok=True)
        for f in ("day.mp4", "night.mp4", "poster.jpg", "model.glb"):
            os.replace(work / f, dest / f)
        asset = {
            "key": key,
            "name": j["name"], "country": j["country"],
            "day_video": f"/terrella/assets/{key}/day.mp4",
            "night_video": f"/terrella/assets/{key}/night.mp4",
            "poster": f"/terrella/assets/{key}/poster.jpg",
            "glb": f"/terrella/assets/{key}/model.glb",
            "duration_s": int(DURATION), "width": WIDTH, "height": HEIGHT,
            "created_at": now_iso(),
        }
        with _lock:
            j["asset"] = asset
            j["status"], j["progress"], j["stage"] = "ready", 1.0, None
            _catalog["version"] += 1
            _catalog["assets"] = [a for a in _catalog["assets"] if a["key"] != key] + [asset]
        save_catalog()
        save_jobs()
        print(f"[job {jid}] published {key} (catalog v{_catalog['version']})", flush=True)
    except Exception as e:
        fail(j, f"internal error: {e.__class__.__name__}: {e}", "")
    finally:
        _cancel.discard(jid)


def worker_loop():
    while True:
        jid = _queue.get()
        try:
            j = _jobs.get(jid)
            if not j or j["status"] != "queued":
                continue  # cancelled/purged while queued
            run_job(jid)
        except Exception as e:
            print(f"[worker] error on {jid}: {e}", flush=True)
            # Never leave a job hanging in "generating" on internal errors
            jj = _jobs.get(jid)
            if jj and jj["status"] in ("queued", "generating"):
                fail(jj, f"internal error: {e.__class__.__name__}: {e}", "")
        finally:
            _queue.task_done()


threading.Thread(target=worker_loop, daemon=True, name="asset-worker").start()
load_state()

# --------------------------------------------------------------------------- #
# Endpoints (paths carry the /terrella prefix — Caddy forwards it verbatim)
# --------------------------------------------------------------------------- #

@app.get("/terrella/api/catalog")
def get_catalog(_=Depends(auth)):
    with _lock:
        return copy.deepcopy(_catalog)


@app.get("/terrella/api/health")
def health(_=Depends(auth)):
    with _lock:
        n_jobs = sum(1 for j in _jobs.values() if j["status"] in ("queued", "generating"))
        return {"ok": True, "catalog_version": _catalog["version"], "active_jobs": n_jobs}


class JobRequest(BaseModel):
    name: str
    country: str
    lat: float | None = None
    lon: float | None = None
    force: bool = False  # bypass catalog/in-flight dedupe and regenerate
    lon: float | None = None


@app.post("/terrella/api/jobs")
def create_job(req: JobRequest, _=Depends(auth)):
    key = norm_key(req.name, req.country)
    if not key.split(",")[0] or not key.split(",")[1]:
        raise HTTPException(400, "name and country required")
    with _lock:
        if not req.force:
            for a in _catalog["assets"]:
                if a["key"] == key:
                    return {"status": "ready", "asset": copy.deepcopy(a)}
            for j in _jobs.values():
                if j["key"] == key and j["status"] in ("queued", "generating"):
                    return public_job(j)
        j = {"job_id": uuid.uuid4().hex[:12], "key": key, "name": req.name.strip(),
             "country": req.country.strip(), "status": "queued", "progress": 0.0,
             "stage": None, "error": None, "asset": None,
             "created_at": now_iso()}
        _jobs[j["job_id"]] = j
        _queue.put(j["job_id"])
    save_jobs()
    return public_job(j)


@app.get("/terrella/api/jobs/{job_id}")
def get_job(job_id: str, _=Depends(auth)):
    with _lock:
        j = _jobs.get(job_id)
        if not j:
            raise HTTPException(404, "job not found")
        return public_job(j)


@app.delete("/terrella/api/jobs/{job_id}")
def cancel_job(job_id: str, purge: bool = False, _=Depends(auth)):
    """Additive to the contract: cancel a queued/running job; DELETE again to purge."""
    with _lock:
        j = _jobs.get(job_id)
        if not j:
            raise HTTPException(404, "job not found")
        if j["status"] in ("queued", "generating"):
            _cancel.add(job_id)
            j["status"] = "cancelled"
            j["stage"], j["error"] = None, None
            save_jobs()
        elif purge:
            del _jobs[job_id]
            save_jobs()
            return {"status": "purged", "job_id": job_id}
    return public_job(j)


@app.get("/terrella/assets/{key}/{fname}")
def get_asset(key: str, fname: str, _=Depends(auth)):
    if "/" in key or "\\" in key or key.startswith(".") or fname not in ASSET_FILES:
        raise HTTPException(404, "not found")
    path = ASSETS / key / fname
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type=ASSET_FILES[fname], filename=fname)