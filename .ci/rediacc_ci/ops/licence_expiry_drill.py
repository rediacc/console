"""Bench drill: a delegation cert 7 days from its end becomes ONE owner mail, an unread notice and ONE sales digest line, then nothing more on a second run.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-bench --profile bench-login -- python3 -m rediacc_ci.ops.licence_expiry_drill [--dry-run]

BENCH ONLY. The target is `BENCH_ORIGIN`; no other server is accepted. The run re-executes itself under the `deploy-bench` and `bench-login` Bitwarden profiles (it needs `CF_GLOBAL_API_KEY` and `CF_EMAIL` for the D1 queries, `ROOT_EMAIL` plus `BENCH_ROOT_PASSWORD` for the root session and `SALES_NOTIFY_EMAIL` for the sales inbox the digest goes to) unless both are already bound. The `bench-login` profile binds `REDIACC_BENCH_TOTP_SEED`, which answers the bench root's two-factor challenge (`POST /auth/2fa/verify`, one retry with the next window's code); the seed is never printed. Plan: agent/plans/PLAN-licence-expiry-notices.md, box L1.

THE STEPS, each printing one evidence line `STEP <n> <name> rc=<rc> <detail>`:

  1  allowlist  `bench_access add-current`, so this host passes the bench WAF rule.
  2  register   `POST /auth/register` with a throwaway `lexp+<stamp>@rediacc.io` address and a random password.
  3  terms      A login with a cookie jar, then `POST /portal/terms/accept` when the Terms are not satisfied.
  4  plant      One active `delegation_certs` row for the user's subscription, valid until now + 7 days minus one hour (the 7-day reminder threshold and the digest's 7-day stage). The subscription's tenant shard is read first and a shard other than 0 is refused.
  5  reminders  The root session (`ROOT_EMAIL`, `BENCH_ROOT_PASSWORD`) calls `POST /admin/reminders/run {kinds:['delegation']}`.
  6  digest     The root session calls `POST /admin/sales-digest/run`; the answer must count at least one line.
  7  owner-mail Exactly one `captured_emails` row to the owner names the cert's `validUntil` date.
  8  sales-mail Exactly one `captured_emails` row to `SALES_NOTIFY_EMAIL` names the planted cert (its 8-character id) and the org's name.
  9  unread     With the user's session `GET /portal/notices/unread-count` is 1.
  10 rerun      Both root runs again: the digest answers 0 lines and no second owner or sales mail names the cert.
  11 cleanup    Always runs. Deletes the planted cert, the notices, the reminder-log rows (the owner's and the sales digest's), the sales mail naming the planted cert, then the user, its organizations, subscriptions and captured mail (`free_to_registered.cleanup`), and proves the user is gone.

The password and every token travel only in a child environment or a request body, never on argv and never printed. Exit 0 only when every step held; cleanup failing is a failure.
"""

from __future__ import annotations

import os
import pathlib
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
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
    Rows,
    q,
    sql_literal,
)
from rediacc_ci.well_known import INFRA_DOMAIN

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

PROFILE = "deploy-bench"
ADDRESS = re.compile(r"^lexp\+\d{14}@" + re.escape(INFRA_DOMAIN) + "$")
CLOCK_SKEW_S = 60
CERT_LEAD = timedelta(days=7) - timedelta(hours=1)
STEPS = (
    ("1", "allowlist"),
    ("2", "register"),
    ("3", "terms"),
    ("4", "plant"),
    ("5", "reminders"),
    ("6", "digest"),
    ("7", "owner-mail"),
    ("8", "sales-mail"),
    ("9", "unread"),
    ("10", "rerun"),
    ("11", "cleanup"),
)

Call = ftr.Call


def stamp_address(stamp: str) -> str:
    """The throwaway address of one run."""
    return "lexp+%s@%s" % (stamp, INFRA_DOMAIN)


