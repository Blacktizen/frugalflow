from decimal import Decimal, ROUND_HALF_UP


def total(lines):
    cents = 0
    for price, qty, tax in lines:
        subtotal = Decimal(str(price)) * qty
        line = subtotal + subtotal * Decimal(tax) / Decimal(100)
        line = line.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cents += int(line * 100)
    return cents
