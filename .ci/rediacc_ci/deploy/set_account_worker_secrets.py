#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/set-account-worker-secrets.sh`.

Pushes twenty-nine runtime secrets into ONE regional account Worker in a single `wrangler secret bulk` call. The twin's header carries the reason the call is bulk and not twenty-nine `secret put`s: each `put` mints a new Worker version, and on an assets-bound Worker a new version disassociates the static assets the deploy just uploaded.

THIS IS THE THIRD AND LARGEST MEMBER OF A FAMILY, and the differences from the other two are the whole content of the port. `set-preview-worker-secrets.sh` (15 keys) and `set-www-worker-secrets.sh` (24 keys) MARSHAL: they read a name, they write that name. This one DECIDES, four times over, and every decision is a place a port can be quietly wrong:

  1. CHANNEL. `TARGET=stable` takes the Stripe key and the region's webhook
     secret; anything else is the edge channel, where Stripe is deliberately
     blank because billing is disabled there. The two Stripe guards are
     therefore demanded on stable ONLY.
  2. REGION FAN-IN. Four values are read through a CONSTRUCTED name:
     `AWS_SES_ACCESS_KEY_ID_<SUFFIX>`, `AWS_SES_SECRET_ACCESS_KEY_<SUFFIX>`,
     `OBS_OTLP_CREDENTIALS_<SUFFIX>` and `STRIPE_WEBHOOK_SECRET_<SUFFIX>`, and
     the suffix is DROPPED on the way into the Worker, which has no concept of
     the other region's credential. The twin resolves them with bash
     indirection (`${!var}`), so a find-and-replace cannot see these names and
     neither can a reader skimming for the string.
  3. THE ASIA BORROW. With `SUFFIX=ASIA` the two SES values are overwritten with
     the literal `AWS_SES_ACCESS_KEY_ID_EU` / `AWS_SES_SECRET_ACCESS_KEY_EU`
     pair, AFTER the suffixed pair has already been read. The suffixed ASIA read
     therefore happens and is discarded; reproduced here rather than optimised
     away, because the read order is what a `set -u` failure would key on.
  4. THE BACKUP PLANE. The bucket follows the CHANNEL
     (`BACKUP_BUCKET_STABLE` / `BACKUP_BUCKET_EDGE`) and is refused when empty,
     with its own four-line message; the endpoint follows the region's R2
     JURISDICTION, and an EU bucket is reachable only at
     `<account>.eu.r2.cloudflarestorage.com`, so the jurisdiction label is
     spliced into the host when it is not already there.

