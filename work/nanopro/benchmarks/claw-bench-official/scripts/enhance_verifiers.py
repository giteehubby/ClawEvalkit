#!/usr/bin/env python3
"""Batch-enhance existing task verifiers with robustness/quality/strictness checks.

Scans each task's instruction.md and existing test_output.py to determine the
output file type(s), then appends new test functions that do NOT overlap with
existing tests.

Usage:
    python scripts/enhance_verifiers.py              # dry-run (shows what would change)
    python scripts/enhance_verifiers.py --apply      # actually write changes
"""

from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path

TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"

PLACEHOLDER_PATTERNS = [
    "TODO", "FIXME", "XXX", "PLACEHOLDER", "CHANGEME",
    "your_", "example.com", "lorem ipsum",
]

SEPARATOR = "\n\n# ── Enhanced checks (auto-generated) " + "─" * 40 + "\n\n"


def detect_output_files(instruction: str, verifier_code: str) -> list[dict]:
    """Detect output files from instruction and verifier code."""
    outputs = []
    patterns = [
        (r'["\']?workspace/(\w[\w\-./]*\.\w+)', None),
        (r'output[_.]?(\w*)\.(json|csv|txt|md|py|yaml|yml|html|xml|sql)', None),
        (r'(\w[\w\-]*\.(json|csv|txt|md|py|yaml|yml|html|xml|sql))', None),
    ]
    seen = set()
    combined = instruction + "\n" + verifier_code

    for pat, _ in patterns:
        for m in re.finditer(pat, combined):
            fname = m.group(0).strip("'\"")
            if fname.startswith("workspace/"):
                fname = fname[len("workspace/"):]
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if fname not in seen and ext in ("json", "csv", "txt", "md", "py", "yaml", "yml", "html", "xml", "sql"):
                seen.add(fname)
                outputs.append({"name": fname, "ext": ext})

    if not outputs:
        for ext in ("json", "csv", "txt"):
            if f".{ext}" in verifier_code.lower():
                outputs.append({"name": f"output.{ext}", "ext": ext})
                break

    return outputs


def generate_robustness_checks(outputs: list[dict], existing_code: str) -> str:
    """Generate robustness test functions."""
    lines = []

    if "test_no_placeholder_values" not in existing_code:
        placeholder_list = ", ".join(f'"{p}"' for p in PLACEHOLDER_PATTERNS[:6])
        lines.append(textwrap.dedent(f'''\
            @pytest.mark.weight(1)
            def test_no_placeholder_values(workspace):
                """Output files must not contain placeholder/TODO markers."""
                placeholders = [{placeholder_list}]
                for f in workspace.iterdir():
                    if f.is_file() and f.suffix in (".json", ".csv", ".txt", ".md", ".py", ".yaml", ".yml", ".html", ".xml"):
                        content = f.read_text(errors="replace").lower()
                        for p in placeholders:
                            assert p.lower() not in content, f"Placeholder '{{p}}' found in {{f.name}}"
        '''))

    if "test_no_empty_critical_fields" not in existing_code:
        for out in outputs:
            if out["ext"] == "json":
                lines.append(textwrap.dedent(f'''\
                    @pytest.mark.weight(2)
                    def test_no_empty_critical_fields(workspace):
                        """JSON output must not have empty-string or null values in top-level fields."""
                        import json
                        path = workspace / "{out['name']}"
                        if not path.exists():
                            pytest.skip("output file not found")
                        data = json.loads(path.read_text())
                        items = data if isinstance(data, list) else [data]
                        for i, item in enumerate(items):
                            if not isinstance(item, dict):
                                continue
                            for k, v in item.items():
                                assert v is not None, f"Item {{i}}: field '{{k}}' is null"
                                if isinstance(v, str):
                                    assert v.strip() != "", f"Item {{i}}: field '{{k}}' is empty string"
                '''))
                break

    if "test_encoding_valid" not in existing_code:
        lines.append(textwrap.dedent('''\
            @pytest.mark.weight(1)
            def test_encoding_valid(workspace):
                """All text output files must be valid UTF-8."""
                for f in workspace.iterdir():
                    if f.is_file() and f.suffix in (".json", ".csv", ".txt", ".md", ".py", ".yaml", ".yml", ".html"):
                        try:
                            f.read_text(encoding="utf-8")
                        except UnicodeDecodeError:
                            pytest.fail(f"{f.name} contains invalid UTF-8 encoding")
        '''))

    return "\n".join(lines)


