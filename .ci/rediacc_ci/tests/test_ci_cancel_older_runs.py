"""`rediacc_ci.ci.cancel_older_runs` against its bash twin.

THE FAKE `gh` IS RECORDING, AND THE CALL LOG IS THE POINT. This script's only
effect on the world is the sequence of `gh api` calls it makes: the run lookup,
the in-progress listing with its four query parameters, and one POST per older
run to `force-cancel` and then to `cancel`. A differential that compared only
the log lines would pass a port that cancelled the WRONG run, or that hit the
endpoints in the other order. The fake appends its exact argv to `$FAKE_LOG`,
each side writes into its own, and every case asserts the two are identical.

LOOP CASES LEAVE THROUGH THE CLEAN DOOR, NOT THROUGH THE TIMEOUT, AND THAT WAS
LEARNED THE HARD WAY. The twin's loop has two exits: "no older CI runs in
progress" and the timeout. Driving a cancellation round with `--timeout 1
--poll-interval 1` looks like it gives exactly one round -- iteration one sees
elapsed 0, cancels, sleeps, iteration two sees elapsed >= 1 and gives up -- but
`START_TIME=$(date +%s)` and the loop's `$(date +%s)` are two separate reads of
a whole-second clock, so if a second boundary falls between them the FIRST
iteration already sees elapsed 1 and the script gives up having done nothing.
That is a real property of the twin (reproduced by the port, since it reads the
same clock the same way) and it made a shadow-gate row record
MISMATCH_FINDINGS purely on which side of a second the two runs landed.

So every loop case here sets `FAKE_LIST_THEN_EMPTY=1` and a generous timeout:
the first listing returns the fixture, every later one returns an empty array,
and the loop leaves through the clean door after exactly one round. The timeout
arm is exercised separately with `--timeout 0`, which is the one value that
cannot race.

WHAT IS NORMALISED. Two arms print bash's own arithmetic diagnostic, which
begins `<program>: line <N>:`. The program NAME necessarily differs between a
`.sh` and a module file; `strip_prog` replaces that one token and the line
NUMBER is compared, because a drifting line number is what this pinning exists
to catch.

The K=5 ledger is `.ci/shadow/w7p6-cancel-older-runs.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-cancel-older-runs --assert
--k 5`).
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

from rediacc_ci.ci import cancel_older_runs as port
from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/ci/cancel-older-runs.sh"
MODULE = "rediacc_ci.ci.cancel_older_runs"

# The program's own name wherever bash prints it. NOT anchored to the start of a
# line: the `2>&1` on the twin's line 57 captures `gh: command not found` INTO
# the run body, so the diagnostic reappears in the MIDDLE of a `log_warn` line.
# Scoped to the two basenames so it can only ever eat the program name.
_PROG = re.compile(r"\S*(?:cancel-older-runs\.sh|cancel_older_runs\.py): line ")

# The current run: id 9, created 2026-01-01. Every fixture below is relative to
# these two values, because the twin's filter is `.id != <id> and .created_at <
# "<created>"` and both halves have to be exercised.
CURRENT_ID = "9"
CURRENT_CREATED = "2026-01-01T00:00:00Z"
CURRENT_RUN_JSON = json.dumps({"created_at": CURRENT_CREATED, "head_branch": "main"})

# `.replace`, not `.format`: the canned bodies below are JSON and are full of
# braces that `str.format` would read as fields.
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
    bindir.mkdir(exist_ok=True)
    script = bindir / "gh"
    script.write_text(FAKE_GH_SRC.replace("@PYTHON@", sys.executable), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def restricted_bin(tmp_path: pathlib.Path, *, drop: str) -> pathlib.Path:
    """A PATH directory with everything either side needs EXCEPT `drop`.

    `gh` really is installed at /usr/bin/gh here, so the only honest way to
    reach the twin's missing-tool arm is a PATH that does not contain /usr/bin
    at all. `dirname` and `uname` are in the list because common.sh runs both
    while it is being SOURCED and would otherwise fail for an unrelated reason.
    """
    bindir = tmp_path / ("nobin-%s" % drop)
    bindir.mkdir(exist_ok=True)
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


def run_both(
    tmp_path: pathlib.Path,
    *args: str,
    env_extra: dict[str, str | None] | None = None,
    drop_from_path: str | None = None,
    tty: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str], dict[str, str]]:
    quoted = " ".join(shlex.quote(a) for a in args)
    if drop_from_path is None:
        bindir = make_fake_gh(tmp_path)
        path = "%s:%s" % (bindir, os.environ.get("PATH", ""))
    else:
        path = str(restricted_bin(tmp_path, drop=drop_from_path))

    envs: dict[str, dict[str, str | None]] = {}
    logs: dict[str, pathlib.Path] = {}
    for side in ("old", "new"):
        env = dict(base_env())
        env.update(env_extra or {})
        log = tmp_path / ("%s-ghcalls.txt" % side)
        log.write_text("", encoding="utf-8")
        env["FAKE_LOG"] = str(log)
        env["PATH"] = path
        envs[side] = env
        logs[side] = log

    old = diff.bash_streams(
        "bash %s %s" % (TWIN, quoted), env=diff.env_for(**envs["old"]), tty=tty, timeout=60
    )
    new = diff.bash_streams(
        "python3 -m %s %s" % (MODULE, quoted),
        env=diff.env_for(**envs["new"], PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        tty=tty,
        timeout=60,
    )
    return old, new, {k: v.read_text(encoding="utf-8") for k, v in logs.items()}


def assert_identical(old, new, calls) -> None:
    assert new[0] == old[0], "exit code: %r vs %r" % (old, new)
    assert new[1] == old[1], "stdout: %r vs %r" % (old[1], new[1])
    assert strip_prog(new[2]) == strip_prog(old[2]), "stderr: %r vs %r" % (old[2], new[2])
    assert calls["new"] == calls["old"], "gh call log diverged:\n%s\n%s" % (
        calls["old"],
        calls["new"],
    )


def listing_call(workflow: str = "ci.yml", branch: str = "main") -> str:
    return (
        "FAKEGH| api repos/rediacc/console/actions/workflows/%s/runs"
        "?status=in_progress&branch=%s&per_page=10\n" % (workflow, branch)
    )


RUN_CALL = "FAKEGH| api repos/rediacc/console/actions/runs/9\n"

# What every LOOP case passes. `--poll-interval 0` because the sleep is not what
# is under test and a real second per case is a real second; the timeout is
# generous because these cases leave through the clean door, never through it.
LOOP_ARGS = ("--timeout", "30", "--poll-interval", "0")


# ---------------------------------------------------------------------------
# The three environment guards
# ---------------------------------------------------------------------------


def test_no_github_run_id_is_a_warning_and_a_pass(tmp_path: pathlib.Path) -> None:
    """Not in GitHub Actions is a legitimate skip, and it calls nothing."""
    old, new, calls = run_both(tmp_path, env_extra={"GITHUB_RUN_ID": None})
    assert old[0] == 0
    assert old[2] == "⚠ GITHUB_RUN_ID not set - skipping (not running in GitHub Actions)\n"
    assert calls["old"] == ""
    assert_identical(old, new, calls)


def test_an_empty_github_run_id_is_the_same_as_unset(tmp_path: pathlib.Path) -> None:
    old, new, calls = run_both(tmp_path, env_extra={"GITHUB_RUN_ID": ""})
    assert old[0] == 0
    assert "GITHUB_RUN_ID not set" in old[2]
    assert_identical(old, new, calls)


def test_a_missing_repository_is_one_of_the_only_two_real_failures(
    tmp_path: pathlib.Path,
) -> None:
    old, new, calls = run_both(tmp_path, env_extra={"GITHUB_REPOSITORY": None})
    assert old[0] == 1
    assert old[2] == "✗ GITHUB_REPOSITORY not set\n"
    assert_identical(old, new, calls)


def test_a_missing_token_is_the_other_one(tmp_path: pathlib.Path) -> None:
    old, new, calls = run_both(tmp_path, env_extra={"GH_TOKEN": None})
    assert old[0] == 1
    assert old[2] == "✗ GH_TOKEN not set\n"
    assert_identical(old, new, calls)


def test_the_run_id_guard_runs_before_the_repository_guard(
    tmp_path: pathlib.Path,
) -> None:
    """All three missing: exit 0, not 1. The skip wins, and the order is why."""
    old, new, calls = run_both(
        tmp_path,
        env_extra={"GITHUB_RUN_ID": None, "GITHUB_REPOSITORY": None, "GH_TOKEN": None},
    )
    assert old[0] == 0
    assert "GITHUB_REPOSITORY" not in old[2]
    assert_identical(old, new, calls)


# ---------------------------------------------------------------------------
# Fetching the current run
# ---------------------------------------------------------------------------


def test_a_failing_run_lookup_warns_and_exits_zero(tmp_path: pathlib.Path) -> None:
    """ "Could not check" folded into "nothing to do". The twin's choice, pinned."""
    old, new, calls = run_both(tmp_path, env_extra={"FAKE_RUN_RC": "3"})
    assert old[0] == 0, "a gh failure is a PASS here; if that changed, re-read the docstring"
    assert old[2] == (
        "→ Checking for older in-progress CI runs...\n"
        "⚠ Failed to fetch current run info: gh: simulated failure\n"
    )
    assert calls["old"] == RUN_CALL, "it does not go on to list anything"
    assert_identical(old, new, calls)


