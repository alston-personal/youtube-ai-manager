# Shared Media Capture & Publishing — capability contract v0.1

Owner: existing **AI YouTube Manager** for media ingest/indexing/subtitle/publishing; **AgentOS Windows Node** for desktop capture. This is an implementation contract, not a claim of deployed capability.

## Boundaries
- **Node:** existing enrolled Windows Node (see AgentOS #745). Never create a second Realm identity or generic executor for game capture.
- **Media Worker:** a scoped, user-session-bound capability provider for OBS/DingCam file outputs, finalized-file inspection, ffprobe/ffmpeg and optional screen/audio capture. It uses existing Node transport/attestation/ONE; no standalone remote command server, generic shell or scheduler.
- **Sources:** OBS, NVIDIA replay, manual MP4, WoW Addon permitted game events and logs. Addon is optional and never responsible for encoding/uploading raw video.
- **AI YouTube Manager:** owner of local Video IR/media indexing, genuine speech transcription, subtitle tracks, YouTube title/description/chapters and authorized publishing. Other projects consume this same pipeline rather than cloning it.
- **ONE:** task/receipt authority, routing, authorization, idempotency, retry and owner assignment. Distinguish advertised/verified/routable/authorized/executed capability.
- **Website/Studio Library:** displays installed shared-capability metadata and docs. It is not the worker or another source of truth; require deployed real capability and receipt before any READY label.

## Proposed capabilities (unverified until attested)
| id | Provider | Inputs | Outputs | Consent boundary |
| --- | --- | --- | --- | --- |
| `media.capture.record` | Windows session Media Worker | source, event/manual trigger, bounds | local file ref, capture receipt | user-authorized screen/audio scope |
| `media.capture.ingest` | Windows Media Worker | finalized media file | immutable Video IR asset id/hash | only approved watch roots; preserve original |
| `media.video.index` | YouTube AI Manager | Video IR + readable media | timestamped observations/evidence | local or explicit provider file-transfer permission |
| `media.video.transcribe` | YouTube AI Manager | audio media | verified timecoded SRT/VTT or no-speech | speech data transfer policy |
| `media.youtube.publish` | YouTube AI Manager | validated Video IR, media, credentials reference, explicit publish authorization | YouTube video id and receipt | initial private upload only, NEVER implicit public publish |

## Data plane and control plane
- **Data plane:** Windows media stored locally; worker hands back a **media reference + hash**. If indexing is offloaded, transfer only through an explicitly permitted mechanism, not by sending unbounded video via ONE control messages or default Oracle copies.
- **Control plane:** ONE sends bounded jobs to Media Worker via registered Node adapter and receives typed checkpoint/terminal receipts.
- **Video IR:** includes schema version, source game/client optional, local asset id/hash, capture metadata, timecoded evidence observations, transcription status, subtitle artifact refs, QA, provider processing version, publication state and YouTube id. Game-specific telemetry is optional evidence with source/provenance and is not silently treated as video observations.
- **Lifecycle:** `CAPTURE_READY -> INGESTED -> INDEXED -> TRANSCRIBED_OR_NO_SPEECH -> QA_PASSED -> AUTHORIZED -> UPLOADED_PRIVATE -> RECEIPT_VERIFIED`. Each stage is recoverable/idempotent; errors stay explicitly BLOCKED/RETRYABLE.
- **Storage:** original recording never deleted by indexing. Use deterministic hash identity and post-upload dedup; retain source media according to configured retention.

## Website / Library / Skill registration acceptance
1. Expose a machine-readable capability manifest from the existing registry, not a website-only static declaration. Status must distinguish `planned`, `advertised`, `verified`, `available`, `blocked`.
2. Add discoverable **Media Capture & Publishing** Library documentation and usage example to Studio only after confirming existing Studio ownership/routes. Registration must link to canonical capability and evidence; no new Studio control plane.
3. Provide skill guidance for agents on `media.capture.ingest`, `media.video.index`, `media.video.transcribe`, `media.youtube.publish`: typed inputs, permission fences, failures, receipts, and fallback routes. Do not describe it as installed before it is packaged/registered.
4. Dashboard may add reusable UI components `MediaSourcePicker`, `VideoPipelineStatus`, `VideoIndexTimeline`, `PublishReview` once data contracts and route ownership are verified. Do not implement UI before backend readiness solely to create a mock demo.
5. Evidence must include Windows actual capture, original preserved, indexing/subtitle correctness, authorized private YouTube video ID and receipt, reconnect/no duplicate, and second non-WoW media source.

## Dependencies and coordination
- Primary delivery: [YouTube AI Manager #1](https://github.com/alston-personal/youtube-ai-manager/issues/1).
- Initial implementation: [Draft PR #2](https://github.com/alston-personal/youtube-ai-manager/pull/2).
- Existing Windows architecture: AgentOS #745 and optional WoW control interface #2134 (independent; never a blocking dependency).
- Game Coach #2122 and quality advisor #2121 are downstream/later consumers, not scope of upload MVP.
- Avoid diverting AgentOS #470/#1682. Tangential findings to backlog, then return to main workflow.

## Known hardening before unattended integration
The current `analyze_video_multimodal` removes its input video in a finally block: remove ownership ambiguity, delete **only explicitly owned temp files**. Existing Gemini calls disable TLS certificate verification: restore proper verification. Existing upload reads entire video into memory: use bounded streaming/resumable handling and file-length limits. Never infer that existing caption-upload API already does transcription. Nothing in this document grants YouTube publishing authority.

## Implemented Node-facing one-shot intake (2026-11-09)
- Added `media_watch_scan.py`: bounded scan of an **already authorized** local folder; no daemon, separate scheduler or direct ONE HTTP client. It only considers finalized old-enough media files (`.mp4/.mov/.mkv/.webm`), refuses symlink entries/roots, validates files through `ffprobe`, hashes immutable source and returns `agentos.media-watch-scan/v1` with ingested/skipped/failed counts. It leaves raw recordings unchanged and reports `one_receipt_status: not_submitted`.
- Invoke this module via the existing Windows Node session adapter **after** governance resolves `media.capture.ingest` and confirms an allowed recording folder. Input: `folder, ir_dir, source, stable_age, max_files`. Output: sanitized bounded summary and IR references. The invoking Node/Runtime, not this module, owns authentication, queue, dispatch, retries and canonical ONE receipt.
- GitHub Actions [run #42557666349](https://github.com/alston-personal/youtube-ai-manager/actions/runs/42557666349) passed mock/unit tests. This does not evidence a live Windows Node/ONE call. The existing AgentOS [WoW NodeAdapter PR #2135](https://github.com/alston-personal/agentmanager/pull/2135) confirms there is an Adapter pattern in a separate workstream, but it does **not** make Media Worker live.
- Need existing Windows Node maintainer to bind the typed `media.capture.ingest` adapter to an actual Windows session and live attestation; do not create new global Executor or Node enrollment. Preserve priority of AgentOS #470 and #1682.

## Installable Node extension checkpoint — 2026-11-09
- The existing media worker capability is packaged in `pyproject.toml` as `agentos-media-worker`, with `agentos-media-ingest`, `agentos-media-scan` and `agentos-media-index` CLI entry points. Provider-specific SDKs are optional dependencies. This package is a scoped **extension for an existing Windows Node**, not another Node enrollment or executor runtime.
- `media_node_adapter.py` implements exactly the existing `agentos_node.node_adapter.NodeAdapter` interface (`adapter_id`, `capabilities`, `describe`, `execute`) as verified against AgentOS source. The factory returns an **unbound** adapter; `AGENTOS_NODE_ADAPTERS=media_node_adapter` alone does not grant filesystem access or report live readiness.
- The *trusted Node session configuration* must supply `MediaIngestAdapter(approved_folder=..., ir_dir=...)` after authenticating an authorized task and checking allowed folders, then register that instance with existing `AdapterRegistry`. The external task accepts only `{"action":"media.capture.ingest"}` and never accepts a path/shell/permission parameter. All queue, lease and canonical receipt operations remain owned by ONE.
- Packaging/CI cannot substitute for actual deployed Windows installer, node registration, fresh capability verification, or end-to-end ONE receipt. No user credentials are included in this package.
