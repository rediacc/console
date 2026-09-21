"""`rediacc_ci.ci.cancel_older_runs`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/ci/cancel-older-runs.sh` and the port over the same fake `gh` and compared exit code, stdout, stderr and the recorded call log. The K=5 ledger `.ci/shadow/w7p6-cancel-older-runs.observations.jsonl` recorded that comparison, and `.ci/shadow/w7p4b-cancel-older-runs.observations.jsonl` holds ten more trees from the earlier
pass. The twin has now been deleted and every case that executed it compares against `goldens/cancel-older-runs/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

THE FAKE `gh` IS RECORDING, AND THE CALL LOG IS THE POINT. This script's only effect on the world is the sequence of `gh api` calls it makes: the run lookup, the in-progress listing with its four query parameters, and one POST per older run to `force-cancel` and then to `cancel`. A recording of the streams alone would bless a port that cancelled the WRONG run, or that hit the
endpoints in the other order. The fake appends its exact argv to `$FAKE_LOG`, and every golden carries a fourth `--- calls ---` section holding it.

LOOP CASES LEAVE THROUGH THE CLEAN DOOR, NOT THROUGH THE TIMEOUT, AND THAT WAS
LEARNED THE HARD WAY. The twin's loop had two exits: "no older CI runs in progress" and the timeout. Driving a cancellation round with `--timeout 1 --poll-interval 1` looks like it gives exactly one round -- iteration one sees
elapsed 0, cancels, sleeps, iteration two sees elapsed >= 1 and gives up -- but
`START_TIME=$(date +%s)` and the loop's `$(date +%s)` were two separate reads of
a whole-second clock, so if a second boundary fell between them the FIRST iteration already saw elapsed 1 and the script gave up having done nothing. That is a real property of the twin (reproduced by the port, since it reads the same clock the same way) and it made a shadow-gate row record MISMATCH_FINDINGS purely on which side of a second the two runs landed.

So every loop case here sets `FAKE_LIST_THEN_EMPTY=1` and a generous timeout:
the first listing returns the fixture, every later one returns an empty array, and the loop leaves through the clean door after exactly one round. The timeout arm is exercised separately with `--timeout 0`, which is the one value that cannot race.

WHAT IS NORMALISED. Three arms print bash's own diagnostics, which begin `<program>: line <N>:`. The program NAME necessarily differed between a `.sh` and a module file; `strip_prog` replaces that one token and the line NUMBER is compared, because a drifting line number is what this pinning exists to catch.

THE FOUR STALENESS ALARMS THAT READ THE TWIN'S SOURCE ARE GONE, and the recordings replace them. They existed so the port's copies of the twin's line numbers, jq filters and defaults could not drift away from the file CI ran. A deleted file does not drift; the port's copies are pinned instead by bytes the twin really printed -- `line 92` in two recordings, `line 57` in the
missing-gh one, the default workflow inside the recorded listing URL, and the whole `select` semantics by which of three runs the recorded call log cancelled.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ci import cancel_older_runs as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if TYPE_CHECKING:
    import pathlib

SLUG = "cancel-older-runs"
MODULE = "rediacc_ci.ci.cancel_older_runs"

CALLS_MARKER = "--- calls ---\n"

# The program's own name wherever bash printed it. NOT anchored to the start of a line: the `2>&1` on the twin's line 57 captured `gh: command not found` INTO the run body, so the diagnostic reappears in the MIDDLE of a `log_warn` line. Scoped to the two basenames so it can only ever eat the program name.
_PROG = re.compile(r"\S*(?:cancel-older-runs\.sh|cancel_older_runs\.py): line ")

# The current run: id 9, created 2026-01-01. Every fixture below is relative to
# these two values, because the twin's filter was `.id != <id> and .created_at <
# "<created>"` and both halves have to be exercised.
CURRENT_ID = "9"
CURRENT_CREATED = "2026-01-01T00:00:00Z"
CURRENT_RUN_JSON = json.dumps({"created_at": CURRENT_CREATED, "head_branch": "main"})

# `.replace`, not `.format`: the canned bodies below are JSON and are full of braces that `str.format` would read as fields.
FAKE_GH_SRC = """#!@PYTHON@
import os
import sys

argv = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("FAKEGH| " + " ".join(argv) + "\\n")
joined = " ".join(argv)
noise = ""
if joined.endswith("/force-cancel"):
    body = os.environ.get("FAKE_FORCE_BODY", "{}")
    rc = int(os.environ.get("FAKE_FORCE_RC", "0"))
