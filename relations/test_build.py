"""Tests for the relationship map data: python3 -m unittest test_build"""
import unittest

import build

REGISTER = {
    "parties": [
        {"id": "a", "short": "А", "name": "Партия А", "color": "#111111", "seats": {"50": 40}},
        {"id": "b", "short": "Б", "name": "Партия Б", "color": "#222222", "seats": {}},
    ],
    "links": [{"date": "2020-01", "from": "a", "to": "b", "type": "split", "note": "Б се отцепва."}],
    "politicians": [{"id": "x", "name": "Иван Иванов", "path": [
        {"party": "a", "from": "2010-01", "to": "2020-01"},
        {"gap": "Пауза", "from": "2020-01", "to": "2021-01"},
        {"party": "b", "from": "2021-01", "to": None, "note": "Основава Б"}]}],
}


class Derive(unittest.TestCase):
    def test_parties_people_and_links(self):
        nodes, edges = build.derive(REGISTER)
        ids = {n["id"] for n in nodes}
        self.assertEqual(ids, {"p:a", "p:b", "pol:x"})
        self.assertEqual(next(n for n in nodes if n["id"] == "p:a")["seats"], 40)
        self.assertEqual(next(n for n in nodes if n["id"] == "pol:x")["party"], "b")
        types = sorted(e["type"] for e in edges)
        self.assertEqual(types, ["founder", "member", "split"])
        self.assertTrue(all(e["status"] == "documented" and e["source"] for e in edges))


class Validate(unittest.TestCase):
    def check(self, manual):
        nodes, _ = build.derive(REGISTER)
        return build.validate(manual, nodes, {"a", "b"})

    def test_good_data(self):
        manual = {"nodes": [{"id": "m", "type": "oligarch", "label": "Бизнесмен"}],
                  "edges": [{"from": "m", "to": "p:a", "type": "funding", "status": "claim"}]}
        self.assertEqual(self.check(manual), [])

    def test_unknown_node_type_status_and_party(self):
        manual = {"nodes": [{"id": "m", "type": "alien", "label": "Х", "party": "zz"}],
                  "edges": [{"from": "m", "to": "nobody", "type": "magic", "status": "fact"}]}
        errors = "\n".join(self.check(manual))
        for word in ("alien", "zz", "nobody", "magic", "статусът"):
            self.assertIn(word, errors)

    def test_duplicate_id(self):
        manual = {"nodes": [{"id": "m", "type": "media", "label": "М"}, {"id": "m", "type": "media", "label": "М2"}]}
        self.assertTrue(any("повторен" in e for e in self.check(manual)))

    def test_payload_rejects_bad_data(self):
        with self.assertRaises(build.DataError):
            build.payload(REGISTER, {"edges": [{"from": "p:a", "to": "p:b", "type": "influence", "status": "?"}]})

    def test_payload_gives_edges_ids(self):
        data = build.payload(REGISTER, {"edges": [{"from": "p:a", "to": "p:b", "type": "influence", "status": "rumor"}]})
        self.assertEqual(data["base"]["edges"][0]["id"], "m0")


if __name__ == "__main__":
    unittest.main()
