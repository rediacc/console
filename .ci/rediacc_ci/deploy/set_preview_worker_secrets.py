#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/set-preview-worker-secrets.sh`.

Pushes fifteen runtime secrets into the per-PR preview Worker `pr-<PR_NUMBER>` in ONE `wrangler secret bulk` call. The twin's own header carries the reason the call is bulk and not fifteen `secret put`s: each `put` mints a new Worker version, and on an assets-bound Worker a new version disassociates the static assets the deploy just uploaded. One bulk call sets them all against a
single version.

SECRETS ARRIVE AS ENVIRONMENT VARIABLES, NEVER AS ARGUMENTS, and this port keeps that property end to end. `argv` is visible in `ps` and in some log surfaces; the value only ever travels env -> `jq --arg` -> the pipe into `wrangler`, exactly as the twin routes it.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` is the only external tool that carries a credential, so the differential (`.ci/rediacc_ci/tests/test_deploy_set_preview_worker_secrets.py`) puts a RECORDING FAKE `npx` on a scratch PATH that logs its exact argv AND THE BYTES ON ITS STDIN. The stdin log is the main evidence for this script: the observable effect of the program is the
JSON document handed to `wrangler`, and two implementations can print an identical `✓ Set 15 secrets` line while writing a different key set, a different key ORDER, or a differently escaped value.

`jq` IS CALLED, NOT REIMPLEMENTED, and here the reason is stronger than the one `cf_purge_urls.py` gives for the same choice. The bytes on wrangler's stdin ARE the contract, and `json.dumps` differs from jq on inputs a secret can really contain: jq emits raw UTF-8 where `json.dumps` defaults to `\\uXXXX` escapes, and jq escapes U+007F where Python does not. A secret is opaque bytes
chosen by someone else, so "probably the same" is not a property this port may assume. The same binary, the same argv, the same document.

PIPEFAIL IS REPRODUCED, NOT APPROXIMATED. The twin's one pipeline is `jq -n ... | npx wrangler secret bulk`, under `set -o pipefail`, so the run's status is the RIGHTMOST non-zero one: wrangler's when wrangler fails, jq's when only jq fails. `main` therefore runs both sides even when jq fails, and folds the two statuses in that order.

THE ONE CASE THE SEQUENTIAL PIPE CANNOT REPRODUCE, said out loud rather than left to be discovered. In bash the two halves run CONCURRENTLY, so a `wrangler` that exited 0 WITHOUT draining its stdin would kill jq with SIGPIPE, and pipefail would end the run at 141 with no closing line. Here jq always finishes first, so the same wrangler produces a clean exit 0. It is unreachable
with the real tool, which reads the document it was given before deciding anything, and reproducing it would mean writing a second process supervisor to model a failure mode that has never occurred.

ONE DIVERGENCE, in text nobody parses. `: "${PR_NUMBER:?PR_NUMBER is required}"`
(:38) is bash's own refusal, and it prints the bash FILE and a bash LINE NUMBER:

    .ci/scripts/deploy/set-preview-worker-secrets.sh: line 38: PR_NUMBER: PR_NUMBER is required

A port cannot honestly print a line number in a file it is not. `MISSING_PR_NUMBER` carries the `VAR: message` half, on the same stream, with the same exit status 1. Identical ruling to `deploy/wait_for_preview_worker.py` and `deploy/delete_r2_channel.py`, and the differential asserts BOTH sides of it so it cannot be "fixed" into agreement by accident.

`:?` IS AN UNSET-OR-EMPTY TEST, not an unset test, so `PR_NUMBER=` refuses
exactly as an absent one does. Driven in the differential, because a port testing `"PR_NUMBER" in os.environ` would sail past the empty case and then write fifteen production secrets to a Worker literally named `pr-`.

TWO OBSERVATIONS ABOUT THE TWIN, NEITHER OF THEM REPAIRED HERE (this wave's acceptance rule is agreement with the live twin; a repair is a cutover-box decision):

  1. THE GUARD MESSAGE NAMES A VARIABLE THIS SCRIPT DOES NOT HAVE. Line 53
     prints `WORKER_NAME=$WORKER`, and there is no `WORKER_NAME` here: the
     sentence is inherited verbatim from `set-www-worker-secrets.sh`, where the
     variable is real. The VALUE printed is right (`pr-123`); the label points a
     reader at an environment variable that plays no part on this path.
     `GUARD_LABEL_SAYS_WORKER_NAME` names it so a test can assert it by name.
  2. "15" IS A LITERAL IN THE CLOSING LINE (:105), not a count of what was sent.
     Reproduced as a literal for byte parity, and `SECRET_COUNT_CLAIM` is
     asserted against `len(KEYS)` in the differential, so the day someone adds a
     sixteenth key to the twin without touching that line, the test says so
     instead of the log quietly under-reporting.

K=5 LEDGER: `.ci/shadow/w7p6-set-preview-worker-secrets.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# The twin's own name, printed in every guard message it emits (:53). A literal rather than argv[0], because the bytes must survive the port and argv[0] here is a `.py` path.
SELF = "set-preview-worker-secrets.sh"

