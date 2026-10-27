#!/usr/bin/env python3
"""Mirror one remote config store from a stable account database into its edge twin, at the database level: same CEK, same password and recovery slots (worklist #046d4339, operator ruling ASKED:2026-10-27T09:45Z).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.mirror_config_store --from eu-stable --to eu-edge --list-stores
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.mirror_config_store --from eu-stable --to eu-edge --store <id> [--dry-run]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.mirror_config_store --from eu-stable --to eu-edge --store <id> --apply --i-understand-edge-write

WHY IT WORKS. A key slot wraps the CEK under `deriveWrappingKey(slotSecret, serverSecret)` (packages/shared/src/config-crypto/cek.ts, slots.ts), and `serverSecret` is the store's own `config_stores.server_secret`. Copying the store row and the slot rows byte for byte therefore lets the same master password or recovery code unlock the edge copy. The blobs are copied by their recorded `r2_key`, and the envelope v3 AAD binds `(storeId, configId, teamId, version, sdkEpoch)`, so those ids are kept; the operator's user id may be remapped.

THE MIRROR IS A FORK. Nothing syncs afterwards: a push to either side diverges them.

WHAT IS COPIED. Verbatim: `config_stores` (but `require_passkey` is written 0 on edge, operator answer ASKED:2026-10-27T10:35Z), `config_entries` and `config_versions`. Filtered: the operator's `config_key_slots` of method password and recovery, and the operator's `config_user_identities` with every passkey column cleared. PASSKEYS DO NOT CARRY OVER: the WebAuthn RP ID is the stable host on stable and the edge host on edge, so a stable passkey can never sign in on edge. Identity rows: the organization, its live subscriptions (status active, grace or inactive and not expired), the operator's org membership, the teams the entries use and the operator's memberships of them. The OPERATOR is the org owner; no other member's user row, slots or identity is copied, and the plan names them by count only. Never copied: `config_tokens`, `config_executor_grants`, `config_cek_handoffs`, `config_cek_rotations`. A `config_versions.created_by_user_id` that names another member is written NULL.

IDENTITY. Case A: no edge user has the operator's `email_hash`, so the user row is copied with the same id. Case B: edge user X has it, so the operator's id is rewritten to X in `config_key_slots.user_id`, `config_user_identities.user_id`, `config_versions.created_by_user_id`, `org_memberships.user_id`, `team_memberships.user_id` and `organizations.owner_user_id`.

REUSE ON MATCH, REFUSE ON CONFLICT (the identity tables). An edge D1 once cloned from stable already holds the operator's org, subscription and memberships under the same ids. An edge row of `organizations`, `subscriptions`, `org_memberships`, `teams`, `team_memberships` or `users` with the plan's id is REUSED, never updated, when its identity columns match (`IDENTITY_MATCH`; user ids compared after the case-B remap; a user matches on `email_hash`), and the run refuses, naming the table and column, when one differs. A unique key (`IDENTITY_UNIQUE`) held under another id refuses too. A reused subscription that is not live on edge is printed as a note. The store's own rows (`config_stores`, `config_entries`, `config_versions`, `config_key_slots`, `config_user_identities`) refuse on any collision.

PRE-CHECKS, each one refusing the run: a pending CEK rotation; an operator with no password or recovery slot at the store's current CEK generation; a `CONFIG_SERVER_KEY` secret present on one Worker and absent on the other (it encrypts `server_recoverable_org_passphrase`, falling back to a constant, config.service.ts getServerEncryptionKey; the check reads secret NAMES through `prune_worker_secrets.survey`, where the name shows as an extra because no deploy pushes it); a stable `d1_migrations` entry edge lacks, a stable column edge lacks, or an edge-only NOT NULL column with no default; an edge row already holding the store id, a store for the org, or an entry, version, slot or identity id; an identity row that conflicts as above, or the operator's id under another email hash; a write target that is a stable database or bucket.

THE APPLY, in order: the pre-checks; the edge D1 bookmark (`wrangler d1 time-travel info`, parsed by `deploy_record.parse_bookmark`; no bookmark, no write); the rollback files written to `--out-dir` and their paths printed with the time-travel restore command; the R2 copy, each object fetched to a temp dir, put, read back and compared by sha256; one `wrangler d1 execute --file` of plain INSERTs (never OR REPLACE) ending with an `event_log` row `config.store.mirrored`; then a re-read of every inserted row compared column by column with the plan, and `PRAGMA foreign_key_check` on every touched table compared with the check taken before the write.

ROLLBACK. `rollback.sql` deletes the store (cascading identities, slots, entries and versions) and then, by id, exactly the identity rows and the audit row this run inserted; a reused edge row is never deleted. `rollback.sh` runs it and deletes each copied R2 object. The D1 time-travel restore to the printed bookmark is the full undo.

OUTPUT. Names, counts and 8-character id prefixes only. No `wrapped_cek`, `server_secret`, `sdk_master`, passphrase, email or email hash is ever printed; the rollback files carry full ids and are written mode 0600.

CREDENTIALS. `cf_auth.resolve_scoped("mirror-config-store")`: a supplied `CF_MANAGEMENT_TOKEN`, or a token minted from `CF_GLOBAL_API_KEY` + `CF_EMAIL` carrying `SCOPED_GROUPS["mirror-config-store"]`, destroyed in a `finally`. With neither set, the run re-executes itself under `bws_env exec --profile mirror-config-store`. The token reaches wrangler only through its environment.

Exit codes: 0 done (or a clean dry run), 1 refused or failed, 2 bad arguments.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
import uuid
from typing import Protocol

from rediacc_ci import log, paths
from rediacc_ci.deploy import console_executor as target_mod
from rediacc_ci.deploy import deploy_record
from rediacc_ci.ops import cf_auth
from rediacc_ci.ops import prune_worker_secrets as prune

SELF = "rediacc_ci.ops.mirror_config_store"
PURPOSE = "mirror-config-store"
PROFILE = "mirror-config-store"
PREFIX_LEN = 8
SERVER_KEY_NAME = "CONFIG_SERVER_KEY"
EVENT_TYPE = "config.store.mirrored"
EVENT_SOURCE = "ops-mirror-config-store"

STORE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}\Z")
SQL_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}\Z")
END_NAME = re.compile(r"^([a-z]+)-(stable|edge)\Z")
R2_KEY = re.compile(r"^[A-Za-z0-9_.=:@+-]+(/[A-Za-z0-9_.=:@+-]+)*\Z")

LIVE_STATUSES = ("active", "grace", "inactive")
COPY_SLOT_METHODS = ("password", "recovery")
PASSKEY_CLEARED = {
    "passkey_credential_id": None,
    "passkey_public_key": None,
    "passkey_counter": 0,
    "passkey_transports": None,
    "passkey_device_type": None,
    "passkey_backed_up": 0,
}
# Insert order, parents first: D1 enforces foreign keys.
TABLE_ORDER = (
    "users",
    "organizations",
    "subscriptions",
    "org_memberships",
    "teams",
    "team_memberships",
    "config_stores",
    "config_user_identities",
    "config_key_slots",
    "config_entries",
    "config_versions",
    "event_log",
)
# Identity tables: an edge row with the same id is REUSED when these columns match (user ids compared after the case-B remap) and refused when one differs; never updated. The store's own rows refuse on any collision.
IDENTITY_MATCH = {
    "organizations": ("customer_id", "owner_user_id"),
    "subscriptions": ("customer_id",),
    "org_memberships": ("org_id", "user_id"),
    "teams": ("org_id", "slug"),
    "team_memberships": ("team_id", "user_id"),
}
# Unique keys of the identity tables beside the id: an edge row holding the key under another id refuses.
IDENTITY_UNIQUE = {
    "organizations": ("customer_id",),
    "org_memberships": ("org_id", "user_id"),
    "teams": ("org_id", "slug"),
    "team_memberships": ("team_id", "user_id"),
}
NEVER_COPIED = (
    "config_tokens",
    "config_executor_grants",
    "config_cek_handoffs",
    "config_cek_rotations",
)


class RefusedError(Exception):
    """A run that must stop with exit 1; the message never carries a secret."""


class Reader(Protocol):
    def query(self, sql: str) -> list[dict]: ...

    def query_many(self, sql: str) -> list[list[dict]]: ...


def prefix(value: object) -> str:
    return str(value or "")[:PREFIX_LEN]


def lit(value: object) -> str:
    """One SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        if "\x00" in value:
            raise RefusedError("%s: a value holds a NUL byte and cannot be written as SQL" % SELF)
        return "'" + value.replace("'", "''") + "'"
    raise RefusedError("%s: a value of type %s cannot be written as SQL" % (SELF, type(value)))


