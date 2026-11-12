# Security Policy

## Scope

FrugalFlow protects a cooperative assistant from its own mistakes: forgetting
the project's rules, skipping a delegation, writing over a log, turning a
setting off, sending private data to a third party. It is not a security
boundary against a hostile agent: the hooks run as the same user as the
assistant, and no rule on the text of a command can see inside it. What is
covered and what is not is listed in
[public/THREAT_MODEL.md](public/THREAT_MODEL.md).

## Reporting a vulnerability

Report a vulnerability through a private security advisory on GitHub: open the
Security tab of the repository and choose "Report a vulnerability". Never
report it in a public issue, so the fix can ship before the bypass is known.

## Public adversarial review program

Anyone may try to bypass the guard. A valid finding is a replayable command or
file that the guard lets through and that the threat model says it should
stop. Each accepted finding becomes a red-then-green test in `public/tests`
and a line in [CHANGELOG.md](CHANGELOG.md).

The text guard is frozen at v0.1.7: findings against it are recorded as known
bypass families; findings against the coming isolated mode are fixed.

## Hall of fame

| Version | Bypasses found | Found by |
|---|---|---|
| v0.1.2 | case folding (1 family) | independent AI review session |
| v0.1.3 | 19 | independent AI review session |
| v0.1.4 | 12 | independent AI review session |
| v0.1.5 | 13 | independent AI review session |
| v0.1.6 | 3 | independent AI review session |
| v0.1.7 | 5 | independent AI review session |
| next release | your finding | Your name here |