def test_quirk_1_a_non_json_body_kills_the_script_with_jqs_own_message(
    tmp_path: pathlib.Path,
) -> None:
    """Exit 5 out of a script that otherwise cannot fail, and no sentence of its own."""
    old, new, calls = run_both(tmp_path, env_extra={"FAKE_RUN_JSON": "not json"})
    assert old[0] == 5
    assert "jq: parse error" in old[2]
    assert "✗" not in old[2], "no error line of the script's own"
    assert_identical(old, new, calls)


def test_quirk_1_is_reachable_from_a_gh_warning_beside_a_perfectly_good_body(
    tmp_path: pathlib.Path,
) -> None:
    """This is the SHAPE that makes QUIRK 1 a live hazard rather than a curiosity.

    `RUN_INFO=$(gh api ... 2>&1)` merges gh's stderr into the body, so one
    deprecation notice on stderr turns a valid response into a jq parse error
    and takes the step down with exit 5.
    """
    old, new, calls = run_both(
        tmp_path, env_extra={"FAKE_RUN_STDERR": "gh: a deprecation notice\n"}
    )
    assert old[0] == 5
    assert "jq: parse error" in old[2]
    # WHICH LINE jq NAMES IS THE ORDERING ASSERTION. The warning was written
    # first, so under a shared `2>&1` pipe it is line 1 and jq chokes there.
    # Concatenating two separately captured buffers would put the valid body on
    # line 1 and the warning on line 2, and jq would say `line 2` instead. The
    # port failed exactly this way before `gh_capture` switched to
    # `stderr=STDOUT`.
    assert "at line 1, column 3" in old[2]
    assert_identical(old, new, calls)


