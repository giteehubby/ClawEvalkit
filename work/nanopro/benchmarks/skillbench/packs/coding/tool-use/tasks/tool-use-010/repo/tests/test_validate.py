import unittest
import json
import pathlib

class TestValidate(unittest.TestCase):
    def test_results_exists(self):
        self.assertTrue(pathlib.Path("results.json").exists())
    def test_results_correct(self):
        data = json.loads(pathlib.Path("results.json").read_text())
        self.assertEqual(data.get("alpha"), True)   # valid
        self.assertEqual(data.get(""), False)       # empty name
        self.assertEqual(data.get("gamma"), False)  # negative value
        self.assertEqual(data.get("delta"), True)   # valid

if __name__ == "__main__":
    unittest.main()
