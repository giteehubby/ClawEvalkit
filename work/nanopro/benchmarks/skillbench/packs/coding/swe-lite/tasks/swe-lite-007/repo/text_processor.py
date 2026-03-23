import re


def remove_extra_spaces(text: str) -> str:
    """Remove extra spaces, collapsing multiple spaces into one."""
    # BUG: strip() only removes leading/trailing, doesn't collapse internal spaces
    return text.strip()


def normalize_whitespace(text: str) -> str:
    """Normalize all whitespace to single spaces."""
    return re.sub(r'\s+', ' ', text).strip()
