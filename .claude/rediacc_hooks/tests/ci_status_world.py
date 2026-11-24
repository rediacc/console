"""The CI-status fixtures that need no pytest: the payloads the gh shim serves, `write_exec`, `ci_rollup` and `ci_job`.

test_wl_ci_status.py re-exports these names (its importers keep working), and the bare-python3 suites (.claude/hooks/stop/test-wl_worktrees.py) import them from here, because importing test_wl_ci_status itself reaches pytest.
"""

from __future__ import annotations

# The Actions job the shim serves for every per-job lookup: one green step and one red one, so the block can name a failing step.
CI_JOB_PAYLOAD = {
    "run_id": 30514648812,
    "run_attempt": 1,
    "steps": [
        {"name": "Set up job", "conclusion": "success"},
        {"name": "Shell format", "conclusion": "failure"},
    ],
}

# The freshness check shares the `gh api graphql` path, so the shim must answer BOTH queries; a body edited in 2999 keeps that check quiet.
CI_FRESH_PAYLOAD = {
    "data": {
        "repository": {
            "pullRequests": {
                "nodes": [
                    {
                        "number": 543,
                        "lastEditedAt": "2999-01-01T00:00:00Z",
                        "updatedAt": "2999-01-01T00:00:00Z",
                    }
                ]
            }
        }
    }
}


def write_exec(path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def ci_rollup(fix, state: str, contexts: str) -> None:
    """The statusCheckRollup the shim serves, plus the cache drop the swap needs.

    The read is cached on the published tip SHA, so a fixture swap inside one case must drop the cache or it reads the previous shape.
    """
    payload = (
        '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,"url":"u",'
        '"commits":{"nodes":[{"commit":{"oid":"deadsha0000","statusCheckRollup":'
        '{"state":"%s","contexts":{"totalCount":9,"pageInfo":{"hasNextPage":false,'
        '"endCursor":null},"nodes":%s}}}}]}}]}}}}\n' % (state, contexts)
    )
    (fix.base / "ci-rollup.json").write_text(payload, encoding="utf-8")
    fix.stem(".cistate-deadbeef").unlink(missing_ok=True)


def ci_job(name: str, conclusion: str, ident: int = 90784763855) -> str:
    """A completed Actions check run."""
    return (
        '{"__typename":"CheckRun","name":"%s","status":"COMPLETED","conclusion":"%s",'
        '"databaseId":%s,"detailsUrl":"https://x/job/%s",'
        '"checkSuite":{"workflowRun":{"databaseId":30514648812}}}'
        % (name, conclusion, ident, ident)
    )
