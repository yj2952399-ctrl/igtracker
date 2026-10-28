"""Safe shared image/video upload helpers for chat and DMs."""
from __future__ import annotations
import os, uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException

MEDIA_DIR = Path(os.getenv("CHAT_MEDIA_DIR", "data/chat_uploads"))
MAX_BYTES = int(os.getenv("CHAT_MEDIA_MAX_BYTES", str(20 * 1024 * 1024)))
ALLOWED = {
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".gif": ("image/gif", b"GIF8"),
    ".webp": ("image/webp", b"RIFF"),
    ".mp4": ("video/mp4", b""),
    ".webm": ("video/webm", b"\x1aE\xdf\xa3"),
    ".mov": ("video/quicktime", b""),
}

async def save_upload(upload: UploadFile):
    name = (upload.filename or "").replace("\\", "/").split("/")[-1]
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "対応していない形式です（JPG/PNG/GIF/WEBP/MP4/WEBM/MOV）")
    data = await upload.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(400, "空のファイルです")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"ファイルは{MAX_BYTES // (1024*1024)}MB以下にしてください")
    mime, magic = ALLOWED[ext]
    if magic and not data.startswith(magic):
        raise HTTPException(415, "ファイル内容と拡張子が一致しません")
    if ext == ".webp" and data[8:12] != b"WEBP":
        raise HTTPException(415, "WEBPファイルとして認識できません")
    if ext in (".mp4", ".mov") and b"ftyp" not in data[:32]:
        raise HTTPException(415, "動画ファイルとして認識できません")
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex + ext
    dest = MEDIA_DIR / token
    dest.write_bytes(data)
    kind = "video" if mime.startswith("video/") else "image"
    return {"filename": token, "url": "/chat/media/" + token, "type": kind,
            "mime": mime, "name": name[:180], "size": len(data)}
