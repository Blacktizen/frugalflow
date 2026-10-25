import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

cases = [
    ("bool_true", lambda: (parse_bool(True),)),
    ("bool_false", lambda: (parse_bool(False),)),
    ("int_1", lambda: (parse_bool(1),)),
    ("int_0", lambda: (parse_bool(0),)),
    ("int_2_raises", lambda: (parse_bool(2),)),
    ("str_yes", lambda: (parse_bool("yes"),)),
    ("str_no", lambda: (parse_bool("no"),)),
    ("str_true_upper", lambda: (parse_bool("TRUE"),)),
    ("str_false_upper", lambda: (parse_bool("False"),)),
    ("str_on", lambda: (parse_bool("on"),)),
    ("str_off_upper", lambda: (parse_bool("OFF"),)),
    ("str_y", lambda: (parse_bool("y"),)),
    ("str_n", lambda: (parse_bool("n"),)),
    ("str_t", lambda: (parse_bool("t"),)),
    ("str_f", lambda: (parse_bool("f"),)),
    ("str_1", lambda: (parse_bool("1"),)),
    ("str_0", lambda: (parse_bool("0"),)),
    ("str_strip_case", lambda: (parse_bool("  YeS  "),)),
    ("str_maybe_raises", lambda: (parse_bool("maybe"),)),
    ("str_empty_raises", lambda: (parse_bool(""),)),
    ("none_raises", lambda: (parse_bool(None),)),
    ("float_1_raises", lambda: (parse_bool(1.0),)),
    ("list_raises", lambda: (parse_bool([1]),)),
]

expected_map = {
    "bool_true": (True,),
    "bool_false": (False,),
    "int_1": (True,),
    "int_0": (False,),
    "int_2_raises": ValueError,
    "str_yes": (True,),
    "str_no": (False,),
    "str_true_upper": (True,),
    "str_false_upper": (False,),
    "str_on": (True,),
    "str_off_upper": (False,),
    "str_y": (True,),
    "str_n": (False,),
    "str_t": (True,),
    "str_f": (False,),
    "str_1": (True,),
    "str_0": (False,),
    "str_strip_case": (True,),
    "str_maybe_raises": ValueError,
    "str_empty_raises": ValueError,
    "none_raises": ValueError,
    "float_1_raises": ValueError,
    "list_raises": ValueError,
}

try:
    from boolparse import parse_bool
except Exception:
    print("FAIL parse_bool | import error | | ")
    sys.exit(1)

discrepancies = []
for case_name, fn in cases:
    exp = expected_map[case_name]
    try:
        result = fn()
        if isinstance(exp, type) and issubclass(exp, Exception):
            discrepancies.append((case_name, "ValueError raised", str(result)))
        elif result != exp:
            discrepancies.append((case_name, str(exp), str(result)))
    except Exception as e:
        if isinstance(exp, type) and issubclass(exp, Exception):
            if not isinstance(e, exp):
                discrepancies.append((case_name, exp.__name__, type(e).__name__ + ": " + str(e)))
        else:
            discrepancies.append((case_name, str(exp), "raised " + str(e)))

if discrepancies:
    msg = "FAIL parse_bool | " + " | ".join(
        "{0}: expected={1} obtained={2}".format(d[0], d[1], d[2])
        for d in discrepancies[:3]
    )
    print(msg[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
