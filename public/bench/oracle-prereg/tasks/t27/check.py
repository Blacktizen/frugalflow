import sys

TASK_ID = "redact_emails_v1"

try:
    from redact import redact_emails
except ImportError as exc:
    print("FAIL " + TASK_ID + " import error: " + str(exc)[:580])
    sys.exit(1)

cases = [
    ("a@example.com", "a***@example.com"),
    ("ab@example.com", "a***@example.com"),
    ("alice@example.com", "a***@example.com"),
    ("abcd@example.com", "a***@example.com"),
    ("alice@bob", "alice@bob"),
    ("hello @mot there", "hello @mot there"),
    ("alice@example.com and bob@example.net", "a***@example.com and b***@example.net"),
    ("user123@example.com", "u***@example.com"),
    ("alice@sub." + "example.com", "a***@sub." + "example.com"),
    ("", ""),
    ("no emails here", "no emails here"),
    ("x@example.com", "x***@example.com"),
    ("bob@example.com, alice@example.net", "b***@example.com, a***@example.net"),
    ("start alice@example.com end", "start a***@example.com end"),
    ("a@example.net", "a***@example.net"),
]

discrepancies = []

for idx, (inp, expected) in enumerate(cases):
    try:
        result = redact_emails(inp)
        if result != expected:
            discrepancies.append("case %d: expected %r, obtained %r" % (idx, expected, result))
    except Exception as exc:
        discrepancies.append("case %d: exception %s" % (idx, str(exc)))
    if discrepancies:
        break

if discrepancies:
    msg = "FAIL " + TASK_ID
    for i, d in enumerate(discrepancies[:3]):
        msg += " | " + d
    msg = msg[:600]
    print(msg)
    sys.exit(1)

print("PASS")
sys.exit(0)
