"""`rediacc_ci.housekeeping.retry_failed_runs`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/housekeeping/retry-failed-runs.sh` and the port over the same fixture, one after the other, and compared exit code, stdout, stderr and the `gh` call log. The K=5 ledger `.ci/shadow/w7p6-retry-failed-runs.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case
that executed it compares against `goldens/retry-failed-runs/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A RECORDING FAKE `gh` ON A PATH WITH NO REAL `gh` ON IT. The live effect of this script is `POST .../rerun-failed-jobs` against `rediacc/console`, and this
machine has a logged-in `gh`, so every case also pins `RETRY_REPO=acme/widget`:
a leak past the fake would still not name the real repository.

THE CALL LOG IS RECORDED, NOT JUST THE STREAMS, because "retried 1" and "retried 1 against a different run id" print the same line.

BOTH LOGGING WORLDS ARE RECORDED. `source common.sh 2>/dev/null || { ... }` gave
this script a second logger whose `log_info` and `log_step` write to STDOUT with their own prefixes, and the fallback is not a cosmetic variant: on a fresh clone every summary line moves stream. The three `the-fallback-*` cases were recorded in a tree with no `.ci/scripts/lib/`.

TIME IS PINNED BY CONSTRUCTION, not by freezing a clock. Fixtures compute `created_at` relative to the real now, well inside or well outside the age window, so neither the twin's `date -u +%s` at recording time nor the port's `time.time()` at replay time can decide a case, and no timestamp reaches a recorded stream.

WHAT IS NORMALIZED is the fixture directory, which a recording compared against a tree built minutes later cannot share. Nothing else.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import retry_failed_runs as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "housekeeping" / "retry_failed_runs.py"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "retry-failed-runs"

LIVE_HEAD = "a" * 40
DEAD_HEAD = "b" * 40
WATCHDOG = ".github/workflows/watchdog-monitor.yml"
NORMAL = ".github/workflows/cleanup-pr-preview.yml"

FAKE_GH = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("\\t".join(argv) + "\\n")

joined = "\\t".join(argv)

if "-X" in argv and "POST" in argv:
    sys.stdout.write("rerun stdout that must never be seen\\n")
    sys.stderr.write("rerun stderr that must never be seen\\n")
    sys.exit(int(os.environ.get("FAKE_GH_RERUN_RC", "0")))

if "/branches?" in joined:
    rc = int(os.environ.get("FAKE_GH_BRANCHES_RC", "0"))
    sys.stdout.write(os.environ.get("FAKE_GH_HEADS", ""))
    if rc:
        sys.stderr.write("gh: fake branches failure\\n")
    sys.exit(rc)

if "/actions/runs?" in joined:
    rc = int(os.environ.get("FAKE_GH_RUNS_RC", "0"))
    sys.stdout.write(os.environ.get("FAKE_GH_RUNS", "[]\\n"))
    if rc:
        sys.stderr.write("gh: fake runs failure\\n")
    sys.exit(rc)

sys.stderr.write("fake gh: unrouted call: %s\\n" % joined)
sys.exit(90)
"""

# `jq` and `date` are REAL here: the port asks the same two programs the twin asked, so a symlink is the honest stub. `gh` is the only fake.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq", "date", "grep", "sed", "cat")

CALLS_MARKER = "--- calls ---\n"


def _stub_path(tmp_path: pathlib.Path, side: str, *, with_gh: bool = True) -> str:
    stub = tmp_path / ("%s-bin" % side)
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    if with_gh:
        fake = stub / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
        found = shutil.which("gh", path=str(stub))
        assert found == str(fake), "the real gh shadowed the fake: %s" % found
    else:
        assert shutil.which("gh", path=str(stub)) is None, "gh leaked into the stub PATH"
    return str(stub)


