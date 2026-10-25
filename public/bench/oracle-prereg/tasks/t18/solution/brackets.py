def balanced(s):
    stack = []
    in_single = False
    in_double = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\':
            i += 2
            continue
        if in_single:
            if c == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if c == '"':
                in_double = False
            i += 1
            continue
        if c == "'":
            in_single = True
        elif c == '"':
            in_double = True
        elif c in '([{':
            stack.append(c)
        elif c in ')]}':
            if not stack:
                return False
            open_c = stack.pop()
            if open_c == '(' and c != ')':
                return False
            if open_c == '[' and c != ']':
                return False
            if open_c == '{' and c != '}':
                return False
        i += 1
    if in_single or in_double:
        return False
    return len(stack) == 0

