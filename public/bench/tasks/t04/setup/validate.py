import re


def is_valid_identifier(name):
    return bool(re.match(r"[a-zA-Z_][a-zA-Z0-9_]*", name))
