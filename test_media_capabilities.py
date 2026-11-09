import unittest
from media_capabilities import CATALOG, SCHEMA_VERSION, catalog_manifest, check_reuse


class SharedMediaCatalogTests(unittest.TestCase):
    def test_catalog_declares_contract_not_live_readiness(self):
        doc = catalog_manifest()
        self.assertEqual(doc["schema_version"], SCHEMA_VERSION)
        self.assertEqual(len(doc["capabilities"]), 4)
        self.assertTrue(all(c["implementation_status"] == "candidate" and
                            c["live_status"] == "unverified" for c in doc["capabilities"]))

    def test_unverified_contract_is_not_routable(self):
        required = {"media.capture.ingest", "media.video.index"}
        result = check_reuse(required, {})
        self.assertFalse(result["can_reuse_all"])
        self.assertEqual(result["live_candidates"], [])
        self.assertEqual(result["missing_or_unverified"], sorted(required))

    def test_live_verified_candidates_reusable_across_projects(self):
        # Same reusable provider is requested from unrelated scenarios.
        required = {"media.capture.ingest", "media.video.index"}
        live = {cap: True for cap in required}
        wow = check_reuse(required, live)
        studio = check_reuse(required, live)
        self.assertTrue(wow["can_reuse_all"])
        self.assertEqual(wow, studio)
        # This proves deterministic reuse logic only, NOT ONE acceptance or
        # real cross-project capability invocation / growth improvement.

    def test_unknown_and_external_write_fenced(self):
        result = check_reuse({"media.youtube.publish", "media.experimental.foo"},
                             {"media.youtube.publish": False, "media.experimental.foo": True})
        self.assertFalse(result["can_reuse_all"])
        self.assertEqual(result["unknown_contracts"], ["media.experimental.foo"])
        publish = next(c for c in CATALOG if c.capability_id == "media.youtube.publish")
        self.assertTrue(publish.external_write)


if __name__ == "__main__":
    unittest.main()
