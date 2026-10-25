import sys
from redact import redact_emails

try:
    assert redact_emails("abcd@example.com") == "a***@example.com"
    assert redact_emails("hello world 123") == "hello world 123"
    assert redact_emails("abcd@example.net and efgh@example.net") == "a***@example.net and e***@example.net"
    assert redact_emails("no emails here") == "no emails here"
    print("OK")
    sys.exit(0)
except AssertionError:
    sys.exit(1)