def _fixture(tmp_path: pathlib.Path, side: str, *, with_common: bool = True) -> pathlib.Path:
    root = tmp_path / ("tree-%s" % side)
    (root / ".ci" / "rediacc_ci" / "housekeeping").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "housekeeping" / PORT.name)
    if with_common:
        (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
        shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    else:
        assert not (root / ".ci" / "scripts" / "lib" / "common.sh").exists()
    return root


def _run(
    tmp_path: pathlib.Path,
    side: str,
    args: list[str],
    *,
    with_gh: bool = True,
    with_common: bool = True,
    port_source: str | None = None,
    subject: pathlib.Path | None = None,
    **extra: str,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = _fixture(tmp_path, side, with_common=with_common)
    if port_source is not None:
        (root / ".ci" / "rediacc_ci" / "housekeeping" / PORT.name).write_text(
            port_source, encoding="utf-8"
        )
    call_log = tmp_path / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _stub_path(tmp_path, side, with_gh=with_gh),
        "HOME": str(tmp_path / ("%s-home" % side)),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(call_log),
        # NEVER the real repository, even if the fake were somehow bypassed.
        "RETRY_REPO": "acme/widget",
    }
    os.makedirs(env["HOME"], exist_ok=True)
    env.update(extra)

    if subject is None:
        subject = root / ".ci" / "rediacc_ci" / "housekeeping" / PORT.name
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *args],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


