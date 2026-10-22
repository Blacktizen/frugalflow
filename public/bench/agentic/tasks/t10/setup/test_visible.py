from csvline import split_line

assert split_line("a,b,c") == ["a", "b", "c"]
assert split_line("one") == ["one"]
assert split_line("1,2,3,4") == ["1", "2", "3", "4"]
print("visible tests passed")
