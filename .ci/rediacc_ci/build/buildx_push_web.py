#!/usr/bin/env python3
"""Port of `.ci/scripts/build/buildx-push-web.sh` (46 lines).

Builds ONE single-arch web image variant and pushes it. The twin's header says
why single-arch (emulated arm64 builds of this image were prohibitively slow, so
amd64 and arm64 run as separate jobs on native runners and are joined into a
manifest later) and that reasoning is not restated here.

Everything is driven by ENVIRONMENT, not argv: `PLATFORM`, `VARIANT`,
`IMAGE_PATH`, `WEB_TAG` and `ACCOUNT_ENTRY` are required, and
`ACCOUNT_ED25519_PUBLIC_KEY` is optional and may be empty on a non-release
build.

LIVE CALLERS, none repointed by this port. Four workflow steps, two amd64 and
two arm64, all in `.github/workflows/ci-build-docker.yml`:
  * `:287`  `Build & push (amd64)`, `build-server-docker`,       PLATFORM=linux/amd64
  * `:387`  the arm64 twin of it,   `build-server-docker-arm64`, PLATFORM=linux/arm64
  * plus the two later variant jobs that reach it through the same step name.
`.ci/scripts/ci/generate-tag.sh:220` and `rediacc_ci/ci/generate_tag.py:162`
name the path in the change-detection table; neither EXECUTES it.

-----------------------------------------------------------------------------
IT PUSHES TO ghcr.io, SO THE DIFFERENTIAL NEVER RUNS `docker`
-----------------------------------------------------------------------------
`--push` on the build means there is no dry-run mode and no local-only path:
one real invocation is a registry write. Every case in
`.ci/rediacc_ci/tests/test_build_buildx_push_web.py` runs against a RECORDING
FAKE `docker` on a PATH that REPLACES the caller's rather than prepending to it,
and the suite asserts that the real binary is unreachable from that PATH before
it drives either side. The argv the fake records IS the evidence: swapping two
`--build-arg` values, or dropping `--push`, produces identical stdout, identical
stderr and an identical exit code, and only the call log can tell.

-----------------------------------------------------------------------------
THE FIVE `: "${VAR:?...}"` REFUSALS ARE bash's, AND THEY ARE FORGED
-----------------------------------------------------------------------------
`:27-31` refuse through parameter expansion, not through `common.sh`, so the
message has no `✗` and no colour: bash writes
`<script>: line 27: PLATFORM: PLATFORM is required (linux/amd64 or linux/arm64)`
on stderr and exits 1. This port reproduces the sentence, following
`rediacc_ci.docker.retag_image`'s precedent for `set -u` deaths, because the
five sentences are the entire operator-facing contract of the script and a
silent exit 1 would say nothing at all.

Two properties of `:?` that are easy to get wrong and are pinned:

  * `:?` (with the colon) fires on SET-BUT-EMPTY as well as unset, so
    `PLATFORM=` refuses. `${VAR?...}` would not. Driven both ways.
  * THE ORDER IS OBSERVABLE. The expansions run top to bottom, so a run with
    none of the five set reports `PLATFORM` and stops; a port that validated
    them in any other order would print a different sentence with the same exit
    code. `require_cmd docker` (`:26`) runs BEFORE all five, so a machine with
    no docker hears about docker even when every variable is also missing.

`$0` is the one thing that cannot agree between the two sides: bash prints the
path it was invoked with and `sys.argv[0]` ends `.py`. The differential masks
both to `<SELF>` and compares everything else byte-for-byte. `shadow-gate.ts`
files the line as chatter on both sides -- no `✗`/`ERROR:`/`::error::` marker,
and it does not match the `<path>:<line>:` finding shape either, because bash
writes `: line 27:` with a space after the colon -- so it plays no part in any
recorded ledger verdict.

-----------------------------------------------------------------------------
THREE DEFECTS IN THE TWIN, REPRODUCED HERE RATHER THAN FIXED
-----------------------------------------------------------------------------
Fixing any of them changes what four live release-path workflow steps do, which
is outside this port's ownership (W7P6: the bash twin stays registered). All
three are pinned by tests.

  1. THE BUILD CONTEXT IS THE CALLER'S CURRENT DIRECTORY, UNCHECKED (`:36,:44`).
     `--file Dockerfile` and the trailing `.` are both relative and the script
     never `cd`s -- unlike BOTH of its neighbours in the same directory,
     `build-www.sh:12` and `build-json.sh:12`, which begin `cd "$(get_repo_root)"`.
     Run from anywhere but the repo root it builds the wrong context, and it
     does not fail cleanly: it fails as `docker` complaining it cannot read a
     Dockerfile, or worse, it succeeds against a DIFFERENT Dockerfile that
     happens to be there. Driven: from a scratch directory containing a
     one-line `Dockerfile`, the twin builds that one and pushes it under the
     production tag, exit 0. The four live call sites are safe only because
     GitHub Actions happens to start every `run:` at the workspace root.
  2. `PLATFORM` IS NEVER VALIDATED, ONLY SPLIT (`:33`). The refusal message
     promises `linux/amd64 or linux/arm64`; the code is `ARCH="${PLATFORM##*/}"`,
     which accepts anything. Driven: `PLATFORM=nonsense` exits 0 having pushed
     `<IMAGE_PATH>:<WEB_TAG>-nonsense`, and `PLATFORM=linux/` pushes a tag
     ending in a bare hyphen. The image name is derived from unvalidated input
     on a path whose only mode is `--push`, so a typo in a workflow `env:` block
     publishes a real tag under a name nothing will ever look for.
  3. THE OPTIONAL BUILD ARG IS ALWAYS PASSED, EMPTY OR NOT (`:41`).
     `ACCOUNT_ED25519_PUBLIC_KEY=` reaches the Dockerfile as a defined-but-empty
     build arg rather than being omitted, so a Dockerfile distinguishing
     "unset" from "empty" cannot. Reproduced verbatim; noted because the twin's
     own header calls the variable optional, which it is not, at the docker
     level.

-----------------------------------------------------------------------------
ONE THING THAT IS NOT A DEFECT, stated so it is not "fixed" later
-----------------------------------------------------------------------------
`set -e` lets docker's exit status through unchanged: a build that fails with 17
exits 17, and the success line is not printed. That is the OPPOSITE of
`build-www.sh`, which flattens npm's status to 1 (see `build_www`, defect 2).
The two are inconsistent with each other and this one is the correct half, so it
is kept exactly.

K=5 LEDGER: `.ci/shadow/w7p6-buildx-push-web.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# The five `: "${VAR:?...}"` expansions (`:27-31`), IN THE TWIN'S ORDER, each
# with the line bash names in its diagnostic and the message verbatim. A tuple
# rather than a dict so the order cannot be lost to a re-sort.
REQUIRED_ENV: tuple[tuple[str, int, str], ...] = (
    ("PLATFORM", 27, "PLATFORM is required (linux/amd64 or linux/arm64)"),
    ("VARIANT", 28, "VARIANT is required"),
    ("IMAGE_PATH", 29, "IMAGE_PATH is required"),
    ("WEB_TAG", 30, "WEB_TAG is required"),
    ("ACCOUNT_ENTRY", 31, "ACCOUNT_ENTRY is required"),
)

# `:41`. Optional, and read with a `:-` default, so unset and empty are the same
# thing to the twin.
OPTIONAL_ENV = "ACCOUNT_ED25519_PUBLIC_KEY"

# The line of the `docker buildx build` (`:35`), for the `command not found`
# diagnostic bash would write if docker vanished between `require_cmd` and the
# call.
DOCKER_LINE = 35


def bash_expansion_refusal(name: str, line: int, message: str) -> str:
    """bash's `${VAR:?message}` diagnostic, without its trailing newline."""
    return "%s: line %d: %s: %s" % (sys.argv[0], line, name, message)


