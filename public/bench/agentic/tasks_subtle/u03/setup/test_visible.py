from wrap import wrap

assert wrap("hello world", 11) == ["hello world"]
assert wrap("hello world", 10) == ["hello", "world"]
assert wrap("the quick brown fox", 10) == ["the quick", "brown fox"]
assert wrap("hi there friend", 6) == ["hi", "there", "friend"]
