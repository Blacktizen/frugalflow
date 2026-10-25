from wrap import wrap_text

assert wrap_text("hello world", 11) == ["hello world"]
assert wrap_text("hello world", 5) == ["hello", "world"]
assert wrap_text("hello\nworld", 10) == ["hello", "world"]
assert wrap_text("hello", 5) == ["hello"]

print("OK")