def arch_of(platform: str) -> str:
    """`ARCH="${PLATFORM##*/}"` (:33). Longest leading `*/` removed.

    Not `os.path.basename` and not a validator: `linux/amd64` gives `amd64`,
    `nonsense` gives `nonsense` (defect 2), `linux/` gives the empty string, and
    `a/b/c` gives `c`. All four are pinned against the real shell.
    """
    return platform.rsplit("/", 1)[-1]


def build_argv(
    platform: str,
    variant: str,
    image_path: str,
    web_tag: str,
    account_entry: str,
    public_key: str,
) -> list[str]:
    """`:35-44`, argument for argument, including the trailing `.` context.

    Exported so the differential can compare it against the fake's recorded argv
    without inferring the order from the output, and so a reader can see that
    the context is `.` -- the CALLER's directory. See defect 1.
    """
    return [
        "docker",
        "buildx",
        "build",
        "--file",
        "Dockerfile",
        "--target",
        variant,
        "--platform",
        platform,
        "--build-arg",
        "VITE_APP_VERSION=%s" % web_tag,
        "--build-arg",
        "ACCOUNT_ENTRY=%s" % account_entry,
        "--build-arg",
        "%s=%s" % (OPTIONAL_ENV, public_key),
        "--tag",
        "%s:%s-%s" % (image_path, web_tag, arch_of(platform)),
        "--push",
        ".",
    ]


