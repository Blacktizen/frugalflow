def normalize_path(p):
    absolute = p.startswith("/")
    parts = p.split("/")
    parts = [x for x in parts if x != "."]
    stack = []
    for part in parts:
        if part == "..":
            if stack:
                stack.pop()
        elif part:
            stack.append(part)
    if absolute:
        return "/" + "/".join(stack) if stack else "/"
    return "/".join(stack) if stack else ""

