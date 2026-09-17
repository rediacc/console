"""Port of `.ci/scripts/release/deployment-summary.sh`.

Appends the release job's closing summary to `$GITHUB_STEP_SUMMARY`. Pure string emission: no network, no subprocess, one file append. Same shape as `rediacc_ci.deploy.resolve_account_deploy_config`, except this twin has nothing to decide between, so this port has no branch either -- the whole comparison surface is "did every line come out identical".

REWORDED, NOT BYTE-IDENTICAL, on the missing-env-var path only, same
reasoning as every other twin in this box: the bash `${VAR:?msg}` diagnostic
carries a bash line number this port does not reproduce. The written summary text (the actual point of the script) is byte-for-byte identical on both sides; only the refusal wording differs.
"""

from __future__ import annotations

import os
import sys

SELF = "deployment-summary.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    version = _require("VERSION")
    ci_run_id = _require("CI_RUN_ID")
    ci_sha = _require("CI_SHA")
    summary_path = _require("GITHUB_STEP_SUMMARY")

    lines = [
        "",
        "---",
        "",
        "## Deployment Complete",
        "",
        f"**Version:** v{version}",
        f"**CI Run:** {ci_run_id} (sha: {ci_sha})",
        "**Pages URL:** https://www.rediacc.com",
        "",
        "**Docker images:**",
        f"- ghcr.io/rediacc/renet:{version} + :latest",
        f"- ghcr.io/rediacc/rdc:{version} + :latest",
        f"- ghcr.io/rediacc/server:{version} + :latest (on-prem)",
    ]
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.writelines(line + "\n" for line in lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
