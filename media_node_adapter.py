"""Opt-in Media ingest adapter compatible with AgentOS NodeAdapter contract.

Provider is instantiated by existing Windows Node adapter registry, not by a
new scheduler/worker daemon. This module does not enroll, authenticate, or send
receipts to ONE. The host MUST inject the authorized root and IR destination
from trusted configuration; task payloads may not select paths.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import os
from typing import Any

from media_watch_scan import scan_once

CAPABILITY = "media.capture.ingest"
ALLOWED_TASK_KEYS = frozenset({"action"})


class MediaIngestAdapter:
    adapter_id = "media-ingest"

    def __init__(self, *, approved_folder: str | None = None,
                 ir_dir: str | None = None, source: str = "obs",
                 scanner: Callable[..., dict[str, Any]] = scan_once):
        self._folder = approved_folder
        self._ir_dir = ir_dir
        self._source = source
        self._scanner = scanner

    def capabilities(self) -> tuple[str, ...]:
        return (CAPABILITY,)

    def describe(self) -> dict[str, Any]:
        return {
            "kind": "interactive-session",
            "transport": "existing-node-adapter",
            "live_verified": False,
            "read_only": False,
            "implementation": "candidate",
            "effects": ["read-approved-media", "write-approved-video-ir"],
            "needs_host_authorization": True,
        }

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(task, dict):
            raise ValueError("task must be an object")
        if set(task) != ALLOWED_TASK_KEYS or task.get("action") != CAPABILITY:
            raise ValueError("unsupported media action or caller-controlled arguments")
        if not self._folder or not self._ir_dir:
            return {"status": "UNAVAILABLE", "reason": "APPROVED_MEDIA_ROOT_NOT_BOUND",
                    "one_receipt_status": "not_submitted"}
        result = self._scanner(self._folder, self._ir_dir, source=self._source)
        if not isinstance(result, dict) or result.get("schema_version") != "agentos.media-watch-scan/v1":
            raise ValueError("invalid bounded media scan result")
        return {"status": "OK", "result": result,
                "one_receipt_status": "not_submitted"}


def create_adapter() -> MediaIngestAdapter:
    """Fail-closed factory for existing AGENTOS_NODE_ADAPTERS registration.

    The *trusted Node startup environment*, never a task payload, supplies the
    allowlisted media directory and output directory. No implicit activation.
    """
    if os.environ.get("AGENTOS_MEDIA_ENABLED") != "1":
        return MediaIngestAdapter()
    root_raw = os.environ.get("AGENTOS_MEDIA_APPROVED_ROOT", "")
    output_raw = os.environ.get("AGENTOS_MEDIA_IR_DIR", "")
    if not root_raw or not output_raw:
        return MediaIngestAdapter()
    root, output = Path(root_raw), Path(output_raw)
    if not root.is_absolute() or not output.is_absolute():
        return MediaIngestAdapter()
    if not root.is_dir() or root.is_symlink():
        return MediaIngestAdapter()
    # The IR directory may not be the media root itself.
    if root.resolve() == output.resolve():
        return MediaIngestAdapter()
    source = os.environ.get("AGENTOS_MEDIA_SOURCE", "obs")
    if source not in {"local", "wow", "obs", "other"}:
        return MediaIngestAdapter()
    return MediaIngestAdapter(approved_folder=str(root), ir_dir=str(output), source=source)
