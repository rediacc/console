"""Every workflow job that starts the per-run account server installs private/account's dependency trees.

Run 41348962671: E2E Workers called `setup-workspace` without `account: 'true'`, so private/account/node_modules was never installed and `start_account` died on `Cannot find package 'better-sqlite3'` in all 43 legs.

The scan reads inline `run:` text in each workflow's own jobs. A job reaching the server through a composite action or a reusable `uses:` job is outside it; the callee workflow's own jobs are scanned here.
"""

import pathlib

import pytest
import yaml

WORKFLOWS = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows"
NEEDLES = ("rediacc_ci.testrun.start_account", "rediacc_ci.testrun.start_backup_plane")


def _jobs() -> list[tuple[str, str, dict]]:
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text())
        for name, job in (data.get("jobs") or {}).items():
            if isinstance(job, dict) and job.get("steps"):
                found.append((path.name, name, job))
    return found


def _needs_account_tree(job: dict) -> bool:
    return any(n in str(step.get("run", "")) for step in job["steps"] for n in NEEDLES)


def _installs_account_tree(job: dict) -> bool:
    """The install must come before the first step that starts a server."""
    for step in job["steps"]:
        if any(n in str(step.get("run", "")) for n in NEEDLES):
            return False
        if (
            "setup-workspace" in str(step.get("uses", ""))
            and str((step.get("with") or {}).get("account")).lower() == "true"
        ):
            return True
    return False


def test_the_scan_sees_account_server_jobs() -> None:
    assert sum(_needs_account_tree(job) for _, _, job in _jobs()) >= 10


@pytest.mark.parametrize(
    ("file", "name", "job"),
    [j for j in _jobs() if _needs_account_tree(j[2])],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_a_job_that_starts_the_account_server_installs_its_tree(
    file: str, name: str, job: dict
) -> None:
    assert _installs_account_tree(job), f"{file} {name}: setup-workspace needs `account: 'true'`"


def test_an_install_after_the_start_does_not_count() -> None:
    start = {"run": "python3 -m rediacc_ci.testrun.start_account"}
    install = {"uses": "./.github/actions/setup-workspace", "with": {"account": True}}
    assert _installs_account_tree({"steps": [install, start]})
    assert not _installs_account_tree({"steps": [start, install]})
