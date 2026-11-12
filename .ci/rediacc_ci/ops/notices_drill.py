"""Bench drill: expired repository licences become ONE reminder mail, an unread notice and an `rdc` verb, driven from both sides.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.notices_drill [--dry-run] [--wait-cron]

BENCH ONLY. The target is `BENCH_ORIGIN`; no other server is accepted. The run re-executes itself under the `deploy-bench` Bitwarden profile (it needs `CF_GLOBAL_API_KEY` and `CF_EMAIL` for the D1 queries, and `ROOT_EMAIL` plus `BENCH_ROOT_PASSWORD` for the root session) unless that profile is already bound. Plan: agent/plans/PLAN-account-notices.md, box D1 (Design 1 to 5, Context 6 and 7).

THE STEPS, each printing one evidence line `STEP <n> <name> rc=<rc> <detail>`:

  1  allowlist  `bench_access add-current`, so this host passes the bench WAF rule.
  2  register   `POST /auth/register` with a throwaway `ntc+<stamp>@rediacc.io` address and a random password.
  3  terms      A login with a cookie jar, then `POST /portal/terms/accept` when the Terms are not satisfied.
  4  config     A throwaway named config `ntc-<stamp>` (`rdc config init`), a CLI login, the machine `drillbox` added offline (`rdc machine add`, TEST-NET 192.0.2.10), and a repository record `drill` carrying the planted GUID patched into the config JSON.
  5  plant      Two `repo_license_issued` events in the D1 `event_log`, one hard-expired and one refresh-recommended, for the throwaway subscription. The event log is tenant-sharded: the subscription's shard is read from `subscription_shards` first, and a shard other than 0 is refused (bench runs the directory database only).
  6  root-run    The root session (`ROOT_EMAIL`, `BENCH_ROOT_PASSWORD`) calls `POST /admin/reminders/run {kinds:['repo']}`. With `--wait-cron` the call is skipped and the run waits for the deployed 03:00 UTC cron to send the mail (use it when the bench root has two-factor on).
  7  mail       Exactly one `captured_emails` row names either planted GUID; its text holds both 8-char GUIDs, `rdc subscription refresh` and `/account/notices`, and neither the repository name, the machine name nor the planted machine id.
  8  unread     With the user's session `GET /portal/notices/unread-count` is 1.
  9  notices    `rdc subscription notices -o json` names the planted repository `drill@drillbox`.
  10 rerun      The reminder run again: no second mail (the same cadence bucket), still one row.
  11 retire     `rdc subscription retire <guid> --yes` exits 0 and `rdc subscription status -o json` no longer lists the retired licence (the refresh-recommended one stays). It runs after the rerun on purpose: retiring changes the GUID set, and a changed set starts a new episode that mails again.
  12 cleanup    Always runs. Deletes the notices, reminder-log rows and planted events, then the user, its organizations, subscriptions and captured mail (`free_to_registered.cleanup`), the throwaway config and its token file, and proves the user is gone.

The password and every token travel only in a child environment or a request body, never on argv and never printed. Exit 0 only when every step held; cleanup failing is a failure.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.ops import deploy_bench
from rediacc_ci.ops import free_to_registered as ftr
from rediacc_ci.ops.free_to_registered import (
    API,
    UUID,
    DrillError,
    Evidence,
    Rdc,
    Rows,
    q,
    sql_literal,
)
from rediacc_ci.well_known import BENCH_ORIGIN, INFRA_DOMAIN

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

PROFILE = "deploy-bench"
ADDRESS = re.compile(r"^ntc\+\d{14}@" + re.escape(INFRA_DOMAIN) + "$")
REPO_NAME = "drill"
MACHINE_NAME = "drillbox"
MACHINE_IP = "192.0.2.10"
REF = "%s@%s" % (REPO_NAME, MACHINE_NAME)
TAG = "latest"
CLOCK_SKEW_S = 60
WAIT_CRON_S = 26 * 3600
WAIT_CRON_POLL_S = 60.0
NEEDS = ("rdc subscription refresh", "/account/notices")
STEPS = (
    ("1", "allowlist"),
    ("2", "register"),
    ("3", "terms"),
    ("4", "config"),
    ("5", "plant"),
    ("6", "root-run"),
    ("7", "mail"),
    ("8", "unread"),
    ("9", "notices"),
    ("10", "rerun"),
    ("11", "retire"),
    ("12", "cleanup"),
)

Call = ftr.Call


def stamp_address(stamp: str) -> str:
    """The throwaway address of one run."""
    return "ntc+%s@%s" % (stamp, INFRA_DOMAIN)


def iso(moment: datetime) -> str:
    """`Date.toISOString()` spelling, the form the event log stores."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (
        moment.microsecond // 1000
    )


