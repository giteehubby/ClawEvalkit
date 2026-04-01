import unittest

from validator import is_valid_age, is_valid_email


class TestValidator(unittest.TestCase):
    def test_valid_age(self) -> None:
        self.assertTrue(is_valid_age(25))
        self.assertTrue(is_valid_age(0))
        self.assertTrue(is_valid_age(150))

    def test_invalid_age(self) -> None:
        self.assertFalse(is_valid_age(-1))
        self.assertFalse(is_valid_age(151))

    def test_valid_email(self) -> None:
        self.assertTrue(is_valid_email("test@example.com"))


if __name__ == "__main__":
    unittest.main()
