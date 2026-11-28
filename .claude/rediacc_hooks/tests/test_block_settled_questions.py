"""block_settled_questions reads a CLI verb that ends in `push` as a CLI verb, not the git act (#24fa4d53).

The measured false positive, 2026-10-28T13:27Z: a question about keeping `rdc machine access set` and `rdc machine access push` out of MCP was refused as a push-timing ask, because `push` sat inside the rdc command name and `already` followed the second one. Each payload runs through the real dispatcher in a subprocess, with HOME and TMPDIR pointed at a fresh directory so a
refusal's ledger row never lands in this machine's live ledger. Both directions are asserted: the rdc questions pass, and the genuine push-timing and permission spellings beside them are still refused, including `git push` and `gh pr create` written in backticks.

The second measured false positive, 2026-11-21 (#073c50c5): an operator design question about the two-tree fix flow DESCRIBED a push ("the landing folder adds it to the PR and pushes, and development picks it up later ...?") and was refused as a push-timing ask, because the time word sat in the next clause. FIX_FLOW passes now; the refusals beside it keep a time word in the push's own clause and an `or wait` alternative after a comma refused, and `test_the_clause_cut_is_what_admits_the_design_question` plants the old whole-sentence scan and watches FIX_FLOW read as a timing ask again.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest

from rediacc_hooks.guards import block_settled_questions as guard
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

# The design question #073c50c5 measured, verbatim with its header.
FIX_FLOW = (
    "Go with the reviewed fix flow: development supervises a helper that builds the fix on top "
    "of the PR's code, the landing folder adds it to the PR and pushes, and development picks it "
    "up later when it needs it or at handover?"
)

PASS = [
    ("the measured rdc question", MEASURED, "MCP access"),
    ("the measured fix-flow design question", FIX_FLOW, "Fix flow"),
    (
        "a design question naming who pushes, with a condition in the next clause",
        "Should the landing tree own the push, and development wait until the release is green?",
        "",
    ),
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
        "push timing: a finished batch",
        "How should a finished batch push?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: the time word in the push's own clause",
        "Should the landing tree push it later?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: an or-wait alternative after a comma",
        "Push it, or wait?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: now, or keep working",
        "Push now, or keep working on the plan?",
        "",
        "decided by the hooks",
    ),
    (
        "push timing: a condition in the push's own clause",
        "Should we push until CI is green, or hold?",
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
    ("push timing: a comma straight after the action, a time word", "Push, now?", "", "BLOCKED"),
    (
        "push timing: a comma straight after the action, a condition",
        "Should we push, once the review is in?",
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
    # eu-remote in ANOTHER sentence does not excuse an eu-bench login ask.
    ("a login ask beside an eu-remote remark", "Can you log into eu-bench? eu-remote is fine.", ""),
    ("sign into spelling", "Please sign into bench for me.", ""),
    # Review bcee4974.1: eu-remote in the SAME sentence as a comparison does not excuse it either.
    (
        "a login ask with eu-remote as a comparison",
        "Can you log into eu-bench again, same as eu-remote?",
        "",
    ),
    (
        "a bench code ask naming eu-remote",
        "Could you send the TOTP code for eu-bench, the one beside eu-remote's?",
        "",
    ),
    # Review b6058d34.1 and .2: every login phrasing aimed at bench keeps the eu-remote comparison from opening the door.
    ("login to, beside eu-remote", "Can you login to eu-bench, same as eu-remote?", ""),
    (
        "log it back in, beside eu-remote",
        "Can you log it back in to eu-bench, same as eu-remote?",
        "",
    ),
    ("sign back in, beside eu-remote", "Could you sign back in to bench, like eu-remote?", ""),
    ("re-login, beside eu-remote", "Please re-login to eu-bench, same as eu-remote.", ""),
    (
        "logging in, beside eu-remote",
        "Could you try logging in to eu-bench again, as on eu-remote?",
        "",
    ),
    # Review 2652b857.1 and .2: the "signing" form is the same ask, with and without eu-remote.
    (
        "signing in, beside eu-remote",
        "Could you try signing in to eu-bench, as on eu-remote?",
        "",
    ),
    ("signing in to bench", "Could you try signing in to bench?", ""),
]

BENCH_PASS = [
    # Review 28139d6b.1 control: a login ask with no bench named is not this rule's concern.
    ("log into a non-bench service", "Can you log into the staging DB?", ""),
    (
        "the operator's door: a placeholder value",
        (
            "login:bench refused BENCH_ROOT_TOTP_SEED as still PLACEHOLDER-operator-fills; "
            "can you fill it in Bitwarden?"
        ),
        "",
    ),
    ("a fact question about the code", "Is the bench TOTP derivation RFC 6238?", ""),
    ("a design question about the flow", "Should the bench login flow cover us-bench too?", ""),
    ("another config", "Could you enter the authenticator code for eu-remote?", ""),
    (
        "eu-remote's login with bench as the alternative",
        "Should we run the eu-remote reads behind your login, or reword them to bench?",
        "",
    ),
    ("a design question about the module", "Should we let login_bench retry a refused code?", ""),
    # Review dae87b66.1: addressed to the operator, yet the ask is for a code change, not a login.
    ("a request to fix the login test", "Do you want me to fix the bench login test?", ""),
]


BENCH_REFUSE += [
    # PLAN-multi-region-bench W5: the us and asia benches are the same agent-owned login.
    ("us-bench log into", "Can you log into us-bench again?", ""),
    ("asia-bench code ask", "Could you send the TOTP code for asia-bench?", ""),
    ("us-bench header", "Can you log in again from this IP?", "us-bench login"),
    ("us-bench re-login beside eu-remote", "Please re-login to us-bench, same as eu-remote.", ""),
    (
        "asia-bench code ask beside eu-remote",
        "Could you send the TOTP code for asia-bench, the one beside eu-remote's?",
        "",
    ),
    ("signing in to asia-bench", "Could you try signing in to asia-bench?", ""),
]

BENCH_PASS += [
    # Controls: a regional config that is not bench, and a design question about a regional bench.
    ("a us config that is not bench", "Could you enter the authenticator code for us-remote?", ""),
    ("a design question about asia-bench", "Should the bench login flow cover asia-bench?", ""),
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


def test_the_push_message_names_the_two_tree_loop(tmp_path):
    """PUSH_MESSAGE answers with the loop that decides push timing now: the development tree's backup push and promote, and the landing tree's one PR."""
    proc = _run("Push now?", "", tmp_path)
    assert proc.returncode == 2, proc.stderr
    text = proc.stderr + proc.stdout
    for needle in ("Development tree", "landing --promote", "Landing tree"):
        assert needle in text, "PUSH_MESSAGE lacks %r:\n%s" % (needle, text)


def test_the_clause_cut_is_what_admits_the_design_question(monkeypatch):
    """The mutant: CLAUSE_AFTER planted to match nothing, the time-word scan reads to the sentence end again and FIX_FLOW is a push-timing ask, as it was on 2026-11-21. The control is the same call on the real pattern, which finds no timing (test_rdc_push_verb_passes drives it through the dispatcher)."""
    sentence = FIX_FLOW.translate(guard._ASCII_LOWER)
    assert guard._push_timing(sentence, "") is None
    monkeypatch.setattr(guard, "CLAUSE_AFTER", r"(?!x)x")
    assert guard._push_timing(sentence, "") == "pushes"
