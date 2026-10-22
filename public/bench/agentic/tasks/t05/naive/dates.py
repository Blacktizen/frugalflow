import datetime


def add_months(date, n):
    """Return the date n months after `date`."""
    month = date.month - 1 + n
    year = date.year + month // 12
    month = month % 12 + 1
    day = date.day
    if month == 2 and day > 28:
        day = 28
    return datetime.date(year, month, day)