elif joined.endswith("/cancel"):
    body = os.environ.get("FAKE_CANCEL_BODY", "{}")
    rc = int(os.environ.get("FAKE_CANCEL_RC", "0"))
elif "/actions/workflows/" in joined:
    # FAKE_LIST_THEN_EMPTY makes every listing AFTER the first return an empty
    # array. It is what lets a case exercise a full cancellation round and then
    # leave through the "no older runs" door rather than through the timeout --
    # see LOOP CASES LEAVE THROUGH THE CLEAN DOOR in the module docstring.
    seen = 0
    counter = (log or "") + ".listings"
    if log:
        try:
            with open(counter, encoding="utf-8") as fh:
                seen = int(fh.read() or "0")
        except OSError:
            seen = 0
        with open(counter, "w", encoding="utf-8") as fh:
            fh.write(str(seen + 1))
    if seen and os.environ.get("FAKE_LIST_THEN_EMPTY"):
        body, rc = '{"workflow_runs":[]}', 0
    else:
        body = os.environ.get("FAKE_LIST_JSON", '{"workflow_runs":[]}')
        rc = int(os.environ.get("FAKE_LIST_RC", "0"))
    noise = os.environ.get("FAKE_LIST_STDERR", "")
else:
    body = os.environ.get("FAKE_RUN_JSON", "{}")
    rc = int(os.environ.get("FAKE_RUN_RC", "0"))
    noise = os.environ.get("FAKE_RUN_STDERR", "")
# BEFORE the body, which is what a real `gh` warning does and what makes the
# `2>&1` merge order observable.
sys.stderr.write(noise)
sys.stderr.flush()
if rc != 0:
    sys.stderr.write("gh: simulated failure\\n")
    sys.exit(rc)
sys.stdout.write(body + "\\n")
"""


def strip_prog(text: str) -> str:
    return _PROG.sub("<prog>: line ", text)


def make_fake_gh(tmp_path: pathlib.Path) -> pathlib.Path:
    bindir = tmp_path / "fakebin"
    bindir.mkdir(parents=True, exist_ok=True)
    script = bindir / "gh"
    script.write_text(FAKE_GH_SRC.replace("@PYTHON@", sys.executable), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def restricted_bin(tmp_path: pathlib.Path, *, drop: str) -> pathlib.Path:
    """A PATH directory with everything the subject needs EXCEPT `drop`.

    `gh` really is installed at /usr/bin/gh here, so the only honest way to reach the missing-tool arm is a PATH that does not contain /usr/bin at all. `dirname` and `uname` are in the list because common.sh ran both
    while it was being SOURCED and would otherwise have failed for an unrelated reason.
    """
    bindir = tmp_path / ("nobin-%s" % drop)
    bindir.mkdir(parents=True, exist_ok=True)
    for tool in ("bash", "python3", "uname", "dirname", "cat", "sed", "date", "jq", "sleep"):
        if tool == drop:
            continue
        found = shutil.which(tool)
        target = bindir / tool
        if found and not target.exists():
            target.symlink_to(found)
    return bindir


def base_env() -> dict[str, str | None]:
    return {
        "GITHUB_RUN_ID": CURRENT_ID,
        "GITHUB_REPOSITORY": "rediacc/console",
        "GH_TOKEN": "t",
        "FAKE_RUN_JSON": CURRENT_RUN_JSON,
    }


def run(
    tmp_path: pathlib.Path,
    command: str,
    *args: str,
    env_extra: dict[str, str | None] | None = None,
    drop_from_path: str | None = None,
    tty: str | None = None,
    side: str = "new",
) -> tuple[int, str, str, str]:
    """One side, once, with its own recording log."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    quoted = " ".join(shlex.quote(a) for a in args)
    if drop_from_path is None:
        bindir = make_fake_gh(tmp_path)
        path = "%s:%s" % (bindir, os.environ.get("PATH", ""))
    else:
        path = str(restricted_bin(tmp_path, drop=drop_from_path))

    env = dict(base_env())
    env.update(env_extra or {})
    log = tmp_path / ("%s-ghcalls.txt" % side)
    log.write_text("", encoding="utf-8")
    env["FAKE_LOG"] = str(log)
    env["PATH"] = path
    if command.startswith("python3"):
        env["PYTHONPATH"] = ".ci"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
    returncode, stdout, stderr = diff.bash_streams(
        "%s %s" % (command, quoted), env=diff.env_for(**env), tty=tty, timeout=60
    )
    return returncode, stdout, stderr, log.read_text(encoding="utf-8")


