"""NodeAdapter contract test; no real Windows node or ONE identity claimed."""
import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from media_node_adapter import CAPABILITY, MediaIngestAdapter, create_adapter


class MediaNodeAdapterTests(unittest.TestCase):
    def test_factory_fails_closed(self):
        adapter = create_adapter()
        self.assertEqual(adapter.capabilities(), (CAPABILITY,))
        self.assertEqual(adapter.describe()["live_verified"], False)
        self.assertEqual(adapter.execute({"action": CAPABILITY})["status"], "UNAVAILABLE")

    def test_refuse_task_controlled_file_paths_and_shell(self):
        adapter = MediaIngestAdapter(approved_folder="C:/approved", ir_dir="C:/ir",
                                    scanner=lambda *a, **k: {"schema_version":"agentos.media-watch-scan/v1"})
        for request in [
            {"action":"shell.exec"},
            {"action":CAPABILITY,"folder":"C:/private"},
            {"action":CAPABILITY,"command":"whoami"},
            {"action":CAPABILITY,"allow":"*"},
        ]:
            with self.subTest(request=request), self.assertRaises(ValueError):
                adapter.execute(request)

    def test_trusted_source_binding_and_receipt_boundary(self):
        calls = []
        def scan(folder, ir_dir, **kwargs):
            calls.append((folder,ir_dir,kwargs["source"]))
            return {"schema_version":"agentos.media-watch-scan/v1",
                    "ingested":[{"file":"a.mp4","asset_id":"sha256:sample"}],
                    "failures":[],"one_receipt_status":"not_submitted"}
        adapter = MediaIngestAdapter(approved_folder="C:/Videos",ir_dir="C:/MediaIR",
                                    source="wow",scanner=scan)
        result=adapter.execute({"action":CAPABILITY})
        self.assertEqual(calls,[("C:/Videos","C:/MediaIR","wow")])
        self.assertEqual(result["status"],"OK")
        self.assertEqual(result["one_receipt_status"],"not_submitted")

    def test_real_registry_factory_requires_trusted_environment(self):
        with TemporaryDirectory() as root:
            media = Path(root) / "recordings"
            media.mkdir()
            ir = Path(root) / "ir"
            env = {
                "AGENTOS_MEDIA_ENABLED": "1",
                "AGENTOS_MEDIA_APPROVED_ROOT": str(media),
                "AGENTOS_MEDIA_IR_DIR": str(ir),
                "AGENTOS_MEDIA_SOURCE": "wow",
            }
            with patch.dict(os.environ, env, clear=True):
                adapter = create_adapter()
                self.assertEqual(adapter.capabilities(), (CAPABILITY,))
                # No movie files, but this actually invokes the allowed scan.
                outcome = adapter.execute({"action": CAPABILITY})
                self.assertEqual(outcome["status"], "OK")
                self.assertEqual(outcome["one_receipt_status"], "not_submitted")
                self.assertFalse(adapter.describe()["live_verified"])

    def test_incomplete_or_disabled_config_stays_unbound(self):
        with TemporaryDirectory() as root:
            for config in (
                {"AGENTOS_MEDIA_ENABLED":"0", "AGENTOS_MEDIA_APPROVED_ROOT": root,
                 "AGENTOS_MEDIA_IR_DIR": root + "/ir"},
                {"AGENTOS_MEDIA_ENABLED":"1", "AGENTOS_MEDIA_APPROVED_ROOT": root},
                {"AGENTOS_MEDIA_ENABLED":"1", "AGENTOS_MEDIA_APPROVED_ROOT": "relative",
                 "AGENTOS_MEDIA_IR_DIR": root + "/ir"},
                {"AGENTOS_MEDIA_ENABLED":"1", "AGENTOS_MEDIA_APPROVED_ROOT": root,
                 "AGENTOS_MEDIA_IR_DIR": root},
            ):
                with self.subTest(config=config), patch.dict(os.environ, config, clear=True):
                    outcome = create_adapter().execute({"action": CAPABILITY})
                    self.assertEqual(outcome["status"], "UNAVAILABLE")


if __name__ == '__main__':
    unittest.main()
