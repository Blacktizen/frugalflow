from bill import split_bill

assert split_bill(10, 3) == [4, 3, 3]
assert split_bill(6, 2) == [3, 3]
assert split_bill(0, 3) == [0, 0, 0]
assert split_bill(7, 1) == [7]
print("OK")

