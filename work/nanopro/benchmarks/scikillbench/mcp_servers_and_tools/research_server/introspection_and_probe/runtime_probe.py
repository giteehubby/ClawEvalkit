"""
Lightweight runtime probing helpers for debugging KeyError/AttributeError.

Usage examples:

# Probe a mapping for a key; on KeyError prints available keys
value = try_get_key(mapping, "target_key")

# Probe an object attribute; on AttributeError prints accessible attributes and suggestions
attr_value = try_get_attr(obj, "attribute_name")
"""

from __future__ import annotations

from typing import Any, List
import inspect
import difflib


def _iter_public_dir(obj: Any) -> list[str]:
    try:
        names = [n for n in dir(obj) if not n.startswith("_")]
        names.sort()
        return names
    except Exception:
        return []


def show_all_keys_or_attrs(obj: Any) -> None:
    """Print all accessible keys (for mappings) or all public attributes (for objects)."""
    try:
        if isinstance(obj, dict):
            try:
                keys = sorted(obj.keys())  # type: ignore[arg-type]
            except Exception:
                keys = list(obj.keys())  # type: ignore[arg-type]
            print("DICT_KEYS:", keys)
            print("TYPE:", type(obj).__name__)
            return

        # pydantic v2 style models
        if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
            try:
                keys = sorted(list(getattr(obj, "model_dump")().keys()))
            except Exception:
                keys = []
            print("MODEL_KEYS:", keys)
            print("TYPE:", type(obj).__name__)
            return

        # generic object
        names = _iter_public_dir(obj)
        print("ATTRS:", names)
        print("TYPE:", type(obj).__name__)
        print("HINT: Some attributes may themselves contain nested attributes; probe them individually if needed (e.g., obj.attr).")
    except Exception as e:  # pragma: no cover
        print("PROBE_FAIL:", e)

def try_get_key(mapping: Any, key: Any) -> Any:
    """Attempt mapping[key]. 

    On success: print a concise success note (or a None-value warning) and return the value.
    On KeyError: print available keys for the mapping and re-raise KeyError.
    """
    try:
        value = mapping[key]
        try:
            if value is None:
                print(f"[probe_key] Found key {key!r} but value is None; verify the intended key or upstream logic.")
            else:
                print(
                    f"[probe_key] OK: key {key!r} is present (type={type(value).__name__}). "
                    f"This may mean either the earlier KeyError was at a different site so you should probe the correct line and re-run, "
                    f"or you are now probing a different key than the one that caused the earlier KeyError and have successfully debugged the issue."
                )
        except Exception:
            pass
        return value
    except KeyError:
        print(f"KeyError: missing key -> {key!r}")
        show_all_keys_or_attrs(mapping)
        raise


def try_get_attr(obj: Any, name: str) -> Any:
    """Attempt to access an attribute.

    On success: print a concise success note (or a None-value warning) and return the value.
    On AttributeError: print accessible attributes and suggest similar names, then re-raise AttributeError.
    """
    try:
        value = getattr(obj, name)
        try:
            if value is None:
                print(f"[probe_attr] Found attribute {name!r} but value is None; verify the intended attribute or upstream logic.")
            else:
                print(
                    f"[probe_attr] OK: attribute {name!r} is present (type={type(value).__name__}). "
                    f"This may mean either the earlier AttributeError was at a different site so you should probe the correct line and re-run, "
                    f"or you are now probing a different attribute than the one that caused the earlier AttributeError and have successfully debugged the issue."
                )
        except Exception:
            pass
        return value
    except AttributeError:
        print(f"AttributeError: missing attribute -> {name!r}")
        show_all_keys_or_attrs(obj)
        # Additionally, suggest similar attribute names (best-effort, includes class properties)
        try:
            def _normalize(s: str) -> str:
                return s.replace("_", "").lower()

            def _similar(a: str, b: str) -> float:
                return difflib.SequenceMatcher(a=_normalize(a), b=_normalize(b)).ratio()

            candidates: List[str] = []
            # Instance-visible names
            try:
                candidates.extend([n for n in dir(obj) if not n.startswith("_")])
            except Exception:
                pass
            # Class-level properties/descriptors across MRO
            try:
                for base in inspect.getmro(type(obj)):
                    for n, desc in getattr(base, "__dict__", {}).items():
                        if n.startswith("_"):
                            continue
                        if isinstance(desc, property) or inspect.isdatadescriptor(desc) or inspect.ismethoddescriptor(desc):
                            candidates.append(n)
            except Exception:
                pass
            # Rank and print top suggestions
            uniq = sorted(set(candidates))
            ranked = sorted(uniq, key=lambda n: (_normalize(n) != _normalize(name), 0 if _normalize(n).startswith(_normalize(name)) else 1, -_similar(n, name), len(n)))
            top = ranked[:10]
            if top:
                print("SUGGEST_ATTRS (maybe related by name similarity):", top)
                print("HINT: Suggestions are based on string similarity; try them directly or probe nested attributes if needed.")
        except Exception:
            pass
        raise

