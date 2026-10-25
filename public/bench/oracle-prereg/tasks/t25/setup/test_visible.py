import sys
sys.path.insert(0, ".")
from bucket import TokenBucket

b = TokenBucket(5, 1.0)
assert b.allow(0.0) is True
assert b.allow(1.0) is True
assert b.allow(2.0) is True
assert b.allow(3.0) is True
print("OK")