def test_the_same_warning_is_harmless_on_the_listing_call(tmp_path: pathlib.Path) -> None:
    """The negative control: `2>/dev/null` on the listing, `2>&1` on the lookup.

    Identical noise, identical fake, and this one is green -- which is what
    proves the exit 5 above belongs to the MERGE at the twin's line 57 and not
    to the fake writing on stderr at all.
    """
    old, new, calls = run_both(
        tmp_path, env_extra={"FAKE_LIST_STDERR": "gh: a deprecation notice\n"}
    )
    assert old[0] == 0
    assert "jq: parse error" not in old[2]
    assert "deprecation" not in old[2], "the listing's stderr goes to /dev/null"
    assert "✓ No older CI runs in progress - done\n" in old[2]
    assert_identical(old, new, calls)


def test_json_without_the_two_fields_is_a_warning_and_a_pass(
    tmp_path: pathlib.Path,
) -> None:
    old, new, calls = run_both(tmp_path, env_extra={"FAKE_RUN_JSON": "{}"})
    assert old[0] == 0
    assert "⚠ Could not parse run info - skipping\n" in old[2]
    assert calls["old"] == RUN_CALL
    assert_identical(old, new, calls)


def test_a_missing_head_branch_alone_is_enough_to_skip(tmp_path: pathlib.Path) -> None:
    """`-z "$CURRENT_CREATED" || -z "$HEAD_BRANCH"`: either half, not both."""
    old, new, calls = run_both(
        tmp_path, env_extra={"FAKE_RUN_JSON": json.dumps({"created_at": CURRENT_CREATED})}
    )
    assert "Could not parse run info" in old[2]
    assert_identical(old, new, calls)


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def test_no_older_runs_is_the_clean_exit(tmp_path: pathlib.Path) -> None:
    old, new, calls = run_both(tmp_path)
    assert old[0] == 0
    assert old[2] == (
        "→ Checking for older in-progress CI runs...\n"
        "✓ Current run: #9 (branch: main, created: %s)\n"
        "✓ No older CI runs in progress - done\n" % CURRENT_CREATED
    )
    assert calls["old"] == RUN_CALL + listing_call()
    assert_identical(old, new, calls)


