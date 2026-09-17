"""Port of `.ci/scripts/release/resolve-backfill-commit.sh`.

Resolves (and sanity-checks) the commit SHA a backfilled release sentinel records: either the operator-supplied `INPUT_SHA`, or the commit a version tag points at, then verifies that commit is reachable from `origin/main`.

GIT IS SHELLED OUT TO, NOT REIMPLEMENTED. `git rev-list`, `git cat-file` and `git merge-base --is-ancestor` are exactly the twin's own three probes, run
with the SAME arguments against whatever git repository the process's cwd
belongs to (this port never `cd`s, matching the twin, which also never does). Reimplementing tag resolution or ancestry testing in Python would be a
second, independent opinion about the repository's object graph; shelling out
to the one git binary both sides already trust is what keeps the two implementations looking at the same answer.

MESSAGE TEXT IS BYTE-IDENTICAL ON PURPOSE, unlike the `${VAR:?msg}` twins in
this box. Every message a human or a workflow log actually reads here is an explicit `echo`/`::error::` line the twin author already chose carefully (see the twin's own long comment on the two-different-failures distinction for `INPUT_SHA`) rather than a bash diagnostic wrapper, so there is nothing to reword: this port reproduces them exactly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

SELF = "resolve-backfill-commit.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def main(argv: list[str]) -> int:
    del argv
    if shutil.which("git") is None:
        print("✗ Required command 'git' is not available", file=sys.stderr)
        return 1

    version = _require("VERSION")
    output_path = _require("GITHUB_OUTPUT")
    input_sha = os.environ.get("INPUT_SHA", "")

    if input_sha:
        sha = input_sha
        print(f"→ using operator-supplied commit_sha: {sha}")
    else:
        resolved = _git("rev-list", "-n1", version)
        sha = resolved.stdout.strip() if resolved.returncode == 0 else ""
        if not sha:
            print(f"::error::tag {version} not found in this checkout; pass commit_sha explicitly")
            return 1
        print(f"→ resolved {version} → {sha}")

    if input_sha and _git("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        print(
            f"::error::commit {sha} does not name a commit in this repository -- "
            "either no such object exists here at all, or the object is not a commit"
        )
        print(
            f"::error::if you took this SHA from an old release note or an R2 sentinel, "
            "it no longer exists: the 2026-08-23 git history rewrite renamed every commit. "
            f"Leave commit_sha/INPUT_SHA EMPTY and let {version} resolve through the tag "
            "instead -- the rewrite moved tags with the commits, so the tag path still works."
        )
        return 1

    if _git("merge-base", "--is-ancestor", sha, "origin/main").returncode != 0:
        print(f"::error::commit {sha} is not reachable from origin/main")
        print("::error::refusing to backfill a sentinel for a detached tag")
        return 1

    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"commit_sha={sha}\n")
    print("✓ commit reachable from origin/main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
