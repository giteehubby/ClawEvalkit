# swe-lite-010

Fix the missing None check in `user_utils.get_display_name` so it handles users without a nickname gracefully.

Run the test suite to verify:
```
python3 -m unittest discover -s tests -p "test_*.py"
```
