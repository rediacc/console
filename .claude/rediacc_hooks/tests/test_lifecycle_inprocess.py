"""Advisory lifecycle members run in-process (agent/plans/PLAN-tooling-speed.md SP4, design D5).

Every Bash call started about 16 Python processes: one runner per PostToolUse pattern, plus one per post-bash (8) and post-tool (4) member. lifecycle.run_inprocess now calls those advisors in the runner's own interpreter, with a per-member deadline and crash isolation.

HOW THE PROCESSES ARE COUNTED. A `sitecustomize.py` put first on PYTHONPATH appends one line per Python interpreter that starts, read from /proc/self/cmdline, and PYTHONPATH reaches every child the harness commands start. The three harness commands one Bash call runs (pre-bash, post-bash, post-tool, as `lifecycle.entry_command` spells them) are driven with a fixture payload against this checkout.

EVERY POSITIVE HAS ITS CONTROL: with REDIACC_HOOK_INPROCESS=off the same call starts the old count (the counter is not blind), a member that raises is named while the others still run, a member past its deadline is cut while the others still run, and a member marked `process` keeps its process.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING

import pytest

from rediacc_hooks import lifecycle

if TYPE_CHECKING:
    import pathlib

REPO = lifecycle.repo_root()
BASELINE = REPO / ".ci" / "policy" / "hook-exec-baseline.json"
BASH_CALL = ("pre-bash", "post-bash", "post-tool")

SITECUSTOMIZE = textwrap.dedent(
    """
    import os
    _log = os.environ.get("LIFECYCLE_PROC_LOG")
    if _log:
        try:
            with open("/proc/self/cmdline", "rb") as _fh:
                _argv = [a.decode("utf-8", "replace") for a in _fh.read().split(b"\\0") if a]
        except OSError:
            _argv = ["?"]
        _fd = os.open(_log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        os.write(_fd, (" ".join(os.path.basename(a) for a in _argv[:3]) + "\\n").encode())
        os.close(_fd)
    """
)


def payload(event: str) -> str:
    doc = {
        "session_id": "deadbeef-1111-2222-3333-444444444444",
        "transcript_path": "/nonexistent/t.jsonl",
        "cwd": str(REPO),
        "hook_event_name": event,
        "tool_name": "Bash",
        "tool_input": {"command": "ls", "description": "List files"},
    }
    if event == "PostToolUse":
        doc["tool_response"] = {"stdout": "a\n", "stderr": "", "interrupted": False}
    return json.dumps(doc)


def count_bash_call(tmp_path: pathlib.Path, extra: dict | None = None) -> dict[str, list[str]]:
    """{pattern key: [one line per Python interpreter started]} for one fixture Bash call."""
    site = tmp_path / "site"
    site.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    state = tmp_path / "tmp"
    state.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("WORKLIST_", "CLAUDE_"))}
    env.update(
        {
            "CLAUDE_PROJECT_DIR": str(REPO),
            "PYTHONPATH": str(site),
            "TMPDIR": str(state),
            "WORKLIST_PROFILE": "off",
            "WORKLIST_SESSION_ID": "deadbeef-1111-2222-3333-444444444444",
        }
    )
    env.pop("REDIACC_HOOK_INPROCESS", None)
    env.update(extra or {})
    seen = {}
    for key in BASH_CALL:
        log = tmp_path / ("%s.log" % key)
        if log.exists():
            log.unlink()
        env["LIFECYCLE_PROC_LOG"] = str(log)
        argv = shlex.split(lifecycle.entry_command(key).replace("$CLAUDE_PROJECT_DIR", str(REPO)))
        event = lifecycle.PATTERNS[key]["event"]
        proc = subprocess.run(
            argv,
            input=payload(event),
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO),
            timeout=lifecycle.entry_timeout(key),
            check=False,
        )
        assert proc.returncode in (0, 1), (key, proc.returncode, proc.stderr[-800:])
        seen[key] = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return seen


@pytest.fixture(scope="module")
def counted(tmp_path_factory):
    on = count_bash_call(tmp_path_factory.mktemp("on"))
    off = count_bash_call(tmp_path_factory.mktemp("off"), {"REDIACC_HOOK_INPROCESS": "off"})
    return on, off


def test_one_bash_call_starts_at_most_four_python_processes(counted):
    on, _off = counted
    total = sum(len(v) for v in on.values())
    # ZERO would mean the counter is blind (no sitecustomize loaded), not that the call is free.
    assert total >= len(BASH_CALL), on
    assert total <= 4, on


def test_the_counter_sees_the_old_fan_out_with_in_process_off(counted):
    """CONTROL: REDIACC_HOOK_INPROCESS=off runs every member as its own process again, and the same counter then sees about 16."""
    on, off = counted
    assert sum(len(v) for v in off.values()) >= 12, off
    assert len(off["post-bash"]) > len(on["post-bash"]), (on, off)
    assert len(off["post-tool"]) > len(on["post-tool"]), (on, off)


def test_the_baseline_pins_the_measured_per_call_count(counted):
    """`.ci/policy/hook-exec-baseline.json` `perCall` carries the true per-call Python count, lifecycle fan-out included; a count that moves either way fails here until the record is edited."""
    on, _off = counted
    pinned = json.loads(BASELINE.read_text(encoding="utf-8"))["perCall"]
    assert pinned["tool"] == "Bash"
    live = {key: len(on[key]) for key in BASH_CALL}
    live["total"] = sum(live.values())
    assert pinned["pythonProcesses"] == live, (pinned["pythonProcesses"], live)


# ---- the runner, in this interpreter ----------------------------------------


def script(tmp_path, name, body, sibling=None):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    if sibling is not None:
        (d / "helper.py").write_text(sibling, encoding="utf-8")
    p = d / "member.py"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return {"command": "python3 %s" % p, "timeout": 5}


def run(members, payload_text="{}"):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(REPO))
    return lifecycle.run_pattern("post-bash", payload_text, env=env, members=members)


def test_a_member_that_raises_is_named_and_the_others_still_run(tmp_path):
    boom = script(tmp_path, "boom", "raise RuntimeError('planted failure')\n")
    fine = script(tmp_path, "fine", "print('still ran')\n")
    rc, out, err = run([boom, fine])
    assert rc == 1
    assert "still ran" in out
    assert "RuntimeError: planted failure" in err
    assert "HOOK MEMBER RAISED" in err
    assert boom["command"] in err


def test_a_member_past_its_deadline_is_cut_and_the_others_still_run(tmp_path):
    slow = script(tmp_path, "slow", "import time\ntime.sleep(30)\n")
    slow["timeout"] = 1
    fine = script(tmp_path, "fine", "print('after the hang')\n")
    rc, out, err = run([slow, fine])
    assert rc == 1
    assert "TIMED OUT after 1s" in err
    assert "after the hang" in out


def test_exit_two_still_stops_the_pattern(tmp_path):
    block = script(
        tmp_path, "block", "import sys\nprint('refused', file=sys.stderr)\nsys.exit(2)\n"
    )
    never = script(tmp_path, "never", "print('must not run')\n")
    rc, out, err = run([block, never])
    assert rc == 2
    assert "refused" in err
    assert "must not run" not in out


def test_a_member_reads_its_payload_and_writes_bytes(tmp_path):
    member = script(
        tmp_path,
        "io",
        """
        import json, sys
        doc = json.loads(sys.stdin.buffer.read())
        sys.stdout.buffer.write(("tool=%s\\n" % doc["tool_name"]).encode())
        print("argv0=" + sys.argv[0].rsplit("/", 1)[-1])
        """,
    )
    rc, out, _err = run([member], payload("PostToolUse"))
    assert rc == 0
    assert "tool=Bash" in out
    assert "argv0=member.py" in out


def test_state_a_member_changes_is_put_back(tmp_path):
    """Environment, working directory, sys.path and a same-named sibling module: the second member sees none of what the first changed."""
    first = script(
        tmp_path,
        "first",
        """
        import os, sys
        import helper
        os.environ["LEAKED_BY_MEMBER"] = "1"
        os.chdir("/")
        sys.path.append("/leaked")
        print("first:" + helper.NAME)
        """,
        sibling="NAME = 'first-helper'\n",
    )
    second = script(
        tmp_path,
        "second",
        """
        import os, sys
        import helper
        print("second:" + helper.NAME)
        print("env:" + os.environ.get("LEAKED_BY_MEMBER", "clean"))
        print("path:" + ("leaked" if "/leaked" in sys.path else "clean"))
        """,
        sibling="NAME = 'second-helper'\n",
    )
    cwd = os.getcwd()
    rc, out, _err = run([first, second])
    assert rc == 0, out
    assert "first:first-helper" in out
    assert "second:second-helper" in out
    assert "env:clean" in out
    assert "path:clean" in out
    assert os.getcwd() == cwd
    assert "LEAKED_BY_MEMBER" not in os.environ


def test_a_member_marked_process_keeps_its_process(tmp_path, monkeypatch):
    member = script(tmp_path, "proc", "import os\nprint('pid=%d' % os.getpid())\n")
    member["process"] = "planted: the control for the marker"
    rc, out, _err = run([member])
    assert rc == 0
    assert "pid=%d" % os.getpid() not in out
    inproc = script(tmp_path, "inproc", "import os\nprint('pid=%d' % os.getpid())\n")
    rc, out, _err = run([inproc])
    assert "pid=%d" % os.getpid() in out
    monkeypatch.setenv("REDIACC_HOOK_INPROCESS", "off")
    rc, out, _err = run([inproc])
    assert "pid=%d" % os.getpid() not in out


def test_the_marker_never_reaches_the_flattened_wiring():
    """`process` and `inprocess` are this runner's notes; the settings-facing view carries command and timeout only."""
    for key in lifecycle.PATTERNS:
        for member in lifecycle.flat_commands(key):
            assert set(member) <= set(lifecycle.WIRING_KEYS), (key, member)


def test_only_the_advisory_patterns_run_in_process():
    assert {k for k, p in lifecycle.PATTERNS.items() if p.get("inprocess")} == {
        "post-bash",
        "post-tool",
    }
    blocking = lifecycle.PATTERNS["pre-bash"]["members"][0]
    assert (
        lifecycle.inprocess_script("pre-bash", blocking, {"CLAUDE_PROJECT_DIR": str(REPO)}) is None
    )


def test_a_shell_member_keeps_its_process():
    member = {"command": "echo hi | cat"}
    assert lifecycle.inprocess_script("post-bash", member, {}) is None


def test_the_lifecycle_module_imports_without_running(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, %r); from rediacc_hooks import lifecycle; print(len(lifecycle.PATTERNS))"
            % str(REPO / ".claude"),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(tmp_path),
    )
    assert int(proc.stdout) >= 2