def test_the_filter_excludes_this_run_and_anything_newer(tmp_path: pathlib.Path) -> None:
    """Three candidates, one match. Both halves of the jq `select` are exercised.

    id 9 is THIS run (excluded by id even though it is older), id 7 was created
    after this one (excluded by timestamp), id 5 is the only older other run.
    """
    listing = json.dumps(
        {
            "workflow_runs": [
                {"id": 9, "run_number": 90, "created_at": "2020-01-01T00:00:00Z"},
                {"id": 7, "run_number": 70, "created_at": "2026-06-01T00:00:00Z"},
                {"id": 5, "run_number": 50, "created_at": "2025-01-01T00:00:00Z"},
            ]
        }
    )
    old, new, calls = run_both(
        tmp_path,
        *LOOP_ARGS,
        env_extra={"FAKE_LIST_JSON": listing, "FAKE_LIST_THEN_EMPTY": "1"},
    )
    assert old[0] == 0
    assert "✓ Found 1 older run(s) - force-cancelling...\n" in old[2]
    assert "✓ Force-cancelled run #50\n" in old[2]
    assert "✓ No older CI runs in progress - done\n" in old[2]
    # Exactly one cancellation round, then the clean door: list, cancel the one
    # match, list again and find nothing.
    assert calls["old"] == (
        RUN_CALL
        + listing_call()
        + "FAKEGH| api -X POST repos/rediacc/console/actions/runs/5/force-cancel\n"
        + listing_call()
    )
    assert_identical(old, new, calls)


def test_quirk_3_the_api_response_body_leaks_onto_stdout(tmp_path: pathlib.Path) -> None:
    """`gh api -X POST ... 2>/dev/null` redirects stderr ONLY.

    So GitHub's response body lands on the script's stdout, once per cancelled
    run. A caller piping this step's stdout gets JSON it never asked for.
    """
    listing = json.dumps(
        {"workflow_runs": [{"id": 5, "run_number": 50, "created_at": "2025-01-01T00:00:00Z"}]}
    )
    old, new, calls = run_both(
        tmp_path,
        *LOOP_ARGS,
        env_extra={
            "FAKE_LIST_JSON": listing,
            "FAKE_LIST_THEN_EMPTY": "1",
            "FAKE_FORCE_BODY": '{"leaked":true}',
        },
    )
    assert old[1] == '{"leaked":true}\n', "QUIRK 3 changed; re-read the module docstring"
    assert_identical(old, new, calls)


def test_force_cancel_falls_back_to_plain_cancel(tmp_path: pathlib.Path) -> None:
    listing = json.dumps(
        {"workflow_runs": [{"id": 5, "run_number": 50, "created_at": "2025-01-01T00:00:00Z"}]}
    )
    old, new, calls = run_both(
        tmp_path,
        *LOOP_ARGS,
        env_extra={"FAKE_LIST_JSON": listing, "FAKE_LIST_THEN_EMPTY": "1", "FAKE_FORCE_RC": "1"},
    )
    assert "✓ Cancelled run #50 (force-cancel unavailable)\n" in old[2]
    assert "FAKEGH| api -X POST repos/rediacc/console/actions/runs/5/cancel\n" in calls["old"]
    assert_identical(old, new, calls)


def test_both_endpoints_failing_is_a_warning_and_still_a_pass(
    tmp_path: pathlib.Path,
) -> None:
    """Nothing was cancelled and the step is green. The twin's choice, pinned."""
    listing = json.dumps(
        {"workflow_runs": [{"id": 5, "run_number": 50, "created_at": "2025-01-01T00:00:00Z"}]}
    )
    old, new, calls = run_both(
        tmp_path,
        *LOOP_ARGS,
        env_extra={
            "FAKE_LIST_JSON": listing,
            "FAKE_LIST_THEN_EMPTY": "1",
            "FAKE_FORCE_RC": "1",
            "FAKE_CANCEL_RC": "1",
        },
    )
    assert old[0] == 0
    assert "⚠ Failed to cancel run #50\n" in old[2]
    assert old[1] == "", "a failing POST prints no body"
    assert_identical(old, new, calls)


