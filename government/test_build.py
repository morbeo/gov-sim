"""Tests for build.py: data integrity and page assembly."""
import copy
import json
import unittest
from pathlib import Path

import build

HERE = Path(__file__).resolve().parent
GOV = json.loads((HERE / "data/government.json").read_text(encoding="utf-8"))
CONST = json.loads((HERE / "data/constitution.json").read_text(encoding="utf-8"))


class TestData(unittest.TestCase):
    def test_real_data_is_valid(self):
        self.assertEqual(build.validate(GOV, CONST), [])

    def test_articles_in_parses_letters_and_lists(self):
        self.assertEqual(build.articles_in("чл. 99, ал. 5; чл. 130а, ал. 3"), ["99", "130а"])

    def test_missing_article_is_reported(self):
        gov = copy.deepcopy(GOV)
        gov["edges"][0]["ref"] = "чл. 999"
        self.assertTrue(any("чл. 999" in e for e in build.validate(gov, CONST)))

    def test_edge_without_source_is_reported(self):
        gov = copy.deepcopy(GOV)
        gov["edges"][0].pop("ref", None)
        gov["edges"][0].pop("law", None)
        self.assertTrue(any("без източник" in e for e in build.validate(gov, CONST)))

    def test_unknown_node_in_scenario_is_reported(self):
        gov = copy.deepcopy(GOV)
        gov["scenarios"][0]["steps"][0]["nodes"].append("nope")
        self.assertTrue(any("nope" in e for e in build.validate(gov, CONST)))


class TestBuild(unittest.TestCase):
    def test_data_is_inlined_and_script_safe(self):
        gov = copy.deepcopy(GOV)
        gov["nodes"][0]["comp"] = "</script>"
        html = build.build(gov, CONST, "<script>const D = /*__DATA__*/null;</script>")
        self.assertNotIn("/*__DATA__*/", html)
        self.assertNotIn("</script>\"", html)

    def test_template_without_placeholder_fails(self):
        with self.assertRaises(ValueError):
            build.build(GOV, CONST, "<html></html>")


if __name__ == "__main__":
    unittest.main()
