def is_valid_age(age: int) -> bool:
    """Check if age is valid (0 to 150 inclusive)."""
    # BUG: should use <= 150, not < 150
    return age >= 0 and age < 150


def is_valid_email(email: str) -> bool:
    """Basic email validation."""
    return "@" in email and "." in email
