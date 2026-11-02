"""The admit gate of `.github/workflows/local-release-assist.yml`: only a commit in the default branch's history may be built next to the release secrets."""

from __future__ import annotations

import subprocess
import typing

from rediacc_ci import paths, workflows

if typing.TYPE_CHECKING:
    import pathlib

WORKFLOW = paths.repo_root() / ".github" / "workflows" / "local-release-assist.yml"
ANCESTRY_MARK = "git merge-base --is-ancestor"


def _jobs() -> dict:
    return workflows.load(WORKFLOW)["jobs"]


def _needs(jobs: dict, name: str) -> set[str]:
    need = jobs[name].get("needs", [])
    direct = {need} if isinstance(need, str) else set(need)
    out = set(direct)
    for d in direct:
        out |= _needs(jobs, d)
    return out


def _ancestry_command() -> str:
    steps = _jobs()["admit"]["steps"]
    (run,) = [s["run"] for s in steps if ANCESTRY_MARK in s.get("run", "")]
    return run


def test_every_other_job_waits_on_admit_and_every_job_pins_the_default_branch() -> None:
    jobs = _jobs()
    assert "admit" in jobs
    for name, job in jobs.items():
        assert "default_branch" in job["if"], name
        if name != "admit":
            assert "admit" in _needs(jobs, name), "%s can start without the admit gate" % name


def test_the_admit_step_refuses_on_any_nonzero_ancestry_result() -> None:
    run = _ancestry_command()
    assert '%s "$SHA" HEAD ||' % ANCESTRY_MARK in run
    assert "exit 1" in run


def _git(repo: pathlib.Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _admit(repo: pathlib.Path, sha: str) -> int:
    env = {
        "SHA": sha,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "tip",
        "PATH": "/usr/bin:/bin",
    }
    return subprocess.run(
        ["bash", "-c", "cd %s && %s" % (repo, _ancestry_command())],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    ).returncode


def test_the_admit_command_admits_history_and_refuses_a_side_branch_and_an_unknown_sha(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "one")
    first = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "side")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "side")
    side = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "two")
    tip = _git(repo, "rev-parse", "HEAD")
    assert _admit(repo, first) == 0
    assert _admit(repo, tip) == 0
    assert _admit(repo, side) != 0
    assert _admit(repo, "0" * 40) != 0
