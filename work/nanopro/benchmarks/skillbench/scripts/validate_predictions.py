#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: scripts/validate_predictions.py <predictions.jsonl>", file=sys.stderr)
        return 2
    pred_path = pathlib.Path(sys.argv[1])
    schema_path = pathlib.Path(__file__).resolve().parent.parent / "schemas" / "predictions.schema.json"

    try:
        import jsonschema
    except ImportError:
        print("Missing dependency: jsonschema. Install with `pip install jsonschema`.", file=sys.stderr)
        return 2

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    for idx, line in enumerate(pred_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        jsonschema.validate(json.loads(line), schema)
    print("Predictions JSONL is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
