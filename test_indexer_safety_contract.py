"""Source regression tests: old indexing must never delete user-owned inputs."""
import ast
from pathlib import Path
import unittest


class IndexerSafetyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).with_name("youtube_ai_manager.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_tls_validation_is_not_disabled(self):
        self.assertNotIn("ssl.CERT_NONE", self.source)
        self.assertNotIn("check_hostname = False", self.source)

    def test_indexing_takes_explicit_owned_temp_flag_default_false(self):
        func = next(node for node in self.tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "analyze_video_multimodal")
        args = func.args
        self.assertIn("owned_temp", args.kwonlyargs and [a.arg for a in args.kwonlyargs])
        offset = [a.arg for a in args.kwonlyargs].index("owned_temp")
        self.assertIs(args.kw_defaults[offset].value, False)

    def test_owned_temp_guard_around_delete(self):
        func = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "analyze_video_multimodal")
        guarded = []
        for node in ast.walk(func):
            if isinstance(node, ast.If):
                condition = ast.unparse(node.test)
                if "owned_temp" in condition:
                    guarded.extend(ast.walk(node))
        self.assertTrue(any(isinstance(n, ast.Call)
                            and isinstance(n.func, ast.Attribute)
                            and n.func.attr == "remove"
                            for n in guarded))


if __name__ == "__main__":
    unittest.main()
