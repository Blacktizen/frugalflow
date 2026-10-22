def normalize(path):
    if not isinstance(path, str):
        raise ValueError("path must be a string")
    if path == "":
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    parts = [p for p in path.split("/") if p != ""]
    return "/" + "/".join(parts)
