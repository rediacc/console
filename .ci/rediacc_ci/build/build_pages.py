#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-pages.sh` (78 lines).

Assembles the Cloudflare Pages deployment package: `packages/www/dist` at the
root, `packages/json/dist` under `/json/`, optionally a CLI manifest under
`/cli/edge/` and `/cli/stable/`, and then a copy of the whole thing into
`workers/www/dist` so the www worker serves it as static assets.

LIVE CALLERS, neither repointed by this port:
  * `.github/workflows/cd-stage.yml:185`  `.ci/scripts/build/build-pages.sh --output dist/pages`
  * `.ci/legacy/run-legacy.sh:231`        the same invocation, for a PR preview

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHY IT IS NOT `shutil`
-----------------------------------------------------------------------------
`rm -rf`, `mkdir -p` and `cp -r` are spawned exactly as the twin spawns them,
rather than reimplemented with `shutil.rmtree` / `os.makedirs` / `shutil.copytree`.

The reason is that this script's ONLY output on a failure is the diagnostic
those three tools print. There is no `require_*` guard on any of the six copies:
an empty `packages/www/dist` reports `cp: cannot stat 'packages/www/dist/*': No
such file or directory` and a missing `workers/www` reports `cp: cannot create
directory '<root>/workers/www/dist': No such file or directory`. Those sentences
ARE the failure surface a CI log carries, and `shutil` writes different ones.
Reproducing the tool would mean reproducing the tool's error catalogue.

The GLOB, by contrast, is BASH's and not `cp`'s (`cp -r packages/www/dist/*`
is expanded by the shell before `cp` ever runs), so it is reproduced here in
`bash_glob` rather than delegated.

-----------------------------------------------------------------------------
SIX DEFECTS IN THE TWIN, ALL REPRODUCED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
1. THE CLI-MANIFEST BLOCK IS UNREACHABLE UNDER THE DEFAULT `--output`.
   `:43` runs `rm -rf "$OUTPUT_DIR"`, whose default (`:22`) is `dist`. `:58`
   then asks whether `dist/cli-manifest/manifest.json` exists. With no
   `--output` the answer is always no, because line 43 just deleted the
   directory it lives in. Driven 2026-09-14 in a fixture: exit 0, no `cli/`
   in the package, and `✓   - /cli: ...` still printed by the summary.

2. NOTHING IN THE TREE WRITES `dist/cli-manifest/` AT ALL, so the block is
   dead even with `--output dist/pages`. `grep -rn 'dist/cli-manifest' .`
   returns three hits, all three inside this one script. The manifest producer
   (`generate-cli-manifest.sh`, driven at `cd-stage.yml:170`) writes
   `dist/cli/manifest.json`, and `cd-stage.yml:186-189` copies it into
   `dist/pages/cli/` in a separate step of its own -- to a DIFFERENT path than
   the `cli/edge/` + `cli/stable/` pair this block would have written, and
   AFTER `:71` has already copied the package into `workers/www/dist`, so that
   step's manifest never reaches the worker either.

3. THE SUMMARY CLAIMS `/cli` UNCONDITIONALLY. `:78` prints
   `- /cli: www.rediacc.com/cli/ (CLI update manifest)` whether or not the
   block at `:58` ran. Given defects 1 and 2 it has never been true.

4. DOTFILES ARE SILENTLY DROPPED, AND AN EMPTY BUILD IS A RAW `cp` ERROR.
   `packages/www/dist/*` is a bash glob: it does not match `.nojekyll`,
   `.well-known/`, or anything else beginning with a dot, and when it matches
   NOTHING bash passes the literal pattern through (no `nullglob`, no
   `failglob`), so `cp` reports `cannot stat 'packages/www/dist/*'` instead of
   the script saying which build was empty. Driven: a `dist/` holding only
   `.nojekyll` is indistinguishable from an empty one.

5. THERE IS NO `*)` ARM. `parse_args` (common.sh:324-353) ignores every token
   it does not recognise, so `build-pages.sh --outupt dist/pages` is not an
   error: `ARG_OUTPUT` stays unset, `OUTPUT_DIR` falls back to `dist`, and
   `:43` runs `rm -rf dist` against the repo's real `dist/` directory. A typo
   in the flag name is a silent delete.

