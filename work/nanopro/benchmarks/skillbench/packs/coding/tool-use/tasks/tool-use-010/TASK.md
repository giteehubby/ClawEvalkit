# tool-use-010: Validation Loop

The `validate.py` script should check each item in `items.json` and write validation results to `results.json`.

Each item has `name` (required string) and `value` (required positive number).
Results should be: `{"item_name": true/false, ...}`

Run tests to verify:
```
python3 -m unittest discover -s tests -p "test_*.py"
```
