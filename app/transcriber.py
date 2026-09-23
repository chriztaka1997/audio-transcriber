import asyncio
import os
import re
import shutil
from typing import Callable

from .models import Job


async def _get_audio_duration(file_path: str) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        file_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return 0.0


def _parse_timestamp(ts: str) -> float:
    """Parse a timestamp like '00:01:30.500' or '01:30.500' to seconds."""
    parts = ts.strip().split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def _get_transcript_name(job: Job) -> str:
    if job.transcript_name:
        return job.transcript_name
    if job.video_name:
        return job.video_name
    return os.path.splitext(os.path.basename(job.video_path))[0]


async def transcribe_video(job: Job, progress_callback: Callable) -> str:
    if not job.video_path or not os.path.exists(job.video_path):
        raise RuntimeError(f"Video file not found: {job.video_path}")

    whisper_bin = shutil.which("whisper")
    if not whisper_bin:
        raise RuntimeError("whisper CLI not found. Install with: pip install openai-whisper")

    total_duration = await _get_audio_duration(job.video_path)

    output_format = "txt"
    if job.generate_srt:
        output_format = "txt,srt"

    transcript_name = _get_transcript_name(job)
    os.makedirs(job.output_dir, exist_ok=True)

    cmd = [
        whisper_bin,
        job.video_path,
        "--model", job.whisper_model,
        "--output_format", output_format,
        "--output_dir", job.output_dir,
        "--verbose", "True",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    # Whisper prints lines like: [00:00.000 --> 00:30.000] Some transcribed text
    timestamp_pattern = re.compile(r'\[(\d+:\d+[\d:.]*)\s*-->\s*(\d+:\d+[\d:.]*)\]')

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace")
        match = timestamp_pattern.search(line)
        if match and total_duration > 0:
            end_ts = _parse_timestamp(match.group(2))
            pct = min((end_ts / total_duration) * 100, 100)
            await progress_callback(pct)

    await proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"Whisper exited with code {proc.returncode}")

    await progress_callback(100)

    # Whisper saves output using the input filename stem
    input_stem = os.path.splitext(os.path.basename(job.video_path))[0]
    whisper_output = os.path.join(job.output_dir, f"{input_stem}.txt")

    # Rename to the desired transcript name if different
    final_txt = os.path.join(job.output_dir, f"{transcript_name}.txt")
    if whisper_output != final_txt and os.path.exists(whisper_output):
        os.rename(whisper_output, final_txt)

    if job.generate_srt:
        whisper_srt = os.path.join(job.output_dir, f"{input_stem}.srt")
        final_srt = os.path.join(job.output_dir, f"{transcript_name}.srt")
        if whisper_srt != final_srt and os.path.exists(whisper_srt):
            os.rename(whisper_srt, final_srt)

    if not os.path.exists(final_txt):
        raise RuntimeError(f"Transcript file not found at {final_txt}")

    return final_txt
