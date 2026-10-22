You are given a module `roman.py` that converts between integers and Roman numerals. Implement `to_roman(n)` for the range 1 through 3999 using standard subtractive notation (IV, IX, XL, XC, CD, CM), and `from_roman(s)` which parses a Roman numeral back to an integer. `from_roman` accepts uppercase or lowercase letters, but it must raise `ValueError` for anything that is not a correctly formed, canonical Roman numeral, so forms such as `IIII`, `VX` and `IC` must be rejected, as must strings that are not Roman numerals at all. Values outside 1..3999 raise `ValueError` in `to_roman`.

For example, `to_roman(1994)` returns `"MCMXCIV"` and `from_roman("XIV")` returns `14`.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
