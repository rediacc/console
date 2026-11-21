#!/usr/bin/env python3
"""Resolves the `preset` input of the app-token action to `perm-*=<level>` step outputs.

Usage (from action.yml, env PRESET set): python3 "$APP_TOKEN_PERMS"
Environment: PRESET (the preset name, any case, surrounding space ignored), GITHUB_OUTPUT.

It sits beside the action because several callers sparse-check-out only `.github/actions` before minting, so nothing under `.ci/` is guaranteed to exist yet. Standard library only.

An unknown preset prints `::error::Unknown preset: <name>` and exits 1.

The old `ci` and `push` presets were deleted, not merely unused, and for the same reason: both handed contents:write to PR-triggered jobs, and this App bypasses the main-branch ruleset. `push` existed solely so ci-quality.yml's `quality-branch` could rebase and republish the PR branch; that job now only REPORTS that a rebase is needed (.ci/scripts/quality/check_branch.py) and runs on the default contents:read token. `preset: ci` and `preset: push` now fail loudly here rather than silently over-scoping.

`cd` carries workflows:write, added 2026-09-06, ONLY on cd and only after the App installation was granted it. Without it the 'Tag & GitHub Release' step's `git push origin v<X>` is rejected outright ("refusing to allow a GitHub App to create or update workflow <file> without workflows permission") whenever the tagged commit range touches .github/workflows. The release then half-completes: edge deploys and the R2 artifacts publish, but no git tag and no GitHub Release exist. Seen twice, runs 34019022671 (v1.3.11) and 34003183456 (v1.3.8); v1.3.11 went untagged for a day because of it.
ORDER MATTERS AND IS NOT REVERSIBLE HERE: create-github-app-token FAILS the mint when asked for a permission the installation does not hold, so this entry breaks every CD run if the grant is ever withdrawn. It is deliberately not on `housekeeping`, which never pushes a tag.
"""

import os
import sys

PRESETS = {
    "readonly": [("contents", "read")],
    "pr-read": [("contents", "read"), ("pull-requests", "read")],
    "cd": [
        ("contents", "write"),
        ("pull-requests", "write"),
        ("actions", "write"),
        ("workflows", "write"),
    ],
    "housekeeping": [
        ("contents", "write"),
        ("packages", "write"),
        ("actions", "write"),
        ("deployments", "write"),
    ],
}


def resolve(preset: str) -> list[str] | None:
    """The `perm-<scope>=<level>` lines for a preset, or None when it is unknown."""
    grants = PRESETS.get(" ".join(preset.lower().split()))
    if grants is None:
        return None
    return ["perm-%s=%s" % grant for grant in grants]


def main() -> int:
    preset = os.environ.get("PRESET", "")
    lines = resolve(preset)
    if lines is None:
        print("::error::Unknown preset: %s" % " ".join(preset.lower().split()))
        return 1
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("".join(line + "\n" for line in lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
