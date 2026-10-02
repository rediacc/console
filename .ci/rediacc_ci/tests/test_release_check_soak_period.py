"""`rediacc_ci.release.check_soak_period`, driven directly.

WHILE BOTH COPIES EXISTED every case below ran `.ci/scripts/release/check-soak-period.sh` over the same environment and compared its stdout, its stderr and its `$GITHUB_OUTPUT` bytes against the port's.
The K=5 ledger `.ci/shadow/w7p5a-check-soak-period.observations.jsonl` recorded that verdict over five distinct trees (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-check-soak-period --assert --k 5`) and licensed the port; W7 P5 retired the twin and the cases that executed it went with it.

THE SILENT-ABORT CASE (`test_unparseable_date_aborts_silently`) IS THE ONE WORTH READING FIRST. It looks like a missing assertion rather than a real case: the subject exits 1 with EMPTY stdout, EMPTY stderr and an EMPTY `$GITHUB_OUTPUT`. That is not this test failing to check anything. It is the twin's own `set -e` behaviour (see the port's module docstring), measured directly
against the real `date` binary while both copies existed, then reproduced by the port rather than "fixed" into a helpful error message the twin never printed.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess

from rediacc_ci.release import list_edge_releases
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


def head(written: str) -> str:
    """The `ready` and `path` lines, which every case judges; `version` and `date` are asserted where the case is about them."""
    return "".join(written.splitlines(keepends=True)[:2])


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
    env = {"EDGE_DATE": edge_date(70), "SOAK_DAYS": "7", "EDGE_VERSION": "1.2.3"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert out == "Edge release age: 70 days (soak: 7 days)\nSoak period complete\n"
    assert head(written) == "ready=true\npath=soak\n"
    assert "version=1.2.3\n" in written


def test_fresh_edge_release_is_not_ready(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(2), "SOAK_DAYS": "7", "EDGE_VERSION": "1.2.3"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert out == "Edge release age: 2 days (soak: 7 days)\nEdge needs 5 more day(s) of soak\n"
    assert head(written) == "ready=false\npath=soak\n"
    assert "version=\n" in written


def test_force_bypasses_the_soak_window(tmp_path: pathlib.Path) -> None:
    env = {"EDGE_DATE": edge_date(4), "SOAK_DAYS": "7", "FORCE": "true", "EDGE_VERSION": "1.2.3"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert (
        out
        == "Edge release age: 4 days (soak: 7 days)\nForce promotion requested, skipping soak check\n"
    )
    assert head(written) == "ready=true\npath=force\n"
    assert "version=1.2.3\n" in written


def test_delta_an_unparseable_date_is_named(tmp_path: pathlib.Path) -> None:
    """INTENTIONAL DELTA (Rule T): the twin's `set -e` aborted with exit 1 and NOTHING on either stream, so a promote job went red with no reason in its log. The port exits 1 and names the variable and its value on stderr, still writing nothing to `$GITHUB_OUTPUT` and printing nothing on stdout."""
    env = {"EDGE_DATE": "not-a-date", "SOAK_DAYS": "7", "EDGE_VERSION": "1.2.3"}
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert exit_code == 1
    assert out == ""
    assert written == ""
    assert "EDGE_DATE" in err
    assert "'not-a-date'" in err


def test_delta_a_non_numeric_soak_days_is_named_not_a_traceback(tmp_path: pathlib.Path) -> None:
    """INTENTIONAL DELTA (Rule T): the twin's `[[ -lt $SOAK_DAYS ]]` printed a bash arithmetic diagnostic and read false (so it promoted); the port used to die in a Python traceback. It now refuses by name before anything is decided."""
    env = {"EDGE_DATE": edge_date(2), "SOAK_DAYS": "seven", "EDGE_VERSION": "1.2.3"}
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
    assert head(written) == "ready=true\npath=nightly\n"
    assert "version=1.2.3\n" in written


def test_nightly_on_the_edge_commit_itself_skips_the_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "-a", "-m", "annotated", "v1.2.3", h["B"])
    (exit_code, _, err), written = run_in(repo_dir, tmp_path, nightly_env(0, h["B"]))
    assert (exit_code, err) == (0, "")
    assert head(written) == "ready=true\npath=nightly\n"
    assert "version=1.2.3\n" in written


