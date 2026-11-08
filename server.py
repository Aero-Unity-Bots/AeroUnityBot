import os
import re
import mimetypes
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

CHUNK = 1024 * 1024

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
    file_data = FILE_DATABASE.get(token)
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found.")

    message = file_data["message"]
    size = file_data["file_size"]
    name = file_data["file_name"]
    mime = mimetypes.guess_type(name)[0] or "video/mp4"

    start, end, status = 0, size - 1, 200
    rng = request.headers.get("range")
    if rng:
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m:
            s, e = m.groups()
            if s == "" and e:
                start = max(size - int(e), 0)
            else:
                if s:
                    start = int(s)
                if e:
                    end = min(int(e), size - 1)
            if start > end or start >= size:
                raise HTTPException(status_code=416, detail="Bad range")
            status = 206

    first = start // CHUNK
    nchunks = end // CHUNK - first + 1

    async def gen():
        skip = start % CHUNK
        remaining = end - start + 1
        try:
            async for chunk in app_client.stream_media(message, limit=nchunks, offset=first):
                if skip:
                    chunk, skip = chunk[skip:], 0
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]
                yield chunk
                remaining -= len(chunk)
                if remaining <= 0:
                    break
        except Exception:
            pass

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Disposition": "inline",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    return StreamingResponse(gen(), status_code=status, headers=headers, media_type=mime)

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