@dataclass
class Planted:
    """The two licences the drill plants, so the checks and the cleanup name exactly them."""

    hard_guid: str
    fresh_guid: str
    machine_id: str
    event_ids: list[str] = field(default_factory=list)

    @property
    def guids(self) -> tuple[str, str]:
        return (self.hard_guid, self.fresh_guid)

    def short(self) -> tuple[str, str]:
        return (self.hard_guid[:8], self.fresh_guid[:8])


def event_rows(
    planted: Planted,
    ids: Sequence[str],
    sub_id: str,
    user_id: str,
    org_id: str,
    team_id: str | None,
    now: datetime,
) -> list[str]:
    """Two INSERT statements shaped like SubscriptionService's `repo_license_issued` log call (subscription.service.ts ~832): the data holds the GUIDs, kind, dates and the machine id, never a name."""
    for ident in (sub_id, user_id, org_id, *ids, *([team_id] if team_id else [])):
        if not UUID.match(ident):
            raise DrillError("refusing a non-UUID id in an insert: %r" % ident)
    plans = (
        (
            ids[0],
            planted.hard_guid,
            now - timedelta(days=45),
            now - timedelta(days=40),
            now - timedelta(days=1),
        ),
        (
            ids[1],
            planted.fresh_guid,
            now - timedelta(days=2),
            now - timedelta(days=1),
            now + timedelta(days=29),
        ),
    )
    out: list[str] = []
    for event_id, guid, issued, refresh_at, hard_at in plans:
        data = {
            "machineId": planted.machine_id,
            "clientMachineId": "ntc-client",
            "repositoryGuid": guid,
            "grandGuid": guid,
            "kind": "grand",
            "requestedSizeGb": 10,
            "refreshRecommendedAt": iso(refresh_at),
            "hardExpiresAt": iso(hard_at),
        }
        out.append(
            q(
                "INSERT INTO event_log (id, type, source, user_id, subscription_id, customer_id, "
                "team_id, data, org_id, timestamp) VALUES ($id, 'repo_license_issued', 'account', "
                "NULL, $sub, $cust, $team, $data, $org, $ts)",
                id=sql_literal(event_id),
                sub=sql_literal(sub_id),
                cust=sql_literal(user_id),
                team=sql_literal(team_id) if team_id else "NULL",
                data=sql_literal(json.dumps(data, separators=(",", ":"))),
                org=sql_literal(org_id),
                ts=sql_literal(iso(issued)),
            )
        )
    return out


def shard_check(rows: Sequence[dict]) -> str | None:
    """None when the subscription lives on shard 0 (no row means shard 0); otherwise the reason this drill cannot plant on it."""
    if not rows:
        return None
    shard = str(rows[0].get("shard") or "0")
    if shard == "0":
        return None
    return (
        "subscription is on tenant shard %s; the drill plants into the bench directory D1 only"
        % shard
    )


def mail_check(mails: Sequence[dict], planted: Planted, needs: Sequence[str] = NEEDS) -> list[str]:
    """Reasons the captured mails are not exactly one digest holding both short GUIDs, the fix command and the notices link, with no name. Empty when it holds."""
    short = planted.short()
    named = [m for m in mails if any(s in str(m.get("text_body") or "") for s in short)]
    if len(named) != 1:
        return ["%d mails name a planted GUID, want exactly 1" % len(named)]
    text = str(named[0].get("text_body") or "")
    bad = ["both short GUIDs are not in the mail"] if not all(s in text for s in short) else []
    bad += ["%r is not in the mail" % n for n in needs if n not in text]
    lowered = text.lower()
    for leak, label in (
        (REPO_NAME, "repository name"),
        (MACHINE_NAME, "machine name"),
        (planted.machine_id.lower(), "machine id"),
    ):
        if re.search(r"\b%s\b" % re.escape(leak), lowered):
            bad.append("the %s %r is in the mail" % (label, leak))
    return bad


