# tool-use-004: Missing File Handling

Create a script `check_files.py` that reads a list of filenames from `filelist.txt` and writes to `status.txt` whether each file exists or not.

Format: `filename: EXISTS` or `filename: MISSING`

Run tests to verify:
```
python3 -m unittest discover -s tests -p "test_*.py"
```
