"""`rediacc_ci.autopilot.autopilot_gate`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/autopilot/autopilot-gate.sh` and the port over identical private trees and compared the exit code, stdout, stderr and the `gh` call log, for every case.

The ledger `.ci/shadow/w7p6-autopilot-gate.observations.jsonl` recorded that comparison over five distinct trees, every one of them EQUIVALENT; the row count is stated here from the file rather than carried forward from the sentence that used to claim it.

Every case now compares against `goldens/autopilot-gate/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree; each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE TWIN'S OWN SENTENCE IS THIS FILE'S BRIEF: "an untested branch in this file is an untested security decision". The subject is the arming decision for the whole autonomy loop, a decision tree with twenty-seven distinct exits, and a port that quietly dropped one of them would look exactly like a port that kept it, on every input except the one the dropped check existed for. So the
cases walk the tree ARM BY ARM, in the twin's own order, and each is named after the refusal it proves.

THE PURITY CLAIM IS MECHANICAL, NOT ASSERTED. The gate advertises itself as running no network call, and every case runs with a POISON `gh` first on PATH that records its argv and exits 66. `test_the_gate_never_reaches_the_network` proves the poison would be noticed, `--- calls ---` carries the log into every recording, and `test_no_recording_ever_called_gh` walks all of them, so a
port that grew a `gh` call fails the whole corpus rather than one case.

STDOUT IS THE WHOLE PRODUCT HERE: one JSON line whose twelve keys the calling workflow reads, so a port that reached the right verdict with the wrong `rounds_max` would still be a different gate. The recordings are compared as BYTES, and several cases then assert the decoded object field by field on top of that, because "the two sides agree" and "the two sides are right" are
different claims and only the second catches a shared misreading of the twin.

ONE CASE IS COMPARED BY SHAPE, and it is the only filtering in this file. `((08 > 0))` is a bash arithmetic ERROR whose diagnostic carries the twin's script path and line number, which no port can reproduce without lying about where it came from. `an-invalid-octal-repo-variable-cap` compares the exit code, stdout and the call log byte for byte and drops that single line from the
recorded stderr, whose presence there is asserted so the filter cannot become a way of hiding a different divergence.

WHAT IS MASKED, and it is one path in that same recording: the repository root becomes `<ROOT>`, because a recording is compared from a different checkout. Nothing else is touched. Every fixture path is relative, every diagnostic names it as the caller spelled it, and the decision line carries no path at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import autopilot_gate as ag
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
SLUG = "autopilot-gate"

TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "autopilot-gate.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "autopilot_gate.py"
BASH = shutil.which("bash") or "/bin/bash"

ROOT_PLACEHOLDER = "<ROOT>"
CALLS_MARKER = "--- calls ---\n"
ARITH_ERROR = "value too great for base"

# A `gh` that cannot succeed and cannot be silent. The gate is documented PURE; this is what turns that documentation into a test result.
POISON_GH = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(sys.argv[1:]) + "\\n")
sys.stderr.write("poison gh: the autopilot gate must not reach the network\\n")
sys.exit(66)
"""

HEADER = "### Autopilot state (machine-maintained, do not edit)"

EVENT_ARGS = ["--classify", "--event", "event.json", "--pr", "pr.json"]
STATE_ARGS = [*EVENT_ARGS, "--state", "state.md"]
JOBS_ARGS = [*EVENT_ARGS, "--failed-jobs", "jobs.txt"]
JOBS_STATE_ARGS = [*EVENT_ARGS, "--failed-jobs", "jobs.txt", "--state", "state.md"]
WATCHDOG_ARGS = [*EVENT_ARGS, "--watchdog", "watchdog.txt"]

ENABLED = {"AUTOPILOT_ENABLED": "true"}
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
    """A rendered state comment, in `state_comment render`'s exact shape.

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

    `LC_ALL=C sort` then sha256, first 8 hex. Recomputed here rather than imported from the port, so a fixture that must MATCH a stored signature is not built by the same code the case is testing.
    """
    lines = sorted(line for line in text.split("\n") if line != "")
    blob = "".join(line + "\n" for line in lines).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:8]


BASE_FIXTURES = {"event.json": event_json(), "pr.json": pr_json()}

JOBS = "quality\nbuild\n"
JOBS_SIG = sig_of(JOBS)
DISPATCH = {"actor": "operator", "pr_input": "5", "model": "", "max_rounds": ""}


def wired(argv: list[str] = EVENT_ARGS, *, files=None, env=None) -> dict[str, typing.Any]:
    """One case's wiring: the argv, the fixture files on top of the two the gate always reads, and the environment."""
    fixtures = dict(BASE_FIXTURES)
    fixtures.update(files or {})
    return {"argv": list(argv), "fixtures": fixtures, "env": dict(env or {})}


def stuck_state(sig_count: str) -> str:
    return state_body(
        rounds=2, campaign="open", rounds_max="25", last_sig=JOBS_SIG, sig_count=sig_count
    )