def walk_items(node: object) -> list[dict]:
    """Every dict in a decoded JSON tree that carries a `guid`."""
    found: list[dict] = []
    if isinstance(node, dict):
        if "guid" in node:
            found.append(node)
        for value in node.values():
            found += walk_items(value)
    elif isinstance(node, list):
        for value in node:
            found += walk_items(value)
    return found


def notices_check(out: str, planted: Planted) -> list[str]:
    """Reasons `subscription notices -o json` does not name the hard-expired repository `drill@drillbox`."""
    data = ftr._envelope(out).get("data")
    items = [i for i in walk_items(data) if i.get("guid") == planted.hard_guid]
    if not items:
        return ["no notice item carries the planted GUID"]
    for item in items:
        name, machine = item.get("name"), item.get("machine")
        if name == REF or (name == REPO_NAME and machine == MACHINE_NAME):
            return []
    return ["item names %r on %r, want %s" % (items[0].get("name"), items[0].get("machine"), REF)]


def retire_check(out: str, planted: Planted) -> list[str]:
    """Reasons the status summary still lists the retired licence or lost the other one."""
    if planted.hard_guid in out:
        return ["the retired licence is still in the status summary"]
    if planted.fresh_guid not in out:
        return ["the refresh-recommended licence is missing from the status summary"]
    return []


def patch_config(text: str, guid: str) -> str:
    """The config JSON with the machine `drillbox` guaranteed and the repository family `drill` placed on it, carrying `guid` as its grand tag. Everything else is kept."""
    config = json.loads(text)
    resources = config.setdefault("resources", {})
    machines = resources.get("machines") or {}
    if MACHINE_NAME not in machines:
        raise DrillError(
            "machine %s is not in the config; `machine add` did not write it" % MACHINE_NAME
        )
    resources.setdefault("repositories", {})[REPO_NAME] = {
        "placement": {"machine": MACHINE_NAME},
        "grand": TAG,
        "tags": {TAG: {"repositoryGuid": guid}},
    }
    return json.dumps(config, indent=2) + "\n"


def notice_cleanup_sql(
    email: str,
    user_id: str,
    sub_ids: Sequence[str],
    event_ids: Sequence[str],
) -> list[str]:
    """Deletes of what the notices work adds beyond `free_to_registered.cleanup`: the user's notices, the reminder-log rows of the exact recipient, the planted events and anything logged for the subscription (the retire event)."""
    for ident in (user_id, *sub_ids, *event_ids):
        if not UUID.match(ident):
            raise DrillError("refusing a non-UUID id in a delete: %r" % ident)
    subs = ", ".join(sql_literal(s) for s in sub_ids) or "''"
    ids = ", ".join(sql_literal(i) for i in event_ids) or "''"
    return [
        q("DELETE FROM account_notices WHERE user_id = $u", u=sql_literal(user_id)),
        q("DELETE FROM notification_reminder_log WHERE recipient_email = $e", e=sql_literal(email)),
        q("DELETE FROM event_log WHERE id IN ($i)", i=ids),
        q("DELETE FROM event_log WHERE subscription_id IN ($s)", s=subs),
    ]


def cleanup_notices(email: str, planted: Planted, rows: Rows, log: Callable[[str], None]) -> None:
    """Delete the notice-side rows of `email`'s user. DrillError when any is still present."""
    lit = sql_literal(email)
    for user in rows(q("SELECT id FROM users WHERE email = $e", e=lit)):
        user_id = str(user["id"])
        if not UUID.match(user_id):
            raise DrillError("refusing a non-UUID user id %r" % user_id)
        subs = [
            str(r["id"])
            for r in rows(
                q("SELECT id FROM subscriptions WHERE customer_id = $u", u=sql_literal(user_id))
            )
        ]
        for sql in notice_cleanup_sql(email, user_id, subs, planted.event_ids):
            rows(sql)
        left = rows(q("SELECT id FROM account_notices WHERE user_id = $u", u=sql_literal(user_id)))
        left += rows(
            q("SELECT id FROM notification_reminder_log WHERE recipient_email = $e", e=lit)
        )
        if planted.event_ids:
            ids = ", ".join(sql_literal(i) for i in planted.event_ids)
            left += rows(q("SELECT id FROM event_log WHERE id IN ($i)", i=ids))
        log("notice rows of user %s deleted, %d subscription(s)" % (user_id, len(subs)))
        if left:
            raise DrillError("notice, reminder-log or planted event rows remain after the delete")


