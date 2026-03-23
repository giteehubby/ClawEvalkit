# tool-use-002: Multi-file Search

Find all `.py` files in the `src/` directory that contain the string `TODO` and create a file `todo_report.txt` listing each file path and line number.

Format: `filepath:lineno: <line content>`

Run tests to verify:
```
python3 -m unittest discover -s tests -p "test_*.py"
```
