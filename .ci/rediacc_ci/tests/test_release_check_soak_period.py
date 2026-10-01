"""`rediacc_ci.release.check_soak_period`, driven directly.

WHILE BOTH COPIES EXISTED every case below ran `.ci/scripts/release/check-soak-period.sh` over the same environment and compared its stdout, its stderr and its `$GITHUB_OUTPUT` bytes against the port's.
The K=5 ledger `.ci/shadow/w7p5a-check-soak-period.observations.jsonl` recorded that verdict over five distinct trees (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-check-soak-period --assert --k 5`) and licensed the port; W7 P5 retired the twin and the cases that executed it went with it.

THE SILENT-ABORT CASE (`test_unparseable_date_aborts_silently`) IS THE ONE WORTH READING FIRST. It looks like a missing assertion rather than a real case: the subject exits 1 with EMPTY stdout, EMPTY stderr and an EMPTY `$GITHUB_OUTPUT`. That is not this test failing to check anything. It is the twin's own `set -e` behaviour (see the port's module docstring), measured directly
against the real `date` binary while both copies existed, then reproduced by the port rather than "fixed" into a helpful error message the twin never printed.
"""

from __future__ import annotations

import datetime
import pathlib
import subprocess

from rediacc_ci.tests import differential as diff

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
    assert written == "ready=true\npath=soak\n"


def test_fresh_edge_release_is_not_ready(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(2), "SOAK_DAYS": "7"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert out == "Edge release age: 2 days (soak: 7 days)\nEdge needs 5 more day(s) of soak\n"
    assert written == "ready=false\npath=soak\n"


def test_force_bypasses_the_soak_window(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(4), "SOAK_DAYS": "7", "FORCE": "true"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert (
        out
        == "Edge release age: 4 days (soak: 7 days)\nForce promotion requested, skipping soak check\n"
    )
    assert written == "ready=true\npath=force\n"


def test_delta_an_unparseable_date_is_named(tmp_path: pathlib.Path) -> None:
    """INTENTIONAL DELTA (Rule T): the twin's `set -e` aborted with exit 1 and NOTHING on either stream, so a promote job went red with no reason in its log. The port exits 1 and names the variable and its value on stderr, still writing nothing to `$GITHUB_OUTPUT` and printing nothing on stdout."""
    env = {"EDGE_DATE": "not-a-date", "SOAK_DAYS": "7"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert exit_code == 1
    assert out == ""
    assert written == ""
    assert "EDGE_DATE" in err
    assert "'not-a-date'" in err


def test_delta_a_non_numeric_soak_days_is_named_not_a_traceback(tmp_path: pathlib.Path) -> None:
    """INTENTIONAL DELTA (Rule T): the twin's `[[ -lt $SOAK_DAYS ]]` printed a bash arithmetic diagnostic and read false (so it promoted); the port used to die in a Python traceback. It now refuses by name before anything is decided."""
    env = {"EDGE_DATE": edge_date(2), "SOAK_DAYS": "seven"}
    (exit_code, _out, err), written = run_port(tmp_path, env)
    assert exit_code == 1
    assert "SOAK_DAYS" in err
    assert "'seven'" in err
    assert "Traceback" not in err
    assert written == ""


def test_missing_soak_days_is_refused_and_names_the_variable(tmp_path: pathlib.Path) -> None:
    (exit_code, _, err), written = run_port(tmp_path, {"EDGE_DATE": "2026-07-01T00:00:00"})
    assert exit_code == 1
    assert "SOAK_DAYS" in err
    assert "must be set" in err
    assert written == ""


# --- The nightly waiver (operator ruling 2026-09-30) ---------------------------
#
# Driven against a REAL throwaway git repository, not a mocked runner: the claim under test is what `git merge-base --is-ancestor` answers for a tag's commit, and a mock would only restate the implementation. History: A <- B (main, the nightly head) and A <- C (a side commit the nightly never saw).


def _git(cwd: pathlib.Path, *args: str) -> str:
    env = diff.env_for(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@t",
    )
    proc = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def make_history(root: pathlib.Path) -> dict[str, str]:
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "tag.gpgsign", "false")
    _git(root, "commit", "-q", "--allow-empty", "-m", "A")
    a = _git(root, "rev-parse", "HEAD")
    _git(root, "commit", "-q", "--allow-empty", "-m", "B")
    b = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "-b", "side", a)
    _git(root, "commit", "-q", "--allow-empty", "-m", "C")
    c = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")
    return {"A": a, "B": b, "C": c}


def run_in(
    repo_dir: pathlib.Path, tmp_path: pathlib.Path, env_extra: dict[str, str]
) -> tuple[tuple[int, str, str], str]:
    out = tmp_path / "output.txt"
    env = diff.env_for(
        **env_extra,
        GITHUB_OUTPUT=str(out),
        PYTHONPATH=str(pathlib.Path(diff.repo()) / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=env, timeout=30, cwd=str(repo_dir)
    )
    written = out.read_text(encoding="utf-8") if out.exists() else ""
    return result, written


def nightly_env(days_ago: int, head_sha: str, version: str = "1.2.3") -> dict[str, str]:
    return {
        "EDGE_DATE": edge_date(days_ago),
        "SOAK_DAYS": "7",
        "PROMOTE_TRIGGER": "workflow_run",
        "EDGE_VERSION": version,
        "NIGHTLY_HEAD_SHA": head_sha,
    }


def test_nightly_containing_the_edge_commit_skips_the_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["A"])
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(1, h["B"]))
    assert (exit_code, err) == (0, "")
    assert "is contained in the green nightly head" in out
    assert "Decided by: green nightly contains the edge commit" in out
    assert written == "ready=true\npath=nightly\n"


