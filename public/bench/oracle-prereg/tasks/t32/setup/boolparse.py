def parse_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(int(v))
    if isinstance(v, str):
        s = v.strip().lower()
        mapping = {"yes": True, "no": False, "true": True, "false": False,
                   "on": True, "off": False, "y": True, "n": False,
                   "t": True, "f": False, "1": True, "0": False}
        if s in mapping:
            return mapping[s]
        raise ValueError("invalid bool representation")
    raise ValueError("invalid bool representation")

