"""Sanitized source-side receipt projection for existing AgentOS ONE.

This intentionally does NOT write to ONE or claim an accepted canonical receipt.
Runtime must submit it via existing authorized receipt transport and persist the
ONE-side acceptance ID separately.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

SCHEMA = "agentos.media-pipeline-source-receipt/v1"
TERMINAL = {"uploaded_private", "reconciliation_required"}


def project_media_receipt(ir_path: str) -> dict:
    ir = json.loads(Path(ir_path).read_text(encoding="utf-8"))
    if ir.get("schema_version") != "video-ir/0.1":
        raise ValueError("unsupported Video IR")
    asset_id = ir.get("asset_id")
    source_hash = ir.get("source_sha256")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        raise ValueError("missing SHA-256 provenance")
    if asset_id != "sha256:" + source_hash:
        raise ValueError("asset identity mismatch")
    publication = ir.get("publication") or {}
    state = publication.get("status", "not_started")
    video_id = publication.get("youtube_video_id")
    remote_confirmed = (
        state == "uploaded_private"
        and isinstance(video_id, str) and bool(video_id.strip())
        and publication.get("privacy") == "private"
    )
    if state == "uploaded_private" and not remote_confirmed:
        raise ValueError("uploaded state has no validated local API response")
    return {
        "schema_version": SCHEMA,
        "asset_id": asset_id,
        "source_hash": source_hash,
        "indexing_status": ir.get("indexing", {}).get("status", "unknown"),
        "transcription_status": ir.get("transcription", {}).get("status", "unknown"),
        "publication_status": state,
        "remote_api_response_recorded": remote_confirmed,
        "youtube_video_id": video_id if remote_confirmed else None,
        "youtube_url": (
            "https://www.youtube.com/watch?v=" + video_id if remote_confirmed else None
        ),
        "one_receipt_status": "not_submitted",
        "one_accepted_receipt_id": None,
        "growth_proof_status": "unverified",
    }
