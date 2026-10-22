import re

def build(path, params):
    result = path
    for key, value in params.items():
        result = result.replace("{" + key + "}", str(value))
    leftover = re.search(r"\{[^{}]+\}", result)
    if leftover:
        raise ValueError("missing param: " + leftover.group(0)[1:-1])
    return result
