# Unit converter — package `conv`

Six work items; each is one module inside `conv/`. Import modules with
`from conv import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `length.py`
- Table `LENGTH` maps `"m"`, `"km"`, `"cm"`, `"mm"`, `"mi"` to metres
  (`m: 1`, `km: 1000`, `cm: 0.01`, `mm: 0.001`, `mi: 1609.344`).
- `convert(value, from_unit, to_unit)` returns `value * LENGTH[from] / LENGTH[to]`.
  An unknown unit raises `ValueError`.

## Item 2 — `mass.py`
- Table `MASS` maps `"kg"`, `"g"`, `"mg"`, `"lb"` to kilograms
  (`kg: 1`, `g: 0.001`, `mg: 1e-6`, `lb: 0.45359237`).
- `convert(value, from_unit, to_unit)` as above; unknown unit raises `ValueError`.

## Item 3 — `temp.py`
- `c_to_f(c)` = `round(c * 9 / 5 + 32, 2)`.
- `f_to_c(f)` = `round((f - 32) * 5 / 9, 2)`.
- `c_to_k(c)` = `round(c + 273.15, 2)`.

## Item 4 — `time.py`
- Table `HOURS` maps `"s"` (`1/3600`), `"min"` (`1/60`), `"h"` (`1`),
  `"day"` (`24`) to hours.
- `to_hours(value, unit)` returns `value * HOURS[unit]`; unknown unit raises
  `ValueError`.

## Item 5 — `format.py`
`fmt(value, unit) -> str`
- Return `"<value> <unit>"` where value is formatted with the Python format
  spec `"{:.4g}"` (so `2.0` prints as `2`, `0` as `0`, `1.5` as `1.5`).

## Item 6 — `square.py`
`area(side, unit) -> (float, str)`
- Return `(side * side, unit + "2")`.
