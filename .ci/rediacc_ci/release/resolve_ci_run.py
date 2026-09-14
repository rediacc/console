"""Port of `.ci/scripts/release/resolve-ci-run.sh`.

Resolves (or validates) the CI run a release publishes from: auto-derives the
latest green Console CI run on `main` when no `ci_run_id` was given, or
validates an explicitly-dispatched one for branch/workflow/status.

`gh api` AND `jq` ARE BOTH SHELLED OUT TO, not reimplemented against the REST
API directly, for the same reason as every other `gh`-based port in this box:
the twin's exact invocations (including `gh api --jq` filters and the
`|| echo '{}'` fallback shape) are what the differential proves parity
against.

THE `run_json` FALLBACK IS REPRODUCED EXACTLY. `gh api .../runs/$ID
2>/dev/null || echo '{}'` means a failed lookup (bad id, rate limit, network)
degrades to an EMPTY OBJECT rather than aborting -- every subsequent
`jq -r '.field // ""'` then reads as an empty string, which the twin's own
branch/workflow checks treat as a validation FAILURE (not a crash). This port
matches that: a failed `gh api` call is caught and treated as `{}`, never
raised.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SELF = "resolve-ci-run.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def _gh_api(url: str, *, jq_filter: str | None = None) -> subprocess.CompletedProcess[str]:
    args = ["gh", "api", url]
    if jq_filter is not None:
        args += ["--jq", jq_filter]
    return subprocess.run(args, capture_output=True, text=True, check=False)


def main(argv: list[str]) -> int:
    del argv
    github_repository = _require("GITHUB_REPOSITORY")
    output_path = _require("GITHUB_OUTPUT")

    input_ci_run_id = os.environ.get("INPUT_CI_RUN_ID", "")
    allow_stale = os.environ.get("ALLOW_STALE", "")

    if not input_ci_run_id:
        listing = _gh_api(
            f"repos/{github_repository}/actions/workflows/ci.yml/runs?branch=main&status=success&per_page=1",
            jq_filter=".workflow_runs[0].id // empty",
        )
        latest_id = listing.stdout.strip() if listing.returncode == 0 else ""
        if not latest_id:
            print(
                "::error::No green Console CI run found on main. Cannot auto-derive "
                "ci_run_id; dispatch will not proceed."
            )
            return 1
        ci_run_id = latest_id
        print(f"::notice::Auto-derived ci_run_id={ci_run_id} (latest green Console CI on main).")
    else:
        ci_run_id = input_ci_run_id
        lookup = _gh_api(f"repos/{github_repository}/actions/runs/{ci_run_id}")
        if lookup.returncode != 0:
            run_json: dict[str, object] = {}
        else:
            try:
                run_json = json.loads(lookup.stdout)
            except json.JSONDecodeError:
                # `jq -r` on non-JSON input exits 5; under `set -euo pipefail`
                # that aborts the twin silently, before any output. Same
                # silence here, same reasoning as check_edge_manifest.py.
                return 1
        run_branch = run_json.get("head_branch") or ""
        run_conclusion = run_json.get("conclusion") or ""
        run_status = run_json.get("status") or ""
        run_workflow = run_json.get("name") or ""

        failed = False
        if run_branch != "main":
            print(f"::error::ci_run_id {ci_run_id} is on branch '{run_branch}', not 'main'.")
            failed = True
        if run_workflow != "Console CI":
            print(f"::error::ci_run_id {ci_run_id} is workflow '{run_workflow}', not 'Console CI'.")
            failed = True
        if run_status == "completed" and run_conclusion != "success":
            if allow_stale == "true":
                print(
                    f"::warning::ci_run_id {ci_run_id} completed with conclusion "
                    f"'{run_conclusion}'; allow_stale_ci_run_id is set, proceeding anyway."
                )
            else:
                print(
                    f"::error::ci_run_id {ci_run_id} completed with conclusion "
                    f"'{run_conclusion}', not 'success'."
                )
                failed = True
        if failed:
            print(
                "::error::ci_run_id validation failed -- refusing to dispatch with invalid CI run."
            )
            return 1

    sha_lookup = _gh_api(
        f"repos/{github_repository}/actions/runs/{ci_run_id}", jq_filter=".head_sha"
    )
    ci_sha = (
        sha_lookup.stdout.strip()
        if sha_lookup.returncode == 0
        else os.environ.get("GITHUB_SHA", "")
    )

    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"ci_run_id={ci_run_id}\n")
        fh.write(f"ci_sha={ci_sha}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
