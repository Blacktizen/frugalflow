import re


def is_valid_identifier(name):
    return bool(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name))
