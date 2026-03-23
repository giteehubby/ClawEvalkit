import unittest

from string_utils import slugify


class TestStringUtils(unittest.TestCase):
    def test_slugify_spaces(self) -> None:
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_slugify_punct(self) -> None:
        self.assertEqual(slugify("Hello, World!!!"), "hello-world")


if __name__ == "__main__":
    unittest.main()