def test_a_failing_listing_is_retried_rather_than_reported(
    tmp_path: pathlib.Path,
) -> None:
    """A listing that fails is a warning and a `continue`, never a failure."""
    old, new, calls = run_both(
        tmp_path,
        *LOOP_ARGS,
        env_extra={"FAKE_LIST_RC": "7", "FAKE_LIST_THEN_EMPTY": "1"},
    )
    assert old[0] == 0
    assert "⚠ Failed to list workflow runs - retrying...\n" in old[2]
    assert "✓ No older CI runs in progress - done\n" in old[2]
    assert calls["old"] == RUN_CALL + listing_call() + listing_call()
    assert_identical(old, new, calls)


def test_timeout_zero_gives_up_before_listing_anything(tmp_path: pathlib.Path) -> None:
    old, new, calls = run_both(tmp_path, "--timeout", "0")
    assert old[0] == 0
    assert old[2].endswith("⚠ Timeout reached (0s) - some older runs may not have been cancelled\n")
    assert calls["old"] == RUN_CALL
    assert_identical(old, new, calls)


def test_the_workflow_flag_changes_the_endpoint(tmp_path: pathlib.Path) -> None:
    old, new, calls = run_both(tmp_path, "--workflow", "release.yml")
    assert calls["old"] == RUN_CALL + listing_call(workflow="release.yml")
    assert_identical(old, new, calls)


def test_the_branch_comes_from_the_run_not_from_the_environment(
    tmp_path: pathlib.Path,
) -> None:
    old, new, calls = run_both(
        tmp_path,
        env_extra={
            "FAKE_RUN_JSON": json.dumps({"created_at": CURRENT_CREATED, "head_branch": "topic/x"}),
            "GITHUB_REF_NAME": "not-this-one",
        },
    )
    assert calls["old"] == RUN_CALL + listing_call(branch="topic/x")
    assert_identical(old, new, calls)


def test_the_equals_form_of_a_flag_is_accepted(tmp_path: pathlib.Path) -> None:
    """`parse_args` splits `--key=value` on the FIRST `=`."""
    old, new, calls = run_both(tmp_path, "--workflow=release.yml", "--timeout=0")
    assert calls["old"] == RUN_CALL
    assert "Timeout reached (0s)" in old[2]
    assert_identical(old, new, calls)


def test_the_defaults_are_60_10_and_ci_yml() -> None:
    """Read out of the twin rather than restated, so a change there is caught."""
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    assert 'TIMEOUT="${ARG_TIMEOUT:-%s}"' % port.DEFAULT_TIMEOUT in text
    assert 'POLL_INTERVAL="${ARG_POLL_INTERVAL:-%s}"' % port.DEFAULT_POLL_INTERVAL in text
    assert 'WORKFLOW="${ARG_WORKFLOW:-%s}"' % port.DEFAULT_WORKFLOW in text


# ---------------------------------------------------------------------------
# QUIRK 2: the arithmetic on an unquoted --timeout
# ---------------------------------------------------------------------------


def test_quirk_2_a_bare_word_timeout_is_a_fatal_unbound_variable(
    tmp_path: pathlib.Path,
) -> None:
    old, new, calls = run_both(tmp_path, "--timeout", "abc")
    assert old[0] == 1
    assert strip_prog(old[2]).endswith("<prog>: line 92: abc: unbound variable\n")
    assert calls["old"] == RUN_CALL, "it dies before the first listing"
    assert_identical(old, new, calls)


def test_quirk_2_a_numeric_prefix_timeout_disables_the_timeout_entirely(
    tmp_path: pathlib.Path,
) -> None:
    """`1abc` is an arithmetic SYNTAX error, so `[[ ]]` answers false, forever.

    Driven with no older runs so the loop can still exit through its other
    door; with an older run always present the twin runs until something else
    kills it (measured: `timeout 4` returned 124). The observable half here is
    that the diagnostic is printed and the script CONTINUES past it.
    """
    old, new, calls = run_both(tmp_path, "--timeout", "1abc")
    assert old[0] == 0
    assert (
        '<prog>: line 92: [[: 1abc: value too great for base (error token is "1abc")'
        in strip_prog(old[2])
    )
    assert "✓ No older CI runs in progress - done\n" in old[2]
    assert_identical(old, new, calls)


