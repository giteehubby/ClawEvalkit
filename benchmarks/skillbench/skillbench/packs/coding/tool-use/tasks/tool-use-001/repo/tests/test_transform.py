import unittest
import pathlib

class TestTransform(unittest.TestCase):
    def test_output_exists(self):
        output = pathlib.Path("data/output.txt")
        self.assertTrue(output.exists(), "output.txt should exist")

    def test_output_is_uppercase(self):
        output = pathlib.Path("data/output.txt")
        content = output.read_text()
        self.assertEqual(content, content.upper(), "content should be uppercase")

    def test_output_matches_input(self):
        input_path = pathlib.Path("data/input.txt")
        output_path = pathlib.Path("data/output.txt")
        expected = input_path.read_text().upper()
        actual = output_path.read_text()
        self.assertEqual(actual, expected)

if __name__ == "__main__":
    unittest.main()