def _iso(hours_ago: float) -> str:
    when = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(hours=hours_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def runs_json(*records: dict) -> str:
    return json.dumps(list(records))


def a_run(
    run_id: int,
    *,
    name: str = "Cleanup PR Preview",
    path: str = NORMAL,
    head: str = LIVE_HEAD,
    attempt: int = 1,
    hours_ago: float = 1,
) -> dict:
    return {
        "id": run_id,
        "name": name,
        "path": path,
        "head_sha": head,
        "run_attempt": attempt,
        "created_at": _iso(hours_ago),
    }


SUMMARY = "considered=%d excluded=%d too-old=%d attempt-capped=%d dead-head=%d retried=%d"


def _null_name_record() -> dict:
    record = a_run(1, path=WATCHDOG)
    record["name"] = None
    return record


def _bad_date_record() -> dict:
    record = a_run(1)
    record["created_at"] = "not-a-date"
    return record


def case_kw(name: str) -> tuple[list[str], dict]:
    """One recorded case's argv and fake knobs, rebuilt fresh so `created_at` is always relative to the real now."""
    live = {"FAKE_GH_HEADS": LIVE_HEAD + "\n"}
    table: dict[str, tuple[list[str], dict]] = {
        "a-missing-gh": ([], {"with_gh": False}),
        "unreadable-branch-tips": ([], {"FAKE_GH_HEADS": "", "FAKE_GH_BRANCHES_RC": "1"}),
        "an-empty-branch-listing": ([], {"FAKE_GH_HEADS": ""}),
        "no-failed-runs": ([], {**live, "FAKE_GH_RUNS": "[]"}),
        "the-watchdog-is-excluded-by-path": (
            [],
            {
                **live,
                "FAKE_GH_RUNS": runs_json(a_run(1, name="Watchdog: run 99 (gen 2)", path=WATCHDOG)),
            },
        ),
        "older-than-the-age-floor": (
            [],
            {**live, "FAKE_GH_RUNS": runs_json(a_run(1, hours_ago=100))},
        ),
        "an-unparseable-created-at": (
            [],
            {**live, "FAKE_GH_RUNS": runs_json(_bad_date_record())},
        ),
        "the-attempt-cap": ([], {**live, "FAKE_GH_RUNS": runs_json(a_run(7, attempt=3))}),
        "a-head-that-is-no-longer-a-tip": (
            [],
            {**live, "FAKE_GH_RUNS": runs_json(a_run(1, head=DEAD_HEAD))},
        ),
        "an-eligible-run-is-reran": (
            [],
            {
                "FAKE_GH_HEADS": "%s\n%s\n" % (LIVE_HEAD, DEAD_HEAD),
                "FAKE_GH_RUNS": runs_json(a_run(32903006150)),
            },
        ),
        "the-reruns-output-is-swallowed": ([], {**live, "FAKE_GH_RUNS": runs_json(a_run(5))}),
        "a-rejected-rerun": (
            [],
            {**live, "FAKE_GH_RUNS": runs_json(a_run(5)), "FAKE_GH_RERUN_RC": "1"},
        ),
        "a-dry-run": (["--dry-run"], {**live, "FAKE_GH_RUNS": runs_json(a_run(5))}),
        "dash-n-is-a-live-run": (["-n"], {**live, "FAKE_GH_RUNS": runs_json(a_run(5))}),
        "the-per-night-cap": (
            [],
            {
                **live,
                "FAKE_GH_RUNS": runs_json(*[a_run(n) for n in range(1, 6)]),
                "RETRY_MAX_PER_RUN": "2",
            },
        ),
        "the-three-numeric-knobs": (
            [],
            {
                **live,
                "FAKE_GH_RUNS": runs_json(a_run(1, hours_ago=5, attempt=2)),
                "RETRY_MAX_AGE_HOURS": "2",
                "RETRY_MAX_ATTEMPT": "9",
            },
        ),
        "the-repo-comes-from-the-environment": (
            [],
            {**live, "FAKE_GH_RUNS": runs_json(a_run(1)), "RETRY_REPO": "other/repo"},
        ),
        "an-unreadable-runs-listing": (
            [],
            {**live, "FAKE_GH_RUNS": "", "FAKE_GH_RUNS_RC": "1"},
        ),
        "the-fallback-logger-world": (
            [],
            {**live, "FAKE_GH_RUNS": runs_json(a_run(5)), "with_common": False},
        ),
        "the-fallback-world-warn-path": ([], {"FAKE_GH_HEADS": "", "with_common": False}),
        "the-fallback-world-require-cmd": ([], {"with_common": False, "with_gh": False}),
        "a-null-workflow-name-shifts-the-fields": (
            [],
            {**live, "FAKE_GH_RUNS": runs_json(_null_name_record())},
        ),
    }
    return table[name]


CASES = (
    "a-missing-gh",
    "unreadable-branch-tips",
    "an-empty-branch-listing",
    "no-failed-runs",
    "the-watchdog-is-excluded-by-path",
    "older-than-the-age-floor",
    "an-unparseable-created-at",
    "the-attempt-cap",
    "a-head-that-is-no-longer-a-tip",
    "an-eligible-run-is-reran",
    "the-reruns-output-is-swallowed",
    "a-rejected-rerun",
    "a-dry-run",
    "dash-n-is-a-live-run",
    "the-per-night-cap",
    "the-three-numeric-knobs",
    "the-repo-comes-from-the-environment",
    "an-unreadable-runs-listing",
    "the-fallback-logger-world",
    "the-fallback-world-warn-path",
    "the-fallback-world-require-cmd",
    "a-null-workflow-name-shifts-the-fields",
)

# The one case the port deliberately does not reproduce line for line: bash's own arithmetic diagnostic. Compared with that line filtered out, in its own test.
DIVERGENT = "a-null-workflow-name-shifts-the-fields"

# bash's complaint about a timestamp reaching `-ge`, which the port reaches the same FALSE without.
ARITHMETIC_NOISE = "value too great for base"


def render(proc, calls: list[str], base: pathlib.Path) -> str:
    body = frozen.render(
        proc.returncode,
        frozen.mask_root(proc.stdout, base),
        frozen.mask_root(proc.stderr, base),
    )
    return body + CALLS_MARKER + "".join("%s\n" % frozen.mask_root(c, base) for c in calls)


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, calls_text = rest.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        [line for line in calls_text.splitlines() if line],
    )


def drive(tmp_path: pathlib.Path, name: str, **override):
    args, kw = case_kw(name)
    kw.update(override)
    return _run(tmp_path, "new", args, **kw)


def observed(tmp_path: pathlib.Path, name: str, **override) -> tuple[int, str, str, list[str]]:
    proc, calls = drive(tmp_path, name, **override)
    base = tmp_path / "tree-new"
    return (
        proc.returncode,
        frozen.mask_root(proc.stdout, base),
        frozen.mask_root(proc.stderr, base),
        [frozen.mask_root(c, base) for c in calls],
    )


