"""`rediacc_ci.release.check_soak_period`, driven directly.

WHILE BOTH COPIES EXISTED every case below ran `.ci/scripts/release/check-soak-period.sh` over the same environment and compared its stdout, its stderr and its `$GITHUB_OUTPUT` bytes against the port's.
The K=5 ledger `.ci/shadow/w7p5a-check-soak-period.observations.jsonl` recorded that verdict over five distinct trees (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-check-soak-period --assert --k 5`) and licensed the port; W7 P5 retired the twin and the cases that executed it went with it.

THE SILENT-ABORT CASE (`test_unparseable_date_aborts_silently`) IS THE ONE WORTH READING FIRST. It looks like a missing assertion rather than a real case: the subject exits 1 with EMPTY stdout, EMPTY stderr and an EMPTY `$GITHUB_OUTPUT`. That is not this test failing to check anything. It is the twin's own `set -e` behaviour (see the port's module docstring), measured directly
against the real `date` binary while both copies existed, then reproduced by the port rather than "fixed" into a helpful error message the twin never printed.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

MODULE = "check_soak_period"


def edge_date(days_ago: int) -> str:
    """An `EDGE_DATE` exactly `days_ago` days before the moment this runs.

    A literal calendar date rots: the age is computed from the clock AT RUN TIME, so a fixture pinned to a fixed date drifts by one real day every day this file exists, and it drifted for six days before this was noticed. The arithmetic is a FLOOR (whole days from a second count), so subtracting exactly `days_ago * 86400` seconds keeps the floor at `days_ago` for as long as the
    test itself takes to run.
    """
    # Suppressed on this LINE only, rather than disabling DTZ in pyproject: the rule is right everywhere else and wrong here. The twin stamped and read this in LOCAL time (`date +%s` against a `%Y-%m-%dT%H:%M:%S` string carrying no offset) and the port reproduces that, so a tz-aware `now()` would shift the fixture by the machine's offset and move the floor across a day boundary on
    # any host east or west of Greenwich -- the same two-clock defect block_stale_pr_branch_date.py records in its own port notes.
    then = datetime.datetime.now() - datetime.timedelta(days=days_ago)  # noqa: DTZ005
    return then.strftime("%Y-%m-%dT%H:%M:%S")


def run_port(tmp_path: pathlib.Path, env_extra: dict[str, str]) -> tuple[tuple[int, str, str], str]:
    out = tmp_path / "output.txt"
    env = diff.env_for(
        **env_extra,
        GITHUB_OUTPUT=str(out),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=env, timeout=30)
    written = out.read_text(encoding="utf-8") if out.exists() else ""
    return result, written


def test_old_edge_release_is_ready(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(70), "SOAK_DAYS": "7"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert out == "Edge release age: 70 days (soak: 7 days)\nSoak period complete\n"
    assert written == "ready=true\n"


def test_fresh_edge_release_is_not_ready(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(2), "SOAK_DAYS": "7"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert out == "Edge release age: 2 days (soak: 7 days)\nEdge needs 5 more day(s) of soak\n"
    assert written == "ready=false\n"


def test_force_bypasses_the_soak_window(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(4), "SOAK_DAYS": "7", "FORCE": "true"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert (
        out
        == "Edge release age: 4 days (soak: 7 days)\nForce promotion requested, skipping soak check\n"
    )
    assert written == "ready=true\n"


def test_unparseable_date_aborts_silently(tmp_path: pathlib.Path) -> None:
    """See the module docstring. Not a weak assertion -- this IS the behaviour the twin had, measured directly against it while it existed."""
    env = {"EDGE_DATE": "not-a-date", "SOAK_DAYS": "7"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, out, err) == (1, "", "")
    assert written == ""


def test_missing_soak_days_is_refused_and_names_the_variable(tmp_path: pathlib.Path) -> None:
    (exit_code, _, err), written = run_port(tmp_path, {"EDGE_DATE": "2026-07-01T00:00:00"})
    assert exit_code == 1
    assert "SOAK_DAYS" in err
    assert "must be set" in err
    assert written == ""
