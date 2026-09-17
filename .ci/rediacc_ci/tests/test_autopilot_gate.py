"""Differential: `rediacc_ci.autopilot.autopilot_gate` against its twin
`.ci/scripts/autopilot/autopilot-gate.sh`.

THE TWIN'S OWN SENTENCE IS THIS FILE'S BRIEF: "an untested branch in this file is an untested security decision". The subject is a 414-line decision tree with twenty-seven distinct exits, and a port that quietly dropped one of them would look exactly like a port that kept it -- on every input except the one the dropped check existed for. So the cases below walk the tree ARM BY ARM,
in the twin's own order, and each arm is named after the refusal string it proves.

THE PURITY CLAIM IS MADE MECHANICAL, NOT ASSERTED. The gate advertises itself as running no network calls, and every case here runs with a POISON `gh` first on PATH that records its argv and exits 66. `test_the_gate_never_reaches_the_network` is the control that proves the poison would be noticed, and every `_sides` call asserts the call log is empty, so a port that grew a `gh`
call would fail every
case rather than one.

WHAT IS COMPARED. Exit code, stdout bytes, stderr bytes, and the `gh` call log, on both sides, for every case. STDOUT IS THE WHOLE PRODUCT HERE: one JSON line whose twelve keys the calling workflow reads, so a port that reached the right verdict with the wrong `rounds_max` would still be a different gate. Several cases therefore assert the decoded object field by field ON TOP of
the byte comparison, because "the two sides agree" and "the two sides are right" are different claims and only the second one catches a shared misreading of the twin.

ONE STDERR LINE DIVERGES, IN ONE CASE, AND IT IS PINNED RATHER THAN HIDDEN.
`((08 > 0))` is a bash arithmetic ERROR whose diagnostic carries the script path and line number; see `autopilot_gate.py`'s docstring. `test_an_invalid_octal_round_cap` compares exit code, stdout and the `gh` log byte for byte, and compares stderr
with that single line filtered out of both sides. Nothing else in this file
filters anything.

K=5 LEDGER: `.ci/shadow/w7p6-autopilot-gate.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout, since `shadow-gate.ts --record` refuses a dirty tree and this checkout is never clean.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.autopilot import autopilot_gate as ag

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "autopilot-gate.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "autopilot_gate.py"
BASH = shutil.which("bash") or "/bin/bash"

# A `gh` that cannot succeed and cannot be silent. The gate is documented PURE;
# this is what turns that documentation into a test result.
POISON_GH = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(sys.argv[1:]) + "\\n")
sys.stderr.write("poison gh: the autopilot gate must not reach the network\\n")
sys.exit(66)
"""

HEADER = "### Autopilot state (machine-maintained, do not edit)"


def _stub_bin(base: pathlib.Path) -> str:
    """The poison `gh` FIRST, then the real PATH.

    The real PATH is kept because the twin needs `jq`, `grep`, `sort`, `awk`, `sed`, `tr`, `mktemp`, `dirname`, `uname`, `cat` and `wc` -- and because `state-comment.sh`, which the twin spawns for real, needs them too. Only `gh` is displaced, and `test_the_gate_never_reaches_the_network` proves the displacement took.
    """
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(POISON_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], env_extra: dict[str, str]):
    log = base / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": _stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
    }
    env.update(env_extra)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


ARITH_ERROR = b"value too great for base"


def _drop_arith(stream: bytes) -> bytes:
    """Remove bash's arithmetic diagnostic. Used by exactly one case."""
    return b"".join(line + b"\n" for line in stream.split(b"\n")[:-1] if ARITH_ERROR not in line)


def _sides(
    name: str,
    argv: list[str],
    *,
    fixtures: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    filter_arith: bool = False,
):
    """Run both subjects on identical private trees and compare everything."""
    results = []
    with tempfile.TemporaryDirectory() as td:
        # "old"/"new" rather than the subjects' stems, because a fixture path is passed relative to `cwd` and the two bases must not be the same dir.
        for side, subject in (("old", TWIN), ("new", PORT)):
            base = pathlib.Path(td) / side
            base.mkdir(parents=True)
            for rel, text in (fixtures or {}).items():
                (base / rel).write_text(text, encoding="utf-8")
            results.append(_run(subject, base, argv, dict(env or {})))
    old, new = results
    assert new[0] == old[0], "%s: exit diverged: %r vs %r\nold stderr %r\nnew stderr %r" % (
        name,
        old[0],
        new[0],
        old[2],
        new[2],
    )
    assert new[1] == old[1], "%s: stdout diverged:\nold %r\nnew %r" % (name, old[1], new[1])
    old_err, new_err = (old[2], new[2])
    if filter_arith:
        old_err, new_err = _drop_arith(old_err), _drop_arith(new_err)
        assert ARITH_ERROR in old[2], "%s: the arithmetic filter fired on nothing" % name
    assert new_err == old_err, "%s: stderr diverged:\nold %r\nnew %r" % (name, old_err, new_err)
    assert new[3] == old[3], "%s: gh calls diverged:\nold %r\nnew %r" % (name, old[3], new[3])
    assert old[3] == [], "%s: the gate called gh: %r" % (name, old[3])
    return old


def _decision(stdout: bytes) -> dict:
    return json.loads(stdout.decode("utf-8"))


# --------------------------------------------------------------------------- Fixture builders ---------------------------------------------------------------------------

EVENT_ARGS = ["--classify", "--event", "event.json", "--pr", "pr.json"]
ARMED = {"AUTOPILOT_ENABLED": "true", "AUTOPILOT_AUTHOR_ALLOWLIST": "operator"}


def event_json(
    conclusion: str = "success",
    *,
    run_id: object = 4242,
    attempt: object = 1,
    head_sha: str = "cafe1234",
    repo: str = "rediacc/console",
    head_repo: str | None = "rediacc/console",
    dispatch: dict | None = None,
) -> str:
    run: dict = {"conclusion": conclusion, "id": run_id, "run_attempt": attempt}
    if head_sha:
        run["head_sha"] = head_sha
    if head_repo is not None:
        run["head_repository"] = {"full_name": head_repo}
    payload: dict = {"workflow_run": run, "repository": {"full_name": repo}}
    if dispatch is not None:
        payload["autopilot_dispatch"] = dispatch
    return json.dumps(payload) + "\n"


def pr_json(**over: object) -> str:
    fields: dict = {
        "number": 5,
        "author": "operator",
        "draft": False,
        "labels": ["autopilot"],
        "label_applier": "operator",
        "head_repo": "rediacc/console",
        "base_repo": "rediacc/console",
        "head_sha": "cafe1234",
        "unresolved_threads": 0,
        "review_gate_red": False,
    }
    fields.update(over)
    return json.dumps(fields) + "\n"


