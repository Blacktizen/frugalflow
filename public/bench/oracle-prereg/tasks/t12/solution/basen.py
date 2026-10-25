def to_base(n, base):
    if isinstance(n, bool):
        raise ValueError("n must be an integer, not bool")
    if not isinstance(n, int):
        raise ValueError("n must be an integer")
    if not isinstance(base, int) or isinstance(base, bool):
        raise ValueError("base must be an integer")
    if base < 2 or base > 36:
        raise ValueError("base must be between 2 and 36")
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    negative = n < 0
    n = abs(n)
    result = ""
    while n > 0:
        result = digits[n % base] + result
        n //= base
    if negative:
        result = "-" + result
    return result

