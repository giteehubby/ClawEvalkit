def process_items(items):
    result = []
    i = 0
    while i < len(items):
        result.append(items[i].upper())
        # Bug: missing i += 1
    return result
