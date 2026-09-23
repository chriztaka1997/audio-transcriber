import os
from fastapi import APIRouter, HTTPException

from .models import JobCreate

router = APIRouter()


def get_queue_manager():
    """Injected at startup via app.state."""
    from .main import app
    return app.state.queue_manager


@router.post("/api/jobs")
async def create_job(job_create: JobCreate):
    qm = get_queue_manager()
    job = await qm.add_job(job_create)
    return job.model_dump()


@router.get("/api/jobs")
async def list_jobs():
    qm = get_queue_manager()
    jobs = await qm.get_all_jobs()
    return [j.model_dump() for j in jobs]


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    qm = get_queue_manager()
    job = await qm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()


@router.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    qm = get_queue_manager()
    job = await qm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await qm.cancel_job(job_id)
    return {"status": "cancelled"}


@router.get("/api/models")
async def list_models():
    return ["tiny", "base", "small", "medium", "large", "turbo"]


@router.post("/api/validate-dir")
async def validate_dir(body: dict):
    path = body.get("path", "")
    if not path:
        return {"valid": False, "error": "Path is empty"}
    expanded = os.path.expanduser(path)
    if os.path.isdir(expanded) and os.access(expanded, os.W_OK):
        return {"valid": True, "resolved": expanded}
    if not os.path.exists(expanded):
        # Try creating it
        try:
            os.makedirs(expanded, exist_ok=True)
            return {"valid": True, "resolved": expanded}
        except OSError as e:
            return {"valid": False, "error": str(e)}
    return {"valid": False, "error": "Path is not a writable directory"}
