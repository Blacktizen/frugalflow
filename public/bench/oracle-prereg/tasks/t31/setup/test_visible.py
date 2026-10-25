import sys
sys.path.insert(0, ".")
from paths import normalize_path

assert normalize_path("/foo/bar") == "/foo/bar"
assert normalize_path("/foo/./bar") == "/foo/bar"
assert normalize_path("/foo/../bar") == "/bar"
assert normalize_path("/") == "/"

print("OK")
sys.exit(0)

