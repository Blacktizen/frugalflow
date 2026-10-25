import sys
sys.path.insert(0, ".")

TASK = "batch_by_weight"

try:
    from batching import batch_by_weight
except Exception as e:
    print("FAIL " + TASK + " | import | expected module | obtained " + str(e)[:200])
    sys.exit(1)

discrepancies = []

def check(case, expected, obtained):
    if expected != obtained:
        discrepancies.append((case, repr(expected), repr(obtained)))

def check_raise(case):
    try:
        result = batch_by_weight(*case[1])
        discrepancies.append((case[0], "ValueError", "no exception, got " + repr(result)))
    except ValueError:
        pass
    except Exception as e:
        discrepancies.append((case[0], "ValueError", "wrong exception: " + repr(e)))

# 1 - basic greedy split
check("1-basic", [["A","B"],["C"]], batch_by_weight([("A",2),("B",3),("C",4)], 6))
# 2 - equality at boundary (sum == max_weight)
check("2-equality", [["A","B"]], batch_by_weight([("A",3),("B",2)], 5))
# 3 - heavy item in middle
check("3-heavy-mid", [["A"],["B"],["C"]], batch_by_weight([("A",3),("B",8),("C",2)], 5))
# 4 - heavy item first
check("4-heavy-first", [["B"],["A"]], batch_by_weight([("B",8),("A",3)], 5))
# 5 - weight 0 allowed together
check("5-zeros", [["A","B"]], batch_by_weight([("A",0),("B",0)], 5))
# 6 - weight 0 mixed with positive
check("6-zero-mixed", [["A","B","C"]], batch_by_weight([("A",3),("B",0),("C",2)], 5))
# 7 - negative weight raises
check_raise(("7-neg-weight", ([("A",-1)], 5)))
# 8 - max_weight == 0 raises
check_raise(("8-max0", ([("A",1)], 0)))
# 9 - max_weight < 0 raises
check_raise(("9-maxneg", ([("A",1)], -3)))
# 10 - empty items
check("10-empty", [], batch_by_weight([], 7))
# 11 - single item equals max_weight
check("11-exact-fit", [["A"]], batch_by_weight([("A",5)], 5))
# 12 - single heavy item
check("12-single-heavy", [["A"]], batch_by_weight([("A",6)], 5))
# 13 - all fit one batch
check("13-all-fit", [["A","B","C"]], batch_by_weight([("A",1),("B",1),("C",1)], 10))
# 14 - each item separate (sum exceeds after first)
check("14-separate", [["A"],["B"]], batch_by_weight([("A",5),("B",5)], 5))
# 15 - multiple heavy items consecutive
check("15-multi-heavy", [["A"],["B"]], batch_by_weight([("A",8),("B",9)], 5))
# 16 - order preserved with names
check("16-order", [["Z","A"],["B"]], batch_by_weight([("Z",2),("A",3),("B",4)], 6))

if discrepancies:
    lines = ["FAIL " + TASK]
    for d in discrepancies[:3]:
        lines.append("case=" + d[0] + " | expected=" + d[1][:150] + " | obtained=" + d[2][:150])
    msg = " || ".join(lines)
    print(msg[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