# name -> how the run is wired. Ordered as the twin's decision tree is ordered, so a reader walking this table walks the gate.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    # --------------------------------------------- the LOUD exits: a wiring bug must never read as a quiet no-go
    "usage-with-no-arguments": wired([]),
    "usage-with-a-bare-classify-word": wired(["classify"]),
    "usage-with-only-a-pr-flag": wired(["--pr", "pr.json"]),
    "usage-with-help": wired(["--help"]),
    "missing-both-fixture-flags": wired(["--classify"]),
    "missing-the-pr-flag": wired(["--classify", "--event", "event.json"]),
    "missing-the-event-flag": wired(["--classify", "--pr", "pr.json"]),
    "an-empty-event-flag": wired(["--classify", "--event=", "--pr", "pr.json"]),
    "an-event-file-that-does-not-exist": wired(
        ["--classify", "--event", "nope.json", "--pr", "pr.json"]
    ),
    "a-pr-file-that-does-not-exist": wired(
        ["--classify", "--event", "event.json", "--pr", "gone.json"]
    ),
    "an-event-that-is-garbage": wired(files={"event.json": "not json at all\n"}),
    "an-event-that-is-null": wired(files={"event.json": "null\n"}),
    "an-event-that-is-false": wired(files={"event.json": "false\n"}),
    "a-pr-that-is-garbage": wired(files={"pr.json": "{oops\n"}),
    "a-pr-that-is-null": wired(files={"pr.json": "null\n"}),
    "an-event-with-no-conclusion": wired(
        files={"event.json": json.dumps({"workflow_run": {"id": 1}}) + "\n"}, env=ARMED
    ),
    "an-event-with-no-conclusion-and-the-stage-off": wired(
        files={"event.json": json.dumps({"workflow_run": {"id": 1}}) + "\n"}
    ),
    "an-event-with-no-run-id": wired(
        files={"event.json": json.dumps({"workflow_run": {"conclusion": "success"}}) + "\n"},
        env=ARMED,
    ),
    # --------------------------------------------- the master stage flag
    "the-stage-flag-absent": wired(),
    "the-stage-flag-empty": wired(env={"AUTOPILOT_ENABLED": ""}),
    "the-stage-flag-in-upper-case": wired(env={"AUTOPILOT_ENABLED": "TRUE"}),
    "the-stage-flag-as-one": wired(env={"AUTOPILOT_ENABLED": "1"}),
    "the-stage-flag-as-yes": wired(env={"AUTOPILOT_ENABLED": "yes"}),
    "the-stage-flag-with-a-trailing-space": wired(env={"AUTOPILOT_ENABLED": "true "}),
    "push-allowed-is-reported-on-a-refusal": wired(env={"AUTOPILOT_ALLOW_PUSH": "true"}),
    "push-allowed-only-for-the-literal-true": wired(env={"AUTOPILOT_ALLOW_PUSH": "TRUE"}),
    # --------------------------------------------- the fork guard, in both records
    "fork-in-the-run-record": wired(
        files={"event.json": event_json(head_repo="attacker/console")}, env=ARMED
    ),
    "an-absent-head-repository-is-not-a-fork": wired(
        files={"event.json": event_json(head_repo=None)}, env=ARMED
    ),
    "fork-in-the-pr-record": wired(
        files={"pr.json": pr_json(head_repo="attacker/console")}, env=ARMED
    ),
    "an-empty-pr-head-repo": wired(files={"pr.json": pr_json(head_repo="")}, env=ARMED),
    # --------------------------------------------- the escalation latch and its order
    "blocked-beats-the-label": wired(
        files={"pr.json": pr_json(labels=["autopilot", "autopilot-blocked"])}, env=ARMED
    ),
    "blocked-beats-a-dispatch": wired(
        files={
            "pr.json": pr_json(labels=["autopilot-blocked"]),
            "event.json": event_json(dispatch=DISPATCH),
        },
        env=ARMED,
    ),
    "the-blocked-label-alone-at-index-zero": wired(
        files={"pr.json": pr_json(labels=["autopilot-blocked"])}, env=ARMED
    ),
    "the-arming-label-alone-at-index-zero": wired(
        files={"pr.json": pr_json(labels=["autopilot"])}, env=ARMED
    ),
    # --------------------------------------------- the three arming paths
    "not-armed-names-what-it-looked-for": wired(files={"pr.json": pr_json(labels=[])}, env=ARMED),
    "not-armed-with-a-renamed-label": wired(
        files={"pr.json": pr_json(labels=[])},
        env={**ARMED, "AUTOPILOT_LABEL": "babysit"},
    ),
    "armed-by-a-renamed-label": wired(
        files={"pr.json": pr_json(labels=["babysit"])},
        env={**ARMED, "AUTOPILOT_LABEL": "babysit"},
    ),
    "a-dispatch-arms-round-one": wired(
        files={"pr.json": pr_json(labels=[]), "event.json": event_json(dispatch=DISPATCH)},
        env=ARMED,
    ),
    "a-dispatch-that-buys-a-fix-round-opens-the-campaign": wired(
        files={
            "pr.json": pr_json(labels=[]),
            "event.json": event_json("failure", dispatch={"actor": "operator", "pr_input": "5"}),
        },
        env=ARMED,
    ),
    "a-dispatch-with-no-pr-input": wired(
        files={
            "pr.json": pr_json(labels=[]),
            "event.json": event_json(dispatch={"actor": "operator"}),
        },
        env=ARMED,
    ),
    "an-open-campaign-carries-the-loop": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=2, campaign="open", rounds_max="9"),
        },
        env=ARMED,
    ),
    "a-closed-campaign-does-not-arm": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=2, campaign="closed", rounds_max="9"),
        },
        env=ARMED,
    ),
    "an-open-campaign-with-its-cap-spent": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=9, campaign="open", rounds_max="9"),
        },
        env=ARMED,
    ),
    # --------------------------------------------- the two trust checks and the order between them
    "the-author-allowlist-absent": wired(env=ENABLED),
    "the-author-allowlist-empty": wired(env={**ENABLED, "AUTOPILOT_AUTHOR_ALLOWLIST": ""}),
    "the-author-allowlist-naming-others": wired(
        env={**ENABLED, "AUTOPILOT_AUTHOR_ALLOWLIST": "somebody,else"}
    ),
    "the-author-allowlist-with-a-prefix-only": wired(
        env={**ENABLED, "AUTOPILOT_AUTHOR_ALLOWLIST": "operator2"}
    ),
    "the-author-allowlist-with-spaces-around-the-name": wired(
        env={**ENABLED, "AUTOPILOT_AUTHOR_ALLOWLIST": "a, operator ,b"}
    ),
    "a-strangers-unarmed-pr-is-not-armed-first": wired(
        files={"pr.json": pr_json(labels=[], author="stranger")}, env=ARMED
    ),
    "an-applier-who-is-not-allowlisted": wired(
        files={"pr.json": pr_json(label_applier="drive-by")}, env=ARMED
    ),
    "an-applier-allowlist-that-overrides-the-author-list": wired(
        env={**ARMED, "AUTOPILOT_APPLIER_ALLOWLIST": "someone-else"}
    ),
    "an-applier-allowlist-that-names-the-applier": wired(
        env={**ARMED, "AUTOPILOT_APPLIER_ALLOWLIST": "operator"}
    ),
    "a-dispatching-actor-who-is-not-allowlisted": wired(
        files={
            "pr.json": pr_json(labels=[]),
            "event.json": event_json(dispatch={"actor": "drive-by", "pr_input": "5"}),
        },
        env=ARMED,
    ),
    "armed-by-label-and-dispatched-by-a-stranger": wired(
        files={"event.json": event_json(dispatch={"actor": "drive-by", "pr_input": ""})},
        env=ARMED,
    ),
    "armed-by-label-and-dispatched-by-the-operator": wired(
        files={"event.json": event_json(dispatch={"actor": "operator", "pr_input": ""})},
        env=ARMED,
    ),
    "a-campaign-round-with-a-hostile-applier": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[], label_applier="drive-by"),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
        },
        env=ARMED,
    ),
    # --------------------------------------------- dedup, the round cap, the watchdog
    "a-duplicate-of-an-already-handled-run": wired(
        STATE_ARGS,
        files={"state.md": state_body(run_ids=["4242/1"], campaign="none", rounds_max="9")},
        env=ARMED,
    ),
    "a-second-attempt-of-the-same-run": wired(
        STATE_ARGS,
        files={
            "state.md": state_body(run_ids=["4242/1"], campaign="none", rounds_max="9"),
            "event.json": event_json(attempt=2),
        },
        env=ARMED,
    ),
    "a-run-id-that-is-a-prefix-of-the-recorded-one": wired(
        STATE_ARGS,
        files={
            "state.md": state_body(run_ids=["4242/1"], campaign="none", rounds_max="9"),
            "event.json": event_json(run_id=424),
        },
        env=ARMED,
    ),
    "the-round-cap-reached": wired(
        STATE_ARGS,
        files={"state.md": state_body(rounds=3, campaign="none", rounds_max="0")},
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "3"},
    ),
    "the-round-cap-not-yet-reached": wired(
        STATE_ARGS,
        files={"state.md": state_body(rounds=3, campaign="none", rounds_max="0")},
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "4"},
    ),
    "max-rounds-empty": wired(env={**ARMED, "AUTOPILOT_MAX_ROUNDS": ""}),
    "max-rounds-not-a-number": wired(env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "abc"}),
    "max-rounds-of-five-digits": wired(env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "99999"}),
    "max-rounds-that-is-negative": wired(env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "-1"}),
    "max-rounds-of-seven": wired(env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "7"}),
    "the-watchdog-holds-a-pending-rerun": wired(
        WATCHDOG_ARGS, files={"watchdog.txt": "pending_rerun 4242\n"}, env=ARMED
    ),
    "an-empty-watchdog-file-is-not-a-hold": wired(
        WATCHDOG_ARGS, files={"watchdog.txt": ""}, env=ARMED
    ),
    # --------------------------------------------- mode selection, one case per arm
    "a-failed-run-buys-a-fix-round": wired(files={"event.json": event_json("failure")}, env=ARMED),
    "the-signature-with-quality-first": wired(
        JOBS_ARGS,
        files={"event.json": event_json("failure"), "jobs.txt": "quality\nbuild\n"},
        env=ARMED,
    ),
    "the-signature-with-build-first": wired(
        JOBS_ARGS,
        files={"event.json": event_json("failure"), "jobs.txt": "build\nquality\n"},
        env=ARMED,
    ),
    "the-third-round-on-one-unchanged-failure-set": wired(
        JOBS_STATE_ARGS,
        files={
            "event.json": event_json("failure"),
            "jobs.txt": JOBS,
            "state.md": stuck_state("2"),
        },
        env=ARMED,
    ),
    "the-second-round-on-one-unchanged-failure-set": wired(
        JOBS_STATE_ARGS,
        files={
            "event.json": event_json("failure"),
            "jobs.txt": JOBS,
            "state.md": stuck_state("1"),
        },
        env=ARMED,
    ),
    "a-changed-failure-set-resets-the-counter": wired(
        JOBS_STATE_ARGS,
        files={
            "event.json": event_json("failure"),
            "jobs.txt": "something-else\n",
            "state.md": stuck_state("2"),
        },
        env=ARMED,
    ),
    "an-empty-failed-jobs-file-never-matches-a-stored-signature": wired(
        JOBS_STATE_ARGS,
        files={
            "event.json": event_json("failure"),
            "jobs.txt": "",
            "state.md": state_body(
                rounds=1, campaign="open", rounds_max="25", last_sig="none", sig_count="3"
            ),
        },
        env=ARMED,
    ),
    "a-cancelled-run-with-failed-jobs": wired(
        JOBS_ARGS,
        files={"event.json": event_json("cancelled"), "jobs.txt": "quality\nbuild\n\n"},
        env=ARMED,
    ),
    "a-cancelled-run-whose-head-moved-on": wired(
        files={"event.json": event_json("cancelled", head_sha="oldsha")}, env=ARMED
    ),
    "a-cancelled-run-with-nothing-to-act-on": wired(
        files={"event.json": event_json("cancelled")}, env=ARMED
    ),
    "a-cancelled-run-with-no-head-sha": wired(
        files={"event.json": event_json("cancelled", head_sha="")}, env=ARMED
    ),
    "success-with-a-red-review-gate-and-no-threads": wired(
        files={"pr.json": pr_json(review_gate_red=True, unresolved_threads=0)}, env=ARMED
    ),
    "success-with-a-red-review-gate-and-threads": wired(
        files={"pr.json": pr_json(review_gate_red=True, unresolved_threads=3)}, env=ARMED
    ),
    "success-while-draft": wired(files={"pr.json": pr_json(draft=True)}, env=ARMED),
    "success-with-threads-only": wired(files={"pr.json": pr_json(unresolved_threads=2)}, env=ARMED),
    "success-with-nothing-outstanding": wired(env=ARMED),
    "a-red-review-gate-beats-a-draft": wired(
        files={"pr.json": pr_json(review_gate_red=True, draft=True, unresolved_threads=0)},
        env=ARMED,
    ),
    "a-thread-count-that-is-a-word": wired(
        files={"pr.json": pr_json(unresolved_threads="many")}, env=ARMED
    ),
    "a-thread-count-that-is-negative": wired(
        files={"pr.json": pr_json(unresolved_threads=-1)}, env=ARMED
    ),
    "a-thread-count-that-is-a-float": wired(
        files={"pr.json": pr_json(unresolved_threads=1.5)}, env=ARMED
    ),
    "a-thread-count-that-is-null": wired(
        files={"pr.json": pr_json(unresolved_threads=None)}, env=ARMED
    ),
    "an-unhandled-conclusion-skipped": wired(
        files={"event.json": event_json("skipped")}, env=ARMED
    ),
    "an-unhandled-conclusion-neutral": wired(
        files={"event.json": event_json("neutral")}, env=ARMED
    ),
    "an-unhandled-conclusion-timed-out": wired(
        files={"event.json": event_json("timed_out")}, env=ARMED
    ),
    "an-unhandled-conclusion-action-required": wired(
        files={"event.json": event_json("action_required")}, env=ARMED
    ),
    # --------------------------------------------- model resolution and the campaign hand-off
    "the-default-model": wired(env=ARMED),
    "the-model-from-the-campaign-record": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(
                rounds=1, campaign="open", rounds_max="9", model="claude-opus-5"
            ),
        },
        env=ARMED,
    ),
    "the-model-from-the-dispatch-input": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(
                rounds=1, campaign="open", rounds_max="9", model="claude-opus-5"
            ),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "model": "claude-sonnet-5"}
            ),
        },
        env=ARMED,
    ),
    "an-unknown-dispatch-model": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(
                rounds=1, campaign="open", rounds_max="9", model="claude-opus-5"
            ),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "model": "gpt-9"}
            ),
        },
        env=ARMED,
    ),
    "an-unknown-model-on-a-refused-round": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[], head_repo="attacker/console"),
            "state.md": state_body(
                rounds=1, campaign="open", rounds_max="9", model="claude-opus-5"
            ),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "model": "gpt-9"}
            ),
        },
        env=ARMED,
    ),
    "done-closes-an-open-campaign": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
        },
        env=ARMED,
    ),
    "done-with-no-campaign-stays-none": wired(
        STATE_ARGS,
        files={"state.md": state_body(rounds=1, campaign="none", rounds_max="9")},
        env=ARMED,
    ),
    "a-label-armed-fix-round-carries-the-campaign": wired(
        STATE_ARGS,
        files={
            "event.json": event_json("failure"),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
        },
        env=ARMED,
    ),
    "the-campaign-cap-beats-the-repo-variable": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
        },
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "13"},
    ),
    "the-dispatch-cap-beats-the-campaign": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "max_rounds": "4"}
            ),
        },
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "13"},
    ),
    "a-dispatch-cap-of-zero": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "max_rounds": "0"}
            ),
        },
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "13"},
    ),
    "a-dispatch-cap-that-is-empty": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "max_rounds": ""}
            ),
        },
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "13"},
    ),
    "a-dispatch-cap-that-is-not-a-number": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "max_rounds": "abc"}
            ),
        },
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "13"},
    ),
    "a-dispatch-cap-of-five-digits": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="9"),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "max_rounds": "99999"}
            ),
        },
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "13"},
    ),
    "the-repo-variable-with-no-campaign-cap": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=1, campaign="open", rounds_max="0"),
            "event.json": event_json(
                dispatch={"actor": "operator", "pr_input": "5", "max_rounds": "0"}
            ),
        },
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "13"},
    ),
    # --------------------------------------------- bash arithmetic, both halves
    "a-campaign-cap-with-a-leading-zero": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=10, campaign="open", rounds_max="012"),
        },
        env=ARMED,
    ),
    "an-octal-repo-variable-cap-at-the-bound": wired(
        STATE_ARGS,
        files={"state.md": state_body(rounds=10, campaign="none", rounds_max="0")},
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "012"},
    ),
    "an-octal-repo-variable-cap-under-the-bound": wired(
        STATE_ARGS,
        files={"state.md": state_body(rounds=9, campaign="none", rounds_max="0")},
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "012"},
    ),
    "a-thread-count-with-a-leading-zero": wired(
        files={"pr.json": pr_json(unresolved_threads="012")}, env=ARMED
    ),
    "an-invalid-octal-repo-variable-cap": wired(
        STATE_ARGS,
        files={"state.md": state_body(rounds=10, campaign="none", rounds_max="0")},
        env={**ARMED, "AUTOPILOT_MAX_ROUNDS": "08"},
    ),
    # --------------------------------------------- the two preserved hazards
    "a-state-path-that-exists": wired(
        STATE_ARGS,
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=9, campaign="open", rounds_max="9"),
        },
        env=ARMED,
    ),
    "a-state-path-with-a-typo": wired(
        [*EVENT_ARGS, "--state", "stat.md"],
        files={
            "pr.json": pr_json(labels=[]),
            "state.md": state_body(rounds=9, campaign="open", rounds_max="9"),
        },
        env=ARMED,
    ),
    "a-watchdog-path-with-a-typo": wired([*EVENT_ARGS, "--watchdog", "nope.txt"], env=ARMED),
    "an-allowlist-entry-with-an-interior-space": wired(
        files={"pr.json": pr_json(author="ab", label_applier="ab")},
        env={**ENABLED, "AUTOPILOT_AUTHOR_ALLOWLIST": "a b"},
    ),
    "an-allowlist-entry-with-an-interior-space-control": wired(
        files={"pr.json": pr_json(author="a b", label_applier="a b")},
        env={**ENABLED, "AUTOPILOT_AUTHOR_ALLOWLIST": "a b"},
    ),
    "an-allowlist-that-wraps-onto-a-second-line": wired(
        env={**ENABLED, "AUTOPILOT_AUTHOR_ALLOWLIST": "someone\noperator"}
    ),
    "an-allowlist-whose-first-line-names-the-author": wired(
        env={**ENABLED, "AUTOPILOT_AUTHOR_ALLOWLIST": "operator\nsomeone"}
    ),
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce byte for byte. Compared by shape, in its own test.
DIVERGENT = ("an-invalid-octal-repo-variable-cap",)


