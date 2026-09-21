#!/usr/bin/env python3
"""Port of `.ci/scripts/infra/docker-pull-ghcr.sh`.

Authenticate to GHCR, pull ONE named image, log out again. The twin's header sells the logout as "preserves other Docker credentials", which is what `docker logout ghcr.io` does that deleting `~/.docker/config.json` would not.

-----------------------------------------------------------------------------
THE SHARED GHCR-AUTH LOGIC WITH `ci-pull-images.sh`, AND WHY NO HELPER IS BEING
INVENTED HERE
-----------------------------------------------------------------------------
`.ci/scripts/infra/ci-pull-images.sh` (ported beside this file as `rediacc_ci.infra.ci_pull_images`) runs the same login/pull/logout dance. The duplication is REAL and it is not shared today: `.ci/scripts/lib/common.sh` is 772 lines and contains no `ghcr`, no `docker login`, and no registry helper at all (grepped 2026-09-13, zero hits). Both twins open-coded it.

This one's twin has since been retired against `goldens/docker-pull-ghcr/`, and the duplication it names lives on in the sibling.

So this port open-codes it too. Factoring a `core.ghcr` on the Python side only would give the port a structure its twin does not have, and the differential would then be comparing two differently-shaped programs -- which is how a port starts "agreeing" for reasons unrelated to the subject. Naming the duplication is the deliverable; removing it is a cutover decision for a later
box.

FOUR LIVE DIFFERENCES BETWEEN THE TWO TWINS, none of them cosmetic, all of them preserved on both Python sides:

  1. THIS script calls `require_cmd docker`; `ci-pull-images.sh` does not, so
     the two behave differently on a runner with no docker (a one-line refusal
     at exit 1 here, bash's `command not found` at 127 there).
  2. THIS script is `set -euo pipefail`; `ci-pull-images.sh` is bare `set -e`.
  3. THIS script takes `--token`/`--actor` and falls back to the environment;
     `ci-pull-images.sh` is environment-only.
  4. THIS script's `docker logout` is UNGUARDED, so a failing logout ends the
     run non-zero AFTER a successful pull and the "Successfully pulled" line
     never prints. `ci-pull-images.sh` writes `2>/dev/null || true`. Pinned by
     `test_a_failing_logout_loses_the_success_line`.

-----------------------------------------------------------------------------
THE `:latest` LADDER IS THE INTERESTING PART, AND IT HAS THREE ARMS, NOT TWO
-----------------------------------------------------------------------------
Reached only when `CI` is NON-EMPTY (`[[ -n "${CI:-}" ]]`, so `CI=0` and `CI=1`
both count -- this is NOT `is_ci`, which compares against the literal `true`) and the image ends in `:latest`:

    USE_CI_IMAGES=true   -> three error lines, exit 1. The build produced a
                            CI-tagged image and something asked for latest, so
                            the pull would silently test the wrong artifact.
    USE_CI_IMAGES=false  -> ONE WARNING and the pull proceeds. This is the
                            no-private-repo-access fallback.
    anything else        -> three error lines, exit 1. The twin calls this the
                            "legacy fallback"; note that `USE_CI_IMAGES=TRUE`
                            and `USE_CI_IMAGES=1` land HERE, not in the first
                            arm, because the comparison is against the exact
                            literal.

`*":latest"` is a GLOB SUFFIX, not a tag parse, so `ghcr.io/x/notlatest` does not match and `ghcr.io/x/y:notlatest` does not either, while a bare `:latest` would. Reproduced with `str.endswith`, which is the same test.

-----------------------------------------------------------------------------
ARGUMENT PARSING IS common.sh's `parse_args`, QUIRKS INCLUDED
-----------------------------------------------------------------------------
`rediacc_ci.core.common.parse_args` is the port of that function and is reused rather than re-derived, so this file inherits the two behaviours 53 bash callers already live with:

  * `--image -x` CONSUMES `-x` as the value, because the lookahead excludes only
    tokens starting with `--` (QUIRK 4 in `core.common`).
  * `--quiet` with nothing after it is the string `"true"`, which is exactly
    what `[[ "$QUIET" == "true" ]]` wants; `--quiet false` is the string
    `"false"` and drops the flag.

`--quiet` DOES NOT MEAN QUIET HERE, ONLY FOR DOCKER. It adds `--quiet` to `docker pull` and changes nothing about this script's own three `log_step` lines. Pinned by `test_quiet_only_reaches_docker_and_not_the_log_lines`.

-----------------------------------------------------------------------------
ONE LATENT PORTABILITY HAZARD IN THE TWIN, REPORTED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
`PULL_ARGS=()` followed by `docker pull "${PULL_ARGS[@]}" "$IMAGE"` expands an
EMPTY array under `set -u`. bash 4.4+ treats that as zero words; bash 4.3 and earlier (which is what ships as `/bin/bash` on stock macOS, 3.2) raise `PULL_ARGS[@]: unbound variable` and the script dies before pulling anything. Every CI runner here is bash 5, so it is latent. Not repaired: the twin stays live and a one-for-one port does not get to change the twin's argv.

Exit: 0 on a completed pull; 1 for a missing `--image`, a `:latest` violation, a missing token, a missing actor, or a missing `docker`; otherwise docker's own status from login, pull or logout.

K=5 LEDGER: `.ci/shadow/w7p6-docker-pull-ghcr.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

REGISTRY_HOST = "ghcr.io"

# `*":latest"`, as a suffix. See the module docstring.
LATEST_SUFFIX = ":latest"

# `"${USE_CI_IMAGES:-}" == "true"` / `== "false"`. The exact literals, because
# `TRUE` and `1` take the third arm and that is a behavioural difference.
USE_CI_TRUE = "true"
USE_CI_FALSE = "false"

USAGE = (
    "Usage: docker-pull-ghcr.sh --image <ghcr.io/org/repo:tag> [--token <token>] [--actor <actor>]"
)

# The three-line refusal, shared by the `USE_CI_IMAGES=true` arm and the legacy
# arm, which differ only in their middle line.
LATEST_HEAD_CI = "ERROR: Pulling :latest tag when USE_CI_IMAGES=true"
LATEST_MID_CI = "This indicates a configuration error - CI tag should be used"
LATEST_HEAD_LEGACY = "ERROR: Pulling :latest tag is not allowed in CI"
LATEST_MID_LEGACY = "Set USE_CI_IMAGES=false to explicitly allow :latest, or use CI tag"
LATEST_TAIL = "Image requested: %s"

LATEST_ALLOWED_WARNING = "Using :latest tag (builds were skipped due to no private repo access)"

# S105 fires on the NAME (`TOKEN`), not the value. This is the twin's error text at line 58 and must stay byte-identical; nothing here is a credential.
MISSING_TOKEN = "GitHub token required (--token or GITHUB_TOKEN environment variable)"  # noqa: S105
MISSING_ACTOR = "GitHub actor required (--actor or GITHUB_ACTOR environment variable)"


def resolve(args: dict[str, str], env: dict[str, str]) -> tuple[str, str, str, str]:
    """Lines 25-28 -> (image, token, actor, quiet).

    `${ARG_TOKEN:-${GITHUB_TOKEN:-}}` is a nested COLON default, so an
    `--token ''` on the command line falls through to the environment rather than winning as an empty value. Exported so the differential can drive the precedence ladder without spawning docker.
    """
    image = args.get("ARG_IMAGE") or ""
    token = args.get("ARG_TOKEN") or env.get("GITHUB_TOKEN") or ""
    actor = args.get("ARG_ACTOR") or env.get("GITHUB_ACTOR") or ""
    quiet = args.get("ARG_QUIET") or "false"
    return image, token, actor, quiet


def latest_verdict(image: str, env: dict[str, str]) -> tuple[list[str], list[str]]:
    """Lines 40-55 -> (error lines, warning lines). Both empty means proceed.

    Returned as two lists instead of printed, because this ladder is the half of the script with real branching and no network, and a caller that can ASSERT on it is worth more than one that can only read stderr.
    """
    if not env.get("CI"):
        return [], []
    if not image.endswith(LATEST_SUFFIX):
        return [], []
    flag = env.get("USE_CI_IMAGES", "")
    if flag == USE_CI_TRUE:
        return [LATEST_HEAD_CI, LATEST_MID_CI, LATEST_TAIL % image], []
    if flag == USE_CI_FALSE:
        return [], [LATEST_ALLOWED_WARNING]
    return [LATEST_HEAD_LEGACY, LATEST_MID_LEGACY, LATEST_TAIL % image], []


def pull_argv(image: str, quiet: str) -> list[str]:
    """`docker pull "${PULL_ARGS[@]}" "$IMAGE"` (lines 73-75).

    `[[ "$QUIET" == "true" ]] && PULL_ARGS+=("--quiet")` compares against the
    exact literal, so `--quiet yes`, `--quiet 1` and `--quiet TRUE` all leave the flag OFF. Reproduced; a port that accepted any truthy spelling would pull with a different argv than the twin on the same command line.
    """
    if quiet == USE_CI_TRUE:
        return ["docker", "pull", "--quiet", image]
    return ["docker", "pull", image]


def _not_found(binary: str) -> int:
    print("%s: command not found" % binary, file=sys.stderr, flush=True)
    return 127


def docker_login(token: str, actor: str) -> int:
    """`echo "$TOKEN" | docker login ghcr.io -u "$ACTOR" --password-stdin`.

    Under `pipefail` the pipeline's status is docker's, so `set -e` ends the script with docker's code. `echo` appends the newline; it is reproduced so the bytes on docker's stdin match.
    """
    sys.stdout.flush()
    try:
        return subprocess.run(
            ["docker", "login", REGISTRY_HOST, "-u", actor, "--password-stdin"],
            input=(token + "\n").encode(),
            check=False,
        ).returncode
    except OSError:
        return _not_found("docker")


def _run(argv: list[str]) -> int:
    """Both streams INHERITED. The twin never captures docker here."""
    sys.stdout.flush()
    try:
        return subprocess.run(argv, check=False).returncode
    except OSError:
        return _not_found(argv[0])


def main(argv: list[str]) -> int:
    env = dict(os.environ)

    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        # QUIRK 3: `printf -v` on a key that is not a shell identifier exits 2 and, under this script's `set -e`, takes the whole run down before a
        # single validation has happened. `--foo.bar=x` is the reachable shape.
        exc.report()
        return exc.code

    image, token, actor, quiet = resolve(args, env)

    if not image:
        log.error(USAGE)
        return 1

    errors, warnings = latest_verdict(image, env)
    for line in errors:
        log.error(line)
    if errors:
        return 1
    for line in warnings:
        log.warn(line)

    if not token:
        log.error(MISSING_TOKEN)
        return 1
    if not actor:
        log.error(MISSING_ACTOR)
        return 1

    try:
        common.require_cmd("docker")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    log.step("Authenticating with ghcr.io...")
    code = docker_login(token, actor)
    if code != 0:
        return code

    log.step("Pulling %s..." % image)
    code = _run(pull_argv(image, quiet))
    if code != 0:
        return code

    log.step("Cleaning up GHCR credentials...")
    # UNGUARDED, unlike `ci-pull-images.sh`. Difference 4 in the module docstring: a failing logout costs the success line and the zero exit.
    code = _run(["docker", "logout", REGISTRY_HOST])
    if code != 0:
        return code

    log.info("Successfully pulled %s" % image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
