import re


def _cols(s):
    return sum(4 if c == "\t" else 1 for c in s)


def wrap(text, width):
    out = []
    for para in text.split("\n"):
        para = para.rstrip(" \t")
        if para.strip(" \t") == "":
            out.append("")
            continue
        parts = re.split(r"([ \t]+)", para)
        line = ""
        col = 0
        gap = ""
        for part in parts:
            if part == "":
                continue
            if part[0] in " \t":
                gap = part
                continue
            word = part
            if _cols(word) > width:
                if line:
                    out.append(line)
                    line = ""
                    col = 0
                while _cols(word) > width:
                    out.append(word[:width])
                    word = word[width:]
                gap = ""
            if word == "":
                continue
            if not line:
                line = word
                col = _cols(word)
            elif col + _cols(gap) + _cols(word) <= width:
                line += gap + word
                col += _cols(gap) + _cols(word)
            else:
                out.append(line)
                line = word
                col = _cols(word)
            gap = ""
        if line:
            out.append(line)
    return out
