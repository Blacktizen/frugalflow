The file `app.log` contains log entries, one per line, where each entry starts with `YYYY-MM-DD HH:MM:SS LEVEL message` and LEVEL is one of INFO, WARN, ERROR or DEBUG. Some entries are followed by one or more continuation lines (for example stack traces starting with `Traceback` or indented lines) that belong to that same entry and are not new entries. A message may itself contain a word such as ERROR. Write `levels.json` as a JSON object counting how many entries have each level, with keys INFO, WARN, ERROR and DEBUG.

For example, if the file contained only `2026-01-01 00:00:00 INFO started`, then `levels.json` would be `{"INFO": 1, "WARN": 0, "ERROR": 0, "DEBUG": 0}`.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
