"""`claude_reviewer` sends its prompt on stdin: on argv a prompt past the kernel's argument limit fails to launch with E2BIG (`[Errno 7] Argument list too long`, 2026-11-18, the judge's four sites; this is the same shape at the per-commit reviewer).

The model is a stub `claude` on PATH that records what reached its stdin and its argv. Control: a short prompt takes the same path, and a call that puts the prompt back on argv fails with E2BIG here.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")
wl_proc = wlfix.import_wl("wl_proc")

STUB = r"""#!/usr/bin/env python3
import json, os, sys
data = sys.stdin.read()
with open(os.environ["STUB_SEEN"], "w") as fh:
    json.dump({"stdin_len": len(data), "argv_max": max(len(a) for a in sys.argv), "argv": sys.argv[1:]}, fh)
print(json.dumps({"is_error": False, "total_cost_usd": 0.0, "structured_output": {"ok": True}}))
"""

CFG = {"model": "stub-model", "budget_usd": "1", "timeout_s": 60}


@pytest.fixture
def stub(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "claude"
    script.write_text(STUB, encoding="utf-8")
    script.chmod(0o755)
    seen = tmp_path / "seen.json"
    monkeypatch.setenv(
        "PATH", "%s:%s:/usr/bin:/bin" % (bindir, pathlib.Path(sys.executable).parent)
    )
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("STUB_SEEN", str(seen))
    return seen


def test_control_a_short_prompt_arrives_on_stdin_and_not_on_argv(stub):
    out, why, _cost = R.claude_reviewer("SHORT PROMPT", CFG, log=lambda *_a: None)
    assert out == {"ok": True}, why
    seen = json.loads(stub.read_text())
    assert seen["stdin_len"] == len("SHORT PROMPT")
    assert "SHORT PROMPT" not in seen["argv"]


def test_a_prompt_over_200_kb_reaches_the_reviewer_through_the_real_launch_path(stub):
    prompt = "x" * 250_000
    out, why, _cost = R.claude_reviewer(prompt, CFG, log=lambda *_a: None)
    assert out == {"ok": True}, why
    seen = json.loads(stub.read_text())
    assert seen["stdin_len"] == len(prompt)
    assert seen["argv_max"] < 10_000


@pytest.mark.usefixtures("stub")
def test_control_the_same_prompt_on_argv_fails_with_e2big():
    exe = R.resolve_claude()
    proc = wl_proc.run([exe, "-p", "x" * 250_000], timeout=30)
    assert proc.returncode == wl_proc.SPAWN_FAILED_RC
    assert "Argument list too long" in (proc.stderr or "")
