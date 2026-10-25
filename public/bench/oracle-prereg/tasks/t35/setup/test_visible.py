import sys
from pager import paginate

try:
    r = paginate(10, 1, 5)
    assert r == {"page": 1, "pages": 2, "offset": 0, "limit": 5, "has_prev": False, "has_next": True}

    r = paginate(10, 2, 5)
    assert r == {"page": 2, "pages": 2, "offset": 5, "limit": 5, "has_prev": True, "has_next": False}

    r = paginate(6, 1, 3)
    assert r == {"page": 1, "pages": 2, "offset": 0, "limit": 3, "has_prev": False, "has_next": True}

    print("OK")
    sys.exit(0)
except AssertionError:
    sys.exit(1)

