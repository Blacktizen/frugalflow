def parse_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        if v == 1:
            return True
        if v == 0:
            return False
        raise ValueError("invalid bool representation")
    if isinstance(v, float):
        raise ValueError("invalid bool representation")
    if isinstance(v, str):
        s = v.strip().lower()
        mapping = {"yes": True, "no": False, "true": True, "false": False,
                   "on": True, "off": False, "y": True, "n": False,
                   "t": True, "f": False, "1": True, "0": False}
        if s in mapping:
            return mapping[s]
        raise ValueError("invalid bool representation")
    raise ValueError("invalid bool representation")

