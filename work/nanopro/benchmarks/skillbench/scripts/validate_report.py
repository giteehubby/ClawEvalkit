#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: scripts/validate_report.py <report.json>", file=sys.stderr)
        return 2
    report_path = pathlib.Path(sys.argv[1])
    schema_path = pathlib.Path(__file__).resolve().parent.parent / "schemas" / "report.schema.json"

    try:
        import jsonschema
    except ImportError:
        print("Missing dependency: jsonschema. Install with `pip install jsonschema`.", file=sys.stderr)
        return 2

    report = json.loads(report_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(report, schema)
    print("Report is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
