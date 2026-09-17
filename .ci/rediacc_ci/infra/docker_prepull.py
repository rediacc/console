#!/usr/bin/env python3
"""Port of `.ci/scripts/infra/docker-prepull.sh`.

Pre-pull the public base images a buildx build is about to need, with retry.
The twin's own header states the reason: buildx occasionally fails to
authenticate mid-build when it pulls a base image itself, so pulling the bases
up front with `docker pull` sidesteps that and a transient registry hiccup
retries here instead of failing the build.

NOT `ci-pull-images.sh`, which authenticates to GHCR and pulls our own rediacc
images. This one pulls public bases and needs no credentials.

-----------------------------------------------------------------------------
THIS IS A DIFFERENT TWIN FROM `rediacc_ci.proxies.docker_prepull`, AND THE
NAME COLLISION IS WORTH ONE PARAGRAPH BECAUSE IT LOOKS LIKE DUPLICATED WORK
-----------------------------------------------------------------------------
`rediacc_ci.proxies.docker_prepull` is the port of
`.ci/scripts/test/proxies/proxy-docker-prepull.sh`, the local PROXY that drives
this script against a real docker daemon on `hello-world`. Its own docstring
says so in as many words: "The subject stays bash and unported; only the proxy
is ported here." THIS module is that subject. The two files have the same
basename because the proxy is named after what it proxies; nothing here is a
second copy of anything there.

WRITTEN AS A MODULE NAME, NOT AS A PATH, AND THAT IS LOAD-BEARING. Spelling it
`.ci/rediacc_ci/proxies/<basename>.py` gives that file the `mentioned` route in
`check:ci-dead-python`, whose exemption-liveness half then reports its
`MANUAL_ENTRY_POINTS` entry as no longer true -- a finding produced by a
sentence in a docstring rather than by anything that runs. Measured: the path
spelling reddened that gate with one extra finding, this spelling does not.
Leave it dotted.

-----------------------------------------------------------------------------
`sleep` IS EXECUTED, NOT `time.sleep`, and that is the reason the differential
for the retry path costs milliseconds instead of three minutes
-----------------------------------------------------------------------------
`wait_for_vm_ssh.py:30-36` already records the argument and this port follows
it: both implementations resolve `sleep` through PATH, so ONE stub on a scratch
PATH serves both sides. `time.sleep` would leave the bash side stubbed and the
Python side sleeping for real, and a comparison timed differently on the two
sides is not a comparison. The schedule is the twin's: 30s after the first
failure, 60s after the second, nothing after the third.

`docker pull` ITSELF INHERITS BOTH STREAMS. The twin never captures it, so the
pull's progress meter goes to the caller's terminal in real time; a port that
captured and replayed would reorder it against this script's own log lines.

-----------------------------------------------------------------------------
THE ARGUMENT GRAMMAR IS THE INTERESTING PART, and it is one line of bash
-----------------------------------------------------------------------------
    image="${spec%%=*}"                       text before the FIRST `=`
    [[ "$spec" == *=* ]] && platform="${spec#*=}"   everything after it

So `ubuntu:24.04` is a bare ref with no platform, `ubuntu:24.04=linux/amd64`
splits into the two, and a ref carrying its own `:` and `/`
(`ghcr.io/rediacc/x:1`) survives because the split is on `=` alone. A spec of
`a=b=c` yields image `a`, platform `b=c` -- `%%=*` is the LONGEST suffix match
and `#*=` the SHORTEST prefix match, which point at the same `=`.

TWO SHAPES THE TWIN ACCEPTS THAT LOOK LIKE MISTAKES, both preserved:

  * `=linux/amd64` (an empty ref) reaches docker as an empty image argument and
    fails there, with docker's message, three times, with the sleeps. The twin
    validates no spec beyond the split.
  * `ubuntu:24.04=` (a trailing `=`) matches `*=*`, so the platform is set to
    the EMPTY STRING, and `[[ -n "$platform" ]]` is then false -- so it behaves
    exactly like a bare ref. Pinned by `test_a_trailing_equals_is_a_bare_ref`.

-----------------------------------------------------------------------------
ONE HAZARD, REPORTED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
The closing line is `log_info "Pre-pulled $# base image(s)"`, and `$#` is the
number of ARGUMENTS, not the number of images that were pulled. Pass the same
ref twice and it says 2; the count is a restatement of the command line rather
than a measurement of what happened. It is only ever reached when every spec
succeeded, so it cannot over-report a failure -- which is why this is a
reporting wart and not a green-when-red gate, and why fixing it would change a
line a workflow log reader has learned to read. Pinned by
`test_the_count_is_the_argument_count_not_the_image_count`.

Exit: 0 when every spec pulled, 1 on no arguments, on a missing docker, or when
any spec could not be pulled after 3 attempts.

K=5 LEDGER: `.ci/shadow/w7p6-docker-prepull.observations.jsonl`.
"""

