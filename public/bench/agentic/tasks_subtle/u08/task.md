You are given a module `slug.py` with a function `slugify(text, max_len=50)` that builds a URL slug from `text`. Convert accented characters to their plain ASCII base letters (for example é becomes e), lowercase everything, and replace every run of characters that are not ASCII letters or digits with a single hyphen, then remove any leading or trailing hyphen. If the result is longer than `max_len`, cut it at the last hyphen at or before position `max_len`, dropping that hyphen and everything after it; if there is no hyphen at or before `max_len`, cut it hard at `max_len` characters, and in either case do not leave a trailing hyphen.

For example, `slugify("Hello, World!")` returns `"hello-world"`.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
