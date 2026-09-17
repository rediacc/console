#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/set-www-worker-secrets.sh`.

Pushes twenty-four runtime secrets into the www Worker (stable or edge) in ONE
`wrangler secret bulk` call. The twin's own header carries the reason the call
is bulk and not twenty-four `secret put`s: each `put` mints a new Worker
version, and on an assets-bound Worker a new version disassociates the static
assets the deploy just uploaded.

THIS SCRIPT MARSHALS, IT DOES NOT DECIDE. Which Stripe and SES credentials land
here is `cd-deploy-worker.yml`'s choice (sandbox on edge, live EU on stable), and
the twin says so at :10-12 and again at :36-38: there is no region indirection
anywhere in it. The port keeps that property, which is why there is no channel
argument and no lookup table here either.

SECRETS ARRIVE AS ENVIRONMENT VARIABLES, NEVER AS ARGUMENTS. `argv` is visible
in `ps` and in some log surfaces; a value travels env -> `jq --arg` -> the pipe
into `wrangler` and nowhere else.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` is the only external tool that
carries a credential, so the differential
(`.ci/rediacc_ci/tests/test_deploy_set_www_worker_secrets.py`) puts a RECORDING
FAKE `npx` on a scratch PATH that logs its exact argv AND THE BYTES ON ITS
STDIN. The stdin log is the main evidence here, and on this script it is the
ONLY evidence on the happy path: unlike its preview sibling, this twin prints
NOTHING of its own when it succeeds (there is no closing `log_info` at :141), so
a port that sent an empty document would produce byte-identical streams. What
distinguishes success from doing nothing is entirely the document.

`jq` IS CALLED, NOT REIMPLEMENTED, for the reason
`set_preview_worker_secrets.py` states at length: the bytes on wrangler's stdin
ARE the contract, and `json.dumps` differs from jq on inputs a secret can really
contain (raw UTF-8 versus `\\uXXXX`, and U+007F). A secret is opaque bytes chosen
by someone else, so "probably the same" is not a property this port may assume.

PIPEFAIL IS REPRODUCED, NOT APPROXIMATED, and on this script it is a documented
repair rather than an incidental. The twin's header (:44-46) records that the
workflow block it came from ran under plain `bash -e`, and that `-uo pipefail`
were added precisely because "a jq failure previously went unnoticed because
wrangler's status won". So the run's status is the RIGHTMOST non-zero one, and
`main` runs both halves even when jq fails, then folds the two in that order.
The concurrency caveat is the same one the preview sibling names: a wrangler
exiting 0 without draining stdin would SIGPIPE jq in bash and cannot here.

ONE DIVERGENCE, in text nobody parses.
`: "${WORKER_NAME:?set-www-worker-secrets.sh: WORKER_NAME must be set}"` (:54) is
bash's own refusal, and it prints the bash FILE and a bash LINE NUMBER:

    .ci/scripts/deploy/set-www-worker-secrets.sh: line 54: WORKER_NAME: set-www-worker-secrets.sh: WORKER_NAME must be set

Note the doubled name: the twin's message already begins with the script name,
so bash's own prefix says it twice. `MISSING_WORKER_NAME` carries the
`VAR: message` half, on the same stream, with the same exit status 1. Identical
ruling to `deploy/wait_for_preview_worker.py` and `deploy/delete_r2_channel.py`,
and the differential asserts BOTH sides of it so it cannot be quietly "fixed"
into agreement.

`:?` IS AN UNSET-OR-EMPTY TEST, so `WORKER_NAME=` refuses exactly as an absent
one does. Driven in the differential: a port testing `"WORKER_NAME" in
os.environ` would sail past the empty case and then run
`wrangler secret bulk --name ''` against whatever Worker wrangler picks by
default.

THE SIBLING SCRIPTS ARE NOT THE SAME SCRIPT, and the differences are load
bearing rather than cosmetic. Against `set-preview-worker-secrets.sh`: this one
demands STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET too (thirteen guards, not
eleven), carries the nine SELLER_* keys (twenty-four keys, not fifteen), takes
its Worker name whole instead of composing `pr-<n>`, prints a DIFFERENT
explanation under a failed guard, and ends with no log line at all. Each of
those is pinned separately in the differential, because "the same file with a
longer list" is exactly the assumption that would port it wrong.

K=5 LEDGER: `.ci/shadow/w7p6-set-www-worker-secrets.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci.core import common

# The twin's own name, printed in every guard message it emits (:67). A literal rather than argv[0], because the bytes must survive the port.
SELF = "set-www-worker-secrets.sh"

# The `${WORKER_NAME:?...}` stand-in named in the docstring's divergence note.
# The twin's message repeats the script name; kept, because that is the text.
MISSING_WORKER_NAME = "WORKER_NAME: set-www-worker-secrets.sh: WORKER_NAME must be set"

# The twenty-four `--arg <var> "${<ENV>:-}"` pairs (:92-115) in the twin's ORDER,
# which is also the key order of the object it builds (:116-140). ORDER IS OBSERVABLE: it is the byte order of the document on wrangler's stdin. The differential re-derives this list from the twin's source and compares.
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
    ("SELLER_NAME", "seller_name"),
    ("SELLER_VAT_NUMBER", "seller_vat"),
    ("SELLER_REGISTRATION_NUMBER", "seller_reg"),
    ("SELLER_ADDRESS_LINE1", "seller_addr1"),
    ("SELLER_ADDRESS_LINE2", "seller_addr2"),
    ("SELLER_CITY", "seller_city"),
    ("SELLER_POSTAL_CODE", "seller_postal"),
    ("SELLER_COUNTRY", "seller_country"),
    ("SELLER_EMAIL", "seller_email"),
)

