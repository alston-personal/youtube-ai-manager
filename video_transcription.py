"""Local speech transcription for Video IR using optional faster-whisper.

No generated commentary is passed off as spoken subtitles. Never deletes source
media. Local STT is opt-in; language is detected unless explicitly supplied.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile

from video_ir_indexing import SCHEMA

def _stamp(seconds: float, *, vtt: bool = False) -> str:
    milliseconds = int(round(seconds * 1000))
    h, rem = divmod(milliseconds, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    sep = "." if vtt else ","
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def normalize_segments(segments, duration: float) -> list[dict]:
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid media duration")
    output = []
    previous_end = 0.0
    for seg in segments:
        start, end, text = float(seg["start"]), float(seg["end"]), str(seg["text"]).strip()
        if not text:
            continue
        if not all(math.isfinite(x) for x in (start, end)):
            raise ValueError("non-finite subtitle time")
        if start < 0 or end <= start or end > duration + 0.05:
            raise ValueError("subtitle outside video duration")
        if start < previous_end - 0.05:
            raise ValueError("overlapping/out-of-order subtitle segments")
        output.append({"start": start, "end": min(end, duration), "text": text})
        previous_end = end
    return output


def as_srt(segments: list[dict]) -> str:
    return "".join(
        f'{i}\n{_stamp(x["start"])} --> {_stamp(x["end"])}\n{x["text"]}\n\n'
        for i, x in enumerate(segments, 1)
    )


def as_vtt(segments: list[dict]) -> str:
    return "WEBVTT\n\n" + "".join(
        f'{_stamp(x["start"], vtt=True)} --> {_stamp(x["end"], vtt=True)}\n{x["text"]}\n\n'
        for x in segments
    )


def transcribe_ir(ir_path: str, *, model=None, language: str | None = None,
                  model_size: str = "small") -> dict:
    """Source-level processor. Runtime must authorize reading local audio."""
    path = Path(ir_path)
    ir = json.loads(path.read_text(encoding="utf-8"))
    if ir.get("schema_version") != SCHEMA or not ir.get("source_sha256"):
        raise ValueError("unsupported Video IR")
    media = Path(ir["source_path"])
    if not media.is_file():
        raise FileNotFoundError("original media not available on this node")
    # Verify identity again before processing; protect against a renamed/replaced recording.
    from local_video_ingest import sha256_file
    if sha256_file(media) != ir["source_sha256"]:
        raise ValueError("media changed since intake")
    duration = float(ir["probe"]["duration_seconds"])
    if ir.get("transcription", {}).get("status") in ("transcribed", "no_speech"):
        return ir
    if model is None:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, info = model.transcribe(str(media), language=language,
                                     vad_filter=True, beam_size=5)
    normalized = normalize_segments(
        ({"start": s.start, "end": s.end, "text": s.text} for s in segments),
        duration,
    )
    language_code = getattr(info, "language", None) or language or "und"
    if not isinstance(language_code, str) or not language_code.strip():
        language_code = "und"
    artifacts = {}
    if normalized:
        for extension, content in (("srt", as_srt(normalized)), ("vtt", as_vtt(normalized))):
            output = path.with_suffix("." + extension)
            fd, temporary = tempfile.mkstemp(prefix=".subtitle-", dir=path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as target:
                    target.write(content)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, output)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            artifacts[extension] = str(output)
    ir["transcription"] = {
        "status": "transcribed" if normalized else "no_speech",
        "language": language_code,
        "segments": normalized,
        "artifacts": artifacts,
        "model": model_size if isinstance(model_size, str) else "injected",
        "transcribed_at": datetime.now(timezone.utc).isoformat(),
    }
    fd, temp = tempfile.mkstemp(prefix=".transcribe-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(ir, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return ir
