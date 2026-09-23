import asyncio
import os
import re
from datetime import date
from typing import Callable

import yt_dlp

from .models import Job


def _slugify(text: str) -> str:
    text = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[-\s]+', '-', text).strip('-')


def _format_speed(speed: float | None) -> str | None:
    if speed is None:
        return None
    if speed >= 1_000_000:
        return f"{speed / 1_000_000:.1f} MB/s"
    elif speed >= 1_000:
        return f"{speed / 1_000:.1f} KB/s"
    return f"{speed:.0f} B/s"


def _get_video_name(job: Job) -> str:
    if job.video_name:
        return job.video_name
    return f"video-{date.today().isoformat()}"


async def download_video(job: Job, progress_callback: Callable) -> str:
    video_name = _get_video_name(job)
    os.makedirs(job.output_dir, exist_ok=True)
    outtmpl = os.path.join(job.output_dir, f"{video_name}.%(ext)s")

    final_path = None

    def _progress_hook(d):
        nonlocal final_path
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            pct = (downloaded / total * 100) if total > 0 else 0
            speed = d.get('speed')
            progress_callback(pct, _format_speed(speed))
        elif d['status'] == 'finished':
            final_path = d.get('filename', '')
            progress_callback(100, None)

    ydl_opts = {
        'outtmpl': outtmpl,
        'progress_hooks': [_progress_hook],
        'no_check_certificate': True,
        'quiet': True,
        'no_warnings': True,
    }

    def _do_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([job.url])

    await asyncio.to_thread(_do_download)

    if final_path and os.path.exists(final_path):
        return final_path

    # yt-dlp may have merged to mp4
    for ext in ['mp4', 'mkv', 'webm', 'ts']:
        candidate = os.path.join(job.output_dir, f"{video_name}.{ext}")
        if os.path.exists(candidate):
            return candidate

    raise RuntimeError(f"Download completed but output file not found in {job.output_dir}")
