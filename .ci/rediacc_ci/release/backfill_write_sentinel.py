"""Ported from `.ci/scripts/release/backfill-write-sentinel.sh`, which W7 P5 batch B5 retired once `.ci/shadow/w7p5a-backfill-write-sentinel.observations.jsonl` asserted equivalence over five distinct trees.

The only R2-mutating step of the backfill workflow, wrapped in a DRY_RUN preview so it stays trivially safe to re-run. `dry_run=true` prints the exact writer invocation and touches nothing; only an explicit `DRY_RUN=false` (already gated on a typed confirmation input upstream) reaches the writer, `rediacc_ci.deploy.write_release_sentinel`, which needs `aws` and live R2 credentials.

THE WRITER IS CALLED IN PROCESS. It used to be the bash script `.ci/scripts/deploy/write-release-sentinel.sh`, forwarded to by a subprocess; that script was frozen to goldens and deleted under operator ruling D5 (PLAN-retire-bash-oracles, unit W7), and its Python port had been the CD's writer already. THE DRY-RUN PREVIEW NAMES WHAT NOW RUNS (a Rule-T delta: the preview used to print the deleted script's path), and `test_release_backfill_write_sentinel.py` pins the new spelling.

The twin printed its own "-> writing sentinel(s) ..." line BEFORE invoking the writer (it was the last statement in the script, not an `exec`), so this port does the same and returns the writer's status.

`printf '%q'` IS REPRODUCED WITH `shlex.quote`, not with a hand-rolled quoter. For every value these three flags carry (a stripped semver, `edge`/`stable`, a git SHA) both quoting schemes leave the string bare, verified directly with `bash -c 'printf "%q" "1.1.2"'` et al. against `shlex.quote` for the same inputs. VERSION/CHANNEL/COMMIT_SHA are not free-form operator text, they are workflow inputs the upstream guards have already pattern-checked.
"""

from __future__ import annotations

import os
import shlex
import sys

from rediacc_ci.deploy import write_release_sentinel

SELF = "backfill-write-sentinel.py"

# `.ci/rediacc_ci/release/backfill_write_sentinel.py` -> `.ci` -> repo root, exactly as the twin's `SCRIPT_DIR/../../..` (`.ci/scripts/release/../../..`) is the same three levels up, even though the two files live in different directories.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
# What the dry-run preview prints as the invocation: the command a person would type to run the same writer by hand.
_WRITER_REL = "PYTHONPATH=.ci python3 -m rediacc_ci.deploy.write_release_sentinel"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    version = _require("VERSION")
    channel = _require("CHANNEL")
    commit_sha = _require("COMMIT_SHA")
    dry_run = _require("DRY_RUN")

    numeric_version = version.removeprefix("v")
    args = ["--version", numeric_version, "--channel", channel, "--commit-sha", commit_sha]

    if dry_run == "true":
        quoted = " ".join(shlex.quote(a) for a in args)
        print("→ DRY RUN -- would invoke:")
        print(f"   {_WRITER_REL} {quoted}")
        print("→ no R2 mutation performed")
        return 0

    print(f"→ writing sentinel(s) for {version} on channel {channel} (commit {commit_sha})")
    sys.stdout.flush()
    # The writer runs in process and resolves paths from the checkout root; the previous directory is restored so the cwd change does not outlive the call (review finding 67a505d6.2). An exception from the writer still ends the process with a traceback and status 1, which the workflow step reports as a failure.
    previous = os.getcwd()
    os.chdir(_ROOT)
    try:
        return write_release_sentinel.main(args)
    finally:
        os.chdir(previous)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
