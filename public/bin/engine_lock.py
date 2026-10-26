import sys
import os
import re
import time
import fcntl
import tempfile
import shutil
import subprocess
import importlib.util

USAGE = "usage: engine_lock.py --status NAME --slots N [--dir DIR] | --notice | --autotest"

NOTICE = """NAME      engine_lock.py - lets at most N delegations run at once on one engine, with kernel file locks freed when their holder dies.
READS     --dir, else FRUGALFLOW_HOME/locks, else ~/.frugalflow/locks: one lock file per slot.
WRITES    empty slot files; --status prints how many slots are busy (0); bad arguments give 2.
EXAMPLE   python3 engine_lock.py --status model-a --slots 2
PITFALLS  2026-08-23 two delegations shared one engine and the measure was false; a slot is now required before sending.
          A lock held by a dead process never blocks: the kernel frees it."""

def default_dir():
    if "FRUGALFLOW_HOME" in os.environ:
        return os.path.join(os.environ["FRUGALFLOW_HOME"], "locks")
    else:
        return os.path.join(os.path.expanduser("~"), ".frugalflow", "locks")

def safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(name))

def try_slots(name, slots, lock_dir):
    os.makedirs(lock_dir, exist_ok=True)
    for i in range(slots):
        path = os.path.join(lock_dir, safe(name) + ".slot" + str(i) + ".lock")
        try:
            f = open(path, "a")
        except OSError:
            continue
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            f.close()
            continue
    return None

def acquire(name, slots, lock_dir=None, wait=0.0, poll=0.1):
    if lock_dir is None:
        lock_dir = default_dir()
    if not isinstance(slots, int) or slots < 1:
        slots = 1
    start = time.monotonic()
    while True:
        h = try_slots(name, slots, lock_dir)
        if h is not None:
            return h
        if time.monotonic() >= start + wait:
            return None
        time.sleep(poll)

def release(handle):
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
    except OSError:
        pass

def busy(name, slots, lock_dir=None):
    if lock_dir is None:
        lock_dir = default_dir()
    os.makedirs(lock_dir, exist_ok=True)
    count = 0
    for i in range(slots):
        path = os.path.join(lock_dir, safe(name) + ".slot" + str(i) + ".lock")
        try:
            f = open(path, "a")
        except OSError:
            continue
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            count += 1
        finally:
            f.close()
    return count