def compare(tmp_path: pathlib.Path, name: str, **override) -> tuple[int, str, str, list[str]]:
    want = recorded(name)
    got = observed(tmp_path, name, **override)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert got[2] == want[2], "%s: stderr diverged from the recorded bytes" % name
    assert got[3] == want[3], "%s: the gh call sequence diverged:\n%s\n%s" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c != DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- Refusals ---------------------------------------------------------------------------


def test_missing_gh_is_refused_first() -> None:
    returncode, stdout, stderr, _ = recorded("a-missing-gh")
    assert returncode == 1
    assert stderr == "✗ Required command 'gh' is not available\n"
    assert stdout == ""


def test_unreadable_branch_tips_skip_rather_than_retry_on_incomplete_data() -> None:
    """FAIL CLOSED, AND EXIT 0 WHILE DOING IT. Without the branch tips a superseded run cannot be told from a current one, and reviving a superseded pipeline is the expensive mistake. It is not an error either, so the job stays green and tomorrow tries again."""
    returncode, _, stderr, calls = recorded("unreadable-branch-tips")
    assert returncode == 0
    assert "⚠ could not list branch tips; skipping rather than retrying" in stderr
    assert len(calls) == 1, "the runs listing was fetched anyway"
    assert "gh: fake branches failure" not in stderr, "gh's stderr leaked past 2>/dev/null"


def test_an_empty_but_successful_branch_listing_is_also_a_skip() -> None:
    returncode, _, stderr, _ = recorded("an-empty-branch-listing")
    assert returncode == 0
    assert "could not list branch tips" in stderr


# --------------------------------------------------------------------------- The five filters, one case each ---------------------------------------------------------------------------


def test_no_failed_runs_reports_the_normal_night() -> None:
    """A SWEEPER THAT RETRIES NOTHING MUST NOT LOOK BROKEN. The measured baseline is ~1 retry per night, so zero is the expected outcome and the summary line plus the closing sentence are what make it readable."""
    returncode, _, stderr, _ = recorded("no-failed-runs")
    assert returncode == 0
    assert (SUMMARY % (0, 0, 0, 0, 0, 0)) in stderr
    assert "nothing to retry -- on this repo's baseline that is the normal night" in stderr


def test_the_watchdog_is_excluded_by_path() -> None:
    """63 OF 64 MEASURED FAILURES ARE THIS ONE WORKFLOW failing by design. It is excluded by PATH because its display name is generated per run."""
    returncode, _, stderr, calls = recorded("the-watchdog-is-excluded-by-path")
    assert returncode == 0
    assert (SUMMARY % (1, 1, 0, 0, 0, 0)) in stderr
    assert not any("rerun-failed-jobs" in c for c in calls)


def test_a_run_older_than_the_age_floor_is_skipped() -> None:
    returncode, _, stderr, _ = recorded("older-than-the-age-floor")
    assert returncode == 0
    assert (SUMMARY % (1, 0, 1, 0, 0, 0)) in stderr


def test_an_unparseable_created_at_counts_as_too_old() -> None:
    """`date -u -d ... || echo 0` and then `-eq 0` was the too-old branch, so an unreadable timestamp never licenses a rerun. The direction matters more than the label."""
    returncode, _, stderr, _ = recorded("an-unparseable-created-at")
    assert returncode == 0
    assert (SUMMARY % (1, 0, 1, 0, 0, 0)) in stderr


def test_the_attempt_cap_says_so_out_loud() -> None:
    returncode, _, stderr, _ = recorded("the-attempt-cap")
    assert returncode == 0
    assert "skip 7 (Cleanup PR Preview): already at attempt 3; a rerun is not fixing this" in stderr
    assert (SUMMARY % (1, 0, 0, 1, 0, 0)) in stderr


def test_a_head_that_is_no_longer_a_branch_tip_is_superseded() -> None:
    returncode, _, stderr, _ = recorded("a-head-that-is-no-longer-a-tip")
    assert returncode == 0
    assert (SUMMARY % (1, 0, 0, 0, 1, 0)) in stderr


# --------------------------------------------------------------------------- The retry itself ---------------------------------------------------------------------------


