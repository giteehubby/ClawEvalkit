"""Shared harness config utilities for building exec scripts."""

# Maps config key suffix → harness module path
HARNESS_MODULE_MAP = {
    "memory_config": "harness.agent.memory",
    "control_config": "harness.agent.control",
    "collab_config": "harness.agent.collaboration",
    "procedural_config": "harness.agent.procedure",
}


def build_harness_script_parts(harness_config: dict) -> tuple[str, str]:
    """Build harness import lines and constructor kwargs string for exec scripts.

    Returns (harness_imports, harness_kwargs_str).
    """
    if not harness_config:
        return "", ""
    import_lines = []
    kwarg_lines = []
    for key, val in harness_config.items():
        cls_name = type(val).__name__
        # Use explicit module map for collab_config special case
        module_path = HARNESS_MODULE_MAP.get(key, f"harness.agent.{key.replace('_config', '')}")
        import_lines.append(f"from {module_path} import {cls_name}")
        kwarg_lines.append(f"    {key}={cls_name}(enabled=True),")
    harness_imports = "\n".join(import_lines) + "\n"
    harness_kwargs_str = "\n" + "\n".join(kwarg_lines)
    return harness_imports, harness_kwargs_str