def stub_bin(base: pathlib.Path) -> str:
    """The poison `gh` FIRST, then the real PATH.

    The real PATH is kept because the twin needed `jq`, `grep`, `sort`, `awk`, `sed`, `tr`, `mktemp`, `dirname`, `uname`, `cat` and `wc`, and because the state-comment renderer it spawned for real needed them too. Only `gh` is displaced, and `test_the_gate_never_reaches_the_network` proves the displacement took.
    """
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(POISON_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def run(
    tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path = PORT
) -> tuple[int, str, str, list[str]]:
    """One subject, once, over this case's own scratch directory.

    THE STREAMS ARE DECODED AS UTF-8 with no fallback: the decision line is JSON and every diagnostic is prose, so a case that ever produced a byte outside it would have failed the recording rather than been silently mangled.
    """
    kw = CASE_KW[name]
    base = tmp_path / "base"
    base.mkdir(parents=True, exist_ok=True)
    for rel, text in kw["fixtures"].items():
        (base / rel).write_text(text, encoding="utf-8")
    log = base / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
    }
    env.update(kw["env"])
    runner = BASH if subject.suffix == ".sh" else sys.executable
    proc = subprocess.run(
        [str(runner), str(subject), *kw["argv"]],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return (
        proc.returncode,
        proc.stdout.decode("utf-8").replace(str(ROOT), ROOT_PLACEHOLDER),
        proc.stderr.decode("utf-8").replace(str(ROOT), ROOT_PLACEHOLDER),
        calls,
    )


def render(code: int, stdout: str, stderr: str, calls: list[str]) -> str:
    return "%s%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        json.dumps(calls, indent=2),
    )


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, json.loads(calls)


