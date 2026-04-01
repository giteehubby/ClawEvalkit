import unittest

from calc import add, subtract


class TestCalc(unittest.TestCase):
    def test_add(self) -> None:
        self.assertEqual(add(2, 3), 5)

    def test_subtract(self) -> None:
        self.assertEqual(subtract(5, 3), 2)


if __name__ == "__main__":
    unittest.main()
