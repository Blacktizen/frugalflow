def flatten(obj, sep="."):
    if not isinstance(obj, (dict, list)):
        raise ValueError("top-level value must be a dict or a list")

    result = {}

    def _flatten(current, path):
        if isinstance(current, dict):
            for k, v in current.items():
                new_path = str(k) if not path else path + sep + str(k)
                _process(v, new_path)
        elif isinstance(current, list):
            for i, v in enumerate(current):
                new_path = str(i) if not path else path + sep + str(i)
                _process(v, new_path)

    def _process(value, path):
        if isinstance(value, dict) and value:
            _flatten(value, path)
        elif isinstance(value, list) and value:
            _flatten(value, path)
        elif isinstance(value, dict) and not value:
            result[path] = value
        elif isinstance(value, list) and not value:
            result[path] = value
        else:
            result[path] = value

    _flatten(obj, "")
    return result

