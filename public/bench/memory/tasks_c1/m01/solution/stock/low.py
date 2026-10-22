def below(totals, limit):
    return sorted(name for name, qty in totals.items() if qty < limit)
