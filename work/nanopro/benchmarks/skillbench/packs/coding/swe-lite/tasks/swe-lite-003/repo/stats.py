from typing import List


def mean(values: List[float]) -> float:
    if not values:
        raise ValueError("values must not be empty")
    # BUG: divides by len(values) - 1 instead of len(values)
    return sum(values) / (len(values) - 1)
