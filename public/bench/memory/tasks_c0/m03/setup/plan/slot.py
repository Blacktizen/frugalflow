def parse_time(text):
    if not isinstance(text, str):
        raise ValueError("time must be a string")
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError("time must be HH:MM")
    if len(parts[0]) != 2 or len(parts[1]) != 2:
        raise ValueError("time must be HH:MM")
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        raise ValueError("time must be HH:MM")
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise ValueError("time out of range")
    return h * 60 + m
