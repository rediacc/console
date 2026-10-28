"""block_settled_questions reads a CLI verb that ends in `push` as a CLI verb, not the git act (#24fa4d53).

The measured false positive, 2026-10-28T13:27Z: a question about keeping `rdc machine access set` and `rdc machine access push` out of MCP was refused as a push-timing ask, because `push` sat inside the rdc command name and `already` followed the second one. Each payload runs through the real dispatcher in a subprocess, with HOME and TMPDIR pointed at a fresh directory so a
refusal's ledger row never lands in this machine's live ledger. Both directions are asserted: the rdc questions pass, and the genuine push-timing and permission spellings beside them are still refused, including `git push` and `gh pr create` written in backticks.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
DISPATCH = HOOKS / "dispatch.py"
STEM = "block_settled_questions"

# The question that was refused, as the ledger recorded it (lowercased there; the casing does not matter to the guard).
MEASURED = (
    "Should the new `rdc machine access set` and `rdc machine access push` be kept out of MCP, "
    "the tool surface AI agents call, the way `machine infra set|push` already are by the "
    "earlier ruling? They change which source addresses may log in to a machine over SSH."
)

PASS = [
    ("the measured rdc question", MEASURED, "MCP access"),
    (
        "a permission shape over a backticked rdc verb",
        "Should we bar `rdc machine access push` from MCP?",
        "",
    ),
    ("an unquoted rdc verb", "Should rdc machine access push be barred from MCP now?", ""),
    (
        "a backticked infra push with a time word",
        "Is `rdc machine infra push` already excluded?",
        "",
    ),
]

REFUSE = [
    ("push timing: push now", "Push now?", "", "decided by the hooks"),
    ("push timing: ready to push", "Ready to push?", "", "decided by the hooks"),
    (
        "push timing: the turbo batch",
        "How should a finished turbo batch push?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: git push in backticks",
        "Should I run `git push` now?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: gh pr create in backticks",
        "When should I run `gh pr create`?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: the branch, beside an rdc verb",
        "After `rdc machine access push` lands, should we push the branch now?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: a time word right after an unquoted rdc verb",
        "Should we rdc repo push now?",
        "",
        "decided by the hooks",
    ),
    ("permission: may I push", "May I push these to origin?", "", "BLOCKED"),
    ("permission: open the pr", "Should I open the PR?", "", "BLOCKED"),
]


def _run(question, header, tmp_path):
    payload = {"tool_input": {"questions": [{"question": question, "header": header}]}}
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["TMPDIR"] = str(tmp_path)
    return subprocess.run(
        ["python3", str(DISPATCH), STEM],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize(("label", "question", "header"), PASS, ids=[c[0] for c in PASS])
def test_rdc_push_verb_passes(label, question, header, tmp_path):
    proc = _run(question, header, tmp_path)
    assert proc.returncode == 0, "%s: refused (rc=%d)\n%s" % (label, proc.returncode, proc.stderr)


@pytest.mark.parametrize(
    ("label", "question", "header", "needle"), REFUSE, ids=[c[0] for c in REFUSE]
)
def test_genuine_push_question_still_refused(label, question, header, needle, tmp_path):
    proc = _run(question, header, tmp_path)
    assert proc.returncode == 2, "%s: not refused (rc=%d)\n%s" % (
        label,
        proc.returncode,
        proc.stderr,
    )
    assert needle in proc.stderr + proc.stdout, "%s: refusal text lacks %r" % (label, needle)
