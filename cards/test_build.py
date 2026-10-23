"""Tests for the card stats model: python3 -m unittest test_build"""
import unittest

import build

MPS = [
    {"name": "Иван Примеров", "born": "1970-01-01", "terms": [
        {"na": 50, "mpId": 1, "region": "23-СОФИЯ", "electedList": "ГЕРБ-СДС", "party": "gerb",
         "from": "2023-04-12", "to": "2024-06-18",
         "groups": [{"group": "ГЕРБ-СДС", "party": "gerb", "role": "Председател", "from": "2023-04-12", "to": "2024-06-18"}]},
        {"na": 51, "mpId": 2, "region": "23-СОФИЯ", "electedList": "ГЕРБ-СДС", "party": "gerb",
         "from": "2024-11-11", "to": None,
         "groups": [{"group": "ГЕРБ-СДС", "party": "gerb", "role": "Член", "from": "2024-11-11", "to": "2025-02-01"},
                    {"group": "Нечленуващи", "party": None, "role": "", "from": "2025-02-01", "to": None}]}]},
    {"name": "Мария Бивша", "born": "1980-01-01", "terms": [
        {"na": 50, "mpId": 3, "region": "16-ПЛОВДИВ", "electedList": "БСП", "party": "bsp",
         "from": "2023-04-12", "to": "2024-06-18", "groups": []}]},
]


class StatsModel(unittest.TestCase):
    def test_current_filter_keeps_sitting_mps(self):
        people = build.from_mps(MPS, current=True)
        self.assertEqual([p["name"] for p in people], ["Иван Примеров"])

    def test_mps_adapter_and_scoring(self):
        p = build.from_mps(MPS, current=False)[0]
        self.assertEqual(p["terms"], [50, 51])
        s = build.score(p)
        names = [k["name"] for k in s["keywords"]]
        self.assertIn("Лидер", names)          # group chair role
        self.assertIn("Независим", names)      # moved to Нечленуващи
        self.assertEqual(s["party"], "gerb")
        self.assertLess(s["stats"]["loyalty"], 10)

    def test_stats_are_bounded(self):
        register = {"politicians": [{"id": "x", "name": "Х", "path": [
            {"party": p, "from": "1990-01", "to": "2020-01", "note": "Основава, министър-председател"}
            for p in "abcdefgh"]}]}
        s = build.score(build.from_register(register)[0])
        for v in s["stats"].values():
            self.assertTrue(1 <= v <= 10)
        self.assertTrue(1 <= s["cost"] <= 7)

    def test_record_adds_keyword_and_kompromat(self):
        p = build.from_mps(MPS, current=False)[1]
        rec = [{"name": "Мария Бивша", "type": "conflict", "date": "2024-01",
                "summary": "Решение за конфликт на интереси", "source": "https://example.org/act"}]
        s = build.score(p, rec)
        self.assertEqual(s["keywords"][0]["name"], "Конфликт на интереси")
        self.assertEqual(s["kompromat"], 1)
        self.assertLessEqual(len(s["keywords"]), 3)
        self.assertEqual(build.score(p)["kompromat"], 0)

    def test_records_without_source_are_refused(self):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "r.json"
            f.write_text(json.dumps({"records": [{"name": "X", "type": "sanction", "source": ""}]}))
            with self.assertRaises(SystemExit):
                build.load_records(f)

    def test_months(self):
        self.assertEqual(build.months("2020-01", "2021-03"), 14)
        self.assertEqual(build.months(None, "2021-03"), 0)


if __name__ == "__main__":
    unittest.main()
