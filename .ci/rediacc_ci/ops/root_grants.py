#!/usr/bin/env python3
"""Root grants: resolve the names in .ci/config/root-grants.json to each region's ids, report drift, and apply it through the account route (agent/plans/PLAN-root-grants.md, Design 2, 3, 5 and 6, box C1).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants [--target <id>|all] [--dry-run|--apply] [--json]

Defaults: `--target all` and `--dry-run`. A bare run is the ops-health check's command and never writes.

THE PHASES. The parent holds no secret: each phase is a child, `bws_env exec --profile <P> -- python3 -m rediacc_ci.ops.root_grants --phase <name> --target <ids>`, started with an environment scrubbed of every name the profiles bind (and of REDIACC_BWS_PROFILES), so `bws_env exec` never meets a name that is already bound. A child prints one JSON document on stdout, which carries no email, token, seed or full id.

  1. `read` (profile `root-grants`: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, ROOT_EMAIL). Two SELECT batches through `wrangler d1 execute --remote --json --command`: the user row whose `email_hash` is the sha256 of the lower-cased ROOT_EMAIL (`USER_SQL`), then that user's owned orgs, their subscriptions and the partner rows at the deterministic partner id (`GRANTS_SQL`). The user counts only when its stored email equals ROOT_EMAIL exactly, the comparison sign-in makes. Then `plan()` and one line per target, for example `edge-us user=35eb74dc actions=3 skipped=0 operator=1`, then one line per action.
  2. `bookmark` (apply only, `root-grants`): `wrangler d1 time-travel info` records `BOOKMARK <database> <bookmark>` before any POST. A failed bookmark exits 2 with nothing written. A target with zero planned actions takes no bookmark and makes no POST.
  3. `post` (apply only): edge under `root-login`, `root_login.open_token_session("edge", region).post("/admin/root-grants/apply", desired)`; bench under `bench-login-<region>`, a password and TOTP sign-in with `login_bench.AccountApi`, `login_bench.elevate`, then the same POST. A missing token or bench seed exits 2 and names the remedy.
  4. `verify` re-runs `read`. Actions left after an apply exit 1.

WHY NOT `--file`. The plan named a 0600 temp `--file` for the read so the email stays off argv. wrangler 4.162.0 sends `d1 execute --remote --file` through the D1 import API (wrangler-dist/cli.js `executeRemotely`): it answers a "Total queries executed" summary instead of the SELECT rows and warns that the database is unavailable while the file is processed. So the read selects by `email_hash` on argv, never by the email, and the email is compared in memory.

NEVER. No SQL write (every statement is a SELECT), no user, personal org or config store created, no plan or tier lowered, no `cus_` subscription written, no console unblocked, no stable target or enterprise config resolved, no apply before the bookmark is recorded, and no email, token, seed or full id printed. The writes are the account route's (`POST /admin/root-grants/apply`), which runs the account services.

EXIT. 0 when no target has an action or a red skip (an absent user and an AMBER operator item are allowed); 1 on drift, a red skip, or actions left after an apply; 2 on a config refusal, a missing credential, a failed bookmark or an unreadable D1.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from rediacc_ci import log, paths
from rediacc_ci.core import wrangler
from rediacc_ci.deploy import console_executor, deploy_record
from rediacc_ci.ops import bench_preflight, executor_orgs, login_bench, root_login, totp

if TYPE_CHECKING:
    import pathlib

SELF = "rediacc_ci.ops.root_grants"
CONFIG_PARTS = (".ci", "config", "root-grants.json")
SUPPLY_PARTS = (".ci", "config", "secret-supply.json")

# The uuidv5 namespace of the partner org id, equal to the account side's constant (held equal by the parity test, box P1).
ROOT_GRANTS_NS = uuid.UUID("62ddf7eb-801c-4b6f-b9a1-17b4dba38b0c")
PARTNER_NAME_PREFIX = "root-grants/partner/"

KINDS = ("edge", "bench")
PLAN_CODES = ("COMMUNITY", "PROFESSIONAL", "BUSINESS", "ENTERPRISE")
TIERS = ("registered", "silver", "gold", "platinum")
PARTNER_ROLES = ("admin",)
EMAIL_ENV = "ROOT_EMAIL"
TARGET_KEYS = frozenset({"id", "kind", "region", "data_region"})
NAME_MAX = 120

READ_PROFILE = "root-grants"
EDGE_POST_PROFILE = root_login.PROFILE
BENCH_LOGIN_ROLE = login_bench.PROFILE_ROLE
READ_NAMES = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", EMAIL_ENV)
APPLY_ROUTE = "/admin/root-grants/apply"
CONFIG_STORE_WHERE = "/account/config-storage"
PHASES = ("read", "bookmark", "post")

PREFIX_LEN = 8
SQL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")
HEX64 = re.compile(r"^[0-9a-f]{64}\Z")

# A plan below the floor is raised; FREE and an unknown code rank below COMMUNITY.
PLAN_RANK = {code: rank for rank, code in enumerate(PLAN_CODES)}
TIER_RANK = {tier: rank for rank, tier in enumerate(TIERS)}
RED_SKIPS = frozenset(
    {
        "personal_org.absent",
        "personal_org.ambiguous",
        "subscription.absent",
        "subscription.billing_managed",
        "console.blocked",
    }
)
BILLING_PREFIX = "cus_"

USER_SQL = "SELECT id, email, role FROM users WHERE email_hash = '@HASH@'"
GRANTS_SQL = (
    (
        "SELECT o.id AS id, o.name AS name, o.customer_id AS customer_id, "
        "o.data_region AS data_region, o.console_executor_blocked_at AS blocked_at, "
        "(SELECT COUNT(*) FROM config_stores c WHERE c.org_id = o.id "
        "AND c.server_recoverable_org_passphrase IS NOT NULL) AS store_count, "
        "(SELECT COUNT(*) FROM partner_profiles p WHERE p.org_id = o.id) AS profile_count "
        "FROM organizations o WHERE o.owner_user_id = '@USER@' ORDER BY o.id"
    ),
    (
        "SELECT s.id AS id, s.customer_id AS customer_id, s.plan_code AS plan_code, "
        "s.status AS status, s.type AS type, s.expires_at AS expires_at, s.created_at AS created_at "
        "FROM subscriptions s WHERE s.customer_id IN "
        "(SELECT o.customer_id FROM organizations o WHERE o.owner_user_id = '@USER@') ORDER BY s.id"
    ),
    "SELECT id, org_id, status, tier FROM partner_profiles WHERE org_id = '@PARTNER@'",
    (
        "SELECT id, org_id, user_id, partner_role FROM partner_members "
        "WHERE org_id = '@PARTNER@' AND user_id = '@USER@'"
    ),
)


class RefusedError(Exception):
    """A run that must stop; `rc` is its exit status. The message carries no secret and no full id."""

    def __init__(self, message: str, rc: int = 2):
        super().__init__(message)
        self.rc = rc


# ---- the config ---------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Target:
    id: str
    kind: str
    region: str
    data_region: str

    @property
    def wrangler_config(self) -> str:
        """The account wrangler config: `wrangler.<region>.toml` for edge (edge and stable share one Worker set per region), `wrangler.bench-<region>.toml` for a bench."""
        return console_executor.account_config(
            console_executor.BENCH_TARGET
            if self.kind == "bench"
            else console_executor.STABLE_TARGET,
            self.region,
        )


@dataclasses.dataclass(frozen=True)
class Config:
    plan: str
    partner_name: str
    tier: str
    partner_role: str
    targets: tuple[Target, ...]

    def desired(self, target: Target) -> dict[str, Any]:
        """The `Desired` body of the route (Design 4) for one target."""
        return {
            "role": "root",
            "personalOrg": {"plan": self.plan, "status": "active"},
            "partnerOrg": {
                "name": self.partner_name,
                "tier": self.tier,
                "partnerRole": self.partner_role,
                "status": "active",
            },
            "dataRegion": target.data_region,
        }


def _need(doc: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in doc:
        raise RefusedError("root-grants config: %s.%s is missing" % (where, key))
    return doc[key]


def _section(doc: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _need(doc, key, "$")
    if not isinstance(value, dict):
        raise RefusedError("root-grants config: %s is not an object" % key)
    return value


def _choice(doc: Mapping[str, Any], key: str, where: str, allowed: Sequence[str]) -> str:
    value = _need(doc, key, where)
    if value not in allowed:
        raise RefusedError(
            "root-grants config: %s.%s is %r, not one of %s"
            % (where, key, value, ", ".join(allowed))
        )
    return str(value)


def parse_config(doc: object, regions: Sequence[Mapping[str, Any]]) -> Config:
    """The config, refused with rc 2 naming the key: a kind other than edge or bench (stable and any enterprise config by name), a region regions.json lacks, a bench region whose `bench.deployable` is not true, a data_region unlike its region, a plan outside the admin enum, a tier outside the tier enum, a partner_role other than admin."""
    if not isinstance(doc, dict):
        raise RefusedError("root-grants config: the document is not an object")
    if doc.get("version") != 1:
        raise RefusedError("root-grants config: version is %r, not 1" % doc.get("version"))
    user = _section(doc, "user")
    if user.get("email_secret") != EMAIL_ENV:
        raise RefusedError("root-grants config: user.email_secret must be %s" % EMAIL_ENV)
    _choice(user, "role", "user", ("root",))
    personal = _section(doc, "personal_org")
    plan = _choice(personal, "plan", "personal_org", PLAN_CODES)
    _choice(personal, "status", "personal_org", ("active",))
    partner = _section(doc, "partner_org")
    name = _need(partner, "name", "partner_org")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= NAME_MAX:
        raise RefusedError(
            "root-grants config: partner_org.name must be 1-%d characters" % NAME_MAX
        )
    tier = _choice(partner, "tier", "partner_org", TIERS)
    role = _choice(partner, "partner_role", "partner_org", PARTNER_ROLES)
    _choice(partner, "status", "partner_org", ("active",))
    console = _section(doc, "console")
    _choice(console, "config_store", "console", ("operator",))
    raw = _need(doc, "targets", "$")
    if not isinstance(raw, list) or not raw:
        raise RefusedError("root-grants config: targets must be a non-empty list")
    known = {str(r.get("id")): r for r in regions if isinstance(r, dict)}
    targets: list[Target] = []
    for index, entry in enumerate(raw):
        where = "targets[%d]" % index
        if not isinstance(entry, dict):
            raise RefusedError("root-grants config: %s is not an object" % where)
        extra = sorted(set(entry) - TARGET_KEYS)
        if extra:
            raise RefusedError(
                "root-grants config: %s.%s is not a key a target takes (only %s); no config file "
                "is ever named here" % (where, extra[0], ", ".join(sorted(TARGET_KEYS)))
            )
        kind = _choice(entry, "kind", where, KINDS)
        region = str(_need(entry, "region", where))
        row = known.get(region)
        if row is None:
            raise RefusedError(
                "root-grants config: %s.region %r is not a regions.json region (%s)"
                % (where, region, ", ".join(sorted(known)))
            )
        bench = row.get("bench")
        if kind == "bench" and not (isinstance(bench, dict) and bench.get("deployable") is True):
            raise RefusedError(
                "root-grants config: %s.region %r has no deployable bench (regions.json "
                "bench.deployable is not true)" % (where, region)
            )
        data_region = str(_need(entry, "data_region", where))
        if data_region != region:
            raise RefusedError(
                "root-grants config: %s.data_region %r differs from its region %r"
                % (where, data_region, region)
            )
        target_id = str(_need(entry, "id", where))
        if target_id != "%s-%s" % (kind, region):
            raise RefusedError(
                "root-grants config: %s.id %r must be %s-%s" % (where, target_id, kind, region)
            )
        if any(t.id == target_id for t in targets):
            raise RefusedError("root-grants config: %s.id %r is repeated" % (where, target_id))
        targets.append(Target(target_id, kind, region, data_region))
    return Config(plan, name.strip(), tier, role, tuple(targets))


def load_config(root: pathlib.Path, config_path: pathlib.Path | None = None) -> Config:
    path = config_path or root.joinpath(*CONFIG_PARTS)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        regions = json.loads((root / "regions.json").read_text(encoding="utf-8"))["regions"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RefusedError("root-grants config cannot be read: %s" % exc) from None
    return parse_config(doc, regions)


def select_targets(config: Config, wanted: str) -> tuple[Target, ...]:
    if wanted == "all":
        return config.targets
    ids = [w for w in wanted.split(",") if w]
    chosen = []
    for target_id in ids:
        hit = next((t for t in config.targets if t.id == target_id), None)
        if hit is None:
            raise RefusedError(
                "--target %s is not in the config (%s, or all)"
                % (target_id, ", ".join(t.id for t in config.targets))
            )
        chosen.append(hit)
    if not chosen:
        raise RefusedError("--target names no target")
    return tuple(chosen)


# ---- the planner (the Python mirror of planGrants) ----------------------------------------------


def prefix(value: object) -> str:
    return str(value or "")[:PREFIX_LEN]


def partner_org_id(user_id: str) -> str:
    """The deterministic partner org id: uuidv5(ROOT_GRANTS_NS, "root-grants/partner/" + userId)."""
    return str(uuid.uuid5(ROOT_GRANTS_NS, PARTNER_NAME_PREFIX + user_id))


def email_hash(email: str) -> str:
    """The `users.email_hash` of an address, as the account computes it (sha256 hex of the lower-cased, trimmed email)."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """What READ_SQL returned for one region: the matched user (None when absent) and its rows."""

    user: Mapping[str, Any] | None
    orgs: Sequence[Mapping[str, Any]] = ()
    subscriptions: Sequence[Mapping[str, Any]] = ()
    profiles: Sequence[Mapping[str, Any]] = ()
    members: Sequence[Mapping[str, Any]] = ()


# Mirrors STATUS_RANK and TYPE_RANK of private/account/src/services/root-grants.service.ts: every status ranks, so an expired or suspended row can still be the primary (and is raised).
STATUS_RANK = {"active": 0, "grace": 1, "inactive": 2, "expired": 3, "suspended": 4}
TYPE_RANK = executor_orgs.TYPE_RANK


def primary_subscription(
    subs: Sequence[Mapping[str, Any]], customer_id: str
) -> Mapping[str, Any] | None:
    """The org's primary subscription, ranked as the account planner ranks it: status, then type, then newest, then id ascending."""
    mine = [s for s in subs if s.get("customer_id") == customer_id]
    mine.sort(key=lambda s: str(s.get("id") or ""))
    mine.sort(key=lambda s: str(s.get("created_at") or ""), reverse=True)
    mine.sort(
        key=lambda s: (
            STATUS_RANK.get(str(s.get("status")), 99),
            TYPE_RANK.get(str(s.get("type")), 99),
        )
    )
    return mine[0] if mine else None


