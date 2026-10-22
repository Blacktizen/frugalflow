# Task: inventory value

The file `stock.csv` has a header row `sku,qty,unit_price,updated` followed by data rows. A sku can appear on several rows; the current state of a sku is the row with the latest `updated` timestamp, and the rows are not ordered by time. A row whose `qty` is negative is a return and contributes 0 to the value.

Write `value.json` with `total` equal to the sum over all skus of `qty * unit_price` for the current state, rounded to 2 decimal places.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
