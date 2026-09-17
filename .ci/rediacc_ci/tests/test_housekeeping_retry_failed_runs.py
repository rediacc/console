"""Differential: `rediacc_ci.housekeeping.retry_failed_runs` against its twin
`.ci/scripts/housekeeping/retry-failed-runs.sh`.

A RECORDING FAKE `gh` ON A PATH WITH NO REAL `gh` ON IT. The live effect of
this script is `POST .../rerun-failed-jobs` against `rediacc/console`, and this
machine has a logged-in `gh`, so every case also pins `RETRY_REPO=acme/widget`:
a leak past the fake would still not name the real repository.

THE CALL LOG IS COMPARED, NOT JUST THE STREAMS, because "retried 1" and
"retried 1 against a different run id" print the same line.

BOTH LOGGING WORLDS ARE DRIVEN. `source common.sh 2>/dev/null || { ... }` gives
this script a second logger whose `log_info` and `log_step` write to STDOUT with
their own prefixes, and the fallback is not a cosmetic variant: on a fresh
clone every summary line moves stream. `test_the_fallback_logger_world_*` copies
each subject into a tree with no `.ci/scripts/lib/` and compares there too.

TIME IS PINNED BY CONSTRUCTION, not by freezing a clock. Fixtures compute
`created_at` relative to the real now, well inside or well outside the age
window, so the one-second skew between the twin's `date -u +%s` and the port's
`time.time()` can never decide a case.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.housekeeping import retry_failed_runs as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "housekeeping" / "retry-failed-runs.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "housekeeping" / "retry_failed_runs.py"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"

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

# `jq` and `date` are REAL here: the port asks the same two programs the twin asks, so a symlink is the honest stub. `gh` is the only fake.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq", "date", "grep", "sed", "cat")


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
    (root / ".ci" / "scripts" / "housekeeping").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "rediacc_ci" / "housekeeping").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "housekeeping" / TWIN.name)
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
    **extra: str,
):
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

    if side.startswith("old"):
        subject = root / ".ci" / "scripts" / "housekeeping" / TWIN.name
        runner = [BASH]
    else:
        subject = root / ".ci" / "rediacc_ci" / "housekeeping" / PORT.name
        runner = [sys.executable]
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


def run_both(tmp_path: pathlib.Path, args: list[str], **kw):
    old, old_calls = _run(tmp_path, "old", args, **kw)
    new, new_calls = _run(tmp_path, "new", args, **kw)
    return old, new, old_calls, new_calls


def assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, "%s: exit diverged: %r vs %r" % (
        label,
        old.returncode,
        new.returncode,
    )
    assert new.stdout == old.stdout, "%s: stdout diverged:\nold: %r\nnew: %r" % (
        label,
        old.stdout,
        new.stdout,
    )
    assert new.stderr == old.stderr, "%s: stderr diverged:\nold: %r\nnew: %r" % (
        label,
        old.stderr,
        new.stderr,
    )
    if old_calls is not None:
        assert new_calls == old_calls, "%s: gh call sequence diverged:\nold: %s\nnew: %s" % (
            label,
            old_calls,
            new_calls,
        )


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


# --------------------------------------------------------------------------- Refusals ---------------------------------------------------------------------------


def test_missing_gh_is_refused_first(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [], with_gh=False)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'gh' is not available\n"
    assert old.stdout == ""
    assert_agree(old, new, "missing-gh", old_calls, new_calls)


def test_unreadable_branch_tips_skip_rather_than_retry_on_incomplete_data(
    tmp_path: pathlib.Path,
) -> None:
    """FAIL CLOSED, AND EXIT 0 WHILE DOING IT. Without the branch tips a
    superseded run cannot be told from a current one, and reviving a superseded
    pipeline is the expensive mistake. It is not an error either, so the job
    stays green and tomorrow tries again."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], FAKE_GH_HEADS="", FAKE_GH_BRANCHES_RC="1"
    )
    assert old.returncode == 0
    assert "⚠ could not list branch tips; skipping rather than retrying" in old.stderr
    assert len(old_calls) == 1, "the runs listing was fetched anyway"
    assert "gh: fake branches failure" not in old.stderr, "gh's stderr leaked past 2>/dev/null"
    assert_agree(old, new, "no-branch-tips", old_calls, new_calls)


def test_an_empty_but_successful_branch_listing_is_also_a_skip(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [], FAKE_GH_HEADS="")
    assert old.returncode == 0
    assert "could not list branch tips" in old.stderr
    assert_agree(old, new, "empty-branch-tips", old_calls, new_calls)


# --------------------------------------------------------------------------- The five filters, one case each ---------------------------------------------------------------------------


