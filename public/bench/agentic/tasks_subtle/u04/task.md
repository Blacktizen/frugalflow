You are given a module `semver.py` with a function `compare(a, b)` that returns -1, 0 or 1 according to semantic version precedence. Versions have numeric major, minor and patch parts; a version may have a pre-release part after a `-` and build metadata after a `+`, and the build metadata is ignored when comparing. A pre-release version has lower precedence than the same version without one. Within the pre-release part, identifiers are compared numerically when they are numeric and by ASCII order when they are alphanumeric, and a numeric identifier is lower than an alphanumeric one. When all preceding identifiers are equal, a version with fewer identifiers has lower precedence than one with more.

For example, `compare("1.2.3", "1.10.0")` returns `-1`.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
