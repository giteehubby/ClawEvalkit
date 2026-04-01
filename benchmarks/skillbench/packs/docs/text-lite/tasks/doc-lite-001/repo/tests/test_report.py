import unittest


class TestReport(unittest.TestCase):
    def test_report_filled(self) -> None:
        with open("report.md", "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Title: Q1 Report", content)
        self.assertIn("Summary: Revenue increased by 12%.", content)


if __name__ == "__main__":
    unittest.main()
