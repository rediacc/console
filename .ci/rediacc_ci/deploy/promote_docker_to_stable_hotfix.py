#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/promote-docker-to-stable-hotfix.sh`.

Retags the three published `:edge` Docker images as `:stable`, skipping the normal 7-day soak. This is the emergency lane `Release` takes with
`publish_stable=true`. `docker buildx imagetools create` copies the manifest
LIST, so a multi-arch image is promoted without pulling or rebuilding anything.

Three calls, in this order, and the order is observable because it is the order a partial failure stops in:

    docker buildx imagetools create -t ghcr.io/rediacc/renet:stable  ghcr.io/rediacc/renet:edge
    docker buildx imagetools create -t ghcr.io/rediacc/rdc:stable    ghcr.io/rediacc/rdc:edge
    docker buildx imagetools create -t ghcr.io/rediacc/server:stable ghcr.io/rediacc/server:edge

The third is written out separately in the twin rather than folded into the loop, and the twin says why: the on-prem server image lives at `ghcr.io/rediacc/server`, outside the `elite/` namespace the other two share. The port keeps the split for the same reason and because a reader comparing the two files should see the same shape.

NOTHING HERE REACHES GHCR IN A TEST. `docker` is the only external tool involved and it is the one carrying the registry credential, so the differential (`.ci/rediacc_ci/tests/test_deploy_promote_docker_to_stable_hotfix.py`) puts a RECORDING FAKE `docker` on a scratch PATH that logs its exact argv. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real
run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE EVIDENCE, MORE THAN THE STREAMS. The three `Promoting ...` lines are printed BEFORE the call they announce and are derived from the loop index rather than from anything docker returns, so a port that promoted `ghcr.io/rediacc/renet:latest` would print byte-identical stdout, byte-identical stderr and exit 0. Only the recorded argv sees the difference, which is
why the fake's own stdout line is constant and why the differential plants exactly that defect.

`docker` INHERITS BOTH STREAMS. The twin never captures it, so `imagetools` progress interleaves with this script's own `echo` lines in real time. A port that captured and replayed would reorder them; a port that used `print()` without flushing would ALSO reorder them, because Python block-buffers stdout against a pipe while the child writes straight to the inherited descriptor.
`_flush` exists for that and is called before every spawn.

THE VACUITY FACT, AND IT IS THE INTERESTING PART OF THIS FILE. THERE IS NO
VERIFICATION THAT THE `:edge` TAGS EXIST OR THAT THE `:stable` TAGS MOVED. `docker buildx imagetools create` is trusted to fail loudly, and it is the only thing standing between "three images promoted" and "the closing line printed". Because every call is unguarded under `set -e` the twin cannot report a half-promotion either: renet succeeding and rdc failing leaves renet:stable
ADVANCED and server:stable BEHIND, and the run says only what docker said. `NO_POST_PROMOTION_VERIFICATION` names it so a test can assert it by name. Reproduced rather than repaired, because the acceptance rule for this wave is agreement with the live twin.

NO ARGUMENTS, NO ENVIRONMENT. The twin parses neither, so `--dry-run` is silently ignored by both sides rather than refused; the differential drives that so the agreement is recorded rather than assumed.

K=5 LEDGER: `.ci/shadow/w7p6-promote-docker-to-stable-hotfix.observations.jsonl`.
"""

from __future__ import annotations

import subprocess
import sys

from rediacc_ci.core import common

# `for image in renet rdc` (twin :29). ORDER MATTERS to the call log, which is how this port is proved equivalent, and to which images survive a mid-run docker failure.
LOOP_IMAGES = ("renet", "rdc")

# The on-prem image, handled after the loop (twin :36-40). Named separately because the twin names it separately, for the `elite/` reason in its header.
STANDALONE_IMAGE = "server"

# `ghcr.io/rediacc/${image}` (twin :31-33). A literal, because the registry and
# the org are the twin's and a port that derived either from an env var would be answering a question the twin does not ask.
REGISTRY_NAMESPACE = "ghcr.io/rediacc"

# The two tags, in the direction of promotion.
SOURCE_TAG = "edge"
TARGET_TAG = "stable"

# The defect named in the module docstring, as a constant so a test can assert it by name instead of restating the sentence.
NO_POST_PROMOTION_VERIFICATION = True


class BashExitError(Exception):
    """`set -e` ending the run on the one command the twin does not guard.

    `docker buildx imagetools create` has no `||`, no `if` and no retry, so the failing call's own stderr is the entire explanation and its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


def images() -> tuple[str, ...]:
    """Every image this script promotes, in the order it promotes them.

    A pure helper so the differential can assert the SEQUENCE directly as well as compare it against the twin: two implementations printing the same three lines can still call docker in a different order, and only the order decides what a partial failure leaves behind.
    """
    return (*LOOP_IMAGES, STANDALONE_IMAGE)


def image_ref(image: str, tag: str) -> str:
    """`ghcr.io/rediacc/<image>:<tag>` (twin :31-33, :38-40)."""
    return "%s/%s:%s" % (REGISTRY_NAMESPACE, image, tag)


def promote_argv(image: str) -> list[str]:
    """One `docker buildx imagetools create -t <dst> <src>` (twin :30-33).

    `-t` COMES FIRST AND THE SOURCE LAST, which is `imagetools create`'s own grammar rather than a style choice: the trailing positional is the manifest being copied. Swapping them would promote stable BACKWARDS onto edge, and the two argvs differ only in position, so the call log is the only witness.
    """
    return [
        "docker",
        "buildx",
        "imagetools",
        "create",
        "-t",
        image_ref(image, TARGET_TAG),
        image_ref(image, SOURCE_TAG),
    ]


def announce(image: str) -> str:
    """`echo "Promoting ${image}: edge -> stable"` (twin :30, :36).

    Printed BEFORE the call, on STDOUT, and that placement is the vacuity fact in the module docstring: the line is a statement of intent, not of outcome.
    """
    return "Promoting %s: %s -> %s" % (image, SOURCE_TAG, TARGET_TAG)


def _flush() -> None:
    """Empty Python's own buffers before a child inherits the descriptor.

    NOT HOUSEKEEPING, A REAL DIVERGENCE THIS REPAIRS. bash `echo` writes through immediately; Python block-buffers stdout when it is a pipe and flushes at exit, so without this the three `Promoting ...` lines land AFTER every line docker wrote, on the same stream, with byte-identical content in a different order. Both exits agree and the call log agrees; only a byte comparison of
    stdout sees it.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _docker(argv: list[str]) -> int:
    """One unguarded `docker` with BOTH streams inherited, as the twin leaves it."""
    _flush()
    return subprocess.run(argv, check=False).returncode


def main(argv: list[str]) -> int:
    del argv  # the twin parses nothing; extra arguments are ignored by both

    try:
        common.require_cmd("docker")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        for image in images():
            print(announce(image))
            status = _docker(promote_argv(image))
            if status:
                raise BashExitError(status)
    except BashExitError as exc:
        return exc.code

    # UNCONDITIONAL ONLY IN THE SENSE THAT NOTHING VERIFIES IT: every call above had to exit 0 to reach here, and none of them checked that the tag moved.
    print("Docker promoted to stable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
