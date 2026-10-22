import os
import subprocess
import sys

BUCKETS = [2000, 5000, 10000, 20000, 50000]
MINIMUM = 3


def bucket(chars):
    for i in range(len(BUCKETS)):
        if chars < BUCKETS[i]:
            return i
    return len(BUCKETS)


def number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value >= 0
    return False


def median(values):
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def estimate(records, model, chars):
    b = bucket(chars)
    durations = []
    for r in records:
        if not isinstance(r, dict):
            continue
        if r.get("status") != "success":
            continue
        if r.get("model_asked") != model:
            continue
        if not number(r.get("seconds")):
            continue
        if not number(r.get("chars")):
            continue
        if bucket(r.get("chars")) != b:
            continue
        durations.append(r["seconds"])
    if len(durations) < MINIMUM:
        return None
    return (round(median(durations), 1), len(durations))


def describe(est):
    if est is None:
        return "ETA: unknown, fewer than 3 past deliveries of this model at this size"
    return "ETA: about " + str(est[0]) + " s, median of " + str(est[1]) + " past deliveries of this model at this size"


def R(seconds, chars=3000, model="m1", status="success"):
    return {"status": status, "model_asked": model, "seconds": seconds, "chars": chars}


LOG = [R(10), R(30), R(20), R(99, chars=30000), R(5, model="m2"), R(7, status="failure"), R(True), R("12"), R(None), "junk", 5]

NOTICE = (
    "NAME      eta_rules.py - estimates how long a delegation will take: the median measured duration of past successful deliveries of the same model for a brief of the same size band.\n"
    "READS     nothing: pure module; the caller passes the log records, the model name and the brief size in characters.\n"
    "WRITES    nothing: estimate() returns (seconds, count), or None under 3 comparable records; describe() the line to print.\n"
    "EXAMPLE   python3 eta_rules.py --notice\n"
    "PITFALLS  2026-09-26 the log carried no duration, so no delay could be estimated; each record now carries its measured seconds, and nothing is guessed below 3 records.\n"
)


def _autotest():
    all_pass = True

    # Test 1
    e1 = (bucket(0) == 0 and bucket(1999) == 0 and bucket(2000) == 1
          and bucket(49999) == 4 and bucket(50000) == 5
          and median([3, 1, 2]) == 2 and median([4, 1, 3, 2]) == 2.5
          and number(True) is False and number(-1) is False
          and number(0) is True and number(2.5) is True and number("3") is False)
    if e1:
        print("PASS 1: bucket/median/number all correct")
    else:
        got = (bucket(0), bucket(1999), bucket(2000), bucket(49999), bucket(50000),
               median([3, 1, 2]), median([4, 1, 3, 2]),
               number(True), number(-1), number(0), number(2.5), number("3"))
        print(f"FAIL 1: expected=((0,0,1,4,5,2,2.5,False,False,True,True,False)) got={got!r}")
        all_pass = False

    # Test 2
    a = estimate(LOG, "m1", 4000)
    a0 = a[0] if a is not None else None
    b = estimate(LOG + [R(40)], "m1", 2500)
    e2 = (a == (20, 3) and a0 == 20.0 and b == (25.0, 4))
    if e2:
        print("PASS 2: estimate returns correct tuples")
    else:
        print(f"FAIL 2: expected=((20,3),20.0,(25.0,4)) got=({a!r},{a0!r},{b!r})")
        all_pass = False

    # Test 3
    c1 = estimate(LOG, "m1", 30000)
    c2 = estimate(LOG, "m2", 3000)
    c3 = estimate(LOG, "m1", 100)
    c4 = estimate([], "m1", 3000)
    c5 = estimate([R(10), R(11)], "m1", 3000)
    e3 = (c1 is None and c2 is None and c3 is None and c4 is None and c5 is None)
    if e3:
        print("PASS 3: fewer than 3 comparable -> None")
    else:
        print(f"FAIL 3: expected=(None,None,None,None,None) got=({c1!r},{c2!r},{c3!r},{c4!r},{c5!r})")
        all_pass = False

    # Test 4
    d1 = describe(None)
    d2 = describe((20.0, 3))
    d3 = describe(estimate(LOG + [R(40)], "m1", 2500))
    exp1 = "ETA: unknown, fewer than 3 past deliveries of this model at this size"
    exp2 = "ETA: about 20.0 s, median of 3 past deliveries of this model at this size"
    exp3 = "ETA: about 25.0 s, median of 4 past deliveries of this model at this size"
    e4 = (d1 == exp1 and d2 == exp2 and d3 == exp3)
    if e4:
        print("PASS 4: describe returns correct strings")
    else:
        print(f"FAIL 4: expected=({exp1!r},{exp2!r},{exp3!r}) got=({d1!r},{d2!r},{d3!r})")
        all_pass = False

    # Test 5
    exe = sys.executable
    path = os.path.abspath(__file__)
    p1 = subprocess.run([exe, path, "--notice"], capture_output=True, text=True)
    p2 = subprocess.run([exe, path], capture_output=True, text=True)
    e5 = (p1.returncode == 0 and p1.stdout.startswith("NAME      eta_rules.py")
          and p2.returncode == 2 and p2.stdout == "usage: eta_rules.py --notice | --autotest\n")
    if e5:
        print("PASS 5: subprocess --notice code=0 and no-args code=2 correct")
    else:
        print(f"FAIL 5: expected=(code=0,startswith='NAME      eta_rules.py'),(code=2,stdout='usage...') got=(code={p1.returncode},stdout[:30]={p1.stdout[:30]!r}),(code={p2.returncode},stdout={p2.stdout!r})")
        all_pass = False

    return 0 if all_pass else 1


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write("usage: eta_rules.py --notice | --autotest\n")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "eta_rules", sys.argv[1:])
