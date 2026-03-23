from typing import Optional


def get_display_name(first_name: str, last_name: str, nickname: Optional[str]) -> str:
    """Return user's display name, preferring nickname if available."""
    # BUG: doesn't check if nickname is None before using it
    if len(nickname) > 0:
        return nickname
    return f"{first_name} {last_name}"


def get_initials(first_name: str, last_name: str) -> str:
    """Return user's initials."""
    return f"{first_name[0]}{last_name[0]}".upper()
