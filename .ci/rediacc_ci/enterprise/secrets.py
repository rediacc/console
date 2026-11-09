"""Company secrets for an Enterprise company's account Worker (agent/plans/PLAN-enterprise-isolation.md D2).

WHAT A COMPANY GETS. Generated per company: the X25519 pair (a shared one would let one breached Worker open another company's captured request tunnel), `ACCOUNT_JWT_SECRET`, `ACCOUNT_CONFIG_SERVER_KEY` (stored durably, because losing it loses layer 3 of the config store), `ACCOUNT_SERVER_API_KEY` and `ACCOUNT_BACKUP_STORE_KEK`. Minted per company: an IAM user on the shared SES sender, allowed `ses:SendEmail` and `ses:SendRawEmail` only, and an R2 token scoped to object read and write on `backups-<company>`, pushed as R2's S3 pair (the token id and sha256 of its value, as rotation's `r2-keypair` shape does). Shared and handed in by the caller: the Ed25519 PUBLIC key, the Turnstile secret, the region's OTLP credentials, the SES region and sender, and `ROOT_EMAIL`. Absent, and refused if offered: the Ed25519 private key (the signer holds it), `FREE_LICENSE_HMAC_KEY` (a company issues no FREE licences), Stripe and every `SELLER_*` (contract billing lives outside). The shared pusher demands the FREE key (`set_account_worker_secrets.REQUIRED_NONEMPTY`), so a company has its own `COMPANY_REQUIRED`.

OPAQUE NAMES. A company is known outside its control row by `c<16 hex>`, drawn from the OS's randomness and never derived from the name: a hash of a guessable company name is reversed by a dictionary. Store entries are `<id>_<WORKER KEY>` in the separate enterprise bws project, the Cloudflare token is `enterprise-<id>-backups` and the IAM user `rediacc-ses-<id>`. The bucket and Worker names carry the label, as the Design's Shape fixes; they appear inside the Worker payload and in wrangler's `--name`, never in a store name.

NO VALUE IN ARGV, A LOG LINE OR AN EXCEPTION. Values reach wrangler as one JSON document on its STDIN through `set_account_worker_secrets.wrangler_argv`, and wrangler's output is captured, not echoed, since it can name the Worker. The bws write goes through `bws_env.write_secret`, whose request rides stdin. Every refusal names keys and the opaque id only. A seam that raises is re-raised as `SecretsError` carrying the step and the exception's TYPE, `from None`, because an external error text may quote what it was handed; the production adapters translate their libraries' own errors the same way.

DURABLE BEFORE PUSHED, AND RESUMABLE. Each generated or minted value is written to the store before the push, and a rerun reuses whatever the store already holds, so `enterprise add` resumes without regenerating the config server key or minting a second token. Half a pair in the store (one X25519 half, one half of an S3 or SES pair) is refused rather than completed, because the missing half cannot be re-derived.

EVERY EXTERNAL CALL IS A SEAM. `provision` takes a `Store`, a `Minter` and a `push` callable; the production adapters (`BwsStore`, `CloudflareMinter`, `IamMinter`, `wrangler_push`) take their transports as arguments too, so `tests/test_enterprise_secrets.py` drives all of it with fakes and nothing reaches bws, Cloudflare or AWS.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from rediacc_ci.core import awscli, bws_env
from rediacc_ci.deploy import set_account_worker_secrets
from rediacc_ci.enterprise import names
from rediacc_ci.ops import cf_auth

RandomBytes = Callable[[int], bytes]

# The opaque id: `c` and 16 lowercase hex characters (64 random bits). Inside the leak gate's `c[0-9a-f]{8,}` and the control schema's CHECK.
COMPANY_ID = re.compile(r"c[0-9a-f]{16}")
STORE_NAME = re.compile(r"c[0-9a-f]{16}_[A-Z][A-Z0-9_]*")
_WORKER_KEY = re.compile(r"[A-Z][A-Z0-9_]*")

X25519_PKCS8_PREFIX = bytes.fromhex("302e020100300506032b656e04220420")
X25519_SPKI_PREFIX = bytes.fromhex("302a300506032b656e032100")

# Generated here, one fresh value per company.
GENERATED: tuple[str, ...] = (
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_JWT_SECRET",
    "ACCOUNT_CONFIG_SERVER_KEY",
    "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_BACKUP_STORE_KEK",
)
X25519_PAIR = ("ACCOUNT_X25519_PRIVATE_KEY", "ACCOUNT_X25519_PUBLIC_KEY")
SES_PAIR = ("AWS_SES_ACCESS_KEY_ID", "AWS_SES_SECRET_ACCESS_KEY")
BACKUP_PAIR = ("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY")
MINTED: tuple[str, ...] = (*SES_PAIR, *BACKUP_PAIR)
STORED: tuple[str, ...] = (*GENERATED, *MINTED)

# Shared values the caller hands in, already fanned in for the company's region.
SHARED: tuple[str, ...] = (
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY",
    "OBS_OTLP_CREDENTIALS",
    "AWS_SES_REGION",
    "AWS_SES_FROM",
    "AWS_SES_CONFIGURATION_SET",
    "ROOT_EMAIL",
)
# Computed from the company, not secret.
DERIVED: tuple[str, ...] = ("ACCOUNT_BACKUP_S3_ENDPOINT", "ACCOUNT_BACKUP_S3_BUCKET")

PAYLOAD_KEYS: tuple[str, ...] = (*GENERATED, *MINTED, *SHARED, *DERIVED)

# Every payload key that must be non-empty. AWS_SES_FROM and AWS_SES_CONFIGURATION_SET stay optional, as on the shared tier.
COMPANY_REQUIRED: tuple[str, ...] = tuple(
    k for k in PAYLOAD_KEYS if k not in ("AWS_SES_FROM", "AWS_SES_CONFIGURATION_SET")
)

# Never on a company Worker.
FORBIDDEN: tuple[str, ...] = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "FREE_LICENSE_HMAC_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    *(k for k, _v, _s in set_account_worker_secrets.KEYS if k.startswith("SELLER_")),
)

OTLP_KEY = "OBS_OTLP_CREDENTIALS"
STORE_NOTE = "enterprise company secret; generated by rediacc_ci.enterprise.secrets"
R2_BUCKET_SCOPE = "com.cloudflare.edge.r2.bucket"
R2_BUCKET_PERMISSIONS = (
    "Workers R2 Storage Bucket Item Read",
    "Workers R2 Storage Bucket Item Write",
)

# What a seam may raise. Anything else is a bug here and propagates as itself.
SEAM_ERRORS = (
    OSError,
    RuntimeError,
    ValueError,
    LookupError,
    TypeError,
    AttributeError,
    subprocess.SubprocessError,
)


class SecretsError(RuntimeError):
    """A refusal or a failed step. The message names keys and the opaque id, never a value or the company label."""


# --- opaque ids and names --------------------------------------------------------


def new_company_id(random_bytes: RandomBytes = os.urandom) -> str:
    return "c" + random_bytes(8).hex()


def _check_id(company_id: str) -> str:
    if not isinstance(company_id, str) or not COMPANY_ID.fullmatch(company_id):
        raise SecretsError("not an opaque company id (c and 16 lowercase hex characters)")
    return company_id


def store_name(company_id: str, key: str) -> str:
    """`<id>_<KEY>`, the name a company secret is stored under in the enterprise bws project."""
    _check_id(company_id)
    if not _WORKER_KEY.fullmatch(key):
        raise SecretsError("store key %r is not an UPPER_SNAKE Worker key" % key)
    return "%s_%s" % (company_id, key)


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    region: str
    cf_account_id: str
    r2_jurisdiction: str | None = None

    def __post_init__(self) -> None:
        _check_id(self.id)
        try:
            names.check(self.name)
        except names.CompanyNameError:
            raise SecretsError("company %s has an unusable name" % self.id) from None

    @property
    def worker(self) -> str:
        return "account-%s" % self.name

    @property
    def backup_bucket(self) -> str:
        return "backups-%s" % self.name

    @property
    def backup_endpoint(self) -> str:
        jurisdiction = "%s." % self.r2_jurisdiction if self.r2_jurisdiction else ""
        return "https://%s.%sr2.cloudflarestorage.com" % (self.cf_account_id, jurisdiction)

    @property
    def bucket_resource(self) -> str:
        return "%s.%s_%s_%s" % (
            R2_BUCKET_SCOPE,
            self.cf_account_id,
            self.r2_jurisdiction or "default",
            self.backup_bucket,
        )


def r2_token_name(company: Company) -> str:
    return "enterprise-%s-backups" % company.id


def ses_user_name(company: Company) -> str:
    return "rediacc-ses-%s" % company.id


# --- generation ------------------------------------------------------------------

_P = 2**255 - 19
_A24 = 121665


def x25519_public(private: bytes) -> bytes:
    """The X25519 public key of a 32-byte private scalar (RFC 7748 section 5, base point 9)."""
    if len(private) != 32:
        raise SecretsError("an X25519 private key is 32 bytes")
    k = bytearray(private)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    scalar = int.from_bytes(k, "little")
    x1, x2, z2, x3, z3, swap = 9, 1, 0, 9, 1, 0
    for t in reversed(range(255)):
        bit = (scalar >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a, b = (x2 + z2) % _P, (x2 - z2) % _P
        aa, bb = a * a % _P, b * b % _P
        e = (aa - bb) % _P
        c, d = (x3 + z3) % _P, (x3 - z3) % _P
        da, cb = d * a % _P, c * b % _P
        x3 = (da + cb) ** 2 % _P
        z3 = x1 * (da - cb) ** 2 % _P
        x2 = aa * bb % _P
        z2 = e * (aa + _A24 * e) % _P
    if swap:
        x2, z2 = x3, z3
    return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, "little")


def _token(random_bytes: RandomBytes) -> str:
    """48 random bytes, base64url without padding: 64 characters, over every `min(32)` in the Worker schema."""
    return base64.urlsafe_b64encode(random_bytes(48)).rstrip(b"=").decode("ascii")


def generate(random_bytes: RandomBytes = os.urandom) -> dict[str, str]:
    """A fresh value for every GENERATED key. The X25519 pair is base64 PKCS8 and SPKI, the forms `importX25519PrivateKey` and the published key list read."""
    private = random_bytes(32)
    values = {
        "ACCOUNT_X25519_PRIVATE_KEY": base64.b64encode(X25519_PKCS8_PREFIX + private).decode(),
        "ACCOUNT_X25519_PUBLIC_KEY": base64.b64encode(
            X25519_SPKI_PREFIX + x25519_public(private)
        ).decode(),
    }
    for key in GENERATED:
        if key not in values:
            values[key] = _token(random_bytes)
    return values


def shared_from_env(env: Mapping[str, str], suffix: str) -> dict[str, str]:
    """The SHARED keys from an environment, the OTLP credential read as `OBS_OTLP_CREDENTIALS_<SUFFIX>`. Anything else in `env` is ignored."""
    out = {k: env[k] for k in SHARED if k != OTLP_KEY and k in env}
    regional = "%s_%s" % (OTLP_KEY, suffix)
    if regional in env:
        out[OTLP_KEY] = env[regional]
    return out


# --- seams -----------------------------------------------------------------------


class Store(Protocol):
    def read(self, names: Sequence[str]) -> dict[str, str]: ...

    def create(self, name: str, value: str) -> None: ...


class Minter(Protocol):
    def r2_bucket_token(self, token_name: str, bucket_resource: str) -> tuple[str, str]: ...

    def ses_user(self, user_name: str) -> tuple[str, str]: ...


Push = Callable[[list[str], str], int]


def _step(what: str, fn: Callable[..., Any], *args: Any) -> Any:
    """Run one seam call; a failure keeps only its type, because its text may quote a value."""
    try:
        return fn(*args)
    except SecretsError:
        raise
    except SEAM_ERRORS as exc:
        raise SecretsError("%s failed (%s)" % (what, type(exc).__name__)) from None


# --- provision -------------------------------------------------------------------


@dataclass
class Report:
    company_id: str
    created: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    pushed: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        return [
            "company %s: %d secret(s) created, %d reused, %d key(s) pushed"
            % (self.company_id, len(self.created), len(self.reused), len(self.pushed)),
            *("  created %s" % k for k in self.created),
            *("  reused %s" % k for k in self.reused),
        ]


def check_shared(shared: Mapping[str, str]) -> None:
    """Refuse a forbidden, company-owned or unknown key in the shared set. Names only."""
    forbidden = sorted(k for k in shared if k in FORBIDDEN)
    if forbidden:
        raise SecretsError(
            "refused on a company Worker: %s (the signing key, FREE licences and billing stay off it)"
            % ", ".join(forbidden)
        )
    owned = sorted(k for k in shared if k in STORED)
    if owned:
        raise SecretsError("generated or minted per company, not shared: %s" % ", ".join(owned))
    unknown = sorted(k for k in shared if k not in SHARED)
    if unknown:
        raise SecretsError("not a shared company key: %s" % ", ".join(unknown))


def _refuse_missing(payload: Mapping[str, str], keys: Sequence[str], company_id: str) -> None:
    missing = [k for k in keys if not payload.get(k)]
    if missing:
        raise SecretsError(
            "company %s: missing or empty required secret(s): %s" % (company_id, ", ".join(missing))
        )


def check_required(payload: Mapping[str, str], company_id: str) -> None:
    """Every COMPANY_REQUIRED key non-empty, and the OTLP credential in the shape the Worker parses."""
    _refuse_missing(payload, COMPANY_REQUIRED, company_id)
    try:
        otlp = json.loads(payload[OTLP_KEY])
        shaped = isinstance(otlp.get("user"), str) and isinstance(otlp.get("pass"), str)
    except (ValueError, AttributeError):
        shaped = False
    if not shaped:
        raise SecretsError(
            'company %s: %s is not a JSON {"user","pass"} object' % (company_id, OTLP_KEY)
        )


def _check_pairs(existing: Mapping[str, str], company_id: str) -> None:
    for pair in (X25519_PAIR, SES_PAIR, BACKUP_PAIR):
        held = [k for k in pair if k in existing]
        if len(held) == 1:
            raise SecretsError(
                "company %s: the store holds %s without its other half; it cannot be re-derived, so nothing is completed"
                % (company_id, held[0])
            )


def provision(
    company: Company,
    shared: Mapping[str, str],
    *,
    store: Store,
    minter: Minter,
    push: Push,
    random_bytes: RandomBytes = os.urandom,
) -> Report:
    """Generate, store, mint and push one company's secrets; reuse what the store already holds. Raises SecretsError, value-free."""
    cid = company.id
    check_shared(shared)
    base = {k: shared.get(k, "") for k in SHARED}
    base["ACCOUNT_BACKUP_S3_ENDPOINT"] = company.backup_endpoint
    base["ACCOUNT_BACKUP_S3_BUCKET"] = company.backup_bucket
    # The caller's half is checked before anything is written or minted.
    _refuse_missing(base, [k for k in COMPANY_REQUIRED if k in base], cid)

    by_key = {k: store_name(cid, k) for k in STORED}
    held = _step("reading the store", store.read, list(by_key.values()))
    existing = {k: held[n] for k, n in by_key.items() if held.get(n)}
    _check_pairs(existing, cid)

    report = Report(company_id=cid)
    values: dict[str, str] = {}

    def keep(key: str, value: str) -> None:
        _step("storing %s" % by_key[key], store.create, by_key[key], value)
        values[key] = value
        report.created.append(key)

    def reuse(keys: Sequence[str]) -> None:
        values.update({k: existing[k] for k in keys})
        report.reused.extend(keys)

    fresh = generate(random_bytes)
    for key in GENERATED:
        if key in existing:
            reuse([key])
        else:
            keep(key, fresh[key])

    if all(k in existing for k in SES_PAIR):
        reuse(SES_PAIR)
    else:
        key_id, secret = _step("minting the SES user", minter.ses_user, ses_user_name(company))
        keep(SES_PAIR[0], key_id)
        keep(SES_PAIR[1], secret)

    if all(k in existing for k in BACKUP_PAIR):
        reuse(BACKUP_PAIR)
    else:
        token_id, token_value = _step(
            "minting the backup token",
            minter.r2_bucket_token,
            r2_token_name(company),
            company.bucket_resource,
        )
        keep(BACKUP_PAIR[0], token_id)
        keep(BACKUP_PAIR[1], hashlib.sha256(token_value.encode()).hexdigest())

    merged = {**values, **base}
    payload = {k: merged[k] for k in PAYLOAD_KEYS}
    check_required(payload, cid)

    rc = _step(
        "pushing to the company Worker",
        push,
        set_account_worker_secrets.wrangler_argv(company.worker),
        json.dumps(payload),
    )
    if rc != 0:
        raise SecretsError(
            "company %s: wrangler secret bulk exited %d; its output is withheld because it names the Worker"
            % (cid, rc)
        )
    report.pushed = list(PAYLOAD_KEYS)
    return report


