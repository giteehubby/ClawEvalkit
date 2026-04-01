def percentage(part: int, whole: int) -> float:
    """Calculate what percentage 'part' is of 'whole'."""
    if whole == 0:
        return 0.0
    # BUG: integer division truncates result, should use float division
    return (part // whole) * 100


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(value, max_val))
