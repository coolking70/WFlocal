#!/usr/bin/env python3
"""Check the Hub's edit path end to end, then put the file back.

    python3 tools/verify_edit.py

This is the only part of WFMod that writes data on a request from the browser,
so it gets checked the way a writer should be: apply a real edit, prove the file
changed exactly where it was meant to, apply the original value back, and prove
the file is byte-identical to how it started. If that last step ever fails,
editing is lossy and the tooling has a bug worth more than the feature.

Also checks that the requests which must be refused are refused - an edit
outside the fork directory, a bad command name, a value that is not JSON.

And it drives the dev server over HTTP, because the first version of this feature
shipped with a working writer behind a route nobody had ever called: the endpoint
was fine and the browser could not save. Testing apply() alone would not have
caught that, and neither would testing the page.
"""

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_edit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROGRAM = "battle/action/skill/action/wfmod/wfmod_001$wfmod_001_1"
TARGET = ROOT / "WFTest" / "assets" / "production" / (PROGRAM + ".action.dsl.json")

failures = 0


def check(ok, what):
    global failures
    print(f"  {'ok  ' if ok else 'BAD '} {what}")
    if not ok:
        failures += 1


def value_of(command, param):
    reference = json.loads((ROOT / "WFTest" / "wfmod" / "dsl-reference.json")
                           .read_text(encoding="utf-8"))
    fields = reference["commands"][command]["params"]
    found = []

    def walk(node):
        if isinstance(node, list):
            if len(node) == 2 and node[0] == "Command" and isinstance(node[1], list) \
                    and node[1] and node[1][0] == command:
                found.append(node[1])
            for item in node:
                walk(item)

    walk(json.loads(TARGET.read_text(encoding="utf-8")))
    if not found:
        sys.exit(f"{PROGRAM} has no {command}")
    return found[0][fields.index(param) + 1]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def request(port, payload):
    """(status, body) for a POST to the edit endpoint."""
    url = f"http://127.0.0.1:{port}/wfmod/api/edit"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def http_checks(before, original):
    """The same edit again, but through the route the browser actually uses."""
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, str(ROOT / "run_server_nocache.py"),
         "--port", str(port), "--no-open"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/wfmod/api/edit", timeout=1) as probe:
                    ready = json.loads(probe.read())
                break
            except Exception:
                time.sleep(0.1)
        else:
            check(False, "the dev server started")
            return

        check(ready.get("ready") is True,
              "GET on the endpoint reports editing is available")

        status, body = request(port, {
            "program": PROGRAM, "command": "CreateNormalAttack",
            "param": "damage", "value": "4321"})
        check(status == 200 and body.get("ok"), "POST writes an edit")
        check(value_of("CreateNormalAttack", "damage") == 4321,
              "the value the POST asked for is in the file")

        status, body = request(port, {
            "program": PROGRAM, "command": "CreateNormalAttack",
            "param": "damage", "value": json.dumps(original)})
        check(status == 200, "POST writes the original value back")
        check(TARGET.read_bytes() == before,
              "the file is byte-identical after the HTTP round trip")

        status, body = request(port, {
            "program": "battle/action/skill/action/rare5/brown_fighter$brown_fighter_1",
            "command": "CreateNormalAttack", "param": "damage", "value": "1"})
        check(status == 400 and "error" in body,
              "POST refuses a shipped skill, with a reason")
        check(TARGET.read_bytes() == before, "the refused POST touched nothing")
    finally:
        server.terminate()
        server.wait(timeout=10)


def main():
    if not TARGET.exists():
        sys.exit(f"{TARGET.relative_to(ROOT)} does not exist; "
                 f"run tools/fork_skill.py first")

    before = TARGET.read_bytes()
    original = value_of("CreateNormalAttack", "damage")
    print(f"file    {TARGET.relative_to(ROOT)}")
    print(f"damage  {original}\n")

    apply_edit.apply(PROGRAM, "CreateNormalAttack", "damage", "1234")
    check(value_of("CreateNormalAttack", "damage") == 1234, "an edit is written")
    check(TARGET.read_bytes() != before, "the file on disk changed")

    apply_edit.apply(PROGRAM, "CreateNormalAttack", "damage", json.dumps(original))
    check(value_of("CreateNormalAttack", "damage") == original, "the original value is restored")
    check(TARGET.read_bytes() == before,
          "the file is byte-identical after the round trip")

    refusals = [
        (("battle/action/skill/action/rare5/brown_fighter$brown_fighter_1",
          "CreateNormalAttack", "damage", "1"), "a shipped skill outside the fork directory"),
        ((PROGRAM, "../../etc/passwd", "damage", "1"), "a command name that is not a name"),
        ((PROGRAM, "CreateNormalAttack", "damage", "not json"), "a value that is not JSON"),
        (("../../../etc/passwd", "CreateNormalAttack", "damage", "1"), "a path escaping the tree"),
    ]
    for args, what in refusals:
        try:
            apply_edit.apply(*args)
            check(False, f"refuses {what}")
        except apply_edit.EditError:
            check(True, f"refuses {what}")

    check(TARGET.read_bytes() == before, "no refused request touched the file")

    print("")
    http_checks(before, original)

    print("")
    if failures:
        print(f"{failures} problem(s) found")
        return 1
    print("the edit path writes, restores byte-identically, and refuses the rest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
