"""Attachment upload + retrieval. Files are written to a local directory
(overridable via ATTACHMENTS_DIR) and metadata is stored in MongoDB.
In production swap this for S3/GCS by replacing the `store_*` helpers."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import current_user
from app.db import mongo
from app.services.audit import log_action

log = logging.getLogger(__name__)
router = APIRouter(prefix="/attachments", tags=["attachments"])

ALLOWED_KIND = {"image", "file"}
MAX_BYTES = 20 * 1024 * 1024
# Dangerous extensions never allowed (polyglot or executable)
_BLOCKED_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".pif",
    ".sh", ".bash", ".zsh", ".ksh",
    ".ps1", ".psm1", ".psd1",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".hta", ".html", ".htm", ".xhtml", ".svg",
    ".jar", ".class",
    ".app", ".gadget",
    ".dll", ".sys", ".drv",
    ".reg", ".inf",
})
# Magic bytes for MIME content validation
_MIME_MAGIC: dict[str, list[tuple[int, bytes]]] = {
    "image/jpeg": [(0, b"\xff\xd8\xff")],
    "image/png": [(0, b"\x89PNG\r\n\x1a\n")],
    "image/gif": [(0, b"GIF87a"), (0, b"GIF89a")],
    "image/webp": [(8, b"WEBP")],
    "image/bmp": [(0, b"BM")],
    "application/pdf": [(0, b"%PDF")],
    "text/plain": [],
    "text/markdown": [],
    "text/csv": [],
    "application/json": [],
    "application/zip": [(0, b"PK\x03\x04")],
}


def _validate_content_type(content_type: str | None, blob: bytes, filename: str | None) -> str:
    """Validate MIME type against magic bytes and block dangerous files."""
    if not content_type or content_type == "application/octet-stream":
        # Try to detect from content
        if blob[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if blob[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if blob[:4] == b"%PDF":
            return "application/pdf"
        raise HTTPException(400, "unknown file type")

    ext = (Path(filename or "").suffix or "").lower()[:16] if filename else ""
    if ext in _BLOCKED_EXTENSIONS:
        raise HTTPException(400, f"file extension '.{ext}' is not allowed")

    # Validate magic bytes where we have known signatures
    sigs = _MIME_MAGIC.get(content_type)
    if sigs is not None:
        if sigs:
            matched = any(blob[offset:offset + len(magic)] == magic for offset, magic in sigs)
            if not matched:
                raise HTTPException(400, f"content does not match declared type '{content_type}'")
    elif content_type.startswith("image/"):
        # Unknown image type - reject
        raise HTTPException(400, f"unsupported image type '{content_type}'")

    return content_type


def _storage_dir() -> Path:
    base = os.environ.get("ATTACHMENTS_DIR") or os.path.join(os.getcwd(), "attachments")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


class AttachmentOut(BaseModel):
    id: str
    kind: Literal["image", "file"]
    mimeType: str
    size: int
    originalName: str
    url: str
    createdAt: datetime


def _detect_kind(mime: str) -> str:
    return "image" if mime.startswith("image/") else "file"


@router.post("", response_model=AttachmentOut, status_code=201)
async def upload(user=Depends(current_user), file: UploadFile = File(...)) -> AttachmentOut:
    blob = await file.read()
    if len(blob) > MAX_BYTES:
        raise HTTPException(413, "file too large")
    mime_type = _validate_content_type(file.content_type, blob, file.filename)
    # Enforce per-user storage quota (200 MB per user)
    user_total = await mongo.attachments().aggregate([
        {"$match": {"userId": user["_id"]}},
        {"$group": {"_id": None, "total": {"$sum": "$size"}}},
    ]).to_list(length=1)
    current_used = user_total[0]["total"] if user_total else 0
    if current_used + len(blob) > 200 * 1024 * 1024:
        raise HTTPException(413, "storage quota exceeded (200 MB per user)")
    digest = hashlib.sha256(blob).hexdigest()
    ext = Path(file.filename or "").suffix[:16] or ""
    storage_key = f"{digest[:2]}/{digest}{ext}"
    full_path = _storage_dir() / storage_key
    full_path.parent.mkdir(parents=True, exist_ok=True)
    if not full_path.exists():
        full_path.write_bytes(blob)
    now = datetime.now(tz=UTC)
    doc = {
        "userId": user["_id"],
        "kind": _detect_kind(mime_type),
        "mimeType": mime_type,
        "size": len(blob),
        "originalName": (file.filename or "file")[:255],
        "storageKey": storage_key,
        "sha256": digest,
        "createdAt": now,
    }
    res = await mongo.attachments().insert_one(doc)
    await log_action(actor_id=str(user["_id"]), action="attachment.upload", resource=f"attachment:{res.inserted_id}")
    return AttachmentOut(
        id=str(res.inserted_id),
        kind=doc["kind"],
        mimeType=doc["mimeType"],
        size=doc["size"],
        originalName=doc["originalName"],
        url=f"/api/v1/attachments/{res.inserted_id}",
        createdAt=now,
    )


@router.get("/{attachment_id}")
async def download(attachment_id: str, user=Depends(current_user)):
    if not ObjectId.is_valid(attachment_id):
        raise HTTPException(400, "invalid id")
    doc = await mongo.attachments().find_one({"_id": ObjectId(attachment_id)})
    if not doc:
        raise HTTPException(404, "not found")
    if str(doc["userId"]) != str(user["_id"]):
        raise HTTPException(403, "forbidden")
    path = _storage_dir() / doc["storageKey"]
    if not path.exists():
        raise HTTPException(410, "file gone")
    return FileResponse(path, media_type=doc["mimeType"], filename=doc["originalName"])


@router.delete("/{attachment_id}", status_code=204)
async def remove(attachment_id: str, user=Depends(current_user)) -> None:
    if not ObjectId.is_valid(attachment_id):
        raise HTTPException(400, "invalid id")
    res = await mongo.attachments().delete_one({"_id": ObjectId(attachment_id), "userId": user["_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "not found")
    await log_action(actor_id=str(user["_id"]), action="attachment.delete", resource=f"attachment:{attachment_id}")