def listing_call(workflow: str = "ci.yml", branch: str = "main") -> str:
    return (
        "FAKEGH| api repos/rediacc/console/actions/workflows/%s/runs"
        "?status=in_progress&branch=%s&per_page=10\n" % (workflow, branch)
    )


RUN_CALL = "FAKEGH| api repos/rediacc/console/actions/runs/9\n"

# What every LOOP case passes. `--poll-interval 0` because the sleep is not what is under test and a real second per case is a real second; the timeout is generous because these cases leave through the clean door, never through it.
LOOP_ARGS = ("--timeout", "30", "--poll-interval", "0")

ONE_OLDER = json.dumps(
    {"workflow_runs": [{"id": 5, "run_number": 50, "created_at": "2025-01-01T00:00:00Z"}]}
)
THREE_CANDIDATES = json.dumps(
    {
        "workflow_runs": [
            {"id": 9, "run_number": 90, "created_at": "2020-01-01T00:00:00Z"},
            {"id": 7, "run_number": 70, "created_at": "2026-06-01T00:00:00Z"},
            {"id": 5, "run_number": 50, "created_at": "2025-01-01T00:00:00Z"},
        ]
    }
)

CASE_KW: dict[str, tuple[tuple[str, ...], dict[str, object]]] = {
    "no-github-run-id": ((), {"env_extra": {"GITHUB_RUN_ID": None}}),
    "an-empty-github-run-id": ((), {"env_extra": {"GITHUB_RUN_ID": ""}}),
    "a-missing-repository": ((), {"env_extra": {"GITHUB_REPOSITORY": None}}),
    "a-missing-token": ((), {"env_extra": {"GH_TOKEN": None}}),
    "all-three-guards-missing": (
        (),
        {"env_extra": {"GITHUB_RUN_ID": None, "GITHUB_REPOSITORY": None, "GH_TOKEN": None}},
    ),
    "a-failing-run-lookup": ((), {"env_extra": {"FAKE_RUN_RC": "3"}}),
    "a-non-json-run-body": ((), {"env_extra": {"FAKE_RUN_JSON": "not json"}}),
    "a-gh-warning-beside-a-good-body": (
        (),
        {"env_extra": {"FAKE_RUN_STDERR": "gh: a deprecation notice\n"}},
    ),
    "a-gh-warning-on-the-listing": (
        (),
        {"env_extra": {"FAKE_LIST_STDERR": "gh: a deprecation notice\n"}},
    ),
    "a-run-body-without-the-two-fields": ((), {"env_extra": {"FAKE_RUN_JSON": "{}"}}),
    "a-missing-head-branch": (
        (),
        {"env_extra": {"FAKE_RUN_JSON": json.dumps({"created_at": CURRENT_CREATED})}},
    ),
    "no-older-runs": ((), {}),
    "three-candidates-one-match": (
        LOOP_ARGS,
        {"env_extra": {"FAKE_LIST_JSON": THREE_CANDIDATES, "FAKE_LIST_THEN_EMPTY": "1"}},
    ),
    "the-response-body-leaks-onto-stdout": (
        LOOP_ARGS,
        {
            "env_extra": {
                "FAKE_LIST_JSON": ONE_OLDER,
                "FAKE_LIST_THEN_EMPTY": "1",
                "FAKE_FORCE_BODY": '{"leaked":true}',
            }
        },
    ),
    "force-cancel-falls-back-to-cancel": (
        LOOP_ARGS,
        {
            "env_extra": {
                "FAKE_LIST_JSON": ONE_OLDER,
                "FAKE_LIST_THEN_EMPTY": "1",
                "FAKE_FORCE_RC": "1",
            }
        },
    ),
    "both-endpoints-fail": (
        LOOP_ARGS,
        {
            "env_extra": {
                "FAKE_LIST_JSON": ONE_OLDER,
                "FAKE_LIST_THEN_EMPTY": "1",
                "FAKE_FORCE_RC": "1",
                "FAKE_CANCEL_RC": "1",
            }
        },
    ),
    "a-failing-listing-is-retried": (
        LOOP_ARGS,
        {"env_extra": {"FAKE_LIST_RC": "7", "FAKE_LIST_THEN_EMPTY": "1"}},
    ),
    "a-timeout-of-zero": (("--timeout", "0"), {}),
    "the-workflow-flag": (("--workflow", "release.yml"), {}),
    "the-branch-comes-from-the-run": (
        (),
        {
            "env_extra": {
                "FAKE_RUN_JSON": json.dumps(
                    {"created_at": CURRENT_CREATED, "head_branch": "topic/x"}
                ),
                "GITHUB_REF_NAME": "not-this-one",
            }
        },
    ),
    "the-equals-form-of-a-flag": (("--workflow=release.yml", "--timeout=0"), {}),
    "a-bare-word-timeout": (("--timeout", "abc"), {}),
    "a-numeric-prefix-timeout": (("--timeout", "1abc"), {}),
    "an-empty-timeout": (("--timeout=",), {}),
    "a-bad-poll-interval": (
        ("--timeout", "30", "--poll-interval", "zz"),
        {"env_extra": {"FAKE_LIST_JSON": ONE_OLDER}},
    ),
    "a-missing-gh": ((), {"drop_from_path": "gh"}),
    "colour-on-a-terminal": (("--timeout", "0"), {"tty": "stderr"}),
    "no-color-on-a-terminal": (
        ("--timeout", "0"),
        {"tty": "stderr", "env_extra": {"NO_COLOR": "1"}},
    ),
}

