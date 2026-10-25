def flatten(obj, sep="."):
    result = {}

    def _flatten(current, path):
        if isinstance(current, dict):
            for k, v in current.items():
                new_path = str(k) if not path else path + sep + str(k)
                if isinstance(v, dict) or isinstance(v, list):
                    _flatten(v, new_path)
                else:
                    result[new_path] = v
        elif isinstance(current, list):
            for i, v in enumerate(current):
                new_path = str(i) if not path else path + sep + str(i)
                if isinstance(v, dict) or isinstance(v, list):
                    _flatten(v, new_path)
                else:
                    result[new_path] = v

    if not isinstance(obj, (dict, list)):
        pass
    _flatten(obj, "")
    return result

