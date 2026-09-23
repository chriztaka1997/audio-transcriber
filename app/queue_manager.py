import asyncio
from typing import Optional

from .database import Database
from .downloader import download_video
from .models import Job, JobCreate, JobStatus, ProgressUpdate
from .transcriber import transcribe_video
from .ws import WebSocketManager


class QueueManager:
    def __init__(self, db: Database, ws_manager: WebSocketManager):
        self.db = db
        self.ws_manager = ws_manager
        self.jobs: dict[str, Job] = {}
        self.transcribe_queue: asyncio.Queue[str] = asyncio.Queue()
        self._transcribe_task: Optional[asyncio.Task] = None
        self._download_tasks: dict[str, asyncio.Task] = {}

    async def add_job(self, job_create: JobCreate) -> Job:
        job = Job(
            url=job_create.url,
            output_dir=job_create.output_dir,
            video_name=job_create.video_name,
            transcript_name=job_create.transcript_name,
            whisper_model=job_create.whisper_model,
            generate_srt=job_create.generate_srt,
        )
        self.jobs[job.id] = job
        await self.db.save_job(job)
        await self._broadcast_job(job)
        self._start_download(job.id)
        return job

    async def cancel_job(self, job_id: str):
        job = self.jobs.get(job_id)
        if not job:
            return
        job.status = JobStatus.cancelled
        await self.db.save_job(job)
        await self._broadcast_job(job)
        # Cancel download task if running
        task = self._download_tasks.get(job_id)
        if task and not task.done():
            task.cancel()

    async def get_job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    async def get_all_jobs(self) -> list[Job]:
        return list(self.jobs.values())

    async def resume_jobs(self):
        """Load jobs from DB and resume interrupted ones."""
        all_jobs = await self.db.get_all_jobs()
        for job in all_jobs:
            self.jobs[job.id] = job

        resumable = await self.db.get_resumable_jobs()
        for job in resumable:
            if job.status in (JobStatus.queued, JobStatus.downloading):
                # Restart download from scratch
                job.status = JobStatus.queued
                job.download_progress = 0.0
                await self.db.save_job(job)
                self._start_download(job.id)
            elif job.status in (JobStatus.downloaded, JobStatus.transcribing):
                # Skip download, re-queue for transcription
                job.status = JobStatus.downloaded
                job.transcribe_progress = 0.0
                await self.db.save_job(job)
                await self.transcribe_queue.put(job.id)
                self._ensure_transcription_worker()

    def _start_download(self, job_id: str):
        task = asyncio.create_task(self._download_job(job_id))
        self._download_tasks[job_id] = task

    def _ensure_transcription_worker(self):
        if self._transcribe_task is None or self._transcribe_task.done():
            self._transcribe_task = asyncio.create_task(self._transcription_worker())

    async def _download_job(self, job_id: str):
        job = self.jobs.get(job_id)
        if not job or job.status == JobStatus.cancelled:
            return

        try:
            job.status = JobStatus.downloading
            await self.db.save_job(job)
            await self._broadcast_job(job)

            loop = asyncio.get_running_loop()

            def on_download_progress(pct: float, speed: str | None):
                job.download_progress = pct
                job.download_speed = speed
                loop.call_soon_threadsafe(
                    loop.create_task,
                    self._save_and_broadcast_progress(job, "download"),
                )

            video_path = await download_video(job, on_download_progress)
            job.video_path = video_path
            job.status = JobStatus.downloaded
            job.download_progress = 100
            await self.db.save_job(job)
            await self._broadcast_job(job)

            # Queue for transcription
            await self.transcribe_queue.put(job_id)
            self._ensure_transcription_worker()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            job.status = JobStatus.failed
            job.error = str(e)
            await self.db.save_job(job)
            await self._broadcast_job(job)
        finally:
            self._download_tasks.pop(job_id, None)

    async def _transcription_worker(self):
        while True:
            try:
                job_id = await asyncio.wait_for(self.transcribe_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No more jobs in queue
                break

            job = self.jobs.get(job_id)
            if not job or job.status == JobStatus.cancelled:
                continue

            try:
                job.status = JobStatus.transcribing
                await self.db.save_job(job)
                await self._broadcast_job(job)

                async def on_transcribe_progress(pct: float):
                    job.transcribe_progress = pct
                    await self._save_and_broadcast_progress(job, "transcribe")

                transcript_path = await transcribe_video(job, on_transcribe_progress)
                job.transcript_path = transcript_path
                job.status = JobStatus.completed
                job.transcribe_progress = 100
                await self.db.save_job(job)
                await self._broadcast_job(job)

            except Exception as e:
                job.status = JobStatus.failed
                job.error = str(e)
                await self.db.save_job(job)
                await self._broadcast_job(job)

    async def _save_and_broadcast_progress(self, job: Job, progress_type: str):
        progress = job.download_progress if progress_type == "download" else job.transcribe_progress
        update = ProgressUpdate(
            job_id=job.id,
            type=progress_type,
            progress=progress,
            speed=job.download_speed if progress_type == "download" else None,
            status=job.status,
        )
        await self.ws_manager.broadcast(update.model_dump())

    async def _broadcast_job(self, job: Job):
        await self.ws_manager.broadcast({
            "type": "job_update",
            "job": job.model_dump(),
        })
