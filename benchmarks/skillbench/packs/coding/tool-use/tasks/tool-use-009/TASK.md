# tool-use-009: Multi-Step Pipeline

Create a data pipeline:
1. Read numbers from `input.txt` (one per line)
2. Filter out negative numbers
3. Square each remaining number
4. Write results to `output.txt`

Run tests to verify:
```
python3 -m unittest discover -s tests -p "test_*.py"
```