SECRETS ARRIVE AS ENVIRONMENT VARIABLES, NEVER AS ARGUMENTS. `argv` is visible in `ps` and in some log surfaces; a value travels env -> `jq --arg` -> the pipe into `wrangler` and nowhere else.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` is the only external tool that carries a credential, so the differential (`.ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py`) puts a RECORDING FAKE `npx` on a scratch PATH that logs its exact argv AND the bytes on its stdin. As with the www sibling the document IS the evidence on the happy path: this twin prints nothing
of its own when it succeeds, so a port that sent the wrong bucket, the wrong region's SES key, or an un-jurisdictioned endpoint would produce byte-identical streams and exit 0.

`jq` IS CALLED, NOT REIMPLEMENTED, for the reason `set_preview_worker_secrets.py` states at length: the bytes on wrangler's stdin ARE the contract, and `json.dumps` differs from jq on inputs a secret can really contain (raw UTF-8 versus `\\uXXXX`, and U+007F). A secret is opaque bytes chosen by someone else.

PIPEFAIL IS REPRODUCED, NOT APPROXIMATED. The twin's header (:94-98) records that the workflow block it came from ran under plain `bash -e` and that `-uo pipefail` were added because "a jq failure previously went unnoticed because wrangler's status won". So the run's status is the RIGHTMOST non-zero one, and `main` runs both halves even when jq fails. The concurrency caveat is the
siblings': a wrangler exiting 0 without draining stdin would SIGPIPE jq in bash and cannot here.

TWO DIVERGENCES, BOTH IN TEXT NOBODY PARSES, BOTH ASSERTED IN THE DIFFERENTIAL
SO NEITHER CAN BE "FIXED" INTO AGREEMENT BY ACCIDENT.

  A. THE THREE `:?` REFUSALS (:106-108). Each is bash's own, and bash prints the
     FILE and a LINE NUMBER, then the twin's message, which already begins with
     the script name, so the name appears TWICE:

         .ci/scripts/deploy/set-account-worker-secrets.sh: line 106: WORKER_NAME: set-account-worker-secrets.sh: WORKER_NAME must be set

     `MISSING_MESSAGES` carries the `VAR: message` half, on the same stream, with
     the same exit status 1. Same ruling as the two siblings and as
     `deploy/wait_for_preview_worker.py`. `:?` IS AN UNSET-OR-EMPTY TEST, so
     `TARGET=` refuses exactly as an absent one does, and all three are driven
     empty in the differential.

  B. A SUFFIX THAT IS NOT AN IDENTIFIER. `${!var}` refuses a constructed name
     bash cannot parse: `SUFFIX=EU-1` ends the run at
     `AWS_SES_ACCESS_KEY_ID_EU-1: invalid variable name`, exit 1, and WHICH name
     it happens to be depends on the channel, because on stable the Stripe
     webhook indirection is evaluated first (:115) and on edge the first one
     reached is the SES key (:124). Reproduced, prefix and all, minus bash's file
     and line.

     THE ONE SHAPE THIS PORT DOES NOT REPRODUCE, said out loud rather than left
     to be discovered: bash also accepts `${!var}` where the constructed name is
     an ARRAY REFERENCE, and a scalar answers to subscript 0. So `SUFFIX=EU[0]`
     reads `AWS_SES_ACCESS_KEY_ID_EU[0]`, which IS the EU credential, and the
     twin deploys successfully where this refuses. Measured against bash 5.3.9 on
     2026-09-13, not reasoned about. It is unreachable in production (SUFFIX is
     `regions.json`'s `secretSuffix`, one of EU / US / ASIA) and modelling bash's
     subscript grammar would be a second parser written for a case that cannot
     occur, so the divergence is named, pinned by
     `test_divergence_b_an_array_subscript_suffix_is_the_one_shape_not_reproduced`,
     and left. It is also the SAFE direction: the port refuses where the twin
     would deploy, rather than deploying something the twin refused.

WHAT THE SIBLINGS' KNOWN DEFECTS DO HERE, checked one by one because this file is the copy-paste target of both:

  * THE GUARD LABEL IS CORRECT HERE. `set-preview-worker-secrets.sh:53` prints
    `WORKER_NAME=` for a script whose variable is `WORKER`; this twin really does
    have `WORKER_NAME`, and prints `TARGET` and `SUFFIX` beside it. No third
    occurrence.
  * THERE IS NO HARD-CODED COUNT, because there is no closing line at all: the
    twin ends on the pipe into wrangler (:278). `SUCCESS_IS_SILENT` names that.
  * THE DOUBLED SCRIPT NAME IS HERE, three times over. Divergence A.

K=5 LEDGER: `.ci/shadow/w7p6-set-account-worker-secrets.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from rediacc_ci.core import common

# The twin's own name, printed in every message it emits. A literal rather than argv[0], because the bytes must survive the port and argv[0] here is a `.py`.
SELF = "set-account-worker-secrets.sh"

# The channel that takes Stripe. Every other value of TARGET is the edge
# channel: the twin tests `[[ "$TARGET" == "stable" ]]` and has no third arm.
STABLE = "stable"

# The three `${VAR:?...}` stand-ins, IN THE TWIN'S ORDER (:106-108), which is
# observable: a run missing all three names WORKER_NAME. Each message repeats the script name because the twin's own text begins with it (divergence A).
MISSING_MESSAGES: tuple[tuple[str, str], ...] = (
    ("WORKER_NAME", "WORKER_NAME: %s: WORKER_NAME must be set" % SELF),
    ("TARGET", "TARGET: %s: TARGET must be set" % SELF),
    ("SUFFIX", "SUFFIX: %s: SUFFIX must be set" % SELF),
)

