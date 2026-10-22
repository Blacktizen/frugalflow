In this folder, `pricing.py` declares `apply_discount(price_cents, discount_percent)` but its body is missing. Implement it.

The function takes a non-negative integer price in cents and a non-negative integer discount percentage. It returns the price in cents after the discount, as an integer: compute the discount amount as price * percentage / 100, subtract it from the price, round the result to the nearest integer cent, and never return a value below zero. Keep the function name and the file name unchanged. Use only the Python standard library. The module must stay importable.

The result is verified by an automatic script that imports `pricing` from this folder and calls `apply_discount` on several pairs of integers, checking each result for exact equality.