def iso(moment: datetime) -> str:
    """`Date.toISOString()` spelling, the form the cert table stores."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (
        moment.microsecond // 1000
    )


@dataclass
class Planted:
    """The one cert the drill plants, so the checks and the cleanup name exactly it."""

    cert_id: str
    valid_until: str = ""

    @property
    def short(self) -> str:
        return self.cert_id[:8]

    @property
    def day(self) -> str:
        return self.valid_until[:10]


def cert_insert(planted: Planted, sub_id: str, now: datetime) -> str:
    """The INSERT of one active cert shaped like a `delegation_certs` row (private/account/src/db/schema.ts): placeholder key and signature, `validUntil` a hair under 7 days away."""
    for ident in (planted.cert_id, sub_id):
        if not UUID.match(ident):
            raise DrillError("refusing a non-UUID id in an insert: %r" % ident)
    planted.valid_until = iso(now + CERT_LEAD)
    return q(
        "INSERT INTO delegation_certs (id, subscription_id, delegated_public_key, signed_payload, "
        "signature, public_key_id, valid_from, valid_until, genesis_hash, genesis_sequence, "
        "max_total_issuances, status, created_at) VALUES ($id, $sub, 'lexp-pk', '{}', 'lexp-sig', "
        "'lexp-kid', $vfrom, $until, 'lexp-genesis', 0, 100, 'active', $created)",
        id=sql_literal(planted.cert_id),
        sub=sql_literal(sub_id),
        vfrom=sql_literal(iso(now - timedelta(days=300))),
        until=sql_literal(planted.valid_until),
        created=sql_literal(iso(now)),
    )


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


def owner_mail_check(mails: Sequence[dict], planted: Planted) -> list[str]:
    """Reasons the owner's captured mails are not exactly one naming the cert's `validUntil` date. Empty when it holds."""
    named = [m for m in mails if planted.day in str(m.get("text_body") or "")]
    if len(named) != 1:
        return ["%d owner mails name %s, want exactly 1" % (len(named), planted.day)]
    return []


def sales_mail_check(mails: Sequence[dict], planted: Planted, org_name: str) -> list[str]:
    """Reasons the sales inbox does not hold exactly one digest mail naming the planted cert, with the org's name on its line."""
    named = [m for m in mails if planted.short in str(m.get("text_body") or "")]
    if len(named) != 1:
        return ["%d sales mails name cert %s, want exactly 1" % (len(named), planted.short)]
    text = str(named[0].get("text_body") or "")
    lines = [ln for ln in text.splitlines() if planted.short in ln]
    if not org_name or not any(org_name in ln for ln in lines):
        return ["the digest line of cert %s does not name the org %r" % (planted.short, org_name)]
    return []


def cleanup_sql(
    email: str,
    sales: str,
    user_id: str,
    sub_ids: Sequence[str],
    planted: Planted,
    since: str,
) -> list[str]:
    """Deletes of what this drill adds beyond `free_to_registered.cleanup`: the planted cert, the user's notices, the reminder-log rows of the exact owner address and of the subscription (the digest's), and the sales mail that names the planted cert and is no older than the run."""
    for ident in (user_id, planted.cert_id, *sub_ids):
        if not UUID.match(ident):
            raise DrillError("refusing a non-UUID id in a delete: %r" % ident)
    subs = ", ".join(sql_literal(s) for s in sub_ids) or "''"
    return [
        q("DELETE FROM delegation_certs WHERE id = $c", c=sql_literal(planted.cert_id)),
        q("DELETE FROM delegation_certs WHERE subscription_id IN ($s)", s=subs),
        q("DELETE FROM account_notices WHERE user_id = $u", u=sql_literal(user_id)),
        q(
            "DELETE FROM notification_reminder_log WHERE recipient_email = $e "
            "OR subscription_id IN ($s)",
            e=sql_literal(email),
            s=subs,
        ),
        q(
            "DELETE FROM captured_emails WHERE recipient = $r AND created_at >= $since "
            "AND text_body LIKE $like",
            r=sql_literal(sales),
            since=sql_literal(since),
            like=sql_literal("%" + planted.short + "%"),
        ),
    ]


