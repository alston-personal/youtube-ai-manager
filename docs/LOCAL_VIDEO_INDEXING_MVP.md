# Local video indexing MVP — developer/operator guide

This is part of existing AI YouTube Manager, not a replacement publisher or Node.

## Components
- `local_video_ingest.py` — local media inspection, immutable sha256 identity, versioned IR, original preserved.
- `gemini_index_backend.py` — **optional, explicitly consented** cloud analysis using official `google-genai` Python SDK; resolves model-reported timecode observations and writes the index through `video_ir_indexing.py`.
- `media_capabilities.py` — shared contract catalog, status **unverified** until ONE live attestation.
- `skills/media-capture-publishing/SKILL.md` — skill candidate, **not installed**.

## Installation (developer only)
```bash
python -m pip install google-genai
# ffprobe / ffmpeg must be installed on the host
```

## Local no-cloud import
```bash
python local_video_ingest.py /path/to/finalized-recording.mp4 --source wow --output-dir video_ir
```

## Optional Gemini indexing
Data transfer MUST be allowed by project governance and the user. CLI consent flag is necessary but NOT a replacement for a real ONE authorization check:
```bash
export GEMINI_API_KEY='(configure in protected runtime secret storage, not checked-in files)'
python gemini_index_backend.py /path/to/finalized-recording.mp4 \
  --source wow --ir-dir video_ir --allow-cloud-upload
```
Indexing generates timecoded model-reported video observations. It does NOT produce verified transcript/subtitles, upload to YouTube, publish publicly, or prove provider-independent temporal accuracy. For oversized videos (>150 MiB), the bounded adapter refuses to upload; segmentation or a governed data-plane transport is needed.

## Offline test command (execute in working checkout)
```bash
python -m unittest -v test_local_video_ingest test_media_capabilities test_video_ir_indexing test_gemini_index_backend test_indexer_safety_contract
```

## Remaining gates before marking READY
1. Verify actual video indexing on a permitted clip, correct event timestamps against frames.
2. Produce genuine transcript or `no_speech` (never a synthetic commentary caption posing as transcript).
3. Governed YouTube OAuth and resumable private upload with remote video ID receipt, restart/dedup.
4. Register capabilities through existing Windows Node/ONE, check attestation, authorized routing, and canonical receipts. Do not mark online from a static manifest.
5. Prove non-WoW consumer reuses the same provider with accepted ONE Experience and controlled cold/hydrated growth comparison per AgentOS #1768.

Current state: source-level implementation and offline tests submitted; no formal CI, Windows deployment or ONE acceptance evidence yet.
