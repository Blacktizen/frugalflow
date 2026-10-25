
import sys
sys.path.insert(0, '.')

task_id = "titles_title_case"
failures = []

try:
    from titles import title_case
except Exception as e:
    print("FAIL " + task_id + " | import | expected=callable obtained=" + str(e))[:600]
    sys.exit(1)

cases = [
    ("hello world", "Hello World", "basic_capitalization"),
    ("the cat in the hat", "The Cat in the Hat", "small_middle_first_last"),
    ("a day to remember", "A Day to Remember", "small_first_and_middle"),
    ("up-to-date", "Up-to-Date", "hyphen_small_in_middle"),
    ("a-to-a", "A-to-A", "hyphen_small_at_start_end"),
    ("up-TO-date", "Up-TO-Date", "allcaps_in_compound"),
    ("THE cat", "THE Cat", "allcaps_word_preserved"),
    ("TO go", "TO Go", "allcaps_small_still_preserved"),
    ("  hello  world  ", "  Hello  World  ", "multiple_spaces_preserved"),
    ("a  the  a", "A  the  A", "first_last_small_multi_space"),
    ("the-up-to-the", "The-Up-to-The", "hyphen_compound_small_start_end"),
    ("of a", "Of A", "small_at_first_and_last"),
    ("A", "A", "single_letter_reprocessed"),
    ("", "", "empty_string"),
    ("a", "A", "single_small_first_last"),
]

for inp, expected, desc in cases:
    try:
        got = title_case(inp)
        if got != expected:
            failures.append((desc, expected, got))
    except Exception as e:
        failures.append((desc, expected, "EXC:" + str(e)))

if failures:
    msg = "FAIL " + task_id
    for desc, exp, got in failures[:3]:
        msg += " | " + desc + " expected=" + repr(exp) + " obtained=" + repr(got)
    print(msg[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