def leftover_sql(
    email: str, sales: str, user_id: str, planted: Planted, since: str, subs: str
) -> list[str]:
    """The reads that prove `cleanup_sql` removed everything."""
    return [
        q("SELECT id FROM delegation_certs WHERE id = $c", c=sql_literal(planted.cert_id)),
        q("SELECT id FROM account_notices WHERE user_id = $u", u=sql_literal(user_id)),
        q(
            "SELECT id FROM notification_reminder_log WHERE recipient_email = $e "
            "OR subscription_id IN ($s)",
            e=sql_literal(email),
            s=subs,
        ),
        q(
            "SELECT recipient FROM captured_emails WHERE recipient = $r AND created_at >= $since "
            "AND text_body LIKE $like",
            r=sql_literal(sales),
            since=sql_literal(since),
            like=sql_literal("%" + planted.short + "%"),
        ),
    ]


NO_USER_ID = "00000000-0000-0000-0000-000000000000"


def cleanup_licence(
    email: str,
    sales: str,
    planted: Planted,
    since: str,
    rows: Rows,
    log: Callable[[str], None],
) -> None:
    """Delete the cert, notice, reminder-log and sales-mail rows of `email`'s user. DrillError when any is still present."""
    found = rows(q("SELECT id FROM users WHERE email = $e", e=sql_literal(email)))
    targets: list[tuple[str, str | None]] = [(str(u["id"]), None) for u in found] or [
        (NO_USER_ID, "no user row")
    ]
    for user_id, note in targets:
        if not UUID.match(user_id):
            raise DrillError("refusing a non-UUID user id %r" % user_id)
        subs = (
            [
                str(r["id"])
                for r in rows(
                    q("SELECT id FROM subscriptions WHERE customer_id = $u", u=sql_literal(user_id))
                )
            ]
            if note is None
            else []
        )
        for sql in cleanup_sql(email, sales, user_id, subs, planted, since):
            rows(sql)
        sub_list = ", ".join(sql_literal(s) for s in subs) or "''"
        left: list[dict] = []
        for sql in leftover_sql(email, sales, user_id, planted, since, sub_list):
            left += rows(sql)
        log(
            "licence rows of %s deleted, %d subscription(s)%s"
            % (user_id, len(subs), " (%s)" % note if note else "")
        )
        if left:
            raise DrillError(
                "cert, notice, reminder-log or sales-mail rows remain after the delete"
            )


def _root_creds() -> tuple[str, str]:
    email = os.environ.get("ROOT_EMAIL") or ""
    if not email:
        raise DrillError("ROOT_EMAIL is not set (the deploy-bench profile binds it)")
    try:
        return email, deploy_bench.root_password()
    except deploy_bench.SeedError as exc:
        raise DrillError(str(exc)) from None


def _sales_address(env: Mapping[str, str]) -> str:
    sales = env.get("SALES_NOTIFY_EMAIL") or ""
    if not sales:
        raise DrillError("SALES_NOTIFY_EMAIL is not set (the deploy-bench profile binds it)")
    return sales


@dataclass
class Deps:
    http: ftr.Http = ftr._http
    call: Call = ftr._call
    rows: Rows = deploy_bench._d1_rows
    allowlist: Callable[[], int] = ftr._allowlist
    root_creds: Callable[[], tuple[str, str]] = _root_creds
    root_seed: Callable[[], str] = ftr.root_seed_from_env
    sleep: Callable[[float], None] = time.sleep
    new_uuid: Callable[[], str] = lambda: str(uuid.uuid4())
    jar_path: Callable[[str], str] = lambda stamp: str(
        pathlib.Path(tempfile.gettempdir()) / ("lexp-jar-%s-%s.txt" % (stamp, secrets.token_hex(4)))
    )
    unlink: Callable[[str], None] = lambda path: pathlib.Path(path).unlink(missing_ok=True)
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    password: Callable[[], str] = lambda: secrets.token_urlsafe(24)


