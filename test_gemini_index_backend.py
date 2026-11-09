"""Offline mocks for the real Gemini index adapter."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gemini_index_backend import index_local_video

PROBE = {"duration_seconds": 50.0, "container": "mp4", "streams": [{"codec_type": "video"}]}


class FakeFiles:
    def __init__(self):
        self.upload_calls = 0
        self.delete_calls = 0
    def upload(self, file):
        self.upload_calls += 1
        return SimpleNamespace(name="files/1", state=SimpleNamespace(name="ACTIVE"))
    def delete(self, name):
        self.delete_calls += 1


class FakeClient:
    def __init__(self, observations):
        self.files = FakeFiles()
        self.models = SimpleNamespace(generate_content=lambda **_: SimpleNamespace(
            text=json.dumps({"observations": observations})))


class GeminiIndexTests(unittest.TestCase):
    def test_requires_explicit_cloud_consent(self):
        with self.assertRaises(PermissionError):
            index_local_video("missing.mp4", "ir", allow_cloud_upload=False)

    def test_source_preserved_and_second_project_reuses_pipeline(self):
        for source in ("wow", "other"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as root:
                src = Path(root) / "original.mp4"
                src.write_bytes(b"original video bytes")
                client = FakeClient([{"time":"00:04", "event":"scene transition",
                                      "evidence":"frame:00:04", "confidence":0.85}])
                with patch("local_video_ingest.probe_video", return_value=PROBE):
                    ir_file, record = index_local_video(str(src), str(Path(root) / "ir"),
                                    allow_cloud_upload=True, source=source, client=client)
                    repeat_file, repeat = index_local_video(str(src), str(Path(root) / "ir"),
                                    allow_cloud_upload=True, source=source, client=client)
                self.assertEqual(ir_file, repeat_file)
                self.assertEqual(record["indexing"]["observations"][0]["seconds"], 4.0)
                self.assertEqual(client.files.upload_calls, 1)
                self.assertEqual(client.files.delete_calls, 1)
                self.assertEqual(src.read_bytes(), b"original video bytes")
                self.assertEqual(repeat["indexing"]["status"], "indexed")

    def test_invalid_timestamp_never_marked_indexed(self):
        with tempfile.TemporaryDirectory() as root:
            src = Path(root) / "video.mp4"
            src.write_bytes(b"video")
            client = FakeClient([{"time":"05:00","event":"invented", "evidence":"frame:05:00","confidence":0.9}])
            with patch("local_video_ingest.probe_video", return_value=PROBE):
                with self.assertRaisesRegex(ValueError, "exceeds media"):
                    index_local_video(str(src), str(Path(root)/"ir"),
                                      allow_cloud_upload=True, client=client)
            self.assertEqual(client.files.delete_calls, 1)
            ir = next((Path(root)/"ir").glob("*.json"))
            self.assertEqual(json.loads(ir.read_text())["indexing"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