# `WORKER="pr-${PR_NUMBER}"` (:40).
WORKER_PREFIX = "pr-"

# The `${PR_NUMBER:?...}` stand-in named in the docstring's divergence note.
MISSING_PR_NUMBER = "PR_NUMBER: PR_NUMBER is required"

# The fifteen `--arg <var> "${<ENV>:-}"` pairs (:72-86) in the twin's ORDER,
# which is also the key order of the object it builds (:87-103). ORDER IS OBSERVABLE: it is the byte order of the document on wrangler's stdin, so the tuple is the port's copy of the twin's list and the differential re-derives the same list from the twin's source and compares.
#
# (environment variable this script READS, jq variable it binds it to). ONE NAME EVERYWHERE: the variable read is the key written, which is what the Worker's zod schema declares (private/account/src/types/env.ts).
KEYS: tuple[tuple[str, str], ...] = (
    ("ACCOUNT_ED25519_PRIVATE_KEY", "ed25519_priv"),
    ("ACCOUNT_ED25519_PUBLIC_KEY", "ed25519_pub"),
    ("ACCOUNT_X25519_PRIVATE_KEY", "x25519_priv"),
    ("ACCOUNT_X25519_PUBLIC_KEY", "x25519_pub"),
    ("ACCOUNT_SERVER_API_KEY", "api_key"),
    ("ACCOUNT_JWT_SECRET", "jwt"),
    ("STRIPE_SECRET_KEY", "stripe"),
    ("STRIPE_WEBHOOK_SECRET", "stripe_wh"),
    ("ROOT_EMAIL", "admin"),
    ("AWS_SES_ACCESS_KEY_ID", "ses_key"),
    ("AWS_SES_SECRET_ACCESS_KEY", "ses_secret"),
    ("AWS_SES_REGION", "ses_region"),
    ("AWS_SES_FROM", "ses_from"),
    ("AWS_SES_CONFIGURATION_SET", "ses_cs"),
    ("CLOUDFLARE_TURNSTILE_SECRET_KEY", "turnstile"),
)

# The eleven `_require_nonempty` calls (:59-69), in order. The FIRST empty one ends the run, so the order is observable in the message a caller reads.
#
# WHY THESE ELEVEN AND NOT THE OTHER FOUR, in the twin's own words (:42-49): the SES pair, the SES region and Turnstile are optional() in the Worker schema and turn their feature off SILENTLY when empty, and the six ACCOUNT_* ones are non-optional and would make every request on the preview 500 with an EnvConfigError. Stripe is deliberately NOT demanded: ci.yml feeds the preview
# the SANDBOX key, and a preview without billing is a legitimate state.
REQUIRED_NONEMPTY: tuple[str, ...] = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_JWT_SECRET",
    "ROOT_EMAIL",
    "AWS_SES_ACCESS_KEY_ID",
    "AWS_SES_SECRET_ACCESS_KEY",
    "AWS_SES_REGION",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY",
)

# The two explanation lines under a guard failure (:54-55), byte for byte, including their two-space indent.
GUARD_EXPLANATION: tuple[str, ...] = (
    "  The Worker's schema either accepts an empty value and silently disables the",
    "  feature, or rejects it on every request; this refuses to deploy instead.",
)