def main(argv: list[str]) -> int:
    """The twin's whole body, in its order. Extra arguments are ignored, as there."""
    del argv  # `.ci/scripts/build/buildx-push-web.sh` parses none.

    # `:26`, and it runs BEFORE the five expansions.
    try:
        common.require_cmd("docker")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    # `:27-31`. EVERY NAME IS A LITERAL AT ITS OWN `os.environ.get` CALL SITE,
    # and the obvious `for name, ... in REQUIRED_ENV: os.environ.get(name)` is
    # deliberately not used. `check:ci-python-env-registry` derives a module's
    # declared inputs from the AST, and a non-literal key is recorded as the
    # EXPRESSION -- `*name` -- so the loop form would leave all five of this
    # script's actual inputs undeclared while the gate stayed green. Measured
    # against the gate's own `scan_module`: the loop yields
    # `['*name', 'ACCOUNT_ED25519_PUBLIC_KEY']`, this form yields all six names.
    values = {
        "PLATFORM": os.environ.get("PLATFORM", ""),
        "VARIANT": os.environ.get("VARIANT", ""),
        "IMAGE_PATH": os.environ.get("IMAGE_PATH", ""),
        "WEB_TAG": os.environ.get("WEB_TAG", ""),
        "ACCOUNT_ENTRY": os.environ.get("ACCOUNT_ENTRY", ""),
    }
    # Reading is side-effect-free, so reading all five above and REFUSING in the
    # twin's order here is observationally identical to bash expanding them one
    # at a time: the first empty one is the only one reported.
    for name, line, message in REQUIRED_ENV:
        if not values[name]:
            print(bash_expansion_refusal(name, line, message), file=sys.stderr, flush=True)
            return 1

    command = build_argv(
        platform=values["PLATFORM"],
        variant=values["VARIANT"],
        image_path=values["IMAGE_PATH"],
        web_tag=values["WEB_TAG"],
        account_entry=values["ACCOUNT_ENTRY"],
        # Defect 3: passed whether or not it has a value.
        public_key=os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", ""),
    )

    # Both streams INHERITED: a buildx log is the caller's, not this script's.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        code = subprocess.run(command, check=False).returncode
    except PermissionError:
        print(
            "%s: line %d: docker: Permission denied" % (sys.argv[0], DOCKER_LINE),
            file=sys.stderr,
            flush=True,
        )
        return 126
    except FileNotFoundError:
        print(
            "%s: line %d: docker: command not found" % (sys.argv[0], DOCKER_LINE),
            file=sys.stderr,
            flush=True,
        )
        return 127

    # `set -e`: docker's own status, not a flattened 1. See the note above.
    if code != 0:
        return code

    log.info(
        "Pushed %s:%s-%s" % (values["IMAGE_PATH"], values["WEB_TAG"], arch_of(values["PLATFORM"]))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
