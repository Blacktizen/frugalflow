def capitalize_words(text):
    parts = text.split(" ")
    for i in range(len(parts)):
        if parts[i]:
            parts[i] = parts[i][0].upper() + parts[i][1:].lower()
    return " ".join(parts)


def chunk(text, size):
    if size <= 0:
        raise ValueError("size must be positive")
    return [text[i:i + size] for i in range(0, len(text), size)]


def count_vowels(text):
    return sum(1 for ch in text.lower() if ch in "aeiou")