def test_nightly_not_containing_the_edge_commit_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    """The mutant this pins: invert `--is-ancestor`'s verdict and this case promotes a 2-day-old edge the nightly never tested."""
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["C"])
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(2, h["B"]))
    assert (exit_code, err) == (0, "")
    assert "is NOT contained in the green nightly head" in out
    assert "Edge needs 5 more day(s) of soak" in out
    assert head(written) == "ready=false\npath=soak\n"
    assert "version=\n" in written


def test_nightly_not_containing_an_old_edge_still_promotes_by_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["C"])
    (exit_code, _, err), written = run_in(repo_dir, tmp_path, nightly_env(9, h["B"]))
    assert (exit_code, err) == (0, "")
    assert head(written) == "ready=true\npath=soak\n"
    assert "version=1.2.3\n" in written


def test_nightly_with_a_missing_tag_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(2, h["B"]))
    assert (exit_code, err) == (0, "")
    assert "tag v1.2.3 does not resolve" in out
    assert head(written) == "ready=false\npath=soak\n"
    assert "version=\n" in written


def test_nightly_with_an_unknown_head_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["A"])
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(2, "f" * 40))
    assert (exit_code, err) == (0, "")
    assert "is not in this checkout" in out
    assert head(written) == "ready=false\npath=soak\n"
    assert "version=\n" in written


def test_nightly_outside_any_git_repository_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    (exit_code, _, err), written = run_in(bare, tmp_path, nightly_env(2, "a" * 40))
    assert (exit_code, err) == (0, "")
    assert head(written) == "ready=false\npath=soak\n"
    assert "version=\n" in written


def test_nightly_with_a_malformed_head_sha_falls_back_to_soak(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.2.3", h["A"])
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, nightly_env(2, "HEAD"))
    assert (exit_code, err) == (0, "")
    assert "is not a full commit SHA" in out
    assert head(written) == "ready=false\npath=soak\n"
    assert "version=\n" in written


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
    assert head(written) == "ready=false\npath=soak\n"
    assert "version=\n" in written


