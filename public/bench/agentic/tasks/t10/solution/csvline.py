import csv


def split_line(line):
    """Split one CSV line into fields."""
    return next(csv.reader([line]))
