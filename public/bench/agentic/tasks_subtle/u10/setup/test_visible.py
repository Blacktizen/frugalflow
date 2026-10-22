from invoice import total

assert total([("10.00", 1, 0)]) == 1000
assert total([("1.50", 2, 0)]) == 300
assert total([("1.00", 1, 20)]) == 120
assert total([("2.50", 4, 10)]) == 1100
