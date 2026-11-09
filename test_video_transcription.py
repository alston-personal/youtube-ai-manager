import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from local_video_ingest import sha256_file
from video_transcription import normalize_segments, as_srt, as_vtt, transcribe_ir

class FakeWhisper:
    def __init__(self, segments):
        self.segments = segments
        self.calls = 0
    def transcribe(self, path, **kwargs):
        self.calls += 1
        return iter(SimpleNamespace(**x) for x in self.segments), SimpleNamespace(language="zh")

class TranscriptTests(unittest.TestCase):
    def prepare(self, root):
        media = Path(root) / "capture.mp4"
        media.write_bytes(b"immutable source")
        manifest = Path(root) / "clip.video-ir.json"
        manifest.write_text(json.dumps({
            "schema_version":"video-ir/0.1", "source_sha256": sha256_file(media),
            "source_path":str(media), "probe":{"duration_seconds":20},
            "transcription":{"status":"pending"}, "publication":{"status":"not_authorized"}}))
        return media, manifest

    def test_timed_speech_from_actual_transcriber_output(self):
        with tempfile.TemporaryDirectory() as root:
            media, ir = self.prepare(root)
            model = FakeWhisper([{"start":1.2, "end":2.5, "text":"你好 世界"}])
            result = transcribe_ir(str(ir), model=model)
            self.assertEqual(result["transcription"]["status"], "transcribed")
            self.assertIn("00:00:01,200 --> 00:00:02,500", Path(result["transcription"]["artifacts"]["srt"]).read_text())
            self.assertIn("WEBVTT", Path(result["transcription"]["artifacts"]["vtt"]).read_text())
            self.assertEqual(media.read_bytes(), b"immutable source")
            transcribe_ir(str(ir), model=model)
            self.assertEqual(model.calls, 1)

    def test_silent_clip_does_not_fabricate_caption(self):
        with tempfile.TemporaryDirectory() as root:
            _, ir = self.prepare(root)
            result = transcribe_ir(str(ir), model=FakeWhisper([]))
            self.assertEqual(result["transcription"]["status"], "no_speech")
            self.assertEqual(result["transcription"]["artifacts"], {})

    def test_invalid_timestamps_rejected(self):
        for segment in ({"start":19,"end":21,"text":"wrong"}, {"start":-1,"end":2,"text":"wrong"},
                        {"start":2,"end":2,"text":"wrong"}):
            with self.assertRaises(ValueError):
                normalize_segments([segment],20)

    def test_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            media, ir = self.prepare(root)
            media.write_bytes(b"changed file")
            with self.assertRaisesRegex(ValueError, "changed"):
                transcribe_ir(str(ir), model=FakeWhisper([]))

if __name__ == "__main__":
    unittest.main()