def subscription_raise(sub: Mapping[str, Any], floor: str, now: str) -> dict[str, Any] | None:
    """The write a primary subscription needs to meet the floor, or None: the plan raised when below it (never lowered), status `active`, and an `expires_at` already past cleared to null."""
    updates: dict[str, Any] = {}
    if PLAN_RANK.get(str(sub.get("plan_code") or ""), -1) < PLAN_RANK[floor]:
        updates["planCode"] = floor
    if sub.get("status") != "active":
        updates["status"] = "active"
    expires = sub.get("expires_at")
    if expires and str(expires) <= now:
        updates["expiresAt"] = None
    return updates or None


def _action(
    code: str, kind: str, subject_id: object, before: str | None = None, after: str | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "subject": {"kind": kind, "idPrefix": prefix(subject_id)}}
    if before is not None:
        out["from"] = before
    if after is not None:
        out["to"] = after
    return out


def plan(snapshot: Snapshot, desired: Mapping[str, Any], region: str, now: str) -> dict[str, Any]:
    """The `Report` (Design 4) a dry-run of `desired` over one region's snapshot gives, with `applied` false. Pure: no I/O. Mirrors `planGrants` in private/account/src/services/root-grants.service.ts action for action and text for text (box P1 pins the two equal)."""
    report: dict[str, Any] = {
        "region": region,
        "user": {"state": "absent"},
        "actions": [],
        "skipped": [],
        "operator": [],
        "applied": False,
    }
    user = snapshot.user
    if user is None:
        report["skipped"].append({"code": "user.absent", "reason": "absent, skipped"})
        return report
    user_id = str(user["id"])
    report["user"] = {"state": "present", "idPrefix": prefix(user_id)}
    actions: list[dict[str, Any]] = report["actions"]
    skipped: list[dict[str, Any]] = report["skipped"]
    partner_id = partner_org_id(user_id)
    personal = [
        o
        for o in snapshot.orgs
        if o.get("id") != partner_id and int(o.get("profile_count") or 0) == 0
    ]
    if len(personal) > 1:
        ids = ", ".join(sorted(prefix(o.get("id")) for o in personal))
        skipped.append(
            {
                "code": "personal_org.ambiguous",
                "reason": "owns %d non-partner orgs: %s; nothing written until one is named"
                % (len(personal), ids),
            }
        )
        return report
    if user.get("role") != desired["role"]:
        actions.append(
            _action("role.promote", "user", user_id, str(user.get("role")), str(desired["role"]))
        )
    if not personal:
        skipped.append(
            {"code": "personal_org.absent", "reason": "no personal org; sign-in provisions it"}
        )
    else:
        _plan_personal(report, personal[0], snapshot, desired, now)
    _plan_partner(report, user_id, partner_id, snapshot, desired)
    return report


