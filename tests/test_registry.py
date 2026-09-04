import unittest

from connectors import registry


class RegistryTests(unittest.TestCase):
    def test_discovers_all_six_shipped_connectors(self):
        names = registry.list_source_files()
        expected = {"openalex", "crossref", "semanticscholar", "pubmed", "europepmc", "arxiv"}
        self.assertTrue(expected.issubset(set(names)), names)
        self.assertNotIn("_shared", names)
        self.assertNotIn("registry", names)

    def test_list_sources_reports_source_key_and_base_url_for_every_connector(self):
        sources = registry.list_sources()
        by_name = {s["name"]: s for s in sources}
        self.assertEqual(by_name["openalex"]["source_key"], "openalex")
        self.assertTrue(by_name["openalex"]["base_url"].startswith("http"))
        # pubmed/arxiv/europepmc/semanticscholar use SOURCE, not SOURCE_KEY -- both must resolve.
        self.assertEqual(by_name["pubmed"]["source_key"], "pubmed")

    def test_optional_api_key_env_only_set_for_sources_that_have_one(self):
        sources = {s["source_key"]: s for s in registry.list_sources()}
        self.assertEqual(sources["pubmed"]["api_key_env"], "NCBI_API_KEY")
        self.assertEqual(sources["semanticscholar"]["api_key_env"], "S2_API_KEY")
        self.assertIsNone(sources["openalex"]["api_key_env"])

    def test_get_source_module_imports_the_real_module(self):
        mod = registry.get_source_module("openalex")
        self.assertTrue(hasattr(mod, "main"))


if __name__ == "__main__":
    unittest.main()
