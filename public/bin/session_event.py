import json
import hashlib
import sys
import subprocess

INPUT_LIMIT = 20000
RESPONSE_LIMIT = 4000

NOTICE = """NAME      session_event.py - turns what a Claude Code hook receives into one session log entry, and reads back what the assistant wrote since the last human message.
READS     nothing: pure module; the caller passes the hook payload, the time, the vault and the transcript lines.
WRITES    nothing: build() returns the entry, before it is sealed.
EXAMPLE   python3 session_event.py --notice
PITFALLS  2026-09-19 a tool result is sent to the model as a user message: it is not a human message, and never resets the turn.
          A long tool input is cut, but its sha256 is taken on the whole input.
"""

USAGE = "usage: session_event.py --notice | --autotest"


def texts_since_last_human(transcript_lines):
    records = []
    for line in transcript_lines:
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(parsed, dict):
            continue
        records.append(parsed)

    last_human = -1
    for idx, rec in enumerate(records):
        if rec.get("type") != "user":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            last_human = idx
        elif isinstance(content, list):
            is_human = True
            for element in content:
                if isinstance(element, dict) and element.get("type") == "tool_result":
                    is_human = False
                    break
            if is_human:
                last_human = idx

    texts = []
    for idx in range(last_human + 1, len(records)):
        rec = records[idx]
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, list):
            for element in content:
                if isinstance(element, dict) and element.get("type") == "text":
                    texts.append(element.get("text", ""))
    return texts


def build(payload, now, vault, transcript_lines):
    entry = {
        "ts": now,
        "session": payload.get("session_id", ""),
        "cwd": payload.get("cwd", ""),
        "vault": vault,
    }
    name = payload.get("hook_event_name", "")

    if name == "UserPromptSubmit":
        entry["event"] = "prompt"
        entry["text"] = payload.get("prompt", "")
    elif name == "PreToolUse":
        entry["event"] = "tool_before"
        entry["tool"] = payload.get("tool_name", "")
        entry["id"] = payload.get("tool_use_id", "")
        full = json.dumps(payload.get("tool_input", {}), ensure_ascii=False)
        entry["input"] = full[:INPUT_LIMIT]
        entry["input_sha256"] = hashlib.sha256(full.encode("utf-8")).hexdigest()
    elif name == "PostToolUse":
        entry["event"] = "tool_after"
        entry["tool"] = payload.get("tool_name", "")
        entry["id"] = payload.get("tool_use_id", "")
        response = payload.get("tool_response", "")
        if not isinstance(response, str):
            response = json.dumps(response, ensure_ascii=False)
        entry["response"] = response[:RESPONSE_LIMIT]
    elif name == "Stop":
        entry["event"] = "stop"
        entry["texts"] = texts_since_last_human(transcript_lines)
    elif name == "SessionStart":
        entry["event"] = "start"
        entry["source"] = payload.get("source", "")
    elif name == "SessionEnd":
        entry["event"] = "end"
        entry["reason"] = payload.get("reason", "")
    else:
        entry["event"] = name

    return entry