# The four PREFIXES read through a constructed `<PREFIX>_<SUFFIX>` name, in the order the twin evaluates them. STRIPE_WEBHOOK_SECRET is first and is reached on the stable channel only; the other three are reached on both.
SUFFIXED_PREFIXES: tuple[str, ...] = (
    "STRIPE_WEBHOOK_SECRET",
    "AWS_SES_ACCESS_KEY_ID",
    "AWS_SES_SECRET_ACCESS_KEY",
    "OBS_OTLP_CREDENTIALS",
)

# What bash will accept as the target of `${!var}`. Divergence B: bash also
# accepts an array reference, this does not.
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

# bash's own wording when `${!var}` is handed something else. The twin's output
# prefixes this with its file and a line number; the port cannot.
INVALID_VARIABLE_NAME = "%s: invalid variable name"

# The suffix ASIA borrows from, and the two names it borrows (:128-131). Literal in the twin, literal here: `regions.json` gives asia `sesRegion: eu-central-1`, so the region and the credential agree once the borrow has happened.
ASIA = "ASIA"
ASIA_BORROWS = ("AWS_SES_ACCESS_KEY_ID_EU", "AWS_SES_SECRET_ACCESS_KEY_EU")

# The bucket, by channel (:139-143). Not a secret: the names are public and already committed in workers/account/wrangler.*.toml as the BACKUP_BUCKET binding. Two constants rather than a table, because the twin's `if` has exactly two arms and a table invites a third that does not exist.
BUCKET_VAR_STABLE = "BACKUP_BUCKET_STABLE"
BUCKET_VAR_EDGE = "BACKUP_BUCKET_EDGE"

# The four lines of the bucket refusal (:151-154). The first is dynamic; the other three are byte for byte, including their two-space indent.
BUCKET_REFUSAL: tuple[str, ...] = (
    "  Expected BACKUP_BUCKET_STABLE / BACKUP_BUCKET_EDGE from the deploy",
    "  matrix (regions.json backupR2/edgeBackupR2). Refusing to deploy a",
    "  Worker that would presign against an empty bucket name.",
)

# The R2 host the jurisdiction label is spliced into (:162-165). bash's
# `${var/pat/rep}` replaces the FIRST occurrence only, hence `count=1` below.
R2_HOST = ".r2.cloudflarestorage.com"

# The two explanation lines under a failed `_require_nonempty` (:189-190), byte
# for byte. Identical to `set_www_worker_secrets.GUARD_EXPLANATION` and NOT to
# the preview sibling's, which offers two possibilities instead of one.
GUARD_EXPLANATION: tuple[str, ...] = (
    "  The Worker's schema accepts an empty value and silently disables the feature it",
    "  drives, so this refuses to deploy instead. Check the secret store for that name.",
)

