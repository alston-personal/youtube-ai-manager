"""Provider-neutral video index acceptance and persistence for AI YouTube Manager.

No Gemini/YouTube call occurs here. A provider supplies observations that this
module validates against the real media duration before publishing a checkpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

TIME_PATTERN = re.compile(r"^(?:(\d{1,3}):)?([0-5]?\d):([0-5]\d)$")
SCHEMA = "video-ir/0.1"


def parse_timecode(value: str) -> float:
    if not isinstance(value, str):
        raise ValueError("timecode must be a string")
    match = TIME_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid timecode: {value!r}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    if match.group(1) is None:
        # MM:SS permits hours by using minute totals of up to 59 in this contract.
        return minutes * 60 + seconds
    return hours * 3600 + minutes * 60 + seconds


def normalize_observations(observations: list[dict], duration: float) -> list[dict]:
    if not isinstance(observations, list):
        raise ValueError("observations must be an array")
    if not (0 < duration < float("inf")):
        raise ValueError("duration must be finite and positive")
    result = []
    for entry in observations:
        if not isinstance(entry, dict):
            raise ValueError("observation must be an object")
        timecode = entry.get("time")
        event = entry.get("event")
        if not isinstance(event, str) or not event.strip():
            raise ValueError("observation event cannot be empty")
        seconds = parse_timecode(timecode)
        if seconds > duration:
            raise ValueError(f"observation {timecode} exceeds media duration")
        if not isinstance(entry.get("evidence"), str) or not entry["evidence"].strip():
            raise ValueError("observation requires an explicit evidence pointer")
        confidence = entry.get("confidence")
        if not isinstance(confidence, (float, int)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ValueError("observation confidence must be in [0, 1]")
        result.append({
            "time": timecode, "seconds": seconds, "event": event.strip(),
            "evidence": entry["evidence"].strip(), "confidence": float(confidence),
        })
    result.sort(key=lambda item: (item["seconds"], item["event"]))
    return result


def accept_index(ir_path: str, observations: list[dict], *, provider: str, model: str) -> dict:
    path = Path(ir_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA or not data.get("source_sha256"):
        raise ValueError("not a supported Video IR source")
    if data.get("publication", {}).get("youtube_video_id"):
        raise ValueError("published IR requires governed revision handling")
    duration = float(data["probe"]["duration_seconds"])
    if not provider.strip() or not model.strip():
        raise ValueError("provider and model provenance required")
    normalized = normalize_observations(observations, duration)
    if not normalized:
        raise ValueError("zero observations: mark unindexable in workflow instead")
    # Merge only the indexing section, never delete user media.
    data["indexing"] = {
        "status": "indexed",
        "observations": normalized,
        "provider": provider,
        "model": model,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    fd, temp = tempfile.mkstemp(prefix=".index-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return data
