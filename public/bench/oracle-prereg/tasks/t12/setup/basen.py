def to_base(n, base):
    if not isinstance(n, int):
        raise ValueError("n must be an integer")
    if base < 0 or base > 36:
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
    return "-" + result if negative else result

