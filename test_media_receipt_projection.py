import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from media_receipt_projection import project_media_receipt

HASH = "f" * 64


class ReceiptProjectionTests(unittest.TestCase):
    def make(self, root, publication):
        path = Path(root) / "asset.video-ir.json"
        path.write_text(json.dumps({
            "schema_version":"video-ir/0.1",
            "asset_id":"sha256:" + HASH,
            "source_sha256":HASH,
            "source_path":"/sensitive/recording.mp4",
            "indexing":{"status":"indexed"},
            "transcription":{"status":"no_speech"},
            "publication":publication,
        }))
        return path

    def test_unresolved_upload_is_not_success(self):
        with TemporaryDirectory() as root:
            ir = self.make(root, {"status":"reconciliation_required", "youtube_video_id":None})
            receipt = project_media_receipt(str(ir))
            self.assertFalse(receipt["remote_api_response_recorded"])
            self.assertIsNone(receipt["one_accepted_receipt_id"])
            self.assertEqual(receipt["one_receipt_status"], "not_submitted")
            self.assertNotIn("/sensitive/", str(receipt))

    def test_recorded_remote_id_not_one_receipt(self):
        with TemporaryDirectory() as root:
            ir = self.make(root, {"status":"uploaded_private", "youtube_video_id":"test_id",
                                  "privacy":"private"})
            receipt = project_media_receipt(str(ir))
            self.assertTrue(receipt["remote_api_response_recorded"])
            self.assertEqual(receipt["youtube_video_id"],"test_id")
            self.assertIsNone(receipt["one_accepted_receipt_id"])
            self.assertEqual(receipt["growth_proof_status"], "unverified")

    def test_fake_success_rejected(self):
        with TemporaryDirectory() as root:
            ir = self.make(root, {"status":"uploaded_private", "youtube_video_id":None,
                                  "privacy":"private"})
            with self.assertRaises(ValueError):
                project_media_receipt(str(ir))


if __name__ == "__main__":
    unittest.main()
