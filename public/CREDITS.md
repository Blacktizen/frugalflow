# Credits

FrugalFlow reuses what others already do better, and names them. Material reused as is keeps
its licence next to it; an idea rewritten here was proven by a test seen red.

| Idea | From | Where it lives here |
|---|---|---|
| Secret detection rules, **reused as is** (439 of 463 rules; `generic-` rules and patterns Python refuses are left out) | **Zachary Rice**, [`betterleaks/betterleaks`](https://github.com/betterleaks/betterleaks), MIT (`data/BETTERLEAKS_LICENSE`) | `data/betterleaks_rules.json`, rebuilt by `bin/import_betterleaks.py`, loaded by `bin/anon_rules.py` |
| A leak detector is proven on planted fixtures **before** it is trusted on the repository | `mpommrehn/agent-delegation-kit`, `tests/run-tests.sh` | `tests/e2e_anonymizer.py`, test 1: ten planted leaks, each must be found, then the rules are disarmed and the private ones must disappear |

## Ideas taken, rewritten (no code copied)

| Idea | From | Licence | Where |
|---|---|---|---|
| One-token probe before the real call, telling engine absent, model unknown, model stuck | delegate-local, `scripts/delegate.sh` | MIT | `card_rules.py`, `card_check.py` |
| Escalation rate always shown, even at zero; counterfactual cost on the expensive model | efficient-model-selection, `model-selection-report.py` | MIT | `ledger_rules.py` |
| Cost receipt printed by a hook, never by the model | claude-delegator-deepseek-mcp | MIT | `usage_report.py --hook` |
| Count a message once although the transcript repeats its usage on several lines | ccusage | see its repository | `usage_rules.py` |
