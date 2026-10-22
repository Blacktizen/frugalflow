You are given a module `invoice.py` with a function `total(lines)` that takes a list of lines and returns the invoice total as an integer number of cents. Each line is a tuple `(unit_price, quantity, tax_percent)` where `unit_price` is a decimal string, `quantity` is an integer, and `tax_percent` is an integer percentage. For each line, multiply the unit price by the quantity, add the tax, and round that line's total to whole cents with ties rounded away from zero, then add the rounded line totals together. Use exact decimal arithmetic, not binary floating point, so that values like 0.105 round correctly.

For example, `total([("10.00", 1, 0)])` returns `1000`.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
