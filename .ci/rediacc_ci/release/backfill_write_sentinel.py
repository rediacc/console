"""Ported from `.ci/scripts/release/backfill-write-sentinel.sh`, which W7 P5 batch B5 retired once `.ci/shadow/w7p5a-backfill-write-sentinel.observations.jsonl` asserted equivalence over five distinct trees.

The only R2-mutating step of the backfill workflow, wrapped in a DRY_RUN
preview so it stays trivially safe to re-run. `dry_run=true` prints the exact
writer invocation and touches nothing; only an explicit `DRY_RUN=false`
(already gated on a typed confirmation input upstream) reaches `.ci/scripts/deploy/write-release-sentinel.sh`, which is `blocked` in `.ci/shadow/w7p5a-status.json` (it needs `aws` and live R2 credentials) and therefore stays bash forever.

FORWARDS TO THE BLOCKED SCRIPT RATHER THAN REIMPLEMENTING IT, same reasoning as `rediacc_ci.deploy.upload_media_to_r2`'s forwarding shim: the writer is a whole separate contract (payload shape, idempotent readback, `aws`/`jq` requirements) that already has one implementation, and re-deriving it here would be a second one to keep in sync. Unlike that sibling this is not a bare
`os.execv`: the twin prints its own "→ writing sentinel(s) ..." line BEFORE invoking the writer (it is the last statement in the script, not an `exec`), so this port does the same -- a normal `subprocess.run` with inherited stdout/stderr, exiting with the writer's own return code.

`printf '%q'` IS REPRODUCED WITH `shlex.quote`, not with a hand-rolled quoter. For every value these three flags carry (a stripped semver, `edge`/`stable`, a git SHA) both quoting schemes leave the string bare -- verified directly
with `bash -c 'printf "%q" "1.1.2"'` et al. against `shlex.quote` for the same
inputs. Reaching for a fancier reproduction of `%q`'s full escaping grammar (control characters, embedded quotes) would be solving a problem neither side of this differential can actually hit: VERSION/CHANNEL/COMMIT_SHA are not free-form operator text, they are the workflow's own semver/channel/sha inputs.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

SELF = "backfill-write-sentinel.py"

# `.ci/rediacc_ci/release/backfill_write_sentinel.py` -> `.ci` -> repo root, exactly as the twin's `SCRIPT_DIR/../../..` (`.ci/scripts/release/../../..`) is the same three levels up, even though the two files live in different directories.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
# The RELATIVE spelling the retired twin printed and invoked, once it had `cd`'d to the repo root. The dry-run preview line must show this exact relative path, not the absolute one this port resolves `_WRITER` to for the actual (non-dry-run) subprocess call.
_WRITER_REL = os.path.join(".ci", "scripts", "deploy", "write-release-sentinel.sh")
_WRITER = os.path.join(_ROOT, _WRITER_REL)


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
    proc = subprocess.run([_WRITER, *args], cwd=_ROOT, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
