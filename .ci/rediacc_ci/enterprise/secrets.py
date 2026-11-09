"""Company secrets for an Enterprise company's account Worker (agent/plans/PLAN-enterprise-isolation.md D2).

WHAT A COMPANY GETS. Generated per company: the X25519 pair (a shared one would let one breached Worker open another company's captured request tunnel), `ACCOUNT_JWT_SECRET`, `ACCOUNT_CONFIG_SERVER_KEY` (stored durably, because losing it loses layer 3 of the config store), `ACCOUNT_SERVER_API_KEY` and `ACCOUNT_BACKUP_STORE_KEK`. Minted per company: an IAM user on the shared SES sender, allowed `ses:SendEmail` and `ses:SendRawEmail` only, and an R2 token scoped to object read and write on `backups-<company>`, pushed as R2's S3 pair (the token id and sha256 of its value, as rotation's `r2-keypair` shape does). Shared and handed in by the caller: the Ed25519 PUBLIC key, the Turnstile secret, the region's OTLP credentials, the SES region and sender, and `ROOT_EMAIL`. Absent, and refused if offered: the Ed25519 private key (the signer holds it), `FREE_LICENSE_HMAC_KEY` (a company issues no FREE licences), Stripe and every `SELLER_*` (contract billing lives outside). The shared pusher demands the FREE key (`set_account_worker_secrets.REQUIRED_NONEMPTY`), so a company has its own `COMPANY_REQUIRED`.

OPAQUE NAMES. A company is known outside its control row by `c<16 hex>`, drawn from the OS's randomness and never derived from the name: a hash of a guessable company name is reversed by a dictionary. Store entries are `<id>_<WORKER KEY>` in the separate enterprise bws project, the Cloudflare token is `enterprise-<id>-backups` and the IAM user `rediacc-ses-<id>`. The bucket and Worker names carry the label, as the Design's Shape fixes; they appear inside the Worker payload and in wrangler's `--name`, never in a store name.

NO VALUE IN ARGV, A LOG LINE OR AN EXCEPTION. Values reach wrangler as one JSON document on its STDIN through `set_account_worker_secrets.wrangler_argv`, and wrangler's output is captured, not echoed, since it can name the Worker. The bws write goes through `bws_env.write_secret`, whose request rides stdin. Every refusal names keys and the opaque id only. A seam that raises is re-raised as `SecretsError` carrying the step and the exception's TYPE, because an external error text may quote what it was handed. Every `SecretsError` that translates another exception is raised AFTER the except block has closed, so it carries neither `__cause__` nor `__context__`: `from None` inside the block only hides the original from the printed traceback, and the original stays reachable as `__context__`. The production adapters translate their libraries' own errors the same way.

DURABLE BEFORE PUSHED, AND RESUMABLE. Each generated or minted value is written to the store before the push, and a rerun reuses whatever the store already holds, so `enterprise add` resumes without regenerating the config server key or minting a second token. Each pair (X25519, SES, R2's S3 pair) is ONE store entry, `<id>_<PAIR>` holding a JSON object of both halves, so a crash between two writes cannot leave half a pair; an entry missing a half is refused, because the missing half cannot be re-derived. The minters resume too: the IAM minter continues from a user an earlier run created, and both minters revoke what an earlier run minted but never stored (the IAM user's access keys, the same-named Cloudflare token), because the store is the only place a minted secret can be recovered from and the minters run only when the store holds no pair. Every caller-supplied value, the OTLP credential's JSON shape included, is checked before the store is read, anything is minted or anything is written.

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
OWNED: tuple[str, ...] = (*GENERATED, *MINTED)

# Each pair is one store entry holding both halves as a JSON object, so it is written atomically.
PAIRS: dict[str, tuple[str, str]] = {
    "ACCOUNT_X25519_KEYPAIR": X25519_PAIR,
    "AWS_SES_KEYPAIR": SES_PAIR,
    "ACCOUNT_BACKUP_S3_KEYPAIR": BACKUP_PAIR,
}
SINGLES: tuple[str, ...] = tuple(k for k in GENERATED if k not in X25519_PAIR)
# The store entry keys: one per unpaired generated secret, one per pair.
STORED: tuple[str, ...] = (*SINGLES, *PAIRS)

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
            usable = True
        except names.CompanyNameError:
            usable = False
        if not usable:
            raise SecretsError("company %s has an unusable name" % self.id)

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
    """Run one seam call; a failure keeps only its type, because its text may quote a value. Raised outside the except block, so neither `__cause__` nor `__context__` holds the seam exception."""
    try:
        return fn(*args)
    except SecretsError:
        raise
    except SEAM_ERRORS as exc:
        failed = type(exc).__name__
    raise SecretsError("%s failed (%s)" % (what, failed))


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
    owned = sorted(k for k in shared if k in OWNED or k in STORED)
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


def check_otlp(value: str, company_id: str) -> None:
    """The OTLP credential in the shape the Worker parses: a JSON object with string `user` and `pass`."""
    try:
        otlp = json.loads(value)
        shaped = isinstance(otlp.get("user"), str) and isinstance(otlp.get("pass"), str)
    except (ValueError, AttributeError):
        shaped = False
    if not shaped:
        raise SecretsError(
            'company %s: %s is not a JSON {"user","pass"} object' % (company_id, OTLP_KEY)
        )


def check_required(payload: Mapping[str, str], company_id: str) -> None:
    """Every COMPANY_REQUIRED key non-empty, and the OTLP credential in the shape the Worker parses."""
    _refuse_missing(payload, COMPANY_REQUIRED, company_id)
    check_otlp(payload[OTLP_KEY], company_id)


def _unpack_pair(entry: str, raw: str, company_id: str) -> dict[str, str]:
    """A pair entry's two halves, or a value-free refusal naming the entry."""
    halves = PAIRS[entry]
    try:
        held = json.loads(raw)
        whole = (
            isinstance(held, dict)
            and set(held) == set(halves)
            and all(isinstance(held[k], str) and held[k] for k in halves)
        )
    except ValueError:
        whole = False
    if not whole:
        raise SecretsError(
            "company %s: the store entry %s is not both halves of its pair; the missing half cannot be re-derived, so nothing is completed"
            % (company_id, entry)
        )
    return {k: held[k] for k in halves}


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
    # Every caller-supplied check runs before the store is read, anything is minted or anything is written.
    _refuse_missing(base, [k for k in COMPANY_REQUIRED if k in base], cid)
    check_otlp(base[OTLP_KEY], cid)

    by_entry = {k: store_name(cid, k) for k in STORED}
    held = _step("reading the store", store.read, list(by_entry.values()))
    existing = {k: held[n] for k, n in by_entry.items() if held.get(n)}
    pairs = {k: _unpack_pair(k, existing[k], cid) for k in PAIRS if k in existing}

    report = Report(company_id=cid)
    values: dict[str, str] = {}

    def keep(entry: str, value: str | dict[str, str]) -> None:
        """Store one entry; a pair goes in as one JSON object, so it is never half written."""
        raw = json.dumps(value, sort_keys=True) if isinstance(value, dict) else value
        _step("storing %s" % by_entry[entry], store.create, by_entry[entry], raw)
        values.update(value if isinstance(value, dict) else {entry: value})
        report.created.append(entry)

    def reuse(entry: str) -> None:
        values.update(pairs[entry] if entry in PAIRS else {entry: existing[entry]})
        report.reused.append(entry)

    fresh = generate(random_bytes)
    for entry in SINGLES:
        if entry in existing:
            reuse(entry)
        else:
            keep(entry, fresh[entry])

    if "ACCOUNT_X25519_KEYPAIR" in pairs:
        reuse("ACCOUNT_X25519_KEYPAIR")
    else:
        keep("ACCOUNT_X25519_KEYPAIR", {k: fresh[k] for k in X25519_PAIR})

    if "AWS_SES_KEYPAIR" in pairs:
        reuse("AWS_SES_KEYPAIR")
    else:
        key_id, secret = _step("minting the SES user", minter.ses_user, ses_user_name(company))
        keep("AWS_SES_KEYPAIR", dict(zip(SES_PAIR, (key_id, secret), strict=True)))

    if "ACCOUNT_BACKUP_S3_KEYPAIR" in pairs:
        reuse("ACCOUNT_BACKUP_S3_KEYPAIR")
    else:
        token_id, token_value = _step(
            "minting the backup token",
            minter.r2_bucket_token,
            r2_token_name(company),
            company.bucket_resource,
        )
        secret_key = hashlib.sha256(token_value.encode()).hexdigest()
        keep(
            "ACCOUNT_BACKUP_S3_KEYPAIR", dict(zip(BACKUP_PAIR, (token_id, secret_key), strict=True))
        )

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
            environ = None
        if environ is None:
            raise SecretsError("no bws access token")
        binary = bws_env.binary(environ)
        if not binary:
            raise SecretsError("no bws binary")
        account = os.path.join(bws_env.root(environ), *bws_env.WRITER_DIR_PARTS)

        def list_rows() -> list[dict]:
            try:
                return bws_env.listing(binary, environ)
            except bws_env.RefusalError:
                pass
            raise SecretsError("bws secret list failed")

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

    def _revoke_named(self, token_name: str) -> None:
        """Delete every token already named `token_name`: one an earlier run minted but never stored, whose value is lost."""
        stale: list[str] = []
        page, pages = 1, 1
        while page <= pages:
            answer = self._http("GET", "/user/tokens?page=%d&per_page=50" % page)
            rows = answer.get("result")
            if not isinstance(rows, list):
                raise SecretsError("listing tokens before minting %s failed" % token_name)
            stale += [
                str(r["id"]) for r in rows if isinstance(r, dict) and r.get("name") == token_name
            ]
            info = answer.get("result_info")
            pages = int(info.get("total_pages") or 1) if isinstance(info, dict) else 1
            page += 1
        for token_id in stale:
            self._http("DELETE", "/user/tokens/%s" % token_id)

    def r2_bucket_token(self, token_name: str, bucket_resource: str) -> tuple[str, str]:
        self._revoke_named(token_name)
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
                pass
            raise SecretsError("Cloudflare %s %s failed" % (method, path))

        return cls(http=http)


