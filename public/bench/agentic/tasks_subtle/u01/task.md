You are given a module `money.py` with a function `parse_amount(text)` that converts a human-written money amount into an integer number of cents. Fill it in so all of the following work.

Amounts may be written in US style, with a comma grouping thousands and a period for the decimal part, or in European style, with a period grouping thousands and a comma for the decimal part. When both a period and a comma appear in the number, the separator that comes last (rightmost) is the decimal separator and the other one groups thousands; when only one of the two appears, it is the decimal separator if it is followed by one or two digits, and otherwise it groups thousands. A leading minus sign or surrounding parentheses make the amount negative, and an optional currency prefix such as `$` or `€` or a suffix such as `EUR` or `USD` may be present and is ignored. If there is no decimal part, the cents are `00`, so a lone `12` means twelve dollars and zero cents. Any input that is not a well-formed amount must raise `ValueError`.

For example, `parse_amount("$1,234.50")` returns `123450`.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
