import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from publication_lock import publication_lock
from youtube_private_publisher import publish_private
from test_youtube_private_publisher import PublishTests, FakeYoutube


class PublicationLockTests(TestCase):
    def test_second_worker_denied_even_if_ir_is_valid(self):
        with TemporaryDirectory() as folder:
            helper = PublishTests()
            media, ir_path = helper.prepare(folder)
            yt = FakeYoutube()
            with publication_lock(ir_path):
                with self.assertRaisesRegex(RuntimeError, "locked"):
                    publish_private(str(ir_path), youtube=yt,
                                    media_factory=lambda path: path,
                                    title="Example", description="Description",
                                    authorized=True, channel_verified=True)
            self.assertEqual(yt.insert_calls, 0)
            self.assertEqual(json.loads(ir_path.read_text())["publication"]["status"], "not_authorized")
            self.assertEqual(media.read_bytes(), b"unchanged video")

    def test_lock_released_on_normal_exception(self):
        with TemporaryDirectory() as folder:
            ir_path = Path(folder) / "video.json"
            with self.assertRaisesRegex(ValueError, "test failure"):
                with publication_lock(ir_path):
                    raise ValueError("test failure")
            with publication_lock(ir_path):
                self.assertTrue(True)

    def test_existing_orphan_lock_fails_closed(self):
        with TemporaryDirectory() as folder:
            ir_path = Path(folder) / "video.json"
            lock = ir_path.with_name(ir_path.name + ".publish.lock")
            lock.write_text("abandoned-owner")
            with self.assertRaisesRegex(RuntimeError, "locked"):
                with publication_lock(ir_path):
                    pass
            self.assertEqual(lock.read_text(), "abandoned-owner")
