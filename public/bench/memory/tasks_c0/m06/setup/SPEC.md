# Markdown table renderer — package `table`

Six work items; each is one module inside `table/`. Import modules with
`from table import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `split.py`
`split(text) -> list[list[str]]`
- Split `text` into rows on newlines; skip rows that are empty after stripping.
- Split each row into cells on `"|"` and strip each cell.
- If a row starts with `|`, drop the empty first cell; if it ends with `|`,
  drop the empty last cell. Interior empty cells are kept.
- A non-string `text` raises `ValueError`.

## Item 2 — `widths.py`
`widths(rows) -> list[int]`
- Return, per column, the maximum length of the cells in that column.
- Rows may be ragged: a missing cell counts as `""`. Empty input yields `[]`.

## Item 3 — `render.py`
`render(rows) -> str`
- Render a markdown table: a header row, a separator row of `-` characters, then
  the remaining rows. Each cell is left-justified to its column width and framed
  as `"| cell | ... |"`. Empty input renders as `""`. End with a trailing newline.

## Item 4 — `align.py`
`pad(cell, width, align) -> str`
- `"left"`: `cell.ljust(width)`. `"right"`: `cell.rjust(width)`.
- `"center"`: pad with spaces so the cell is centred; when the padding is odd,
  put the extra space on the RIGHT.
- Any other `align` raises `ValueError`.

## Item 5 — `escape.py`
`escape(cell) -> str`
- Return `cell` with every `"|"` replaced by `"\|"`.

## Item 6 — `markdown.py`
`table(text) -> str`
- The pipeline: `render(split(text))`.