def ident(name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*\Z", name):
        raise RefusedError("%s: %r is not a plain SQL identifier" % (SELF, name))
    return '"%s"' % name


TOKEN = re.compile(r"@([A-Z][A-Z0-9_]*)@")


def q(template: str, **values: str) -> str:
    """One SQL text: each `@NAME@` token of the template replaced, in one pass, by an already-rendered fragment (the output of `lit`, `id_list` or `ident`); a substituted value is never rescanned."""

    def fill(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        if name not in values:
            raise RefusedError("%s: SQL token @%s@ has no value" % (SELF, match.group(1)))
        return values[name]

    return TOKEN.sub(fill, template)


def id_list(values: list[str] | set[str]) -> str:
    """`(...)` of quoted ids; every id is checked to be plain first."""
    items = sorted(set(values))
    for v in items:
        if not isinstance(v, str) or not SQL_ID.match(v):
            raise RefusedError("%s: id %s is not safe to put in SQL" % (SELF, prefix(v)))
    return "(" + ", ".join(lit(v) for v in items) + ")" if items else "('')"


# ---- ends --------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class End:
    name: str
    channel: str
    region: str
    config: str
    database: str
    bucket: str
    jurisdiction: str
    worker: str


def _regions(root: pathlib.Path) -> list[dict]:
    try:
        doc = json.loads((root / "regions.json").read_text(encoding="utf-8"))
        return [r for r in doc["regions"] if isinstance(r, dict)]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RefusedError("%s: regions.json cannot be read: %s" % (SELF, exc)) from None


def stable_names(root: pathlib.Path) -> tuple[set[str], set[str]]:
    """(stable D1 database names, stable bucket names) of every region: never a write target."""
    dbs, buckets = set(), set()
    for r in _regions(root):
        dbs.add(str((r.get("d1") or {}).get("name") or ""))
        for key in ("r2", "backupR2"):
            buckets.add(str((r.get(key) or {}).get("name") or ""))
    dbs.discard("")
    buckets.discard("")
    return dbs, buckets


def resolve_end(root: pathlib.Path, name: str) -> End:
    match = END_NAME.match(name or "")
    region_doc = None
    if match:
        region_doc = next((r for r in _regions(root) if r.get("id") == match.group(1)), None)
    if not match or region_doc is None:
        raise RefusedError("%s is not <region>-stable or <region>-edge for a known region" % name)
    region, channel = match.group(1), match.group(2)
    config = target_mod.account_config(channel, region)
    path = root.joinpath(*target_mod.ACCOUNT_SUBDIR, config)
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        database = doc["d1_databases"][0]["database_name"]
        bucket = next(b for b in doc["r2_buckets"] if b.get("binding") == "CONFIG_BUCKET")
    except (OSError, tomllib.TOMLDecodeError, KeyError, IndexError, TypeError, StopIteration):
        raise RefusedError("%s has no readable D1 database or CONFIG_BUCKET" % path) from None
    worker = region_doc.get("edgeWorkerName" if channel == "edge" else "workerName")
    return End(
        name=name,
        channel=channel,
        region=region,
        config=config,
        database=str(database),
        bucket=str(bucket.get("bucket_name") or ""),
        jurisdiction=str(bucket.get("jurisdiction") or ""),
        worker=str(worker or ""),
    )


def check_ends(root: pathlib.Path, src: End, dst: End) -> None:
    """The source is a stable end, the target an edge end of the same region, and no stable name is a write target."""
    if src.channel != "stable":
        raise RefusedError("--from %s: the source must be a stable end" % src.name)
    if dst.channel != "edge":
        raise RefusedError("--to %s: the target must be an edge end" % dst.name)
    if src.region != dst.region:
        raise RefusedError(
            "--from and --to must name one region (%s, %s)" % (src.region, dst.region)
        )
    dbs, buckets = stable_names(root)
    if dst.database in dbs or dst.database == src.database:
        raise RefusedError("write target database %s is a stable database" % dst.database)
    if dst.bucket in buckets or dst.bucket == src.bucket or not dst.bucket:
        raise RefusedError("write target bucket %s is a stable bucket" % (dst.bucket or "(none)"))


# ---- wrangler ----------------------------------------------------------------


def parse_results(text: str) -> list[list[dict]] | None:
    """Per statement, the result rows of `wrangler d1 execute --json`; None when the text is not that shape."""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(data, list) or not data:
        return None
    out: list[list[dict]] = []
    for statement in data:
        if not isinstance(statement, dict) or statement.get("success") is not True:
            return None
        found = statement.get("results")
        if not isinstance(found, list) or not all(isinstance(r, dict) for r in found):
            return None
        out.append(found)
    return out


class Wrangler:
    """Runs `npx wrangler ...` in the account Worker directory with a fixed environment; stdout is returned and never printed, since it carries row data.

    A failure is reported by its exit code and the message `_wrangler_error` extracts (the JSON `error.text` and its notes, else the last non-empty line). Before it is shown, every value in `mask` (the secret columns of the copied rows) is replaced whole by `<redacted>`, every id in `redact` is cut to its prefix, a message that echoes SQL is withheld outright (a truncated echo could carry part of a secret no replacement would match), and the result is capped at 300 characters.
    """

    def __init__(self, worker_dir: pathlib.Path, env: dict[str, str]) -> None:
        self.worker_dir = worker_dir
        self.env = env
        self.redact: list[str] = []
        self.mask: list[str] = []

    def _shown(self, text: str) -> str:
        msg = _wrangler_error(text)
        if SQL_ECHO.search(msg):
            return "(wrangler echoed SQL; the message is withheld because it may carry row data)"
        for value in sorted((v for v in self.mask if v), key=len, reverse=True):
            msg = msg.replace(value, "<redacted>")
        for value in self.redact:
            if value:
                msg = msg.replace(value, prefix(value))
        return msg[:300]

    def run(self, argv: list[str], what: str) -> str:
        proc = subprocess.run(
            ["npx", "wrangler", *argv],
            cwd=self.worker_dir,
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            tail = self._shown(proc.stderr) or self._shown(proc.stdout)
            raise RefusedError(
                "%s: wrangler exited %d%s" % (what, proc.returncode, ": " + tail if tail else "")
            )
        return proc.stdout

    def probe(self, argv: list[str]) -> tuple[int, str]:
        """(exit code, raw stdout+stderr) of one wrangler call that may fail by design; the text is classified by the caller and never printed."""
        proc = subprocess.run(
            ["npx", "wrangler", *argv],
            cwd=self.worker_dir,
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout + "\n" + proc.stderr


SQL_ECHO = re.compile(r"\b(INSERT\s+INTO|VALUES\s*\(|UPDATE\s+\S+\s+SET)\b", re.IGNORECASE)


def _wrangler_error(text: str) -> str:
    """The message of a wrangler failure. With --json, wrangler prints a JSON object whose last line is a bare `}`, which hides the cause, so the `error.text` (or `error`) field is used when the output parses; otherwise the last non-empty line."""
    body = text.strip()
    decoder = json.JSONDecoder()
    # Every `{` is tried in turn, so a banner line holding a brace ahead of the JSON object cannot hide it.
    for start in (i for i, ch in enumerate(body) if ch == "{"):
        try:
            doc, _end = decoder.raw_decode(body, start)
        except ValueError:
            continue
        if not isinstance(doc, dict) or "error" not in doc:
            continue
        err = doc.get("error")
        if isinstance(err, dict):
            notes = err.get("notes")
            notes = notes if isinstance(notes, list) else []
            parts = [str(err.get("text") or "")] + [
                str(n.get("text") or "") for n in notes if isinstance(n, dict)
            ]
            msg = " | ".join(p for p in parts if p)
            if msg:
                return msg
        elif err:
            return str(err)
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


class D1:
    """One end's D1 database through wrangler."""

    def __init__(self, wrangler: Wrangler, end: End) -> None:
        self.wrangler = wrangler
        self.end = end

    def _argv(self, *rest: str) -> list[str]:
        return [
            "d1",
            "execute",
            self.end.database,
            "--remote",
            "--json",
            *rest,
            "--config",
            self.end.config,
        ]

    def query_many(self, sql: str) -> list[list[dict]]:
        out = self.wrangler.run(self._argv("--command", sql), "d1 read on %s" % self.end.database)
        found = parse_results(out)
        if found is None:
            raise RefusedError(
                "UNVERIFIED: d1 read on %s printed no result rows" % self.end.database
            )
        return found

    def query(self, sql: str) -> list[dict]:
        return [row for group in self.query_many(sql) for row in group]

    def execute_file(self, path: pathlib.Path) -> None:
        self.wrangler.run(
            self._argv("--yes", "--file", str(path)), "d1 write on %s" % self.end.database
        )

    def bookmark(self) -> str:
        argv = deploy_record.time_travel_argv(self.end.database, self.end.config)[2:]
        try:
            out = self.wrangler.run(argv, "d1 time-travel info on %s" % self.end.database)
        except RefusedError as exc:
            raise RefusedError("NO D1 BOOKMARK, nothing written: %s" % exc) from None
        found = deploy_record.parse_bookmark(out)
        if not found:
            raise RefusedError(
                "NO D1 BOOKMARK for %s: no restore point, so nothing is written" % self.end.database
            )
        return found


# wrangler's answer for a missing object (R2 NoSuchKey, API code 10007).
OBJECT_ABSENT = re.compile(r"does not exist|NoSuchKey|\b10007\b|not found", re.IGNORECASE)


class R2:
    """One end's config bucket through wrangler."""

    def __init__(self, wrangler: Wrangler, end: End) -> None:
        self.wrangler = wrangler
        self.end = end

    def _tail(self) -> list[str]:
        tail = ["--remote"]
        if self.end.jurisdiction:
            tail += ["--jurisdiction", self.end.jurisdiction]
        return [*tail, "--config", self.end.config]

    def get(self, key: str, dest: pathlib.Path) -> None:
        self.wrangler.run(
            [
                "r2",
                "object",
                "get",
                "%s/%s" % (self.end.bucket, key),
                "--file",
                str(dest),
                *self._tail(),
            ],
            "r2 get from %s" % self.end.bucket,
        )

    def exists(self, key: str, dest: pathlib.Path) -> bool:
        """Whether the bucket holds `key`: a get that succeeds is True, a get refused with wrangler's not-found answer is False, and any other failure refuses, because an unknown answer must not be read as absent."""
        code, text = self.wrangler.probe(
            [
                "r2",
                "object",
                "get",
                "%s/%s" % (self.end.bucket, key),
                "--file",
                str(dest),
                *self._tail(),
            ]
        )
        if code == 0:
            return True
        if OBJECT_ABSENT.search(text):
            return False
        raise RefusedError(
            "r2: could not tell whether %s holds an object this copy would write (wrangler exited %d)"
            % (self.end.bucket, code)
        )

    def put(self, key: str, src: pathlib.Path) -> None:
        self.wrangler.run(
            [
                "r2",
                "object",
                "put",
                "%s/%s" % (self.end.bucket, key),
                "--file",
                str(src),
                *self._tail(),
            ],
            "r2 put to %s" % self.end.bucket,
        )


# ---- reading -----------------------------------------------------------------


def _one(rows: list[dict], what: str) -> dict:
    if len(rows) != 1:
        raise RefusedError("%s: expected one row, found %d" % (what, len(rows)))
    return rows[0]


def list_stores(src: Reader) -> list[str]:
    """One line per store: store id prefix, org id prefix, member count, slot methods. Org names are not printed: a personal org is named after its owner's email."""
    rows = src.query(
        "SELECT s.id AS id, s.org_id AS org_id, "
        "(SELECT COUNT(*) FROM org_memberships m WHERE m.org_id = s.org_id) AS members, "
        "(SELECT group_concat(DISTINCT k.method) FROM config_key_slots k "
        "WHERE k.config_store_id = s.id) AS methods "
        "FROM config_stores s JOIN organizations o ON o.id = s.org_id ORDER BY s.id"
    )
    lines = []
    for r in rows:
        methods = ",".join(sorted(str(r.get("methods") or "").split(","))) or "-"
        lines.append(
            "%s  org %s  members %d  slots %s"
            % (
                prefix(r.get("id")),
                prefix(r.get("org_id")),
                int(r.get("members") or 0),
                methods,
            )
        )
    return lines


def read_source(src: Reader, store_id: str, now: str) -> dict:
    """Every stable row the plan needs for one store, read in full (crypto columns included, never printed)."""
    if not STORE_ID.match(store_id):
        raise RefusedError("--store needs a full store id (8-64 characters of [A-Za-z0-9_-])")
    stores = src.query(q("SELECT * FROM config_stores WHERE id = @SID@", sid=lit(store_id)))
    if not stores:
        # The listing prints 8-character prefixes, so a unique prefix names its store.
        # substr, not LIKE: LIKE reads `_` as a wildcard and ignores ASCII case, so a mistyped prefix could name another store.
        like = src.query(
            q(
                "SELECT * FROM config_stores WHERE substr(id, 1, @N@) = @P@",
                n=str(len(store_id)),
                p=lit(store_id),
            )
        )
        if len(like) > 1:
            raise RefusedError(
                "store prefix %s matches %d stores on the source; give more characters"
                % (prefix(store_id), len(like))
            )
        stores = like
    if not stores:
        raise RefusedError("store %s does not exist on the source" % prefix(store_id))
    store_id = str(stores[0]["id"])
    sid = lit(store_id)
    store = stores[0]
    org = _one(
        src.query(q("SELECT * FROM organizations WHERE id = @ID@", id=lit(store["org_id"]))),
        "the store's org",
    )
    owner = org.get("owner_user_id")
    operator = _one(
        src.query(q("SELECT * FROM users WHERE id = @ID@", id=lit(owner))), "the org owner"
    )
    entries = src.query(
        q("SELECT * FROM config_entries WHERE config_store_id = @SID@ ORDER BY id", sid=sid)
    )
    entry_ids = [str(e["id"]) for e in entries]
    versions = (
        src.query(
            q(
                "SELECT * FROM config_versions WHERE config_entry_id IN @IDS@ ORDER BY id",
                ids=id_list(entry_ids),
            )
        )
        if entry_ids
        else []
    )
    team_ids = sorted({str(e["team_id"]) for e in entries if e.get("team_id")})
    teams = (
        src.query(q("SELECT * FROM teams WHERE id IN @IDS@ ORDER BY id", ids=id_list(team_ids)))
        if team_ids
        else []
    )
    team_memberships = (
        src.query(
            q(
                "SELECT * FROM team_memberships WHERE team_id IN @IDS@ AND user_id = @UID@ "
                "ORDER BY id",
                ids=id_list(team_ids),
                uid=lit(owner),
            )
        )
        if team_ids
        else []
    )
    # The source may lag the newest migrations (eu stable had no config_executor_grants on 2026-10-27), so the never-copied tables are counted only where they exist; an absent table holds nothing to leave behind.
    present = {
        str(r.get("name"))
        for r in src.query(
            q(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN @T@",
                t=id_list([*NEVER_COPIED, "config_cek_rotations"]),
            )
        )
    }
    parts = [
        q(
            "(SELECT COUNT(*) FROM @T@ WHERE config_store_id = @SID@) AS @T@",
            t=ident(t),
            sid=sid,
        )
        if t in present
        else q("0 AS @T@", t=ident(t))
        for t in NEVER_COPIED
    ]
    parts.append(
        q(
            "(SELECT COUNT(*) FROM config_cek_rotations "
            "WHERE config_store_id = @SID@ AND status = 'pending') AS pending_rotations",
            sid=sid,
        )
        if "config_cek_rotations" in present
        else "0 AS pending_rotations"
    )
    parts.append(
        q(
            "(SELECT COUNT(*) FROM org_memberships WHERE org_id = @ORG@) AS members",
            org=lit(org["id"]),
        )
    )
    counts = _one(src.query("SELECT " + ", ".join(parts)), "the store counts")
    return {
        "store": store,
        "org": org,
        "operator": operator,
        "subscriptions": src.query(
            q(
                "SELECT * FROM subscriptions WHERE customer_id = @CUST@ AND status IN @LIVE@ "
                "AND (expires_at IS NULL OR expires_at = '' OR expires_at > @NOW@) ORDER BY id",
                cust=lit(org["customer_id"]),
                live=id_list(list(LIVE_STATUSES)),
                now=lit(now),
            )
        ),
        "org_memberships": src.query(
            q(
                "SELECT * FROM org_memberships WHERE org_id = @ORG@ AND user_id = @UID@ ORDER BY id",
                org=lit(org["id"]),
                uid=lit(owner),
            )
        ),
        "teams": teams,
        "team_memberships": team_memberships,
        "slots": src.query(
            q("SELECT * FROM config_key_slots WHERE config_store_id = @SID@ ORDER BY id", sid=sid)
        ),
        "identities": src.query(
            q(
                "SELECT * FROM config_user_identities WHERE config_store_id = @SID@ ORDER BY id",
                sid=sid,
            )
        ),
        "entries": entries,
        "versions": versions,
        "counts": {k: int(v or 0) for k, v in counts.items()},
    }


# The store's own rows: any edge row holding one of these ids refuses the run.
def _collision_probes(source: dict) -> list[tuple[str, str, str, list[str]]]:
    """(label, table, column, values)."""
    org, store = source["org"], source["store"]
    probes = [
        ("store id", "config_stores", "id", [store["id"]]),
        ("store of the org", "config_stores", "org_id", [org["id"]]),
        ("entry id", "config_entries", "id", [e["id"] for e in source["entries"]]),
        ("version id", "config_versions", "id", [v["id"] for v in source["versions"]]),
        ("slot id", "config_key_slots", "id", [s["id"] for s in source["slots"]]),
        ("identity id", "config_user_identities", "id", [i["id"] for i in source["identities"]]),
    ]
    return [p for p in probes if p[3]]


def _edge_identity_rows(dst: Reader, source: dict) -> dict[str, list[dict]]:
    """The edge rows of each identity table that share an id or a unique key with the plan's rows: the identity columns, the id and (subscriptions) the status only, never a secret column."""
    org = source["org"]
    team_ids = [str(t["id"]) for t in source["teams"]]
    wanted = {
        "organizations": (
            "id, customer_id, owner_user_id",
            "id = @ORG@ OR customer_id = @CUST@",
        ),
        "subscriptions": (
            "id, customer_id, status, expires_at",
            "id IN @SUBS@ OR customer_id = @CUST@",
        ),
        "org_memberships": ("id, org_id, user_id", "id IN @OMS@ OR org_id = @ORG@"),
        "teams": ("id, org_id, slug", "id IN @TEAMS@ OR org_id = @ORG@"),
        "team_memberships": ("id, team_id, user_id", "id IN @TMS@ OR team_id IN @TEAMS@"),
    }
    values = {
        "org": lit(org["id"]),
        "cust": lit(org["customer_id"]),
        "subs": id_list([str(r["id"]) for r in source["subscriptions"]]),
        "oms": id_list([str(r["id"]) for r in source["org_memberships"]]),
        "teams": id_list(team_ids),
        "tms": id_list([str(r["id"]) for r in source["team_memberships"]]),
    }
    return {
        table: dst.query(
            q(
                "SELECT @COLS@ FROM @T@ WHERE @WHERE@",
                cols=cols,
                t=ident(table),
                where=q(where, **values),
            )
        )
        for table, (cols, where) in wanted.items()
    }


def read_target(dst: Reader, source: dict) -> dict:
    """What the edge database already holds of the ids the plan would write."""
    operator = source["operator"]
    collisions: list[str] = []
    for label, table, column, values in _collision_probes(source):
        hit = dst.query(
            q(
                "SELECT COUNT(*) AS n FROM @T@ WHERE @C@ IN @IDS@",
                t=ident(table),
                c=ident(column),
                ids=id_list(values),
            )
        )
        if int((hit[0] if hit else {}).get("n") or 0):
            collisions.append("%s (%s.%s)" % (label, table, column))
    by_hash = dst.query(
        q("SELECT id FROM users WHERE email_hash = @H@", h=lit(operator["email_hash"]))
    )
    by_id = dst.query(q("SELECT id, email_hash FROM users WHERE id = @ID@", id=lit(operator["id"])))
    return {
        "collisions": collisions,
        "identity": _edge_identity_rows(dst, source),
        "user_by_hash": str(by_hash[0]["id"]) if by_hash else None,
        "user_id_taken": bool(by_id) and by_id[0].get("email_hash") != operator["email_hash"],
    }


def resolve_identity(
    planned: list[tuple[str, dict]], edge: dict[str, list[dict]], org_id: str, customer_id: str
) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]], list[str]]:
    """(rows to insert, rows reused as (table, edge row), conflicts) for the identity tables. A conflict names the table and column(s) and an id prefix, never a value."""
    insert: list[tuple[str, dict]] = []
    reused: list[tuple[str, dict]] = []
    conflicts: list[str] = []
    for table, row in planned:
        rows = edge.get(table, [])
        same = next((r for r in rows if str(r.get("id")) == str(row["id"])), None)
        if same is not None:
            differ = [c for c in IDENTITY_MATCH[table] if same.get(c) != row.get(c)]
            if differ:
                conflicts.append(
                    "%s row %s differs in %s" % (table, prefix(row["id"]), ", ".join(differ))
                )
            else:
                reused.append((table, same))
            continue
        key = IDENTITY_UNIQUE.get(table)
        if key and any(
            str(r.get("id")) != str(row["id"]) and all(r.get(c) == row.get(c) for c in key)
            for r in rows
        ):
            conflicts.append("%s (%s) is held by another edge row" % (table, ", ".join(key)))
            continue
        insert.append((table, row))
    org_reused = any(t == "organizations" and str(r["id"]) == org_id for t, r in reused)
    planned_subs = {str(r["id"]) for t, r in planned if t == "subscriptions"}
    stranger = [
        r
        for r in edge.get("subscriptions", [])
        if r.get("customer_id") == customer_id and str(r.get("id")) not in planned_subs
    ]
    if stranger and not org_reused:
        conflicts.append(
            "subscriptions (customer_id) has %d edge row(s) for a customer whose org is not on edge"
            % len(stranger)
        )
    return insert, reused, conflicts


# ---- schema parity -----------------------------------------------------------


def schema_parity(src: Reader, dst: Reader) -> list[str]:
    """Refuses drift the copy cannot carry; returns the summary lines."""
    src_m = {str(r.get("name")) for r in src.query("SELECT name FROM d1_migrations")}
    dst_m = {str(r.get("name")) for r in dst.query("SELECT name FROM d1_migrations")}
    missing = sorted(src_m - dst_m)
    if missing:
        raise RefusedError(
            "schema: %d stable migration(s) are not applied on edge (%s): deploy edge first"
            % (len(missing), ", ".join(missing[:5]))
        )
    sql = "; ".join("PRAGMA table_info(%s)" % ident(t) for t in TABLE_ORDER)
    src_cols, dst_cols = src.query_many(sql), dst.query_many(sql)
    if len(src_cols) != len(TABLE_ORDER) or len(dst_cols) != len(TABLE_ORDER):
        raise RefusedError("UNVERIFIED: table_info did not answer once per table")
    problems = []
    for table, s_rows, d_rows in zip(TABLE_ORDER, src_cols, dst_cols, strict=True):
        if not d_rows:
            problems.append("%s is missing on edge" % table)
            continue
        s_names = {str(r["name"]) for r in s_rows}
        d_by = {str(r["name"]): r for r in d_rows}
        problems += ["%s.%s is missing on edge" % (table, c) for c in sorted(s_names - set(d_by))]
        for name, r in sorted(d_by.items()):
            if (
                name not in s_names
                and int(r.get("notnull") or 0)
                and r.get("dflt_value") is None
                and not int(r.get("pk") or 0)
            ):
                problems.append("%s.%s is NOT NULL with no default on edge only" % (table, name))
    if problems:
        raise RefusedError("schema: " + "; ".join(problems))
    return [
        "schema: %d stable migration(s) all applied on edge (%d there); %d table(s) compatible"
        % (len(src_m), len(dst_m), len(TABLE_ORDER))
    ]


def fk_violations(dst: Reader) -> set[tuple]:
    sql = "; ".join("PRAGMA foreign_key_check(%s)" % ident(t) for t in TABLE_ORDER)
    out = set()
    for group in dst.query_many(sql):
        for r in group:
            out.add((r.get("table"), r.get("rowid"), r.get("parent"), r.get("fkid")))
    return out


# ---- CONFIG_SERVER_KEY -------------------------------------------------------


def secret_presence(token: str, account: str, workers: list[str]) -> dict[str, bool]:
    """Whether each Worker holds CONFIG_SERVER_KEY, by name: no deploy pushes it, so `prune_worker_secrets.survey` lists it as an extra exactly when it is set."""
    if SERVER_KEY_NAME in prune.expected_names():
        raise RefusedError(
            "%s is now a pushed secret, so the survey cannot tell its presence; check by hand"
            % SERVER_KEY_NAME
        )
    rows = [prune.Row("", "", w) for w in workers]
    try:
        prune.survey(rows, account, token, prune.http_fetch)
    except prune.ApiError as exc:
        raise RefusedError("the Worker secret names could not be read: %s" % exc) from None
    return {r.worker: SERVER_KEY_NAME in r.extras for r in rows}


def check_server_key(presence: dict[str, bool], src: End, dst: End) -> str:
    a, b = presence.get(src.worker), presence.get(dst.worker)
    if a is None or b is None:
        raise RefusedError("%s presence is unknown for a Worker" % SERVER_KEY_NAME)
    if a != b:
        raise RefusedError(
            "%s is %s on %s and %s on %s: server_recoverable_org_passphrase would not decrypt on edge"
            % (
                SERVER_KEY_NAME,
                "set" if a else "absent",
                src.worker,
                "set" if b else "absent",
                dst.worker,
            )
        )
    # Worker secrets are write-only and no bws entry holds CONFIG_SERVER_KEY, so presence is all that can be compared from here.
    if not a:
        return "%s: absent on both Workers (both use the built-in fallback key)" % SERVER_KEY_NAME
    return (
        "%s: set on both Workers; the values cannot be read back (write-only), so the first edge pull is the proof"
        % SERVER_KEY_NAME
    )


# ---- the plan ----------------------------------------------------------------


@dataclasses.dataclass
class Plan:
    store_id: str
    org_id: str
    customer_id: str
    operator_id: str
    edge_user_id: str
    case: str
    inserts: list[tuple[str, dict]]
    reused: list[tuple[str, str]]
    r2_keys: list[str]
    require_passkey_reset: bool
    lines: list[str]

    def rows(self, table: str) -> list[dict]:
        return [r for t, r in self.inserts if t == table]


SECRET_COLUMNS = {
    "store": (
        "sdk_master",
        "server_secret",
        "encrypted_org_passphrase",
        "server_recoverable_org_passphrase",
    ),
    "operator": (
        "email",
        "email_hash",
        "password_hash",
        "password_salt",
        "totp_secret",
        "totp_backup_hashes",
    ),
}


def secret_values(source: dict) -> list[str]:
    """Every secret value of the copied rows, for `Wrangler.mask`: the store's key material, the operator's credentials and every slot's wrapped CEK."""
    out = [str(source[k].get(c) or "") for k, cols in SECRET_COLUMNS.items() for c in cols]
    out += [str(s.get("wrapped_cek") or "") for s in source["slots"]]
    return [v for v in out if len(v) >= 4]


def build_plan(source: dict, target: dict, src: End, dst: End, now: str, event_id: str) -> Plan:
    """The copy and remap plan; every pre-check that needs only these rows refuses here."""
    store, org, operator = source["store"], source["org"], source["operator"]
    counts = source["counts"]
    if counts.get("pending_rotations"):
        raise RefusedError(
            "store %s has a pending CEK rotation: finish or abort it first" % prefix(store["id"])
        )
    if target["collisions"]:
        raise RefusedError(
            "edge already holds rows this copy would write: %s; nothing written"
            % ", ".join(target["collisions"])
        )
    if target["user_by_hash"] is None and target["user_id_taken"]:
        raise RefusedError(
            "edge holds user %s under another email: case A cannot keep the id"
            % prefix(operator["id"])
        )
    op = str(operator["id"])
    known_teams = {str(t["id"]) for t in source["teams"]}
    stray = {str(e["team_id"]) for e in source["entries"] if e.get("team_id")} - known_teams
    if stray:
        raise RefusedError("%d entry team id(s) name no team on the source" % len(stray))

    case = "A" if target["user_by_hash"] is None else "B"
    edge_user = op if case == "A" else str(target["user_by_hash"])

    def remap(uid: object) -> object:
        return edge_user if uid == op else uid

    gen = int(store.get("cek_generation") or 1)
    op_slots = [s for s in source["slots"] if s.get("user_id") == op]
    kept_slots = [s for s in op_slots if s.get("method") in COPY_SLOT_METHODS]
    if not any(int(s.get("cek_generation") or 0) == gen for s in kept_slots):
        raise RefusedError(
            "the operator %s holds no password or recovery slot at CEK generation %d: the edge copy could not be unlocked"
            % (prefix(op), gen)
        )
    passkey_slots = [s for s in source["slots"] if s.get("method") == "passkey"]
    other_slots = [s for s in source["slots"] if s.get("user_id") != op]
    op_identities = [i for i in source["identities"] if i.get("user_id") == op]
    other_identities = len(source["identities"]) - len(op_identities)

    planned: list[tuple[str, dict]] = [
        ("organizations", {**org, "owner_user_id": remap(org.get("owner_user_id"))})
    ]
    planned += [("subscriptions", dict(s)) for s in source["subscriptions"]]
    planned += [
        ("org_memberships", {**m, "user_id": remap(m["user_id"])})
        for m in source["org_memberships"]
    ]
    planned += [("teams", dict(t)) for t in source["teams"]]
    planned += [
        ("team_memberships", {**m, "user_id": remap(m["user_id"])})
        for m in source["team_memberships"]
    ]
    identity_rows, reused_rows, conflicts = resolve_identity(
        planned, target["identity"], str(org["id"]), str(org["customer_id"])
    )
    if conflicts:
        raise RefusedError(
            "edge holds identity rows that conflict with this copy: %s; nothing written"
            % "; ".join(conflicts)
        )
    inserts: list[tuple[str, dict]] = []
    reused: list[tuple[str, str]] = []
    if case == "A":
        inserts.append(("users", dict(operator)))
    else:
        reused.append(("users", edge_user))
    inserts += identity_rows
    reused += [(t, str(r["id"])) for t, r in reused_rows]
    reset = bool(int(store.get("require_passkey") or 0))
    inserts.append(("config_stores", {**store, "require_passkey": 0} if reset else dict(store)))
    inserts += [
        ("config_user_identities", {**i, **PASSKEY_CLEARED, "user_id": edge_user})
        for i in op_identities
    ]
    inserts += [("config_key_slots", {**s, "user_id": edge_user}) for s in kept_slots]
    inserts += [("config_entries", dict(e)) for e in source["entries"]]
    nulled = 0
    for v in source["versions"]:
        by = v.get("created_by_user_id")
        if by is not None and by != op:
            nulled += 1
            by = None
        inserts.append(("config_versions", {**v, "created_by_user_id": remap(by)}))
    inserts.append(
        (
            "event_log",
            {
                "id": event_id,
                "type": EVENT_TYPE,
                "source": EVENT_SOURCE,
                "actor_role": "root",
                "org_id": org["id"],
                "customer_id": org["customer_id"],
                "user_id": edge_user,
                "data": json.dumps(
                    {
                        "from": src.name,
                        "to": dst.name,
                        "store": prefix(store["id"]),
                        "identity": case,
                        "entries": len(source["entries"]),
                        "versions": len(source["versions"]),
                        "slots": len(kept_slots),
                    },
                    sort_keys=True,
                ),
                "timestamp": now,
            },
        )
    )
    keys = sorted(
        {str(e["r2_key"]) for e in source["entries"]}
        | {str(v["r2_key"]) for v in source["versions"]}
    )
    for key in keys:
        if not R2_KEY.match(key) or ".." in key.split("/"):
            raise RefusedError(
                "an r2_key of store %s is not a plain object key" % prefix(store["id"])
            )
    unscoped = [k for k in keys if not k.startswith("s/%s/" % store["id"])]

    method_counts = {m: sum(1 for s in kept_slots if s["method"] == m) for m in COPY_SLOT_METHODS}
    lines = [
        "mirror %s -> %s: store %s, org %s"
        % (src.name, dst.name, prefix(store["id"]), prefix(org["id"])),
        (
            "identity: case A, operator %s copied with the same id" % prefix(op)
            if case == "A"
            else "identity: case B, operator %s remapped to edge user %s"
            % (prefix(op), prefix(edge_user))
        ),
        "copy: "
        + ", ".join(
            "%s %d" % (t, sum(1 for tt, _ in inserts if tt == t))
            for t in TABLE_ORDER
            if t != "event_log"
        ),
        "reused on edge (never updated): "
        + (
            ", ".join(
                "%s %d" % (t, n)
                for t in TABLE_ORDER
                if (n := sum(1 for tt, _ in reused if tt == t))
            )
            or "none"
        ),
        "slots copied: password %d, recovery %d (operator only)"
        % (method_counts["password"], method_counts["recovery"]),
        "left out: passkey slots %d, other members' slots %d, other members' identities %d, other members %d (count only)"
        % (
            len(passkey_slots),
            len(other_slots),
            other_identities,
            max(int(counts.get("members") or 0) - len(source["org_memberships"]), 0),
        ),
        "never copied: " + ", ".join("%s %d" % (t, int(counts.get(t) or 0)) for t in NEVER_COPIED),
        "identities: passkey columns cleared (passkeys do not carry over to the edge RP ID)",
        "versions: created_by of another member written NULL on %d" % nulled,
        "r2: %d object(s) %s -> %s (%s)"
        % (len(keys), src.bucket, dst.bucket, dst.jurisdiction or "no jurisdiction"),
    ]
    if reset:
        lines.append(
            "require_passkey: 1 on %s, written 0 on %s (edge is password/recovery only)"
            % (src.name, dst.name)
        )
    if unscoped:
        lines.append(
            "r2: %d key(s) are outside s/<store>/ (legacy layout), copied by key" % len(unscoped)
        )
    for table, row in reused_rows:
        if table == "subscriptions" and (
            row.get("status") not in LIVE_STATUSES
            or (row.get("expires_at") and str(row["expires_at"]) <= now)
        ):
            lines.append(
                "subscriptions: reused %s is %s on edge (not live), left as it is"
                % (
                    prefix(row["id"]),
                    "expired" if row.get("status") in LIVE_STATUSES else str(row.get("status")),
                )
            )
    if not source["subscriptions"]:
        lines.append("subscriptions: the org has no live subscription; none copied")
    if not source["org_memberships"]:
        lines.append("org_memberships: the operator holds no membership row; none copied")
    return Plan(
        store_id=str(store["id"]),
        org_id=str(org["id"]),
        customer_id=str(org["customer_id"]),
        operator_id=op,
        edge_user_id=edge_user,
        case=case,
        inserts=inserts,
        reused=reused,
        r2_keys=keys,
        require_passkey_reset=reset,
        lines=lines,
    )


def plan_sql(plan: Plan) -> str:
    """The plan as plain INSERT statements in foreign key order; never OR REPLACE, so a row edge already holds aborts the batch."""
    out = []
    for table in TABLE_ORDER:
        for row in plan.rows(table):
            cols = list(row)
            out.append(
                q(
                    "INSERT INTO @T@ (@COLS@) VALUES (@VALS@);",
                    t=ident(table),
                    cols=", ".join(ident(c) for c in cols),
                    vals=", ".join(lit(row[c]) for c in cols),
                )
            )
    return "\n".join(out) + "\n"


# Rollback order: the store first (it cascades its identities, slots, entries and versions, and entries hold team ids without a cascade), then each identity table child first.
ROLLBACK_ORDER = (
    "team_memberships",
    "teams",
    "org_memberships",
    "subscriptions",
    "organizations",
    "users",
    "event_log",
)


def rollback_sql(plan: Plan) -> str:
    """Deletes exactly the rows this run inserted, by id; a reused edge row is never named."""
    stmts = [q("DELETE FROM config_stores WHERE id = @ID@;", id=lit(plan.store_id))]
    for table in ROLLBACK_ORDER:
        ids = [str(r["id"]) for r in plan.rows(table)]
        if ids:
            stmts.append(q("DELETE FROM @T@ WHERE id IN @IDS@;", t=ident(table), ids=id_list(ids)))
    return "\n".join(stmts) + "\n"


def write_private(path: pathlib.Path, body: str, mode: int) -> None:
    """Creates (or truncates) `path` with `mode` from the first byte, so a file holding secret columns is never readable under a wider umask, even briefly."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.fchmod(fd, mode)
        os.write(fd, body.encode("utf-8"))
    finally:
        os.close(fd)


def rollback_sh(plan: Plan, dst: End, sql_path: pathlib.Path) -> str:
    """The rollback script; every path and name is shell-quoted and the SQL path is absolute, since the script changes directory first."""
    sql_path = sql_path.resolve()
    jur = " --jurisdiction %s" % shlex.quote(dst.jurisdiction) if dst.jurisdiction else ""
    lines = [
        "#!/usr/bin/env bash",
        "# Targeted rollback of mirror_config_store for store %s on %s."
        % (prefix(plan.store_id), dst.name),
        "set -euo pipefail",
        'cd "$(git rev-parse --show-toplevel)/%s"' % "/".join(target_mod.ACCOUNT_SUBDIR),
        "npx wrangler d1 execute %s --remote --yes --file %s --config %s"
        % (shlex.quote(dst.database), shlex.quote(str(sql_path)), shlex.quote(dst.config)),
    ]
    lines += [
        "npx wrangler r2 object delete %s --remote%s --config %s"
        % (shlex.quote("%s/%s" % (dst.bucket, k)), jur, shlex.quote(dst.config))
        for k in plan.r2_keys
    ]
    return "\n".join(lines) + "\n"


# ---- the apply ---------------------------------------------------------------


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edge_objects_absent(keys: list[str], dst: R2) -> str:
    """Refuses when the edge bucket already holds any object this copy would put, so no pre-existing object is overwritten or later deleted by the rollback; a read-only probe, run on a dry run too."""
    with tempfile.TemporaryDirectory(prefix="mirror-config-store-probe-") as tmp:
        held = sum(
            dst.exists(key, pathlib.Path(tmp) / ("%d.probe" % n)) for n, key in enumerate(keys)
        )
    if held:
        raise RefusedError(
            "edge bucket %s already holds %d of the %d object(s) this copy would write; nothing written"
            % (dst.end.bucket, held, len(keys))
        )
    return "r2: none of the %d object(s) exists on %s yet" % (len(keys), dst.end.bucket)


def copy_r2(keys: list[str], src: R2, dst: R2) -> None:
    """Each object fetched, put, read back and compared by sha256."""
    with tempfile.TemporaryDirectory(prefix="mirror-config-store-") as tmp:
        work = pathlib.Path(tmp)
        for n, key in enumerate(keys):
            got, back = work / ("%d.src" % n), work / ("%d.back" % n)
            src.get(key, got)
            dst.put(key, got)
            dst.get(key, back)
            if not got.is_file() or not back.is_file() or _sha256(got) != _sha256(back):
                raise RefusedError(
                    "r2: object %d of %d did not read back byte-equal on %s"
                    % (n + 1, len(keys), dst.end.bucket)
                )
    log.info("r2: %d object(s) copied and read back byte-equal" % len(keys))


def verify(plan: Plan, dst: Reader, fk_before: set[tuple]) -> None:
    """Every inserted row re-read from edge and compared column by column; no new foreign key violation."""
    for table in TABLE_ORDER:
        rows = plan.rows(table)
        if not rows:
            continue
        found = {
            str(r["id"]): r
            for r in dst.query(
                q(
                    "SELECT * FROM @T@ WHERE id IN @IDS@",
                    t=ident(table),
                    ids=id_list([str(r["id"]) for r in rows]),
                )
            )
        }
        for row in rows:
            got = found.get(str(row["id"]))
            if got is None:
                raise RefusedError(
                    "UNVERIFIED: %s row %s is absent after the write" % (table, prefix(row["id"]))
                )
            diff = sorted(c for c in row if got.get(c) != row[c])
            if diff:
                raise RefusedError(
                    "UNVERIFIED: %s row %s differs after the write in %s"
                    % (table, prefix(row["id"]), ", ".join(diff))
                )
    new = fk_violations(dst) - fk_before
    if new:
        raise RefusedError("UNVERIFIED: %d new foreign key violation(s) after the write" % len(new))
    log.info(
        "verified: %d row(s) byte-equal on re-read, no new foreign key violation"
        % len(plan.inserts)
    )


def apply(
    plan: Plan, src_r2: R2, dst_d1: D1, dst_r2: R2, out_dir: pathlib.Path, fk_before: set[tuple]
) -> None:
    dst = dst_d1.end
    bookmark = dst_d1.bookmark()
    log.info("edge D1 bookmark taken before any write: %s" % bookmark)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    sql_path, sh_path, ins_path = (
        out_dir / "rollback.sql",
        out_dir / "rollback.sh",
        out_dir / "insert.sql",
    )
    for path, body, mode in (
        (sql_path, rollback_sql(plan), 0o600),
        (sh_path, rollback_sh(plan, dst, sql_path), 0o700),
        (ins_path, plan_sql(plan), 0o600),
    ):
        write_private(path, body, mode)
    log.info("targeted rollback: bash %s" % sh_path)
    log.info("full restore: %s" % deploy_record.restore_command(dst.database, bookmark, dst.config))
    copy_r2(plan.r2_keys, src_r2, dst_r2)
    dst_d1.execute_file(ins_path)
    ins_path.unlink()
    verify(plan, dst_d1, fk_before)


# ---- the run -----------------------------------------------------------------


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    p.add_argument("--from", dest="src", required=True, help="source end, e.g. eu-stable")
    p.add_argument("--to", dest="dst", required=True, help="target end, e.g. eu-edge")
    p.add_argument("--store", default=None, help="full config store id")
    p.add_argument(
        "--list-stores", action="store_true", help="list the source's stores (read-only)"
    )
    p.add_argument("--dry-run", action="store_true", help="plan only (the default)")
    p.add_argument(
        "--apply", action="store_true", help="write edge; needs --i-understand-edge-write"
    )
    p.add_argument("--i-understand-edge-write", dest="ack", action="store_true")
    p.add_argument("--out-dir", default=None, help="where the rollback files go")
    return p


def _reexec(argv: list[str]) -> int | None:
    """This run under the mirror-config-store profile, unless a credential is in the environment; None when it should run here."""
    have_key = os.environ.get("CF_GLOBAL_API_KEY") and os.environ.get("CF_EMAIL")
    if os.environ.get("CF_MANAGEMENT_TOKEN") or have_key:
        return None
    if target_mod.profile_bound(PROFILE):
        return None
    argv_exec = [
        sys.executable, "-m", "rediacc_ci.core.bws_env", "exec", "--profile", PROFILE,
        "--", sys.executable, "-m", SELF, *argv,
    ]  # fmt: skip
    return subprocess.run(argv_exec, env=target_mod.package_env(), check=False).returncode


def run(
    args: argparse.Namespace, argv: list[str] | None = None, root: pathlib.Path | None = None
) -> int:
    root = root or paths.repo_root()
    if args.apply and args.dry_run:
        log.error("--apply and --dry-run exclude each other")
        return 2
    if args.apply and not args.ack:
        log.error("--apply writes the edge database and bucket: add --i-understand-edge-write")
        return 2
    if not args.list_stores and not args.store:
        log.error("--store <id> or --list-stores is required")
        return 2
    try:
        src_end, dst_end = resolve_end(root, args.src), resolve_end(root, args.dst)
        check_ends(root, src_end, dst_end)
    except RefusedError as exc:
        log.error(str(exc))
        return 1
    if argv is not None:
        code = _reexec(argv)
        if code is not None:
            return code
    auth = None
    try:
        auth = cf_auth.resolve_scoped(PURPOSE, cf_auth.DEFAULT_ACCOUNT_ID)
        cf_auth.await_propagation(auth)
        env = cf_auth.wrangler_env(auth, cf_auth.DEFAULT_ACCOUNT_ID, scrub_global_key=True)
        return _work(args, root, src_end, dst_end, env, auth.token)
    except (RefusedError, cf_auth.CfAuthError) as exc:
        log.error(str(exc))
        return 1
    finally:
        if auth is not None and auth.created:
            cf_auth.self_destruct(auth)


def _work(
    args: argparse.Namespace,
    root: pathlib.Path,
    src_end: End,
    dst_end: End,
    env: dict[str, str],
    token: str,
) -> int:
    worker_dir = root.joinpath(*target_mod.ACCOUNT_SUBDIR)
    wrangler = Wrangler(worker_dir, env)
    src, dst = D1(wrangler, src_end), D1(wrangler, dst_end)
    if args.list_stores:
        lines = list_stores(src)
        for line in lines:
            log.info(line)
        log.info("%d store(s) on %s" % (len(lines), src_end.name))
        return 0
    now = _now()
    wrangler.redact.append(args.store)
    source = read_source(src, args.store, now)
    wrangler.redact += [
        str(source["org"]["id"]),
        str(source["operator"]["id"]),
        str(source["operator"].get("email_hash") or ""),
    ]
    wrangler.mask += secret_values(source)
    lines = schema_parity(src, dst)
    lines.append(
        check_server_key(
            secret_presence(token, env["CLOUDFLARE_ACCOUNT_ID"], [src_end.worker, dst_end.worker]),
            src_end,
            dst_end,
        )
    )
    target = read_target(dst, source)
    plan = build_plan(source, target, src_end, dst_end, now, uuid.uuid4().hex)
    fk_before = fk_violations(dst)
    lines.append(edge_objects_absent(plan.r2_keys, R2(wrangler, dst_end)))
    for line in plan.lines + lines:
        log.info(line)
    if not args.apply:
        log.info("dry run: nothing written; re-run with --apply --i-understand-edge-write")
        return 0
    stamp = now.replace(":", "").replace("-", "")[:15]
    out_dir = (
        pathlib.Path(args.out_dir)
        if args.out_dir
        else root
        / ".ci"
        / "cache"
        / "mirror-config-store"
        / ("%s-%s" % (stamp, prefix(plan.store_id)))
    )
    apply(plan, R2(wrangler, src_end), dst, R2(wrangler, dst_end), out_dir, fk_before)
    log.success(
        "store %s mirrored to %s (identity case %s)"
        % (prefix(plan.store_id), dst_end.name, plan.case)
    )
    return 0


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return run(args, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
