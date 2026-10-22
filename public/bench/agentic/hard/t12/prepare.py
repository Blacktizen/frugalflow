import random
import sys

sys.dont_write_bytecode = True

FILES = ["events.log"]
LINES_PER_FILE = 2400

TYPES = ["purchase", "refund", "signup", "chargeback", "adjustment"]
TYPE_WEIGHTS = [40, 15, 25, 8, 12]


def timestamp(idx):
    secs = idx * 17
    hour = (secs // 3600) % 24
    minute = (secs // 60) % 60
    second = secs % 60
    return "2026-04-01T%02d:%02d:%02d" % (hour, minute, second)


def main():
    rng = random.Random(4242)
    idx = 0
    for fname in FILES:
        with open(fname, "w") as handle:
            for _ in range(LINES_PER_FILE):
                idx += 1
                etype = rng.choices(TYPES, weights=TYPE_WEIGHTS, k=1)[0]
                event_id = "evt-%04d" % idx
                if etype == "signup":
                    amount = 0
                else:
                    amount = rng.randint(100, 2000)
                handle.write("%s %s %s %d\n" % (timestamp(idx), etype, event_id, amount))


if __name__ == "__main__":
    main()
