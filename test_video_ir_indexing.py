import json
from pathlib import Path
import tempfile
import unittest
from video_ir_indexing import accept_index, normalize_observations, parse_timecode

class VideoIndexTests(unittest.TestCase):
    def test_timecodes(self):
        self.assertEqual(parse_timecode("01:23"), 83)
        self.assertEqual(parse_timecode("01:02:03"), 3723)
        for bad in ("1:73", "wrong", "-1:00", "00:60"):
            with self.assertRaises(ValueError):
                parse_timecode(bad)

    def test_accept_rejects_hallucinated_or_unattributed_events(self):
        with self.assertRaisesRegex(ValueError, "exceeds media"):
            normalize_observations([{"time":"01:00","event":"boss","evidence":"frame:1","confidence":0.8}], 30)
        with self.assertRaisesRegex(ValueError, "evidence"):
            normalize_observations([{"time":"00:01","event":"boss","confidence":0.8}], 30)
        with self.assertRaisesRegex(ValueError, "confidence"):
            normalize_observations([{"time":"00:01","event":"boss","evidence":"frame:1","confidence":1.5}], 30)

    def test_provider_independent_index_no_media_mutation(self):
        for source in ("wow", "studio"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as root:
                root = Path(root)
                media = root / "original.mp4"
                media.write_bytes(b"source bytes")
                ir = root / "manifest.json"
                ir.write_text(json.dumps({
                    "schema_version":"video-ir/0.1", "source_sha256":"a1",
                    "source_kind":source, "probe":{"duration_seconds":30},
                    "publication":{"status":"not_authorized","youtube_video_id":None}
                }))
                indexed = accept_index(str(ir), [
                    {"time":"00:02","event":"visible scene", "evidence":"frame:00:02", "confidence":0.7}
                ], provider="test-provider", model="test-model")
                self.assertEqual(indexed["indexing"]["status"], "indexed")
                self.assertEqual(indexed["indexing"]["observations"][0]["seconds"], 2)
                self.assertEqual(media.read_bytes(), b"source bytes")
                self.assertEqual(json.loads(ir.read_text())["source_kind"], source)

if __name__ == "__main__":
    unittest.main()
