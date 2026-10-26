import json
import os
import shutil
import subprocess
import sys
import tempfile


def read_sessions(chain_dir):
    path = os.path.join(chain_dir, "results.jsonl")
    sessions = []
    if not os.path.isfile(path):
        return sessions
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                sessions.append(json.loads(line))
    return sessions


def is_complete(sessions):
    ks = sorted(int(s.get("k", 0)) for s in sessions)
    if ks != [1, 2, 3, 4, 5]:
        return False
    for s in sessions:
        if s.get("infra"):
            return False
    return True


def load_chains(runs_dir):
    chains = {}
    for name in sorted(os.listdir(runs_dir)):
        d = os.path.join(runs_dir, name)
        if not os.path.isdir(d):
            continue
        sessions = read_sessions(d)
        chains[name] = {
            "name": name,
            "cond": name[:1],
            "sessions": sessions,
            "complete": is_complete(sessions),
        }
    return chains


def cum_tokens(chain):
    cum = {}
    total = 0
    for s in sorted(chain["sessions"], key=lambda x: int(x.get("k", 0))):
        total += int(s.get("tokens", {}).get("total", 0))
        cum[int(s.get("k", 0))] = total
    return cum


def session_at(chain, k):
    for s in chain["sessions"]:
        if int(s.get("k", 0)) == k:
            return s
    return {}


def mean(vals):
    if not vals:
        return None
    return sum(vals) / len(vals)


def pairwise_max(vals):
    if len(vals) < 2:
        return None
    best = 0.0
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            d = abs(vals[i] - vals[j])
            if d > best:
                best = d
    return best


def memory_ratio(chain):
    first = session_at(chain, 1)
    first_slugs = set(first.get("slugs", []))
    s5 = session_at(chain, 5)
    modules = s5.get("rules", {}).get("modules", {})
    delivered = 0
    conformes = 0
    for name in sorted(modules):
        if name in first_slugs:
            continue
        mod = modules[name]
        if mod.get("delivered"):
            delivered += 1
            if mod.get("ok"):
                conformes += 1
    if delivered == 0:
        return 0.0
    return conformes / delivered


def cond_stats(chains, cond):
    lst = [c for c in chains.values() if c["complete"] and c["cond"] == cond]
    st = {"n": len(lst), "avg_cum": {}, "ecart_cum": {}}
    for k in range(1, 6):
        vals = [cum_tokens(c)[k] for c in lst]
        st["avg_cum"][k] = mean(vals)
        st["ecart_cum"][k] = pairwise_max(vals)
    solved = []
    respect = []
    memoire = []
    t5_bad = 0
    for c in lst:
        s5 = session_at(c, 5)
        solved.append(float(s5.get("solved_cum", 0)))
        summary = s5.get("rules", {}).get("summary", {})
        delivered = int(summary.get("delivered", 0))
        conformes = int(summary.get("conformes", 0))
        respect.append(conformes / delivered if delivered else 0.0)
        memoire.append(memory_ratio(c))
        for s in c["sessions"]:
            if s.get("rules", {}).get("t5", {}).get("tests_intact", True) is False:
                t5_bad += 1
    st["solved_avg"] = mean(solved)
    st["solved_ecart"] = pairwise_max(solved)
    st["respect_avg"] = mean(respect)
    st["respect_ecart"] = pairwise_max(respect)
    st["memoire_avg"] = mean(memoire)
    st["t5_bad"] = t5_bad
    return st


