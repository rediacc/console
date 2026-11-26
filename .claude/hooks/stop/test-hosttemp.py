#!/usr/bin/env python3
"""Controls for the host-temp finished marker (agent/plans/PLAN-host-temp-disposal.md HT11, D6).

    python3 .claude/hooks/stop/test-hosttemp.py
    PYTHONPATH=.claude/hooks/stop python3 -m pytest -q .claude/hooks/stop/test-hosttemp.py -k marker

Every case works in its own temporary fixture repository and never touches a real path. Runs under pytest (the `test_` functions) and as a script (the `__main__` block runs each of them).
"""

import contextlib
import importlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
AGENT = "a0123456789abcdef"


def _check(cond):
    """A failed control: raised, so it fails under pytest and the script alike."""
    if not cond:
        raise AssertionError("control failed")


def _mod(name):
    """A hook module by name, with this directory on the path (the hooks import each other flat)."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    return importlib.import_module(name)


def _fixture(tmp, record=True):
    """A git repository whose common dir holds a lease record for AGENT (or none)."""
    root = pathlib.Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    records = root / ".git" / _mod("wl_worktrees").RECORD_DIR
    records.mkdir()
    if record:
        (records / ("agent-%s.json" % AGENT)).write_text(json.dumps({"id": "agent-" + AGENT}))
    return root, records


def _marker(records):
    return records / ("agent-%s.finished" % AGENT)


def test_marker_final_stop_writes_it():
    wt = _mod("wl_worktrees")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp)
        got = wt.mark_finished(root, AGENT, "/x/agent.jsonl", "", now=1000)
        body = json.loads(_marker(records).read_text())
        _check(got == str(_marker(records)))
        _check(body == {"agent": AGENT, "finished_at": 1000, "transcript": "/x/agent.jsonl"})
        wt.mark_finished(root, AGENT, "/x/agent.jsonl", "", now=2000)
        _check(json.loads(_marker(records).read_text())["finished_at"] == 2000)
        _check([p.name for p in records.iterdir() if p.suffix == ".tmp"] == [])


def test_marker_interim_stop_writes_none():
    wt = _mod("wl_worktrees")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp)
        _check(wt.mark_finished(root, AGENT, "/x/agent.jsonl", "Monitor armed") == "")
        _check(not _marker(records).exists())


def test_marker_agent_without_record_writes_none():
    wt = _mod("wl_worktrees")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp, record=False)
        _check(wt.mark_finished(root, AGENT, "/x/agent.jsonl", "") == "")
        _check(not _marker(records).exists())


def test_marker_unwritable_records_dir_raises_nothing():
    wt = _mod("wl_worktrees")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp)
        os.chmod(records, 0o500)
        try:
            if os.access(records, os.W_OK):  # running as root: the mode cannot deny it
                return
            _check(wt.mark_finished(root, AGENT, "/x/agent.jsonl", "") == "")
        finally:
            os.chmod(records, 0o700)


def test_marker_written_by_the_subagent_stop_handler():
    report = _mod("wl_report")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp)
        keys = ("CLAUDE_PROJECT_DIR", "WORKLIST_REPORTS_DIR")
        saved = {k: os.environ.get(k) for k in keys}
        os.environ["CLAUDE_PROJECT_DIR"] = str(root)
        os.environ["WORKLIST_REPORTS_DIR"] = str(pathlib.Path(tmp) / "reports")
        real = report.armed_monitors
        try:
            event = {"agent_id": AGENT, "last_assistant_message": "done", "session_id": "s" * 8}
            report.handle_subagent_stop(event)
            _check(_marker(records).is_file())
            # an armed Monitor makes the stop interim: the rewrite must not happen
            _marker(records).unlink()
            transcript = pathlib.Path(tmp) / "agent.jsonl"
            transcript.write_text("{}\n")
            report.armed_monitors = lambda *_a, **_k: ["Monitor until x"]
            report.handle_subagent_stop({**event, "agent_transcript_path": str(transcript)})
            _check(not _marker(records).exists())
        finally:
            report.armed_monitors = real
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:  # report every failing case, then exit 1
                failed += 1
                print("FAIL %s: %r" % (name, exc))
            else:
                print("ok   %s" % name)
    with contextlib.suppress(BrokenPipeError):
        sys.stdout.flush()
    sys.exit(1 if failed else 0)
