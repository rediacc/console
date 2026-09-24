"""Port of `.ci/scripts/release/create-github-release.sh`.

Creates the GitHub Release for a version and uploads every built asset to it. Runs LAST in cd-v2.yml, after edge deploys, smoke tests and post-publish install validation, so a broken release never gets a Release page pointing at it.

REFUSES RATHER THAN PUBLISHES AN EMPTY RELEASE. `dist/{cli,packages}` matching
nothing means the download step upstream produced nothing, and a Release with no assets looks published and installs nothing. That refusal is the one behaviour here worth more than the `gh` call itself, so it keeps its own exit-1 path and its `::error::` line on STDOUT (the twin's plain `echo`, not `>&2`; reproduced because a workflow annotation is parsed off either stream and
moving it would change what a `2>/dev/null` caller sees).

THE ASSET ORDER IS BASH'S GLOB ORDER, AND `sorted(glob(...))` REPRODUCES IT.
`shopt -s globstar nullglob; assets=(dist/cli/**/* dist/packages/**/*)` sorts
each pattern's matches independently and concatenates, so this port sorts each pattern's matches independently and concatenates too, rather than sorting the union. Driven rather than reasoned about, including the case that separates a plain byte sort from a pre-order directory walk: with `dist/cli/v1/a.bin`, `dist/cli/v1-x` and `dist/cli/v1.y` present, bash emits `v1`, `v1-x`,
`v1.y`, `v1/a.bin` -- `-` (0x2D) and `.` (0x2E) both below `/` (0x2F) -- which is the byte order `sorted()` gives and is NOT the order a walk emitting a directory's children immediately after the directory would give.

ONE KNOWN LOCALE DIVERGENCE, NAMED RATHER THAN PAPERED OVER: bash sorts glob results with `strcoll`, so under a UTF-8 locale whose collation ignores punctuation the twin can order two asset paths differently from this port's codepoint sort. It changes only the order of positional arguments handed to
`gh release create`, which uploads a set; the differential pins `LC_ALL=C` on
both sides so the comparison measures the port rather than the locale.

DIRECTORIES ARE FILTERED OUT AFTER THE GLOB, not during it, matching the twin's
`for f in "${assets[@]}"; do [[ -f "$f" ]] && files+=("$f"); done`. `-f` follows
symlinks and is true only for a regular file, which is what `os.path.isfile` does, so a symlink to a directory is dropped by both and a symlink to a file is kept by both.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "create-github-release.py"

# The twin `cd "$(get_repo_root)"`s, and `get_repo_root` (common.sh:205-210) resolves three levels up from `.ci/scripts/lib`. This file sits at `.ci/rediacc_ci/release/`, which is the same three levels.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# `dist/cli/**/* dist/packages/**/*`, in the twin's order.
ASSET_PATTERNS = ("dist/cli/**/*", "dist/packages/**/*")

NO_ASSETS = "::error::No release assets matched dist/{cli,packages}/**/*"


def _require_cmd(name: str) -> int | None:
    """`require_cmd` (common.sh:141-147): log and exit 1, message byte-identical."""
    try:
        common.require_cmd(name)
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1
    return None


def _require_var(name: str) -> str:
    """`${NAME:?message}`: unset AND empty both refuse, with exit 1.

    The wording is the port's, not bash's `<script>: line N: NAME: ...`; the exit code and the named variable are what the differential compares, as in every sibling port here.
    """
    value = os.environ.get(name)
    if not value:
        print("%s: %s must be set" % (SELF, name), file=sys.stderr)
        raise SystemExit(1)
    return value


def release_assets(root: str = _ROOT) -> list[str]:
    """Every regular file under `dist/cli` and `dist/packages`, in glob order.

    Exported for the differential, which drives it directly against fixture trees a subprocess comparison could only reach through `gh`'s argv.
    """
    files: list[str] = []
    for pattern in ASSET_PATTERNS:
        matched = sorted(glob.glob(os.path.join(root, pattern), recursive=True))
        files.extend(os.path.relpath(m, root) for m in matched if os.path.isfile(m))
    return files


def main(argv: list[str]) -> int:
    del argv
    refusal = _require_cmd("gh")
    if refusal is not None:
        return refusal
    version = _require_var("VERSION")
    github_sha = _require_var("GITHUB_SHA")
    github_repository = _require_var("GITHUB_REPOSITORY")

    files = release_assets()
    if not files:
        print(NO_ASSETS)
        return 1

    proc = subprocess.run(
        [
            "gh",
            "release",
            "create",
            "v%s" % version,
            "--title",
            "v%s" % version,
            "--target",
            github_sha,
            "--generate-notes",
            # Latest means production; only mark_production moves it (see the bash twin).
            "--latest=false",
            "--repo",
            github_repository,
            *files,
        ],
        cwd=_ROOT,
        check=False,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
