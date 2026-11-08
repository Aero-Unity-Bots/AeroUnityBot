import re
import mimetypes

CHUNK = 1024 * 1024

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
