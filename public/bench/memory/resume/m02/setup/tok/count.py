def frequencies(tokens):
    result = {}
    for t in tokens:
        result[t] = result.get(t, 0) + 1
    return result
