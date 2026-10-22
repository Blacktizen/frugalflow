from router import params as _params

def lookup(routes, path):
    for pattern, handler in routes:
        captured = _params.extract(pattern, path)
        if captured is not None:
            return (handler, captured)
    return None
