def normalize_path(p):
    if p == "":
        return "."

    absolute = p.startswith("/")
    parts = p.split("/")

    stack = []
    leading_parent = 0

    for part in parts:
        if part == "" or part == ".":
            continue
        if part == "..":
            if absolute:
                if stack:
                    stack.pop()
            else:
                if stack:
                    stack.pop()
                else:
                    leading_parent += 1
        else:
            stack.append(part)

    if absolute:
        if not stack:
            return "/"
        return "/" + "/".join(stack)
    else:
        out = [".."] * leading_parent + stack
        if not out:
            return "."
        return "/".join(out)

