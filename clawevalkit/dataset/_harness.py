"""Shared harness config utilities for building exec scripts."""

import dataclasses
from enum import Enum

# Maps config key suffix → harness module path
HARNESS_MODULE_MAP = {
    "memory_config": "harness.agent.memory",
    "structured_memory_config": "harness.agent.memory_structured",
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


def _collect_nested_dataclasses(obj, collected=None, module_path=None):
    """Collect all nested dataclass types from an object, tracking their source module."""
    if collected is None:
        collected = {}
    if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
        return collected
    cls_name = type(obj).__name__
    if cls_name not in collected:
        collected[cls_name] = module_path
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            _collect_nested_dataclasses(value, collected, module_path)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if dataclasses.is_dataclass(item) and not isinstance(item, type):
                    _collect_nested_dataclasses(item, collected, module_path)
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
    all_sub_configs = {}  # class_name -> module_path
    all_enum_imports = {}  # module_path -> set of enum class names

    # 如果包含 collab_config，额外导入 CollabEvent（用于 _record_handoff_event）
    if "collab_config" in harness_config:
        import_lines.append("from harness.agent.collaboration.event import CollabEvent")

    for key, val in harness_config.items():
        cls_name = type(val).__name__
        # Use explicit module map for collab_config special case
        module_path = HARNESS_MODULE_MAP.get(key, f"harness.agent.{key.replace('_config', '')}")
        import_lines.append(f"from {module_path} import {cls_name}")

        # Collect all nested dataclass types for this config
        nested_classes = _collect_nested_dataclasses(val, module_path=module_path)
        for nc, nc_module in nested_classes.items():
            if nc != cls_name:
                all_sub_configs[nc] = nc_module or module_path

        # Collect enum types used in this config
        enum_types = _collect_enum_types(val, module_path)
        for enum_name, enum_module in enum_types:
            mod = enum_module or module_path
            all_enum_imports.setdefault(mod, set()).add(enum_name)

        # Serialize the full config including nested dataclasses
        config_repr = _dataclass_to_repr(val)
        kwarg_lines.append(f"    {key}={config_repr},")

    # Add sub-config imports grouped by module
    sub_by_module = {}
    for nc, nc_module in all_sub_configs.items():
        sub_by_module.setdefault(nc_module, []).append(nc)
    # Merge sub-config imports into existing import lines for the same module
    for mod, classes in sub_by_module.items():
        existing = next((l for l in import_lines if l.startswith(f"from {mod} import ")), None)
        if existing:
            existing_classes = {c.strip() for c in existing.split("import ", 1)[1].split(",")}
            existing_classes.update(classes)
            idx = import_lines.index(existing)
            import_lines[idx] = f"from {mod} import {', '.join(sorted(existing_classes))}"
        else:
            import_lines.insert(0, f"from {mod} import {', '.join(sorted(classes))}")

    # Add enum class imports
    for mod, enum_names in all_enum_imports.items():
        import_lines.append(f"from {mod} import {', '.join(sorted(enum_names))}")

    harness_imports = "\n".join(import_lines) + "\n"
    harness_kwargs_str = "\n" + "\n".join(kwarg_lines)
    return harness_imports, harness_kwargs_str