# Observation 1 in the module docstring: the guard's label says WORKER_NAME while this script's variable is WORKER. Named so the differential can pin it.
GUARD_LABEL_SAYS_WORKER_NAME = True

# Observation 2: the closing line's count is a literal in the twin, not a tally.
SECRET_COUNT_CLAIM = 15


class GuardError(Exception):
    """One `_require_nonempty` firing: three stderr lines, exit 1."""

    def __init__(self, name: str, worker: str) -> None:
        super().__init__(name)
        self.name = name
        self.worker = worker

    def lines(self) -> list[str]:
        return [
            "%s: %s is EMPTY for WORKER_NAME=%s." % (SELF, self.name, self.worker),
            *GUARD_EXPLANATION,
        ]


def worker_name(pr_number: str) -> str:
    """`WORKER="pr-${PR_NUMBER}"` (:40)."""
    return "%s%s" % (WORKER_PREFIX, pr_number)


def check_nonempty(env: dict[str, str], worker: str) -> None:
    """The eleven guards, in the twin's order. Raises on the FIRST empty one.

    An ABSENT variable and an EMPTY one are the same case, because the twin
    reads `"${NAME:-}"` into the check.
    """
    for name in REQUIRED_NONEMPTY:
        if not env.get(name, ""):
            raise GuardError(name, worker)


def jq_filter() -> str:
    """The object constructor (:87-103), rebuilt from `KEYS`.

    Whitespace inside a jq program does not reach the output, so this is the twin's filter in meaning rather than in indentation. What MUST match is the key list and its order, and that is `KEYS`, which the differential re-derives
    from the twin's source.
    """
    body = ", ".join("%s: $%s" % (key, var) for key, var in KEYS)
    return "{%s}" % body


def jq_argv(env: dict[str, str]) -> list[str]:
    """`jq -n --arg ... '{...}'` (:71-103), as an argv a test can pin.

    Every value is read as `"${NAME:-}"`, so an absent variable becomes the
    empty string rather than an error: the eleven guards above have already refused the ones that must not be empty, and the other four are legitimately absent.
    """
    argv = ["jq", "-n"]
    for key, var in KEYS:
        argv += ["--arg", var, env.get(key, "")]
    argv.append(jq_filter())
    return argv


def _jq(argv: list[str]) -> tuple[int, str]:
    """The left half of the pipe: stdout captured, stderr INHERITED.

    jq's diagnostics are the only explanation a workflow log would get if the document could not be built, so they are not captured here either.
    """
    proc = subprocess.run(argv, stdout=subprocess.PIPE, text=True, check=False)
    return proc.returncode, proc.stdout


def wrangler_argv(worker: str) -> list[str]:
    """`npx wrangler secret bulk --name "$WORKER"` (:103)."""
    return ["npx", "wrangler", "secret", "bulk", "--name", worker]


def _wrangler(argv: list[str], payload: str) -> int:
    """The right half of the pipe. BOTH streams inherited, as the twin leaves them: wrangler's own progress is what a workflow log shows for this step."""
    proc = subprocess.run(argv, input=payload, text=True, check=False)
    return proc.returncode


def main(argv: list[str]) -> int:
    del argv  # the twin parses nothing; extra arguments are ignored by both

    # ORDER IS OBSERVABLE: `require_cmd jq` runs first, so a run missing both binaries names jq.
    for tool in ("jq", "npx"):
        try:
            common.require_cmd(tool)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    env = dict(os.environ)

    pr_number = env.get("PR_NUMBER", "")
    if not pr_number:
        # THE DIVERGENCE: bash prefixes this with `<path>: line 38: `.
        print(MISSING_PR_NUMBER, file=sys.stderr)
        return 1

    worker = worker_name(pr_number)

    try:
        check_nonempty(env, worker)
    except GuardError as exc:
        for line in exc.lines():
            print(line, file=sys.stderr)
        return 1

    jq_status, payload = _jq(jq_argv(env))
    wrangler_status = _wrangler(wrangler_argv(worker), payload)

    # `set -o pipefail`: the rightmost non-zero status wins.
    status = wrangler_status or jq_status
    if status:
        return status

    log.info("Set %d secrets on %s in one bulk call" % (SECRET_COUNT_CLAIM, worker))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