CASES = tuple(CASE_KW)


def render(returncode: int, stdout: str, stderr: str, calls: str, root: pathlib.Path) -> str:
    body = frozen.render(
        returncode,
        frozen.mask_root(stdout, root),
        frozen.mask_root(strip_prog(stderr), root),
    )
    return body + CALLS_MARKER + frozen.mask_root(calls, root)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, calls = rest.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def drive(
    tmp_path: pathlib.Path, name: str, *, command: str | None = None
) -> tuple[int, str, str, str]:
    args, kw = CASE_KW[name]
    returncode, stdout, stderr, calls = run(
        tmp_path,
        command or ("python3 -m %s" % MODULE),
        *args,
        **kw,  # type: ignore[arg-type]
    )
    root = tmp_path / "fakebin"
    return (
        returncode,
        frozen.mask_root(stdout, root),
        frozen.mask_root(strip_prog(stderr), root),
        frozen.mask_root(calls, root),
    )


def compare(
    tmp_path: pathlib.Path, name: str, *, command: str | None = None
) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = drive(tmp_path, name, command=command)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert got[2] == want[2], "%s: stderr diverged from the recorded bytes" % name
    assert got[3] == want[3], "%s: the gh call log diverged:\n%s---\n%s" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The three environment guards ---------------------------------------------------------------------------


def test_no_github_run_id_is_a_warning_and_a_pass() -> None:
    """Not in GitHub Actions is a legitimate skip, and it called nothing."""
    returncode, _, stderr, calls = recorded("no-github-run-id")
    assert returncode == 0
    assert stderr == "⚠ GITHUB_RUN_ID not set - skipping (not running in GitHub Actions)\n"
    assert calls == ""


def test_an_empty_github_run_id_is_the_same_as_unset() -> None:
    returncode, _, stderr, _ = recorded("an-empty-github-run-id")
    assert returncode == 0
    assert "GITHUB_RUN_ID not set" in stderr


def test_a_missing_repository_is_one_of_the_only_two_real_failures() -> None:
    returncode, _, stderr, _ = recorded("a-missing-repository")
    assert returncode == 1
    assert stderr == "✗ GITHUB_REPOSITORY not set\n"


def test_a_missing_token_is_the_other_one() -> None:
    returncode, _, stderr, _ = recorded("a-missing-token")
    assert returncode == 1
    assert stderr == "✗ GH_TOKEN not set\n"


def test_the_run_id_guard_runs_before_the_repository_guard() -> None:
    """All three missing: exit 0, not 1. The skip wins, and the order is why."""
    returncode, _, stderr, _ = recorded("all-three-guards-missing")
    assert returncode == 0
    assert "GITHUB_REPOSITORY" not in stderr


# --------------------------------------------------------------------------- Fetching the current run ---------------------------------------------------------------------------


