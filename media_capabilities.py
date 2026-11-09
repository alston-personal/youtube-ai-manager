"""Reusable, non-authoritative media capability catalog.

The registry/ONE live attestation is authoritative; this manifest only describes
the contract to install/advertise once a real provider is installed.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

SCHEMA_VERSION = "agentos.media-capability-catalog/v1"
CAPABILITY_DEFINITIONS = (
    ("media.capture.ingest", "windows-media-worker", "media-source/v1", "video-ir/0.1", False),
    ("media.video.index", "youtube-ai-manager", "video-ir/0.1", "video-ir/0.1", False),
    ("media.video.transcribe", "youtube-ai-manager", "video-ir/0.1", "caption-track/v1", False),
    ("media.youtube.publish", "youtube-ai-manager", "video-ir/0.1", "youtube-upload-receipt/v1", True),
)

@dataclass(frozen=True)
class MediaCapability:
    capability_id: str
    provider: str
    input_schema: str
    output_schema: str
    external_write: bool

    def to_manifest(self) -> dict:
        return {
            "id": self.capability_id, "provider": self.provider,
            "input_schema": self.input_schema, "output_schema": self.output_schema,
            "external_write": self.external_write,
            # Deliberately never mark this as available/ready based only on code.
            "implementation_status": "candidate",
            "live_status": "unverified",
            "authorization": "required_for_external_write" if self.external_write else "capability_scoped",
        }


CATALOG = tuple(MediaCapability(*item) for item in CAPABILITY_DEFINITIONS)


def catalog_manifest() -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "capabilities": [item.to_manifest() for item in CATALOG]}


def check_reuse(required: set[str], advertised: Mapping[str, bool]) -> dict:
    """No capability is reusable unless a host supplies a live positive check.

    This is a discovery helper, NOT a replacement for ONE/governance routing.
    """
    known = {entry.capability_id for entry in CATALOG}
    unsupported = sorted(required - known)
    live = sorted(cap for cap in required if cap in known and advertised.get(cap) is True)
    missing = sorted(required - set(live))
    return {"live_candidates": live, "missing_or_unverified": missing,
            "unknown_contracts": unsupported, "can_reuse_all": not missing}