def autotest():
    D = tempfile.mkdtemp()
    ok = True
    a_global = None
    try:
        # Test 1
        a = None
        b = None
        ep1_passed = False
        try:
            a = acquire("alpha-7b", 1, D)
            if a is None:
                print("FAIL 1: acquire returned None (expected non None)")
                ok = False
            else:
                a_global = a
                b = acquire("alpha-7b", 1, D, wait=0.3)
                busy1 = busy("alpha-7b", 1, D)
                if b is not None or busy1 != 1:
                    print(f"FAIL 1: expected b=None and busy=1, got b={'not None' if b is not None else 'None'}, busy={busy1}")
                    ok = False
                else:
                    print("PASS 1: a non None, b None, busy 1")
                    ep1_passed = True
        except Exception as e:
            print(f"FAIL 1: exception {e!r}")
            ok = False
        finally:
            if not ep1_passed:
                if b is not None:
                    release(b)
                if a_global is not None:
                    release(a_global)
                    a_global = None

        # Test 2
        c = None
        d = None
        e = None
        try:
            if a_global is not None:
                release(a_global)
                a_global = None
            c = acquire("alpha-7b", 2, D)
            if c is None:
                print("FAIL 2: first acquire returned None")
                ok = False
            else:
                d = acquire("alpha-7b", 2, D)
                if d is None:
                    print("FAIL 2: second acquire returned None")
                    ok = False
                else:
                    e = acquire("alpha-7b", 2, D, wait=0.3)
                    if e is not None:
                        print("FAIL 2: e expected None, got non None")
                        ok = False
                    else:
                        print("PASS 2: c and d acquired, e None")
        except Exception as e:
            print(f"FAIL 2: exception {e!r}")
            ok = False
        finally:
            if c is not None:
                release(c)
            if d is not None:
                release(d)
            if e is not None:
                release(e)

        # Test 3
        try:
            busy3 = busy("alpha-7b", 2, D)
            safe_val = safe("org/model:7b")
            release(None)
            if busy3 != 0 or safe_val != "org_model_7b":
                print(f"FAIL 3: expected busy=0 and safe='org_model_7b', got busy={busy3}, safe={safe_val!r}")
                ok = False
            else:
                print("PASS 3: busy 0, safe ok")
        except Exception as e:
            print(f"FAIL 3: exception {e!r}")
            ok = False

        # Test 4
        try:
            # To make sure the file is reachable, the script is copied into D
            script_copy = os.path.join(D, "engine_lock_copy.py")
            shutil.copy(__file__, script_copy)

            CODE = ("import sys, importlib.util\n"
                    "_s = importlib.util.spec_from_file_location('el', %r)\n"
                    "M = importlib.util.module_from_spec(_s)\n"
                    "_s.loader.exec_module(M)\n"
                    "h = M.acquire('alpha-7b', 1, %r)\n"
                    "import os\n"
                    "os._exit(0 if h is not None else 3)\n") % (script_copy, D)

            proc = subprocess.run([sys.executable, "-c", CODE],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  timeout=20)
            if proc.returncode != 0:
                stderr_repr = repr(proc.stderr.decode('utf-8', errors='replace')).replace('\n', '\\n')
                print(f"FAIL 4: subprocess returncode={proc.returncode}, stderr={stderr_repr}, expected 0")
                ok = False
            else:
                f = acquire("alpha-7b", 1, D)
                if f is None:
                    print("FAIL 4: acquire after subprocess death returned None, expected non None")
                    ok = False
                else:
                    print("PASS 4: subprocess death freed lock, acquire succeeded")
                    release(f)
        except subprocess.TimeoutExpired:
            print("FAIL 4: subprocess timed out")
            ok = False
        except Exception as e:
            print(f"FAIL 4: exception {e!r}")
            ok = False

        # Test 5
        g = None
        ep5_fail_messages = []
        try:
            g = acquire("alpha-7b", 2, D)
            if g is None:
                ep5_fail_messages.append("first acquire returned None")
            proc1 = subprocess.run([sys.executable, os.path.abspath(__file__), "--status", "alpha-7b", "--slots", "2", "--dir", D],
                                   capture_output=True, text=True, timeout=20)
            expected_out = "LOCK alpha-7b: 1 of 2 slots busy"
            if proc1.returncode != 0 or proc1.stdout.strip() != expected_out:
                ep5_fail_messages.append(f"status: code={proc1.returncode}, stdout={proc1.stdout.strip()!r}, expected code=0, stdout={expected_out!r}")
            proc2 = subprocess.run([sys.executable, os.path.abspath(__file__), "--status", "alpha-7b", "--slots", "zero"],
                                   capture_output=True, text=True, timeout=20)
            if proc2.returncode != 2:
                ep5_fail_messages.append(f"invalid slots: code={proc2.returncode}, expected 2")
            if ep5_fail_messages:
                print("FAIL 5: " + "; ".join(ep5_fail_messages))
                ok = False
            else:
                print("PASS 5: status showed 1 busy, invalid slots gave 2")
        except subprocess.TimeoutExpired:
            print("FAIL 5: subprocess timed out")
            ok = False
        except Exception as e:
            print(f"FAIL 5: exception {e!r}")
            ok = False
        finally:
            if g is not None:
                release(g)
    finally:
        shutil.rmtree(D, ignore_errors=True)
    return 0 if ok else 1

def main():
    args = sys.argv[1:]
    if "--notice" in args:
        sys.stdout.write(NOTICE)
        return 0
    if "--autotest" in args:
        return autotest()
    if "--status" in args and "--slots" in args:
        try:
            status_idx = args.index("--status")
            name = args[status_idx + 1]
        except IndexError:
            print(USAGE)
            return 2
        try:
            slots_idx = args.index("--slots")
            slots_str = args[slots_idx + 1]
            slots = int(slots_str)
        except (IndexError, ValueError):
            print(USAGE)
            return 2
        if slots < 1:
            print(USAGE)
            return 2
        lock_dir = None
        if "--dir" in args:
            try:
                dir_idx = args.index("--dir")
                lock_dir = args[dir_idx + 1]
            except IndexError:
                print(USAGE)
                return 2
        b = busy(name, slots, lock_dir)
        print("LOCK " + name + ": " + str(b) + " of " + str(slots) + " slots busy")
        return 0
    else:
        print(USAGE)
        return 2

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "engine_lock", sys.argv[1:])
