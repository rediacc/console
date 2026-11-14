#!/usr/bin/env python3
"""Decide whether this push or pull request moved a backup path (PLAN-backup-program J6).

The answer feeds `backup_changed`, which runs ct-tests.yml's `test-e2e-backup-browse-at` job (suite 26, the account gateway and the VM fleet) without `full_suite`. The path set is the `backup` area of `.ci/config/proof-tiers.json` (`tiers.vm.areas.backup`), read through `rediacc_ci.proof.surfaces` rather than listed a second time: its globs select the renet backup paths, and its `suites` are the backup suite files, which sit in the console tree.

A push compares `$BEFORE_SHA` with HEAD. A pull request compares the merge base of `$BASE_SHA` and HEAD with HEAD. Any other event answers false.

Fail open, like renet_changed: a branch-creating push, a missing or unreachable base, a git failure, or a submodule range that cannot be diffed (the initialize job checks no submodule out, so any `private/renet` pointer move lands here) answers true, so the backup leg runs rather than none.

Writes `changed=<true|false>` to `$GITHUB_OUTPUT` when set, and prints it.
"""

from __future__ import annotations

import os
import pathlib
import sys

from rediacc_ci.ci.renet_changed import _git, _has_commit
from rediacc_ci.proof import surfaces

AREA = "backup"


def _suites() -> tuple[str, ...]:
    """The backup area's suite files; an area gone from the map is an error, never an empty set that answers false for ever."""
    area = surfaces.MAP.areas.get(AREA)
    if area is None or not area.suites:
        raise SystemExit(
            f"::error::tiers.vm.areas.{AREA} is missing or lists no suites in .ci/config/proof-tiers.json; "
            "the backup_changed gate would see nothing"
        )
    return area.suites


def _moved(base: str) -> bool:
    """True when a backup path differs between `base` and HEAD, and on anything git cannot decide."""
    if not _has_commit(base):
        print(f"::warning::base '{base}' unavailable, so the backup leg runs")
        return True
    suites = _suites()
    diff = _git("diff", "--name-only", base, "HEAD", "--", *suites)
    if diff.returncode != 0:
        print("::warning::git diff of the backup suites failed, so the backup leg runs")
        return True
    if diff.stdout.strip():
        return True
    changed = surfaces.changed_paths(pathlib.Path.cwd(), base, "push")
    if changed.unknown:
        print(f"::warning::{'; '.join(changed.unknown)}, so the backup leg runs")
        return True
    return AREA in changed.areas


def decide(event: str, before_sha: str, base_sha: str) -> bool:
    if event == "push":
        if before_sha.strip("0") == "":
            print("a push that creates the branch has no base, so the backup leg runs")
            return True
        return _moved(before_sha)
    if event == "pull_request":
        if not base_sha:
            print("::warning::pull request without a base sha, so the backup leg runs")
            return True
        if not _has_commit(base_sha):
            print(f"::warning::base '{base_sha}' unavailable, so the backup leg runs")
            return True
        mb = _git("merge-base", base_sha, "HEAD")
        if mb.returncode != 0 or not mb.stdout.strip():
            print(f"::warning::no merge base with '{base_sha}', so the backup leg runs")
            return True
        return _moved(mb.stdout.strip())
    return False


def main() -> int:
    event = os.environ.get("EVENT_NAME", "")
    changed = decide(event, os.environ.get("BEFORE_SHA", ""), os.environ.get("BASE_SHA", ""))
    print(f"a backup path changed in this {event or 'event'}: {str(changed).lower()}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"changed={str(changed).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
