def batch_by_weight(items, max_weight):
    if max_weight <= 0:
        raise ValueError("max_weight must be positive")
    for name, weight in items:
        if weight < 0:
            raise ValueError("weight must be non-negative")

    result = []
    current_batch = []
    current_sum = 0

    for name, weight in items:
        if weight > max_weight:
            if current_batch:
                result.append(current_batch)
            result.append([name])
            current_batch = []
            current_sum = 0
        else:
            if current_sum + weight > max_weight:
                if current_batch:
                    result.append(current_batch)
                current_batch = [name]
                current_sum = weight
            else:
                current_batch.append(name)
                current_sum += weight

    if current_batch:
        result.append(current_batch)

    return result