Aws = Callable[[list[str]], tuple[int, str]]


class IamMinter:
    """Creates a send-only IAM user on the shared SES sender. `aws(argv) -> (rc, stdout)`; no secret is ever an argument, and the secret key arrives on stdout.

    Resumable: a user an earlier run created is reused, the policy put is an overwrite, and every access key the user already holds is deleted before the new one is created. `provision` calls `ses_user` only when the store holds no SES pair, so any such key is one the store never received: its secret is lost, and leaving it live would leave an unrecoverable credential behind (and IAM's two-key limit would block the mint).
    """

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

    def _exists(self, user: list[str]) -> bool:
        rc, _out = self._aws([awscli.AWS, "iam", "get-user", *user, "--output", "json"])
        return rc == 0

    def _key_ids(self, user: list[str]) -> list[str]:
        out = self._call([awscli.AWS, "iam", "list-access-keys", *user, "--output", "json"])
        try:
            ids = [str(k["AccessKeyId"]) for k in json.loads(out)["AccessKeyMetadata"]]
        except (ValueError, KeyError, TypeError):
            ids = None
        if ids is None:
            raise SecretsError("aws iam list-access-keys answered an unexpected shape")
        return ids

    def ses_user(self, user_name: str) -> tuple[str, str]:
        user = ["--user-name", user_name]
        if not self._exists(user):
            self._call([awscli.AWS, "iam", "create-user", *user])
        self._call(
            [
                *(awscli.AWS, "iam", "put-user-policy", *user),
                *("--policy-name", "ses-send-only", "--policy-document", self.policy()),
            ]
        )
        for key_id in self._key_ids(user):
            self._call([awscli.AWS, "iam", "delete-access-key", *user, "--access-key-id", key_id])
        out = self._call([awscli.AWS, "iam", "create-access-key", *user, "--output", "json"])
        try:
            key = json.loads(out)["AccessKey"]
            pair = (str(key["AccessKeyId"]), str(key["SecretAccessKey"]))
        except (ValueError, KeyError, TypeError):
            pair = None
        if pair is None:
            raise SecretsError("aws iam create-access-key answered an unexpected shape")
        return pair

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
