from money import parse_amount

assert parse_amount("$1,234.50") == 123450
assert parse_amount("-12.00") == -1200
assert parse_amount("12") == 1200
assert parse_amount("$5.25") == 525
assert parse_amount("($2.50)") == -250
