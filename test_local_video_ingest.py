"""Tests for local video intake without real video, network, or YouTube writes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_video_ingest import ingest


VALID_PROBE = {"duration_seconds": 8.5, "container": "mp4",
               "streams": [{"codec_type": "video", "codec_name": "h264"}]}


class LocalVideoIngestTests(unittest.TestCase):
    def test_original_preserved_and_retry_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "clip.mp4"
            source.write_bytes(b"sample immutable capture bytes")
            output_dir = Path(root) / "ir"
            with patch("local_video_ingest.probe_video", return_value=VALID_PROBE):
                p1, ir1 = ingest(str(source), str(output_dir), "wow")
                p2, ir2 = ingest(str(source), str(output_dir), "wow")
            self.assertEqual(source.read_bytes(), b"sample immutable capture bytes")
            self.assertEqual(p1, p2)
            self.assertEqual(ir1, ir2)
            self.assertEqual(len(list(output_dir.glob("*.video-ir.json"))), 1)
            self.assertEqual(ir1["publication"]["status"], "not_authorized")
            self.assertEqual(ir1["indexing"]["status"], "pending")
            self.assertEqual(ir1["source_kind"], "wow")

    def test_empty_input_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "empty.mp4"
            src.touch()
            with self.assertRaises(ValueError):
                ingest(str(src), str(Path(root) / "output"))

    def test_invalid_media_rejected_without_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "invalid.mp4"
            src.write_bytes(b"corrupt")
            with patch("local_video_ingest.probe_video", side_effect=ValueError("invalid")):
                with self.assertRaises(ValueError):
                    ingest(str(src), str(Path(root) / "ir"))
            self.assertEqual(src.read_bytes(), b"corrupt")
            self.assertFalse((Path(root) / "ir").exists())

    def test_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "changing.mp4"
            src.write_bytes(b"part one")
            def modify(_):
                src.write_bytes(b"part two appended")
                return "abc"
            with patch("local_video_ingest.probe_video", return_value=VALID_PROBE), patch(
                    "local_video_ingest.sha256_file", side_effect=modify):
                with self.assertRaisesRegex(ValueError, "changed"):
                    ingest(str(src), str(Path(root) / "ir"))


if __name__ == "__main__":
    unittest.main()