def generate_quality_checks(outputs: list[dict], existing_code: str) -> str:
    """Generate quality tier test functions."""
    lines = []

    if "test_consistent_key_naming" not in existing_code:
        for out in outputs:
            if out["ext"] == "json":
                lines.append(textwrap.dedent(f'''\
                    @pytest.mark.weight(1)
                    def test_consistent_key_naming(workspace):
                        """JSON keys should use a consistent naming convention."""
                        import json, re
                        path = workspace / "{out['name']}"
                        if not path.exists():
                            pytest.skip("output file not found")
                        data = json.loads(path.read_text())
                        items = data if isinstance(data, list) else [data]
                        all_keys = set()
                        for item in items:
                            if isinstance(item, dict):
                                all_keys.update(item.keys())
                        if len(all_keys) < 2:
                            return
                        snake = sum(1 for k in all_keys if re.match(r'^[a-z][a-z0-9_]*$', k))
                        camel = sum(1 for k in all_keys if re.match(r'^[a-z][a-zA-Z0-9]*$', k) and not re.match(r'^[a-z][a-z0-9_]*$', k))
                        pascal = sum(1 for k in all_keys if re.match(r'^[A-Z][a-zA-Z0-9]*$', k))
                        dominant = max(snake, camel, pascal)
                        consistency = dominant / len(all_keys) if all_keys else 1
                        assert consistency >= 0.7, f"Key naming inconsistent: {{snake}} snake, {{camel}} camel, {{pascal}} pascal out of {{len(all_keys)}} keys"
                '''))
                break

    if "test_no_duplicate_entries" not in existing_code:
        for out in outputs:
            if out["ext"] in ("json", "csv"):
                lines.append(textwrap.dedent(f'''\
                    @pytest.mark.weight(1)
                    def test_no_duplicate_entries(workspace):
                        """Output should not contain exact duplicate rows/objects."""
                        import json
                        path = workspace / "{out['name']}"
                        if not path.exists():
                            pytest.skip("output file not found")
                        text = path.read_text().strip()
                        if path.suffix == ".json":
                            data = json.loads(text)
                            if isinstance(data, list):
                                serialized = [json.dumps(item, sort_keys=True) for item in data]
                                dupes = len(serialized) - len(set(serialized))
                                assert dupes == 0, f"Found {{dupes}} duplicate entries in {{path.name}}"
                        elif path.suffix == ".csv":
                            lines_list = text.splitlines()
                            if len(lines_list) > 1:
                                data_lines = lines_list[1:]
                                dupes = len(data_lines) - len(set(data_lines))
                                assert dupes == 0, f"Found {{dupes}} duplicate rows in {{path.name}}"
                '''))
                break

    return "\n".join(lines)


def generate_strictness_checks(outputs: list[dict], existing_code: str) -> str:
    """Generate strictness test functions."""
    lines = []

    if "test_no_extraneous_files" not in existing_code:
        lines.append(textwrap.dedent('''\
            @pytest.mark.weight(1)
            def test_no_extraneous_files(workspace):
                """Workspace should not contain debug/temp files."""
                bad_patterns = [".pyc", "__pycache__", ".DS_Store", "Thumbs.db", ".log", ".bak", ".tmp"]
                for f in workspace.rglob("*"):
                    if f.is_file():
                        for pat in bad_patterns:
                            assert pat not in f.name, f"Extraneous file found: {f.name}"
        '''))

    if "test_output_not_excessively_large" not in existing_code:
        lines.append(textwrap.dedent('''\
            @pytest.mark.weight(1)
            def test_output_not_excessively_large(workspace):
                """Output files should be reasonably sized (< 5MB each)."""
                for f in workspace.iterdir():
                    if f.is_file() and f.suffix in (".json", ".csv", ".txt", ".md", ".py", ".yaml", ".yml", ".html"):
                        size_mb = f.stat().st_size / (1024 * 1024)
                        assert size_mb < 5, f"{f.name} is {size_mb:.1f}MB, exceeds 5MB limit"
        '''))

    if "test_json_parseable_if_present" not in existing_code and "json" not in existing_code.lower()[:200]:
        for out in outputs:
            if out["ext"] == "json":
                break
        else:
            lines.append(textwrap.dedent('''\
                @pytest.mark.weight(2)
                def test_json_parseable_if_present(workspace):
                    """Any .json files in workspace must be valid JSON."""
                    import json
                    for f in workspace.iterdir():
                        if f.is_file() and f.suffix == ".json":
                            try:
                                json.loads(f.read_text())
                            except json.JSONDecodeError:
                                pytest.fail(f"{f.name} is not valid JSON")
            '''))

    return "\n".join(lines)


def enhance_verifier(task_dir: Path, dry_run: bool = True) -> tuple[int, str]:
    """Enhance a single task's verifier. Returns (added_count, summary)."""
    verifier = task_dir / "verifier" / "test_output.py"
    instruction = task_dir / "instruction.md"

    if not verifier.exists():
        return 0, "no verifier"

    existing_code = verifier.read_text()
    inst_text = instruction.read_text() if instruction.exists() else ""

    if SEPARATOR.strip() in existing_code:
        return 0, "already enhanced"

    outputs = detect_output_files(inst_text, existing_code)

    robustness = generate_robustness_checks(outputs, existing_code)
    quality = generate_quality_checks(outputs, existing_code)
    strictness = generate_strictness_checks(outputs, existing_code)

    new_checks = []
    for block in [robustness, quality, strictness]:
        cleaned = block.strip()
        if cleaned:
            new_checks.append(cleaned)

    if not new_checks:
        return 0, "no new checks applicable"

    needs_import = False
    if "import pytest" not in existing_code:
        needs_import = True

    addition = SEPARATOR
    if needs_import:
        addition += "import pytest\n\n"
    addition += "\n\n".join(new_checks) + "\n"

    added_count = addition.count("def test_")

    if not dry_run:
        with open(verifier, "a") as f:
            f.write(addition)

    return added_count, f"+{added_count} checks"


def main():
    parser = argparse.ArgumentParser(description="Enhance task verifiers")
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    args = parser.parse_args()

    total_added = 0
    enhanced = 0
    skipped = 0

    for domain_dir in sorted(TASKS_ROOT.iterdir()):
        if not domain_dir.is_dir() or domain_dir.name.startswith("."):
            continue
        for task_dir in sorted(domain_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            count, summary = enhance_verifier(task_dir, dry_run=not args.apply)
            task_id = task_dir.name
            if count > 0:
                print(f"  {task_id:45s} {summary}")
                total_added += count
                enhanced += 1
            else:
                skipped += 1

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] Enhanced {enhanced} tasks, skipped {skipped}, added {total_added} total checks")


if __name__ == "__main__":
    main()