def section1(chains):
    out = ["## 1. Tableau session par session", ""]
    out.append("| chaine | k | jetons entree | jetons sortie | total | cumule | resolus session | resolus cumules | modules conformes | tours | duree mur | tuee |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name in sorted(chains):
        chain = chains[name]
        cum = cum_tokens(chain)
        for s in sorted(chain["sessions"], key=lambda x: int(x.get("k", 0))):
            k = int(s.get("k", 0))
            tok = s.get("tokens", {})
            summary = s.get("rules", {}).get("summary", {})
            out.append("| {} | {} | {} | {} | {} | {} | {}/{} | {} | {}/{} | {} | {} | {} |".format(
                name, k, tok.get("input", 0), tok.get("output", 0), tok.get("total", 0),
                cum.get(k, 0), s.get("solved_session", 0), len(s.get("slugs", [])),
                s.get("solved_cum", 0), summary.get("conformes", 0), summary.get("delivered", 0),
                tok.get("turns", 0), s.get("wall_s", 0), "oui" if s.get("killed") else "non"))
    return out


def section2(stats):
    out = ["## 2. Courbe du cout cumule par condition", ""]
    out.append("| k | moyenne A | ecart A | barre A | moyenne B | ecart B | barre B |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for k in range(1, 6):
        row = [str(k)]
        for cond in ("A", "B"):
            st = stats[cond]
            avg = st["avg_cum"][k]
            ec = st["ecart_cum"][k]
            if avg is None:
                row.extend(["n/a", "n/a", ""])
            else:
                row.append("{:.0f}".format(avg))
                row.append("n/a" if ec is None else "{:.0f}".format(ec))
                row.append("#" * int(round(avg / 100000.0)))
        out.append("| " + " | ".join(row) + " |")
    return out


def section_incomplete(chains):
    out = ["## Chaines incompletes", ""]
    names = [n for n in sorted(chains) if not chains[n]["complete"]]
    if not names:
        out.append("- aucune")
    for n in names:
        out.append("- {} : {} session(s) faite(s)".format(n, len(chains[n]["sessions"])))
    return out


def fmt_num(v, digits):
    if v is None:
        return "n/a"
    return "{:.{}f}".format(v, digits)


def section3(stats):
    out = ["## 3. Reussite et respect a k = 5", ""]
    out.append("| condition | chaines completes | solved_cum moyen | ecart solved | score respect | ecart respect | score memoire | sessions t5 tests_intact faux |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for cond in ("A", "B"):
        st = stats[cond]
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            cond, st["n"],
            fmt_num(st["solved_avg"], 2), fmt_num(st["solved_ecart"], 2),
            fmt_num(st["respect_avg"], 3), fmt_num(st["respect_ecart"], 3),
            fmt_num(st["memoire_avg"], 3), st["t5_bad"]))
    return out


def verdict_cout(sa, sb):
    a5 = sa["avg_cum"][5]
    b5 = sb["avg_cum"][5]
    if a5 is None or b5 is None:
        return "NON PROUVE", "aucun"
    e = max(sa["ecart_cum"][5], sb["ecart_cum"][5])
    if not (a5 - b5 > e):
        return "NON PROUVE", "aucun"
    for start in range(1, 6):
        ok = True
        for k in range(start, 6):
            if not (sb["avg_cum"][k] < sa["avg_cum"][k]):
                ok = False
                break
        if ok:
            return "UTILE", start
    return "NON PROUVE", "aucun"


def verdict_reussite(sa, sb):
    ds = sb["solved_avg"] - sa["solved_avg"]
    es = max(sa["solved_ecart"], sb["solved_ecart"])
    if ds >= 2 and ds > es:
        return "UTILE"
    dr = sb["respect_avg"] - sa["respect_avg"]
    er = max(sa["respect_ecart"], sb["respect_ecart"])
    if dr >= 0.15 and dr > er:
        return "UTILE"
    return "NON PROUVE"


def verdict_nuisible(sa, sb):
    e = max(sa["ecart_cum"][5], sb["ecart_cum"][5])
    return (sb["avg_cum"][5] - sa["avg_cum"][5] > e
            and sb["solved_avg"] <= sa["solved_avg"]
            and sb["respect_avg"] <= sa["respect_avg"])


def verdict_lines(stats):
    out = ["## 4. Verdict", ""]
    sa = stats["A"]
    sb = stats["B"]
    if sa["n"] < 2 or sb["n"] < 2:
        msg = "NON PROUVE (moins de deux repetitions completes par condition)"
        out.append("VERDICT COUT: " + msg)
        out.append("VERDICT REUSSITE: " + msg)
        out.append("VERDICT GLOBAL: " + msg)
        return out
    cout, k0 = verdict_cout(sa, sb)
    out.append("VERDICT COUT: {} (k0 = {})".format(cout, k0))
    reussite = verdict_reussite(sa, sb)
    out.append("VERDICT REUSSITE: " + reussite)
    if cout == "UTILE" or reussite == "UTILE":
        parts = []
        if cout == "UTILE":
            parts.append("cout")
        if reussite == "UTILE":
            parts.append("reussite")
        out.append("VERDICT GLOBAL: UTILE PROUVE ({})".format(" et ".join(parts)))
    elif verdict_nuisible(sa, sb):
        out.append("VERDICT GLOBAL: NUISIBLE")
    else:
        out.append("VERDICT GLOBAL: NON PROUVE")
    return out


def report(runs_dir):
    chains = load_chains(runs_dir)
    stats = {cond: cond_stats(chains, cond) for cond in ("A", "B")}
    lines = ["# Rapport du banc", ""]
    lines.extend(section1(chains))
    lines.append("")
    lines.extend(section2(stats))
    lines.append("")
    lines.extend(section_incomplete(chains))
    lines.append("")
    lines.extend(section3(stats))
    lines.append("")
    lines.extend(verdict_lines(stats))
    print("\n".join(lines))
    return 0


def write_chain(runs_dir, name, cond, total, solved_factor, conformes):
    os.makedirs(os.path.join(runs_dir, name))
    lines = []
    for k in range(1, 6):
        slug = name + "_s" + str(k)
        modules = {}
        for i in range(4):
            mn = slug + "_m" + str(i + 1)
            modules[mn] = {"delivered": True, "t1": True, "t2": True, "t3": True, "t4": True, "ok": i < conformes}
        session = {
            "chain": name,
            "cond": cond,
            "k": k,
            "wall_s": 10.0 * k,
            "killed": False,
            "infra": False,
            "tokens": {"input": total // 2, "output": total - total // 2, "total": total, "turns": 10},
            "solved_session": solved_factor,
            "solved_cum": solved_factor * k,
            "tests_session": solved_factor,
            "tests_cum": solved_factor * k,
            "rules": {
                "modules": modules,
                "t5": {"tests_intact": True, "common_fail_ok": True},
                "summary": {"delivered": 4, "conformes": conformes},
            },
            "slugs": [slug],
        }
        lines.append(json.dumps(session))
    with open(os.path.join(runs_dir, name, "results.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def run_report(runs_dir):
    script = os.path.abspath(__file__)
    proc = subprocess.run([sys.executable, "-I", script, runs_dir], capture_output=True, text=True)
    return proc.stdout + proc.stderr, proc.returncode


def check(expected, out, code):
    found = expected in out
    passed = found and code == 0
    line = "{} attendu={} obtenu=code={} trouve={}".format(
        "PASS" if passed else "FAIL", expected, code, "oui" if found else "non")
    return passed, line


def run_autotest():
    base = tempfile.mkdtemp(prefix="report_autotest_")
    results = []
    try:
        d1 = os.path.join(base, "t1")
        for name, cond, total, sf, conf in [
            ("A1", "A", 200000, 2, 4),
            ("A2", "A", 200000, 2, 4),
            ("B1", "B", 100000, 2, 4),
            ("B2", "B", 100000, 2, 4),
        ]:
            write_chain(d1, name, cond, total, sf, conf)
        out, code = run_report(d1)
        results.append(check("VERDICT COUT: UTILE", out, code))

        d2 = os.path.join(base, "t2")
        for name, cond, total, sf, conf in [
            ("A1", "A", 200000, 2, 4),
            ("A2", "A", 200000, 2, 4),
            ("B1", "B", 300000, 1, 2),
            ("B2", "B", 300000, 1, 2),
        ]:
            write_chain(d2, name, cond, total, sf, conf)
        out, code = run_report(d2)
        results.append(check("VERDICT GLOBAL: NUISIBLE", out, code))

        d3 = os.path.join(base, "t3")
        write_chain(d3, "A1", "A", 200000, 2, 4)
        write_chain(d3, "B1", "B", 100000, 2, 4)
        out, code = run_report(d3)
        results.append(check("moins de deux repetitions", out, code))
    finally:
        shutil.rmtree(base)
    for passed, line in results:
        print(line)
    return 0 if all(p for p, _ in results) else 1


def main():
    args = sys.argv[1:]
    if args == ["--autotest"]:
        return run_autotest()
    if len(args) == 1:
        return report(args[0])
    print("usage: report.py RUNS_DIR | --autotest")
    return 2


if __name__ == "__main__":
    sys.exit(main())
