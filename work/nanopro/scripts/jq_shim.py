#!/usr/bin/env python3
"""
Very small jq-compatible shim for the claw-bench shell tests.

Supported features:
  -r
  -e
  simple field paths like `.name`, `.result.payloads[0].text`
  array expansion like `.result.payloads[].text`
  fallback chains with `//`
  boolean conjunctions with `and`
  `| length`
  stdin input or a single file argument
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _normalize(expr: str) -> str:
    return " ".join(line.strip() for line in expr.strip().splitlines() if line.strip())


def _split_top_level(expr: str, delim: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    in_string = False
    while i < len(expr):
        ch = expr[i]
        if ch == '"':
            in_string = not in_string
            buf.append(ch)
            i += 1
            continue
        if not in_string and expr.startswith(delim, i):
            parts.append("".join(buf).strip())
            buf = []
            i += len(delim)
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf).strip())
    return parts


def _is_truthy(value) -> bool:
    if value is None or value is False:
        return False
    if value == "" or value == [] or value == {}:
        return False
    return True


def _parse_path(expr: str) -> tuple[list[tuple[str, str | int | None]], str | None]:
    expr = expr.strip()
    length_suffix = None
    if " | " in expr:
        expr, op = [part.strip() for part in expr.split("|", 1)]
        length_suffix = op
    if expr == ".":
        return [], length_suffix
    if not expr.startswith("."):
        raise ValueError(f"Unsupported jq expression: {expr}")

    tokens: list[tuple[str, str | int | None]] = []
    i = 1
    while i < len(expr):
        if expr[i] == ".":
            i += 1
            continue
        if expr[i] == "[":
            end = expr.index("]", i)
            body = expr[i + 1 : end]
            if body == "":
                tokens.append(("expand", None))
            else:
                tokens.append(("index", int(body)))
            i = end + 1
            continue

        start = i
        while i < len(expr) and expr[i] not in ".[":
            i += 1
        tokens.append(("field", expr[start:i]))

    return tokens, length_suffix


def _apply_path(data, expr: str):
    tokens, suffix = _parse_path(expr)
    values = [data]

    for kind, payload in tokens:
        next_values = []
        for value in values:
            if kind == "field":
                if isinstance(value, dict) and payload in value:
                    next_values.append(value[payload])
            elif kind == "index":
                if isinstance(value, list) and 0 <= int(payload) < len(value):
                    next_values.append(value[int(payload)])
            elif kind == "expand":
                if isinstance(value, list):
                    next_values.extend(value)
        values = next_values

    if suffix == "length":
        if len(values) == 1:
            value = values[0]
            if isinstance(value, (list, dict, str)):
                return len(value)
            return 0
        return len(values)
    if not tokens:
        return data
    if len(values) == 1:
        return values[0]
    return values


def _eval_expr(data, expr: str):
    expr = _normalize(expr)

    if " and " in expr:
        return all(_is_truthy(_eval_expr(data, part)) for part in _split_top_level(expr, " and "))

    if " // " in expr:
        for part in _split_top_level(expr, " // "):
            value = _eval_expr(data, part)
            if _is_truthy(value):
                return value
        return None

    if expr.startswith('"') and expr.endswith('"'):
        return json.loads(expr)

    if expr in {"true", "false", "null"}:
        return {"true": True, "false": False, "null": None}[expr]

    return _apply_path(data, expr)


def _format_value(value, raw: bool) -> str:
    if isinstance(value, list):
        if raw:
            return "\n".join(_format_value(item, True) for item in value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if raw:
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    raw = False
    exit_status = False

    while args and args[0].startswith("-"):
        flag = args.pop(0)
        if flag == "-r":
            raw = True
        elif flag == "-e":
            exit_status = True
        else:
            print(f"Unsupported jq option: {flag}", file=sys.stderr)
            return 2

    if not args:
        print("Usage: jq [-r] [-e] <filter> [file]", file=sys.stderr)
        return 2

    expr = args.pop(0)
    if args:
        source = Path(args[0]).read_text(encoding="utf-8")
    else:
        source = sys.stdin.read()

    try:
        data = json.loads(source)
        value = _eval_expr(data, expr)
    except Exception:
        return 4

    if exit_status and not _is_truthy(value):
        return 1

    sys.stdout.write(_format_value(value, raw))
    if not str(_format_value(value, raw)).endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