def test_force_wins_on_the_nightly_trigger_without_consulting_git(tmp_path: pathlib.Path) -> None:
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    env = nightly_env(2, "a" * 40)
    env["FORCE"] = "true"
    (exit_code, out, err), written = run_in(bare, tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert "Nightly check" not in out
    assert head(written) == "ready=true\npath=force\n"
    assert "version=1.2.3\n" in written


# --- The walk back (PLAN-plan-per-pr-loop R2) ------------------------------------
#
# With a release on every merge the newest edge is almost always younger than the soak, so judging it alone starved stable from 2026-09-15 on. The rule now: promote the NEWEST edge release that has soaked, walking back from the newest, never at or below the current stable. `EDGE_RELEASES` carries the older candidates (`list_edge_releases`' output); `EDGE_VERSION` / `EDGE_DATE` stay the newest edge, the one R2's `<dir>/edge/` trees carry.


def releases(*pairs: tuple[str, int]) -> str:
    return json.dumps([{"version": v, "date": edge_date(days)} for v, days in pairs])


def walk_env(stable: str = "1.0.0", **extra: str) -> dict[str, str]:
    env = {
        "EDGE_VERSION": "1.0.3",
        "EDGE_DATE": edge_date(1),
        "SOAK_DAYS": "7",
        "STABLE_VERSION": stable,
        "EDGE_RELEASES": releases(("1.0.3", 1), ("1.0.2", 4), ("1.0.1", 9)),
    }
    env.update(extra)
    return env


def outputs(written: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in written.splitlines())


def test_walk_back_selects_the_newest_edge_that_has_soaked(tmp_path: pathlib.Path) -> None:
    """Edges 1, 4 and 9 days old: the 9-day one is the newest that has soaked, so it is the one selected."""
    (exit_code, out, err), written = run_port(tmp_path, walk_env())
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert got["version"] == "1.0.1"
    assert got["path"] == "soak"
    assert "Soak period complete for v1.0.1" in out


def test_walk_back_does_not_promote_what_r2_does_not_carry(tmp_path: pathlib.Path) -> None:
    """The selected v1.0.1 is not what R2's `<dir>/edge/` trees hold (v1.0.3), and no per-version channel snapshot exists: copying edge/ would ship v1.0.3's packages as "v1.0.1". Not ready, and the reason is named."""
    (exit_code, out, err), written = run_port(tmp_path, walk_env())
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert got["ready"] == "false"
    assert got["blocked"] == "r2-channel-snapshot"
    assert "carry only v1.0.3" in out


def test_walk_back_with_only_young_edges_selects_nothing(tmp_path: pathlib.Path) -> None:
    env = walk_env(EDGE_RELEASES=releases(("1.0.3", 1), ("1.0.2", 4)))
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert (got["ready"], got["path"], got["version"], got["date"]) == ("false", "soak", "", "")
    assert "No edge release newer than stable v1.0.0 has soaked 7 days" in out


def test_walk_back_stops_at_the_current_stable(tmp_path: pathlib.Path) -> None:
    """The 9-day edge IS stable already: re-promoting it, or anything older, is not a promotion."""
    (exit_code, _out, err), written = run_port(tmp_path, walk_env(stable="1.0.1"))
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert (got["ready"], got["version"]) == ("false", "")


def test_walk_back_ignores_a_release_newer_than_the_edge_manifest(tmp_path: pathlib.Path) -> None:
    """A GitHub release R2's edge manifest does not advertise yet is not an edge release."""
    env = walk_env(EDGE_RELEASES=releases(("1.0.9", 30), ("1.0.3", 1)))
    (exit_code, _out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    assert outputs(written)["version"] == ""


def test_newest_edge_that_has_soaked_is_promoted_with_its_own_date(tmp_path: pathlib.Path) -> None:
    env = walk_env(EDGE_DATE=edge_date(8), EDGE_RELEASES=releases(("1.0.3", 8), ("1.0.1", 9)))
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert (got["ready"], got["path"], got["version"]) == ("true", "soak", "1.0.3")
    assert got["date"] == env["EDGE_DATE"]
    assert "blocked" not in got
    assert out.endswith("Soak period complete\n")


def test_force_selects_the_newest_edge(tmp_path: pathlib.Path) -> None:
    (exit_code, _out, err), written = run_port(tmp_path, walk_env(FORCE="true"))
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert (got["ready"], got["path"], got["version"]) == ("true", "force", "1.0.3")


def test_an_unparseable_candidate_list_is_named(tmp_path: pathlib.Path) -> None:
    (exit_code, out, err), written = run_port(tmp_path, walk_env(EDGE_RELEASES="[not json"))
    assert exit_code == 1
    assert "EDGE_RELEASES" in err
    assert (out, written) == ("", "")


def test_nightly_waiver_selects_the_newest_tested_edge(tmp_path: pathlib.Path) -> None:
    """Newest edge v1.0.3 is tagged on C, which the nightly (head B) never saw; v1.0.2 is tagged on A, which it did. The waiver picks v1.0.2, the newest TESTED edge, not the newest edge and not the 9-day soak candidate."""
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.0.3", h["C"])
    _git(repo_dir, "tag", "v1.0.2", h["A"])
    _git(repo_dir, "tag", "v1.0.1", h["A"])
    env = walk_env(PROMOTE_TRIGGER="workflow_run", NIGHTLY_HEAD_SHA=h["B"])
    (exit_code, out, err), written = run_in(repo_dir, tmp_path, env)
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert (got["path"], got["version"]) == ("nightly", "1.0.2")
    assert "edge v1.0.3" in out
    assert "is NOT contained" in out


def test_nightly_waiver_on_the_newest_edge_is_ready(tmp_path: pathlib.Path) -> None:
    repo_dir = tmp_path / "r"
    h = make_history(repo_dir)
    _git(repo_dir, "tag", "v1.0.3", h["B"])
    env = walk_env(PROMOTE_TRIGGER="workflow_run", NIGHTLY_HEAD_SHA=h["B"])
    (exit_code, _out, err), written = run_in(repo_dir, tmp_path, env)
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert (got["ready"], got["path"], got["version"]) == ("true", "nightly", "1.0.3")


# --- list_edge_releases: the candidate list the walk back reads ----------------


def test_list_edge_releases_parses_newest_first_and_drops_non_releases() -> None:
    raw = json.dumps(
        [
            {"tagName": "v1.3.9", "publishedAt": "2026-09-06T04:11:43Z"},
            {"tagName": "v1.4.0", "publishedAt": "2026-09-30T06:07:21Z"},
            {"tagName": "v1.3.12", "publishedAt": "2026-09-07T02:54:33Z"},
            {"tagName": "production", "publishedAt": "2026-09-07T02:54:33Z"},
            {"tagName": "v1.5.0-rc.1", "publishedAt": "2026-10-01T00:00:00Z"},
            {"tagName": "v1.3.11", "publishedAt": ""},
        ]
    )
    assert list_edge_releases.parse_releases(raw) == [
        {"version": "1.4.0", "date": "2026-09-30T06:07:21Z"},
        {"version": "1.3.12", "date": "2026-09-07T02:54:33Z"},
        {"version": "1.3.9", "date": "2026-09-06T04:11:43Z"},
    ]


def test_list_edge_releases_writes_the_output_through_gh(tmp_path: pathlib.Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" > "%s"\n'
        """echo '[{"tagName":"v1.3.12","publishedAt":"2026-09-07T02:54:33Z"}]'\n"""
        % (tmp_path / "argv")
    )
    fake.chmod(0o755)
    out = tmp_path / "output.txt"
    env = diff.env_for(
        GITHUB_OUTPUT=str(out),
        GITHUB_REPOSITORY="o/r",
        PATH="%s:/usr/bin:/bin" % bin_dir,
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    exit_code, stdout, err = diff.bash_streams(
        "python3 -m rediacc_ci.release.list_edge_releases", env=env, timeout=30
    )
    assert (exit_code, err) == (0, "")
    assert "v1.3.12" in stdout
    assert out.read_text() == 'releases=[{"version":"1.3.12","date":"2026-09-07T02:54:33Z"}]\n'
    argv = (tmp_path / "argv").read_text()
    assert "--exclude-drafts --exclude-pre-releases" in argv
    assert "--repo o/r" in argv


def test_list_edge_releases_fails_loudly_when_gh_fails(tmp_path: pathlib.Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text("#!/usr/bin/env bash\necho 'HTTP 503' >&2\nexit 1\n")
    fake.chmod(0o755)
    out = tmp_path / "output.txt"
    env = diff.env_for(
        GITHUB_OUTPUT=str(out),
        PATH="%s:/usr/bin:/bin" % bin_dir,
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    exit_code, _stdout, err = diff.bash_streams(
        "python3 -m rediacc_ci.release.list_edge_releases", env=env, timeout=30
    )
    assert exit_code == 1
    assert "HTTP 503" in err
    assert not out.exists()


# --- Channel snapshots (PLAN-plan-per-pr-loop R2 follow-up, #51ea3682) ------------
#
# Every edge release now writes its signed channel metadata to `snapshots/v<ver>/`, and `promote_r2_to_stable` promotes an older selection from it. `CHANNEL_SNAPSHOTS` (`list_channel_snapshots`' output) names the versions that have one.


def test_an_older_soaked_selection_with_a_channel_snapshot_is_ready(tmp_path: pathlib.Path) -> None:
    env = walk_env(CHANNEL_SNAPSHOTS=json.dumps(["1.0.3", "1.0.1"]))
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert got["ready"] == "true"
    assert got["version"] == "1.0.1"
    assert "blocked" not in got
    assert "Promoting v1.0.1 from its channel snapshot snapshots/v1.0.1/" in out


def test_an_older_selection_without_a_snapshot_is_blocked_and_says_why(
    tmp_path: pathlib.Path,
) -> None:
    """A snapshot of ANOTHER version does not count, and the reason names the missing prefix and why such a release has none."""
    env = walk_env(CHANNEL_SNAPSHOTS=json.dumps(["1.0.3", "1.0.2"]))
    (exit_code, out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert got["ready"] == "false"
    assert got["version"] == "1.0.1"
    assert got["blocked"] == "r2-channel-snapshot"
    assert "no channel snapshot snapshots/v1.0.1/ exists" in out
    assert "releases cut before channel snapshots were introduced have none" in out


def test_the_newest_edge_needs_no_snapshot(tmp_path: pathlib.Path) -> None:
    """The newest edge is what the live `<dir>/edge/` trees carry, so it promotes with or without a snapshot."""
    env = walk_env(EDGE_DATE=edge_date(8), CHANNEL_SNAPSHOTS="[]")
    (exit_code, _out, err), written = run_port(tmp_path, env)
    assert (exit_code, err) == (0, "")
    got = outputs(written)
    assert (got["ready"], got["version"]) == ("true", "1.0.3")
    assert "blocked" not in got


def test_an_unreadable_snapshot_list_is_refused_not_read_as_none(tmp_path: pathlib.Path) -> None:
    env = walk_env(CHANNEL_SNAPSHOTS='{"1.0.1": true}')
    (exit_code, _out, err), written = run_port(tmp_path, env)
    assert exit_code == 1
    assert "CHANNEL_SNAPSHOTS is not a version list" in err
    assert written == ""
