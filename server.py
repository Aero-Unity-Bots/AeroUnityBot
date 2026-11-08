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
    Pulls chunks from Telegram via Pyrogram and pipes them 
    through FFmpeg to transcode on-the-fly into browser-compatible MP4 format.
    """
    file_data = FILE_DATABASE.get(token)
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found.")

    message = file_data["message"]

    async def telegram_chunk_generator():
        async for chunk in app_client.stream_media(message):
            yield chunk

    # Start an FFmpeg background process to transcode the incoming binary stream to web MP4
    # This solves black screens, codec issues, and playback hanging.
    cmd = [
        "ffmpeg",
        "-i", "pipe:0",               # Read input from pipe (Telegram stream)
        "-c:v", "libx264",            # Transcode video to H.264
        "-preset", "ultrafast",       # Fast processing preset for cloud hosting
        "-c:a", "aac",                # Transcode audio to AAC (browser compatible)
        "-movflags", "frag_keyframe+empty_moov", # Enable fast streaming start
        "-f", "mp4",                  # Output format
        "pipe:1"                      # Output to stdout pipe
    ]

    process = None
    try:
        # Pipe input from telegram generator and read transcoded output chunks
        import asyncio
        
        # We use an async generator wrapper around ffmpeg subprocess pipe
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        async def feed_ffmpeg():
            try:
                async for chunk in telegram_chunk_generator():
                    process.stdin.write(chunk)
                    process.stdin.flush()
            except Exception:
                pass
            finally:
                try:
                    process.stdin.close()
                except Exception:
                    pass

        # Run feed task in background while yielding output chunks
        asyncio.create_task(feed_ffmpeg())

        def output_generator():
            while True:
                data = process.stdout.read(65536)
                if not data:
                    break
                yield data

        return StreamingResponse(output_generator(), media_type="video/mp4")

    except Exception as e:
        if process:
            process.terminate()
        raise HTTPException(status_code=500, detail=f"Streaming error: {str(e)}")

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
