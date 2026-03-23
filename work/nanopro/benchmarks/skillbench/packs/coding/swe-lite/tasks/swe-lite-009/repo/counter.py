def count_vowels(text: str) -> int:
    """Count the number of vowels in the text."""
    vowels = "aeiouAEIOU"
    count = 0
    # BUG: range stops one character early (should be len(text), not len(text) - 1)
    for i in range(len(text) - 1):
        if text[i] in vowels:
            count += 1
    return count


def count_consonants(text: str) -> int:
    """Count the number of consonants in the text."""
    consonants = "bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ"
    return sum(1 for c in text if c in consonants)