def decision(name: str) -> dict:
    """The decision line of one recording, decoded."""
    return json.loads(recorded(name)[1])


def reason(name: str) -> str:
    return decision(name)["reason"]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[str]]:
    want = recorded(name)
    got = run(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the gh calls diverged: %r vs %r" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_ever_called_gh() -> None:
    """THE PURITY CLAIM, over the whole corpus rather than one case. The gate is documented as running no network call, and every recording carries the poison `gh`'s own log; one non-empty entry anywhere is a gate that reached out."""
    for name in CASES:
        assert recorded(name)[3] == [], name


def test_the_gate_never_reaches_the_network(tmp_path: pathlib.Path) -> None:
    """CONTROL for the corpus check above.

    Without this, "no gh call was logged" is equally consistent with the log never being written to by anything, and with the poison never being the `gh` a subject would find.
    """
    path = stub_bin(tmp_path)
    found = shutil.which("gh", path=path)
    assert found == str(tmp_path / "bin" / "gh"), "the poison gh is not first on PATH: %r" % found
    log = tmp_path / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [found, "api", "graphql"],
        capture_output=True,
        env={"FAKE_GH_LOG": str(log), "PATH": path},
        check=False,
    )
    assert proc.returncode == 66
    assert log.read_text(encoding="utf-8") == "api\tgraphql\n"


# --------------------------------------------------------------------------- The LOUD exits ---------------------------------------------------------------------------


def test_usage_when_the_mode_is_not_classify() -> None:
    """Both lines, and exit 2 rather than a no-go, including NO arguments at all, which is `${1:-}` reading as the empty string."""
    for name in (
        "usage-with-no-arguments",
        "usage-with-a-bare-classify-word",
        "usage-with-only-a-pr-flag",
        "usage-with-help",
    ):
        code, stdout, stderr, _ = recorded(name)
        assert code == 2, name
        assert stdout == "", name
        assert "usage: autopilot-gate.sh --classify --event <file> --pr <file>" in stderr, name
        assert "the gate is fixtures-only by design" in stderr, name


def test_usage_when_a_fixture_flag_is_missing() -> None:
    for name in (
        "missing-both-fixture-flags",
        "missing-the-pr-flag",
        "missing-the-event-flag",
        "an-empty-event-flag",
    ):
        code, stdout, stderr, _ = recorded(name)
        assert code == 2, name
        assert stdout == "", name
        assert "--event and --pr are required" in stderr, name


def test_a_fixture_that_does_not_exist_is_require_file_not_a_no_go() -> None:
    """Exit 1, `require_file`'s own sentence, and the EVENT is checked first."""
    code, _, stderr, _ = recorded("an-event-file-that-does-not-exist")
    assert code == 1
    assert "Required file 'nope.json' does not exist" in stderr
    code, _, stderr, _ = recorded("a-pr-file-that-does-not-exist")
    assert code == 1
    assert "Required file 'gone.json' does not exist" in stderr


def test_a_fixture_that_is_not_json() -> None:
    """`jq -e .`, and its two failure shapes.

    A PARSE failure and a `null` body are the same refusal here, and that is jq's rule rather than a choice: `jq -e` exits 1 when the last value is null or false. A port built on `json.loads` would accept `null` and then read every field off nothing.
    """
    for name in ("an-event-that-is-garbage", "an-event-that-is-null", "an-event-that-is-false"):
        code, stdout, stderr, _ = recorded(name)
        assert code == 2, name
        assert stdout == "", name
        assert "event payload is not valid JSON: event.json" in stderr, name
    for name in ("a-pr-that-is-garbage", "a-pr-that-is-null"):
        code, _, stderr, _ = recorded(name)
        assert code == 2, name
        assert "pr fixture is not valid JSON: pr.json" in stderr, name


