#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-www.sh` (29 lines).

Builds the Astro marketing site in `packages/www` by shelling out to
`npm run build:www` from the REPO ROOT, then refuses unless the build actually
left `packages/www/dist/index.html` behind. Nine executable lines; every one of
them is load-bearing and three of them are surprising, which is why this
docstring is longer than the twin.

LIVE CALLERS, none repointed by this port:
  * `.github/workflows/ci-build-docker.yml:123`  `- run: .ci/scripts/build/build-www.sh`
    with `APP_VERSION` and `GITHUB_TOKEN` in its `env:` block. That job then
    uploads `packages/www/dist/` as the `build-www-<sha>` artifact, so this
    script's output-verification step is the last thing standing between an
    empty build and a server image with no marketing site in it.
  * `.ci/scripts/ci/generate-tag.sh:217` and its port
    `rediacc_ci/ci/generate_tag.py:159` name the path in the change-detection
    table; neither EXECUTES it.

-----------------------------------------------------------------------------
`npm` IS SHELLED OUT TO, AND THE `if` AROUND IT IS THE WHOLE ERROR STORY
-----------------------------------------------------------------------------
`if npm run build:www; then ... else log_error; exit 1; fi` (:18-23) has three
observable consequences the twin never states, and all three are reproduced:

  * `set -e` IS SUSPENDED INSIDE AN `if` CONDITION, so npm's non-zero status
    does not kill the script; the `else` arm does, with a flat `exit 1`.
  * SO npm's OWN EXIT CODE IS DISCARDED. `npm run build:www` exiting 3 makes
    this script exit 1. Measured, not inferred; see the defect note below.
  * A MISSING `npm` IS INDISTINGUISHABLE FROM A FAILED BUILD in this script's
    own words. bash prints its own `line 18: npm: command not found` on stderr
    and hands the `if` a 127, which takes the same `else` arm and prints
    `✗ www build failed`. The port therefore forges bash's diagnostic line
    rather than letting Python's `FileNotFoundError` traceback out: that line
    is the ONLY thing on either stream that says the tool was absent.

npm's own stdout and stderr are INHERITED, exactly as under the twin. An Astro
build prints thousands of lines and a caller reading them through a pipe is the
normal case, so nothing here captures or re-emits them.

-----------------------------------------------------------------------------
THE REPO ROOT IS THIS FILE'S OWN LOCATION, and `paths.repo_root()` is NOT used
-----------------------------------------------------------------------------
Same call, and for the same reason, as `rediacc_ci.build.ensure_nfpm`:
`paths.repo_root()` honours `$REDIACC_CI_ROOT` and the twin has no such
override, so a fixture that pointed one side at a tree and not the other would
diverge silently. The twin's root is `common.sh`'s `get_repo_root`
(`.ci/scripts/lib/common.sh:205-210`), which is `SCRIPT_DIR/../../..` FROM
common.sh -- `.ci/scripts/lib` -- and NOT from `build-www.sh`. The two happen
to agree here because both files sit three levels down, but the answer belongs
to the library, not the caller.

THE `cd` IS OBSERVABLE, not housekeeping. Every path after it is RELATIVE
(`packages/www/dist`), so the refusal messages carry the relative spelling and
not an absolute path. `os.chdir` is therefore part of the contract, and
`test_both_sides_cd_to_the_repo_root_whatever_the_caller_did` pins it against a
DECOY tree in the caller's directory.

-----------------------------------------------------------------------------
THREE DEFECTS IN THE TWIN, REPRODUCED HERE RATHER THAN FIXED
-----------------------------------------------------------------------------
Fixing any of them changes what a live CI job prints, which is outside this
port's ownership (W7P6: the bash twin stays the registered gate). All three are
pinned by tests in `.ci/rediacc_ci/tests/test_build_build_www.py`.

  1. THE SECOND ARGUMENT TO `require_dir` / `require_file` IS SILENTLY DROPPED
     (`build-www.sh:26-27`). Both calls pass a human label -- `"www build
     output"`, `"www index.html"` -- and `common.sh:161-167` and `:151-157`
     read `$1` ONLY. So the operator-facing sentence is the generic
     `Required directory 'packages/www/dist' does not exist`, and the label
     that was written to explain WHICH build produced nothing never reaches a
     terminal. Driven: with `packages/www/dist` absent the twin's entire stderr
     is that generic line, with no occurrence of the string `www build output`.
     This is the same shape as `require_cmd`/`require_var` accepting several
     names and validating the first, and it is a live instance rather than a
     hypothetical: the argument is not merely redundant, it was written to be
     read and cannot be.
  2. npm's EXIT CODE IS FLATTENED TO 1 (`:18-22`). A build that died of an
     out-of-memory kill (137) and one that failed to typecheck (1) are
     indistinguishable to the workflow step, and the runner's own annotation
     therefore cannot tell an infrastructure failure from a code failure. The
     twin one directory over, `buildx-push-web.sh`, does the opposite: it lets
     `set -e` propagate docker's status verbatim. The two are inconsistent with
     each other, which is what makes this a defect rather than a house rule.
  3. `✓ www build completed` IS PRINTED BEFORE ANYTHING IS VERIFIED (`:19`).
     The green tick means "npm exited 0", not "there is a site"; the run that
     produces an empty `dist/` prints a success line and then a refusal. Kept
     verbatim, because the line is what a human greps for in a CI log.

