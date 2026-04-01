import unittest


class TestSummary(unittest.TestCase):
    def test_summary_filled(self) -> None:
        with open("summary.md", "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Executive Summary:", content)
        self.assertIn("Customer retention improved and churn decreased.", content)


if __name__ == "__main__":
    unittest.main()
