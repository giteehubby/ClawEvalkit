import unittest
from user import User

class TestUser(unittest.TestCase):
    def test_greet(self):
        u = User("Alice", "alice@example.com")
        self.assertEqual(u.greet(), "Hello, Alice!")
    def test_greet_bob(self):
        u = User("Bob", "bob@example.com")
        self.assertEqual(u.greet(), "Hello, Bob!")

if __name__ == "__main__":
    unittest.main()
