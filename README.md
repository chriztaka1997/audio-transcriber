# Audio Transcriber

A local web app to download videos and transcribe them using OpenAI's Whisper model. Built for extracting transcripts from lecture videos (e.g., Circle community platform).

## Features

- **Paste & download** — Supports HLS/m3u8 streams and direct video URLs via yt-dlp
- **Local transcription** — Uses Whisper locally (no data leaves your machine)
- **Job queue** — Submit multiple URLs at once; downloads run in parallel, transcriptions run sequentially
- **Real-time progress** — Live progress bars for both download and transcription via WebSocket
- **Persistent queue** — Jobs are stored in SQLite and automatically resume after restart/sleep
- **Custom output** — Pick destination folder and filenames for video and transcript

## Prerequisites

- Python 3.10+
- ffmpeg (`brew install ffmpeg`)

## Quick Start

```bash
./start.sh
```

This handles everything — creates a virtual environment, installs dependencies (first run only), and starts the server.

Open [http://localhost:8000](http://localhost:8000) in your browser.

1. Paste one or more video URLs (one per line)
2. Set the destination folder and optionally customize filenames
3. Pick a Whisper model (default: `turbo`)
4. Click "Add to Queue"

## Whisper Models

| Model | Speed | Quality | VRAM |
|-------|-------|---------|------|
| tiny | Fastest | Low | ~1 GB |
| base | Fast | Fair | ~1 GB |
| small | Moderate | Good | ~2 GB |
| medium | Slow | Great | ~5 GB |
| large | Slowest | Best | ~10 GB |
| turbo | Fast | Great | ~6 GB |

## Tech Stack

- **Backend:** FastAPI, yt-dlp, openai-whisper, aiosqlite
- **Frontend:** Vanilla HTML/CSS/JS (no framework)
