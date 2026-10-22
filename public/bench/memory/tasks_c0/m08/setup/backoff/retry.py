def should_retry(attempt, max_attempts, error, retryable):
    if attempt >= max_attempts:
        return False
    # TODO: also require the error type to be in the retryable set
    return True