# The twenty-nine `--arg <var> <value>` pairs (:219-247) in the twin's ORDER, which is also the key order of the object it builds (:248-277). ORDER IS OBSERVABLE: it is the byte order of the document on wrangler's stdin, and the differential re-derives this list from the twin's source and compares.
#
# (Worker key, jq variable, environment variable read for it). The third field is EMPTY for the seven values this script COMPUTES rather than reads, and those seven are the whole difference between this script and its two siblings: `resolve` is where each one is decided. ACCOUNT_BACKUP_S3_BUCKET is the one Worker key with no same-named variable anywhere: it comes from the channel.
KEYS: tuple[tuple[str, str, str], ...] = (
    ("ACCOUNT_ED25519_PRIVATE_KEY", "ed25519_priv", "ACCOUNT_ED25519_PRIVATE_KEY"),
    ("ACCOUNT_ED25519_PUBLIC_KEY", "ed25519_pub", "ACCOUNT_ED25519_PUBLIC_KEY"),
    ("ACCOUNT_X25519_PRIVATE_KEY", "x25519_priv", "ACCOUNT_X25519_PRIVATE_KEY"),
    ("ACCOUNT_X25519_PUBLIC_KEY", "x25519_pub", "ACCOUNT_X25519_PUBLIC_KEY"),
    ("ACCOUNT_SERVER_API_KEY", "api_key", "ACCOUNT_SERVER_API_KEY"),
    ("ACCOUNT_JWT_SECRET", "jwt", "ACCOUNT_JWT_SECRET"),
    ("STRIPE_SECRET_KEY", "stripe", ""),
    ("STRIPE_WEBHOOK_SECRET", "stripe_wh", ""),
    ("ROOT_EMAIL", "admin", "ROOT_EMAIL"),
    ("AWS_SES_ACCESS_KEY_ID", "ses_key", ""),
    ("AWS_SES_SECRET_ACCESS_KEY", "ses_secret", ""),
    ("AWS_SES_REGION", "ses_region", "AWS_SES_REGION"),
    ("AWS_SES_FROM", "ses_from", "AWS_SES_FROM"),
    ("AWS_SES_CONFIGURATION_SET", "ses_cs", "AWS_SES_CONFIGURATION_SET"),
    ("CLOUDFLARE_TURNSTILE_SECRET_KEY", "turnstile", "CLOUDFLARE_TURNSTILE_SECRET_KEY"),
    ("OBS_OTLP_CREDENTIALS", "otlp_creds", ""),
    ("ACCOUNT_BACKUP_S3_ENDPOINT", "backup_endpoint", ""),
    ("ACCOUNT_BACKUP_S3_BUCKET", "backup_bucket", ""),
    ("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", "backup_akid", "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"),
    (
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
        "backup_secret",
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
    ),
    ("SELLER_NAME", "seller_name", "SELLER_NAME"),
    ("SELLER_VAT_NUMBER", "seller_vat", "SELLER_VAT_NUMBER"),
    ("SELLER_REGISTRATION_NUMBER", "seller_reg", "SELLER_REGISTRATION_NUMBER"),
    ("SELLER_ADDRESS_LINE1", "seller_addr1", "SELLER_ADDRESS_LINE1"),
    ("SELLER_ADDRESS_LINE2", "seller_addr2", "SELLER_ADDRESS_LINE2"),
    ("SELLER_CITY", "seller_city", "SELLER_CITY"),
    ("SELLER_POSTAL_CODE", "seller_postal", "SELLER_POSTAL_CODE"),
    ("SELLER_COUNTRY", "seller_country", "SELLER_COUNTRY"),
    ("SELLER_EMAIL", "seller_email", "SELLER_EMAIL"),
)

# The fifteen unconditional `_require_nonempty` calls (:198-212), in order. The FIRST empty one ends the run, so the order is observable in the message.
#
# WHY THESE, in the twin's own words (:167-197): the Worker schema marks most of them optional() and normalises "" to undefined, so an empty value deploys cleanly and SILENTLY turns the feature off -- email stops with requests still returning 200, Turnstile disables itself, telemetry goes dark, backups 503. `required: true` on the GitHub side used to be the guard, and a job-start
# Bitwarden fetch has no equivalent: a correct UUID pointing at an empty value injects "" without complaint.
#
# THE NAME IN THE MESSAGE IS THE WORKER KEY, NOT ALWAYS THE VARIABLE TO GO LOOKING FOR. For the four fan-ins the store holds `<NAME>_<SUFFIX>`, so "Check the secret store for that name" is one suffix short of the truth on AWS_SES_ACCESS_KEY_ID, AWS_SES_SECRET_ACCESS_KEY, OBS_OTLP_CREDENTIALS and STRIPE_WEBHOOK_SECRET. Reproduced, and reported to the driver rather than repaired
# here.
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
    "OBS_OTLP_CREDENTIALS",
    "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
)

# The two demanded on the stable channel only (:213-216). On edge the twin has already blanked both, so demanding them there would refuse every edge deploy.
REQUIRED_NONEMPTY_STABLE: tuple[str, ...] = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
)

# THE HAPPY PATH SAYS NOTHING OF ITS OWN: the twin ends on the pipe into wrangler (:278), with no closing `log_info`. Named as a constant because it is the reason the differential compares the document rather than the streams, and because it is why the preview sibling's hard-coded "15" has no third occurrence to check.
SUCCESS_IS_SILENT = True


class ScriptRefusalError(Exception):
    """One refusal the SCRIPT ITSELF prints: some stderr lines and an exit status.

    NOT `common.RefusalError`, which this module also catches. That one is the library half (`require_cmd` and friends) and its lines are printed through `rediacc_ci.log.error`, so they carry the `✗ ` marker. These are the twin's own bare `echo ... >&2` lines and carry no marker at all. Two spellings because they really are two things, and a reader who conflates them will put a
    marker on output that has never had one.
    """

    def __init__(self, *lines: str, code: int = 1) -> None:
        super().__init__(lines[0] if lines else "")
        self.lines = list(lines)
        self.code = code


