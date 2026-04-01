import unittest
import sys
sys.setrecursionlimit(100)
from calc import factorial

class TestCalc(unittest.TestCase):
    def test_factorial_0(self):
        self.assertEqual(factorial(0), 1)
    def test_factorial_5(self):
        self.assertEqual(factorial(5), 120)
    def test_factorial_1(self):
        self.assertEqual(factorial(1), 1)

if __name__ == "__main__":
    unittest.main()
