"""Governed first-time PRIVATE YouTube upload from shared Video IR.

No CLI autopublish. This adapter is callable only after the existing ONE/runtime
authorizes the effect and binds the correct YouTube channel. Failed or interrupted
uploads are ambiguous and MUST be reconciled, never blindly repeated.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from local_video_ingest import sha256_file
from video_ir_indexing import SCHEMA


def _persist(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _validate(ir: dict, title: str, description: str, authorized: bool) -> Path:
    if not authorized:
        raise PermissionError("ONE effect authorization required for YouTube upload")
    if ir.get("schema_version") != SCHEMA:
        raise ValueError("unsupported IR schema")
    if ir.get("indexing", {}).get("status") != "indexed":
        raise ValueError("must index video before publishing")
    if ir.get("transcription", {}).get("status") not in ("transcribed", "no_speech"):
        raise ValueError("must transcribe video or verify no-speech before publishing")
    if not isinstance(title, str) or not (1 <= len(title.strip()) <= 100):
        raise ValueError("invalid YouTube title")
    if not isinstance(description, str) or len(description) > 5000:
        raise ValueError("invalid description")
    media = Path(ir["source_path"])
    if not media.is_file() or sha256_file(media) != ir["source_sha256"]:
        raise ValueError("original video missing or changed")
    return media


def publish_private(ir_path: str, *, youtube, media_factory, title: str,
                    description: str, authorized: bool = False,
                    channel_verified: bool = False, category_id: str = "22",
                    max_chunks: int = 100000) -> dict:
    """Only externally-authorized callers should provide a bound YouTube client.

    The caller must verify the channel identity against a separately authorized
    account/profile; this function never discovers credentials or starts OAuth.
    """
    path = Path(ir_path)
    ir = json.loads(path.read_text(encoding="utf-8"))
    if not channel_verified:
        raise PermissionError("target YouTube channel identity is not verified")
    media = _validate(ir, title, description, authorized)
    publication = ir.get("publication") or {}
    if publication.get("status") == "uploaded_private" and publication.get("youtube_video_id"):
        return ir
    if publication.get("status") in ("upload_in_progress", "reconciliation_required"):
        raise RuntimeError("previous upload may have succeeded; reconcile remote video ID before retry")
    if publication.get("youtube_video_id"):
        raise RuntimeError("existing YouTube video ID requires explicit reconciliation")
    # Durable ambiguous-state barrier BEFORE external upload request.
    ir["publication"] = {
        "status": "upload_in_progress", "youtube_video_id": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "privacy": "private",
    }
    _persist(path, ir)
    try:
        media_body = media_factory(str(media))
        request = youtube.videos().insert(
            part="snippet,status",
            body={"snippet":{"title":title.strip(), "description":description,
                             "categoryId":category_id},
                  "status":{"privacyStatus":"private"}},
            media_body=media_body,
        )
        response = None
        for _ in range(max_chunks):
            _, response = request.next_chunk()
            if response is not None:
                break
        if not isinstance(response, dict) or not response.get("id"):
            raise RuntimeError("YouTube returned no successful video ID")
        video_id = response["id"]
        if not isinstance(video_id, str) or not video_id.strip():
            raise RuntimeError("invalid YouTube video ID")
        ir["publication"].update({
            "status":"uploaded_private", "youtube_video_id":video_id,
            "url":"https://www.youtube.com/watch?v=" + video_id,
            "completed_at":datetime.now(timezone.utc).isoformat(),
        })
        _persist(path, ir)
        return ir
    except Exception:
        ir["publication"]["status"] = "reconciliation_required"
        _persist(path, ir)
        raise


def google_media_factory(path: str):
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(path, mimetype="video/*", chunksize=8 * 1024 * 1024, resumable=True)
