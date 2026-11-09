"""Optional Gemini video index backend for the existing YouTube AI Manager.

Uses official google-genai file upload; source media is never deleted.
Cloud transfer requires explicit --allow-cloud-upload and the existing AgentOS
authorization must also be checked by the invoking Runtime/ONE adapter.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from local_video_ingest import ingest
from video_ir_indexing import accept_index

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_BYTES = 150 * 1024 * 1024
PROMPT = """Analyze the supplied video without assuming a particular game, language or genre.
Return ONLY JSON: {"observations":[{"time":"MM:SS","event":"description of what is visibly happening","evidence":"frame:MM:SS","confidence":0.0}]}.
Use actual visible footage, not the filename. Describe 3-6 useful scene changes/events IF there is enough evidence.
Timestamps must be within the clip duration. Confidence must be 0 to 1. Do not fabricate dialogue,
game mechanics, subtitle text, or events. If insufficient evidence return an empty observations array.
Each event should be a concise neutral statement. The evidence field is a model-reported video
timecode, NOT proof of independently verified frames.
"""


def _observations_from_response(raw: str) -> list:
    value = json.loads(raw)
    if not isinstance(value, dict) or not isinstance(value.get("observations"), list):
        raise ValueError("model must return an observations JSON array")
    return value["observations"]


def index_local_video(path: str, ir_dir: str, *, allow_cloud_upload: bool,
                      source: str = "local", model: str = DEFAULT_MODEL,
                      client=None, timeout_seconds: int = 300):
    if not allow_cloud_upload:
        raise PermissionError("explicit cloud upload consent required")
    if not (30 <= timeout_seconds <= 3600):
        raise ValueError("timeout_seconds must be 30..3600")
    media = Path(path).expanduser()
    ir_path, ir = ingest(str(media), ir_dir, source)
    if ir["indexing"].get("status") == "indexed":
        return ir_path, ir   # idempotent: don't re-upload same indexed source
    if media.stat().st_size > MAX_BYTES:
        raise ValueError("video exceeds bounded cloud indexing limit; segment first")
    if client is None:
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Gemini credential unavailable")
        from google import genai
        client = genai.Client(api_key=key)

    uploaded = None
    try:
        uploaded = client.files.upload(file=str(media))
        if not uploaded or not uploaded.name:
            raise RuntimeError("Gemini upload returned no file identity")
        deadline = time.monotonic() + timeout_seconds
        while True:
            state = getattr(getattr(uploaded, "state", None), "name", None)
            if state == "ACTIVE":
                break
            if state == "FAILED":
                raise RuntimeError("Gemini media processing failed")
            if time.monotonic() >= deadline:
                raise TimeoutError("Gemini media indexing timed out")
            time.sleep(5)
            uploaded = client.files.get(name=uploaded.name)

        result = client.models.generate_content(
            model=model, contents=[uploaded, PROMPT],
            config={"response_mime_type": "application/json"},
        )
        observations = _observations_from_response(result.text or "")
        if not observations:
            raise ValueError("model returned no reliable video observations")
        # Persist only duration-checked, evidence-bearing index. No YouTube write.
        updated = accept_index(str(ir_path), observations, provider="gemini-files", model=model)
        return ir_path, updated
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                # File cleanup failure must be observable by upstream monitoring;
                # do not delete any original user media to compensate.
                import logging
                logging.getLogger(__name__).exception("Unable to delete Gemini temp file")


def main():
    p = argparse.ArgumentParser(description="Local media -> Video IR -> Gemini index (never publish)")
    p.add_argument("video")
    p.add_argument("--ir-dir", default="video_ir")
    p.add_argument("--source", choices=("local", "wow", "obs", "other"), default="local")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--allow-cloud-upload", action="store_true",
                   help="Explicit consent to upload video to Gemini for indexing")
    args = p.parse_args()
    result_path, record = index_local_video(
        args.video, args.ir_dir, allow_cloud_upload=args.allow_cloud_upload,
        source=args.source, model=args.model)
    print(json.dumps({"ir_path": str(result_path), "asset_id": record["asset_id"],
                      "indexing": record["indexing"]["status"],
                      "publication": record["publication"]["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
