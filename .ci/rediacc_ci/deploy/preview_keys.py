#!/usr/bin/env python3
"""Generate a preview Worker's server secrets for ONE preview and push them, so no production secret reaches a pull-request job.

    PREVIEW_NAME=pv-<w>-<w>-<w> PYTHONPATH=.ci python3 -m rediacc_ci.deploy.preview_keys

agent/plans/PLAN-pr-path-ephemeral-credentials.md D3. `rediacc/console` is public and the deploy-preview job runs PR-controlled code, so the tunnel key, the session secret and the server API key of a preview are minted here for that preview and pushed to its Worker, and are never fetched from the Bitwarden store. A holder of one learns nothing about production, and a re-run of the job replaces the set.

WHAT IS GENERATED. A fresh X25519 pair (`ACCOUNT_X25519_PRIVATE_KEY`, `ACCOUNT_X25519_PUBLIC_KEY`: the tunnel key the CLI encrypts to), a session secret (`ACCOUNT_JWT_SECRET`) and a server API key (`ACCOUNT_SERVER_API_KEY`), both 64 characters of `rediacc_ci.core.account.random_secret`. The Worker's schema asks for 32 or more.

WHAT IS PASSED THROUGH. Three values that carry no production credential: `ACCOUNT_ED25519_PUBLIC_KEY` (public by design: every released renet embeds it), `ROOT_EMAIL` (an address, not a credential, optional in the Worker's schema) and the per-PR `CLOUDFLARE_TURNSTILE_SECRET_KEY` the create-widget step minted. A passed-through value that is empty is left out of the push. OUTBOUND MAIL IS OFF: no `AWS_SES_*` value is ever sent, and every one is optional in `private/account/src/types/env.ts`, so the Worker starts with the feature disabled (D3's mail-disabled branch; box W1 measures which routes then refuse).

HOW THEY TRAVEL. Values arrive in this process only, reach wrangler as one JSON object on the stdin of `wrangler secret bulk` (never argv, never a file) and leave it only through the public half: `GITHUB_OUTPUT` receives `x25519_public` and nothing else. Every line of wrangler output printed here is first redacted of every generated and passed-through value, and an error carries a name, never a value. One bulk call, because each `secret put` mints a Worker version and a new version on an assets-bound Worker disassociates the static assets the deploy just uploaded (the twin `set_preview_worker_secrets` documents it).

THE SMOKE TEST NEEDS NO SECRET OF THESE. The licence smoke reads the tunnel public key from the Worker itself, and the seed token it plants is a row the smoke job inserts and uses within that one job.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import typing

from rediacc_ci import log, paths
from rediacc_ci.core import account, common, wrangler
from rediacc_ci.deploy import deploy_signer, preview_name

SELF = "rediacc_ci.deploy.preview_keys"

NAME_ENV = "PREVIEW_NAME"
OUTPUT_ENV = "GITHUB_OUTPUT"

# Generated per preview, in the order of the bulk document.
GENERATED_NAMES = (
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_JWT_SECRET",
)
# (environment variable read, label in a refusal), read when set; none of them is a production credential (module docstring). The two-column shape is the one `check:ci-builder-env-contract` parses as this builder's reads.
KEYS: tuple[tuple[str, str], ...] = (
    ("ACCOUNT_ED25519_PUBLIC_KEY", "ed25519_public"),
    ("ROOT_EMAIL", "root_email"),
    ("CLOUDFLARE_TURNSTILE_SECRET_KEY", "turnstile_secret"),
)
PASSTHROUGH_NAMES = tuple(name for name, _label in KEYS)
# Always required, because the Worker's schema makes each non-optional.
REQUIRED_PASSTHROUGH = ("ACCOUNT_ED25519_PUBLIC_KEY",)
# Never sent: a name starting with one of these would hand the preview a production mail identity.
FORBIDDEN_PREFIXES = ("AWS_SES_",)

PUBLIC_OUTPUT = "x25519_public"

# () -> (private, public), base64 DER. The tests swap it for a fixed pair.
KeyGen = typing.Callable[[], "tuple[str, str]"]
# () -> a fresh secret string. The tests swap it for a counter.
SecretGen = typing.Callable[[], str]
# (argv, cwd, stdin) -> (rc, stdout, stderr). The tests swap it for a recording fake.
Pusher = typing.Callable[[list[str], "str", str], "tuple[int, str, str]"]


class RefusedError(Exception):
    """A run that must stop with exit 1. Its text never carries a secret value."""


@dataclasses.dataclass(frozen=True)
class Keys:
    x25519_private: str
    x25519_public: str
    api_key: str
    session_secret: str

    def values(self) -> dict[str, str]:
        return {
            "ACCOUNT_X25519_PRIVATE_KEY": self.x25519_private,
            "ACCOUNT_X25519_PUBLIC_KEY": self.x25519_public,
            "ACCOUNT_SERVER_API_KEY": self.api_key,
            "ACCOUNT_JWT_SECRET": self.session_secret,
        }


def generate_x25519() -> tuple[str, str]:
    private, public = account.keypair("x25519", strict=True)
    if not private or not public or private == public:
        raise RefusedError("%s: the X25519 key generation produced no key pair" % SELF)
    return private, public


def generate_secret() -> str:
    secret = account.random_secret(strict=True)
    if len(secret) < 32:
        raise RefusedError(
            "%s: the random secret generation produced fewer than 32 characters" % SELF
        )
    return secret


def generate(keygen: KeyGen = generate_x25519, secret: SecretGen = generate_secret) -> Keys:
    """One preview's secrets. The API key and the session secret are two draws, so they differ."""
    private, public = keygen()
    api_key = secret()
    session = secret()
    if api_key == session:
        raise RefusedError("%s: the server API key and the session secret came out equal" % SELF)
    return Keys(private, public, api_key, session)