class GuardError(ScriptRefusalError):
    """One `_require_nonempty` firing (:185-193): three stderr lines, exit 1."""

    def __init__(self, name: str, worker: str, target: str, suffix: str) -> None:
        self.name = name
        super().__init__(
            "%s: %s is EMPTY for WORKER_NAME=%s TARGET=%s SUFFIX=%s."
            % (SELF, name, worker, target, suffix),
            *GUARD_EXPLANATION,
        )


def read_env() -> dict[str, str]:
    """Every variable the twin reads, ONE EXPLICIT `os.environ.get` PER NAME.

    NO `dict(os.environ)` ALIAS, deliberately. The AST scanner behind `.ci/config/python-env-registry.json` records the literal NAME at the call site and cannot see through an alias, so a wholesale copy would register this module as reading nothing at all while it reads thirty-two names by hand plus four it constructs.

    UNSET AND EMPTY ARE THE SAME CASE THROUGHOUT, so a plain `str` per name is
    faithful: every read in the twin is `"${NAME:-}"`, `"${NAME:?...}"` or a
    `${!var:-}` indirection, and all three collapse the two.
    """
    suffix = os.environ.get("SUFFIX", "")
    env = {
        "WORKER_NAME": os.environ.get("WORKER_NAME", ""),
        "TARGET": os.environ.get("TARGET", ""),
        "SUFFIX": suffix,
        "STRIPE_SECRET_KEY": os.environ.get("STRIPE_SECRET_KEY", ""),
        "AWS_SES_ACCESS_KEY_ID_EU": os.environ.get("AWS_SES_ACCESS_KEY_ID_EU", ""),
        "AWS_SES_SECRET_ACCESS_KEY_EU": os.environ.get("AWS_SES_SECRET_ACCESS_KEY_EU", ""),
        "BACKUP_BUCKET_STABLE": os.environ.get("BACKUP_BUCKET_STABLE", ""),
        "BACKUP_BUCKET_EDGE": os.environ.get("BACKUP_BUCKET_EDGE", ""),
        "R2_JURISDICTION": os.environ.get("R2_JURISDICTION", ""),
        "ACCOUNT_ED25519_PRIVATE_KEY": os.environ.get("ACCOUNT_ED25519_PRIVATE_KEY", ""),
        "ACCOUNT_ED25519_PUBLIC_KEY": os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", ""),
        "ACCOUNT_X25519_PRIVATE_KEY": os.environ.get("ACCOUNT_X25519_PRIVATE_KEY", ""),
        "ACCOUNT_X25519_PUBLIC_KEY": os.environ.get("ACCOUNT_X25519_PUBLIC_KEY", ""),
        "ACCOUNT_SERVER_API_KEY": os.environ.get("ACCOUNT_SERVER_API_KEY", ""),
        "ACCOUNT_JWT_SECRET": os.environ.get("ACCOUNT_JWT_SECRET", ""),
        "ROOT_EMAIL": os.environ.get("ROOT_EMAIL", ""),
        "AWS_SES_REGION": os.environ.get("AWS_SES_REGION", ""),
        "AWS_SES_FROM": os.environ.get("AWS_SES_FROM", ""),
        "AWS_SES_CONFIGURATION_SET": os.environ.get("AWS_SES_CONFIGURATION_SET", ""),
        "CLOUDFLARE_TURNSTILE_SECRET_KEY": os.environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY", ""),
        "ACCOUNT_BACKUP_S3_ENDPOINT": os.environ.get("ACCOUNT_BACKUP_S3_ENDPOINT", ""),
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": os.environ.get("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", ""),
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": os.environ.get(
            "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY", ""
        ),
        "SELLER_NAME": os.environ.get("SELLER_NAME", ""),
        "SELLER_VAT_NUMBER": os.environ.get("SELLER_VAT_NUMBER", ""),
        "SELLER_REGISTRATION_NUMBER": os.environ.get("SELLER_REGISTRATION_NUMBER", ""),
        "SELLER_ADDRESS_LINE1": os.environ.get("SELLER_ADDRESS_LINE1", ""),
        "SELLER_ADDRESS_LINE2": os.environ.get("SELLER_ADDRESS_LINE2", ""),
        "SELLER_CITY": os.environ.get("SELLER_CITY", ""),
        "SELLER_POSTAL_CODE": os.environ.get("SELLER_POSTAL_CODE", ""),
        "SELLER_COUNTRY": os.environ.get("SELLER_COUNTRY", ""),
        "SELLER_EMAIL": os.environ.get("SELLER_EMAIL", ""),
    }
    # THE FOUR REGION FAN-INS. The name is constructed, so the registry records
    # the EXPRESSION rather than a literal, exactly as the twin's `${!var}` is
    # invisible to a find-and-replace. With SUFFIX=EU two of these land on names
    # the block above already read; the value is the same either way.
    for prefix in SUFFIXED_PREFIXES:
        name = "%s_%s" % (prefix, suffix)
        env[name] = os.environ.get(name, "")
    return env


