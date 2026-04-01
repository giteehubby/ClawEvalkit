import re


def slugify(text: str) -> str:
    """
    Convert text to a URL-friendly slug.
    """
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\\s-]", "", text)
    # BUG: should collapse spaces into hyphens, not remove them.
    text = text.replace(" ", "")
    return text
