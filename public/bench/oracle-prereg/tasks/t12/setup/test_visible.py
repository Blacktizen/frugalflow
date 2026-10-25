import sys
try:
    from basen import to_base
    assert to_base(10, 2) == "1010"
    assert to_base(255, 16) == "ff"
    assert to_base(-42, 8) == "-52"
    assert to_base(0, 2) == "0"
    print("OK")
    sys.exit(0)
except AssertionError:
    print("FAIL")
    sys.exit(1)

