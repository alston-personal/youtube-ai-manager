import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from local_video_ingest import sha256_file
from youtube_private_publisher import publish_private


class VideoRequest:
    def __init__(self, fail=False):
        self.calls=0
        self.fail=fail
    def next_chunk(self):
        self.calls+=1
        if self.fail:
            raise TimeoutError("unknown remote outcome")
        return None, {"id":"test_video_id"}

class FakeYoutube:
    def __init__(self, fail=False):
        self.insert_calls=0
        self.request=VideoRequest(fail=fail)
        self.last_body=None
    def videos(self): return self
    def insert(self, *, part, body, media_body):
        self.insert_calls+=1
        self.last_body=body
        return self.request


class PublishTests(unittest.TestCase):
    def prepare(self, root):
        media=Path(root)/"video.mp4"
        media.write_bytes(b"unchanged video")
        ir=Path(root)/"file.video-ir.json"
        ir.write_text(json.dumps({
            "schema_version":"video-ir/0.1","source_path":str(media),
            "source_sha256":sha256_file(media),
            "indexing":{"status":"indexed", "observations":[{"time":"00:00","event":"start"}]},
            "transcription":{"status":"no_speech"},
            "publication":{"status":"not_authorized","youtube_video_id":None}
        }))
        return media,ir
    def call(self, ir, youtube, **overrides):
        params=dict(youtube=youtube,media_factory=lambda p:p,title="Test",
                    description="A clip",authorized=True,channel_verified=True)
        params.update(overrides)
        return publish_private(str(ir), **params)

    def test_private_upload_once_with_verified_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            media,ir=self.prepare(root)
            yt=FakeYoutube()
            result=self.call(ir,yt)
            self.assertEqual(result["publication"]["youtube_video_id"],"test_video_id")
            self.assertEqual(result["publication"]["status"],"uploaded_private")
            self.assertEqual(yt.last_body["status"]["privacyStatus"],"private")
            self.assertEqual(yt.last_body["snippet"]["categoryId"],"22")
            self.call(ir,yt)
            self.assertEqual(yt.insert_calls,1)
            self.assertEqual(media.read_bytes(),b"unchanged video")
    def test_external_effect_denied_without_auth(self):
        with tempfile.TemporaryDirectory() as root:
            _,ir=self.prepare(root)
            yt=FakeYoutube()
            with self.assertRaises(PermissionError):
                self.call(ir,yt,authorized=False)
            self.assertEqual(yt.insert_calls,0)
            self.assertEqual(json.loads(ir.read_text())["publication"]["status"],"not_authorized")
    def test_channel_must_be_verified(self):
        with tempfile.TemporaryDirectory() as root:
            _,ir=self.prepare(root)
            yt=FakeYoutube()
            with self.assertRaises(PermissionError):
                self.call(ir,yt,channel_verified=False)
            self.assertEqual(yt.insert_calls,0)
    def test_ambiguous_result_blocks_duplicate_upload(self):
        with tempfile.TemporaryDirectory() as root:
            _,ir=self.prepare(root)
            yt=FakeYoutube(fail=True)
            with self.assertRaises(TimeoutError):
                self.call(ir,yt)
            self.assertEqual(json.loads(ir.read_text())["publication"]["status"],"reconciliation_required")
            second=FakeYoutube()
            with self.assertRaisesRegex(RuntimeError,"reconcile"):
                self.call(ir,second)
            self.assertEqual(second.insert_calls,0)
    def test_requires_index_and_real_transcription_state(self):
        with tempfile.TemporaryDirectory() as root:
            _,ir=self.prepare(root)
            obj=json.loads(ir.read_text())
            obj["indexing"]["status"]="pending"
            ir.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,"index"):
                self.call(ir,FakeYoutube())

if __name__=="__main__":
    unittest.main()
