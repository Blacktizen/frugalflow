import datetime


def add_months(date, n):
    """Return the date n months after `date`."""
    month = date.month - 1 + n
    year = date.year + month // 12
    month = month % 12 + 1
    return datetime.date(year, month, date.day)
