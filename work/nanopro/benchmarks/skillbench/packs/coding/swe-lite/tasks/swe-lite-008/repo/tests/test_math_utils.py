import unittest

from math_utils import percentage, clamp


class TestMathUtils(unittest.TestCase):
    def test_percentage(self) -> None:
        self.assertAlmostEqual(percentage(1, 4), 25.0)
        self.assertAlmostEqual(percentage(3, 4), 75.0)

    def test_percentage_zero(self) -> None:
        self.assertAlmostEqual(percentage(5, 0), 0.0)

    def test_clamp(self) -> None:
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-5, 0, 10), 0)
        self.assertEqual(clamp(15, 0, 10), 10)


if __name__ == "__main__":
    unittest.main()
