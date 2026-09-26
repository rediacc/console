"""Port of `.ci/scripts/version/resolve-version.sh`.

Resolves the current published version from git tags (`git tag -l 'v*'`, newest first by version sort) and, given `--bump-type`, the next patch/minor/major version after it. This is the single place that decides what version number an artifact ships with; `inject-env.sh` calls it as a subprocess (never sources it), and this port preserves that shape: it is a plain stdout-producing
CLI, not a library a caller sources into its own shell.

GIT IS SHELLED OUT TO, NOT REIMPLEMENTED, on the `resolve_backfill_commit.py` precedent: `git tag -l` is the twin's own probe, run with the same arguments against whatever repository the process's cwd belongs to. This port never `cd`s, matching the twin.

MESSAGE TEXT IS BYTE-IDENTICAL ON PURPOSE, including the twin's own name in its own error strings (`resolve-version.sh: ...` never appears -- the twin's messages carry no such prefix at all, see below) so a caller comparing stdout or stderr sees no difference from a port.

THE ONE PIECE OF BASH SEMANTICS WORTH CALLING OUT: `IFS='.' read -r MAJOR
MINOR PATCH <<<"$VERSION_CORE"` does not discard a fourth dotted component,
it folds it into PATCH re-joined with '.' (`1.2.3.4` -> PATCH="3.4"). A
missing component reads as empty, which `${X:-0}` then defaults to "0".
`_split_version_core` reproduces exactly that, not a 3-way `str.split` that would silently drop the tail.
"""

from __future__ import annotations

import subprocess
import sys

USAGE = "Usage: resolve-version.sh [--current | --bump-type patch|minor|major]"


def _split_version_core(core: str) -> tuple[str, str, str]:
    """Mirror `IFS='.' read -r MAJOR MINOR PATCH <<<"$core"` exactly.

    The first two dot-separated fields go to MAJOR/MINOR; every remaining field (zero or more) is rejoined with '.' into PATCH, matching bash's "extra fields land in the last variable" rule. A field that does not exist reads as "", exactly as an unset bash variable would.
    """
    parts = core.split(".")
    major = parts[0] if len(parts) >= 1 else ""
    minor = parts[1] if len(parts) >= 2 else ""
    patch = ".".join(parts[2:]) if len(parts) >= 3 else ""
    return major, minor, patch


def _latest_tag() -> str:
    """`git tag -l 'v*' --sort=-v:refname | head -1`, tolerating no repo/tags.

    The twin wraps the whole pipeline in `|| true` so a failing `git tag` (e.g. not a git repository) falls through to the "no tags found" branch rather than propagating a different error; a failed subprocess here does the same by returning "".
    """
    try:
        completed = subprocess.run(
            ["git", "tag", "-l", "v*", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if completed.returncode != 0:
        return ""
    lines = completed.stdout.splitlines()
    return lines[0] if lines else ""


def main(argv: list[str]) -> int:
    bump_type: str | None = None
    current_only = False

    i = 0
    while i < len(argv):
        arg = argv[i]  # not a secret: one word of `sys.argv`, misread by ruff's S105 heuristic
        if arg == "--current":
            current_only = True
            i += 1
        elif arg == "--bump-type":
            bump_type = argv[i + 1] if i + 1 < len(argv) else ""
            if not bump_type:
                print("Error: --bump-type requires a value", file=sys.stderr)
                return 1
            i += 2
        else:
            print(USAGE, file=sys.stderr)
            return 1

    latest_tag = _latest_tag()
    if not latest_tag:
        print(
            "Error: no version tags found. Create an initial tag: git tag -a v0.0.0 -m v0.0.0",
            file=sys.stderr,
        )
        return 1

    # `${LATEST_TAG#v}`: strip exactly one leading "v", only if present.
    current = latest_tag.removeprefix("v")
    # `${CURRENT%%-*}`: drop the first "-" and everything after it.
    version_core = current.split("-", 1)[0]

    if current_only:
        print(version_core)
        return 0

    if not bump_type:
        print("Error: --bump-type or --current required", file=sys.stderr)
        return 1

    major_s, minor_s, patch_s = _split_version_core(version_core)
    major_s = major_s or "0"
    minor_s = minor_s or "0"
    patch_s = patch_s or "0"

    if bump_type == "patch":
        major_out, minor_out = major_s, minor_s
        patch_out = str(int(patch_s) + 1)
    elif bump_type == "minor":
        major_out = major_s
        minor_out = str(int(minor_s) + 1)
        patch_out = "0"
    elif bump_type == "major":
        major_out = str(int(major_s) + 1)
        minor_out = "0"
        patch_out = "0"
    else:
        print(
            f"Error: invalid bump type '{bump_type}' (expected patch, minor, or major)",
            file=sys.stderr,
        )
        return 1

    print(f"{major_out}.{minor_out}.{patch_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
