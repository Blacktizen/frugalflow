import random
import sys

sys.dont_write_bytecode = True

FILES = ["svc.log"]
LINES_PER_FILE = 2500

LEVELS = ["INFO", "WARN", "ERROR", "DEBUG"]
LEVEL_WEIGHTS = [45, 25, 20, 10]
SERVICES = ["api-4", "db-2", "edge-1", "svc-a", "worker-7", "cache-1", "queue-3", "auth-2"]
CODES = {
    "INFO": ["I-001", "I-002", "I-003"],
    "WARN": ["W-301", "W-305", "W-307"],
    "ERROR": ["E-102", "E-104", "E-110", "E-118"],
    "DEBUG": ["D-010", "D-011"],
}
MESSAGES = {
    "INFO": [
        "connection accepted from client",
        "request completed",
        "health check passed",
        "cache hit on cold key",
    ],
    "WARN": [
        "query took longer than expected",
        "connection timeout while waiting for a reply",
        "queue depth above warning level",
        "cache miss on hot key",
    ],
    "ERROR": [
        "upstream service did not respond",
        "worker failed to finish a task",
        "database write failed",
        "queue overflow detected",
    ],
    "DEBUG": [
        "heartbeat sent to controller",
        "reconnect scheduled in a few seconds",
        "packet inspected and dropped",
    ],
}


def timestamp(idx):
    secs = idx * 23
    hour = (secs // 3600) % 24
    minute = (secs // 60) % 60
    second = secs % 60
    return "2026-02-03T%02d:%02d:%02d" % (hour, minute, second)


def main():
    rng = random.Random(2026)
    idx = 0
    for fname in FILES:
        with open(fname, "w") as handle:
            for _ in range(LINES_PER_FILE):
                level = rng.choices(LEVELS, weights=LEVEL_WEIGHTS, k=1)[0]
                service = rng.choice(SERVICES)
                code = rng.choice(CODES[level])
                message = rng.choice(MESSAGES[level])
                handle.write("%s %s %s %s %s\n" % (timestamp(idx), level, service, code, message))
                idx += 1


if __name__ == "__main__":
    main()
