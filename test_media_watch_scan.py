"""Offline tests for bounded source-agnostic recording intake."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from media_watch_scan import scan_once

PROBE = {"duration_seconds": 10, "container": "mp4",
         "streams": [{"codec_type": "video", "codec_name": "h264"}]}


class WatchScanTests(TestCase):
    def test_recording_is_only_ingested_after_stability_window(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            recordings = root / "recordings"
            recordings.mkdir()
            media = recordings / "wow.mp4"
            media.write_bytes(b"recording bytes")
            now = media.stat().st_mtime + 120
            with patch("local_video_ingest.probe_video", return_value=PROBE):
                pending = scan_once(str(recordings), str(root / "ir"), clock=now - 100)
                self.assertEqual(pending["ingested"], [])
                self.assertEqual(pending["skipped"][0]["reason"], "recently_modified")
                done = scan_once(str(recordings), str(root / "ir"), source="wow", clock=now)
                again = scan_once(str(recordings), str(root / "ir"), source="wow", clock=now)
            self.assertEqual(len(done["ingested"]), 1)
            self.assertEqual(done["ingested"][0]["asset_id"], again["ingested"][0]["asset_id"])
            self.assertEqual(media.read_bytes(), b"recording bytes")
            self.assertEqual(done["one_receipt_status"], "not_submitted")

    def test_no_parent_scan_and_no_unknown_filetype(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            recordings = root / "recordings"
            recordings.mkdir()
            (root / "outside.mp4").write_bytes(b"outside")
            (recordings / "not-video.txt").write_bytes(b"ignored")
            result = scan_once(str(recordings), str(root / "ir"), clock=9999999999)
            self.assertEqual(result["ingested"], [])
            self.assertEqual(result["skipped"], [])

    def test_invalid_limit_or_root_rejected(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                scan_once(root, root, max_files=1000)
            with self.assertRaises(ValueError):
                scan_once(root, root, minimum_stable_age_seconds=0)

    def test_invalid_media_is_failure_not_false_receipt(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            src = root / "clip.mp4"
            src.write_bytes(b"invalid")
            with patch("local_video_ingest.probe_video", side_effect=ValueError("bad media")):
                result = scan_once(str(root), str(root / "ir"), clock=src.stat().st_mtime + 120)
            self.assertEqual(len(result["failures"]), 1)
            self.assertEqual(result["failures"][0]["error_type"], "ValueError")
            self.assertEqual(result["ingested"], [])
            self.assertEqual(result["one_receipt_status"], "not_submitted")