def test_an_event_missing_its_run_identity() -> None:
    """Exit 2, AFTER the stage flag: a wiring bug is loud, but a disabled stage is still a no-go, so the ORDER of the two decides which one a misconfigured stage sees. The twin checked the flag first, and both recordings pin that."""
    code, stdout, stderr, _ = recorded("an-event-with-no-conclusion")
    assert code == 2
    assert stdout == ""
    assert "event payload lacks workflow_run.conclusion or .id" in stderr
    # The same fixture with the stage flag OFF is a no-go, not an exit 2.
    code, _, _, _ = recorded("an-event-with-no-conclusion-and-the-stage-off")
    assert code == 0
    assert reason("an-event-with-no-conclusion-and-the-stage-off").startswith("stage-flag-disabled")
    code, _, stderr, _ = recorded("an-event-with-no-run-id")
    assert code == 2
    assert "event payload lacks workflow_run.conclusion or .id" in stderr


# --------------------------------------------------------------------------- The master stage flag ---------------------------------------------------------------------------


def test_the_stage_flag_is_closed_by_default_and_by_anything_but_true() -> None:
    """FAIL CLOSED, and the whole decision line is checked: a no-go before any fixture has been read still carries round 1, sig_count 0 and armed_by none, which is what the workflow's next state write records."""
    code, stdout, _, _ = recorded("the-stage-flag-absent")
    assert code == 0
    assert stdout == (
        '{"decision":"no-go","mode":"none","reason":"stage-flag-disabled: AUTOPILOT_ENABLED '
        'is not \'true\' (absent means off, fail closed)","round":1,"push_allowed":false,'
        '"armed_by":"none","model":"claude-sonnet-5","rounds_max":25,"campaign":"none",'
        '"dispatch_trusted":false,"sig":"none","sig_count":0}\n'
    ), stdout
    for name in (
        "the-stage-flag-empty",
        "the-stage-flag-in-upper-case",
        "the-stage-flag-as-one",
        "the-stage-flag-as-yes",
        "the-stage-flag-with-a-trailing-space",
    ):
        assert decision(name)["decision"] == "no-go", name


def test_push_allowed_is_reported_but_does_not_arm() -> None:
    """`AUTOPILOT_ALLOW_PUSH` is REPORTED for the harness and gates nothing here, so it must show through even on a refusal."""
    assert decision("push-allowed-is-reported-on-a-refusal")["push_allowed"] is True
    assert decision("push-allowed-only-for-the-literal-true")["push_allowed"] is False


# --------------------------------------------------------------------------- The fork guard, in BOTH records ---------------------------------------------------------------------------


def test_the_fork_guard_reads_the_run_record() -> None:
    assert reason("fork-in-the-run-record") == (
        "fork-pr: workflow_run head repository 'attacker/console' is not the base repo"
    )
    # An ABSENT head_repository is not a fork: the guard is `-n && !=`, so a payload that never names one falls through to the PR record's check.
    assert decision("an-absent-head-repository-is-not-a-fork")["decision"] == "go"


def test_the_fork_guard_reads_the_pr_record() -> None:
    for name in ("fork-in-the-pr-record", "an-empty-pr-head-repo"):
        assert reason(name).startswith("fork-pr: PR head repo "), name


# --------------------------------------------------------------------------- The escalation latch, and its ORDER ---------------------------------------------------------------------------


def test_the_blocked_label_beats_every_arming_path() -> None:
    """`autopilot-blocked` is read FIRST, so it beats a label and a fresh dispatch alike. Cancelling a run kills one round; this kills the loop, and a port that checked it after arming would let a dispatch through."""
    for name in ("blocked-beats-the-label", "blocked-beats-a-dispatch"):
        assert reason(name) == (
            "blocked-label: 'autopilot-blocked' is applied; a human must clear the escalation first"
        ), name


def test_the_blocked_label_is_found_at_index_zero() -> None:
    """jq's `index` returns 0 for a first-position match, and 0 is TRUTHY in jq and FALSY in Python. This is the case a `json`-based port fails, and it is the commonest real shape: a PR carrying only the blocked label."""
    assert reason("the-blocked-label-alone-at-index-zero").startswith("blocked-label:")
    # CONTROL: the same position for the ARMING label must arm, not refuse.
    assert decision("the-arming-label-alone-at-index-zero")["armed_by"] == "label"


# --------------------------------------------------------------------------- The three arming paths ---------------------------------------------------------------------------


def test_not_armed_names_what_it_looked_for() -> None:
    assert reason("not-armed-names-what-it-looked-for") == (
        "not-armed: no 'autopilot' label, no dispatch with a PR number, and no open campaign "
        "with rounds remaining (campaign: none, rounds done: 0/25)"
    )
    assert decision("not-armed-names-what-it-looked-for")["armed_by"] == "none"
    # AUTOPILOT_LABEL renames the arming label, and the refusal says so.
    assert "no 'babysit' label" in reason("not-armed-with-a-renamed-label")
    assert decision("armed-by-a-renamed-label")["armed_by"] == "label"


def test_a_dispatch_arms_round_one_on_its_own() -> None:
    """THE DISPATCH IS THE ARMING ACT: no label, no state, and round 1 runs."""
    armed = decision("a-dispatch-arms-round-one")
    assert armed["armed_by"] == "dispatch"
    assert armed["round"] == 1
    # AND THE ARM THAT SURPRISES: this dispatch lands in mode `done` (CI is already green, nothing outstanding), and the `done` arm is tested FIRST in `emit`, so the campaign is NOT opened. Correct, since there is nothing for a campaign to carry, and worth pinning, because "a dispatch opens the campaign" is the sentence a reader takes from the header and it is only true of a
    # dispatch that buys a round.
    assert armed["campaign"] == "none"
    fix = decision("a-dispatch-that-buys-a-fix-round-opens-the-campaign")
    assert (fix["armed_by"], fix["mode"]) == ("dispatch", "fix")
    assert fix["campaign"] == "open", "a dispatch that buys a round opens the campaign"
    # A dispatch with NO pr_input is not an arming act.
    assert reason("a-dispatch-with-no-pr-input").startswith("not-armed:")


def test_an_open_campaign_carries_the_loop_without_a_label() -> None:
    carried = decision("an-open-campaign-carries-the-loop")
    assert carried["armed_by"] == "campaign"
    assert carried["round"] == 3, "the ledger is the only round counter"
    assert carried["rounds_max"] == 9, "the campaign's cap beats the default"
    # A CLOSED campaign does not arm.
    assert reason("a-closed-campaign-does-not-arm").startswith("not-armed:")
    assert "campaign: closed, rounds done: 2/9" in reason("a-closed-campaign-does-not-arm")
    # An open campaign with the cap already reached does not re-arm either, and says `not-armed` rather than `round-cap`, because arming runs first.
    assert reason("an-open-campaign-with-its-cap-spent").startswith("not-armed:")
    assert "rounds done: 9/9" in reason("an-open-campaign-with-its-cap-spent")


# --------------------------------------------------------------------------- The two trust checks, and the order between them ---------------------------------------------------------------------------


