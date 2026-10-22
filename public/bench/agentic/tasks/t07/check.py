import copy
import sys

from cfg import merge


def run(label, base, override, expected):
    base_before = copy.deepcopy(base)
    override_before = copy.deepcopy(override)
    try:
        got = merge(base, override)
    except Exception as e:
        print("FAIL", label, "raised", type(e).__name__, str(e))
        sys.exit(1)
    if got != expected:
        print("FAIL", label, "got", got, "expected", expected)
        sys.exit(1)
    if base != base_before or override != override_before:
        print("FAIL", label, "inputs were mutated")
        sys.exit(1)


run("list replaced", {"l": [1, 2]}, {"l": [3, 4]}, {"l": [3, 4]})
run("deep merge", {"c": {"x": 1, "y": 2}}, {"c": {"y": 9, "z": 10}}, {"c": {"x": 1, "y": 9, "z": 10}})
run("none deletes top key", {"a": 1, "b": 2}, {"a": None}, {"b": 2})
run("none deletes nested key", {"c": {"x": 1, "y": 2}}, {"c": {"x": None}}, {"c": {"y": 2}})
run("none deletes missing key", {"a": 1}, {"zz": None}, {"a": 1})
run("nested no mutation", {"a": 1, "c": {"x": 1}}, {"c": {"y": 2}}, {"a": 1, "c": {"x": 1, "y": 2}})
run("override non-dict replaces", {"a": {"x": 1}}, {"a": 5}, {"a": 5})

print("PASS")