-----------------------------------------------------------------------------
ONE NAMED DIVERGENCE THAT IS NOT REPRODUCED
-----------------------------------------------------------------------------
`$0`. bash prints the path it was invoked with in the `command not found`
line; `sys.argv[0]` is this file, whose name ends `.py` and not `.sh`. There is
no way for two files to have one name, so the differential MASKS the two paths
to `<SELF>` and asserts everything else byte-for-byte. `scripts/lib/shadow-gate.ts`
files that line as chatter on both sides (no `✗`/`ERROR:`/`::error::` marker and
no `<path>:<line>:` shape, because bash writes `: line 18:` with a space), so it
plays no part in any recorded ledger verdict either.

K=5 LEDGER: `.ci/shadow/w7p6-build-www.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `.ci/scripts/lib/common.sh:205-210` resolves the root as `<lib>/../../..`;
# this module sits at `.ci/rediacc_ci/build/`, which is the same depth.
_ROOT_PARENT_INDEX = 3

# The npm script name (`build-www.sh:18`). `package.json:22` maps it to
# `npm run build -w @rediacc/www`.
NPM_SCRIPT = "build:www"

# The line of the `if npm run build:www` in the twin, for the `command not
# found` diagnostic bash writes when npm is absent from PATH.
NPM_LINE = 18

# The two outputs the twin demands afterwards (`:26-27`), RELATIVE to the repo
# root because the twin has already `cd`-ed there. The dead second argument of
# each call -- see defect 1 -- is recorded beside the path so a reader can see
# what the message was supposed to say and does not.
DIST_DIR = "packages/www/dist"
DIST_DIR_LABEL = "www build output"
INDEX_HTML = "packages/www/dist/index.html"
INDEX_HTML_LABEL = "www index.html"


def repo_root() -> pathlib.Path:
    """The twin's `get_repo_root`. See the module docstring on why not `paths`."""
    return pathlib.Path(__file__).resolve().parents[_ROOT_PARENT_INDEX]


def bash_not_found_line(binary: str, line: int, reason: str) -> str:
    """bash's own diagnostic for a command it could not exec, without newline."""
    return "%s: line %d: %s: %s" % (sys.argv[0], line, binary, reason)


def run_npm(script: str, line: int) -> int:
    """`npm run <script>` with both streams INHERITED. Returns bash's status.

    127 for "not found" and 126 for "permission denied" are bash's numbers, not
    Python's, and the accompanying stderr line is bash's too: the twin's `if`
    swallows the status but NOT the shell's diagnostic, so a port that stayed
    silent here would lose the only evidence that npm was missing.
    """
    # stdout is inherited by the child, so anything already buffered here must
    # land first or the build log interleaves wrongly.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.run(["npm", "run", script], check=False).returncode
    except PermissionError:
        print(bash_not_found_line("npm", line, "Permission denied"), file=sys.stderr, flush=True)
        return 126
    except FileNotFoundError:
        print(bash_not_found_line("npm", line, "command not found"), file=sys.stderr, flush=True)
        return 127


def main(argv: list[str]) -> int:
    """The twin's whole body, in its order. Extra arguments are ignored, as there."""
    del argv  # `.ci/scripts/build/build-www.sh` parses none.

    os.chdir(repo_root())

    log.step("Building www (Astro)...")

    if run_npm(NPM_SCRIPT, NPM_LINE) == 0:
        log.info("www build completed")
    else:
        # Defect 2: npm's status is discarded and this is a flat 1.
        log.error("www build failed")
        return 1

    try:
        # Defect 1: the label argument is passed by the twin and read by nobody,
        # so it is NOT part of the message. Kept as an argument-shaped constant
        # so the dead label is visible in the port too.
        common.require_dir(DIST_DIR)
        common.require_file(INDEX_HTML)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    log.info("www build complete: %s/" % DIST_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