def test_no_failed_runs_reports_the_normal_night(tmp_path: pathlib.Path) -> None:
    """A SWEEPER THAT RETRIES NOTHING MUST NOT LOOK BROKEN. The measured
    baseline is ~1 retry per night, so zero is the expected outcome and the
    summary line plus the closing sentence are what make it readable."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], FAKE_GH_HEADS=LIVE_HEAD + "\n", FAKE_GH_RUNS="[]"
    )
    assert old.returncode == 0
    assert (SUMMARY % (0, 0, 0, 0, 0, 0)) in old.stderr
    assert "nothing to retry -- on this repo's baseline that is the normal night" in old.stderr
    assert_agree(old, new, "empty-runs", old_calls, new_calls)


def test_the_watchdog_is_excluded_by_path(tmp_path: pathlib.Path) -> None:
    """63 OF 64 MEASURED FAILURES ARE THIS ONE WORKFLOW failing by design. It is
    excluded by PATH because its display name is generated per run."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(1, name="Watchdog: run 99 (gen 2)", path=WATCHDOG)),
    )
    assert old.returncode == 0
    assert (SUMMARY % (1, 1, 0, 0, 0, 0)) in old.stderr
    assert not any("rerun-failed-jobs" in c for c in old_calls)
    assert_agree(old, new, "watchdog-excluded", old_calls, new_calls)


def test_a_run_older_than_the_age_floor_is_skipped(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(1, hours_ago=100)),
    )
    assert old.returncode == 0
    assert (SUMMARY % (1, 0, 1, 0, 0, 0)) in old.stderr
    assert_agree(old, new, "too-old", old_calls, new_calls)


def test_an_unparseable_created_at_counts_as_too_old(tmp_path: pathlib.Path) -> None:
    """`date -u -d ... || echo 0` and then `-eq 0` is the too-old branch, so an
    unreadable timestamp never licenses a rerun. The direction matters more than
    the label."""
    record = a_run(1)
    record["created_at"] = "not-a-date"
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], FAKE_GH_HEADS=LIVE_HEAD + "\n", FAKE_GH_RUNS=runs_json(record)
    )
    assert old.returncode == 0
    assert (SUMMARY % (1, 0, 1, 0, 0, 0)) in old.stderr
    assert_agree(old, new, "bad-date", old_calls, new_calls)


def test_the_attempt_cap_says_so_out_loud(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(7, attempt=3)),
    )
    assert old.returncode == 0
    assert "skip 7 (Cleanup PR Preview): already at attempt 3; a rerun is not fixing this" in (
        old.stderr
    )
    assert (SUMMARY % (1, 0, 0, 1, 0, 0)) in old.stderr
    assert_agree(old, new, "attempt-capped", old_calls, new_calls)


def test_a_head_that_is_no_longer_a_branch_tip_is_superseded(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(1, head=DEAD_HEAD)),
    )
    assert old.returncode == 0
    assert (SUMMARY % (1, 0, 0, 0, 1, 0)) in old.stderr
    assert_agree(old, new, "dead-head", old_calls, new_calls)


# --------------------------------------------------------------------------- The retry itself ---------------------------------------------------------------------------


def test_an_eligible_run_is_reran_and_the_call_is_exact(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS="%s\n%s\n" % (LIVE_HEAD, DEAD_HEAD),
        FAKE_GH_RUNS=runs_json(a_run(32903006150)),
    )
    assert old.returncode == 0
    assert (
        "api\t-X\tPOST\trepos/acme/widget/actions/runs/32903006150/rerun-failed-jobs" in old_calls
    )
    assert "reran 32903006150 (Cleanup PR Preview, was attempt 1)" in old.stderr
    assert (SUMMARY % (1, 0, 0, 0, 0, 1)) in old.stderr
    assert "nothing to retry" not in old.stderr
    assert_agree(old, new, "reran", old_calls, new_calls)


def test_the_reruns_output_is_swallowed_on_both_streams(tmp_path: pathlib.Path) -> None:
    """`>/dev/null 2>&1`. The fake writes to both so a port that forgot one
    would be caught here rather than in a nightly log."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], FAKE_GH_HEADS=LIVE_HEAD + "\n", FAKE_GH_RUNS=runs_json(a_run(5))
    )
    assert "must never be seen" not in old.stdout + old.stderr
    assert "must never be seen" not in new.stdout + new.stderr
    assert_agree(old, new, "rerun-swallowed", old_calls, new_calls)


def test_a_rejected_rerun_is_a_warning_and_not_a_failure(tmp_path: pathlib.Path) -> None:
    """A run still winding down answers 403 "already running". The job must stay
    green: tomorrow picks it up, and failing here would page somebody nightly."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(5)),
        FAKE_GH_RERUN_RC="1",
    )
    assert old.returncode == 0
    assert "could not rerun 5 (Cleanup PR Preview); likely still in progress" in old.stderr
    assert (SUMMARY % (1, 0, 0, 0, 0, 0)) in old.stderr
    assert_agree(old, new, "rerun-rejected", old_calls, new_calls)