from __future__ import annotations

import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `for i in 1 2 3` and `sleep $((i * 30))` (docker-prepull.sh:40-47).
ATTEMPTS = 3
BACKOFF_UNIT_SECONDS = 30

# `${platform:-<default>}` in both retry messages. The angle brackets are
# literal text in the twin, not a placeholder this port is meant to fill in.
NO_PLATFORM = "<default>"

NO_IMAGES = "No images given."
USAGE_TAIL = "Usage: %s <ref>[=<platform>] ...   e.g. ubuntu:24.04=linux/amd64"
ALL_FAILED = "One or more base images could not be pulled"


def split_spec(spec: str) -> tuple[str, str]:
    """`<ref>[=<platform>]` -> (image, platform). See the module docstring.

    Exported so the differential can drive the grammar directly, which is the
    half of this script that has interesting cases and no network.
    """
    image, sep, platform = spec.partition("=")
    return image, (platform if sep else "")


def pull_argv(image: str, platform: str) -> list[str]:
    """`docker pull ${args[@]} "$image"`.

    `[[ -n "$platform" ]] && args=(--platform "$platform")`, so an EMPTY
    platform contributes no arguments at all rather than an empty `--platform`
    value. That is what makes a trailing `=` behave like a bare ref.
    """
    if platform:
        return ["docker", "pull", "--platform", platform, image]
    return ["docker", "pull", image]


def pull_with_retry(image: str, platform: str) -> bool:
    """`pull_with_retry` (docker-prepull.sh:34-52). True when the image landed.

    Streams are INHERITED: docker's progress output is the twin's output too.
    A missing `docker` cannot be reached from `main` (require_cmd runs first),
    but `FileNotFoundError` is folded into "this attempt failed" anyway, the
    way bash's 127 would be, so a caller importing this function directly gets
    a verdict rather than a traceback.
    """
    label = platform or NO_PLATFORM
    for attempt in range(1, ATTEMPTS + 1):
        try:
            code = subprocess.run(pull_argv(image, platform), check=False).returncode
        except OSError:
            code = 127
        if code == 0:
            return True
        if attempt < ATTEMPTS:
            log.warn(
                "Pull failed for %s %s, retrying in %ds..."
                % (image, label, attempt * BACKOFF_UNIT_SECONDS)
            )
            # EXECUTED, not `time.sleep`. See the module docstring.
            subprocess.run(["sleep", str(attempt * BACKOFF_UNIT_SECONDS)], check=False)
    log.error("Failed to pull %s %s after %d attempts" % (image, label, ATTEMPTS))
    return False


def main(argv: list[str]) -> int:
    # ORDER, KEPT: the no-arguments refusal comes BEFORE `require_cmd docker`, so a bare invocation on a host with no docker still gets the usage line rather than a message about a binary it was never going to reach.
    if not argv:
        log.error(NO_IMAGES)
        # `$0` is the path the caller typed, so this line names the port when the port is what ran. The twin's own text is otherwise identical, including the three spaces before `e.g.`.
        log.error(USAGE_TAIL % sys.argv[0])
        return 1

    try:
        common.require_cmd("docker")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    failed = False
    for spec in argv:
        image, platform = split_spec(spec)
        if not pull_with_retry(image, platform):
            # `|| failed=1`: every spec is attempted, so one bad ref does not
            # hide the state of the ones after it.
            failed = True

    if failed:
        log.error(ALL_FAILED)
        return 1

    # `$#`, the ARGUMENT count. See the hazard in the module docstring.
    log.info("Pre-pulled %d base image(s)" % len(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
