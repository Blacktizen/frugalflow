import random
import sys

sys.dont_write_bytecode = True

FILES = ["access.log"]
LINES_PER_FILE = 2500

HOSTS = ["edge-2", "svc-a", "node-3", "api-4", "db-2", "worker-7"]
METHODS = ["GET", "POST", "PUT", "DELETE"]
METHOD_WEIGHTS = [70, 15, 10, 5]
PATHS = [
    "/api/orders",
    "/api/users",
    "/api/login",
    "/api/report",
    "/api/billing",
    "/index.html",
    "/static/app.js",
    "/health",
]
STATUSES = [200, 201, 204, 301, 400, 401, 403, 404, 500, 502, 503]
STATUS_WEIGHTS = [55, 5, 3, 4, 8, 4, 3, 8, 4, 3, 3]


def timestamp(idx):
    secs = idx * 37
    hour = (secs // 3600) % 24
    minute = (secs // 60) % 60
    second = secs % 60
    return "2026-01-15T%02d:%02d:%02d" % (hour, minute, second)


def main():
    rng = random.Random(1234)
    idx = 0
    for fname in FILES:
        with open(fname, "w") as handle:
            for _ in range(LINES_PER_FILE):
                host = rng.choice(HOSTS)
                method = rng.choices(METHODS, weights=METHOD_WEIGHTS, k=1)[0]
                path = rng.choice(PATHS)
                status = rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
                size = rng.randint(0, 90000)
                handle.write("%s %s %s %s %d %d\n" % (timestamp(idx), host, method, path, status, size))
                idx += 1


if __name__ == "__main__":
    main()
