import unittest

from converter import celsius_to_fahrenheit, fahrenheit_to_celsius


class TestConverter(unittest.TestCase):
    def test_celsius_to_fahrenheit(self) -> None:
        self.assertAlmostEqual(celsius_to_fahrenheit(0), 32.0)
        self.assertAlmostEqual(celsius_to_fahrenheit(100), 212.0)

    def test_fahrenheit_to_celsius(self) -> None:
        self.assertAlmostEqual(fahrenheit_to_celsius(32), 0.0)
        self.assertAlmostEqual(fahrenheit_to_celsius(212), 100.0)


if __name__ == "__main__":
    unittest.main()
