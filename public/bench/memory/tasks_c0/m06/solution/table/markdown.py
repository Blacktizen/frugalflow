from table import split as _split
from table import render as _render

def table(text):
    return _render.render(_split.split(text))
