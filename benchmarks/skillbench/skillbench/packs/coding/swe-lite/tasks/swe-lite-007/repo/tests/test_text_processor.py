import unittest

from text_processor import remove_extra_spaces, normalize_whitespace


class TestTextProcessor(unittest.TestCase):
    def test_remove_extra_spaces(self) -> None:
        self.assertEqual(remove_extra_spaces("hello   world"), "hello world")
        self.assertEqual(remove_extra_spaces("  hello  "), "hello")

    def test_normalize_whitespace(self) -> None:
        self.assertEqual(normalize_whitespace("hello\t\nworld"), "hello world")


if __name__ == "__main__":
    unittest.main()
