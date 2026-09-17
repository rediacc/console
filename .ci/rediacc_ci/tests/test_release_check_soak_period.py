"""`rediacc_ci.release.check_soak_period` against its bash twin.

Sibling of `test_deploy_resolve_account_deploy_config.py`; see that file for
why `/dev/stdout` is not used as `$GITHUB_OUTPUT`. The K=5 ledger is
`.ci/shadow/w7p5a-check-soak-period.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-check-soak-period --assert --k 5` -> "equivalence holds over 5 distinct trees").

THE SILENT-ABORT CASE (`test_unparseable_date_aborts_silently_on_both_sides`) IS THE ONE WORTH READING FIRST. It looks like a missing assertion rather than a real case: both sides exit 1 with EMPTY stdout, EMPTY stderr, and an EMPTY `$GITHUB_OUTPUT`. That is not this test failing to check anything -- it is the twin's own `set -e` behaviour (see the port's module docstring) proven
directly against the real `date` binary on this host, then reproduced by the port rather than "fixed" into a helpful error message the twin never printed.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN = ".ci/scripts/release/check-soak-period.sh"
MODULE = "check_soak_period"


def edge_date(days_ago: int) -> str:
    """An `EDGE_DATE` exactly `days_ago` days before the moment this runs.

    A literal calendar date rots: the twin computes age from `date +%s` AT RUN TIME, so a fixture pinned to a fixed date drifts by one real day every day this file exists, and it drifted for six days before this was noticed. The twin's own arithmetic is a FLOOR (`$(((NOW_EPOCH - EDGE_EPOCH) / 86400))` on bash integers), so subtracting exactly `days_ago * 86400` seconds keeps the
    floor at `days_ago` for as long as the test itself takes to run.
    """
    # Suppressed on this LINE only, rather than disabling DTZ in pyproject: the rule is right everywhere else and wrong here. The twin stamps and reads this in LOCAL time (`date +%s` against a `%Y-%m-%dT%H:%M:%S` string carrying no offset), so a tz-aware `now()` would shift the fixture by the machine's offset and move the floor across a day boundary on any host east or west of
    # Greenwich -- the same two-clock defect block_stale_pr_branch_date.py records in its own port notes.
    then = datetime.datetime.now() - datetime.timedelta(days=days_ago)  # noqa: DTZ005
    return then.strftime("%Y-%m-%dT%H:%M:%S")


def run_both(
    tmp_path: pathlib.Path, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    out_old = tmp_path / "old-output.txt"
    out_new = tmp_path / "new-output.txt"
    old_env = diff.env_for(**env_extra, GITHUB_OUTPUT=str(out_old))
    new_env = diff.env_for(
        **env_extra,
        GITHUB_OUTPUT=str(out_new),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=new_env, timeout=30)
    old_output = out_old.read_text(encoding="utf-8") if out_old.exists() else ""
    new_output = out_new.read_text(encoding="utf-8") if out_new.exists() else ""
    return old, new, old_output, new_output


def test_old_edge_release_is_ready(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(70), "SOAK_DAYS": "7"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_out == "Edge release age: 70 days (soak: 7 days)\nSoak period complete\n"
    assert new_out == old_out
    assert old_output == "ready=true\n"
    assert new_output == old_output


def test_fresh_edge_release_is_not_ready(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(2), "SOAK_DAYS": "7"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert old_output == "ready=false\n"
    assert new_output == old_output
    assert old_out == new_out


def test_force_bypasses_the_soak_window(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(4), "SOAK_DAYS": "7", "FORCE": "true"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_err) == (0, "")
    assert (new_exit, new_err) == (0, "")
    assert (
        old_out
        == "Edge release age: 4 days (soak: 7 days)\nForce promotion requested, skipping soak check\n"
    )
    assert new_out == old_out
    assert old_output == "ready=true\n"
    assert new_output == old_output


def test_unparseable_date_aborts_silently_on_both_sides(tmp_path: pathlib.Path) -> None:
    """See the module docstring. Not a weak assertion -- this IS the twin's
    behaviour, measured directly against the real bash script."""
    env = {"EDGE_DATE": "not-a-date", "SOAK_DAYS": "7"}
    (old_exit, old_out, old_err), (new_exit, new_out, new_err), old_output, new_output = run_both(
        tmp_path, env
    )
    assert (old_exit, old_out, old_err) == (1, "", "")
    assert (new_exit, new_out, new_err) == (1, "", "")
    assert old_output == ""
    assert new_output == ""


def test_missing_soak_days_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": "2026-07-01T00:00:00"}
    (old_exit, _, old_err), (new_exit, _, new_err), _, _ = run_both(tmp_path, env)
    assert old_exit == 1
    assert new_exit == 1
    assert "SOAK_DAYS" in old_err
    assert "must be set" in old_err
    assert "SOAK_DAYS" in new_err
    assert "must be set" in new_err