def test_a_failing_run_lookup_warns_and_exits_zero() -> None:
    """ "Could not check" folded into "nothing to do". The twin's choice, pinned."""
    returncode, _, stderr, calls = recorded("a-failing-run-lookup")
    assert returncode == 0, "a gh failure is a PASS here; if that changed, re-read the docstring"
    assert stderr == (
        "→ Checking for older in-progress CI runs...\n"
        "⚠ Failed to fetch current run info: gh: simulated failure\n"
    )
    assert calls == RUN_CALL, "it does not go on to list anything"


def test_quirk_1_a_non_json_body_kills_the_script_with_jqs_own_message() -> None:
    """Exit 5 out of a script that otherwise cannot fail, and no sentence of its own."""
    returncode, _, stderr, _ = recorded("a-non-json-run-body")
    assert returncode == 5
    assert "jq: parse error" in stderr
    assert "✗" not in stderr, "no error line of the script's own"


def test_quirk_1_is_reachable_from_a_gh_warning_beside_a_perfectly_good_body() -> None:
    """This is the SHAPE that makes QUIRK 1 a live hazard rather than a curiosity.

    `RUN_INFO=$(gh api ... 2>&1)` merged gh's stderr into the body, so one
    deprecation notice on stderr turned a valid response into a jq parse error and took the step down with exit 5.
    """
    returncode, _, stderr, _ = recorded("a-gh-warning-beside-a-good-body")
    assert returncode == 5
    assert "jq: parse error" in stderr
    # WHICH LINE jq NAMES IS THE ORDERING ASSERTION. The warning was written first, so under a shared `2>&1` pipe it is line 1 and jq chokes there. Concatenating two separately captured buffers would put the valid body on line 1 and the warning on line 2, and jq would say `line 2` instead. The port failed exactly this way before `gh_capture` switched to
    # `stderr=STDOUT`.
    assert "at line 1, column 3" in stderr


def test_the_same_warning_is_harmless_on_the_listing_call() -> None:
    """The negative control: `2>/dev/null` on the listing, `2>&1` on the lookup.

    Identical noise, identical fake, and this one is green -- which is what proves the exit 5 above belongs to the MERGE at the twin's line 57 and not to the fake writing on stderr at all.
    """
    returncode, _, stderr, _ = recorded("a-gh-warning-on-the-listing")
    assert returncode == 0
    assert "jq: parse error" not in stderr
    assert "deprecation" not in stderr, "the listing's stderr goes to /dev/null"
    assert "✓ No older CI runs in progress - done\n" in stderr


def test_json_without_the_two_fields_is_a_warning_and_a_pass() -> None:
    returncode, _, stderr, calls = recorded("a-run-body-without-the-two-fields")
    assert returncode == 0
    assert "⚠ Could not parse run info - skipping\n" in stderr
    assert calls == RUN_CALL


def test_a_missing_head_branch_alone_is_enough_to_skip() -> None:
    """`-z "$CURRENT_CREATED" || -z "$HEAD_BRANCH"`: either half, not both."""
    assert "Could not parse run info" in recorded("a-missing-head-branch")[2]


# --------------------------------------------------------------------------- The loop ---------------------------------------------------------------------------


def test_no_older_runs_is_the_clean_exit() -> None:
    returncode, _, stderr, calls = recorded("no-older-runs")
    assert returncode == 0
    assert stderr == (
        "→ Checking for older in-progress CI runs...\n"
        "✓ Current run: #9 (branch: main, created: %s)\n"
        "✓ No older CI runs in progress - done\n" % CURRENT_CREATED
    )
    assert calls == RUN_CALL + listing_call()
    # THE DEFAULT WORKFLOW, pinned by the URL the twin really asked for rather than by re-reading a file that no longer exists.
    assert "/actions/workflows/%s/runs" % port.DEFAULT_WORKFLOW in calls


def test_the_filter_excludes_this_run_and_anything_newer() -> None:
    """Three candidates, one match. Both halves of the jq `select` are exercised.

    id 9 is THIS run (excluded by id even though it is older), id 7 was created after this one (excluded by timestamp), id 5 is the only older other run. This recording is also what now pins the filter, which used to be re-read out of the twin: a `select` that lost either half would cancel a different set, and the call log names exactly which.
    """
    returncode, _, stderr, calls = recorded("three-candidates-one-match")
    assert returncode == 0
    assert "✓ Found 1 older run(s) - force-cancelling...\n" in stderr
    assert "✓ Force-cancelled run #50\n" in stderr
    assert "✓ No older CI runs in progress - done\n" in stderr
    # Exactly one cancellation round, then the clean door: list, cancel the one match, list again and find nothing.
    assert calls == (
        RUN_CALL
        + listing_call()
        + "FAKEGH| api -X POST repos/rediacc/console/actions/runs/5/force-cancel\n"
        + listing_call()
    )