def test_the_author_allowlist_fails_closed_when_empty() -> None:
    for name in (
        "the-author-allowlist-absent",
        "the-author-allowlist-empty",
        "the-author-allowlist-naming-others",
        "the-author-allowlist-with-a-prefix-only",
    ):
        assert reason(name) == (
            "author-not-allowlisted: PR author 'operator' is not in AUTOPILOT_AUTHOR_ALLOWLIST"
        ), name
    # And the positive side, so the check is not simply always-refusing.
    assert decision("the-author-allowlist-with-spaces-around-the-name")["decision"] == "go"


def test_the_author_check_runs_after_arming() -> None:
    """A stranger's UNARMED PR is `not-armed`, not `author-not-allowlisted`.

    ORDER, and it is the difference between telling an outsider that their PR would otherwise qualify and telling them nothing.
    """
    assert reason("a-strangers-unarmed-pr-is-not-armed-first").startswith("not-armed:")


def test_the_applier_is_a_separate_trust_decision_from_the_author() -> None:
    """Anyone with triage can apply a label, so the APPLIER is checked too."""
    assert reason("an-applier-who-is-not-allowlisted") == (
        "applier-not-allowlisted: label applier 'drive-by' is not allowlisted"
    )
    # AUTOPILOT_APPLIER_ALLOWLIST OVERRIDES the author list rather than adding to it, so an author-allowlisted applier is refused once it is set.
    assert reason("an-applier-allowlist-that-overrides-the-author-list").startswith(
        "applier-not-allowlisted:"
    )
    assert decision("an-applier-allowlist-that-names-the-applier")["decision"] == "go"


def test_the_dispatching_actor_is_checked_on_the_dispatch_path() -> None:
    refused = decision("a-dispatching-actor-who-is-not-allowlisted")
    assert refused["reason"] == (
        "dispatch-actor-not-allowlisted: dispatching actor 'drive-by' is not allowlisted"
    )
    assert refused["dispatch_trusted"] is False


def test_dispatch_trusted_is_not_the_same_claim_as_armed() -> None:
    """A LABEL-armed round dispatched by nobody in particular: armed yes, trusted no. The workflow gates a human shell on the runner on the second one, so collapsing them would hand a shell to whoever pressed the button."""
    untrusted = decision("armed-by-label-and-dispatched-by-a-stranger")
    assert untrusted["armed_by"] == "label"
    assert untrusted["dispatch_trusted"] is False
    assert untrusted["decision"] == "go"
    assert decision("armed-by-label-and-dispatched-by-the-operator")["dispatch_trusted"] is True


def test_the_campaign_path_has_no_further_trust_check() -> None:
    """The empty `campaign)` case arm, asserted rather than assumed: a campaign round with a hostile `label_applier` and no dispatch actor still goes, because the state comment's AUTHORSHIP is the check and it happened upstream."""
    campaign = decision("a-campaign-round-with-a-hostile-applier")
    assert campaign["armed_by"] == "campaign"
    assert campaign["decision"] == "go"


# --------------------------------------------------------------------------- Dedup, the round cap, the watchdog ---------------------------------------------------------------------------


def test_a_duplicate_of_an_already_handled_run() -> None:
    assert reason("a-duplicate-of-an-already-handled-run") == (
        "already-handled: run 4242/1 is in the ledger"
    )
    # A DIFFERENT ATTEMPT of the same run is not a duplicate.
    assert decision("a-second-attempt-of-the-same-run")["decision"] == "go"
    # And `4242/1` must not match `42420/1`: the trailing `([^0-9]|$)` is what stops a shorter run id matching a longer one's prefix.
    assert decision("a-run-id-that-is-a-prefix-of-the-recorded-one")["decision"] == "go"


def test_the_round_cap_is_enforced_from_the_trusted_ledger() -> None:
    capped = decision("the-round-cap-reached")
    assert capped["reason"] == (
        "round-cap: 3 rounds recorded, cap is 3; escalating to the operator is the design working"
    )
    assert capped["round"] == 4, "the round it WOULD have been is still reported"
    assert decision("the-round-cap-not-yet-reached")["decision"] == "go"


def test_an_out_of_shape_max_rounds_falls_back_to_twenty_five() -> None:
    for name, expected in (
        ("max-rounds-empty", 25),
        ("max-rounds-not-a-number", 25),
        ("max-rounds-of-five-digits", 25),
        ("max-rounds-that-is-negative", 25),
        ("max-rounds-of-seven", 7),
    ):
        assert decision(name)["rounds_max"] == expected, name


def test_the_watchdog_deferral() -> None:
    assert reason("the-watchdog-holds-a-pending-rerun") == (
        "watchdog-defer: a pending_rerun is held for this run; the gate defers so the two "
        "cannot race"
    )
    # An EMPTY watchdog file is not a hold: the test is `-s`, not `-f`.
    assert decision("an-empty-watchdog-file-is-not-a-hold")["decision"] == "go"


# --------------------------------------------------------------------------- Mode selection ---------------------------------------------------------------------------


def test_a_failed_run_buys_a_fix_round() -> None:
    fix = decision("a-failed-run-buys-a-fix-round")
    assert (fix["decision"], fix["mode"]) == ("go", "fix")
    assert fix["reason"] == "ci-failure: run 4242 concluded failure"
    assert fix["sig"] == "none", "no failed-jobs file means no signature"


def test_the_failure_signature_is_order_independent() -> None:
    """Sorted before hashing, so the jobs API's ordering cannot change it."""
    first = decision("the-signature-with-quality-first")
    second = decision("the-signature-with-build-first")
    assert first["sig"] == second["sig"] == JOBS_SIG, (first["sig"], second["sig"])
    assert first["sig_count"] == second["sig_count"] == 1


def test_the_stuck_signature_escalates_before_the_cap() -> None:
    """The third consecutive round on one unchanged failed-job set refuses, which is the difference between escalating at round 3 and burning 25."""
    stuck = decision("the-third-round-on-one-unchanged-failure-set")
    assert stuck["reason"] == (
        "stuck-signature: failed-job set %s is unchanged after 2 fix round(s); escalating "
        "rather than burning the round cap" % JOBS_SIG
    )
    assert stuck["sig_count"] == 3
    # ONE round earlier, the same set still buys a fix.
    earlier = decision("the-second-round-on-one-unchanged-failure-set")
    assert (earlier["mode"], earlier["sig_count"]) == ("fix", 2)
    # A DIFFERENT set resets the counter to 1, so a moving failure never sticks.
    moved = decision("a-changed-failure-set-resets-the-counter")
    assert (moved["mode"], moved["sig_count"]) == ("fix", 1)


def test_a_green_run_never_looks_like_a_repeat_of_the_last_red_one() -> None:
    """`sig` is `none` with no failed jobs, and `none` never matches a stored signature even when the stored one is literally absent."""
    green = decision("an-empty-failed-jobs-file-never-matches-a-stored-signature")
    assert (green["sig"], green["sig_count"], green["mode"]) == ("none", 1, "fix")


def test_a_cancelled_run_with_failed_jobs_is_a_watchdog_kill() -> None:
    killed = decision("a-cancelled-run-with-failed-jobs")
    assert (killed["mode"], killed["reason"]) == (
        "fix",
        "watchdog-kill: cancelled with 2 failed job(s)",
    ), killed
    assert "2 failed" in killed["reason"], "blank lines are not jobs (grep -c .)"