@dataclass
class State:
    """What the steps hand to each other and to the cleanup."""

    stamp: str
    email: str
    sales: str
    planted: Planted
    user_jar: str = ""
    # Set the moment the root jar file is created, so the cleanup unlinks it whichever later step raises.
    root_jar: str = ""
    sub_id: str = ""
    org_name: str = ""
    registered: bool = False
    since: str = ""


def _owner_mails(d: Deps, st: State) -> list[dict]:
    return d.rows(
        q(
            "SELECT kind, subject, text_body FROM captured_emails WHERE recipient = $r "
            "AND created_at >= $since ORDER BY created_at",
            r=sql_literal(st.email),
            since=sql_literal(st.since),
        )
    )


def _sales_mails(d: Deps, st: State) -> list[dict]:
    return d.rows(
        q(
            "SELECT kind, subject, text_body FROM captured_emails WHERE recipient = $r "
            "AND created_at >= $since ORDER BY created_at",
            r=sql_literal(st.sales),
            since=sql_literal(st.since),
        )
    )


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
    try:
        status, answer = d.http(API + "/auth/register", {"email": st.email, "password": password})
    except DrillError:
        st.registered = True  # no answer: the server may still have created the user
        raise
    # A 409 means the address already belongs to an account this run did not create, so only a created account (or a 5xx that may have created one) is cleaned by email.
    st.registered = status == 201 or status >= 500
    plan = (answer.get("subscription") or {}).get("planCode")
    ok = status == 201 and plan == "COMMUNITY"
    ev.add(2, "register", 0 if ok else 1, "http=%d email=%s plan=%s" % (status, st.email, plan))
    if not ok:
        raise DrillError("registration did not return 201 with COMMUNITY")


def _step_terms(d: Deps, ev: Evidence, st: State, password: str) -> None:
    status, _ = d.call(
        "POST", API + "/auth/login", {"email": st.email, "password": password}, {}, st.user_jar
    )
    if status != 200:
        ev.add(3, "terms", 1, "login http=%d" % status)
        raise DrillError("the throwaway user could not log in")
    try:
        what = _accept_terms(d, st.user_jar)
    except DrillError as exc:
        ev.add(3, "terms", 1, str(exc))
        raise
    ev.add(3, "terms", 0, "terms %s" % what)


def _step_plant(d: Deps, ev: Evidence, st: State) -> None:
    users = d.rows(q("SELECT id FROM users WHERE email = $e", e=sql_literal(st.email)))
    if len(users) != 1:
        ev.add(4, "plant", 1, "users rows=%d" % len(users))
        raise DrillError("the throwaway user row is missing")
    user_id = str(users[0]["id"])
    subs = d.rows(q("SELECT id FROM subscriptions WHERE customer_id = $u", u=sql_literal(user_id)))
    if len(subs) != 1:
        ev.add(4, "plant", 1, "subscription rows=%d" % len(subs))
        raise DrillError("the throwaway subscription row is missing")
    st.sub_id = str(subs[0]["id"])
    refusal = shard_check(
        d.rows(
            q(
                "SELECT shard FROM subscription_shards WHERE subscription_id = $s",
                s=sql_literal(st.sub_id),
            )
        )
    )
    if refusal:
        ev.add(4, "plant", 1, refusal)
        raise DrillError(refusal)
    # The digest names the org registered for the customer (subscriptions.org_id is null for a
    # self-registered user), so the drill reads the same row.
    orgs = d.rows(
        q("SELECT id, name FROM organizations WHERE customer_id = $u", u=sql_literal(user_id))
    )
    if len(orgs) != 1:
        ev.add(4, "plant", 1, "organization rows=%d for the customer" % len(orgs))
        raise DrillError("the throwaway user's organization is not exactly one row")
    st.org_name = str(orgs[0].get("name") or "")
    if not st.org_name:
        ev.add(4, "plant", 1, "organization %r has no name" % orgs[0].get("id"))
        raise DrillError("the throwaway organization has no name")
    try:
        statement = cert_insert(st.planted, st.sub_id, d.now())
    except DrillError as exc:
        ev.add(4, "plant", 1, str(exc))
        raise
    d.rows(statement)
    ev.add(
        4,
        "plant",
        0,
        "subscription=%s shard=0 cert=%s validUntil=%s"
        % (st.sub_id, st.planted.short, st.planted.valid_until),
    )


