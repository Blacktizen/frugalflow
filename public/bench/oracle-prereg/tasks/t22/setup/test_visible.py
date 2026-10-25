from dedupe import keep_last

rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]
result = keep_last(rows, "name")
assert result == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}], "T1"

rows = [{"id": 1, "name": "x"}, {"id": 2, "name": "y"}]
result = keep_last(rows, "name")
assert result == [{"id": 1, "name": "x"}, {"id": 2, "name": "y"}], "T2"

rows = [{"id": 1, "name": "z"}]
result = keep_last(rows, "name")
assert result == [{"id": 1, "name": "z"}], "T3"

rows = [{"id": 1, "name": "p"}, {"id": 2, "name": "q"}]
result = keep_last(rows, "id")
assert result == [{"id": 1, "name": "p"}, {"id": 2, "name": "q"}], "T4"

print("OK")

