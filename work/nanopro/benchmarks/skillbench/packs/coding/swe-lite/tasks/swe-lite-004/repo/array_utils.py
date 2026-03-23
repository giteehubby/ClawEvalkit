from typing import List, TypeVar

T = TypeVar('T')


def get_last_n(items: List[T], n: int) -> List[T]:
    """Return the last n items from the list."""
    if n <= 0:
        return []
    # BUG: off-by-one error, should be -n not -(n-1)
    return items[-(n - 1):]


def get_first_n(items: List[T], n: int) -> List[T]:
    """Return the first n items from the list."""
    if n <= 0:
        return []
    return items[:n]
