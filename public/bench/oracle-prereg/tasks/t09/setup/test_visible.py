import sys
from rle import rle_decode

def run():
    try:
        assert rle_decode("3a2b1c") == "aaabbc"
        assert rle_decode("12x") == "xxxxxxxxxxxx"
        assert rle_decode("") == ""
        assert rle_decode("0a") == ""
        print("OK")
        sys.exit(0)
    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    run()

