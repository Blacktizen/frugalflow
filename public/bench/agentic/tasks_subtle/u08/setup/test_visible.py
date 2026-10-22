from slug import slugify

assert slugify("Hello World") == "hello-world"
assert slugify("Hello, World!") == "hello-world"
assert slugify("  Spaced  Title  ") == "spaced-title"
assert slugify("Python 3") == "python-3"
