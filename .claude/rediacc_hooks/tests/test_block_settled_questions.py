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

from rediacc_hooks.wellknown import BENCH_ORIGIN

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
    # Review 5071248a.1: the condition and immediacy words PUSH_HEADER_TIMING already counts.
    (
        "push timing: a condition word right after an unquoted rdc verb",
        "Should we rdc repo push when ready?",
        "",
        "BLOCKED",
    ),
    (
        "push timing: until after an unquoted rdc verb",
        "Should we hold off and rdc repo push until CI is green?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: immediately after an unquoted rdc verb",
        "Should we rdc repo push immediately?",
        "",
        "BLOCKED",
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


# ---- the eu-bench login (operator order 2026-10-30) ----
# The refused shape is the one asked on 2026-10-30 after `./rdc.sh --config eu-bench machine status hostinger` answered "tied to another network address": `npm run login:bench` is the agent's own step.
BENCH_REFUSE = [
    (
        "the measured ask: type the TOTP",
        (
            "The eu-bench login is tied to another network address. Could you run "
            "`rdc subscription status` in a terminal and enter the code from your authenticator app?"
        ),
        "",
    ),
    ("a bare code request", "Please send me the 6-digit TOTP code for eu-bench.", ""),
    ("the header carries bench", "Can you log in again from this IP?", "eu-bench login"),
    ("leave to run the script", "May I run npm run login:bench to refresh the login?", ""),
    (
        "the bench host spelled out",
        "Would you re-authenticate the %s login for me?" % BENCH_ORIGIN.removeprefix("https://"),
        "",
    ),
]

BENCH_REFUSE += [
    # Review dae87b66.2: a vault word in ANOTHER sentence does not excuse a login ask.
    (
        "a login ask beside a seed remark",
        "Can you log in to eu-bench again? I rotated the seed.",
        "",
    ),
]

BENCH_REFUSE += [
    # Review 28139d6b.1: "into" and "sign" spellings are the same login ask.
    ("log into spelling", "Can you log into eu-bench again?", ""),
    ("sign into spelling", "Please sign into bench for me.", ""),
]

BENCH_PASS = [
    # Review 28139d6b.1 control: a login ask with no bench named is not this rule's concern.
    ("log into a non-bench service", "Can you log into the staging DB?", ""),
    (
        "the operator's door: a placeholder value",
        (
            "login:bench refused REDIACC_BENCH_TOTP_SEED as still PLACEHOLDER-operator-fills; "
            "can you fill it in Bitwarden?"
        ),
        "",
    ),
    ("a fact question about the code", "Is the bench TOTP derivation RFC 6238?", ""),
    ("a design question about the flow", "Should the bench login flow cover us-bench too?", ""),
    ("another config", "Could you enter the authenticator code for eu-remote?", ""),
    ("a design question about the module", "Should we let login_bench retry a refused code?", ""),
    # Review dae87b66.1: addressed to the operator, yet the ask is for a code change, not a login.
    ("a request to fix the login test", "Do you want me to fix the bench login test?", ""),
]


@pytest.mark.parametrize(
    ("label", "question", "header"), BENCH_REFUSE, ids=[c[0] for c in BENCH_REFUSE]
)
def test_an_eu_bench_login_ask_is_refused_with_the_remedy(label, question, header, tmp_path):
    proc = _run(question, header, tmp_path)
    assert proc.returncode == 2, "%s: not refused (rc=%d)\n%s" % (
        label,
        proc.returncode,
        proc.stderr,
    )
    text = proc.stderr + proc.stdout
    assert "npm run login:bench" in text, "%s: refusal lacks the remedy" % label
    assert "never the operator's" in text


@pytest.mark.parametrize(
    ("label", "question", "header"), BENCH_PASS, ids=[c[0] for c in BENCH_PASS]
)
def test_a_bench_question_that_is_not_a_login_ask_passes(label, question, header, tmp_path):
    proc = _run(question, header, tmp_path)
    assert proc.returncode == 0, "%s: refused (rc=%d)\n%s" % (label, proc.returncode, proc.stderr)
