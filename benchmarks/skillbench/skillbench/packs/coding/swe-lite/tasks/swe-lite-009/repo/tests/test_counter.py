import unittest

from counter import count_vowels, count_consonants


class TestCounter(unittest.TestCase):
    def test_count_vowels(self) -> None:
        self.assertEqual(count_vowels("hello"), 2)
        self.assertEqual(count_vowels("aeiou"), 5)

    def test_count_vowels_ending(self) -> None:
        self.assertEqual(count_vowels("banana"), 3)

    def test_count_consonants(self) -> None:
        self.assertEqual(count_consonants("hello"), 3)


if __name__ == "__main__":
    unittest.main()
