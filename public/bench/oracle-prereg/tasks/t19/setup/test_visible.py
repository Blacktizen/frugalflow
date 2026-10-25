
import sys
sys.path.insert(0, '.')
from titles import title_case

assert title_case("hello world") == "Hello World", "basic"
assert title_case("the cat in the hat") == "The Cat in the Hat", "small words"
assert title_case("a day to remember") == "A Day to Remember", "first and middle small"

print("OK")
sys.exit(0)