# --- production adapters ---------------------------------------------------------


class BwsStore:
    """The enterprise bws project. `list_rows` returns `bws secret list` rows; `write` is `bws_env.write_secret` bound to the account dir and token env, returning None or a value-free reason."""

    def __init__(
        self,
        project_id: str,
        *,
        list_rows: Callable[[], list[dict]],
        write: Callable[[dict], str | None],
    ) -> None:
        if not project_id:
            raise SecretsError(
                "no enterprise bws project id; company secrets never go to the shared project"
            )
        self.project_id = project_id
        self._list = list_rows
        self._write = write

    def read(self, names: Sequence[str]) -> dict[str, str]:
        wanted = set(names)
        out: dict[str, str] = {}
        for row in self._list():
            key = row.get("key")
            if key in wanted and row.get("projectId") == self.project_id and key not in out:
                out[key] = row.get("value") or ""
        return out

    def create(self, name: str, value: str) -> None:
        if not STORE_NAME.fullmatch(name):
            raise SecretsError("refusing a non-opaque store name")
        failure = self._write(
            {
                "op": "create",
                "key": name,
                "value": value,
                "note": STORE_NOTE,
                "projectIds": [self.project_id],
            }
        )
        if failure is not None:
            raise SecretsError("creating %s failed (%s)" % (name, failure))

    @classmethod
    def from_env(cls, project_id: str, env: dict | None = None) -> BwsStore:
        """The live store: `bws secret list` for reads and bws-write.ts (value on stdin) for creates."""
        try:
            environ = bws_env.with_token(env)
        except bws_env.RefusalError:
            raise SecretsError("no bws access token") from None
        binary = bws_env.binary(environ)
        if not binary:
            raise SecretsError("no bws binary")
        account = os.path.join(bws_env.root(environ), *bws_env.WRITER_DIR_PARTS)

        def list_rows() -> list[dict]:
            try:
                return bws_env.listing(binary, environ)
            except bws_env.RefusalError:
                raise SecretsError("bws secret list failed") from None

        return cls(
            project_id,
            list_rows=list_rows,
            write=lambda request: bws_env.write_secret(account, request, environ),
        )


