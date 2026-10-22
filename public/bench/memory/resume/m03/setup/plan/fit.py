def find_slot(busy, duration, day_start, day_end):
    if duration <= 0:
        raise ValueError("duration must be positive")
    if day_start < 0 or day_end <= day_start:
        raise ValueError("invalid day bounds")
    free_from = day_start
    for s, e in sorted(busy):
        s = max(s, day_start)
        e = min(e, day_end)
        if e <= s:
            continue
        if s - free_from >= duration:
            return free_from
        free_from = max(free_from, e)
    if day_end - free_from >= duration:
        return free_from
    return None
