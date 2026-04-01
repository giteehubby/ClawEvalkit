# swe-lite-005

Fix the comparison operator bug in `validator.is_valid_age` so it correctly validates ages in the range [0, 150].

Run the test suite to verify:
```
python3 -m unittest discover -s tests -p "test_*.py"
```