def _plan_personal(
    report: dict[str, Any],
    org: Mapping[str, Any],
    snapshot: Snapshot,
    desired: Mapping[str, Any],
    now: str,
) -> None:
    actions: list[dict[str, Any]] = report["actions"]
    skipped: list[dict[str, Any]] = report["skipped"]
    org_id = str(org["id"])
    target_region = str(desired["dataRegion"])
    if org.get("data_region") != target_region:
        actions.append(
            _action("org.data_region", "org", org_id, str(org.get("data_region")), target_region)
        )
    sub = primary_subscription(snapshot.subscriptions, str(org.get("customer_id") or ""))
    if sub is None:
        skipped.append(
            {"code": "subscription.absent", "reason": "org %s has no subscription" % prefix(org_id)}
        )
    else:
        current = str(sub.get("plan_code") or "")
        status = str(sub.get("status") or "")
        raise_ = subscription_raise(sub, str(desired["personalOrg"]["plan"]), now)
        if raise_ and str(sub.get("customer_id") or "").startswith(BILLING_PREFIX):
            skipped.append(
                {
                    "code": "subscription.billing_managed",
                    "reason": "subscription %s is %s %s and billing-managed"
                    % (prefix(sub.get("id")), current, status),
                }
            )
        elif raise_:
            actions.append(
                _action(
                    "subscription.raise",
                    "subscription",
                    sub.get("id"),
                    "%s %s" % (current, status),
                    "%s %s" % (raise_.get("planCode", current), raise_.get("status", status)),
                )
            )
    if org.get("blocked_at"):
        skipped.append(
            {
                "code": "console.blocked",
                "reason": "org %s console is blocked by root; never unblocked here"
                % prefix(org_id),
            }
        )
    if int(org.get("store_count") or 0) == 0:
        report["operator"].append(
            {
                "code": "config_store.missing",
                "subject": {"kind": "org", "idPrefix": prefix(org_id)},
                "where": CONFIG_STORE_WHERE,
            }
        )


