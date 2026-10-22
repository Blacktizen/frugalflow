def day_index(name):
    days = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    key = name.strip().lower()
    if key not in days:
        raise ValueError("unknown day")
    return days[key]
