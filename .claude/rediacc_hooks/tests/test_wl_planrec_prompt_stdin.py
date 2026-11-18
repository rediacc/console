"""`wl_planrec.ask_why` sends its prompt on stdin: on argv a prompt past the kernel's argument limit fails to launch with E2BIG (`[Errno 7] Argument list too long`, 2026-11-18, the judge's four sites; this is the same shape at the plan-record call).

The model is a stub `claude` on PATH that records what reached its stdin and its argv. Control: a short prompt takes the same path.
"""

from __future__ import annotations

import json

import pytest

from rediacc_hooks.tests import wlfix

P = wlfix.import_wl("wl_planrec")

STUB = r"""#!/usr/bin/env python3
import json, os, sys
data = sys.stdin.read()
with open(os.environ["STUB_SEEN"], "w") as fh:
    json.dump({"stdin_len": len(data), "argv_max": max(len(a) for a in sys.argv), "argv": sys.argv[1:]}, fh)
print(json.dumps({"is_error": False, "structured_output": {"plan_record": {"ok": "yes"}}}))
"""


@pytest.fixture
def stub(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "claude"
    script.write_text(STUB, encoding="utf-8")
    script.chmod(0o755)
    seen = tmp_path / "seen.json"
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % bindir)
    monkeypatch.setenv("STUB_SEEN", str(seen))
    return seen


def test_control_a_short_prompt_arrives_on_stdin_and_not_on_argv(stub):
    fields, why = P.ask_why("PLAN BODY")
    assert fields == {"ok": "yes"}, why
    seen = json.loads(stub.read_text())
    assert seen["stdin_len"] > len("PLAN BODY")
    assert seen["argv_max"] < 10_000


def test_a_prompt_over_200_kb_reaches_the_model_through_the_real_launch_path(stub, monkeypatch):
    # plan_text is capped at 40000 characters, so the template carries the bulk here.
    monkeypatch.setattr(P, "WHY_PROMPT", "y" * 250_000 + "%(plan)s")
    fields, why = P.ask_why("PLAN BODY")
    assert fields == {"ok": "yes"}, why
    seen = json.loads(stub.read_text())
    assert seen["stdin_len"] == 250_000 + len("PLAN BODY")
    assert seen["argv_max"] < 10_000
