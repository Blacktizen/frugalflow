def apply_discount(price_cents, discount_percent):
    amount = price_cents * discount_percent / 100
    total = price_cents - amount
    return max(0, round(total))
