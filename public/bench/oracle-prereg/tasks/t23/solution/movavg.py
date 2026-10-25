import math


def moving_average(xs, k):
    if k < 1:
        raise ValueError("k must be >= 1")
    if k > len(xs):
        return []
    n = len(xs)
    result = []
    for i in range(n - k + 1):
        window = xs[i : i + k]
        avg = math.fsum(window) / k
        result.append(float(avg))
    return result

