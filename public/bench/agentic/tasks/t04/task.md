# Task: total parcel weight

The file `parcels.csv` has a header row `id,weight,unit` followed by data rows. The `unit` column is one of `kg`, `g`, or `lb`, but it may be written with different capitalization and with leading or trailing spaces. Convert every weight to kilograms using 1 kg = 1 kg, 1000 g = 1 kg, and 1 lb = 0.45359237 kg.

Write `weight.json` with `total_kg` equal to the sum of all converted weights, rounded to 3 decimal places.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
