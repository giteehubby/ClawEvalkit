import unittest
import pathlib

class TestCheck(unittest.TestCase):
    def test_status_exists(self):
        self.assertTrue(pathlib.Path("status.txt").exists())
    def test_status_format(self):
        content = pathlib.Path("status.txt").read_text()
        self.assertIn("EXISTS", content)
        self.assertIn("MISSING", content)

if __name__ == "__main__":
    unittest.main()
