import os
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

# In-memory database mapping tokens to file items
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
    file_data = FILE_DATABASE.get(token)
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found.")

    message = file_data["message"]
    file_size = file_data["file_size"]
    
    range_header = request.headers.get("Range")
    from_bytes, to_bytes = 0, file_size - 1

    if range_header:
        try:
            parts = range_header.replace("bytes=", "").split("-")
            from_bytes = int(parts[0])
            if len(parts) > 1 and parts[1]:
                to_bytes = int(parts[1])
        except ValueError:
            pass

    chunk_size = 1024 * 1024  # 1MB
    
    async def file_generator():
        current = from_bytes
        async for chunk in app_client.stream_media(message, offset=current // chunk_size, limit=0):
            yield chunk

    headers = {
        "Content-Range": f"bytes {from_bytes}-{to_bytes}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str((to_bytes - from_bytes) + 1),
        "Content-Type": "video/mp4",
    }
    
    return StreamingResponse(file_generator(), status_code=206, headers=headers)

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

    # Forces browser download window/prompt on Chrome
    headers = {
        "Content-Disposition": f"attachment; filename=\"{file_name}\"",
        "Content-Length": str(file_size),
        "Content-Type": "application/octet-stream",
        "X-Content-Type-Options": "nosniff"
    }
    return StreamingResponse(download_generator(), headers=headers)
