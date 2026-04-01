import unittest

from array_utils import get_last_n, get_first_n


class TestArrayUtils(unittest.TestCase):
    def test_get_last_n(self) -> None:
        self.assertEqual(get_last_n([1, 2, 3, 4, 5], 3), [3, 4, 5])

    def test_get_last_n_all(self) -> None:
        self.assertEqual(get_last_n([1, 2, 3], 3), [1, 2, 3])

    def test_get_first_n(self) -> None:
        self.assertEqual(get_first_n([1, 2, 3, 4, 5], 2), [1, 2])


if __name__ == "__main__":
    unittest.main()