def test_nightly_on_the_edge_commit_itself_skips_the_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "-a", "-m", "annotated", "v1.2.3", h["B"])
    (exit_code, _, err), written = run_in(repo_dir, tmp_path, nightly_env(0, h["B"]))
    assert (exit_code, err) == (0, "")
    assert written == "ready=true\npath=nightly\n"


def test_nightly_not_containing_the_edge_commit_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    """The mutant this pins: invert `--is-ancestor`'s verdict and this case promotes a 2-day-old edge the nightly never tested."""
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["C"])
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(2, h["B"]))
    assert (exit_code, err) == (0, "")
    assert "is NOT contained in the green nightly head" in out
    assert "Edge needs 5 more day(s) of soak" in out
    assert written == "ready=false\npath=soak\n"


def test_nightly_not_containing_an_old_edge_still_promotes_by_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["C"])
    (exit_code, _, err), written = run_in(repo_dir, tmp_path, nightly_env(9, h["B"]))
    assert (exit_code, err) == (0, "")
    assert written == "ready=true\npath=soak\n"


def test_nightly_with_a_missing_tag_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(2, h["B"]))
    assert (exit_code, err) == (0, "")
    assert "tag v1.2.3 does not resolve" in out
    assert written == "ready=false\npath=soak\n"


def test_nightly_with_an_unknown_head_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["A"])
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(2, "f" * 40))
    assert (exit_code, err) == (0, "")
    assert "is not in this checkout" in out
    assert written == "ready=false\npath=soak\n"


def test_nightly_outside_any_git_repository_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    (exit_code, _, err), written = run_in(bare, tmp_path, nightly_env(2, "a" * 40))
    assert (exit_code, err) == (0, "")
    assert written == "ready=false\npath=soak\n"


def test_nightly_with_a_malformed_head_sha_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["A"])
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(2, "HEAD"))
    assert (exit_code, err) == (0, "")
    assert "is not a full commit SHA" in out
    assert written == "ready=false\npath=soak\n"


def test_head_sha_is_ignored_on_the_schedule_trigger(tmp_path: pathlib.Path) -> None:
    """The 06:00 soak run is unchanged even if a head SHA were somehow present: only `workflow_run` consults ancestry."""
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["A"])
    env = nightly_env(2, h["B"])
    env["PROMOTE_TRIGGER"] = "schedule"
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert out == "Edge release age: 2 days (soak: 7 days)\nEdge needs 5 more day(s) of soak\n"
    assert written == "ready=false\npath=soak\n"


def test_force_wins_on_the_nightly_trigger_without_consulting_git(tmp_path: pathlib.Path) -> None:
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    env = nightly_env(2, "a" * 40)
    env["FORCE"] = "true"
    (exit_code, out, err), written = run_in(bare, tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert "Nightly check" not in out
    assert written == "ready=true\npath=force\n"
