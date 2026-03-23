import unittest

from stats import mean


class TestStats(unittest.TestCase):
    def test_mean(self) -> None:
        self.assertAlmostEqual(mean([1.0, 2.0, 3.0]), 2.0)

    def test_mean_single(self) -> None:
        self.assertAlmostEqual(mean([10.0]), 10.0)


if __name__ == "__main__":
    unittest.main()
