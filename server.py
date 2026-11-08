import os
import subprocess
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Aero_Unity File Stream Server")
templates = Jinja2Templates(directory="templates")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

FILE_DATABASE = {}

app_client = Client(
    "AeroUnityStreamSession",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

@app.on_event("startup")
async def startup_event():
    await app_client.start()

@app.on_event("shutdown")
async def shutdown_event():
    await app_client.stop()

@app.get("/watch/{token}", response_class=HTMLResponse)
async def watch_file(request: Request, token: str):
    file_data = FILE_DATABASE.get(token)
    if not file_data:
        raise HTTPException(status_code=404, detail="Link expired or file not found.")
    
    base_url = str(request.base_url).rstrip("/")
    stream_url = f"{base_url}/stream/{token}"
    download_url = f"{base_url}/dl/{token}"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "file_name": file_data["file_name"],
        "file_size": file_data["file_size_formatted"],
        "stream_url": stream_url,
        "download_url": download_url
    })

@app.get("/stream/{token}")
async def stream_video(request: Request, token: str):
    """
    Real-time FFmpeg transcoding pipeline. Pulls raw chunks from Telegram 
    and transcodes them on-the-fly into an HTML5-compatible MP4 stream 
    so mobile browsers can play MKV files instantly.
    """
    file_data = FILE_DATABASE.get(token)
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found.")

    message = file_data["message"]
    file_size = file_data["file_size"]

    async def telegram_generator():
        try:
            async for chunk in app_client.stream_media(message):
                yield chunk
        except Exception:
            pass

    # FFmpeg command to transcode MKV/Audio on-the-fly into browser-ready MP4/H.264/AAC
    cmd = [
        "ffmpeg",
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "frag_keyframe+empty_moov+faststart",
        "-f", "mp4",
        "pipe:1"
    ]

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )

    import asyncio
    async def feed_ffmpeg():
        try:
            async for chunk in telegram_generator():
                process.stdin.write(chunk)
                process.stdin.flush()
        except Exception:
            pass
        finally:
            try:
                process.stdin.close()
            except Exception:
                pass

    asyncio.create_task(feed_ffmpeg())

    def response_generator():
        try:
            while True:
                data = process.stdout.read(32768)
                if not data:
                    break
                yield data
        except Exception:
            pass
        finally:
            if process.poll() is None:
                process.terminate()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
    }

    return StreamingResponse(response_generator(), status_code=200, headers=headers)

@app.get("/dl/{token}")
async def download_file(token: str):
    file_data = FILE_DATABASE.get(token)
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found.")

    message = file_data["message"]
    file_size = file_data["file_size"]
    file_name = file_data["file_name"]

    async def download_generator():
        async for chunk in app_client.stream_media(message):
            yield chunk

    headers = {
        "Content-Disposition": f"attachment; filename=\"{file_name}\"",
        "Content-Length": str(file_size),
        "Content-Type": "application/octet-stream",
        "X-Content-Type-Options": "nosniff"
    }
    return StreamingResponse(download_generator(), headers=headers)
