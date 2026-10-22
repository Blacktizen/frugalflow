import re
import unicodedata


def slugify(text, max_len=50):
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if len(s) > max_len:
        cut = s.rfind("-", 0, max_len + 1)
        if cut != -1:
            s = s[:cut]
        else:
            s = s[:max_len]
        s = s.rstrip("-")
    return s
