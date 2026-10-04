"""A job that calls a reusable workflow grants every permission the called workflow's jobs request.

GitHub refuses a called workflow that asks for more than its caller job grants, and it refuses it at STARTUP: the run ends `startup_failure` with no job and no log. ci.yml's quality job comment recorded the first time (pull-requests: read), and on 2026-10-04 run 37184675916 was the second: ci-quality.yml's quality-security gained `actions: read` for the CI time budget freshness step while ci.yml's caller still granted only contents and pull-requests. Neither `npm run ci:quick` nor the PR's gates could see it, so it surfaced only as a Console CI run with zero jobs.

This test reads every workflow under .github/workflows, finds each job with `uses: ./.github/workflows/<file>`, and checks that the caller job's permissions (or the calling workflow's top-level permissions when the job sets none) cover every scope and level any job of the called workflow requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci import paths, workflows

if TYPE_CHECKING:
    import pathlib

WORKFLOWS = paths.from_root(".github", "workflows")
LEVEL = {"none": 0, "read": 1, "write": 2}


def _perms(block) -> dict[str, int] | None:
    """A permissions block as {scope: level}; None when absent, the shorthand strings expanded."""
    if block is None:
        return None
    if block == "read-all":
        return {"*": 1}
    if block == "write-all":
        return {"*": 2}
    if isinstance(block, dict):
        return {str(k): LEVEL.get(str(v), 0) for k, v in block.items()}
    return {}


def _grants(have: dict[str, int], scope: str) -> int:
    return max(have.get(scope, 0), have.get("*", 0))


def _load(path: pathlib.Path) -> dict:
    # rediacc_ci.workflows, the repo's one dependency-free workflow parser: PyYAML is absent from the pytest toolchain, and its own header records gates dying on that import.
    doc = workflows.load(path)
    return doc if isinstance(doc, dict) else {}


def shortfalls(workflows_dir: pathlib.Path) -> list[str]:
    """Every (caller job, called file, scope) where the caller grants less than a called job requests."""
    docs = {p.name: _load(p) for p in sorted(workflows_dir.glob("*.y*ml"))}
    out = []
    for name, doc in docs.items():
        top = _perms(doc.get("permissions"))
        for job_id, job in (doc.get("jobs") or {}).items():
            uses = str((job or {}).get("uses") or "")
            if not uses.startswith("./.github/workflows/"):
                continue
            called = docs.get(uses.rsplit("/", 1)[-1])
            if called is None:
                out.append("%s:%s calls %s, which does not exist" % (name, job_id, uses))
                continue
            have = _perms(job.get("permissions"))
            if have is None:
                have = top if top is not None else {"*": 2}
            want: dict[str, int] = {}
            for cjob in (called.get("jobs") or {}).values():
                for scope, level in (_perms((cjob or {}).get("permissions")) or {}).items():
                    want[scope] = max(want.get(scope, 0), level)
            for scope, level in (_perms(called.get("permissions")) or {}).items():
                want[scope] = max(want.get(scope, 0), level)
            for scope, level in sorted(want.items()):
                if scope != "*" and _grants(have, scope) < level:
                    out.append(
                        "%s:%s grants %s=%s but %s requests %s"
                        % (
                            name,
                            job_id,
                            scope,
                            {v: k for k, v in LEVEL.items()}[_grants(have, scope)],
                            uses.rsplit("/", 1)[-1],
                            {v: k for k, v in LEVEL.items()}[level],
                        )
                    )
    return out


def test_every_caller_grants_what_its_called_workflow_requests():
    found = shortfalls(WORKFLOWS)
    assert not found, "a called workflow would fail at startup:\n  " + "\n  ".join(found)


def test_control_a_missing_grant_is_caught(tmp_path):
    (tmp_path / "caller.yml").write_text(
        "on: push\njobs:\n  q:\n    permissions:\n      contents: read\n"
        "    uses: ./.github/workflows/called.yml\n",
        encoding="utf-8",
    )
    (tmp_path / "called.yml").write_text(
        "on: workflow_call\njobs:\n  s:\n    permissions:\n      contents: read\n"
        "      actions: read\n    runs-on: ubuntu-latest\n    steps: []\n",
        encoding="utf-8",
    )
    found = shortfalls(tmp_path)
    assert found == ["caller.yml:q grants actions=none but called.yml requests read"], found
    # The same pair with the grant present is clean.
    (tmp_path / "caller.yml").write_text(
        "on: push\njobs:\n  q:\n    permissions:\n      contents: read\n      actions: read\n"
        "    uses: ./.github/workflows/called.yml\n",
        encoding="utf-8",
    )
    assert shortfalls(tmp_path) == []
