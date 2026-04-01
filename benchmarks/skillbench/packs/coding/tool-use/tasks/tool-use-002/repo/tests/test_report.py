import unittest
import pathlib

class TestTodoReport(unittest.TestCase):
    def test_report_exists(self):
        report = pathlib.Path("todo_report.txt")
        self.assertTrue(report.exists(), "todo_report.txt should exist")

    def test_report_has_todos(self):
        report = pathlib.Path("todo_report.txt")
        content = report.read_text()
        self.assertIn("TODO", content, "report should contain TODO entries")

    def test_report_format(self):
        report = pathlib.Path("todo_report.txt")
        lines = report.read_text().strip().split('\n')
        for line in lines:
            self.assertIn(":", line, "each line should have filepath:lineno format")

if __name__ == "__main__":
    unittest.main()
