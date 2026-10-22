from semver import compare

assert compare("1.2.3", "1.10.0") == -1
assert compare("1.10.0", "1.2.3") == 1
assert compare("1.2.3", "1.2.3") == 0
assert compare("2.0.0", "1.9.9") == 1