def _root_post(d: Deps, jar: str, path: str, body: dict) -> tuple[int, dict]:
    status, answer = d.call("POST", path, body, {}, jar)
    code = answer.get("code") if isinstance(answer, dict) else None
    if status == 403 and code == ftr.TERMS_REQUIRED:
        _accept_terms(d, jar)
        status, answer = d.call("POST", path, body, {}, jar)
    return status, answer


def _root_runs(d: Deps, jar: str) -> tuple[tuple[int, dict], tuple[int, dict]]:
    """The reminder run for the delegation kind, then the digest run."""
    return (
        _root_post(d, jar, API + "/admin/reminders/run", {"kinds": ["delegation"]}),
        _root_post(d, jar, API + "/admin/sales-digest/run", {}),
    )


def _open_root(d: Deps, ev: Evidence, st: State) -> str:
    creds = d.root_creds()
    jar = d.jar_path(st.stamp + "-root")
    st.root_jar = jar
    status, answer = d.call(
        "POST", API + "/auth/login", {"email": creds[0], "password": creds[1]}, {}, jar
    )
    if status == 200 and answer.get("requiresTwoFactor"):
        try:
            ftr.verify_root_challenge(
                d.call, jar, answer, d.root_seed, d.sleep, lambda: d.now().timestamp()
            )
        except DrillError as exc:
            d.unlink(jar)
            ev.add(5, "reminders", 1, "the root two-factor challenge failed: %s" % exc)
            raise
    elif status != 200:
        d.unlink(jar)
        ev.add(5, "reminders", 1, "root login http=%d" % status)
        raise DrillError("root login failed")
    return jar


def _step_root_runs(d: Deps, ev: Evidence, st: State) -> str:
    """Open the root session, run the delegation reminders (step 5) and the digest (step 6); returns the root jar."""
    jar = _open_root(d, ev, st)
    (r_status, _r_answer), (d_status, d_answer) = _root_runs(d, jar)
    ev.add(5, "reminders", 0 if r_status == 200 else 1, "reminders/run http=%d" % r_status)
    if r_status != 200:
        raise DrillError("the root reminder run was refused")
    lines = d_answer.get("lines") if isinstance(d_answer, dict) else None
    ok = d_status == 200 and isinstance(lines, int) and lines >= 1
    ev.add(
        6,
        "digest",
        0 if ok else 1,
        "sales-digest/run http=%d lines=%r want >= 1" % (d_status, lines),
    )
    if not ok:
        raise DrillError("the sales digest run mailed no line")
    return jar


def _step_owner_mail(d: Deps, ev: Evidence, st: State) -> None:
    bad = owner_mail_check(_owner_mails(d, st), st.planted)
    ev.add(
        7,
        "owner-mail",
        1 if bad else 0,
        "; ".join(bad) or "one owner mail names %s" % st.planted.day,
    )
    if bad:
        raise DrillError("the owner mail is wrong")


def _step_sales_mail(d: Deps, ev: Evidence, st: State) -> None:
    bad = sales_mail_check(_sales_mails(d, st), st.planted, st.org_name)
    ev.add(
        8,
        "sales-mail",
        1 if bad else 0,
        "; ".join(bad) or "one digest names cert %s and org %r" % (st.planted.short, st.org_name),
    )
    if bad:
        raise DrillError("the sales digest mail is wrong")


