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

## Speech transcription (local, no AI cloud upload)
Requires `faster-whisper` and a local Whisper model. Workflow integration invokes `video_transcription.transcribe_ir(ir_path, language=None)`. It checks the original SHA-256, produces time-checked SRT/VTT for actual speech, or marks `no_speech` without inventing dialog. The original media is never deleted.

## First-time YouTube publishing (private, governed only)
`youtube_private_publisher.publish_private` is a bounded API adapter intended to be called **only by a real authorized AgentOS Runtime/ONE task**. Caller must supply an independently verified YouTube channel client and effect authorization; it does not log in or silently publish. Before any remote write, it persists `upload_in_progress`. On ambiguous remote failures, it moves to `reconciliation_required` and **refuses automatic retry** until the operator/reconciler verifies whether a YouTube video exists. It returns a genuine video ID only after the API returns one, setting privacy to `private`.

Example integration (not a standalone production command):
```python
from youtube_private_publisher import publish_private, google_media_factory
# youtube must already be bound to the right authorized channel.
# authorized and channel_verified must come from governance, never constant True in production.
result = publish_private(ir_path, youtube=youtube, media_factory=google_media_factory,
                         title=approved_title, description=approved_description,
                         authorized=effect_authorized, channel_verified=channel_verified)
```

**Missing production gates:** multi-process lock/lease around upload journal; remote reconciliation after uncertain write; independent channel-ID verification and effect-token binding; actual YouTube OAuth scopes/quota and caption upload integration; Windows service/ONE transport; real media indexing and speech-quality evaluation. Therefore this code is **not authorized for unattended production publishing** yet.

## Verified offline CI
[GitHub Actions run #42547292582](https://github.com/alston-personal/youtube-ai-manager/actions/runs/42547292582) completed successfully after the publisher syntax fix. The run covers offline mocked upload consent, private visibility, and duplicate/ambiguous retry barriers; it does **not** prove live YouTube API upload.

## Publication concurrency and source-side receipt (2026-11-09)
- `publication_lock.py`: atomic per-Video-IR lock, preventing two local publishers from performing concurrent inserts. An orphaned lock **fails closed** and requires reconciliation; it is deliberately not auto-stolen. This is local-host protection, not a distributed ONE lease.
- `media_receipt_projection.py`: sanitized, deterministic `agentos.media-pipeline-source-receipt/v1` projection for existing ONE Runtime. Requires matching source SHA-256; records remote API upload ID when locally persisted, but explicitly marks `one_receipt_status=not_submitted`, `growth_proof_status=unverified`. Never includes local source path, credentials or private transcript.
- True ONE acceptance and durable cross-node receipt remain separate work. Remote reconciliation still requires a governed authoritative channel verification and independent upload provenance; no blind reset of `reconciliation_required`.
- [CI Run 42547770092](https://github.com/alston-personal/youtube-ai-manager/actions/runs/42547770092): completed successfully for source-level offline tests including lock and receipt projection. Live YouTube and ONE checks are not covered.