6. `workers/www` IS ASSUMED TO EXIST. `:70` removes `$WORKER_DIR/dist` and
   `:71` copies into it, with no check that `$WORKER_DIR` is there. When it is
   not, the failure arrives AFTER the whole package has been assembled.

-----------------------------------------------------------------------------
DIVERGENCES, ALL IN TEXT ONLY A HUMAN READS
-----------------------------------------------------------------------------
 * `$0` inside bash's own `command not found` diagnostic is the program's own
   name, so the twin prints a `.sh` path and this prints a `.py` one. The
   differential normalises that one token and nothing else.
 * common.sh's `echo -e` interprets backslash escapes in the message;
   `rediacc_ci.log` formats the message as data. No message here contains one.
 * bash sorts a glob by the locale's collation; `bash_glob` sorts by code
   point. Under `LC_ALL=C` / `C.UTF-8` those agree bytewise, and the order is
   observable only in the argv `cp` receives.

K=5 LEDGER: `.ci/shadow/w7p6-build-pages.observations.jsonl`.
"""

from __future__ import annotations

import glob
import os
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `.ci/scripts/lib/common.sh:205-210` resolves the root as `<lib>/../../..`;
# this module sits at `.ci/rediacc_ci/build/`, which is the same depth.
_ROOT_PARENT_INDEX = 3

# `:22`. The default that makes defect 1 unconditional.
DEFAULT_OUTPUT = "dist"

# `:30` and `:36`, RELATIVE because the twin has already `cd`-ed to the root.
WWW_DIST = "packages/www/dist"
JSON_DIST = "packages/json/dist"

# `:58`, and the only three mentions of this path in the tree (defect 2).
CLI_MANIFEST = "dist/cli-manifest/manifest.json"

# `:68`. Joined onto the repo root, as there.
WORKER_SUBDIR = ("workers", "www")

# `:31-32` and `:37-38`, verbatim. Two `log_error` lines each, then `exit 1`.
NO_WWW_LINES = (
    "www build not found at packages/www/dist/",
    "Run 'npm run build:www' first",
)
NO_JSON_LINES = (
    "json build not found at packages/json/dist/",
    "Run 'npm run build:json' first",
)

# The twin's line numbers for every spawned command, because bash's
# `command not found` diagnostic names the line and a reader diffs on it.
RM_OUTPUT_LINE = 43
MKDIR_OUTPUT_LINE = 44
CP_WWW_LINE = 48
MKDIR_JSON_LINE = 53
CP_JSON_LINE = 54
MKDIR_CLI_LINE = 60
CP_CLI_EDGE_LINE = 61
CP_CLI_STABLE_LINE = 62
RM_WORKER_LINE = 70
CP_WORKER_LINE = 71

# `:75-78`, verbatim including the column padding.
SUMMARY_TAIL = (
    "  - Root:     www.rediacc.com (marketing site)",
    "  - /json:    www.rediacc.com/json/ (template catalog)",
    "  - /cli:     www.rediacc.com/cli/ (CLI update manifest)",
)


def repo_root() -> pathlib.Path:
    """The twin's `get_repo_root` (`:25`, `:67`). See `build_www` on why not `paths`."""
    return pathlib.Path(__file__).resolve().parents[_ROOT_PARENT_INDEX]


def bash_not_found_line(binary: str, line: int, reason: str) -> str:
    """bash's own diagnostic for a command it could not exec, without newline."""
    return "%s: line %d: %s: %s" % (sys.argv[0], line, binary, reason)


def bash_glob(pattern: str) -> list[str]:
    """`dir/*` as BASH expands it, which is not what `cp` would do with it.

    Three rules, and defect 4 is the second and third of them:
      * dotfiles are excluded (bash needs `dotglob`; `glob.glob` agrees), so a
        build output beginning with `.` is silently left behind;
      * NO MATCH yields the LITERAL pattern, because neither `nullglob` nor
        `failglob` is set, which is how `cp: cannot stat 'packages/www/dist/*'`
        comes to be the report for an empty build;
      * matches are sorted, which fixes the argv `cp` receives.
    """
    matches = sorted(glob.glob(pattern))
    return matches or [pattern]


