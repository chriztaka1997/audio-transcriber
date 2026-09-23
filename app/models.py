from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class JobStatus(str, Enum):
    queued = "queued"
    downloading = "downloading"
    downloaded = "downloaded"
    transcribing = "transcribing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobCreate(BaseModel):
    url: str
    output_dir: str
    video_name: Optional[str] = None
    transcript_name: Optional[str] = None
    whisper_model: str = "turbo"
    language: str = "en"
    generate_srt: bool = False


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    output_dir: str
    video_name: Optional[str] = None
    transcript_name: Optional[str] = None
    whisper_model: str = "turbo"
    language: str = "en"
    generate_srt: bool = False
    status: JobStatus = JobStatus.queued
    download_progress: float = 0.0
    download_speed: Optional[str] = None
    transcribe_progress: float = 0.0
    video_path: Optional[str] = None
    transcript_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class ProgressUpdate(BaseModel):
    job_id: str
    type: str  # "download" | "transcribe" | "status"
    progress: float = 0.0
    speed: Optional[str] = None
    status: JobStatus
    error: Optional[str] = None