def _config_path(config: str) -> pathlib.Path:
    return ftr.token_file(config).parent / ("%s.json" % config)


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _root_creds() -> tuple[str, str]:
    email = os.environ.get("ROOT_EMAIL") or ""
    if not email:
        raise DrillError("ROOT_EMAIL is not set (the deploy-bench profile binds it)")
    try:
        return email, deploy_bench.root_password()
    except deploy_bench.SeedError as exc:
        raise DrillError(str(exc)) from None


@dataclass
class Deps:
    http: ftr.Http = ftr._http
    call: Call = ftr._call
    rows: Rows = deploy_bench._d1_rows
    rdc: Rdc = ftr._rdc
    allowlist: Callable[[], int] = ftr._allowlist
    drop_token_file: Callable[[str], bool] = ftr._drop_token_file
    config_path: Callable[[str], pathlib.Path] = _config_path
    read: Callable[[pathlib.Path], str] = _read
    write: Callable[[pathlib.Path, str], None] = _write
    root_creds: Callable[[], tuple[str, str]] = _root_creds
    new_uuid: Callable[[], str] = lambda: str(uuid.uuid4())
    jar_path: Callable[[str], str] = lambda stamp: str(
        pathlib.Path(tempfile.gettempdir()) / ("ntc-jar-%s-%s.txt" % (stamp, secrets.token_hex(4)))
    )
    unlink: Callable[[str], None] = lambda path: pathlib.Path(path).unlink(missing_ok=True)
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    password: Callable[[], str] = lambda: secrets.token_urlsafe(24)
    token_hex: Callable[[], str] = lambda: secrets.token_hex(6)


@dataclass
class State:
    """What the steps hand to each other and to the cleanup."""

    stamp: str
    email: str
    config: str
    planted: Planted
    user_jar: str = ""
    sub_id: str = ""
    config_made: bool = False
    registered: bool = False
    since: str = ""


def _mails(d: Deps, st: State) -> list[dict]:
    return d.rows(
        q(
            "SELECT kind, subject, text_body FROM captured_emails WHERE recipient = $r "
            "AND created_at >= $since ORDER BY created_at",
            r=sql_literal(st.email),
            since=sql_literal(st.since),
        )
    )


def _login_jar(d: Deps, email: str, password: str, jar: str) -> tuple[int, dict]:
    return d.call("POST", API + "/auth/login", {"email": email, "password": password}, {}, jar)


def _accept_terms(d: Deps, jar: str) -> str:
    """Accept the Terms in `jar`'s session when they are not satisfied; returns what happened."""
    _, state = d.call("GET", API + "/portal/terms", None, {}, jar)
    if state.get("satisfied") is True:
        return "already"
    manifest = ftr.terms_manifest()
    status, _ = d.call(
        "POST",
        API + "/portal/terms/accept",
        {
            "version": manifest["version"],
            "sha256": manifest["sha256"],
            "locale": "en",
            "method": "web-checkbox",
        },
        {},
        jar,
    )
    if status != 201:
        raise DrillError("terms accept http=%d want 201" % status)
    return "accepted"


def _step_register(d: Deps, ev: Evidence, st: State, password: str) -> None:
    status, answer = d.http(API + "/auth/register", {"email": st.email, "password": password})
    st.registered = status in (201, 409)
    plan = (answer.get("subscription") or {}).get("planCode")
    ok = status == 201 and plan == "COMMUNITY"
    ev.add(2, "register", 0 if ok else 1, "http=%d email=%s plan=%s" % (status, st.email, plan))
    if not ok:
        raise DrillError("registration did not return 201 with COMMUNITY")