def test_quirk_3_the_api_response_body_leaks_onto_stdout() -> None:
    """`gh api -X POST ... 2>/dev/null` redirected stderr ONLY.

    So GitHub's response body lands on the script's stdout, once per cancelled run. A caller piping this step's stdout gets JSON it never asked for.
    """
    assert recorded("the-response-body-leaks-onto-stdout")[1] == '{"leaked":true}\n', (
        "QUIRK 3 changed; re-read the module docstring"
    )


def test_force_cancel_falls_back_to_plain_cancel() -> None:
    _, _, stderr, calls = recorded("force-cancel-falls-back-to-cancel")
    assert "✓ Cancelled run #50 (force-cancel unavailable)\n" in stderr
    assert "FAKEGH| api -X POST repos/rediacc/console/actions/runs/5/cancel\n" in calls


def test_both_endpoints_failing_is_a_warning_and_still_a_pass() -> None:
    """Nothing was cancelled and the step is green. The twin's choice, pinned."""
    returncode, stdout, stderr, _ = recorded("both-endpoints-fail")
    assert returncode == 0
    assert "⚠ Failed to cancel run #50\n" in stderr
    assert stdout == "", "a failing POST prints no body"


def test_a_failing_listing_is_retried_rather_than_reported() -> None:
    """A listing that failed was a warning and a `continue`, never a failure."""
    returncode, _, stderr, calls = recorded("a-failing-listing-is-retried")
    assert returncode == 0
    assert "⚠ Failed to list workflow runs - retrying...\n" in stderr
    assert "✓ No older CI runs in progress - done\n" in stderr
    assert calls == RUN_CALL + listing_call() + listing_call()


def test_timeout_zero_gives_up_before_listing_anything() -> None:
    returncode, _, stderr, calls = recorded("a-timeout-of-zero")
    assert returncode == 0
    assert stderr.endswith("⚠ Timeout reached (0s) - some older runs may not have been cancelled\n")
    assert calls == RUN_CALL


def test_the_workflow_flag_changes_the_endpoint() -> None:
    assert recorded("the-workflow-flag")[3] == RUN_CALL + listing_call(workflow="release.yml")


def test_the_branch_comes_from_the_run_not_from_the_environment() -> None:
    assert recorded("the-branch-comes-from-the-run")[3] == RUN_CALL + listing_call(branch="topic/x")


def test_the_equals_form_of_a_flag_is_accepted() -> None:
    """`parse_args` split `--key=value` on the FIRST `=`."""
    _, _, stderr, calls = recorded("the-equals-form-of-a-flag")
    assert calls == RUN_CALL
    assert "Timeout reached (0s)" in stderr


def test_the_defaults_are_60_10_and_ci_yml() -> None:
    """The three `${ARG_*:-...}` defaults the port copied.

    `DEFAULT_WORKFLOW` is pinned by the recorded listing URL in `no-older-runs`. The other two are frozen history: the twin's own text is retrievable through the blob sha in every golden's provenance header, and what a reader can check here is that the port still behaves as the recordings say -- an empty `--timeout` does NOT time out, and a `--timeout 0` does.
    """
    assert port.DEFAULT_WORKFLOW == "ci.yml"
    assert port.DEFAULT_TIMEOUT == "60"
    assert port.DEFAULT_POLL_INTERVAL == "10"
    assert "Timeout reached" not in recorded("an-empty-timeout")[2]
    assert "Timeout reached (0s)" in recorded("a-timeout-of-zero")[2]


# --------------------------------------------------------------------------- QUIRK 2: the arithmetic on an unquoted --timeout ---------------------------------------------------------------------------


def test_quirk_2_a_bare_word_timeout_is_a_fatal_unbound_variable() -> None:
    returncode, _, stderr, calls = recorded("a-bare-word-timeout")
    assert returncode == 1
    assert stderr.endswith("<prog>: line %d: abc: unbound variable\n" % port.ARITH_LINE)
    assert calls == RUN_CALL, "it dies before the first listing"


