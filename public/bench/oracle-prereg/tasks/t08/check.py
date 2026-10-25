import sys
import traceback

TASK = "deepget"

def run():
    try:
        from deepget import deep_get
    except Exception:
        print("FAIL " + TASK + " | could not import module: " + traceback.format_exc()[:600])
        sys.exit(1)

    cases = [
        # (label, obj, path, default, expected)
        ("dict_basic", {"a": 1}, "a", None, 1),
        ("dict_nested", {"a": {"b": 2}}, "a.b", None, 2),
        ("list_index", {"a": [10, 20, 30]}, "a[1]", None, 20),
        ("list_of_dict", {"a": [{"c": 1}, {"c": 2}]}, "a[1].c", None, 2),
        ("neg_index", {"a": [10, 20, 30]}, "a[-1]", None, 30),
        ("neg_index2", {"a": [10, 20, 30]}, "a[-2]", None, 20),
        ("oob_pos", {"a": [1, 2]}, "a[5]", None, None),
        ("oob_neg", {"a": [1, 2]}, "a[-3]", "X", "X"),
        ("missing_key", {"a": 1}, "b", None, None),
        ("missing_key_default", {"a": 1}, "b", "D", "D"),
        ("wrong_type_scalar", {"a": 42}, "a.b", "T", "T"),
        ("wrong_type_str_index", {"a": "hello"}, "a[0]", "T", "T"),
        ("wrong_type_dict_on_list", {"a": [1, 2]}, "a.b", "T", "T"),
        ("empty_path_returns_obj", {"a": 1}, "", None, {"a": 1}),
        ("empty_path_with_default", {"a": 1}, "", "D", {"a": 1}),
        ("empty_path_list", [1, 2, 3], "", None, [1, 2, 3]),
        ("none_value_returned", {"a": None}, "a", None, None),
        ("none_value_not_replaced", {"a": None}, "a", "Z", None),
        ("none_nested", {"a": {"b": None}}, "a.b", "Q", None),
        ("deep_path", {"x": {"y": {"z": 7}}}, "x.y.z", None, 7),
    ]

    discrepancies = []
    for i, (label, obj, path, default, expected) in enumerate(cases):
        try:
            got = deep_get(obj, path, default)
            if got != expected or type(got) != type(expected):
                discrepancies.append((label, repr(expected), repr(got)))
                if len(discrepancies) >= 3:
                    break
        except Exception as e:
            discrepancies.append((label, repr(expected), "EXC:" + repr(e)))
            if len(discrepancies) >= 3:
                break

    if discrepancies:
        parts = []
        for d in discrepancies[:3]:
            parts.append("case=" + d[0] + " expected=" + d[1] + " obtained=" + d[2])
        msg = " ".join(parts)
        print("FAIL " + TASK + " | " + msg[:600])
        sys.exit(1)

    print("PASS")
    sys.exit(0)

run()
