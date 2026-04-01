import unittest
import pathlib

class TestPipeline(unittest.TestCase):
    def test_output_exists(self):
        self.assertTrue(pathlib.Path("output.txt").exists())
    def test_output_correct(self):
        lines = pathlib.Path("output.txt").read_text().strip().split('\n')
        values = [int(x) for x in lines]
        self.assertEqual(values, [25, 4, 16])  # 5^2, 2^2, 4^2

if __name__ == "__main__":
    unittest.main()
