#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def patch_calc(path: pathlib.Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if "def add" not in text:
        return False
    if "return a - b" not in text:
        return False
    updated = text.replace("return a - b", "return a + b", 1)
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    cwd = pathlib.Path.cwd()
    target = cwd / "calc.py"
    if patch_calc(target):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
