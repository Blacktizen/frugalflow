def _check_groups(s, sep):
    groups = s.split(sep)
    if any(g == "" for g in groups):
        raise ValueError("bad grouping")
    if not groups[0].isdigit() or len(groups[0]) > 3:
        raise ValueError("bad grouping")
    for g in groups[1:]:
        if not g.isdigit() or len(g) != 3:
            raise ValueError("bad grouping")


def parse_amount(text):
    s = text.strip()
    if not s:
        raise ValueError("empty amount")

    negative = False
    if s[0] == "(":
        if not s.endswith(")"):
            raise ValueError("unbalanced parentheses")
        s = s[1:-1].strip()
        negative = True
    elif s[0] == "-":
        s = s[1:].strip()
        negative = True
    elif s[0] == "+":
        s = s[1:].strip()

    for sym in ("$", "€", "£", "¥"):
        if s.startswith(sym):
            s = s[len(sym):].strip()
            break
    for suf in ("EUR", "USD", "GBP"):
        if s.endswith(suf):
            s = s[:-len(suf)].rstrip()
            break

    if not s:
        raise ValueError("no number")
    if not all(c.isdigit() or c in ".," for c in s):
        raise ValueError("invalid characters")

    dot = s.count(".")
    comma = s.count(",")
    thou = None
    if dot == 0 and comma == 0:
        if not s.isdigit():
            raise ValueError("not an integer")
        int_part, frac = s, "00"
    elif dot > 0 and comma > 0:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thou = "," if dec == "." else "."
        int_part, _, frac = s.rpartition(dec)
        if thou in int_part:
            _check_groups(int_part, thou)
        if int_part == "":
            int_part = "0"
        if frac == "" or not frac.isdigit():
            raise ValueError("bad fraction")
    else:
        sep = "." if dot > 0 else ","
        last = s.rfind(sep)
        tail = s[last + 1:]
        if len(tail) in (1, 2):
            int_part, _, frac = s.rpartition(sep)
            if int_part == "":
                int_part = "0"
            if not frac.isdigit():
                raise ValueError("bad fraction")
        else:
            if tail == "" or len(tail) != 3:
                raise ValueError("bad grouping")
            int_part = s
            thou = sep
            _check_groups(int_part, sep)
            frac = "00"

    if thou is not None:
        int_part = int_part.replace(thou, "")
    if int_part == "" or not int_part.isdigit():
        raise ValueError("bad integer part")
    frac = (frac + "00")[:2]
    cents = int(int_part) * 100 + int(frac)
    return -cents if negative else cents
