# Text tokenizer — package `tok`

Six work items; each is one module inside `tok/`. Import modules with
`from tok import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `tokenize.py`
`words(text) -> list[str]`
- Lowercase `text` and split it into maximal runs of alphanumeric characters
  (use `str.isalnum()`), preserving order and dropping everything else.
- An empty or punctuation-only text yields `[]`.
- A non-string `text` raises `ValueError`.

## Item 2 — `count.py`
`frequencies(tokens) -> dict`
- Return a dict mapping each token to how many times it occurs.

## Item 3 — `stop.py`
`remove_stopwords(tokens, stopwords) -> list[str]`
- Return the tokens that are not in `stopwords` (treated as a set), preserving
  order. Case is significant.

## Item 4 — `stem.py`
`stem(word) -> str`
- If `word` has fewer than 2 characters, return it unchanged.
- Otherwise strip the FIRST matching suffix among `"ing"`, `"ed"`, `"s"` (in that
  order) if `word` ends with it AND the remaining part has at least 2 characters.
  Strip at most one suffix.

## Item 5 — `ngram.py`
`bigrams(tokens) -> list`
- Return the list of consecutive pairs `(tokens[i], tokens[i+1])`.
  Fewer than 2 tokens yields `[]`.

## Item 6 — `vocab.py`
`unique_sorted(tokens) -> list[str]`
- Return the unique tokens as a sorted list.
