"""Port of `.ci/scripts/release/check-existing-release.sh`.

Version guard: refuses to publish a version whose tag or GitHub Release already exists. Two probes, `git tag -l` (after `git fetch --tags`) and `gh release view`; either hit is a hard failure, checked in that order.

BOTH EXTERNAL CALLS ARE SHELLED OUT TO THE REAL BINARIES, not reimplemented. `git fetch`/`git tag -l` run against whatever `origin` the process's cwd has configured -- exactly the twin's own two commands, same arguments -- so the differential test points `origin` at a disposable local bare repo rather than GitHub, the same "real git, fake remote" shape
`rediacc_ci.release.resolve_backfill_commit`'s module docstring argues for plain `git` calls. `gh release view` is the one call that needs GitHub's own API, so THAT binary is the one the differential fakes on PATH -- never `git` itself, which stays real throughout.

REWORDED, NOT BYTE-IDENTICAL, on the missing-env-var paths only; every other message here is copied byte-for-byte from the twin's own `echo` lines, which were already deliberately written (not a bash diagnostic wrapper).
"""

from __future__ import annotations

import os
import subprocess
import sys

SELF = "check-existing-release.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    version = _require("VERSION")
    github_repository = _require("GITHUB_REPOSITORY")

    subprocess.run(["git", "fetch", "--tags", "--quiet"], check=True)

    tag = f"v{version}"
    tags = subprocess.run(
        ["git", "tag", "-l", tag], capture_output=True, text=True, check=True
    ).stdout
    if tags.strip():
        print(f"::error::Git tag {tag} already exists. Aborting to prevent duplicate publish.")
        return 1

    view = subprocess.run(
        ["gh", "release", "view", tag, "--repo", github_repository],
        capture_output=True,
        text=True,
        check=False,
    )
    if view.returncode == 0:
        print(f"::error::Release {tag} already exists. Aborting to prevent duplicate publish.")
        return 1

    print(f"Version {tag} is available for publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