def _plan_partner(
    report: dict[str, Any],
    user_id: str,
    partner_id: str,
    snapshot: Snapshot,
    desired: Mapping[str, Any],
) -> None:
    actions: list[dict[str, Any]] = report["actions"]
    want = desired["partnerOrg"]
    exists = any(o.get("id") == partner_id for o in snapshot.orgs)
    if not exists:
        actions.append(
            _action("partner.org_create", "partner_org", partner_id, None, str(want["name"]))
        )
    profile = (
        next((p for p in snapshot.profiles if p.get("org_id") == partner_id), None)
        if exists
        else None
    )
    if profile is None:
        actions.append(
            _action(
                "partner.profile_create", "partner_profile", partner_id, None, str(want["tier"])
            )
        )
    else:
        if profile.get("status") != want["status"]:
            actions.append(
                _action(
                    "partner.profile_activate",
                    "partner_profile",
                    partner_id,
                    str(profile.get("status")),
                    str(want["status"]),
                )
            )
        tier = str(profile.get("tier") or "")
        if TIER_RANK.get(tier, -1) < TIER_RANK[str(want["tier"])]:
            actions.append(
                _action(
                    "partner.tier_raise", "partner_profile", partner_id, tier, str(want["tier"])
                )
            )
    member = next(
        (
            m
            for m in snapshot.members
            if m.get("org_id") == partner_id and m.get("user_id") == user_id
        ),
        None,
    )
    role = str(member.get("partner_role") or "") if exists and member else ""
    if not role:
        actions.append(
            _action(
                "partner.member_add", "partner_member", partner_id, None, str(want["partnerRole"])
            )
        )
    elif role != want["partnerRole"]:
        actions.append(
            _action(
                "partner.member_role", "partner_member", partner_id, role, str(want["partnerRole"])
            )
        )


def verdict(report: Mapping[str, Any]) -> int:
    """1 when the report holds an action or a red skip, else 0 (an absent user and operator items are green)."""
    if report.get("actions"):
        return 1
    if any(s.get("code") in RED_SKIPS for s in report.get("skipped") or []):
        return 1
    return 0


# ---- the formatter -------------------------------------------------------------------------------