Http = Callable[..., dict]


class CloudflareMinter:
    """Mints the bucket-scoped R2 token. `http(method, path, body=None) -> dict` speaks the Cloudflare API under an admin credential."""

    def __init__(self, *, http: Http) -> None:
        self._http = http

    def _group_ids(self) -> list[str]:
        groups = self._http("GET", "/user/tokens/permission_groups").get("result") or []
        ids: list[str] = []
        for wanted in R2_BUCKET_PERMISSIONS:
            hits = [
                str(g.get("id"))
                for g in groups
                if isinstance(g, dict)
                and g.get("name") == wanted
                and R2_BUCKET_SCOPE in (g.get("scopes") or [])
            ]
            if len(hits) != 1:
                raise SecretsError("permission group %r not resolvable" % wanted)
            ids.append(hits[0])
        return ids

    def r2_bucket_token(self, token_name: str, bucket_resource: str) -> tuple[str, str]:
        payload = {
            "name": token_name,
            "policies": [
                {
                    "effect": "allow",
                    "resources": {bucket_resource: "*"},
                    "permission_groups": [{"id": g} for g in self._group_ids()],
                }
            ],
        }
        created = self._http("POST", "/user/tokens", json.dumps(payload)).get("result")
        token_id = created.get("id") if isinstance(created, dict) else None
        value = created.get("value") if isinstance(created, dict) else None
        if not token_id or not value:
            raise SecretsError("creating token %s failed" % token_name)
        return str(token_id), str(value)

    @classmethod
    def from_headers(cls, headers: list[str]) -> CloudflareMinter:
        """The live minter over `cf_auth.curl_json`, which moves the auth headers to curl's stdin."""

        def http(method: str, path: str, body: str | None = None) -> dict:
            try:
                return cf_auth.curl_json(method, cf_auth.CF_API_BASE + path, headers, body)
            except cf_auth.CfAuthError:
                raise SecretsError("Cloudflare %s %s failed" % (method, path)) from None

        return cls(http=http)


