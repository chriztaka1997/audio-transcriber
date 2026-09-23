import aiosqlite
import os
from datetime import datetime
from .models import Job, JobStatus


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jobs.db")


class Database:
    def __init__(self):
        self.db_path = DB_PATH

    async def init(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    video_name TEXT,
                    transcript_name TEXT,
                    whisper_model TEXT DEFAULT 'turbo',
                    language TEXT DEFAULT 'en',
                    generate_srt BOOLEAN DEFAULT 0,
                    status TEXT DEFAULT 'queued',
                    download_progress REAL DEFAULT 0,
                    transcribe_progress REAL DEFAULT 0,
                    video_path TEXT,
                    transcript_path TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            await db.commit()

    async def save_job(self, job: Job):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO jobs (id, url, output_dir, video_name, transcript_name,
                    whisper_model, language, generate_srt, status, download_progress,
                    transcribe_progress, video_path, transcript_path, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    download_progress=excluded.download_progress,
                    transcribe_progress=excluded.transcribe_progress,
                    video_path=excluded.video_path,
                    transcript_path=excluded.transcript_path,
                    error=excluded.error
            """, (
                job.id, job.url, job.output_dir, job.video_name, job.transcript_name,
                job.whisper_model, job.language, job.generate_srt, job.status.value,
                job.download_progress, job.transcribe_progress,
                job.video_path, job.transcript_path, job.error,
                job.created_at.isoformat()
            ))
            await db.commit()

    async def get_job(self, job_id: str) -> Job | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_job(row)
                return None

    async def get_all_jobs(self) -> list[Job]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM jobs ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_job(row) for row in rows]

    async def get_resumable_jobs(self) -> list[Job]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM jobs WHERE status IN (?, ?, ?, ?) ORDER BY created_at ASC",
                ("queued", "downloading", "downloaded", "transcribing")
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_job(row) for row in rows]

    async def delete_job(self, job_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            await db.commit()

    def _row_to_job(self, row) -> Job:
        return Job(
            id=row["id"],
            url=row["url"],
            output_dir=row["output_dir"],
            video_name=row["video_name"],
            transcript_name=row["transcript_name"],
            whisper_model=row["whisper_model"],
            language=row["language"] or "en",
            generate_srt=bool(row["generate_srt"]),
            status=JobStatus(row["status"]),
            download_progress=row["download_progress"] or 0.0,
            transcribe_progress=row["transcribe_progress"] or 0.0,
            video_path=row["video_path"],
            transcript_path=row["transcript_path"],
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
