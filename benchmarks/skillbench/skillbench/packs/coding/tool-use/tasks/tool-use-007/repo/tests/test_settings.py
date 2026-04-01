import unittest
import json
import pathlib

class TestSettings(unittest.TestCase):
    def test_json_exists(self):
        self.assertTrue(pathlib.Path("settings.json").exists())
    def test_json_has_database(self):
        data = json.loads(pathlib.Path("settings.json").read_text())
        self.assertIn("database", data)
    def test_values_match(self):
        data = json.loads(pathlib.Path("settings.json").read_text())
        self.assertEqual(data["database"]["host"], "localhost")
        self.assertEqual(data["database"]["port"], "5432")

if __name__ == "__main__":
    unittest.main()