def indirect(env: dict[str, str], prefix: str, suffix: str) -> str:
    """`var="<PREFIX>_${SUFFIX}"; "${!var:-}"`, with bash's own refusal.

    Raises `ScriptRefusalError` when the constructed name is not something bash would accept as a variable name, which is divergence B in the module docstring.
    """
    name = "%s_%s" % (prefix, suffix)
    if not IDENTIFIER.match(name):
        raise ScriptRefusalError(INVALID_VARIABLE_NAME % name)
    return env.get(name, "")


def apply_jurisdiction(endpoint: str, jurisdiction: str) -> str:
    """Splice the R2 jurisdiction label into the host (:160-165).

    An EU-jurisdiction bucket lives at `<account>.eu.r2.cloudflarestorage.com` and the default host cannot see it, so a correct bucket name against the default host still fails. An endpoint already carrying the jurisdictional form is left alone, which is why the third clause is a NEGATIVE test rather than an unconditional splice.
    """
    if not jurisdiction:
        return endpoint
    labelled = ".%s%s" % (jurisdiction, R2_HOST)
    if R2_HOST in endpoint and labelled not in endpoint:
        return endpoint.replace(R2_HOST, labelled, 1)
    return endpoint


def resolve(env: dict[str, str]) -> dict[str, str]:
    """The four decisions, in the twin's order, as jq variable -> value.

    ORDER IS OBSERVABLE and it is the reason this is one function rather than four: an invalid SUFFIX is refused at the FIRST indirection reached, which is the Stripe webhook on stable (:115) and the SES key on edge (:124), and the bucket refusal (:150) comes before every `_require_nonempty` guard.
    """
    target = env.get("TARGET", "")
    suffix = env.get("SUFFIX", "")

    # 1. Stripe. The KEY is account-wide (one Stripe account, acct_1ONIroAH2UKrsSNm);
    # only the WEBHOOK signing secret is per-endpoint, hence per-region.
    if target == STABLE:
        stripe_key = env.get("STRIPE_SECRET_KEY", "")
        stripe_webhook = indirect(env, "STRIPE_WEBHOOK_SECRET", suffix)
    else:
        # Edge (beta channel): no Stripe, billing disabled.
        stripe_key = ""
        stripe_webhook = ""

    # 2. SES region fan-in, and 3. the ASIA borrow, which happens AFTER the suffixed pair has been read.
    ses_access_key_id = indirect(env, "AWS_SES_ACCESS_KEY_ID", suffix)
    ses_secret_access_key = indirect(env, "AWS_SES_SECRET_ACCESS_KEY", suffix)
    if suffix == ASIA:
        ses_access_key_id = env.get(ASIA_BORROWS[0], "")
        ses_secret_access_key = env.get(ASIA_BORROWS[1], "")

    otlp_creds = indirect(env, "OBS_OTLP_CREDENTIALS", suffix)

    # 4. The backup plane. The bucket follows the CHANNEL and is refused when empty: backup-chunk-store.ts reads `env.ACCOUNT_BACKUP_S3_BUCKET ?? ''`, so an empty value does NOT throw there. It mints presigned URLs against bucket "" and every backup upload 404s at runtime.
    bucket_var = BUCKET_VAR_STABLE if target == STABLE else BUCKET_VAR_EDGE
    backup_bucket = env.get(bucket_var, "")
    if not backup_bucket:
        raise ScriptRefusalError(
            "%s: no backup bucket for TARGET=%s." % (SELF, target), *BUCKET_REFUSAL
        )

    backup_endpoint = apply_jurisdiction(
        env.get("ACCOUNT_BACKUP_S3_ENDPOINT", ""), env.get("R2_JURISDICTION", "")
    )

    values = {var: env.get(source, "") for _key, var, source in KEYS if source}
    values.update(
        {
            "stripe": stripe_key,
            "stripe_wh": stripe_webhook,
            "ses_key": ses_access_key_id,
            "ses_secret": ses_secret_access_key,
            "otlp_creds": otlp_creds,
            "backup_endpoint": backup_endpoint,
            "backup_bucket": backup_bucket,
        }
    )
    return values