def test_an_eligible_run_is_reran_and_the_call_is_exact() -> None:
    returncode, _, stderr, calls = recorded("an-eligible-run-is-reran")
    assert returncode == 0
    assert "api\t-X\tPOST\trepos/acme/widget/actions/runs/32903006150/rerun-failed-jobs" in calls
    assert "reran 32903006150 (Cleanup PR Preview, was attempt 1)" in stderr
    assert (SUMMARY % (1, 0, 0, 0, 0, 1)) in stderr
    assert "nothing to retry" not in stderr


def test_the_reruns_output_is_swallowed_on_both_streams(tmp_path: pathlib.Path) -> None:
    """`>/dev/null 2>&1`. The fake writes to both so a port that forgot one is caught here rather than in a nightly log."""
    _, stdout, stderr, _ = recorded("the-reruns-output-is-swallowed")
    assert "must never be seen" not in stdout + stderr
    _, new_out, new_err, _ = compare(tmp_path, "the-reruns-output-is-swallowed")
    assert "must never be seen" not in new_out + new_err


def test_a_rejected_rerun_is_a_warning_and_not_a_failure() -> None:
    """A run still winding down answers 403 "already running". The job must stay green: tomorrow picks it up, and failing here would page somebody nightly."""
    returncode, _, stderr, _ = recorded("a-rejected-rerun")
    assert returncode == 0
    assert "could not rerun 5 (Cleanup PR Preview); likely still in progress" in stderr
    assert (SUMMARY % (1, 0, 0, 0, 0, 0)) in stderr


def test_dry_run_posts_nothing_and_prints_eight_characters_of_the_head() -> None:
    returncode, _, stderr, calls = recorded("a-dry-run")
    assert returncode == 0
    assert "[DRY-RUN] would rerun 5 (Cleanup PR Preview, attempt 1, head aaaaaaaa)" in stderr
    assert not any("rerun-failed-jobs" in c for c in calls)
    assert (SUMMARY % (1, 0, 0, 0, 0, 1)) in stderr


def test_only_argv_one_spelled_exactly_dry_run_is_a_dry_run() -> None:
    """`[[ "${1:-}" == "--dry-run" ]]` and nothing else. `-n` is a LIVE run, and
    so is `--dry-run` in second position. Reproduced rather than improved: this script POSTs, and a caller who believes an unrecognised flag was honoured is the person this pins the behaviour for."""
    returncode, _, _, calls = recorded("dash-n-is-a-live-run")
    assert returncode == 0
    assert any("rerun-failed-jobs" in c for c in calls), "-n was treated as a dry run"


def test_the_per_night_cap_breaks_the_loop_and_says_so() -> None:
    returncode, _, stderr, calls = recorded("the-per-night-cap")
    assert returncode == 0
    assert "⚠ hit RETRY_MAX_PER_RUN=2; the rest wait for tomorrow" in stderr
    assert len([c for c in calls if "rerun-failed-jobs" in c]) == 2
    # `break`, not `continue`: the two runs it did not reach are not counted as considered either, so the summary reports 3 and not 5.
    assert (SUMMARY % (3, 0, 0, 0, 0, 2)) in stderr


def test_the_three_numeric_knobs_are_read_from_the_environment() -> None:
    returncode, _, stderr, _ = recorded("the-three-numeric-knobs")
    assert returncode == 0
    assert "Nightly retry: failed runs in acme/widget (last 2h)" in stderr
    assert (SUMMARY % (1, 0, 1, 0, 0, 0)) in stderr, "the 2h floor was not applied"


def test_the_repo_is_read_from_the_environment_and_reaches_every_url() -> None:
    _, _, _, calls = recorded("the-repo-comes-from-the-environment")
    assert calls[0] == "api\trepos/other/repo/branches?per_page=100\t--paginate\t--jq\t%s" % (
        port.BRANCHES_JQ
    )
    assert all("other/repo" in c for c in calls)