def format_report(target_id: str, report: Mapping[str, Any], label: str = "") -> list[str]:
    """The lines of one target's report; a dry-run and a server answer read alike. Ids are cut to their prefix here too."""
    head = "%s%s" % (target_id, " " + label if label else "")
    user = report.get("user") or {}
    actions = list(report.get("actions") or [])
    skipped = list(report.get("skipped") or [])
    operator = list(report.get("operator") or [])
    if user.get("state") != "present":
        return ["%s user absent, skipped" % head]
    lines = [
        "%s user=%s actions=%d skipped=%d operator=%d"
        % (head, prefix(user.get("idPrefix")), len(actions), len(skipped), len(operator))
    ]
    for act in actions:
        subject = act.get("subject") or {}
        change = ""
        if "from" in act or "to" in act:
            change = " %s -> %s" % (act.get("from", "(none)"), act.get("to", "(none)"))
        lines.append(
            "  action %s %s %s%s"
            % (act.get("code"), subject.get("kind"), prefix(subject.get("idPrefix")), change)
        )
    for skip in skipped:
        mark = "RED" if skip.get("code") in RED_SKIPS else "skipped"
        lines.append("  %s %s: %s" % (mark, skip.get("code"), skip.get("reason")))
    for item in operator:
        subject = item.get("subject") or {}
        lines.append(
            "  AMBER operator: %s %s (%s %s at %s)"
            % (
                item.get("code"),
                target_id,
                subject.get("kind"),
                prefix(subject.get("idPrefix")),
                item.get("where"),
            )
        )
    return lines


# ---- the D1 read and the bookmark (phase children) ----------------------------------------------


def _wrangler_env(env: Mapping[str, str]) -> dict[str, str]:
    """wrangler's environment: the Cloudflare pair, never the root email."""
    child = dict(env)
    child.pop(EMAIL_ENV, None)
    return child