def test_dry_run_posts_nothing_and_prints_eight_characters_of_the_head(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--dry-run"],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(5)),
    )
    assert old.returncode == 0
    assert "[DRY-RUN] would rerun 5 (Cleanup PR Preview, attempt 1, head aaaaaaaa)" in old.stderr
    assert not any("rerun-failed-jobs" in c for c in old_calls)
    assert (SUMMARY % (1, 0, 0, 0, 0, 1)) in old.stderr
    assert_agree(old, new, "dry-run", old_calls, new_calls)


def test_only_argv_one_spelled_exactly_dry_run_is_a_dry_run(tmp_path: pathlib.Path) -> None:
    """`[[ "${1:-}" == "--dry-run" ]]` and nothing else. `-n` is a LIVE run, and
    so is `--dry-run` in second position. Reproduced rather than improved: this
    script POSTs, and a caller who believes an unrecognised flag was honoured is
    the person this pins the behaviour for."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["-n"],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(5)),
    )
    assert old.returncode == 0
    assert any("rerun-failed-jobs" in c for c in old_calls), "-n was treated as a dry run"
    assert_agree(old, new, "unknown-flag-is-live", old_calls, new_calls)


def test_the_per_night_cap_breaks_the_loop_and_says_so(tmp_path: pathlib.Path) -> None:
    records = [a_run(n) for n in range(1, 6)]
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(*records),
        RETRY_MAX_PER_RUN="2",
    )
    assert old.returncode == 0
    assert "⚠ hit RETRY_MAX_PER_RUN=2; the rest wait for tomorrow" in old.stderr
    assert len([c for c in old_calls if "rerun-failed-jobs" in c]) == 2
    # `break`, not `continue`: the two runs it did not reach are not counted as considered either, so the summary reports 3 and not 5.
    assert (SUMMARY % (3, 0, 0, 0, 0, 2)) in old.stderr
    assert_agree(old, new, "per-night-cap", old_calls, new_calls)


def test_the_three_numeric_knobs_are_read_from_the_environment(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(1, hours_ago=5, attempt=2)),
        RETRY_MAX_AGE_HOURS="2",
        RETRY_MAX_ATTEMPT="9",
    )
    assert old.returncode == 0
    assert "Nightly retry: failed runs in acme/widget (last 2h)" in old.stderr
    assert (SUMMARY % (1, 0, 1, 0, 0, 0)) in old.stderr, "the 2h floor was not applied"
    assert_agree(old, new, "env-knobs", old_calls, new_calls)


def test_the_repo_is_read_from_the_environment_and_reaches_every_url(
    tmp_path: pathlib.Path,
) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(1)),
        RETRY_REPO="other/repo",
    )
    assert old_calls[0] == "api\trepos/other/repo/branches?per_page=100\t--paginate\t--jq\t%s" % (
        port.BRANCHES_JQ
    )
    assert all("other/repo" in c for c in old_calls)
    assert_agree(old, new, "repo-override", old_calls, new_calls)


def test_an_unreadable_runs_listing_yields_no_candidates(tmp_path: pathlib.Path) -> None:
    """`|| echo '[]'`: a failed listing becomes an empty one, which prints the
    same zero summary a genuinely clean night prints. That is a real weakness of
    the twin and it is reproduced rather than repaired -- the branch-tip lookup
    above is the one that fails closed, and this one does not."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        [],
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS="",
        FAKE_GH_RUNS_RC="1",
    )
    assert old.returncode == 0
    assert (SUMMARY % (0, 0, 0, 0, 0, 0)) in old.stderr
    assert_agree(old, new, "runs-unreadable", old_calls, new_calls)


# --------------------------------------------------------------------------- The fallback logger world ---------------------------------------------------------------------------


def test_the_fallback_logger_world_moves_info_and_step_to_stdout(
    tmp_path: pathlib.Path,
) -> None:
    old, old_calls = _run(
        tmp_path,
        "old",
        [],
        with_common=False,
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(5)),
    )
    new, new_calls = _run(
        tmp_path,
        "new",
        [],
        with_common=False,
        FAKE_GH_HEADS=LIVE_HEAD + "\n",
        FAKE_GH_RUNS=runs_json(a_run(5)),
    )
    assert old.returncode == 0
    assert old.stdout.startswith("==> Nightly retry: failed runs in acme/widget (last 48h)\n")
    assert "  reran 5 (Cleanup PR Preview, was attempt 1)\n" in old.stdout
    assert "✓" not in old.stdout
    assert "→" not in old.stdout
    assert old.stderr == "", "the fallback world wrote to stderr: %r" % old.stderr
    assert_agree(old, new, "fallback-logger", old_calls, new_calls)


