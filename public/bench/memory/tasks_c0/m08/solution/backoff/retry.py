def should_retry(attempt, max_attempts, error, retryable):
    if attempt >= max_attempts:
        return False
    return type(error) in retryable
