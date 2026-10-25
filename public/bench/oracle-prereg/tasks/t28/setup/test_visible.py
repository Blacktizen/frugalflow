import sys
from envexp import env_expand

def run():
    ok = True
    if env_expand("${VAR}", {"VAR": "hello"}) != "hello":
        ok = False
    if env_expand("$$", {}) != "$":
        ok = False
    if env_expand("${MISSING}", {}) != "":
        ok = False
    if env_expand("$VAR", {"VAR": "x"}) != "$VAR":
        ok = False
    if not ok:
        sys.exit(1)
    print("OK")

if __name__ == "__main__":
    run()

