from durations import parse_duration

assert parse_duration("90s") == 90
assert parse_duration("2d") == 172800
assert parse_duration("1d2h3m4s") == 93784
assert parse_duration("0s") == 0
print("visible tests passed")
