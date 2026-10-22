You are given a module `wrap.py` with a function `wrap(text, width)` that breaks a piece of text into a list of lines, each at most `width` columns wide. Existing newline characters in the input are kept as paragraph breaks: each line of the input is wrapped on its own and the resulting lines are returned in order, with an empty input line producing an empty output line. Within a paragraph the text is broken at spaces or tabs, and a tab character counts as four columns when measuring how wide a line is. If a single word is longer than the width it is hard-broken into pieces of exactly `width` columns, with the last piece allowed to be shorter. No output line may end with a space or a tab.

For example, `wrap("the quick brown fox", 10)` returns `["the quick", "brown fox"]`.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