def _step_terms(d: Deps, ev: Evidence, st: State, password: str) -> None:
    status, _ = _login_jar(d, st.email, password, st.user_jar)
    if status != 200:
        ev.add(3, "terms", 1, "login http=%d" % status)
        raise DrillError("the throwaway user could not log in")
    try:
        what = _accept_terms(d, st.user_jar)
    except DrillError as exc:
        ev.add(3, "terms", 1, str(exc))
        raise
    ev.add(3, "terms", 0, "terms %s" % what)


def _step_config(d: Deps, ev: Evidence, st: State, base: Mapping[str, str], password: str) -> None:
    rc, _ = d.rdc(["config", "init", st.config, "--server", BENCH_ORIGIN], base)
    st.config_made = rc == 0
    if rc != 0:
        ev.add(4, "config", rc, "config init failed")
        raise DrillError("config init failed")
    login_env = dict(base)
    login_env[ftr.LOGIN_EMAIL_ENV], login_env[ftr.LOGIN_PW_ENV] = st.email, password
    rc, _ = d.rdc(
        ["--config", st.config, "subscription", "login", "--server", BENCH_ORIGIN], login_env
    )
    if rc != 0:
        ev.add(4, "config", rc, "subscription login failed")
        raise DrillError("subscription login failed")
    rc, _ = d.rdc(
        [
            "--config",
            st.config,
            "machine",
            "add",
            MACHINE_NAME,
            "--ip",
            MACHINE_IP,
            "--user",
            "drill",
        ],
        base,
    )
    if rc != 0:
        ev.add(4, "config", rc, "machine add failed")
        raise DrillError("machine add failed")
    path = d.config_path(st.config)
    try:
        d.write(path, patch_config(d.read(path), st.planted.hard_guid))
    except (OSError, ValueError, DrillError) as exc:
        ev.add(4, "config", 1, "config patch failed: %s" % type(exc).__name__)
        raise DrillError("the repository record was not written into the config") from None
    ev.add(
        4,
        "config",
        0,
        "name=%s machine=%s@%s repo=%s guid=%s"
        % (st.config, MACHINE_NAME, MACHINE_IP, REPO_NAME, st.planted.hard_guid[:8]),
    )


def _step_plant(d: Deps, ev: Evidence, st: State) -> None:
    lit = sql_literal(st.email)
    users = d.rows(q("SELECT id FROM users WHERE email = $e", e=lit))
    if len(users) != 1:
        ev.add(5, "plant", 1, "users rows=%d" % len(users))
        raise DrillError("the throwaway user row is missing")
    user_id = str(users[0]["id"])
    subs = d.rows(
        q("SELECT id, org_id FROM subscriptions WHERE customer_id = $u", u=sql_literal(user_id))
    )
    if len(subs) != 1:
        ev.add(5, "plant", 1, "subscription rows=%d" % len(subs))
        raise DrillError("the throwaway subscription row is missing")
    st.sub_id, org_id = str(subs[0]["id"]), str(subs[0].get("org_id") or "")
    refusal = shard_check(
        d.rows(
            q(
                "SELECT shard FROM subscription_shards WHERE subscription_id = $s",
                s=sql_literal(st.sub_id),
            )
        )
    )
    if refusal:
        ev.add(5, "plant", 1, refusal)
        raise DrillError(refusal)
    teams = d.rows(q("SELECT id FROM teams WHERE org_id = $o", o=sql_literal(org_id)))
    team_id = str(teams[0]["id"]) if teams else None
    ids = [d.new_uuid(), d.new_uuid()]
    statements = event_rows(st.planted, ids, st.sub_id, user_id, org_id, team_id, d.now())
    st.planted.event_ids = ids
    for sql in statements:
        d.rows(sql)
    ev.add(
        5,
        "plant",
        0,
        "subscription=%s shard=0 hard-expired=%s refresh-recommended=%s"
        % (st.sub_id, st.planted.hard_guid[:8], st.planted.fresh_guid[:8]),
    )


