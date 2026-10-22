from roman import to_roman, from_roman

assert to_roman(4) == "IV"
assert to_roman(9) == "IX"
assert to_roman(14) == "XIV"
assert to_roman(1994) == "MCMXCIV"
assert from_roman("MCMXCIV") == 1994
