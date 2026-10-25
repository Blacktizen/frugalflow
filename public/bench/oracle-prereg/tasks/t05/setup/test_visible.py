import sys
from semver import compare

ok = True

r = compare("1.0.0", "1.0.1")
if r != -1: ok = False; print("FAIL 1")

r = compare("1.0.0", "1.0.0")
if r != 0: ok = False; print("FAIL 2")

r = compare("1.0.0-alpha", "1.0.0")
if r != -1: ok = False; print("FAIL 3")

r = compare("1.0.0+build", "1.0.0+other")
if r != 0: ok = False; print("FAIL 4")

if ok:
    print("OK")
    sys.exit(0)
else:
    sys.exit(1)