def test_a_cancelled_run_whose_head_moved_on() -> None:
    assert reason("a-cancelled-run-whose-head-moved-on") == (
        "superseded: run head oldsha is no longer the PR head cafe1234"
    )


def test_a_cancelled_run_with_nothing_to_act_on() -> None:
    assert reason("a-cancelled-run-with-nothing-to-act-on") == (
        "cancelled-no-failure: cancelled with zero failed jobs and no newer head; nothing to act on"
    )
    # An ABSENT head sha on either side skips the superseded check entirely.
    assert reason("a-cancelled-run-with-no-head-sha").startswith("cancelled-no-failure:")


def test_the_four_success_arms_in_their_order() -> None:
    """Review gate first, then draft, then threads, then done. The order is the design's, and each recording differs from the next by ONE field, so a port that reordered them would land on a different mode."""
    for name, mode, why in (
        (
            "success-with-a-red-review-gate-and-no-threads",
            "rerun-review",
            (
                "review-gate-red-no-threads: the Review Gate is red with nothing outstanding "
                "to answer; deterministic rerun, no model"
            ),
        ),
        (
            "success-with-a-red-review-gate-and-threads",
            "review-response",
            "review-gate-red: CI green, the Review Gate is red, and 3 thread(s) are outstanding",
        ),
        (
            "success-while-draft",
            "ready-flip",
            "success-while-draft: deterministic ready-flip, no model",
        ),
        (
            "success-with-threads-only",
            "review-response",
            "unresolved-threads: 2 review thread(s) outstanding",
        ),
        (
            "success-with-nothing-outstanding",
            "done",
            "done-conditions: green, ready, reviewed, no outstanding threads",
        ),
    ):
        got = decision(name)
        assert (got["decision"], got["mode"]) == ("go", mode), name
        assert got["reason"] == why, name
    # A red review gate BEATS a draft: the draft flip would hide the red.
    assert decision("a-red-review-gate-beats-a-draft")["mode"] == "rerun-review"


def test_an_out_of_shape_thread_count_reads_as_zero() -> None:
    """`^[0-9]+$` or 0, so a string, a negative or a float never reaches `((...))` where it would be a syntax error rather than a decision."""
    for name in (
        "a-thread-count-that-is-a-word",
        "a-thread-count-that-is-negative",
        "a-thread-count-that-is-a-float",
        "a-thread-count-that-is-null",
    ):
        assert decision(name)["mode"] == "done", name


def test_an_unhandled_conclusion() -> None:
    for name, conclusion in (
        ("an-unhandled-conclusion-skipped", "skipped"),
        ("an-unhandled-conclusion-neutral", "neutral"),
        ("an-unhandled-conclusion-timed-out", "timed_out"),
        ("an-unhandled-conclusion-action-required", "action_required"),
    ):
        assert reason(name) == (
            "unhandled-conclusion: '%s' is not an actionable run conclusion" % conclusion
        ), name


# --------------------------------------------------------------------------- Model resolution and the campaign hand-off ---------------------------------------------------------------------------


def test_model_resolution_in_the_designs_order() -> None:
    """dispatch input beats campaign record beats default, and an unknown value at either level degrades to the default WITH A WARNING rather than failing the round after the runner has been paid for."""
    assert decision("the-default-model")["model"] == "claude-sonnet-5"
    assert "falling back" not in recorded("the-default-model")[2]
    assert decision("the-model-from-the-campaign-record")["model"] == "claude-opus-5"
    assert decision("the-model-from-the-dispatch-input")["model"] == "claude-sonnet-5"
    # An unknown dispatch model is a TYPO, not an instruction.
    assert decision("an-unknown-dispatch-model")["model"] == "claude-sonnet-5"
    assert (
        "model 'gpt-9' is not one of claude-sonnet-5,claude-opus-5; falling back to "
        "claude-sonnet-5" in recorded("an-unknown-dispatch-model")[2]
    )
    # And the warning fires even on a path that ends in a refusal, because it is emitted before the fork guard.
    assert "falling back to claude-sonnet-5" in recorded("an-unknown-model-on-a-refused-round")[2]
    assert decision("an-unknown-model-on-a-refused-round")["decision"] == "no-go"


def test_the_campaign_field_carried_into_the_next_write() -> None:
    """`campaign` on the decision line is what the NEXT state write records, not what this round read. Three arms, and the third is the one with a guard."""
    closed = decision("done-closes-an-open-campaign")
    assert (closed["mode"], closed["campaign"]) == ("done", "closed")
    # done with NO campaign stays none, never `closed`.
    none = decision("done-with-no-campaign-stays-none")
    assert (none["mode"], none["campaign"]) == ("done", "none")
    # A label-armed FIX round carries an open campaign forward untouched.
    carried = decision("a-label-armed-fix-round-carries-the-campaign")
    assert (carried["armed_by"], carried["campaign"]) == ("label", "open")


def test_round_cap_resolution_order() -> None:
    """dispatch, then campaign, then AUTOPILOT_MAX_ROUNDS, then 25."""
    assert decision("the-campaign-cap-beats-the-repo-variable")["rounds_max"] == 9
    assert decision("the-dispatch-cap-beats-the-campaign")["rounds_max"] == 4
    # A dispatch max_rounds of 0 or out of shape falls through to the campaign.
    for name in (
        "a-dispatch-cap-of-zero",
        "a-dispatch-cap-that-is-empty",
        "a-dispatch-cap-that-is-not-a-number",
        "a-dispatch-cap-of-five-digits",
    ):
        assert decision(name)["rounds_max"] == 9, name
    # With no campaign cap either, the repo variable wins.
    assert decision("the-repo-variable-with-no-campaign-cap")["rounds_max"] == 13


# --------------------------------------------------------------------------- Bash arithmetic, both halves ---------------------------------------------------------------------------


def test_the_campaign_cap_cannot_carry_an_octal_because_jq_launders_it() -> None:
    """MEASURED, AND IT REFUTES THE OBVIOUS GUESS.

    The state-comment renderer emits `rounds_max` through `jq --argjson`, which prints 12 for the input `012`, so the value the gate reads back from a state comment is ALREADY decimal. A case aimed here would pass while proving nothing about bash's grammar. The env-var and dispatch paths are the ones that actually reach `((...))` with the zero intact.
    """
    octal = decision("a-campaign-cap-with-a-leading-zero")
    assert octal["rounds_max"] == 12
    assert octal["armed_by"] == "campaign", "10 < 12, decimal, so the campaign re-arms"


def test_an_octal_round_cap_is_enforced_as_octal_and_reported_as_decimal() -> None:
    """`AUTOPILOT_MAX_ROUNDS=012` is TEN to `((...))` and TWELVE to jq.

    A twin inconsistency, preserved because it decides where a campaign stops. The recording that proves it: ten recorded rounds against a cap that READS as 12 still hits the cap.
    """
    capped = decision("an-octal-repo-variable-cap-at-the-bound")
    assert capped["rounds_max"] == 12, "jq reads the leading zero as decimal"
    assert capped["reason"] == (
        "round-cap: 10 rounds recorded, cap is 012; escalating to the operator is the design "
        "working"
    ), capped["reason"]
    # Nine rounds is still under the OCTAL cap of ten, so the round runs.
    assert decision("an-octal-repo-variable-cap-under-the-bound")["decision"] == "go"
    # And the same grammar on the thread count, which arrives as a JSON STRING.
    threads = decision("a-thread-count-with-a-leading-zero")
    assert threads["mode"] == "review-response"
    assert threads["reason"] == "unresolved-threads: 012 review thread(s) outstanding"