def check_nonempty(values: dict[str, str], env: dict[str, str]) -> None:
    """The fifteen guards, plus two more on stable. Raises on the FIRST empty one.

    An ABSENT variable and an EMPTY one are the same case: every value reaching
    here was read as `"${NAME:-}"` or through `${!var:-}`.
    """
    by_key = {key: values[var] for key, var, _source in KEYS}
    target = env.get("TARGET", "")
    demanded = REQUIRED_NONEMPTY
    if target == STABLE:
        demanded = REQUIRED_NONEMPTY + REQUIRED_NONEMPTY_STABLE
    for name in demanded:
        if not by_key[name]:
            raise GuardError(name, env.get("WORKER_NAME", ""), target, env.get("SUFFIX", ""))


def jq_filter() -> str:
    """The object constructor (:248-277), rebuilt from `KEYS`.

    Whitespace inside a jq program does not reach the output, so this is the twin's filter in meaning rather than in indentation. What MUST match is the key list and its order.
    """
    body = ", ".join("%s: $%s" % (key, var) for key, var, _source in KEYS)
    return "{%s}" % body


def jq_argv(values: dict[str, str]) -> list[str]:
    """`jq -n --arg ... '{...}'` (:218-277), as an argv a test can pin."""
    argv = ["jq", "-n"]
    for _key, var, _source in KEYS:
        argv += ["--arg", var, values.get(var, "")]
    argv.append(jq_filter())
    return argv


def _jq(argv: list[str]) -> tuple[int, str]:
    """The left half of the pipe: stdout captured, stderr INHERITED.

    jq's diagnostics are the only explanation a workflow log would get if the document could not be built, and the twin's header records that this status used to be swallowed. Not captured here either.
    """
    proc = subprocess.run(argv, stdout=subprocess.PIPE, text=True, check=False)
    return proc.returncode, proc.stdout


def wrangler_argv(worker_name: str) -> list[str]:
    """`npx wrangler secret bulk --name "$WORKER_NAME"` (:278)."""
    return ["npx", "wrangler", "secret", "bulk", "--name", worker_name]


def _wrangler(argv: list[str], payload: str) -> int:
    """The right half of the pipe. BOTH streams inherited, as the twin leaves
    them: wrangler's own output is the entire visible result of a good run."""
    proc = subprocess.run(argv, input=payload, text=True, check=False)
    return proc.returncode


def main(argv: list[str]) -> int:
    del argv  # the twin parses nothing; extra arguments are ignored by both

    # ORDER IS OBSERVABLE: `require_cmd jq` runs first, so a run missing both binaries names jq, and both run BEFORE the three `:?` refusals.
    for tool in ("jq", "npx"):
        try:
            common.require_cmd(tool)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    env = read_env()

    for name, message in MISSING_MESSAGES:
        if not env.get(name, ""):
            # DIVERGENCE A: bash prefixes this with `<path>: line <n>: `.
            print(message, file=sys.stderr)
            return 1

    try:
        values = resolve(env)
        check_nonempty(values, env)
    except ScriptRefusalError as exc:
        for line in exc.lines:
            print(line, file=sys.stderr)
        return exc.code

    jq_status, payload = _jq(jq_argv(values))
    wrangler_status = _wrangler(wrangler_argv(env["WORKER_NAME"]), payload)

    # `set -o pipefail`: the rightmost non-zero status wins.
    return wrangler_status or jq_status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