def _run_wrangler(
    root: pathlib.Path, argv: Sequence[str], env: Mapping[str, str], hide: Sequence[str]
) -> tuple[int, str, str]:
    """One wrangler call from the account Worker directory; stderr comes back with every `hide` value cut to its prefix."""
    worker_dir = root.joinpath(*console_executor.ACCOUNT_SUBDIR)
    child = _wrangler_env(env)
    try:
        full = [*wrangler.require(worker_dir, child), *argv]
    except wrangler.WranglerNotInstalledError as exc:
        raise RefusedError(str(exc)) from None
    proc = subprocess.run(
        full,
        cwd=worker_dir,
        env=child,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    err = proc.stderr
    for value in hide:
        if value:
            err = err.replace(value, prefix(value))
    return proc.returncode, proc.stdout, err


def _statement_rows(text: str, count: int) -> list[list[dict[str, Any]]] | None:
    """The rows of each statement of a `wrangler d1 execute --json` answer; None unless it is `count` successful statements."""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(data, list) or len(data) != count:
        return None
    out: list[list[dict[str, Any]]] = []
    for statement in data:
        if not isinstance(statement, dict) or statement.get("success") is not True:
            return None
        rows = statement.get("results")
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            return None
        out.append(rows)
    return out


def _execute(
    root: pathlib.Path,
    target: Target,
    statements: Sequence[str],
    env: Mapping[str, str],
    hide: Sequence[str],
) -> list[list[dict[str, Any]]]:
    for sql in statements:
        if not sql.lstrip().upper().startswith("SELECT"):
            raise RefusedError("%s: refusing a statement that is not a SELECT" % SELF)
    worker_dir = root.joinpath(*console_executor.ACCOUNT_SUBDIR)
    try:
        database = executor_orgs.database_name(worker_dir / target.wrangler_config)
    except executor_orgs.RefusedError as exc:
        raise RefusedError(str(exc)) from None
    command = "; ".join(statements)
    argv = [
        "d1",
        "execute",
        database,
        "--remote",
        "--json",
        "--command",
        command,
        "--config",
        target.wrangler_config,
    ]
    rc, out, err = _run_wrangler(root, argv, env, hide)
    rows = _statement_rows(out, len(statements)) if rc == 0 else None
    if rows is None:
        last = (err.strip().splitlines() or [""])[-1]
        raise RefusedError(
            "%s: wrangler d1 execute on %s exited %d without result rows%s%s"
            % (target.id, database, rc, executor_orgs.d1_cause(out), "; " + last if last else "")
        )
    return rows


def read_snapshot(
    root: pathlib.Path, target: Target, env: Mapping[str, str], email: str
) -> Snapshot:
    """READ_SQL for one target: the user by email hash, kept only when its stored email equals `email` exactly, then its rows."""
    digest = email_hash(email)
    if not HEX64.match(digest):
        raise RefusedError("%s: the email hash is not 64 hex characters" % SELF)
    (users,) = _execute(root, target, [USER_SQL.replace("@HASH@", digest)], env, [digest])
    matched = [u for u in users if u.get("email") == email]
    if not matched:
        return Snapshot(None)
    user = {"id": matched[0].get("id"), "role": matched[0].get("role")}
    user_id = str(user["id"] or "")
    if not SQL_ID.match(user_id):
        raise RefusedError(
            "%s: user id %s is not safe to put in SQL" % (target.id, prefix(user_id))
        )
    partner_id = partner_org_id(user_id)
    statements = [s.replace("@USER@", user_id).replace("@PARTNER@", partner_id) for s in GRANTS_SQL]
    orgs, subs, profiles, members = _execute(
        root, target, statements, env, [digest, user_id, partner_id]
    )
    return Snapshot(user, orgs, subs, profiles, members)


def take_bookmark(root: pathlib.Path, target: Target, env: Mapping[str, str]) -> tuple[str, str]:
    """(database, bookmark) from `wrangler d1 time-travel info`; RefusedError rc 2 when it does not parse."""
    worker_dir = root.joinpath(*console_executor.ACCOUNT_SUBDIR)
    try:
        database = executor_orgs.database_name(worker_dir / target.wrangler_config)
    except executor_orgs.RefusedError as exc:
        raise RefusedError(str(exc)) from None
    argv = deploy_record.time_travel_argv(database, target.wrangler_config)[len(wrangler.ARGV) :]
    rc, out, err = _run_wrangler(root, argv, env, [])
    bookmark = deploy_record.parse_bookmark(out) if rc == 0 else None
    if not bookmark:
        last = (err.strip().splitlines() or [""])[-1]
        raise RefusedError(
            "NO D1 BOOKMARK for %s (wrangler d1 time-travel info exited %d%s): nothing is applied"
            % (database, rc, "; " + last if last else "")
        )
    return database, bookmark


# ---- the POST (phase child) ----------------------------------------------------------------------


@dataclasses.dataclass
class Deps:
    """The seams a phase child calls through; a test replaces them."""

    open_token_session: Callable[..., Any] = root_login.open_token_session
    account_api: Callable[[str], Any] = login_bench.AccountApi
    capture: Callable[[Sequence[str], Mapping[str, str]], tuple[int, str]] = (
        login_bench._subprocess_capture
    )
    now: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep


def mint_page(region: str) -> str:
    try:
        return "%s/account/admin/root-tokens" % root_login.origin_for("edge", region)
    except root_login.RootLoginError:
        return "https://%s.rediacc.cloud/account/admin/root-tokens" % region


def post_edge(
    target: Target, body: Mapping[str, Any], env: Mapping[str, str], deps: Deps
) -> tuple[int, dict[str, Any]]:
    try:
        client = deps.open_token_session("edge", target.region, env)
        return client.post(APPLY_ROUTE, dict(body))
    except root_login.RootLoginError as exc:
        text = root_login.masked(str(exc), env)
        if exc.rc == 2:
            text += "; remedy: mint the token at %s and store it as %s" % (
                mint_page(target.region),
                root_login.token_entry(target.region),
            )
        raise RefusedError("%s: %s" % (target.id, text), rc=exc.rc) from None


def _bench_sign_in(api: Any, values: Mapping[str, str], deps: Deps) -> None:
    """Password sign-in, then the TOTP challenge when the account asks for one (a refused code is retried once from the next window)."""
    status, answer = api.post(
        "login",
        {"email": values[login_bench.EMAIL_ENV], "password": values[login_bench.PW_ENV]},
    )
    if status != 200:
        raise login_bench.LoginError("POST /auth/login answered HTTP %d" % status)
    if not answer.get("requiresTwoFactor"):
        return
    challenge = answer.get("challengeToken")
    if not isinstance(challenge, str):
        raise login_bench.LoginError("POST /auth/login asked for two-factor with no challengeToken")
    seed = values[login_bench.TOTP_SEED_ENV]
    code = login_bench.fresh_code(seed, deps.now, deps.sleep)
    status, _ = api.post("2fa/verify", {"challengeToken": challenge, "code": code})
    if status != 200 and not (status == 429 or status >= 500):
        asked = deps.now()
        wait = totp.STEP - (asked % totp.STEP) + 0.5
        deps.sleep(wait)
        status, _ = api.post(
            "2fa/verify", {"challengeToken": challenge, "code": totp.code(seed, at=asked + wait)}
        )
    if status != 200:
        raise login_bench.LoginError("POST /auth/2fa/verify answered HTTP %d" % status)


def post_bench(
    target: Target, body: Mapping[str, Any], env: Mapping[str, str], deps: Deps
) -> tuple[int, dict[str, Any]]:
    remedy = login_bench.remedy_for(target.region)[0]
    try:
        values = login_bench.read_values(env, target.region)
        server = login_bench.target_for(target.region).server
        api = deps.account_api(server)
        _bench_sign_in(api, values, deps)
        login_bench.elevate(
            api,
            values[login_bench.EMAIL_ENV],
            login_bench.base_env(env),
            deps.capture,
            deps.now,
            target.region,
        )
        return api.post(root_login.API_ROOT + APPLY_ROUTE, dict(body))
    except login_bench.LoginError as exc:
        text = str(exc)
        if exc.rc == 2:
            text += "; remedy: %s" % remedy
        raise RefusedError("%s: %s" % (target.id, text), rc=exc.rc) from None


# ---- the phase child entry -----------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _secret_values(env: Mapping[str, str], root: pathlib.Path) -> list[str]:
    values = []
    for name in sorted(bound_names(root)):
        value = env.get(name) or ""
        if len(value) >= root_login.MIN_MASKED_LENGTH:
            values.append(value)
    return values


def mask(text: str, secrets: Sequence[str]) -> str:
    for value in sorted(secrets, key=len, reverse=True):
        text = text.replace(value, "<withheld>")
    return text


def run_phase(
    phase: str,
    target_ids: str,
    env: Mapping[str, str],
    root: pathlib.Path,
    deps: Deps,
    config_path: pathlib.Path | None = None,
    now: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """One phase for the named targets, with the profile's values in `env`. Returns (rc, document)."""
    config = load_config(root, config_path)
    targets = select_targets(config, target_ids)
    results: dict[str, Any] = {}
    rc = 0
    if phase in ("read", "bookmark"):
        missing = [n for n in READ_NAMES if not env.get(n)]
        if phase == "bookmark":
            missing = [n for n in missing if n != EMAIL_ENV]
        if missing:
            raise RefusedError(
                "%s must be set: run under `bws_env exec --profile %s`"
                % (" and ".join(missing), READ_PROFILE)
            )
        stamp = now or _now_iso()
        for target in targets:
            try:
                if phase == "read":
                    snap = read_snapshot(root, target, env, env[EMAIL_ENV])
                    results[target.id] = {
                        "report": plan(snap, config.desired(target), target.region, stamp)
                    }
                else:
                    database, bookmark = take_bookmark(root, target, env)
                    results[target.id] = {"database": database, "bookmark": bookmark}
            except RefusedError as exc:
                results[target.id] = {"error": str(exc)}
                rc = max(rc, exc.rc)
        return rc, {"phase": phase, "targets": results}
    if len(targets) != 1:
        raise RefusedError("--phase post takes exactly one target")
    target = targets[0]
    poster = post_bench if target.kind == "bench" else post_edge
    status, answer = poster(target, config.desired(target), env, deps)
    if status != 200 or not isinstance(answer.get("actions"), list):
        code, message = root_login._answer_error(answer)
        raise RefusedError(
            "%s: POST %s answered HTTP %d %s %s" % (target.id, APPLY_ROUTE, status, code, message),
            rc=1,
        )
    return 0, {"phase": phase, "targets": {target.id: {"report": answer}}}


def phase_main(
    argv: Sequence[str],
    env: Mapping[str, str] | None = None,
    root: pathlib.Path | None = None,
    deps: Deps | None = None,
    config_path: pathlib.Path | None = None,
    now: str | None = None,
) -> int:
    """`--phase <name> --target <ids>`: print one JSON document; every bound secret is masked out of it."""
    parser = argparse.ArgumentParser(prog=SELF)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--target", required=True)
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return int(exc.code or 2)
    source = os.environ if env is None else env
    base = root or paths.repo_root()
    try:
        rc, doc = run_phase(args.phase, args.target, source, base, deps or Deps(), config_path, now)
    except RefusedError as exc:
        rc, doc = exc.rc, {"phase": args.phase, "error": str(exc)}
    print(mask(json.dumps(doc, sort_keys=True), _secret_values(source, base)))
    return rc


# ---- the parent: children under bws profiles -----------------------------------------------------


def profile_for(target: Target, phase: str) -> str:
    if phase != "post":
        return READ_PROFILE
    if target.kind == "bench":
        return bench_preflight.profile_for(BENCH_LOGIN_ROLE, target.region)
    return EDGE_POST_PROFILE


def _local_name(spec: str) -> str:
    return spec.split(">", 1)[1].strip() if ">" in spec else spec.strip()


def bound_names(root: pathlib.Path) -> set[str]:
    """Every local name the read, edge-post and bench-post profiles bind (from secret-supply.json); a child's environment carries none of them, and a phase document masks their values."""
    try:
        consumers = json.loads(root.joinpath(*SUPPLY_PARTS).read_text(encoding="utf-8"))[
            "consumers"
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RefusedError("secret-supply.json cannot be read: %s" % exc) from None
    wanted = {READ_PROFILE, EDGE_POST_PROFILE} | {
        bench_preflight.profile_for(BENCH_LOGIN_ROLE, r) for r in login_bench.REGIONS
    }
    names: set[str] = set(READ_NAMES)
    for profile in sorted(wanted):
        body = consumers.get(profile)
        if not isinstance(body, dict):
            raise RefusedError("secret-supply.json has no consumer profile %s" % profile)
        for half in ("required", "optional"):
            names.update(_local_name(str(s)) for s in body.get(half) or [])
    return names


def scrubbed_env(root: pathlib.Path, env: Mapping[str, str] | None = None) -> dict[str, str]:
    """The child environment: no bound name, no REDIACC_BWS_PROFILES, and this checkout's `.ci` first on PYTHONPATH."""
    source = dict(os.environ if env is None else env)
    for name in bound_names(root) | {"REDIACC_BWS_PROFILES"}:
        source.pop(name, None)
    ci = str(root / ".ci")
    source["PYTHONPATH"] = ci + (
        os.pathsep + source["PYTHONPATH"] if source.get("PYTHONPATH") else ""
    )
    return source


def child_argv(profile: str, phase: str, target_ids: Sequence[str]) -> list[str]:
    return console_executor.reexec_argv(
        profile, ["--phase", phase, "--target", ",".join(target_ids)], SELF
    )


Child = Callable[[str, str, Sequence[str]], tuple[int, str]]


def bws_child(root: pathlib.Path) -> Child:
    """The real child runner: `bws_env exec --profile <P>` with a scrubbed environment; stdout is captured, stderr is the terminal's."""

    def run_child(profile: str, phase: str, target_ids: Sequence[str]) -> tuple[int, str]:
        proc = subprocess.run(
            child_argv(profile, phase, target_ids),
            env=scrubbed_env(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout

    return run_child


def in_process_child(
    envs: Mapping[str, Mapping[str, str]],
    root: pathlib.Path,
    deps: Deps,
    config_path: pathlib.Path | None = None,
    now: str | None = None,
) -> Child:
    """A child runner that calls `phase_main` in this process with the scrubbed environment plus `envs[profile]`, as `bws_env exec` adds a profile to what it inherits; the test seam."""

    def run_child(profile: str, phase: str, target_ids: Sequence[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = phase_main(
                ["--phase", phase, "--target", ",".join(target_ids)],
                {**scrubbed_env(root), **envs.get(profile, {})},
                root,
                deps,
                config_path,
                now,
            )
        return rc, buffer.getvalue()

    return run_child


def _phase_doc(child: Child, profile: str, phase: str, target_ids: Sequence[str]) -> dict[str, Any]:
    rc, out = child(profile, phase, target_ids)
    start, end = out.find("{"), out.rfind("}")
    try:
        doc = json.loads(out[start : end + 1]) if start >= 0 and end > start else None
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        raise RefusedError(
            "UNVERIFIED: the %s phase under profile %s exited %d without its JSON document"
            % (phase, profile, rc),
            rc=2,
        )
    if doc.get("error"):
        raise RefusedError(str(doc["error"]), rc=rc or 2)
    targets = doc.get("targets")
    if not isinstance(targets, dict):
        raise RefusedError("UNVERIFIED: the %s phase document names no targets" % phase, rc=2)
    return targets


@dataclasses.dataclass
class Outcome:
    rc: int = 0
    lines: list[str] = dataclasses.field(default_factory=list)
    targets: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    def fold(self, rc: int) -> None:
        self.rc = max(self.rc, rc)


def _said(target_id: str, message: str) -> str:
    """`message` led by its target id once."""
    return message if message.startswith(target_id + ":") else "%s: %s" % (target_id, message)


def _fail(out: Outcome, entry: dict[str, Any], target_id: str, message: str) -> None:
    """Record a failed step in the text lines and in the target's JSON entry."""
    line = _said(target_id, message)
    out.lines.append(line)
    entry["error"] = line


def _apply_one(child: Child, target: Target, entry: dict[str, Any], out: Outcome) -> bool:
    """Bookmark, POST and verify one target; False when the run must stop (a failed bookmark)."""
    try:
        marks = _phase_doc(child, READ_PROFILE, "bookmark", [target.id])
    except RefusedError as exc:
        _fail(out, entry, target.id, str(exc))
        out.fold(2)
        return False
    mark = marks.get(target.id) or {}
    if mark.get("error") or not mark.get("bookmark"):
        _fail(out, entry, target.id, str(mark.get("error") or "no bookmark recorded"))
        out.fold(2)
        return False
    out.lines.append("BOOKMARK %s %s" % (mark.get("database"), mark["bookmark"]))
    entry["bookmark"] = {"database": mark.get("database"), "bookmark": mark["bookmark"]}
    try:
        posted = _phase_doc(child, profile_for(target, "post"), "post", [target.id])
        server = (posted.get(target.id) or {}).get("report") or {}
    except RefusedError as exc:
        _fail(out, entry, target.id, str(exc))
        out.fold(exc.rc)
        return True
    entry["applied"] = server
    out.lines.extend(format_report(target.id, server, "applied"))
    try:
        again = _phase_doc(child, READ_PROFILE, "read", [target.id])
    except RefusedError as exc:
        out.lines.append("%s: verify: %s" % (target.id, exc))
        out.fold(2)
        return True
    check = again.get(target.id) or {}
    if check.get("error"):
        out.lines.append("%s: verify: %s" % (target.id, check["error"]))
        out.fold(2)
        return True
    entry["verify"] = check["report"]
    out.lines.extend(format_report(target.id, check["report"], "verify"))
    if check["report"].get("actions"):
        out.lines.append(
            "%s: %d action(s) remain after the apply" % (target.id, len(check["report"]["actions"]))
        )
    out.fold(verdict(check["report"]))
    return True


def orchestrate(targets: Sequence[Target], apply: bool, child: Child) -> Outcome:
    out = Outcome()
    try:
        reads = _phase_doc(child, READ_PROFILE, "read", [t.id for t in targets])
    except RefusedError as exc:
        out.lines.append(str(exc))
        out.fold(2)
        return out
    for target in targets:
        found = reads.get(target.id) or {"error": "the read phase did not report %s" % target.id}
        entry: dict[str, Any] = {"target": target.id}
        out.targets.append(entry)
        if found.get("error"):
            entry["error"] = found["error"]
            out.lines.append(_said(target.id, str(found["error"])))
            out.fold(2)
            continue
        report = found["report"]
        entry["report"] = report
        out.lines.extend(format_report(target.id, report))
        if not apply or not report.get("actions"):
            out.fold(verdict(report))
            if report.get("actions"):
                out.lines.append(
                    "%s: remedy: PYTHONPATH=.ci python3 -m %s --apply --target %s"
                    % (target.id, SELF, target.id)
                )
            continue
        if not _apply_one(child, target, entry, out):
            return out
    return out


# ---- the entry -----------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--target", default="all", help="a target id from the config, or all")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (the default)")
    mode.add_argument("--apply", action="store_true", help="bookmark, POST and verify")
    parser.add_argument("--json", action="store_true", help="print one JSON document")
    return parser


def run(
    argv: Sequence[str],
    root: pathlib.Path | None = None,
    child: Child | None = None,
    config_path: pathlib.Path | None = None,
) -> int:
    try:
        args = _parser().parse_args(list(argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    base = root or paths.repo_root()
    try:
        config = load_config(base, config_path)
        targets = select_targets(config, args.target)
        bound_names(base)
    except RefusedError as exc:
        log.error(str(exc))
        return exc.rc
    out = orchestrate(targets, args.apply, child or bws_child(base))
    if args.json:
        print(json.dumps({"rc": out.rc, "apply": args.apply, "targets": out.targets}, indent=2))
    else:
        for line in out.lines:
            print(line)
    return out.rc


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--phase" in args:
        return phase_main(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
