def stem(word):
    if len(word) < 2:
        return word
    for suffix in ("ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            return word[:-len(suffix)]
    # TODO: strip a trailing "s" the same way
    return word
