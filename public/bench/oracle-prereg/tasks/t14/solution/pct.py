from decimal import Decimal, ROUND_HALF_UP


def pct_change(old, new):
    if old == 0:
        return None
    old_d = Decimal(str(old))
    new_d = Decimal(str(new))
    if old_d == 0:
        return None
    diff = new_d - old_d
    result = (diff / old_d) * Decimal("100")
    result = result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(result)