def _step_unread(d: Deps, ev: Evidence, st: State) -> None:
    status, answer = d.call("GET", API + "/portal/notices/unread-count", None, {}, st.user_jar)
    count = answer.get("count")
    ok = status == 200 and count == 1
    ev.add(9, "unread", 0 if ok else 1, "http=%d count=%r want 1" % (status, count))
    if not ok:
        raise DrillError("the unread count is not 1")


def _step_rerun(d: Deps, ev: Evidence, st: State, jar: str) -> None:
    (r_status, _), (d_status, d_answer) = _root_runs(d, jar)
    lines = d_answer.get("lines") if isinstance(d_answer, dict) else None
    bad = [
        "%s/run http=%d" % (name, status)
        for name, status in (("reminders", r_status), ("sales-digest", d_status))
        if status != 200
    ]
    if d_status == 200 and lines != 0:
        bad.append("the second digest run mailed %r lines, want 0" % lines)
    bad += owner_mail_check(_owner_mails(d, st), st.planted)
    bad += sales_mail_check(_sales_mails(d, st), st.planted, st.org_name)
    ev.add(10, "rerun", 1 if bad else 0, "; ".join(bad) or "no second mail, digest lines=0")
    if bad:
        raise DrillError("the second run mailed again")


def run(
    dry_run: bool,
    deps: Deps | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    d = deps or Deps()
    environ = os.environ if env is None else env
    ev = Evidence()
    started = d.now()
    stamp = ftr.stamp_now(started)
    st = State(
        stamp=stamp,
        email=stamp_address(stamp),
        sales=environ.get("SALES_NOTIFY_EMAIL") or "",
        planted=Planted(d.new_uuid()),
        since=datetime.fromtimestamp(started.timestamp() - CLOCK_SKEW_S, UTC).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
    )
    if dry_run:
        for label, name in STEPS:
            print("DRY-RUN STEP %s %s email=%s" % (label, name, st.email))
        return 0
    password = d.password()
    st.user_jar = d.jar_path(stamp)
    try:
        _sales_address(environ)
        rc = d.allowlist()
        ev.add(1, "allowlist", rc)
        if rc != 0:
            raise DrillError("bench allowlist refresh failed")
        _step_register(d, ev, st, password)
        _step_terms(d, ev, st, password)
        _step_plant(d, ev, st)
        root_jar = _step_root_runs(d, ev, st)
        _step_owner_mail(d, ev, st)
        _step_sales_mail(d, ev, st)
        _step_unread(d, ev, st)
        _step_rerun(d, ev, st, root_jar)
    except DrillError as exc:
        ev.failed = True
        print("drill: %s" % exc, file=sys.stderr)
    finally:
        notes: list[str] = []
        crc = 0
        for jar in (st.user_jar, st.root_jar):
            if jar:
                d.unlink(jar)
        if st.registered:
            for label, action in (
                (
                    "licence",
                    lambda: cleanup_licence(
                        st.email, st.sales, st.planted, st.since, d.rows, notes.append
                    ),
                ),
                ("user", lambda: ftr.cleanup(st.email, d.rows, notes.append)),
            ):
                try:
                    action()
                except DrillError as exc:
                    crc = 1
                    notes.append("%s: %s" % (label, exc))
        ev.add(11, "cleanup", crc, "; ".join(notes) or "nothing to clean")
    return 1 if ev.failed else 0


def _reexec_under_profile(argv: Sequence[str]) -> int | None:
    bound = (os.environ.get("REDIACC_BWS_PROFILES") or "").split(",")
    if PROFILE in bound and ftr.TWO_FACTOR_PROFILE in bound:
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
            "--profile",
            ftr.TWO_FACTOR_PROFILE,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.licence_expiry_drill",
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
    if any(a != "--dry-run" for a in args):
        print("usage: licence_expiry_drill [--dry-run]", file=sys.stderr)
        return 2
    dry = "--dry-run" in args
    if not dry:
        rebound = _reexec_under_profile(args)
        if rebound is not None:
            return rebound
    return run(dry)


if __name__ == "__main__":
    sys.exit(main())
