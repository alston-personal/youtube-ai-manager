#!/usr/bin/env python3
"""Safe local-video intake for the existing YouTube AI Manager.

This is a source adapter, NOT a second scheduler/uploader. It never modifies or
deletes source media. The generated Video IR is a pre-indexing record; no AI
observation, transcript, or YouTube upload is claimed at this stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime, timezone


SCHEMA_VERSION = "video-ir/0.1"
CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,format_name:stream=codec_type,codec_name",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=False, timeout=90,
    )
    if result.returncode:
        raise ValueError("ffprobe rejected input video: " + result.stderr[:200])
    metadata = json.loads(result.stdout)
    duration = float(metadata.get("format", {}).get("duration") or 0)
    streams = metadata.get("streams", [])
    if duration <= 0 or not any(s.get("codec_type") == "video" for s in streams):
        raise ValueError("Input must contain a video stream and positive duration")
    return {"duration_seconds": duration,
            "container": metadata.get("format", {}).get("format_name"),
            "streams": streams}


def ingest(path: str, output_dir: str, source: str = "local") -> tuple[Path, dict]:
    candidate = Path(path).expanduser()
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise ValueError("Input video does not exist or is empty")
    # Source must be stable before indexing. A watch-folder adapter should call
    # this only after close/size-stable checks.
    before = candidate.stat()
    probe = probe_video(candidate)
    digest = sha256_file(candidate)
    after = candidate.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during hashing; retry after recording finishes")

    destination = Path(output_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / (digest + ".video-ir.json")
    if output.exists():
        record = json.loads(output.read_text(encoding="utf-8"))
        if record.get("source_sha256") != digest or record.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Existing IR identity conflict; manual inspection required")
        return output, record

    record = {
        "schema_version": SCHEMA_VERSION,
        "asset_id": "sha256:" + digest,
        "source_sha256": digest,
        "source_kind": source,
        "source_path": str(candidate.resolve()),
        "source_bytes": before.st_size,
        "source_modified_ns": before.st_mtime_ns,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "probe": probe,
        "indexing": {"status": "pending", "observations": []},
        "transcription": {"status": "pending", "subtitles": []},
        "publication": {"status": "not_authorized", "youtube_video_id": None},
    }
    # No original-file mutation and no secrets in IR.
    fd, tmp = tempfile.mkstemp(prefix=".video-ir-", suffix=".tmp", dir=destination)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        # Existing matching records must not be overwritten on retry.
        if output.exists():
            return output, json.loads(output.read_text(encoding="utf-8"))
        os.replace(tmp, output)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return output, record


def main() -> None:
    parser = argparse.ArgumentParser(description="Create safe local Video IR; never publish.")
    parser.add_argument("video", help="Finalized local video file")
    parser.add_argument("--output-dir", default="video_ir")
    parser.add_argument("--source", default="local", choices=["local", "wow", "obs", "other"])
    args = parser.parse_args()
    output, record = ingest(args.video, args.output_dir, args.source)
    print(json.dumps({"ir_path": str(output), "asset_id": record["asset_id"],
                      "status": "indexed_metadata_only"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