def _run_reminders(d: Deps, jar: str) -> tuple[int, dict]:
    path = API + "/admin/reminders/run"
    body = {"kinds": ["repo"]}
    status, answer = d.call("POST", path, body, {}, jar)
    code = answer.get("code") if isinstance(answer, dict) else None
    if status == 403 and code == ftr.TERMS_REQUIRED:
        _accept_terms(d, jar)
        status, answer = d.call("POST", path, body, {}, jar)
    return status, answer


def _step_root_run(d: Deps, ev: Evidence, st: State, wait_cron: bool) -> tuple[str, str] | None:
    """Open the root session and trigger the repo reminders; returns the root jar and creds for the rerun, or None with `--wait-cron`."""
    if wait_cron:
        deadline = WAIT_CRON_S
        waited = 0.0
        while waited <= deadline:
            if any(
                s in str(m.get("text_body") or "")
                for m in _mails(d, st)
                for s in st.planted.short()
            ):
                ev.add(6, "root-run", 0, "waited %ds for the cron tick" % int(waited))
                return None
            d.sleep(WAIT_CRON_POLL_S)
            waited += WAIT_CRON_POLL_S
        ev.add(6, "root-run", 1, "no mail after %ds of waiting for the cron" % int(waited))
        raise DrillError("the cron sent no mail")
    creds = d.root_creds()
    jar = d.jar_path(st.stamp + "-root")
    status, answer = d.call(
        "POST", API + "/auth/login", {"email": creds[0], "password": creds[1]}, {}, jar
    )
    if answer.get("requiresTwoFactor"):
        d.unlink(jar)
        ev.add(6, "root-run", 1, "the root login asks for two-factor")
        raise DrillError("the bench root has two-factor on; rerun with --wait-cron")
    if status != 200:
        d.unlink(jar)
        ev.add(6, "root-run", 1, "root login http=%d" % status)
        raise DrillError("root login failed")
    status, answer = _run_reminders(d, jar)
    ok = status == 200
    ev.add(6, "root-run", 0 if ok else 1, "reminders/run http=%d" % status)
    if not ok:
        d.unlink(jar)
        raise DrillError("the root reminder run was refused")
    return jar, creds[0]


def _step_mail(d: Deps, ev: Evidence, st: State) -> None:
    bad = mail_check(_mails(d, st), st.planted)
    ev.add(7, "mail", 1 if bad else 0, "; ".join(bad) or "one digest, both GUIDs, no name")
    if bad:
        raise DrillError("the reminder mail is wrong")


def _step_unread(d: Deps, ev: Evidence, st: State) -> None:
    status, answer = d.call("GET", API + "/portal/notices/unread-count", None, {}, st.user_jar)
    count = answer.get("count")
    ok = status == 200 and count == 1
    ev.add(8, "unread", 0 if ok else 1, "http=%d count=%r want 1" % (status, count))
    if not ok:
        raise DrillError("the unread count is not 1")


def _step_notices(d: Deps, ev: Evidence, st: State, base: Mapping[str, str]) -> None:
    rc, out = d.rdc(["--config", st.config, "subscription", "notices", "-o", "json"], base)
    bad = notices_check(out, st.planted) if rc == 0 else ["notices exit=%d" % rc]
    ev.add(9, "notices", 1 if bad else 0, "; ".join(bad) or "names %s" % REF)
    if bad:
        raise DrillError("the notices verb does not name the repository")


def _step_rerun(d: Deps, ev: Evidence, st: State, root: tuple[str, str] | None) -> None:
    if root is None:
        ev.add(10, "rerun", 0, "skipped under --wait-cron")
        return
    jar, _ = root
    status, _ = _run_reminders(d, jar)
    mails = _mails(d, st)
    named = [
        m for m in mails if any(s in str(m.get("text_body") or "") for s in st.planted.short())
    ]
    bad = (["reminders/run http=%d" % status] if status != 200 else []) + (
        ["%d mails name a planted GUID after the second run, want 1" % len(named)]
        if len(named) != 1
        else []
    )
    ev.add(10, "rerun", 1 if bad else 0, "; ".join(bad) or "no second mail (same bucket)")
    if bad:
        raise DrillError("the second reminder run mailed again")


