#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile, datetime


def base():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_path():
    return os.environ.get("GUARD_PROBES_DATA") or os.path.join(base(), "data", "guard_probes.json")


def hook_path():
    return os.environ.get("GUARD_PROBES_HOOK") or os.path.join(base(), "bin", "guard_hook.py")


def subst(value, home, now):
    if isinstance(value, str):
        return value.replace("{home}", home).replace("{now}", now)
    if isinstance(value, dict):
        return {k: subst(v, home, now) for k, v in value.items()}
    if isinstance(value, list):
        return [subst(v, home, now) for v in value]
    return value


def run_probe(settings, probe):
    with tempfile.TemporaryDirectory() as h:
        now = datetime.datetime.now().astimezone().isoformat()
        with open(os.path.join(h, "guard.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(settings))
        for item_name, (txt, n) in probe["files"].items():
            with open(os.path.join(h, item_name), "w", encoding="utf-8") as f:
                f.write(txt * n)
        with open(os.path.join(h, "delegations.jsonl"), "w", encoding="utf-8") as f:
            for r in subst(probe["log"], h, now):
                f.write(json.dumps(r) + "\n")
        env = dict(os.environ)
        env["FRUGALFLOW_HOME"] = h
        call = subst(probe["call"], h, now)
        proc = subprocess.run(
            [sys.executable, hook_path(), "--hook"],
            input=json.dumps(call),
            capture_output=True,
            text=True,
            cwd=h,
            env=env,
        )
        got = "deny" if '"deny"' in proc.stdout else "allow"
        return (got, proc.returncode)


def replay():
    try:
        with open(data_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        print("probes unreadable", file=sys.stderr)
        return 3
    ok = 0
    probes = data["probes"]
    for p in probes:
        got, code = run_probe(data["settings"], p)
        conform = code == 0 and got == p["expect"]
        if conform:
            ok += 1
            print(f"PASS probe {p['id']} {p['name']}: expected {p['expect']} (old {p['old']}) | got {got}")
        else:
            print(f"FAIL probe {p['id']} {p['name']}: expected {p['expect']} (old {p['old']}) | got {got} rc={code}")
    print(f"{ok}/{len(probes)} probes conform")
    return 0 if ok == len(probes) else 1


def main():
    args = sys.argv[1:]
    if args == ["--autotest"]:
        sys.exit(replay())
    elif args == ["--notice"]:
        print("NAME      guard_probes.py - replays the 13 probes of an earlier delegation guard against guard_hook.py, one fresh FRUGALFLOW_HOME per probe.")
        print("READS     ../data/guard_probes.json (or GUARD_PROBES_DATA); runs ../bin/guard_hook.py (or GUARD_PROBES_HOOK) as a subprocess.")
        print("WRITES    one PASS or FAIL line per probe, then the count, on stdout. Exits 0 when every probe is conform, 1 otherwise, 2 on a bad argument, 3 when the data cannot be read.")
        print("EXAMPLE   python3 guard_probes.py --autotest")
        print("PITFALLS  2026-09-26 only probe 2 of a naive guard was in the guards E2E; a probe that turns red means a hole was opened.")
        print("          FRUGALFLOW_GUARD=0 in the environment disarms the hook: every deny probe must then turn red.")
        sys.exit(0)
    else:
        print("usage: guard_probes.py --autotest | --notice")
        sys.exit(2)


if __name__ == "__main__":
    main()