def state_body(
    *,
    rounds: int = 0,
    campaign: str = "none",
    model: str = "none",
    rounds_max: str = "0",
    last_sig: str = "none",
    sig_count: str = "0",
    run_ids: list[str] | None = None,
) -> str:
    """A rendered state comment, in `state-comment.sh render`'s exact shape.

    Written by hand rather than by calling the renderer, so a change in the renderer cannot silently change what these cases test. The metadata line's ` | ` separators and the `r<n> | run ` ledger prefix are both parsed by the subject, so both are the contract this fixture asserts against.
    """
    ledger = run_ids or ["%d/1" % (4000 + i) for i in range(rounds)]
    lines = [
        HEADER,
        "state: fix | round: %d/%s | head: cafe1234 | last_run: 4242/1 | campaign: %s | "
        "model: %s | rounds_max: %s | last_sig: %s | sig_count: %s"
        % (len(ledger), rounds_max, campaign, model, rounds_max, last_sig, sig_count),
        "",
        "#### Round ledger",
    ]
    lines += ["r%d | run %s handled" % (i + 1, rid) for i, rid in enumerate(ledger)]
    lines += ["", "#### Ruled out", "", "#### DECISIONS (post-hoc review)", ""]
    return "\n".join(lines)


def sig_of(text: str) -> str:
    """The gate's signature over a failed-jobs file, computed independently.

    `LC_ALL=C sort` then sha256, first 8 hex. Recomputed here rather than
    imported from the port, so a fixture that must MATCH a stored signature is not built by the same code the case is testing.
    """
    lines = sorted(line for line in text.split("\n") if line != "")
    blob = "".join(line + "\n" for line in lines).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:8]


BASE_FIXTURES = {"event.json": event_json(), "pr.json": pr_json()}


# --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------


def test_the_gate_never_reaches_the_network() -> None:
    """CONTROL for every `calls == []` assertion in this file.

    The poison `gh` must be the `gh` a subject would find, AND it must record. Without this, "no gh call was logged" is equally consistent with the log never being written to by anything.
    """
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        found = shutil.which("gh", path=path)
        assert found == str(base / "bin" / "gh"), "the poison gh is not first on PATH: %r" % found
        log = base / "gh-calls.log"
        log.write_text("", encoding="utf-8")
        proc = subprocess.run(
            [found, "api", "graphql"],
            capture_output=True,
            env={"FAKE_GH_LOG": str(log), "PATH": path},
            check=False,
        )
        assert proc.returncode == 66
        assert log.read_text(encoding="utf-8") == "api\tgraphql\n"


# --------------------------------------------------------------------------- Exits 1-7: the LOUD ones. A wiring bug must never read as a quiet no-go. ---------------------------------------------------------------------------


def test_usage_when_the_mode_is_not_classify() -> None:
    """Both lines, and exit 2 rather than a no-go. Including NO arguments at
    all, which is `${1:-}` -> the empty string."""
    for argv in ([], ["classify"], ["--pr", "pr.json"], ["--help"]):
        code, out, err, _ = _sides("usage-%r" % (argv,), argv, fixtures=BASE_FIXTURES)
        assert code == 2, argv
        assert out == b"", argv
        assert b"usage: autopilot-gate.sh --classify --event <file> --pr <file>" in err
        assert b"the gate is fixtures-only by design" in err


def test_usage_when_a_fixture_flag_is_missing() -> None:
    for argv in (
        ["--classify"],
        ["--classify", "--event", "event.json"],
        ["--classify", "--pr", "pr.json"],
        ["--classify", "--event=", "--pr", "pr.json"],
    ):
        code, out, err, _ = _sides("missing-%d" % len(argv), argv, fixtures=BASE_FIXTURES)
        assert code == 2, argv
        assert out == b""
        assert b"--event and --pr are required" in err, argv


def test_a_fixture_that_does_not_exist_is_require_file_not_a_no_go() -> None:
    """Exit 1, `require_file`'s own sentence, and the EVENT is checked first."""
    code, _, err, _ = _sides(
        "no-event",
        ["--classify", "--event", "nope.json", "--pr", "pr.json"],
        fixtures=BASE_FIXTURES,
    )
    assert code == 1
    assert b"Required file 'nope.json' does not exist" in err
    code, _, err, _ = _sides(
        "no-pr",
        ["--classify", "--event", "event.json", "--pr", "gone.json"],
        fixtures=BASE_FIXTURES,
    )
    assert code == 1
    assert b"Required file 'gone.json' does not exist" in err


def test_a_fixture_that_is_not_json() -> None:
    """`jq -e .`, and its two failure shapes.

    A PARSE failure and a `null` body are the same refusal here, and that is jq's rule rather than a choice: `jq -e` exits 1 when the last value is null or false. A port built on `json.loads` would accept `null` and then read every field off nothing.
    """
    for label, body, which in (
        ("garbage-event", "not json at all\n", "event"),
        ("null-event", "null\n", "event"),
        ("false-event", "false\n", "event"),
    ):
        fixtures = dict(BASE_FIXTURES)
        fixtures["event.json"] = body
        code, out, err, _ = _sides(label, EVENT_ARGS, fixtures=fixtures)
        assert code == 2, label
        assert out == b""
        assert b"%s payload is not valid JSON: event.json" % which.encode() in err, err
    for label, body in (("garbage-pr", "{oops\n"), ("null-pr", "null\n")):
        fixtures = dict(BASE_FIXTURES)
        fixtures["pr.json"] = body
        code, _, err, _ = _sides(label, EVENT_ARGS, fixtures=fixtures)
        assert code == 2, label
        assert b"pr fixture is not valid JSON: pr.json" in err


def test_an_event_missing_its_run_identity() -> None:
    """Exit 2, AFTER the stage flag: a wiring bug is loud, but a disabled stage
    is still a no-go, so the ORDER of these two decides which one a misconfigured stage sees. The twin checks the flag first; both cases here
    pin that."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = json.dumps({"workflow_run": {"id": 1}}) + "\n"
    code, out, err, _ = _sides("no-conclusion", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert code == 2
    assert out == b""
    assert b"event payload lacks workflow_run.conclusion or .id" in err
    # Same fixture with the stage flag OFF is a no-go, not an exit 2.
    code, out, _, _ = _sides("no-conclusion-stage-off", EVENT_ARGS, fixtures=fixtures)
    assert code == 0
    assert _decision(out)["reason"].startswith("stage-flag-disabled")
    fixtures["event.json"] = json.dumps({"workflow_run": {"conclusion": "success"}}) + "\n"
    code, _, err, _ = _sides("no-id", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert code == 2
    assert b"event payload lacks workflow_run.conclusion or .id" in err


# --------------------------------------------------------------------------- Exit 8: the master stage flag ---------------------------------------------------------------------------


def test_the_stage_flag_is_closed_by_default_and_by_anything_but_true() -> None:
    """FAIL CLOSED, and the whole decision line is checked: a no-go before any
    fixture has been read still carries round 1, sig_count 0 and armed_by none,
    which is what the workflow's next state write records."""
    code, out, _, _ = _sides("stage-off", EVENT_ARGS, fixtures=BASE_FIXTURES)
    assert code == 0
    assert out == (
        b'{"decision":"no-go","mode":"none","reason":"stage-flag-disabled: AUTOPILOT_ENABLED '
        b'is not \'true\' (absent means off, fail closed)","round":1,"push_allowed":false,'
        b'"armed_by":"none","model":"claude-sonnet-5","rounds_max":25,"campaign":"none",'
        b'"dispatch_trusted":false,"sig":"none","sig_count":0}\n'
    ), out
    for value in ("", "TRUE", "1", "yes", "true "):
        code, out, _, _ = _sides(
            "stage-%r" % value,
            EVENT_ARGS,
            fixtures=BASE_FIXTURES,
            env={"AUTOPILOT_ENABLED": value},
        )
        assert _decision(out)["decision"] == "no-go", value


