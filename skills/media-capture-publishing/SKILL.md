# Media Capture & Publishing — reusable AgentOS skill (candidate)

**Status:** Source-level guidance only. Not an installed AgentOS skill, a live capability, or YouTube authorization. Canonical owner is existing AI YouTube Manager; local capture provider is an adapter on an existing Windows AgentOS Node. See `docs/SHARED_MEDIA_CAPABILITY.md` and `media_capabilities.py`.

## When to invoke
A user requests local video import, game/screen recording, video indexing, transcription/subtitles, or an authorized YouTube upload. Reuse this capability for WoW, studio/program production, other games and desktop videos; do not create a project-specific uploader or second manager.

## Discover first
1. Resolve the canonical project and owner through existing AgentOS Governance Directory / Node Registry. Confirm fresh node/session presence and real capability advertisement, routing and effect authorization independently.
2. Read catalog contract IDs from `media_capabilities.catalog_manifest()`. The manifest explicitly reports `unverified`; **never treat source availability as live authorization**.
3. Use an existing registered worker for `media.capture.ingest` or `media.video.index`; only implement missing capability after running existing Reuse Before Build resolution. Do not create a new Node, executor, scheduler or queue for this skill.

## Minimal steps
1. On a user-approved folder on the desktop node, wait for the recorder to finalize the file. Existing `local_video_ingest.py` creates a hash-based `video-ir/0.1` record without modifying original video.
2. A governed AI YouTube Manager worker indexes real video observations, with timestamp, evidence and confidence. Failing indexing must not be reported as complete. Separate image indexing from actual speech transcription.
3. Produce time-verified SRT/VTT when audible speech exists; record `no_speech` otherwise. Generate grounded chapter timestamps/title/description, then validate media/metadata.
4. **Before any external mutation**, verify channel identity, OAuth permission and explicit publication authorization. Default upload is **private**. If external authorization unavailable, emit NEEDS_HUMAN; do not upload.
5. Store the real YouTube video ID, URL and ONE-governed Receipt. Idempotent retries must not create duplicate uploads, including after process restart.
6. If a different project reuses the capability, record source project, consumer project, same capability/version, provider, evidence/receipt IDs and before/after development or runtime cost where measurable. Submit a sanitized Experience *candidate* to existing #1768 / #117, **not** a separate ledger.

## Safety / acceptance gates
- Original footage is never deleted by the AI indexing step.
- No screen/audio capture outside explicitly approved scope; WoW addon data is optional and untrusted.
- No raw media sent through ONE control messages; remote transfer requires governed data-plane permission.
- No source-code-only claims of READY, no secrets in screenshots/manifests/receipts.
- No pre-upload fabricated chapter timestamps or speech captions; low-confidence event remains unknown.
- Observations, upload and cross-project growth each need independent proof. Source-level unit tests cannot prove production execution.