def _autotest():
    NOW = "2026-09-26T10:00:00+02:00"
    BASE = {"session_id": "s1", "cwd": "/w"}
    TRANSCRIPT = [
        json.dumps({"type": "user", "message": {"content": "first question"}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "old answer"}]}}),
        json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "second question"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}, {"type": "tool_use", "id": "t1"}]}}),
        "",
        "not json",
        json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}),
    ]
    LONG = {"command": "x" * 30000}

    all_pass = True

    # Test 1
    expected_1 = ["working", "done"]
    got_1 = texts_since_last_human(TRANSCRIPT)
    expected_1b = []
    got_1b = texts_since_last_human([])
    expected_1c = ["old answer"]
    got_1c = texts_since_last_human(TRANSCRIPT[:2])
    if got_1 == expected_1 and got_1b == expected_1b and got_1c == expected_1c:
        print("PASS 1: texts_since_last_human")
    else:
        print(f"FAIL 1: expected={expected_1} got={got_1} expected_empty={expected_1b} got_empty={got_1b} expected_prefix={expected_1c} got_prefix={got_1c}")
        all_pass = False

    # Test 2
    expected_2 = {"ts": NOW, "session": "s1", "cwd": "/w", "vault": "/w/vault", "event": "prompt", "text": "fix it"}
    got_2 = build(dict(BASE, hook_event_name="UserPromptSubmit", prompt="fix it"), NOW, "/w/vault", [])
    if got_2 == expected_2:
        print("PASS 2: build UserPromptSubmit")
    else:
        print(f"FAIL 2: expected={expected_2} got={got_2}")
        all_pass = False

    # Test 3
    entry_3 = build(
        dict(BASE, hook_event_name="PreToolUse", tool_name="Bash", tool_use_id="t9", tool_input=LONG),
        NOW, "", []
    )
    expected_sha = hashlib.sha256(json.dumps(LONG, ensure_ascii=False).encode("utf-8")).hexdigest()
    if (
        isinstance(entry_3, dict)
        and entry_3.get("event") == "tool_before"
        and entry_3.get("tool") == "Bash"
        and entry_3.get("id") == "t9"
        and len(entry_3.get("input", "")) == 20000
        and entry_3.get("input_sha256") == expected_sha
    ):
        print("PASS 3: build PreToolUse")
    else:
        print(f"FAIL 3: expected event=tool_before tool=Bash id=t9 input_len=20000 sha256={expected_sha} got={entry_3}")
        all_pass = False

    # Test 4
    after_4 = build(
        dict(BASE, hook_event_name="PostToolUse", tool_name="Bash", tool_use_id="t9", tool_response={"stdout": "ok"}),
        NOW, "", []
    )
    stop_4 = build(dict(BASE, hook_event_name="Stop"), NOW, "", TRANSCRIPT)
    start_4 = build(dict(BASE, hook_event_name="SessionStart", source="clear"), NOW, "", [])
    end_4 = build(dict(BASE, hook_event_name="SessionEnd", reason="exit"), NOW, "", [])
    notif_4 = build(dict(BASE, hook_event_name="Notification"), NOW, "", [])
    if (
        after_4.get("event") == "tool_after"
        and after_4.get("response") == '{"stdout": "ok"}'
        and stop_4.get("texts") == ["working", "done"]
        and start_4.get("source") == "clear"
        and end_4.get("event") == "end"
        and notif_4.get("event") == "Notification"
    ):
        print("PASS 4: build PostToolUse/Stop/SessionStart/SessionEnd/Notification")
    else:
        print(
            f"FAIL 4: expected tool_after response='{{\"stdout\": \"ok\"}}' texts=['working','done'] source=clear end=Notification "
            f"got after={after_4} stop={stop_4} start={start_4} end={end_4} notif={notif_4}"
        )
        all_pass = False

    # Test 5
    proc_notice = subprocess.run([sys.executable, __file__, "--notice"], capture_output=True, text=True)
    proc_bogus = subprocess.run([sys.executable, __file__, "--bogus"], capture_output=True, text=True)
    if (
        proc_notice.returncode == 0
        and proc_notice.stdout.startswith("NAME      session_event.py")
        and proc_bogus.returncode == 2
        and "usage: session_event.py" in proc_bogus.stdout
    ):
        print("PASS 5: subprocess --notice rc=0 and --bogus rc=2")
    else:
        print(
            f"FAIL 5: expected notice_rc=0 starts_with='NAME      session_event.py' bogus_rc=2 contains='usage: session_event.py' "
            f"got notice_rc={proc_notice.returncode} notice_head={proc_notice.stdout[:50]!r} bogus_rc={proc_bogus.returncode} bogus_head={proc_bogus.stdout[:50]!r}"
        )
        all_pass = False

    return 0 if all_pass else 1


def main():
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(2)
    arg = sys.argv[1]
    if arg == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif arg == "--autotest":
        sys.exit(_autotest())
    else:
        print(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "session_event", sys.argv[1:])
