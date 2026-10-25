class TokenBucket:
    def __init__(self, capacity, refill_per_sec):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = float(capacity)
        self.last_now = None

    def allow(self, now, cost=1):
        if cost > self.capacity:
            return False

        if self.last_now is None:
            self.last_now = now
        else:
            if now > self.last_now:
                self.tokens += self.refill_per_sec * (now - self.last_now)
                if self.tokens > self.capacity:
                    self.tokens = self.capacity
                self.last_now = now

        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

