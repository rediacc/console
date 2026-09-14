"""Port of `.ci/scripts/release/decide-release-mode.sh`.

Decides which of three mutually exclusive release modes `cd-v2.yml` runs in
(`workers_only`, `retry`, `patch`) and emits the step outputs the rest of that
workflow gates on. Pure computation, same shape as
`rediacc_ci.deploy.resolve_account_deploy_config`: no network, no subprocess,
one file write to `$GITHUB_OUTPUT` plus `::notice::` lines to stdout.

REWORDED, NOT BYTE-IDENTICAL, same reasoning as the deploy sibling: the bash
twin's `${VAR:?msg}` diagnostic carries a bash line number that is not worth
reproducing. The ledger's `--finding-re` extracts the substance
(`retry_mode=`/`workers_only=` outputs, or the missing-variable name) rather
than the exact wrapper text.
"""

from __future__ import annotations

import os
import sys

SELF = "decide-release-mode.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    output_path = _require("GITHUB_OUTPUT")
    deploy_workers_only = _require("DEPLOY_WORKERS_ONLY")
    release_mode = os.environ.get("RELEASE_MODE", "")

    with open(output_path, "a", encoding="utf-8") as fh:
        if deploy_workers_only == "true":
            fh.write("retry_mode=false\n")
            fh.write("workers_only=true\n")
            print("::notice::Workers-only mode -- deploy Workers without version bump or publish")
            return 0

        fh.write("workers_only=false\n")
        if release_mode == "retry":
            fh.write("retry_mode=true\n")
            print("::notice::Retry mode -- will re-deploy current version without bumping")
        else:
            fh.write("retry_mode=false\n")
            print(f"::notice::Release mode: {release_mode} bump -- will create new release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
