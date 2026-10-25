import sys
import traceback

TASK_ID = "pager"

results = []

def check(label, func, expect_error=False):
    try:
        r = func()
        if expect_error:
            results.append((label, "expected ValueError", "no exception"))
            return
        if isinstance(r, dict):
            results.append((label, r, r))
        else:
            results.append((label, "dict", type(r).__name__))
    except ValueError:
        if expect_error:
            results.append((label, "ok", "ok"))
        else:
            results.append((label, "dict result", "ValueError raised"))
    except Exception as e:
        results.append((label, "dict result", "Exception: %s" % str(e)))

def compare(label, r, expected):
    if r is None:
        return
    for k in ("page", "pages", "offset", "limit", "has_prev", "has_next"):
        if k not in r:
            results.append((label, "key %s present" % k, "key missing"))
        elif r[k] != expected[k]:
            results.append((label, "%s=%s" % (k, expected[k]), "%s=%s" % (k, r[k])))

try:
    import pager as mod
except ImportError:
    print("FAIL %s: import error" % TASK_ID)
    sys.exit(1)

tests = []

# 1 basic first page
def t1():
    return mod.paginate(10, 1, 5)
tests.append(("t01_basic_first", t1, {"page":1,"pages":2,"offset":0,"limit":5,"has_prev":False,"has_next":True}, False))

# 2 last page shorter
def t2():
    return mod.paginate(7, 2, 5)
tests.append(("t02_last_shorter", t2, {"page":2,"pages":2,"offset":5,"limit":2,"has_prev":True,"has_next":False}, False))

# 3 total zero
def t3():
    return mod.paginate(0, 1, 5)
tests.append(("t03_total_zero", t3, {"page":1,"pages":1,"offset":0,"limit":0,"has_prev":False,"has_next":False}, False))

# 4 clamp page below 1
def t4():
    return mod.paginate(10, 0, 5)
tests.append(("t04_clamp_low", t4, {"page":1,"pages":2,"offset":0,"limit":5,"has_prev":False,"has_next":True}, False))

# 5 clamp page above pages
def t5():
    return mod.paginate(10, 3, 5)
tests.append(("t05_clamp_high", t5, {"page":2,"pages":2,"offset":5,"limit":5,"has_prev":True,"has_next":False}, False))

# 6 clamp negative page
def t6():
    return mod.paginate(10, -5, 5)
tests.append(("t06_clamp_neg", t6, {"page":1,"pages":2,"offset":0,"limit":5,"has_prev":False,"has_next":True}, False))

# 7 ValueError per_page 0
def t7():
    return mod.paginate(10, 1, 0)
tests.append(("t07_pp_zero", t7, None, True))

# 8 ValueError per_page negative
def t8():
    return mod.paginate(10, 1, -1)
tests.append(("t08_pp_neg", t8, None, True))

# 9 ValueError total negative
def t9():
    return mod.paginate(-1, 1, 5)
tests.append(("t09_total_neg", t9, None, True))

# 10 per_page 1
def t10():
    return mod.paginate(3, 2, 1)
tests.append(("t10_pp_one", t10, {"page":2,"pages":3,"offset":1,"limit":1,"has_prev":True,"has_next":True}, False))

# 11 exact full single page
def t11():
    return mod.paginate(5, 1, 5)
tests.append(("t11_full_single", t11, {"page":1,"pages":1,"offset":0,"limit":5,"has_prev":False,"has_next":False}, False))

# 12 total 1 large per_page
def t12():
    return mod.paginate(1, 1, 10)
tests.append(("t12_small_total", t12, {"page":1,"pages":1,"offset":0,"limit":1,"has_prev":False,"has_next":False}, False))

# 13 clamp when total zero and page high
def t13():
    return mod.paginate(0, 5, 5)
tests.append(("t13_zero_clamp", t13, {"page":1,"pages":1,"offset":0,"limit":0,"has_prev":False,"has_next":False}, False))

# 14 pages max(1,...) with total zero pp 1
def t14():
    return mod.paginate(0, 1, 1)
tests.append(("t14_zero_pp1", t14, {"page":1,"pages":1,"offset":0,"limit":0,"has_prev":False,"has_next":False}, False))

# 15 page at upper boundary has_next False
def t15():
    return mod.paginate(10, 2, 5)
tests.append(("t15_upper_bound", t15, {"page":2,"pages":2,"offset":5,"limit":5,"has_prev":True,"has_next":False}, False))

# 16 has_prev False after clamping to 1
def t16():
    return mod.paginate(10, 0, 3)
tests.append(("t16_clamp_hasprev", t16, {"page":1,"pages":4,"offset":0,"limit":3,"has_prev":False,"has_next":True}, False))

failures = []

for label, func, expected, expect_err in tests:
    try:
        r = func()
        if expect_err:
            failures.append((label, "expected ValueError", "returned dict"))
            continue
        for k in ("page", "pages", "offset", "limit", "has_prev", "has_next"):
            if k not in r:
                failures.append((label, "key %s in dict" % k, "missing"))
            elif r[k] != expected[k]:
                failures.append((label, "%s expected %s" % (k, expected[k]), "%s got %s" % (k, r[k])))
    except ValueError:
        if not expect_err:
            failures.append((label, "dict result", "ValueError raised"))
    except Exception as e:
        failures.append((label, "dict result", "Exception: %s" % str(e)))

if failures:
    parts = failures[:3]
    line = "FAIL %s:" % TASK_ID
    for f in parts:
        line += " | %s: expected=%s obtained=%s" % (f[0], f[1], f[2])
    print(line[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
