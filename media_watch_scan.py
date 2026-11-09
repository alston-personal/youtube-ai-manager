"""Bounded watch-folder intake for an existing AgentOS Windows Node session.

One-shot action only: scheduling and authorization remain with AgentOS ONE.
No daemon, service, direct ONE endpoint, credentials or upload side effects.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from local_video_ingest import ingest

VIDEO_SUFFIXES = frozenset({".mp4", ".mkv", ".mov", ".webm"})
MAX_FILES_PER_SCAN = 32
MAX_VIDEO_BYTES = 20 * 1024 * 1024 * 1024


def scan_once(folder: str, ir_dir: str, *, source: str = "obs",
              minimum_stable_age_seconds: int = 60, max_files: int = 8,
              clock=None) -> dict:
    """Scan an explicitly allowed folder; only regular finalized media.

    Runtime must authorize the root/path and capability prior to invocation.
    This function does not schedule itself or claim a real ONE receipt.
    """
    if source not in {"local", "wow", "obs", "other"}:
        raise ValueError("unknown source")
    if not (1 <= max_files <= MAX_FILES_PER_SCAN):
        raise ValueError("invalid max_files")
    if not (10 <= minimum_stable_age_seconds <= 86400):
        raise ValueError("invalid minimum_stable_age_seconds")
    root = Path(folder).expanduser()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("watch folder must be an existing non-symlink directory")
    now = time.time() if clock is None else float(clock)
    output = {"schema_version": "agentos.media-watch-scan/v1",
              "status": "completed", "scanned_at": datetime.fromtimestamp(
                  now, tz=timezone.utc).isoformat(),
              "ingested": [], "skipped": [], "failures": [],
              "one_receipt_status": "not_submitted"}
    candidates = sorted(root.iterdir(), key=lambda item: item.name)
    checked = 0
    for path in candidates:
        if checked >= max_files:
            break
        if path.suffix.lower() not in VIDEO_SUFFIXES:
            continue
        checked += 1
        if path.is_symlink() or not path.is_file():
            output["skipped"].append({"file": path.name, "reason": "not_regular_file"})
            continue
        stat = path.stat()
        if stat.st_size == 0 or stat.st_size > MAX_VIDEO_BYTES:
            output["skipped"].append({"file": path.name, "reason": "size_out_of_bounds"})
            continue
        if now - stat.st_mtime < minimum_stable_age_seconds:
            output["skipped"].append({"file": path.name, "reason": "recently_modified"})
            continue
        try:
            ir_path, record = ingest(str(path), ir_dir, source)
            output["ingested"].append({"file": path.name, "asset_id": record["asset_id"],
                                        "ir_path": str(ir_path)})
        except Exception as exc:
            # Avoid returning arbitrary internal paths or tool diagnostics to ONE.
            output["failures"].append({"file": path.name,
                                       "error_type": type(exc).__name__})
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot authorized Windows media scan")
    parser.add_argument("folder", help="Existing approved recording directory")
    parser.add_argument("--ir-dir", required=True)
    parser.add_argument("--source", default="obs", choices=["local", "wow", "obs", "other"])
    parser.add_argument("--stable-age", type=int, default=60)
    parser.add_argument("--max-files", type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(scan_once(args.folder, args.ir_dir, source=args.source,
                               minimum_stable_age_seconds=args.stable_age,
                               max_files=args.max_files), ensure_ascii=False))


if __name__ == "__main__":
    main()