def run(argv: list[str], line: int) -> int:
    """One spawned command with both streams INHERITED. Returns bash's status.

    127 for "not found" and 126 for "permission denied" are bash's numbers, and
    the accompanying stderr line is bash's too. Same shape as
    `rediacc_ci.build.build_www.run_npm`.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(argv, check=False).returncode
    except PermissionError:
        print(bash_not_found_line(argv[0], line, "Permission denied"), file=sys.stderr, flush=True)
        return 126
    except FileNotFoundError:
        print(bash_not_found_line(argv[0], line, "command not found"), file=sys.stderr, flush=True)
        return 127


def _errexit(argv: list[str], line: int) -> None:
    """`set -e`: a non-zero status from an unguarded command ends the script."""
    code = run(argv, line)
    if code != 0:
        raise SystemExit(code)


def main(argv: list[str]) -> int:
    """The twin's whole body, in its order."""
    try:
        # `:20`. QUIRK 5 lives in here: an unrecognised token is dropped, not refused.
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (sys.argv[0], exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    # `:22`. `${ARG_OUTPUT:-dist}` falls back on UNSET *and* on empty.
    output_dir = args.get("ARG_OUTPUT") or DEFAULT_OUTPUT

    root = repo_root()
    os.chdir(root)  # `:25`

    log.step("Assembling pages package...")  # `:27`

    # `:30` / `:36`. `[[ ! -d ]]` follows symlinks, and so does `Path.is_dir()`.
    if not pathlib.Path(WWW_DIST).is_dir():
        for line in NO_WWW_LINES:
            log.error(line)
        return 1

    if not pathlib.Path(JSON_DIST).is_dir():
        for line in NO_JSON_LINES:
            log.error(line)
        return 1

    # `:43-44`. Defect 1: under the default this deletes the directory holding
    # the CLI manifest that `:58` is about to look for.
    _errexit(["rm", "-rf", output_dir], RM_OUTPUT_LINE)
    _errexit(["mkdir", "-p", output_dir], MKDIR_OUTPUT_LINE)

    # `:47-49`. The trailing slash on the destination is the twin's and is kept:
    # it changes what `cp` says when the destination is not a directory.
    log.step("Copying www to root...")
    _errexit(["cp", "-r", *bash_glob(WWW_DIST + "/*"), output_dir + "/"], CP_WWW_LINE)
    log.info("Copied www to %s/" % output_dir)

    # `:52-55`.
    log.step("Copying json to /json/...")
    _errexit(["mkdir", "-p", output_dir + "/json"], MKDIR_JSON_LINE)
    _errexit(
        ["cp", "-r", *bash_glob(JSON_DIST + "/*"), output_dir + "/json/"],
        CP_JSON_LINE,
    )
    log.info("Copied json to %s/json/" % output_dir)

    # `:58-64`. Defects 1 and 2: unreachable under the default output directory,
    # and dead under every output directory because nothing writes the source.
    if pathlib.Path(CLI_MANIFEST).is_file():
        log.step("Copying CLI manifest to /cli/edge/ and /cli/stable/...")
        _errexit(
            ["mkdir", "-p", output_dir + "/cli/edge", output_dir + "/cli/stable"],
            MKDIR_CLI_LINE,
        )
        _errexit(
            ["cp", CLI_MANIFEST, output_dir + "/cli/edge/manifest.json"],
            CP_CLI_EDGE_LINE,
        )
        _errexit(
            ["cp", CLI_MANIFEST, output_dir + "/cli/stable/manifest.json"],
            CP_CLI_STABLE_LINE,
        )
        log.info("Copied CLI manifest to %s/cli/{edge,stable}/" % output_dir)

    # `:67-72`. Defect 6: `$WORKER_DIR` itself is never checked or created.
    worker_dir = root.joinpath(*WORKER_SUBDIR)
    log.step("Copying pages to www worker static assets...")
    _errexit(["rm", "-rf", str(worker_dir / "dist")], RM_WORKER_LINE)
    _errexit(["cp", "-r", output_dir, str(worker_dir / "dist")], CP_WORKER_LINE)
    log.info("Copied pages to %s/dist/" % worker_dir)

    # `:75-78`. Defect 3: the `/cli` line is printed whether or not it is true.
    log.info("Pages package ready at %s/" % output_dir)
    for line in SUMMARY_TAIL:
        log.info(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
