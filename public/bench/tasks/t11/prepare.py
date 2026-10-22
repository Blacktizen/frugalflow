import random
import sys

sys.dont_write_bytecode = True

FILES = ["jobs.log"]
LINES_PER_FILE = 2200


def timestamp(idx):
    secs = idx * 41
    hour = (secs // 3600) % 24
    minute = (secs // 60) % 60
    second = secs % 60
    return "2026-03-12T%02d:%02d:%02d" % (hour, minute, second)


def main():
    rng = random.Random(7701)
    idx = 0
    for fname in FILES:
        with open(fname, "w") as handle:
            for _ in range(LINES_PER_FILE):
                idx += 1
                job_id = "job-%04d" % idx
                if rng.random() < 0.12:
                    status = "FAIL"
                    duration = rng.randint(1, 200)
                else:
                    status = "OK"
                    duration = rng.randint(10, 4000)
                handle.write("%s %s %s %d\n" % (timestamp(idx), job_id, status, duration))


if __name__ == "__main__":
    main()