def test_an_unreadable_runs_listing_yields_no_candidates() -> None:
    """`|| echo '[]'`: a failed listing became an empty one, which prints the same zero summary a genuinely clean night prints. That is a real weakness of the twin and it is reproduced rather than repaired -- the branch-tip lookup above is the one that fails closed, and this one does not."""
    returncode, _, stderr, _ = recorded("an-unreadable-runs-listing")
    assert returncode == 0
    assert (SUMMARY % (0, 0, 0, 0, 0, 0)) in stderr


# --------------------------------------------------------------------------- The fallback logger world ---------------------------------------------------------------------------


def test_the_fallback_logger_world_moves_info_and_step_to_stdout() -> None:
    returncode, stdout, stderr, _ = recorded("the-fallback-logger-world")
    assert returncode == 0
    assert stdout.startswith("==> Nightly retry: failed runs in acme/widget (last 48h)\n")
    assert "  reran 5 (Cleanup PR Preview, was attempt 1)\n" in stdout
    assert "✓" not in stdout
    assert "→" not in stdout
    assert stderr == "", "the fallback world wrote to stderr: %r" % stderr


def test_the_fallback_world_warn_path_also_agrees() -> None:
    returncode, stdout, stderr, _ = recorded("the-fallback-world-warn-path")
    assert returncode == 0
    assert stderr == (
        "  WARN: could not list branch tips; skipping rather than retrying on incomplete data\n"
    )
    assert stdout == "==> Nightly retry: failed runs in acme/widget (last 48h)\n"


def test_the_fallback_world_require_cmd_is_its_own_and_still_reports() -> None:
    """The twin defined a private `require_cmd` in the fallback block because calling common.sh's would die at 127 while reporting nothing about the missing dependency it exists to report."""
    returncode, stdout, stderr, _ = recorded("the-fallback-world-require-cmd")
    assert returncode == 1
    assert stderr == "Required command 'gh' is not available\n"
    assert stdout == ""


# --------------------------------------------------------------------------- Pure helpers, driven against real bash ---------------------------------------------------------------------------