def test_the_fallback_world_warn_path_also_agrees(tmp_path: pathlib.Path) -> None:
    old, old_calls = _run(tmp_path, "old", [], with_common=False, FAKE_GH_HEADS="")
    new, new_calls = _run(tmp_path, "new", [], with_common=False, FAKE_GH_HEADS="")
    assert old.returncode == 0
    assert old.stderr == (
        "  WARN: could not list branch tips; skipping rather than retrying on incomplete data\n"
    )
    assert old.stdout == "==> Nightly retry: failed runs in acme/widget (last 48h)\n"
    assert_agree(old, new, "fallback-warn", old_calls, new_calls)


def test_the_fallback_world_require_cmd_is_its_own_and_still_reports(
    tmp_path: pathlib.Path,
) -> None:
    """The twin defines a private `require_cmd` in the fallback block because
    calling common.sh's would die at 127 while reporting nothing about the
    missing dependency it exists to report."""
    old, old_calls = _run(tmp_path, "old", [], with_common=False, with_gh=False)
    new, new_calls = _run(tmp_path, "new", [], with_common=False, with_gh=False)
    assert old.returncode == 1
    assert old.stderr == "Required command 'gh' is not available\n"
    assert old.stdout == ""
    assert_agree(old, new, "fallback-require-cmd", old_calls, new_calls)


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
    """THE FIELD-SHIFTING HAZARD, PINNED IN BOTH DIRECTIONS. Tab is an IFS
    WHITESPACE character, so a null `.name` does not leave an empty field, it
    shifts every later field left by one and the workflow PATH is read as the
    name. Every case is checked against real bash so the claim is measured, not
    asserted."""
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
    """THE HAZARD, DRIVEN END TO END, AND THE ONE DELIBERATE DIVERGENCE WITH IT.

    A run with a null `.name` collapses to five tab-separated fields, so every
    later field shifts left: the workflow PATH is read as the name, the head sha
    as the path, the ATTEMPT NUMBER as the head, and the TIMESTAMP as the
    attempt. Both implementations then reach the same verdict -- dead head, not
    retried -- and the six counters, the exit code and the gh call log all
    agree.

    What does NOT agree is one line. `[[ "2026-09-13T.." -ge 3 ]]` makes bash
    write `value too great for base (error token is "09")` to stderr and
    evaluate FALSE; the port reads the field as 0 and reaches the same FALSE
    without a diagnostic. `_as_int` names this in its docstring. It is asserted
    in BOTH directions here so nobody later "fixes" either side, and the
    ledger deliberately does not record this scenario.
    """
    record = a_run(1, path=WATCHDOG)
    record["name"] = None
    old, new, old_calls, new_calls = run_both(
        tmp_path, [], FAKE_GH_HEADS=LIVE_HEAD + "\n", FAKE_GH_RUNS=runs_json(record)
    )
    assert old.returncode == new.returncode == 0
    assert (SUMMARY % (1, 0, 0, 0, 1, 0)) in old.stderr, (
        "the shift no longer produces the documented verdict"
    )
    assert "excluded=0" in old.stderr, "the watchdog exclusion caught it after all"
    assert old_calls == new_calls
    assert old.stdout == new.stdout

    noise = 'value too great for base (error token is "09")'
    assert noise in old.stderr, "the twin no longer complains; the divergence is stale"
    assert noise not in new.stderr, "the port started reproducing bash's arithmetic diagnostic"
    assert [ln for ln in old.stderr.splitlines() if noise not in ln] == new.stderr.splitlines()


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the watchdog exclusion -- the filter that removes
    63 of 64 measured candidates and whose absence looks like a busy night
    rather than a bug. Driven red, then the source is confirmed byte-identical
    and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        'EXCLUDED_PATHS = (".github/workflows/watchdog-monitor.yml",)', "EXCLUDED_PATHS = ()"
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    kw = {
        "FAKE_GH_HEADS": LIVE_HEAD + "\n",
        "FAKE_GH_RUNS": runs_json(a_run(1, name="Watchdog: run 99 (gen 2)", path=WATCHDOG)),
    }
    old, old_calls = _run(tmp_path, "old", [], **kw)
    bad, bad_calls = _run(tmp_path, "new", [], port_source=mutated, **kw)
    assert not any("rerun-failed-jobs" in c for c in old_calls), (
        "the TWIN retried the watchdog; the plant is untested"
    )
    assert any("rerun-failed-jobs" in c for c in bad_calls), "the mutant still excluded it"
    assert bad.returncode == old.returncode, (
        "the plant is invisible in the exit code, which is why the call log is compared"
    )

    good, good_calls = _run(tmp_path, "new", [], **kw)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
