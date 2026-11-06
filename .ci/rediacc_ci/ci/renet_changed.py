#!/usr/bin/env python3
"""Decide whether the `private/renet` gitlink moved in this push or pull request (PLAN-backup-program J9).

The answer feeds `renet_changed`, which runs the renet go (BTRFS tier) and integration jobs without `full_suite`. A push compares `$BEFORE_SHA` with HEAD. A pull request compares the merge base of `$BASE_SHA` and HEAD with HEAD. Any other event answers false.

Fail open: a branch-creating push, a missing or unreachable base, or a git failure answers true, so every renet leg runs rather than none. A gitlink diff needs only the two commits, no submodule checkout.

Writes `changed=<true|false>` to `$GITHUB_OUTPUT` when set, and prints it.
"""

from __future__ import annotations

import os
import subprocess
import sys

PATHSPEC = "private/renet"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """One git call; a git that cannot be run answers rc 127, so every caller's fail-open rule still holds."""
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except OSError as exc:
        return subprocess.CompletedProcess(["git", *args], 127, "", str(exc))


def _has_commit(sha: str) -> bool:
    if _git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0:
        return True
    return _git("fetch", "--no-tags", "--filter=blob:none", "origin", sha).returncode == 0


def _moved(base: str) -> bool:
    """True when the gitlink differs between `base` and HEAD, and on anything git cannot decide."""
    if not _has_commit(base):
        print(f"::warning::base '{base}' unavailable, so every renet leg runs")
        return True
    rc = _git("diff", "--quiet", base, "HEAD", "--", PATHSPEC).returncode
    return rc != 0


def decide(event: str, before_sha: str, base_sha: str) -> bool:
    if event == "push":
        if before_sha.strip("0") == "":
            print("a push that creates the branch has no base, so every renet leg runs")
            return True
        return _moved(before_sha)
    if event == "pull_request":
        if not base_sha:
            print("::warning::pull request without a base sha, so every renet leg runs")
            return True
        if not _has_commit(base_sha):
            print(f"::warning::base '{base_sha}' unavailable, so every renet leg runs")
            return True
        mb = _git("merge-base", base_sha, "HEAD")
        if mb.returncode != 0 or not mb.stdout.strip():
            # Comparing against the base tip instead would call a PR renet-changed whenever main moved the gitlink after the branch point.
            print("::warning::no merge base with '%s', so every renet leg runs" % base_sha)
            return True
        return _moved(mb.stdout.strip())
    return False


def main() -> int:
    changed = decide(
        os.environ.get("EVENT_NAME", ""),
        os.environ.get("BEFORE_SHA", ""),
        os.environ.get("BASE_SHA", ""),
    )
    print(
        f"private/renet changed in this {os.environ.get('EVENT_NAME', 'event')}: {str(changed).lower()}"
    )
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"changed={str(changed).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