Aws = Callable[[list[str]], tuple[int, str]]


class IamMinter:
    """Creates a send-only IAM user on the shared SES sender. `aws(argv) -> (rc, stdout)`; no secret is ever an argument, and the secret key arrives on stdout."""

    def __init__(self, *, aws: Aws, ses_region: str, from_domain: str) -> None:
        self._aws = aws
        self.ses_region = ses_region
        self.from_domain = from_domain

    def policy(self) -> str:
        return json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["ses:SendEmail", "ses:SendRawEmail"],
                        "Resource": "*",
                        "Condition": {
                            "StringEquals": {"aws:RequestedRegion": self.ses_region},
                            "StringLike": {"ses:FromAddress": "*@%s" % self.from_domain},
                        },
                    }
                ],
            }
        )

    def _call(self, argv: list[str]) -> str:
        rc, out = self._aws(argv)
        if rc != 0:
            raise SecretsError("aws iam %s exited %d; its output is withheld" % (argv[2], rc))
        return out

    def ses_user(self, user_name: str) -> tuple[str, str]:
        user = ["--user-name", user_name]
        self._call(["aws", "iam", "create-user", *user])
        self._call(
            [
                *("aws", "iam", "put-user-policy", *user),
                *("--policy-name", "ses-send-only", "--policy-document", self.policy()),
            ]
        )
        out = self._call(["aws", "iam", "create-access-key", *user, "--output", "json"])
        try:
            key = json.loads(out)["AccessKey"]
            return str(key["AccessKeyId"]), str(key["SecretAccessKey"])
        except (ValueError, KeyError, TypeError):
            raise SecretsError("aws iam create-access-key answered an unexpected shape") from None

    @staticmethod
    def live_aws(argv: list[str]) -> tuple[int, str]:
        """The live transport: the pinned aws CLI, stdout captured, stderr captured and dropped."""
        proc = awscli.run(argv, capture_output=True, text=True)
        return proc.returncode, proc.stdout


def wrangler_push(
    argv: list[str], payload: str, runner: Callable[..., Any] = subprocess.run
) -> int:
    """`wrangler secret bulk` with the document on stdin and both streams captured, never echoed."""
    proc = runner(argv, input=payload, capture_output=True, text=True, check=False)
    return int(proc.returncode)