def _bash_read_fields(line: str) -> list[str]:
    """What `IFS=$'\\t' read -r a b c d e f` actually assigns, from real bash."""
    script = (
        "IFS=$'\\t' read -r a b c d e f\n"
        'printf "%s\\0%s\\0%s\\0%s\\0%s\\0%s" "$a" "$b" "$c" "$d" "$e" "$f"\n'
    )
    proc = subprocess.run(
        [BASH, "-c", script],
        input=line + "\n",
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    return proc.stdout.split("\0")


def test_read_fields_collapses_runs_of_tabs() -> None:
    """THE FIELD-SHIFTING HAZARD, PINNED IN BOTH DIRECTIONS. Tab is an IFS WHITESPACE character, so a null `.name` does not leave an empty field, it shifts every later field left by one and the workflow PATH is read as the name. Every case is checked against real bash so the claim is measured, not asserted."""
    cases = [
        "1\tCI\t.github/workflows/ci.yml\tabc\t1\t2026-01-01T00:00:00Z",
        "1\t\t.github/workflows/ci.yml\tabc\t1\t2026-01-01T00:00:00Z",
        "\t\t\t",
        "",
        "1\t2",
        "1\t2\t3\t4\t5\t6\t7\t8",
        "\tlead\ttrail\t",
    ]
    for case in cases:
        assert port.read_fields(case) == _bash_read_fields(case), case
    # And the hazard itself, spelled out.
    shifted = port.read_fields("1\t\t.github/workflows/ci.yml\tabc\t1\t2026-01-01T00:00:00Z")
    assert shifted[1] == ".github/workflows/ci.yml", "the shift is no longer reproduced"


def test_pure_helpers() -> None:
    assert port.is_excluded(WATCHDOG)
    assert not port.is_excluded(NORMAL)
    assert not port.is_excluded("")
    assert port.head_is_live("a" * 40, "a" * 40 + "\n" + "b" * 40)
    assert not port.head_is_live("c" * 40, "a" * 40)
    assert not port.head_is_live("", "a" * 40)
    assert port.env_int("X", 48, {}) == 48
    assert port.env_int("X", 48, {"X": ""}) == 48
    assert port.env_int("X", 48, {"X": "2"}) == 2
    assert port.created_epoch("1970-01-01T00:01:00Z") == 60
    assert port.created_epoch("not-a-date") == 0


def test_divergence_a_null_workflow_name_shifts_the_fields_and_only_bash_complains(
    tmp_path: pathlib.Path,
) -> None:
    """THE HAZARD, RECORDED END TO END, AND THE ONE DELIBERATE DIVERGENCE WITH IT.

    A run with a null `.name` collapsed to five tab-separated fields, so every later field shifted left: the workflow PATH was read as the name, the head sha as the path, the ATTEMPT NUMBER as the head, and the TIMESTAMP as the attempt. Both implementations reach the same verdict -- dead head, not retried -- and the six counters, the exit code and the gh call log all agree.

    What does NOT agree is one line. `[[ "2026-09-13T.." -ge 3 ]]` made bash write `value too great for base` to stderr and evaluate FALSE; the port reads the field as 0 and reaches the same FALSE without a diagnostic. `_as_int` names this in its docstring. It is asserted in BOTH directions here so nobody later "fixes" either side, and the ledger deliberately did not record
    this scenario.
    """
    want_exit, want_out, want_err, want_calls = recorded(DIVERGENT)
    returncode, stdout, stderr, calls = observed(tmp_path, DIVERGENT)
    assert want_exit == returncode == 0
    assert (SUMMARY % (1, 0, 0, 0, 1, 0)) in want_err, (
        "the shift no longer produces the documented verdict"
    )
    assert "excluded=0" in want_err, "the watchdog exclusion caught it after all"
    assert calls == want_calls
    assert stdout == want_out

    assert ARITHMETIC_NOISE in want_err, "the twin no longer complains; the divergence is stale"
    assert ARITHMETIC_NOISE not in stderr, "the port reproduces bash's arithmetic diagnostic"
    assert [ln for ln in want_err.splitlines() if ARITHMETIC_NOISE not in ln] == stderr.splitlines()


# --------------------------------------------------------------------------- The controls: these goldens can actually fail ---------------------------------------------------------------------------


def test_planted_watchdog_exclusion_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the watchdog exclusion -- the filter that removes 63 of 64 measured candidates and whose absence looks like a busy night rather than a bug. Driven red against the recording, then the source is confirmed byte-identical and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        'EXCLUDED_PATHS = (".github/workflows/watchdog-monitor.yml",)', "EXCLUDED_PATHS = ()"
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    _, _, _, want_calls = recorded("the-watchdog-is-excluded-by-path")
    assert not any("rerun-failed-jobs" in c for c in want_calls), (
        "the TWIN retried the watchdog; the plant is untested"
    )
    _, _, _, bad_calls = observed(
        tmp_path / "bad", "the-watchdog-is-excluded-by-path", port_source=mutated
    )
    assert any("rerun-failed-jobs" in c for c in bad_calls), "the mutant still excluded it"
    with pytest.raises(AssertionError):
        compare(tmp_path / "bad2", "the-watchdog-is-excluded-by-path", port_source=mutated)

    compare(tmp_path / "good", "the-watchdog-is-excluded-by-path")
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )


def test_planted_per_night_cap_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """THE NEW CONTROL ON THE GOLDENS. Turn the cap's `break` into a `continue`.

    Both spellings stop at two reruns and both warn, so the call log and the warning are identical; the only witness is the `considered=` counter, which the twin left at 3 because `break` never reached the remaining two runs. A mutant that kept sweeping reports 5 and warns three times. The mutation is written to a throwaway copy; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = (
        '            out.warn("hit RETRY_MAX_PER_RUN=%d; the rest wait for tomorrow" % max_retries)'
        "\n            break\n"
    )
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(
        anchor, anchor.replace("            break\n", "            continue\n")
    )
    assert mutated != original

    with pytest.raises(AssertionError):
        compare(tmp_path / "bad", "the-per-night-cap", port_source=mutated)
    compare(tmp_path / "good", "the-per-night-cap")
    assert PORT.read_text(encoding="utf-8") == original