def _step_retire(d: Deps, ev: Evidence, st: State, base: Mapping[str, str]) -> None:
    guid = st.planted.hard_guid
    rc, _ = d.rdc(["--config", st.config, "subscription", "retire", guid, "--yes"], base)
    if rc != 0:
        ev.add(11, "retire", rc, "retire exit=%d want 0" % rc)
        raise DrillError("subscription retire failed")
    src, out = d.rdc(["--config", st.config, "subscription", "status", "-o", "json"], base)
    bad = retire_check(out, st.planted) if src == 0 else ["status exit=%d" % src]
    ev.add(
        11, "retire", 1 if bad else 0, "; ".join(bad) or "retired %s, summary dropped it" % guid[:8]
    )
    if bad:
        raise DrillError("the retired licence is still reported")


def run(
    dry_run: bool,
    deps: Deps | None = None,
    env: Mapping[str, str] | None = None,
    wait_cron: bool = False,
) -> int:
    d = deps or Deps()
    base = {k: v for k, v in (os.environ if env is None else env).items() if k not in ftr.SCRUBBED}
    ev = Evidence()
    started = d.now()
    stamp = ftr.stamp_now(started)
    st = State(
        stamp=stamp,
        email=stamp_address(stamp),
        config="ntc-" + stamp,
        planted=Planted(d.new_uuid(), d.new_uuid(), "ntc-mid-" + d.token_hex()),
        since=datetime.fromtimestamp(started.timestamp() - CLOCK_SKEW_S, UTC).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
    )
    if dry_run:
        for label, name in STEPS:
            print("DRY-RUN STEP %s %s config=%s email=%s" % (label, name, st.config, st.email))
        return 0
    password = d.password()
    st.user_jar = d.jar_path(stamp)
    root_jar = ""
    try:
        rc = d.allowlist()
        ev.add(1, "allowlist", rc)
        if rc != 0:
            raise DrillError("bench allowlist refresh failed")
        _step_register(d, ev, st, password)
        _step_terms(d, ev, st, password)
        _step_config(d, ev, st, base, password)
        _step_plant(d, ev, st)
        root = _step_root_run(d, ev, st, wait_cron)
        root_jar = root[0] if root else ""
        _step_mail(d, ev, st)
        _step_unread(d, ev, st)
        _step_notices(d, ev, st, base)
        _step_rerun(d, ev, st, root)
        _step_retire(d, ev, st, base)
    except DrillError as exc:
        ev.failed = True
        print("drill: %s" % exc, file=sys.stderr)
    finally:
        notes: list[str] = []
        crc = 0
        for jar in (st.user_jar, root_jar):
            if jar:
                d.unlink(jar)
        if st.registered:
            for label, action in (
                ("notices", lambda: cleanup_notices(st.email, st.planted, d.rows, notes.append)),
                ("user", lambda: ftr.cleanup(st.email, d.rows, notes.append)),
            ):
                try:
                    action()
                except DrillError as exc:
                    crc = 1
                    notes.append("%s: %s" % (label, exc))
        if st.config_made:
            rc, _ = d.rdc(["config", "delete", st.config, "-y"], base)
            notes.append("config %s deleted rc=%d" % (st.config, rc))
            crc = crc or rc
            if d.drop_token_file(st.config):
                notes.append("token file of %s removed" % st.config)
        ev.add(12, "cleanup", crc, "; ".join(notes) or "nothing to clean")
    return 1 if ev.failed else 0


def _reexec_under_profile(argv: Sequence[str]) -> int | None:
    if PROFILE in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(","):
        return None
    env = dict(os.environ)
    ci = str(paths.repo_root() / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "exec",
            "--profile",
            PROFILE,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.notices_drill",
            *argv,
        ],
        env=env,
        check=False,
    ).returncode


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    if any(a not in ("--dry-run", "--wait-cron") for a in args):
        print("usage: notices_drill [--dry-run] [--wait-cron]", file=sys.stderr)
        return 2
    dry = "--dry-run" in args
    if not dry:
        rebound = _reexec_under_profile(args)
        if rebound is not None:
            return rebound
    return run(dry, wait_cron="--wait-cron" in args)


if __name__ == "__main__":
    sys.exit(main())
