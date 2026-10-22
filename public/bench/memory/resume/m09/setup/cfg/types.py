def is_int(s):
    if not isinstance(s, str):
        return False
    try:
        int(s)
        return True
    except ValueError:
        return False

def is_float(s):
    if not isinstance(s, str):
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False

def is_bool(s):
    if not isinstance(s, str):
        return False
    return s.strip().lower() in ("true", "false", "yes", "no", "1", "0")