# --------------------------------------------------------------------------- The one recorded divergence ---------------------------------------------------------------------------


def test_an_invalid_octal_round_cap(tmp_path: pathlib.Path) -> None:
    """`08` is a bash arithmetic ERROR that evaluates as false.

    THE ONE FILTERED CASE IN THIS FILE. Exit code, stdout and the call log are compared byte for byte; the bash diagnostic, which carried the twin's own path and line number, is dropped from both sides and its presence in the recording is asserted, so the filter cannot become a way of hiding a divergence that is not this one.

    THE DIRECTION MATTERS: the error reads as FALSE, so the cap is not reached and the round RUNS. A malformed cap fails open, which is a finding about the twin rather than about this port.
    """
    name = "an-invalid-octal-repo-variable-cap"
    want = recorded(name)
    got = run(tmp_path, name)

    def without_arith(stream: str) -> str:
        return "".join(line + "\n" for line in stream.split("\n")[:-1] if ARITH_ERROR not in line)

    assert ARITH_ERROR in want[2], "the arithmetic filter fired on nothing"
    assert ROOT_PLACEHOLDER in want[2], "the twin's own path is masked, and it is still named"
    assert got[0] == want[0]
    assert got[1] == want[1]
    assert without_arith(got[2]) == without_arith(want[2])
    assert got[3] == want[3] == []
    verdict = json.loads(want[1])
    assert verdict["rounds_max"] == 8, "jq reads 08 as 8 while bash refuses it entirely"
    assert verdict["decision"] == "go", "a malformed cap fails OPEN"
    assert verdict["round"] == 11


# --------------------------------------------------------------------------- The two preserved hazards ---------------------------------------------------------------------------


def test_a_mistyped_state_path_is_silently_no_state() -> None:
    """HAZARD 1, PRESERVED AND PINNED. `--state` is `[[ -n && -s ]]`, never `require_file`, so a typo reads as "no state comment yet": the round counter resets to 1 and an exhausted campaign is invisible. Fail OPEN, which is the wrong direction for this file; fixing it changes a live workflow step's contract, so it is the cutover box's call."""
    assert reason("a-state-path-that-exists").startswith("not-armed:"), "the cap is reached"
    typo = decision("a-state-path-with-a-typo")
    assert typo["round"] == 1, "a typo reset the round counter"
    assert typo["campaign"] == "none"
    assert recorded("a-state-path-with-a-typo")[2] == "", "and it said nothing at all"
    # The same silence for a mistyped --watchdog.
    assert decision("a-watchdog-path-with-a-typo")["decision"] == "go"
    assert recorded("a-watchdog-path-with-a-typo")[2] == ""


def test_the_allowlist_strips_interior_whitespace() -> None:
    """HAZARD 2, PRESERVED AND PINNED. `${item//[[:space:]]/}` deletes every whitespace character rather than trimming the ends, so `a b` allowlists `ab`. GitHub logins cannot contain a space, so this cannot admit a real account today; it is pinned because it guards a model invocation."""
    assert decision("an-allowlist-entry-with-an-interior-space")["decision"] == "go", (
        "the twin admits 'ab' from an entry of 'a b'"
    )
    # CONTROL, so the case is not simply "everything is admitted": the entry as written still does not admit the string with the space in it.
    assert reason("an-allowlist-entry-with-an-interior-space-control").startswith(
        "author-not-allowlisted:"
    )


def test_a_multi_line_allowlist_stops_at_the_first_line() -> None:
    """`read` reads ONE line, so a wrapped repo variable admits only the first line's names. Fail CLOSED, which is the right direction, and it is a real shape: a pasted list arrives wrapped."""
    assert reason("an-allowlist-that-wraps-onto-a-second-line").startswith(
        "author-not-allowlisted:"
    )
    assert decision("an-allowlist-whose-first-line-names-the-author")["decision"] == "go"


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

    `((10 >= 08))` is FALSE. Reading `08` as 0 makes it TRUE, which turns a fail-open hazard in the twin into a refusal in the port. Both directions, because only the second one catches a `bash_cmp` that returns False for everything.
    """
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


def test_non_empty_file_is_dash_s_and_not_require_file(tmp_path: pathlib.Path) -> None:
    assert ag.non_empty_file("") is False
    assert ag.non_empty_file(str(tmp_path / "absent")) is False
    empty = tmp_path / "empty"
    empty.write_text("", encoding="utf-8")
    assert ag.non_empty_file(str(empty)) is False
    full = tmp_path / "full"
    full.write_text("x", encoding="utf-8")
    assert ag.non_empty_file(str(full)) is True


KEY_ORDER = [
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


def test_the_emit_program_and_its_key_order() -> None:
    """The decision line's twelve keys, in program order, are the contract with the workflow step that reads them, and the recordings carry that order in their own bytes."""
    for key in KEY_ORDER:
        assert "%s:" % key in ag.EMIT_PROGRAM, key
    gate = ag.Gate()
    decided = gate.emit("go", "fix", "because")
    assert decided.code == 0
    assert list(json.loads(decided.payload).keys()) == KEY_ORDER
    assert list(decision("success-with-nothing-outstanding").keys()) == KEY_ORDER


def test_the_campaign_hand_off_is_a_pure_function_of_three_inputs() -> None:
    """`emit`'s campaign arm, driven directly, so all four combinations are exercised without needing four fixtures."""
    for campaign, verdict, mode, armed, expected in (
        ("open", "go", "done", "label", "closed"),
        ("none", "go", "done", "label", "none"),
        ("none", "go", "fix", "dispatch", "open"),
        ("open", "no-go", "none", "dispatch", "open"),
        ("closed", "go", "fix", "label", "closed"),
    ):
        gate = ag.Gate()
        gate.campaign_state = campaign
        gate.armed_by = armed
        payload = json.loads(gate.emit(verdict, mode, "r").payload)
        assert payload["campaign"] == expected, (campaign, verdict, mode, armed)


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_rename_of_the_escalation_latch_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Rename the label the escalation latch looks for.

    `autopilot-blocked` is the one thing a human can apply that stops the loop rather than one round, and it is read BEFORE every arming path so that it beats a label and a fresh dispatch alike. A latch that looks for a label nobody applies is indistinguishable from a working one on every PR that is not blocked, which is every PR until the day it matters. The mutant arms the round
    the recording refuses, and the decision line says so.

    The mutation runs from a throwaway copy placed outside the fixture and resolving `rediacc_ci` through the same `PYTHONPATH`; the tracked port is never touched, and the real port is compared again afterwards so a mutant that failed for some unrelated reason cannot pass for a caught one.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = 'BLOCKED_LABEL = "autopilot-blocked"\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, 'BLOCKED_LABEL = "autopilot-blocked-nobody-applies"\n')

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "blocked-beats-the-label"
    want = recorded(name)
    got = run(tmp_path / "planted", name, subject=mutant)
    assert json.loads(want[1])["decision"] == "no-go", "the recorded corpus moved"
    planted = json.loads(got[1])
    assert planted["decision"] == "go", "the plant did not disarm the latch"
    assert planted["armed_by"] == "label"
    assert got[3] == want[3] == [], "and neither side reached the network"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
