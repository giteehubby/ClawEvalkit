import unittest

from user_utils import get_display_name, get_initials


class TestUserUtils(unittest.TestCase):
    def test_display_name_with_nickname(self) -> None:
        self.assertEqual(get_display_name("John", "Doe", "Johnny"), "Johnny")

    def test_display_name_without_nickname(self) -> None:
        self.assertEqual(get_display_name("John", "Doe", None), "John Doe")

    def test_display_name_empty_nickname(self) -> None:
        self.assertEqual(get_display_name("John", "Doe", ""), "John Doe")

    def test_initials(self) -> None:
        self.assertEqual(get_initials("John", "Doe"), "JD")


if __name__ == "__main__":
    unittest.main()
