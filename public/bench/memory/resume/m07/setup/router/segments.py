from router import normalize

def segments(path):
    norm = normalize.normalize(path)
    if norm == "/":
        return []
    return norm[1:].split("/")
