#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-json.sh` (36 lines).

Builds the template-catalog site in `packages/json` by shelling out to
`npm run build:json` from the REPO ROOT, then refuses unless the build left
`packages/json/dist/index.html` behind.

LIVE CALLERS, none repointed by this port:
  * `.github/workflows/ci-build-docker.yml:164`  `- run: .ci/scripts/build/build-json.sh`,
    whose job then uploads `packages/json/dist/` as the `build-json-<sha>`
    artifact. Nothing else in the tree executes it.

-----------------------------------------------------------------------------
IT IS `build-www.sh` WITH THE OUTPUT CHECKS HAND-ROLLED, AND THAT IS THE POINT
-----------------------------------------------------------------------------
The two twins are line-for-line the same program through `:23`. They then
diverge, and the divergence is not a behaviour difference the authors chose --
it is two people writing the same three lines twice:

    build-www.sh:26   require_dir  "packages/www/dist"  "www build output"
    build-www.sh:27   require_file "packages/www/dist/index.html" "www index.html"

    build-json.sh:26-29  if [[ ! -d "packages/json/dist" ]]; then
                             log_error "json dist directory not created"; exit 1; fi
    build-json.sh:31-34  if [[ ! -f "packages/json/dist/index.html" ]]; then
                             log_error "json index.html not found in dist"; exit 1; fi

So the SAME failure prints two different sentences depending on which site
failed to build: `✗ Required directory 'packages/www/dist' does not exist`
against `✗ json dist directory not created`. Both are reproduced verbatim,
because a port that unified them would change what a CI log says.

Ironically the hand-rolled half is the BETTER of the two here: it names the
site, which is exactly what `build-www.sh`'s dropped label argument was trying
and failing to do (see `rediacc_ci.build.build_www`, defect 1). The library
helper is the one that loses information.

-----------------------------------------------------------------------------
EVERYTHING ELSE IS `build_www`'s DOCSTRING, AND IS NOT RESTATED
-----------------------------------------------------------------------------
The `if npm ...; then/else` shape and its three consequences (errexit suspended
inside an `if`, npm's exit code flattened to 1, a missing `npm` reported as a
failed build with bash's own `line 18: npm: command not found` above it), the
repo root being resolved from this file rather than `paths.repo_root()`, the
`cd` being observable because every later path is relative, and the `$0`
divergence that the differential masks to `<SELF>` -- all of it applies here
unchanged and is written out once, in `rediacc_ci.build.build_www`.

THE ONE DEFECT WORTH REPEATING, because it is this file's too: `✓ json build
completed` (`:19`) is printed before anything is verified, so the run that
produces an empty `dist/` prints a green tick and then a refusal.

K=5 LEDGER: `.ci/shadow/w7p6-build-json.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import sys

from rediacc_ci import log
from rediacc_ci.build.build_www import run_npm

# `.ci/scripts/lib/common.sh:205-210` resolves the root as `<lib>/../../..`;
# this module sits at `.ci/rediacc_ci/build/`, which is the same depth.
_ROOT_PARENT_INDEX = 3

# The npm script name (`build-json.sh:18`). `package.json:20` maps it to
# `npm run build -w @rediacc/json`.
NPM_SCRIPT = "build:json"

# The line of the `if npm run build:json` in the twin. The same 18 as
# `build-www.sh` by coincidence of the two files being identical up to here, not
# by construction, so it is written down separately.
NPM_LINE = 18

# `:26` and `:31`, RELATIVE because the twin has already `cd`-ed to the root.
DIST_DIR = "packages/json/dist"
INDEX_HTML = "packages/json/dist/index.html"

# `:27` and `:32`, verbatim. These are the twin's OWN sentences rather than
# `common.sh`'s generic ones; see the docstring.
NO_DIST_MESSAGE = "json dist directory not created"
NO_INDEX_MESSAGE = "json index.html not found in dist"


def repo_root() -> pathlib.Path:
    """The twin's `get_repo_root`. See `build_www` on why not `paths`."""
    return pathlib.Path(__file__).resolve().parents[_ROOT_PARENT_INDEX]


def main(argv: list[str]) -> int:
    """The twin's whole body, in its order. Extra arguments are ignored, as there."""
    del argv  # `.ci/scripts/build/build-json.sh` parses none.

    os.chdir(repo_root())

    log.step("Building json (template catalog)...")

    if run_npm(NPM_SCRIPT, NPM_LINE) == 0:
        log.info("json build completed")
    else:
        # npm's status is discarded and this is a flat 1, as in `build_www`.
        log.error("json build failed")
        return 1

    # `[[ ! -d ]]` and `[[ ! -f ]]`: both follow symlinks, and `-f` is true only
    # for a regular file, which `Path.is_dir()`/`Path.is_file()` also are.
    if not pathlib.Path(DIST_DIR).is_dir():
        log.error(NO_DIST_MESSAGE)
        return 1

    if not pathlib.Path(INDEX_HTML).is_file():
        log.error(NO_INDEX_MESSAGE)
        return 1

    log.info("json build complete: %s/" % DIST_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