def worker_name(name: str) -> str:
    """The preview Worker `name` names; anything but a `pv-<w>-<w>-<w>` word name (the `-signer` Worker included) is refused before a call."""
    if preview_name.is_preview_worker(name) and not name.endswith("-signer"):
        return name
    raise RefusedError(
        "%s: %s must be a preview Worker name (pv-<word>-<word>-<word>)" % (SELF, NAME_ENV)
    )


def bulk_document(keys: Keys, environ: typing.Mapping[str, str]) -> dict[str, str]:
    """The object handed to `wrangler secret bulk`: the generated set, then each non-empty pass-through. A required pass-through that is empty is refused by name."""
    labels = dict(KEYS)
    for name in REQUIRED_PASSTHROUGH:
        if not environ.get(name, ""):
            raise RefusedError(
                "%s: %s (%s) is empty; the Worker's schema rejects it on every request, so the preview is not deployed"
                % (SELF, name, labels[name])
            )
    document = dict(keys.values())
    for name in PASSTHROUGH_NAMES:
        value = environ.get(name, "")
        if value:
            document[name] = value
    for name in document:
        if name.startswith(FORBIDDEN_PREFIXES):
            raise RefusedError(
                "%s: %s is a production mail credential and is never pushed to a preview"
                % (SELF, name)
            )
    return document


def wrangler_argv(worker: str) -> list[str]:
    """`npx wrangler secret bulk --name <worker>`: the name only, so no value is on argv."""
    return [*wrangler.ARGV, "secret", "bulk", "--name", worker]


def worker_dir() -> str:
    """`workers/www`, the one directory whose `node_modules/.bin/wrangler` the deploy job installs; `wrangler.ARGV` resolves a local binary only."""
    return str(paths.repo_root() / "workers" / "www")


def run_wrangler(argv: list[str], cwd: str, stdin: str) -> tuple[int, str, str]:
    proc = subprocess.run(argv, input=stdin, cwd=cwd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def push(
    worker: str,
    document: dict[str, str],
    pusher: Pusher = run_wrangler,
    out: typing.TextIO | None = None,
) -> int:
    """One bulk call. The document is the call's stdin; its output is printed redacted of every value in it."""
    stream = out if out is not None else sys.stdout
    redact = deploy_signer.Redactor(document.values())
    rc, stdout, stderr = pusher(wrangler_argv(worker), worker_dir(), json.dumps(document))
    for text in (stdout, stderr):
        if text:
            stream.write(redact(text))
    return rc


def write_outputs(keys: Keys, environ: typing.Mapping[str, str]) -> None:
    """`x25519_public` to `GITHUB_OUTPUT`: the one value of this module that may leave the job."""
    target = environ.get(OUTPUT_ENV, "")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as fh:
        fh.write("%s=%s\n" % (PUBLIC_OUTPUT, keys.x25519_public))


def main(
    argv: list[str],
    environ: typing.Mapping[str, str] | None = None,
    keygen: KeyGen = generate_x25519,
    secret: SecretGen = generate_secret,
    pusher: Pusher = run_wrangler,
) -> int:
    refused = common.refuse_arguments(argv)
    if refused is not None:
        return refused
    env = dict(os.environ if environ is None else environ)
    try:
        worker = worker_name(env.get(NAME_ENV, ""))
        keys = generate(keygen, secret)
        document = bulk_document(keys, env)
    except RefusedError as exc:
        print(exc, file=sys.stderr)
        return 1
    rc = push(worker, document, pusher)
    if rc:
        print("%s: wrangler secret bulk failed (rc %d)" % (SELF, rc), file=sys.stderr)
        return rc
    write_outputs(keys, env)
    log.info(
        "Set %d generated and pass-through secrets on %s in one bulk call" % (len(document), worker)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
