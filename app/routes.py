import asyncio
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


@router.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    qm = get_queue_manager()
    job = await qm.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status.value not in ("failed", "cancelled"):
        raise HTTPException(status_code=400, detail="Only failed or cancelled jobs can be retried")
    await qm.retry_job(job_id)
    return {"status": "retrying"}


@router.get("/api/models")
async def list_models():
    return ["tiny", "base", "small", "medium", "large", "turbo"]


@router.post("/api/jobs/transcribe-only")
async def create_transcribe_only_job(body: dict):
    video_path = body.get("video_path", "")
    output_dir = body.get("output_dir", "")
    transcript_name = body.get("transcript_name", None)
    whisper_model = body.get("whisper_model", "turbo")
    language = body.get("language", "en")
    generate_srt = body.get("generate_srt", False)

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail=f"File not found: {video_path}")
    if not output_dir:
        output_dir = os.path.dirname(video_path)

    from .models import JobCreate
    job_create = JobCreate(
        url="local://" + video_path,
        output_dir=output_dir,
        video_name=os.path.splitext(os.path.basename(video_path))[0],
        transcript_name=transcript_name,
        whisper_model=whisper_model,
        language=language,
        generate_srt=generate_srt,
    )
    qm = get_queue_manager()
    job = await qm.add_transcribe_only_job(job_create, video_path)
    return job.model_dump()


@router.post("/api/pick-file")
async def pick_file():
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e",
        'POSIX path of (choose file with prompt "Select video/audio file" of type {"public.movie", "public.audio"})',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    file_path = stdout.decode().strip()
    if file_path:
        return {"path": file_path}
    return {"path": None}


@router.post("/api/pick-folder")
async def pick_folder():
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e",
        'POSIX path of (choose folder with prompt "Select destination folder")',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    folder = stdout.decode().strip().rstrip("/")
    if folder:
        return {"path": folder}
    return {"path": None}
