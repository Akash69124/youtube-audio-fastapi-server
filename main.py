from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import re
from pathlib import Path
import asyncio
from fastapi.responses import FileResponse

app = FastAPI(title="YouTube Audio Downloader API")

# Enable CORS for Flutter app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp3"

# Create downloads directory
DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

@app.post("/download")
async def download_audio(request: DownloadRequest):
    try:
        # Validate YouTube URL
        if "youtube.com" not in request.url and "youtu.be" not in request.url:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL")

        # yt-dlp options for audio extraction
        ydl_opts = {
            # 1. FIX: Use title only for cleaner file names (removed unique_id_)
            'outtmpl': f'{DOWNLOADS_DIR}/%(title)s.%(ext)s', 
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                # 2. SPEED FIX: Lower quality from 192 to 128 for faster conversion
                'preferredquality': '128', 
            }],
            # 3. PATH FIX: Use raw string (r'...') for reliable Windows path
            'ffmpeg_location': r'C:\ffmpeg\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe', 
        }

        # Download and extract audio
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # This part gets video info
            info = await asyncio.get_event_loop().run_in_executor(
                None, ydl.extract_info, request.url, False
            )
            title = info.get('title', 'Unknown')

            # This part performs the actual download
            await asyncio.get_event_loop().run_in_executor(
                None, ydl.download, [request.url]
            )

        # 4. FINDING FIX: Locate the downloaded file based on the title (no unique ID)
        
        # Sanitize the title to match how Windows and yt-dlp clean filenames
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)

        # Search for files created recently matching the title
        # glob looks for files starting with the sanitized title and ending in .mp3
        downloaded_files = list(DOWNLOADS_DIR.glob(f"{safe_title}*.mp3"))

        if not downloaded_files:
            # If the search fails (e.g., due to complex characters), try to find the newest .mp3 file
            import os
            downloaded_files = [f for f in DOWNLOADS_DIR.iterdir() if f.is_file() and f.suffix == '.mp3']
            if downloaded_files:
                downloaded_files.sort(key=os.path.getctime, reverse=True)

        if not downloaded_files:
            raise HTTPException(status_code=500, detail="Download failed: File not found after processing.")

        file_path = downloaded_files[0]
        filename = file_path.name
        
        return {
            "status": "success",
            "download_url": f"/file/{file_path.name}",
            "filename": filename, # This now contains the clean title
            "title": title,
            "file_size": file_path.stat().st_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@app.get("/file/{filename}")
async def get_file(filename: str):
    file_path = DOWNLOADS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type='audio/mpeg',
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/")
async def root():
    return {"message": "YouTube Audio Downloader API", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)