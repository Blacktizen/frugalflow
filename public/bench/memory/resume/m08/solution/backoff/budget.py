def within_budget(delays, budget):
    result = []
    running = 0.0
    for d in delays:
        if running + d > budget:
            break
        result.append(d)
        running += d
    return result
