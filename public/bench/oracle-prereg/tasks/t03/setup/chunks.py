def windows(seq, size, overlap=0):
    if size < 1:
        raise ValueError("size must be >= 1")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap > size:
        raise ValueError("overlap must be <= size")
    if not seq:
        return []
    step = size - overlap
    n = len(seq)
    result = []
    i = 0
    while i + size <= n:
        result.append(seq[i:i+size])
        i += step
    if i < n:
        result.append(seq[i:i+size])
    return result

