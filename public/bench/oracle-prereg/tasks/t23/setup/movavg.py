import math


def moving_average(xs, k):
    if k > len(xs):
        return []
    n = len(xs)
    result = []
    window_sum = sum(xs[:k])
    result.append(window_sum / k)
    for i in range(1, n - k + 1):
        window_sum = window_sum - xs[i - 1] + xs[i + k - 1]
        result.append(window_sum / k)
    return result