def test_quirk_2_a_numeric_prefix_timeout_disables_the_timeout_entirely() -> None:
    """`1abc` is an arithmetic SYNTAX error, so `[[ ]]` answered false, forever.

    Recorded with no older runs so the loop can still exit through its other door; with an older run always present the twin ran until something else killed it (measured: `timeout 4` returned 124). The observable half here is that the diagnostic is printed and the script CONTINUES past it.
    """
    returncode, _, stderr, _ = recorded("a-numeric-prefix-timeout")
    assert returncode == 0
    assert (
        '<prog>: line %d: [[: 1abc: value too great for base (error token is "1abc")'
        % port.ARITH_LINE
        in stderr
    )
    assert "✓ No older CI runs in progress - done\n" in stderr


def test_an_empty_timeout_falls_back_to_the_default_rather_than_to_zero() -> None:
    """`${ARG_TIMEOUT:-60}` was an emptiness test, so `--timeout=` means 60."""
    returncode, _, stderr, _ = recorded("an-empty-timeout")
    assert returncode == 0
    assert "Timeout reached" not in stderr
    assert "No older CI runs in progress" in stderr


def test_a_bad_poll_interval_takes_the_script_down_with_coreutils_message() -> None:
    returncode, _, stderr, _ = recorded("a-bad-poll-interval")
    assert returncode == 1
    assert "sleep: invalid time interval 'zz'\n" in stderr


def test_a_missing_gh_reads_as_a_pass_because_the_twin_has_no_require_cmd() -> None:
    """The missing-tool arm, and it is GREEN. Pinned in the recording.

    Every other script in this batch guarded with `require_cmd gh`; this one did not, so `gh: command not found` was captured by the `2>&1` on line 57 INTO the run body and reported as "Failed to fetch current run info", exit 0. A CI runner without the GitHub CLI would therefore cancel nothing and say nothing that reads as a failure.

    The port raised `FileNotFoundError` and exited 1 here until `not_found` was written, which is the divergence this case exists to keep out. The recorded line number is also what now pins `RUN_LOOKUP_LINE`.
    """
    returncode, _, stderr, _ = recorded("a-missing-gh")
    assert returncode == 0, "the twin's missing-tool arm changed; re-read the docstring"
    assert "⚠ Failed to fetch current run info:" in stderr
    assert stderr.endswith("<prog>: line %d: gh: command not found\n" % port.RUN_LOOKUP_LINE)


# --------------------------------------------------------------------------- Streams and colour ---------------------------------------------------------------------------


def test_every_log_line_is_on_stderr_and_stdout_carries_only_leaked_bodies() -> None:
    """A stream swap is the one defect a merged `2>&1` recording cannot see."""
    _, stdout, stderr, _ = recorded("no-older-runs")
    assert stdout == ""
    assert stderr.count("\n") == 3


def test_colour_on_a_terminal_is_byte_identical() -> None:
    assert diff.escape_bytes(recorded("colour-on-a-terminal")[2]) > 0, (
        "the twin printed no colour on a tty"
    )


def test_no_color_suppresses_colour() -> None:
    assert diff.escape_bytes(recorded("no-color-on-a-terminal")[2]) == 0


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_widening_of_the_select_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, planted on the half of the filter that excludes THIS run.

    Dropping `.id != <id>` reads as a simplification -- a run cannot be older than itself, so the timestamp half looks sufficient -- and it is not: the listing carries this very run with an earlier `created_at` in the recorded fixture, so the mutant force-cancels the run it is executing inside. Nothing in the tallies gives it away; the recorded call log names run 5 and the
    mutant's names run 9 as well. The mutation is written to a throwaway copy of the module; the tracked port is never touched.
    """
    source = port.__file__
    with open(source, encoding="utf-8") as fh:
        original = fh.read()
    anchor = "'[.workflow_runs[] | select(.id != %s and .created_at < \"%s\") '\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(
        anchor, '\'[.workflow_runs[] | select("%s" != "" and .created_at < "%s") \'\n'
    )
    assert mutated != original

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "cancel_older_runs.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "three-candidates-one-match"
    _, _, _, bad_calls = drive(tmp_path / "bad", name, command="python3 %s" % mutant)
    assert "/actions/runs/9/force-cancel" in bad_calls, "the mutant spared the current run"
    with pytest.raises(AssertionError):
        compare(tmp_path / "bad2", name, command="python3 %s" % mutant)

    compare(tmp_path / "good", name)
    with open(source, encoding="utf-8") as fh:
        assert fh.read() == original