# The thirteen `_require_nonempty` calls (:77-89), in order. The FIRST empty one ends the run, so the order is observable in the message a caller reads.
#
# WHY THESE THIRTEEN, in the twin's own words (:56-76): the Worker schema marks several of them optional() and normalises "" to undefined, so an empty value
# deploys cleanly and SILENTLY turns the feature off; `required: true` on the
# GitHub side used to be the guard and a job-start Bitwarden fetch has no equivalent. The six env.ts declares NON-optional are demanded here too, because zod does catch those, but only inside the deployed Worker as an EnvConfigError 500 on every request afterwards.
#
# STRIPE IS UNCONDITIONAL HERE and is not on the preview sibling's list: edge gets the sandbox key and stable the live one, so it is never legitimately empty for www.
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
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
)

# The two explanation lines under a guard failure (:68-69), byte for byte, including their two-space indent. NOT the preview sibling's wording: that one offers two possibilities ("either accepts ... or rejects"), this one states the single behaviour the www schema has and names where to look.
GUARD_EXPLANATION: tuple[str, ...] = (
    "  The Worker's schema accepts an empty value and silently disables the feature it",
    "  drives, so this refuses to deploy instead. Check the secret store for that name.",
)

# THE HAPPY PATH SAYS NOTHING OF ITS OWN. There is no closing `log_info` at the end of the twin, unlike `set-preview-worker-secrets.sh:105`. Named as a constant because it is the reason the differential compares the document on wrangler's stdin rather than the streams: a silent success is indistinguishable
# from a silent no-op on stdout and stderr alone.
SUCCESS_IS_SILENT = True


class GuardError(Exception):
    """One `_require_nonempty` firing: three stderr lines, exit 1."""

    def __init__(self, name: str, worker_name: str) -> None:
        super().__init__(name)
        self.name = name
        self.worker_name = worker_name

    def lines(self) -> list[str]:
        return [
            "%s: %s is EMPTY for WORKER_NAME=%s." % (SELF, self.name, self.worker_name),
            *GUARD_EXPLANATION,
        ]


def check_nonempty(env: dict[str, str], worker_name: str) -> None:
    """The thirteen guards, in the twin's order. Raises on the FIRST empty one.

    An ABSENT variable and an EMPTY one are the same case, because the twin
    reads `"${NAME:-}"` into the check.
    """
    for name in REQUIRED_NONEMPTY:
        if not env.get(name, ""):
            raise GuardError(name, worker_name)


def jq_filter() -> str:
    """The object constructor (:116-140), rebuilt from `KEYS`.

    Whitespace inside a jq program does not reach the output, so this is the
    twin's filter in meaning rather than in indentation. What MUST match is the
    key list and its order, and that is `KEYS`.
    """
    body = ", ".join("%s: $%s" % (key, var) for key, var in KEYS)
    return "{%s}" % body


def jq_argv(env: dict[str, str]) -> list[str]:
    """`jq -n --arg ... '{...}'` (:91-141), as an argv a test can pin.

    Every value is read as `"${NAME:-}"`, so an absent variable becomes the
    empty string rather than an error: the thirteen guards have already refused
    the ones that must not be empty, and the eleven remaining (the two SES
    presentation fields and the nine SELLER_* ones) are legitimately absent on a
    Worker that issues no invoices.
    """
    argv = ["jq", "-n"]
    for key, var in KEYS:
        argv += ["--arg", var, env.get(key, "")]
    argv.append(jq_filter())
    return argv


def _jq(argv: list[str]) -> tuple[int, str]:
    """The left half of the pipe: stdout captured, stderr INHERITED.

    jq's diagnostics are the only explanation a workflow log would get if the
    document could not be built, and the header at :44-46 exists because that
    status used to be swallowed. Not captured here either.
    """
    proc = subprocess.run(argv, stdout=subprocess.PIPE, text=True, check=False)
    return proc.returncode, proc.stdout


def wrangler_argv(worker_name: str) -> list[str]:
    """`npx wrangler secret bulk --name "$WORKER_NAME"` (:141)."""
    return ["npx", "wrangler", "secret", "bulk", "--name", worker_name]


def _wrangler(argv: list[str], payload: str) -> int:
    """The right half of the pipe. BOTH streams inherited, as the twin leaves
    them: wrangler's own output is the entire visible result of a good run."""
    proc = subprocess.run(argv, input=payload, text=True, check=False)
    return proc.returncode


def main(argv: list[str]) -> int:
    del argv  # the twin parses nothing; extra arguments are ignored by both

    # ORDER IS OBSERVABLE: `require_cmd jq` runs first, so a run missing both binaries names jq, and both run BEFORE the WORKER_NAME guard.
    for tool in ("jq", "npx"):
        try:
            common.require_cmd(tool)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    env = dict(os.environ)

    worker_name = env.get("WORKER_NAME", "")
    if not worker_name:
        # THE DIVERGENCE: bash prefixes this with `<path>: line 54: `.
        print(MISSING_WORKER_NAME, file=sys.stderr)
        return 1

    try:
        check_nonempty(env, worker_name)
    except GuardError as exc:
        for line in exc.lines():
            print(line, file=sys.stderr)
        return 1

    jq_status, payload = _jq(jq_argv(env))
    wrangler_status = _wrangler(wrangler_argv(worker_name), payload)

    # `set -o pipefail`: the rightmost non-zero status wins.
    return wrangler_status or jq_status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
