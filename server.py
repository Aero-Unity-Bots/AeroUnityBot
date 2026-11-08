import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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
async def stream_video(token: str):
    """
    Fetches the direct Telegram file URL and redirects the browser 
    to Telegram's ultra-fast CDN servers for instant playback and seeking.
    """
    file_data = FILE_DATABASE.get(token)
    if not file_data:
        raise HTTPException(status_code=404, detail="File not found.")

    message = file_data["message"]
    media = message.document or message.video or message.audio
    
    try:
        # Get direct file access link from Telegram servers
        file_info = await app_client.get_file(media.file_id)
        direct_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        return RedirectResponse(url=direct_url, status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not fetch stream: {str(e)}")

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
