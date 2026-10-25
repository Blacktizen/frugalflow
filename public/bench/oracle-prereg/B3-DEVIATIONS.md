# B3: deviations in the pre-registration (except B3-PREREG.md, which stays unchanged)

D1 (02:05, before any resolution call): the validity guard rejected 15 tasks out of 35 at the 1st generation, then 8
more after the 2nd (t02 t04 t12 t17 t18 t26 t28 t34), leaving 27 valid tasks for a pre-registered minimum of 30. The
pre-registration allows ONE regeneration. A 3rd regeneration (same task statement, same generation instruction) of the 8 remaining
tasks is performed to reach 30; this is a deviation, decided before any measurement of the model on the tasks, and which
affects neither the task statement, nor the metric, nor the thresholds. Tasks still invalid after this 3rd generation are excluded.
D2: the pre-registered pilot tasks (t05, t17, t25): t17 is invalid at the 2nd generation; if it remains excluded, the
pilot takes the next valid task in numerical order (t19).
D3 (02:20): the launcher `runner.py` delivered by the local model (2 trials, red verification) passes 4 out of 5 autotest checks; the
5th fails because of a flaw in the fake delegate of the AUTOTEST (it does not import os), not the launcher. Rule "after 2 failures,
stop the point": the launcher is not redelegated, it is used as delivered, under the name `runner.py.partiel.py`
(kept as such in the repository, nothing is renamed by hand).
D4 (02:25): the pilot (t05, t19, t25) showed that the launcher reads tokens on standard output while the delegation tool prints them on standard
error: 0 tokens. Fix without touching the launcher: a wrapper `delegate_wrap.py` (local model, autotest 3/3) passed via
`--delegate`. The pilot data without tokens is discarded (`pilot_notokens.jsonl`, kept for record, excluded from measurement)
and the pilot is replayed with the wrapper.
D5: the pilot replaces t17 (invalid) with t19 (see D2).

D6 (25/10, after the measurement, audit-fixes branch): the 5th autotest of `runner.py.partiel.py` failed because the fake
"nofence" delegate of the AUTOTEST itself imported `sys` but not `os` (D3). One word fixed in that fake (`import sys, os`);
the autotest now passes 5/5. The runner code that produced the published results is unchanged (the fake is used only by
`--autotest`), so the B3 figures are not affected.

D7 (25/10, after the measurement, audit-fixes branch): the e-mail addresses of task t27 (`check.py`, `setup/test_visible.py`, `task.md`) used
domains the publication gate rejects (anything but example.com and example.net). They were replaced by those two domains; the logic under test
(first letter, three stars, domain kept) does not depend on the domain, and the validity guard still holds (reference green, naive version red).
t27 was not measured again: its recorded result (no false green in 4 attempts) was obtained on the previous addresses.