def test_an_empty_timeout_falls_back_to_the_default_rather_than_to_zero(
    tmp_path: pathlib.Path,
) -> None:
    """`${ARG_TIMEOUT:-60}` is an emptiness test, so `--timeout=` means 60."""
    old, new, calls = run_both(tmp_path, "--timeout=")
    assert old[0] == 0
    assert "Timeout reached" not in old[2]
    assert "No older CI runs in progress" in old[2]
    assert_identical(old, new, calls)


def test_a_bad_poll_interval_takes_the_script_down_with_coreutils_message(
    tmp_path: pathlib.Path,
) -> None:
    listing = json.dumps(
        {"workflow_runs": [{"id": 5, "run_number": 50, "created_at": "2025-01-01T00:00:00Z"}]}
    )
    old, new, calls = run_both(
        tmp_path,
        "--timeout",
        "30",
        "--poll-interval",
        "zz",
        env_extra={"FAKE_LIST_JSON": listing},
    )
    assert old[0] == 1
    assert "sleep: invalid time interval 'zz'\n" in old[2]
    assert_identical(old, new, calls)


def test_the_arithmetic_line_number_is_still_line_92() -> None:
    """bash prints it, so the port carries it, so it has to be re-derived."""
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    assert lines[port.ARITH_LINE - 1].strip() == "if [[ $ELAPSED -ge $TIMEOUT ]]; then"


def test_the_jq_programs_are_the_twins() -> None:
    """The three filters are copies. Re-read the twin instead of restating them.

    The first is interpolated with the run id and the timestamp in both files,
    so it is rendered with the twin's variable spellings and must then appear
    verbatim. A port that widened the `select` -- dropping the `.id !=` half,
    say -- would cancel the run it is running inside.
    """
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    rendered = port.JQ_OLDER_RUNS % ("${CURRENT_RUN_ID}", "${CURRENT_CREATED}")
    assert rendered.replace('\\"', '"') in text.replace('\\"', '"')
    assert "jq '%s'" % port.JQ_LENGTH in text
    assert "jq -c '%s'" % port.JQ_ROWS in text


def test_a_missing_gh_reads_as_a_pass_because_the_twin_has_no_require_cmd(
    tmp_path: pathlib.Path,
) -> None:
    """The missing-tool arm, and it is GREEN. Pinned in both directions.

    Every other script in this batch guards with `require_cmd gh`; this one does
    not, so `gh: command not found` is captured by the `2>&1` on line 57 INTO the
    run body and reported as "Failed to fetch current run info", exit 0. A CI
    runner without the GitHub CLI would therefore cancel nothing and say nothing
    that reads as a failure.

    The port raised `FileNotFoundError` and exited 1 here until `not_found` was
    written, which is the divergence this case exists to keep out.
    """
    old, new, calls = run_both(tmp_path, drop_from_path="gh")
    assert old[0] == 0, "the twin's missing-tool arm changed; re-read the docstring"
    assert "⚠ Failed to fetch current run info:" in old[2]
    assert strip_prog(old[2]).endswith("<prog>: line 57: gh: command not found\n")
    assert_identical(old, new, calls)


def test_the_line_number_in_the_missing_tool_message_is_the_twins_lookup_line() -> None:
    """bash names the line, so the port carries it, so it must be re-derived."""
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    assert lines[port.RUN_LOOKUP_LINE - 1].startswith("RUN_INFO=$(gh api ")
    assert lines[port.LISTING_LINE - 1].strip().startswith("RUNS_JSON=$(gh api ")


# ---------------------------------------------------------------------------
# Streams and colour
# ---------------------------------------------------------------------------


def test_every_log_line_is_on_stderr_and_stdout_carries_only_leaked_bodies(
    tmp_path: pathlib.Path,
) -> None:
    """A stream swap is the one defect a merged `2>&1` comparison cannot see."""
    old, new, calls = run_both(tmp_path)
    assert old[1] == ""
    assert old[2].count("\n") == 3
    assert_identical(old, new, calls)


def test_colour_on_a_terminal_is_byte_identical(tmp_path: pathlib.Path) -> None:
    old, new, calls = run_both(tmp_path, "--timeout", "0", tty="stderr")
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert_identical(old, new, calls)


def test_no_color_suppresses_colour_on_both_sides(tmp_path: pathlib.Path) -> None:
    old, new, calls = run_both(
        tmp_path, "--timeout", "0", tty="stderr", env_extra={"NO_COLOR": "1"}
    )
    assert diff.escape_bytes(old[2]) == 0
    assert_identical(old, new, calls)
