# The method

FrugalFlow's code is useful, but the rarest thing in this repository is the way of working behind it. Each principle below is something we learned by being wrong, each one is enforced by a tool in `public/bin/` where a tool can enforce it, and each comes with a neutral example you can transpose to any project that puts AI models in the loop.

## 1. A false refusal is a defect, exactly like a hole

A guard can fail in two directions: it lets something bad through (a hole), or it blocks something good (a false refusal). Teams count holes and shrug at false refusals, because a refusal feels safe. It is not. An operator who meets wrong refusals learns to work around the guard, and then the guard protects nothing.

*Example.* A linter rule refuses any commit message containing the word "password", to stop leaked credentials. It also blocks "fix password reset page". After a week, people reword their messages to dodge the rule, then someone disables it. The rule is now worse than no rule, so a wrong refusal is logged, fixed and replayed with the same urgency as a missed leak. Every bench in this project reports both columns.

## 2. A "green" announced by the model is worth nothing without an external oracle

A model that writes code also writes a convincing sentence saying the work is done. The sentence is evidence of fluency, not of correctness. Only a check that runs on the delivered artifact, and whose verdict does not pass through the model, counts. In `delegate.py --verify`, the candidate is never written to its target until the independent check passes.

*Example.* A model reports "all 12 tests pass" after editing a parser. You rerun the suite yourself and 3 fail, because the model's summary described the tests it meant to run. On our pre-registered set, the model announced green on failing work in about one attempt out of ten, and it never announced red, so its own announcement carried no information. See [`BENCHMARKS.md`](BENCHMARKS.md), bench B3.

## 3. The oracle is never written by whoever writes the code

If one author writes both the implementation and its tests, the tests encode the author's misunderstanding along with the code. A model that writes its own checks can also write checks that pass on an empty file. The oracle comes from a different hand (another model, a person, or a script fixed in advance), and it is written, or at least frozen, before the candidate exists.

*Example.* Ask a model for a date parser and its tests in one prompt. It reports 5 passing tests, yet the file defines the function and never calls it, so the tests assert nothing. The same task with an oracle written first and run in a separate process fails immediately and says why.

## 4. A delegated task is a creation, not a retouch

Giving a cheaper model a large existing file and asking for a small edit invites silent damage: lines dropped, quotes altered, an unrelated function rewritten. Ask for a new, small, self-contained file with a precisely stated interface, then integrate it yourself or with a mechanical merge. Fidelity checks (`fidelity.py`) exist because retouching drifts: in bench B4, 69.9 % of the lines of a retouched text had drifted typography before the check.

*Example.* "Fix the timeout bug in `server.py`" (900 lines) comes back with the bug fixed and the logging format changed. "Write `retry.py` exposing `retry(fn, attempts, delay)`, here are the five cases it must pass" comes back as a file you can read in one minute and replace if it is wrong.

## 5. Criteria are fixed before the measurement (pre-registration)

If you pick the success threshold after seeing the results, you will pick one the results meet. Write down the metric, the threshold, the sample and the stopping rule before the first run, commit that file, then run. When a result lands exactly on the threshold, say so and call it fragile instead of rounding it up.

*Example.* "The new prompt should cut errors by 30 %" is written in a file and committed. The run shows 29 %. The report says "criterion missed", even though 29 % looks fine. The temptation to say "close enough" is precisely what the file is there to remove. Bench B3 follows this rule, and its result sits exactly on its threshold.

## 6. A state is re-run, not re-read

A page that says "the tests pass" or "12 open issues" is a photograph of a past moment, and it goes stale without anyone noticing. Whatever can be recomputed (counts, statuses, which checks are green) should be a command that is re-run when you need the answer, not a sentence copied into a document. When a document must carry a number, it carries the command that produces it, and the date of the last run.

*Example.* A status page lists "coverage: 84 %". Nobody updated it after the last refactor, and a new teammate trusts it. Replace the number with `make coverage` and a rule that reports quote the output of that command from today.

## 7. A guard that breaks must close, not open

If a safety check crashes, times out or cannot read its configuration, the safe outcome is refusal with a message saying how to fix it. A check that quietly returns "fine" when it fails is invisible: the dashboard stays green while nothing is checked. A default value that guesses is the same fault in another form, because it manufactures verdicts out of nothing.

*Example.* A secret scanner loads its pattern file from a path that no longer exists, catches the error and scans with an empty list. Every file passes. The fix is the opposite behaviour: a missing pattern file stops the run with a distinct exit code and a "To fix:" line. In FrugalFlow, `anon_check.py` exits with code 13 and prints `NO RULES FILE` rather than reporting a clean tree.

## 8. Testing a component is not testing its wiring

A unit of code can be perfect and never be called. A test that imports the function proves the function; it does not prove that the hook, the command or the pipeline actually reaches it. Test the path a real user takes, from the entry point, and prove the test can go red by breaking the code on purpose (`bite.py` does exactly this and writes the receipt).

*Example.* Your input sanitizer has 40 passing unit tests, but the web handler calls a different, older function. A test that posts a hostile string to the handler fails on day one. A test that never failed once is not yet a test.

## 9. Negative results get published

If only the successes are reported, readers learn nothing about where the tool does not work, and the next person repeats your dead end. A failed experiment, a bench where the tool cost more than it saved, a criterion that was not met: publish them with the same care, including the raw runs. It also keeps the positive results credible.

*Example.* A caching layer is expected to cut token use. The measurement shows a ratio of 0.94 with noise ranging from 0.56 to 1.70 across tasks. The write-up says "no saving shown", keeps the data, and names the reason it might have missed. FrugalFlow's own benches B2, B6 and B7 are in that category and sit in [`BENCHMARKS.md`](BENCHMARKS.md) next to the successes.

## 10. The refusal loop: journal, then bench, then fix without regression

Every refusal a guard issues is written to a journal. A review of that journal separates the right refusals from the wrong ones. Each wrong one becomes a case in a dedicated bench, a fix is made to the rule, and the bench is replayed in full to prove the fix did not open a new hole. Only then does the change merge. `refusal_loop.py` automates the bookkeeping and blocks a commit while a tool logs no refusals or the bench contains an unresolved false refusal or hole.

*Example.* The journal shows `grep -r "TODO" src/` being refused as a write, because the parser saw a redirect-like character inside the quotes. The case `grep with a quoted angle bracket` is added to the bench and shows red. The parser is fixed, the whole bench of previous attacks is replayed, and everything is green. The next person who hits the same pattern finds it already covered.

## How the principles fit together

A delegated model produces a candidate (4). An oracle that someone else wrote and froze judges it (2, 3). The guards around the process fail closed (7) and are tested through the real entry points (8). Every wrong refusal and every wrong acceptance feeds the loop (1, 10), measured against criteria set in advance (5), reported whatever the outcome (9), with state recomputed, never recopied (6).

None of this is specific to our tools. If you adopt only one habit, make it the second: do not accept a model's report of its own success.