def test_push_allowed_is_reported_but_does_not_arm() -> None:
    """`AUTOPILOT_ALLOW_PUSH` is REPORTED for the harness and gates nothing
    here, so it must show through even on a refusal."""
    _, out, _, _ = _sides(
        "push-on-stage-off",
        EVENT_ARGS,
        fixtures=BASE_FIXTURES,
        env={"AUTOPILOT_ALLOW_PUSH": "true"},
    )
    assert _decision(out)["push_allowed"] is True
    _code, out, _, _ = _sides(
        "push-not-true",
        EVENT_ARGS,
        fixtures=BASE_FIXTURES,
        env={"AUTOPILOT_ALLOW_PUSH": "TRUE"},
    )
    assert _decision(out)["push_allowed"] is False


# --------------------------------------------------------------------------- Exits 9-10: the fork guard, in BOTH records ---------------------------------------------------------------------------


def test_the_fork_guard_reads_the_run_record() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json(head_repo="attacker/console")
    _, out, _, _ = _sides("fork-run", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"] == (
        "fork-pr: workflow_run head repository 'attacker/console' is not the base repo"
    )
    # An ABSENT head_repository is not a fork: the guard is `-n && !=`, so a
    # payload that never names one falls through to the PR record's check.
    fixtures["event.json"] = event_json(head_repo=None)
    _code, out, _, _ = _sides("fork-run-absent", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["decision"] == "go"


def test_the_fork_guard_reads_the_pr_record() -> None:
    for label, over in (
        ("mismatch", {"head_repo": "attacker/console"}),
        ("absent", {"head_repo": ""}),
    ):
        fixtures = dict(BASE_FIXTURES)
        fixtures["pr.json"] = pr_json(**over)
        _code, out, _, _ = _sides("fork-pr-%s" % label, EVENT_ARGS, fixtures=fixtures, env=ARMED)
        assert _decision(out)["reason"].startswith("fork-pr: PR head repo "), label


# --------------------------------------------------------------------------- Exit 11: the escalation latch, and its ORDER ---------------------------------------------------------------------------


def test_the_blocked_label_beats_every_arming_path() -> None:
    """`autopilot-blocked` is read FIRST, so it beats a label, a fresh dispatch
    and an open campaign alike. Cancelling a run kills one round; this kills the
    loop, and a port that checked it after arming would let a dispatch through."""
    for label, fixtures_over, env_over in (
        ("label", {"pr.json": pr_json(labels=["autopilot", "autopilot-blocked"])}, {}),
        (
            "dispatch",
            {
                "pr.json": pr_json(labels=["autopilot-blocked"]),
                "event.json": event_json(
                    dispatch={"actor": "operator", "pr_input": "5", "model": "", "max_rounds": ""}
                ),
            },
            {},
        ),
    ):
        fixtures = dict(BASE_FIXTURES)
        fixtures.update(fixtures_over)
        env = dict(ARMED)
        env.update(env_over)
        _code, out, _, _ = _sides("blocked-%s" % label, EVENT_ARGS, fixtures=fixtures, env=env)
        assert _decision(out)["reason"] == (
            "blocked-label: 'autopilot-blocked' is applied; a human must clear the escalation first"
        ), label


def test_the_blocked_label_is_found_at_index_zero() -> None:
    """jq's `index` returns 0 for a first-position match, and 0 is TRUTHY in jq
    and FALSY in Python. This is the case a `json`-based port fails, and it is
    the commonest real shape: a PR carrying only the blocked label."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=["autopilot-blocked"])
    _, out, _, _ = _sides("blocked-first", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"].startswith("blocked-label:")
    # CONTROL: the same position for the ARMING label must arm, not refuse.
    fixtures["pr.json"] = pr_json(labels=["autopilot"])
    _code, out, _, _ = _sides("armed-first", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["armed_by"] == "label"


# --------------------------------------------------------------------------- Exit 12 and the three arming paths ---------------------------------------------------------------------------


def test_not_armed_names_what_it_looked_for() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[])
    _, out, _, _ = _sides("not-armed", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"] == (
        "not-armed: no 'autopilot' label, no dispatch with a PR number, and no open campaign "
        "with rounds remaining (campaign: none, rounds done: 0/25)"
    )
    assert _decision(out)["armed_by"] == "none"
    # AUTOPILOT_LABEL renames the arming label, and the refusal says so.
    env = dict(ARMED)
    env["AUTOPILOT_LABEL"] = "babysit"
    _, out, _, _ = _sides("not-armed-custom", EVENT_ARGS, fixtures=fixtures, env=env)
    assert "no 'babysit' label" in _decision(out)["reason"]
    fixtures["pr.json"] = pr_json(labels=["babysit"])
    _code, out, _, _ = _sides("armed-custom", EVENT_ARGS, fixtures=fixtures, env=env)
    assert _decision(out)["armed_by"] == "label"


def test_a_dispatch_arms_round_one_on_its_own() -> None:
    """THE DISPATCH IS THE ARMING ACT: no label, no state, and round 1 runs."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[])
    fixtures["event.json"] = event_json(
        dispatch={"actor": "operator", "pr_input": "5", "model": "", "max_rounds": ""}
    )
    _, out, _, _ = _sides("dispatch-arms", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert decision["armed_by"] == "dispatch"
    assert decision["round"] == 1
    # AND THE ARM THAT SURPRISES: this dispatch lands in mode `done` (CI is already green, nothing outstanding), and the `done` arm is tested FIRST in `emit`, so the campaign is NOT opened. Correct -- there is nothing for a campaign to carry -- and worth pinning, because "a dispatch opens the campaign" is the sentence a reader takes from the header and it is only true of a dispatch
    # that buys a round.
    assert decision["campaign"] == "none"
    fixtures["event.json"] = event_json("failure", dispatch={"actor": "operator", "pr_input": "5"})
    _, out, _, _ = _sides("dispatch-arms-fix", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert (decision["armed_by"], decision["mode"]) == ("dispatch", "fix")
    assert decision["campaign"] == "open", "a dispatch that buys a round opens the campaign"
    # A dispatch with NO pr_input is not an arming act.
    fixtures["event.json"] = event_json(dispatch={"actor": "operator"})
    _code, out, _, _ = _sides("dispatch-no-pr", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"].startswith("not-armed:")


def test_an_open_campaign_carries_the_loop_without_a_label() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[])
    fixtures["state.md"] = state_body(rounds=2, campaign="open", rounds_max="9")
    argv = [*EVENT_ARGS, "--state", "state.md"]
    _, out, _, _ = _sides("campaign", argv, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert decision["armed_by"] == "campaign"
    assert decision["round"] == 3, "the ledger is the only round counter"
    assert decision["rounds_max"] == 9, "the campaign's cap beats the default"
    # A CLOSED campaign does not arm.
    fixtures["state.md"] = state_body(rounds=2, campaign="closed", rounds_max="9")
    _, out, _, _ = _sides("campaign-closed", argv, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"].startswith("not-armed:")
    assert "campaign: closed, rounds done: 2/9" in _decision(out)["reason"]
    # An open campaign with the cap already reached does not re-arm either, and says `not-armed` rather than `round-cap`, because arming runs first.
    fixtures["state.md"] = state_body(rounds=9, campaign="open", rounds_max="9")
    _code, out, _, _ = _sides("campaign-spent", argv, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"].startswith("not-armed:")
    assert "rounds done: 9/9" in _decision(out)["reason"]


# --------------------------------------------------------------------------- Exits 13-14: the two trust checks, and the order between them ---------------------------------------------------------------------------


def test_the_author_allowlist_fails_closed_when_empty() -> None:
    for label, env_over in (
        ("absent", {}),
        ("empty", {"AUTOPILOT_AUTHOR_ALLOWLIST": ""}),
        ("someone-else", {"AUTOPILOT_AUTHOR_ALLOWLIST": "somebody,else"}),
        ("prefix-only", {"AUTOPILOT_AUTHOR_ALLOWLIST": "operator2"}),
    ):
        env = {"AUTOPILOT_ENABLED": "true"}
        env.update(env_over)
        _, out, _, _ = _sides("author-%s" % label, EVENT_ARGS, fixtures=BASE_FIXTURES, env=env)
        assert _decision(out)["reason"] == (
            "author-not-allowlisted: PR author 'operator' is not in AUTOPILOT_AUTHOR_ALLOWLIST"
        ), label
    # And the positive side, so the check is not simply always-refusing.
    _code, out, _, _ = _sides(
        "author-ok",
        EVENT_ARGS,
        fixtures=BASE_FIXTURES,
        env={"AUTOPILOT_ENABLED": "true", "AUTOPILOT_AUTHOR_ALLOWLIST": "a, operator ,b"},
    )
    assert _decision(out)["decision"] == "go"


def test_the_author_check_runs_after_arming() -> None:
    """A stranger's UNARMED PR is `not-armed`, not `author-not-allowlisted`.

    ORDER, and it is the difference between telling an outsider that their PR
    would otherwise qualify and telling them nothing."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[], author="stranger")
    _code, out, _, _ = _sides("order-arming-first", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"].startswith("not-armed:")


def test_the_applier_is_a_separate_trust_decision_from_the_author() -> None:
    """Anyone with triage can apply a label, so the APPLIER is checked too."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(label_applier="drive-by")
    _, out, _, _ = _sides("applier-no", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"] == (
        "applier-not-allowlisted: label applier 'drive-by' is not allowlisted"
    )
    # AUTOPILOT_APPLIER_ALLOWLIST OVERRIDES the author list rather than adding to it, so an author-allowlisted applier is refused once it is set.
    env = dict(ARMED)
    env["AUTOPILOT_APPLIER_ALLOWLIST"] = "someone-else"
    _, out, _, _ = _sides("applier-override", EVENT_ARGS, fixtures=BASE_FIXTURES, env=env)
    assert _decision(out)["reason"].startswith("applier-not-allowlisted:")
    env["AUTOPILOT_APPLIER_ALLOWLIST"] = "operator"
    _code, out, _, _ = _sides("applier-listed", EVENT_ARGS, fixtures=BASE_FIXTURES, env=env)
    assert _decision(out)["decision"] == "go"


def test_the_dispatching_actor_is_checked_on_the_dispatch_path() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[])
    fixtures["event.json"] = event_json(dispatch={"actor": "drive-by", "pr_input": "5"})
    _code, out, _, _ = _sides("dispatch-actor-no", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert decision["reason"] == (
        "dispatch-actor-not-allowlisted: dispatching actor 'drive-by' is not allowlisted"
    )
    assert decision["dispatch_trusted"] is False


def test_dispatch_trusted_is_not_the_same_claim_as_armed() -> None:
    """A LABEL-armed round dispatched by nobody in particular: armed yes,
    trusted no. The workflow gates a human shell on the runner on the second
    one, so collapsing them would hand a shell to whoever pressed the button."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json(dispatch={"actor": "drive-by", "pr_input": ""})
    _, out, _, _ = _sides("armed-untrusted", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert decision["armed_by"] == "label"
    assert decision["dispatch_trusted"] is False
    assert decision["decision"] == "go"
    fixtures["event.json"] = event_json(dispatch={"actor": "operator", "pr_input": ""})
    _code, out, _, _ = _sides("armed-trusted", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["dispatch_trusted"] is True


def test_the_campaign_path_has_no_further_trust_check() -> None:
    """The empty `campaign)` case arm, asserted rather than assumed: a campaign
    round with a hostile `label_applier` and no dispatch actor still goes, because the state comment's AUTHORSHIP is the check and it happened
    upstream."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[], label_applier="drive-by")
    fixtures["state.md"] = state_body(rounds=1, campaign="open", rounds_max="9")
    _code, out, _, _ = _sides(
        "campaign-trust", [*EVENT_ARGS, "--state", "state.md"], fixtures=fixtures, env=ARMED
    )
    decision = _decision(out)
    assert decision["armed_by"] == "campaign"
    assert decision["decision"] == "go"


# --------------------------------------------------------------------------- Exits 15-17: dedup, the round cap, the watchdog ---------------------------------------------------------------------------


def test_a_duplicate_of_an_already_handled_run() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["state.md"] = state_body(run_ids=["4242/1"], campaign="none", rounds_max="9")
    argv = [*EVENT_ARGS, "--state", "state.md"]
    _, out, _, _ = _sides("dedup", argv, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"] == "already-handled: run 4242/1 is in the ledger"
    # A DIFFERENT ATTEMPT of the same run is not a duplicate.
    fixtures["event.json"] = event_json(attempt=2)
    _, out, _, _ = _sides("dedup-attempt-2", argv, fixtures=fixtures, env=ARMED)
    assert _decision(out)["decision"] == "go"
    # And `4242/1` must not match `42420/1`: the trailing `([^0-9]|$)` is what stops a shorter run id matching a longer one's prefix.
    fixtures["event.json"] = event_json(run_id=424)
    _code, out, _, _ = _sides("dedup-prefix", argv, fixtures=fixtures, env=ARMED)
    assert _decision(out)["decision"] == "go"


def test_the_round_cap_is_enforced_from_the_trusted_ledger() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["state.md"] = state_body(rounds=3, campaign="none", rounds_max="0")
    argv = [*EVENT_ARGS, "--state", "state.md"]
    env = dict(ARMED)
    env["AUTOPILOT_MAX_ROUNDS"] = "3"
    _, out, _, _ = _sides("cap", argv, fixtures=fixtures, env=env)
    decision = _decision(out)
    assert decision["reason"] == (
        "round-cap: 3 rounds recorded, cap is 3; escalating to the operator is the design working"
    )
    assert decision["round"] == 4, "the round it WOULD have been is still reported"
    env["AUTOPILOT_MAX_ROUNDS"] = "4"
    _code, out, _, _ = _sides("cap-not-reached", argv, fixtures=fixtures, env=env)
    assert _decision(out)["decision"] == "go"


def test_an_out_of_shape_max_rounds_falls_back_to_twenty_five() -> None:
    for value, expected in (("", 25), ("abc", 25), ("99999", 25), ("-1", 25), ("7", 7)):
        env = dict(ARMED)
        env["AUTOPILOT_MAX_ROUNDS"] = value
        _code, out, _, _ = _sides(
            "maxrounds-%r" % value, EVENT_ARGS, fixtures=BASE_FIXTURES, env=env
        )
        assert _decision(out)["rounds_max"] == expected, value


def test_the_watchdog_deferral() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["watchdog.txt"] = "pending_rerun 4242\n"
    _, out, _, _ = _sides(
        "watchdog",
        [*EVENT_ARGS, "--watchdog", "watchdog.txt"],
        fixtures=fixtures,
        env=ARMED,
    )
    assert _decision(out)["reason"] == (
        "watchdog-defer: a pending_rerun is held for this run; the gate defers so the two "
        "cannot race"
    )
    # An EMPTY watchdog file is not a hold: the test is `-s`, not `-f`.
    fixtures["watchdog.txt"] = ""
    _code, out, _, _ = _sides(
        "watchdog-empty",
        [*EVENT_ARGS, "--watchdog", "watchdog.txt"],
        fixtures=fixtures,
        env=ARMED,
    )
    assert _decision(out)["decision"] == "go"


# --------------------------------------------------------------------------- Exits 18-27: mode selection, one case per conclusion arm ---------------------------------------------------------------------------


def test_a_failed_run_buys_a_fix_round() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json("failure")
    _code, out, _, _ = _sides("fix", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert (decision["decision"], decision["mode"]) == ("go", "fix")
    assert decision["reason"] == "ci-failure: run 4242 concluded failure"
    assert decision["sig"] == "none", "no failed-jobs file means no signature"


def test_the_failure_signature_is_order_independent() -> None:
    """Sorted before hashing, so the jobs API's ordering cannot change it."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json("failure")
    seen = set()
    for jobs in ("quality\nbuild\n", "build\nquality\n"):
        fixtures["jobs.txt"] = jobs
        _code, out, _, _ = _sides(
            "sig-%r" % jobs,
            [*EVENT_ARGS, "--failed-jobs", "jobs.txt"],
            fixtures=fixtures,
            env=ARMED,
        )
        decision = _decision(out)
        seen.add(decision["sig"])
        assert decision["sig_count"] == 1
    assert len(seen) == 1, "the signature depends on the job ORDER: %r" % seen
    assert seen == {sig_of("quality\nbuild\n")}, seen


def test_the_stuck_signature_escalates_before_the_cap() -> None:
    """The third consecutive round on one unchanged failed-job set refuses.

    This is the difference between escalating at round 3 and burning 25."""
    jobs = "quality\nbuild\n"
    sig = sig_of(jobs)
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json("failure")
    fixtures["jobs.txt"] = jobs
    argv = [*EVENT_ARGS, "--failed-jobs", "jobs.txt", "--state", "state.md"]
    # sig_count 2 in the comment -> this round is the third.
    fixtures["state.md"] = state_body(
        rounds=2, campaign="open", rounds_max="25", last_sig=sig, sig_count="2"
    )
    _, out, _, _ = _sides("stuck", argv, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert decision["reason"] == (
        "stuck-signature: failed-job set %s is unchanged after 2 fix round(s); escalating "
        "rather than burning the round cap" % sig
    )
    assert decision["sig_count"] == 3
    # ONE round earlier, the same set still buys a fix.
    fixtures["state.md"] = state_body(
        rounds=2, campaign="open", rounds_max="25", last_sig=sig, sig_count="1"
    )
    _, out, _, _ = _sides("stuck-minus-one", argv, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert (decision["mode"], decision["sig_count"]) == ("fix", 2)
    # A DIFFERENT set resets the counter to 1, so a moving failure never sticks.
    fixtures["jobs.txt"] = "something-else\n"
    fixtures["state.md"] = state_body(
        rounds=2, campaign="open", rounds_max="25", last_sig=sig, sig_count="2"
    )
    _code, out, _, _ = _sides("stuck-reset", argv, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert (decision["mode"], decision["sig_count"]) == ("fix", 1)


def test_a_green_run_never_looks_like_a_repeat_of_the_last_red_one() -> None:
    """`sig` is `none` with no failed jobs, and `none` never matches a stored
    signature even when the stored one is literally absent."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json("failure")
    fixtures["jobs.txt"] = ""
    fixtures["state.md"] = state_body(
        rounds=1, campaign="open", rounds_max="25", last_sig="none", sig_count="3"
    )
    _code, out, _, _ = _sides(
        "sig-none",
        [*EVENT_ARGS, "--failed-jobs", "jobs.txt", "--state", "state.md"],
        fixtures=fixtures,
        env=ARMED,
    )
    decision = _decision(out)
    assert (decision["sig"], decision["sig_count"], decision["mode"]) == ("none", 1, "fix")


def test_a_cancelled_run_with_failed_jobs_is_a_watchdog_kill() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json("cancelled")
    fixtures["jobs.txt"] = "quality\nbuild\n\n"
    _code, out, _, _ = _sides(
        "watchdog-kill",
        [*EVENT_ARGS, "--failed-jobs", "jobs.txt"],
        fixtures=fixtures,
        env=ARMED,
    )
    decision = _decision(out)
    assert (decision["mode"], decision["reason"]) == (
        "fix",
        "watchdog-kill: cancelled with 2 failed job(s)",
    ), decision
    assert "2 failed" in decision["reason"], "blank lines are not jobs (grep -c .)"


def test_a_cancelled_run_whose_head_moved_on() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json("cancelled", head_sha="oldsha")
    _code, out, _, _ = _sides("superseded", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"] == (
        "superseded: run head oldsha is no longer the PR head cafe1234"
    )


def test_a_cancelled_run_with_nothing_to_act_on() -> None:
    fixtures = dict(BASE_FIXTURES)
    fixtures["event.json"] = event_json("cancelled")
    _, out, _, _ = _sides("cancelled-quiet", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"] == (
        "cancelled-no-failure: cancelled with zero failed jobs and no newer head; nothing to act on"
    )
    # An ABSENT head sha on either side skips the superseded check entirely.
    fixtures["event.json"] = event_json("cancelled", head_sha="")
    _code, out, _, _ = _sides("cancelled-no-head", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["reason"].startswith("cancelled-no-failure:")


def test_the_four_success_arms_in_their_order() -> None:
    """Review gate first, then draft, then threads, then done. The order is the
    design's; each case here differs from the next by ONE field, so a port that
    reordered them would land on a different mode."""
    cases = [
        (
            "rerun-review",
            {"review_gate_red": True, "unresolved_threads": 0},
            "rerun-review",
            (
                "review-gate-red-no-threads: the Review Gate is red with nothing outstanding "
                "to answer; deterministic rerun, no model"
            ),
        ),
        (
            "review-red-threads",
            {"review_gate_red": True, "unresolved_threads": 3},
            "review-response",
            "review-gate-red: CI green, the Review Gate is red, and 3 thread(s) are outstanding",
        ),
        (
            "ready-flip",
            {"draft": True},
            "ready-flip",
            "success-while-draft: deterministic ready-flip, no model",
        ),
        (
            "threads-only",
            {"unresolved_threads": 2},
            "review-response",
            "unresolved-threads: 2 review thread(s) outstanding",
        ),
        (
            "done",
            {},
            "done",
            "done-conditions: green, ready, reviewed, no outstanding threads",
        ),
    ]
    for label, over, mode, reason in cases:
        fixtures = dict(BASE_FIXTURES)
        fixtures["pr.json"] = pr_json(**over)
        _, out, _, _ = _sides("success-%s" % label, EVENT_ARGS, fixtures=fixtures, env=ARMED)
        decision = _decision(out)
        assert (decision["decision"], decision["mode"]) == ("go", mode), label
        assert decision["reason"] == reason, label
    # A red review gate BEATS a draft: the draft flip would hide the red.
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(review_gate_red=True, draft=True, unresolved_threads=0)
    _code, out, _, _ = _sides("red-beats-draft", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["mode"] == "rerun-review"


def test_an_out_of_shape_thread_count_reads_as_zero() -> None:
    """`^[0-9]+$` or 0, so a string, a negative or a float never reaches
    `((...))` where it would be a syntax error rather than a decision."""
    for value in ("many", -1, 1.5, None):
        fixtures = dict(BASE_FIXTURES)
        fixtures["pr.json"] = pr_json(unresolved_threads=value)
        _code, out, _, _ = _sides("threads-%r" % value, EVENT_ARGS, fixtures=fixtures, env=ARMED)
        assert _decision(out)["mode"] == "done", value


def test_an_unhandled_conclusion() -> None:
    for conclusion in ("skipped", "neutral", "timed_out", "action_required"):
        fixtures = dict(BASE_FIXTURES)
        fixtures["event.json"] = event_json(conclusion)
        _code, out, _, _ = _sides(
            "unhandled-%s" % conclusion, EVENT_ARGS, fixtures=fixtures, env=ARMED
        )
        assert _decision(out)["reason"] == (
            "unhandled-conclusion: '%s' is not an actionable run conclusion" % conclusion
        )


# --------------------------------------------------------------------------- Model resolution and the campaign hand-off ---------------------------------------------------------------------------


def test_model_resolution_in_the_designs_order() -> None:
    """dispatch input > campaign record > default, and an unknown value at
    either level degrades to the default WITH A WARNING rather than failing the
    round after the runner has been paid for."""
    fixtures = dict(BASE_FIXTURES)
    # Default.
    _, out, err, _ = _sides("model-default", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    assert _decision(out)["model"] == "claude-sonnet-5"
    assert b"falling back" not in err
    # Campaign record.
    fixtures["pr.json"] = pr_json(labels=[])
    fixtures["state.md"] = state_body(
        rounds=1, campaign="open", rounds_max="9", model="claude-opus-5"
    )
    argv = [*EVENT_ARGS, "--state", "state.md"]
    _, out, _, _ = _sides("model-campaign", argv, fixtures=fixtures, env=ARMED)
    assert _decision(out)["model"] == "claude-opus-5"
    # Dispatch input BEATS the campaign record.
    fixtures["event.json"] = event_json(
        dispatch={"actor": "operator", "pr_input": "5", "model": "claude-sonnet-5"}
    )
    _, out, _, _ = _sides("model-dispatch", argv, fixtures=fixtures, env=ARMED)
    assert _decision(out)["model"] == "claude-sonnet-5"
    # An unknown dispatch model is a TYPO, not an instruction.
    fixtures["event.json"] = event_json(
        dispatch={"actor": "operator", "pr_input": "5", "model": "gpt-9"}
    )
    _, out, err, _ = _sides("model-typo", argv, fixtures=fixtures, env=ARMED)
    assert _decision(out)["model"] == "claude-sonnet-5"
    assert (
        b"model 'gpt-9' is not one of claude-sonnet-5,claude-opus-5; falling back to "
        b"claude-sonnet-5" in err
    ), err
    # And the warning fires even on a path that ends in a refusal, because it is emitted before the fork guard.
    fixtures["pr.json"] = pr_json(labels=[], head_repo="attacker/console")
    _code, out, err, _ = _sides("model-typo-refused", argv, fixtures=fixtures, env=ARMED)
    assert b"falling back to claude-sonnet-5" in err
    assert _decision(out)["decision"] == "no-go"


def test_the_campaign_field_carried_into_the_next_write() -> None:
    """`campaign` on the decision line is what the NEXT state write records, not
    what this round read. Three arms, and the third is the one with a guard."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[])
    argv = [*EVENT_ARGS, "--state", "state.md"]
    # done + an OPEN campaign -> closed.
    fixtures["state.md"] = state_body(rounds=1, campaign="open", rounds_max="9")
    _, out, _, _ = _sides("campaign-close", argv, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert (decision["mode"], decision["campaign"]) == ("done", "closed")
    # done + NO campaign -> still none, never `closed`.
    fixtures["pr.json"] = pr_json()
    fixtures["state.md"] = state_body(rounds=1, campaign="none", rounds_max="9")
    _, out, _, _ = _sides("campaign-none", argv, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert (decision["mode"], decision["campaign"]) == ("done", "none")
    # A label-armed FIX round carries an open campaign forward untouched.
    fixtures["event.json"] = event_json("failure")
    fixtures["state.md"] = state_body(rounds=1, campaign="open", rounds_max="9")
    _code, out, _, _ = _sides("campaign-carry", argv, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert (decision["armed_by"], decision["campaign"]) == ("label", "open")


def test_round_cap_resolution_order() -> None:
    """dispatch > campaign > AUTOPILOT_MAX_ROUNDS > 25."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[])
    fixtures["state.md"] = state_body(rounds=1, campaign="open", rounds_max="9")
    argv = [*EVENT_ARGS, "--state", "state.md"]
    env = dict(ARMED)
    env["AUTOPILOT_MAX_ROUNDS"] = "13"
    _, out, _, _ = _sides("cap-campaign", argv, fixtures=fixtures, env=env)
    assert _decision(out)["rounds_max"] == 9, "the campaign beats the repo variable"
    fixtures["event.json"] = event_json(
        dispatch={"actor": "operator", "pr_input": "5", "max_rounds": "4"}
    )
    _, out, _, _ = _sides("cap-dispatch", argv, fixtures=fixtures, env=env)
    assert _decision(out)["rounds_max"] == 4
    # A dispatch max_rounds of 0 or out of shape falls through to the campaign.
    for value in ("0", "", "abc", "99999"):
        fixtures["event.json"] = event_json(
            dispatch={"actor": "operator", "pr_input": "5", "max_rounds": value}
        )
        _, out, _, _ = _sides("cap-dispatch-%r" % value, argv, fixtures=fixtures, env=env)
        assert _decision(out)["rounds_max"] == 9, value
    # With no campaign either, the repo variable wins.
    fixtures["state.md"] = state_body(rounds=1, campaign="open", rounds_max="0")
    fixtures["event.json"] = event_json(
        dispatch={"actor": "operator", "pr_input": "5", "max_rounds": "0"}
    )
    _code, out, _, _ = _sides("cap-env", argv, fixtures=fixtures, env=env)
    assert _decision(out)["rounds_max"] == 13


# --------------------------------------------------------------------------- Bash arithmetic, both halves ---------------------------------------------------------------------------


def test_the_campaign_cap_cannot_carry_an_octal_because_jq_launders_it() -> None:
    """MEASURED, AND IT REFUTES THE OBVIOUS GUESS.

    `state-comment.sh fields` emits `rounds_max` through `jq --argjson`, which prints 12 for the input `012`, so the value the gate reads back from a state comment is ALREADY decimal. A test aimed here would pass while proving nothing about bash's grammar. The env-var and dispatch paths below are the
    ones that actually reach `((...))` with the zero intact."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[])
    fixtures["state.md"] = state_body(rounds=10, campaign="open", rounds_max="012")
    _code, out, _, _ = _sides(
        "octal-campaign", [*EVENT_ARGS, "--state", "state.md"], fixtures=fixtures, env=ARMED
    )
    decision = _decision(out)
    assert decision["rounds_max"] == 12
    assert decision["armed_by"] == "campaign", "10 < 12, decimal, so the campaign re-arms"


def test_an_octal_round_cap_is_enforced_as_octal_and_reported_as_decimal() -> None:
    """`AUTOPILOT_MAX_ROUNDS=012` is TEN to `((...))` and TWELVE to jq.

    A twin inconsistency, preserved because it decides where a campaign stops. The case that proves it: ten recorded rounds against a cap that READS as 12
    still hits the cap."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["state.md"] = state_body(rounds=10, campaign="none", rounds_max="0")
    argv = [*EVENT_ARGS, "--state", "state.md"]
    env = dict(ARMED)
    env["AUTOPILOT_MAX_ROUNDS"] = "012"
    _, out, _, _ = _sides("octal-cap", argv, fixtures=fixtures, env=env)
    decision = _decision(out)
    assert decision["rounds_max"] == 12, "jq reads the leading zero as decimal"
    assert decision["reason"] == (
        "round-cap: 10 rounds recorded, cap is 012; escalating to the operator is the design "
        "working"
    ), decision["reason"]
    # Nine rounds is still under the OCTAL cap of ten, so the round runs.
    fixtures["state.md"] = state_body(rounds=9, campaign="none", rounds_max="0")
    _, out, _, _ = _sides("octal-cap-under", argv, fixtures=fixtures, env=env)
    assert _decision(out)["decision"] == "go"
    # And the same grammar on the thread count, which arrives as a JSON STRING.
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(unresolved_threads="012")
    _code, out, _, _ = _sides("octal-threads", EVENT_ARGS, fixtures=fixtures, env=ARMED)
    decision = _decision(out)
    assert decision["mode"] == "review-response"
    assert decision["reason"] == "unresolved-threads: 012 review thread(s) outstanding"


def test_an_invalid_octal_round_cap() -> None:
    """`08` is a bash arithmetic ERROR that evaluates as false.

    THE ONE FILTERED CASE IN THIS FILE. Exit code, stdout and the gh log are compared byte for byte; the bash diagnostic (which carries the twin's script path and line number, unreproducible from Python) is dropped from BOTH sides and its presence on the twin's side is asserted, so the filter cannot become a way of hiding a divergence that is not this one.

    THE DIRECTION MATTERS: the error reads as FALSE, so the cap is not reached and the round RUNS. A malformed cap fails open, which is a finding about the
    twin rather than about this port."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["state.md"] = state_body(rounds=10, campaign="none", rounds_max="0")
    env = dict(ARMED)
    env["AUTOPILOT_MAX_ROUNDS"] = "08"
    _code, out, _, _ = _sides(
        "octal-invalid",
        [*EVENT_ARGS, "--state", "state.md"],
        fixtures=fixtures,
        env=env,
        filter_arith=True,
    )
    decision = _decision(out)
    assert decision["rounds_max"] == 8, "jq reads 08 as 8 while bash refuses it entirely"
    assert decision["decision"] == "go", "a malformed cap fails OPEN"
    assert decision["round"] == 11


# --------------------------------------------------------------------------- The two preserved hazards ---------------------------------------------------------------------------


def test_a_mistyped_state_path_is_silently_no_state() -> None:
    """HAZARD 1, PRESERVED AND PINNED. `--state` is `[[ -n && -s ]]`, never
    `require_file`, so a typo reads as "no state comment yet": the round counter resets to 1 and an exhausted campaign is invisible. Fail OPEN, which is the wrong direction for this file; fixing it changes a live workflow step's
    contract, so it is the cutover box's call."""
    fixtures = dict(BASE_FIXTURES)
    fixtures["pr.json"] = pr_json(labels=[])
    fixtures["state.md"] = state_body(rounds=9, campaign="open", rounds_max="9")
    _, out, _, _ = _sides(
        "state-real", [*EVENT_ARGS, "--state", "state.md"], fixtures=fixtures, env=ARMED
    )
    assert _decision(out)["reason"].startswith("not-armed:"), "the cap is reached"
    _, out, err, _ = _sides(
        "state-typo", [*EVENT_ARGS, "--state", "stat.md"], fixtures=fixtures, env=ARMED
    )
    decision = _decision(out)
    assert decision["round"] == 1, "a typo reset the round counter"
    assert decision["campaign"] == "none"
    assert err == b"", "and it said nothing at all: %r" % err
    # The same silence for --failed-jobs and --watchdog.
    _code, out, err, _ = _sides(
        "watchdog-typo",
        [*EVENT_ARGS, "--watchdog", "nope.txt"],
        fixtures=BASE_FIXTURES,
        env=ARMED,
    )
    assert _decision(out)["decision"] == "go"
    assert err == b""


def test_the_allowlist_strips_interior_whitespace() -> None:
    """HAZARD 2, PRESERVED AND PINNED. `${item//[[:space:]]/}` deletes every
    whitespace character rather than trimming the ends, so `a b` allowlists `ab`. GitHub logins cannot contain a space, so this cannot admit a real
    account today; it is pinned because it guards a model invocation."""
    fixtures = dict(BASE_FIXTURES)
    # Both trust checks read the same list here (APPLIER falls back to AUTHOR), so both names have to be the one the entry collapses to; setting only the author gets `applier-not-allowlisted` and proves nothing about hazard 2.
    fixtures["pr.json"] = pr_json(author="ab", label_applier="ab")
    env = {"AUTOPILOT_ENABLED": "true", "AUTOPILOT_AUTHOR_ALLOWLIST": "a b"}
    _, out, _, _ = _sides("interior-space", EVENT_ARGS, fixtures=fixtures, env=env)
    assert _decision(out)["decision"] == "go", "the twin admits 'ab' from an entry of 'a b'"
    # CONTROL, so the case is not simply "everything is admitted": the entry as written still does not admit the string with the space in it.
    fixtures["pr.json"] = pr_json(author="a b", label_applier="a b")
    _code, out, _, _ = _sides("interior-space-control", EVENT_ARGS, fixtures=fixtures, env=env)
    assert _decision(out)["reason"].startswith("author-not-allowlisted:")


def test_a_multi_line_allowlist_stops_at_the_first_line() -> None:
    """`read` reads ONE line, so a wrapped repo variable admits only the first
    line's names. Fail CLOSED, which is the right direction, and it is a real
    shape: a pasted list arrives wrapped."""
    fixtures = dict(BASE_FIXTURES)
    env = {"AUTOPILOT_ENABLED": "true", "AUTOPILOT_AUTHOR_ALLOWLIST": "someone\noperator"}
    _, out, _, _ = _sides("allowlist-wrapped", EVENT_ARGS, fixtures=fixtures | {}, env=env)
    assert _decision(out)["reason"].startswith("author-not-allowlisted:")
    env["AUTOPILOT_AUTHOR_ALLOWLIST"] = "operator\nsomeone"
    _code, out, _, _ = _sides("allowlist-first", EVENT_ARGS, fixtures=BASE_FIXTURES, env=env)
    assert _decision(out)["decision"] == "go"


# --------------------------------------------------------------------------- The pure helpers, driven directly and in BOTH directions ---------------------------------------------------------------------------


def test_bash_arith_reproduces_bashs_literal_grammar() -> None:
    assert ag.bash_arith("") == 0
    assert ag.bash_arith("0") == 0
    assert ag.bash_arith("25") == 25
    assert ag.bash_arith("012") == 10, "a leading zero is OCTAL, not decimal"
    assert ag.bash_arith("0x1f") == 31
    assert ag.bash_arith("08") is None, "an invalid octal digit is an ERROR, not a zero"
    assert ag.bash_arith("null") == 0, "a bare word is an unset variable name"
    assert ag.bash_arith("  7  ") == 7
    assert ag.bash_int("08") == 0, "the value-only wrapper flattens it; see its docstring"


def test_bash_cmp_treats_an_arithmetic_error_as_false_not_as_zero() -> None:
    """THE DIVERGENCE THE DIFFERENTIAL CAUGHT, pinned as a unit as well.

    `((10 >= 08))` is FALSE. Reading `08` as 0 makes it TRUE, which turns a
    fail-open hazard in the twin into a refusal in the port. Both directions, because only the second one catches a `bash_cmp` that returns False for
    everything."""
    assert ag.bash_cmp("10", ">=", "08") is False
    assert ag.bash_cmp("08", ">", "0") is False
    assert ag.bash_cmp("10", ">=", "012") is True, "10 >= octal 10"
    assert ag.bash_cmp("9", ">=", "012") is False
    assert ag.bash_cmp("0", "==", "0") is True
    assert ag.bash_cmp("2", ">", "0") is True
    assert ag.bash_cmp("0", "<", "25") is True


def test_in_csv_allowlist_both_directions() -> None:
    assert ag.in_csv_allowlist("operator", "operator") is True
    assert ag.in_csv_allowlist("operator", " a , operator , b ") is True
    assert ag.in_csv_allowlist("operator", "") is False, "an empty allowlist admits nobody"
    assert ag.in_csv_allowlist("operator", ",,,") is False
    assert ag.in_csv_allowlist("", "a,,b") is False, "an empty entry never matches"
    assert ag.in_csv_allowlist("operator", "operator2") is False, "exact names, not prefixes"
    assert ag.in_csv_allowlist("ab", "a b") is True, "hazard 2"
    assert ag.in_csv_allowlist("operator", "x\noperator") is False, "one line only"


def test_non_empty_file_is_dash_s_and_not_require_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        assert ag.non_empty_file("") is False
        assert ag.non_empty_file(str(base / "absent")) is False
        empty = base / "empty"
        empty.write_text("", encoding="utf-8")
        assert ag.non_empty_file(str(empty)) is False
        full = base / "full"
        full.write_text("x", encoding="utf-8")
        assert ag.non_empty_file(str(full)) is True


def test_the_emit_program_and_its_key_order() -> None:
    """The decision line's twelve keys, in program order, are the contract with
    the workflow step that reads them."""
    for key in (
        "decision",
        "mode",
        "reason",
        "round",
        "push_allowed",
        "armed_by",
        "model",
        "rounds_max",
        "campaign",
        "dispatch_trusted",
        "sig",
        "sig_count",
    ):
        assert "%s:" % key in ag.EMIT_PROGRAM, key
    gate = ag.Gate()
    decided = gate.emit("go", "fix", "because")
    assert decided.code == 0
    assert list(json.loads(decided.payload).keys()) == [
        "decision",
        "mode",
        "reason",
        "round",
        "push_allowed",
        "armed_by",
        "model",
        "rounds_max",
        "campaign",
        "dispatch_trusted",
        "sig",
        "sig_count",
    ]


def test_the_campaign_hand_off_is_a_pure_function_of_three_inputs() -> None:
    """`emit`'s campaign arm, driven directly, so all four combinations are
    exercised without needing four fixtures."""
    for campaign, decision, mode, armed, expected in (
        ("open", "go", "done", "label", "closed"),
        ("none", "go", "done", "label", "none"),
        ("none", "go", "fix", "dispatch", "open"),
        ("open", "no-go", "none", "dispatch", "open"),
        ("closed", "go", "fix", "label", "closed"),
    ):
        gate = ag.Gate()
        gate.campaign_state = campaign
        gate.armed_by = armed
        payload = json.loads(gate.emit(decision, mode, "r").payload)
        assert payload["campaign"] == expected, (campaign, decision, mode, armed)
