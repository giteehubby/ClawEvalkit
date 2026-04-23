"""Shared harness config utilities for building exec scripts."""

import dataclasses
from enum import Enum

# Maps config key suffix → harness module path
HARNESS_MODULE_MAP = {
    "memory_config": "harness.agent.memory",
    "control_config": "harness.agent.control",
    "collab_config": "harness.agent.collaboration",
    "procedural_config": "harness.agent.procedure",
}

# Sub-config classes that need to be imported from control module
CONTROL_SUB_CONFIGS = [
    "PlanFirstConfig",
    "ReplanConfig",
    "RetryConfig",
    "ReflectionConfig",
]


def _collect_nested_dataclasses(obj, collected=None):
    """Collect all nested dataclass types from an object."""
    if collected is None:
        collected = set()
    if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
        return collected
    cls_name = type(obj).__name__
    collected.add(cls_name)
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            _collect_nested_dataclasses(value, collected)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if dataclasses.is_dataclass(item) and not isinstance(item, type):
                    _collect_nested_dataclasses(item, collected)
    return collected


def _dataclass_to_repr(obj) -> str:
    """Serialize a dataclass instance to a repr string with all its fields."""
    if not dataclasses.is_dataclass(obj):
        return repr(obj)

    cls_name = type(obj).__name__
    fields = []
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        if dataclasses.is_dataclass(value):
            # Recursively serialize nested dataclasses
            fields.append(f"{field.name}={_dataclass_to_repr(value)}")
        elif isinstance(value, str):
            fields.append(f"{field.name}='{value}'")
        elif isinstance(value, (list, tuple)):
            # Handle list/tuple fields
            items = []
            for item in value:
                if dataclasses.is_dataclass(item):
                    items.append(_dataclass_to_repr(item))
                else:
                    items.append(repr(item))
            fields.append(f"{field.name}=[{', '.join(items)}]")
        elif isinstance(value, Enum):
            fields.append(f"{field.name}={type(value).__name__}.{value.name}")
        else:
            fields.append(f"{field.name}={repr(value)}")
    return f"{cls_name}({', '.join(fields)})"


def _collect_enum_types(obj, module_path: str, collected=None):
    """Collect all Enum types used in dataclass fields."""
    if collected is None:
        collected = set()
    if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
        return collected
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        if isinstance(value, Enum):
            collected.add((type(value).__name__, module_path))
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            _collect_enum_types(value, module_path, collected)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if dataclasses.is_dataclass(item) and not isinstance(item, type):
                    _collect_enum_types(item, module_path, collected)
    return collected


def build_harness_script_parts(harness_config: dict) -> tuple[str, str]:
    """Build harness import lines and constructor kwargs string for exec scripts.

    Returns (harness_imports, harness_kwargs_str).
    """
    if not harness_config:
        return "", ""
    import_lines = []
    kwarg_lines = []
    all_sub_configs = set()
    all_enum_imports = {}  # module_path -> set of enum class names

    for key, val in harness_config.items():
        cls_name = type(val).__name__
        # Use explicit module map for collab_config special case
        module_path = HARNESS_MODULE_MAP.get(key, f"harness.agent.{key.replace('_config', '')}")
        import_lines.append(f"from {module_path} import {cls_name}")

        # Collect all nested dataclass types for this config
        nested_classes = _collect_nested_dataclasses(val)
        for nc in nested_classes:
            if nc != cls_name:
                all_sub_configs.add(nc)

        # Collect enum types used in this config
        enum_types = _collect_enum_types(val, module_path)
        for enum_name, enum_module in enum_types:
            mod = enum_module or module_path
            all_enum_imports.setdefault(mod, set()).add(enum_name)

        # Serialize the full config including nested dataclasses
        config_repr = _dataclass_to_repr(val)
        kwarg_lines.append(f"    {key}={config_repr},")

    # Add sub-config imports for control module
    if all_sub_configs:
        control_imports = [f"from harness.agent.control import {', '.join(sorted(all_sub_configs))}"]
        import_lines = control_imports + import_lines

    # Add enum class imports
    for mod, enum_names in all_enum_imports.items():
        import_lines.append(f"from {mod} import {', '.join(sorted(enum_names))}")

    harness_imports = "\n".join(import_lines) + "\n"
    harness_kwargs_str = "\n" + "\n".join(kwarg_lines)
    return harness_imports, harness_kwargs_str
