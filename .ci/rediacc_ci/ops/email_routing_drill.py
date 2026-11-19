"""Bench drill: mail routing by class. A contact form, a signed urgent Stripe dispute and a signed expired checkout land in `captured_emails` with the right sender, Reply-To, prefix and urgency, and the daily digest mails the checkout once and then nothing.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-bench-eu --profile bench-login-eu -- env PYTHONPATH=.ci python3 -m rediacc_ci.ops.email_routing_drill [--dry-run]

BENCH ONLY. The target is `BENCH_ORIGIN`; no other server is accepted. The run re-executes itself under the `deploy-bench-eu` and `bench-login-eu` Bitwarden profiles (`CF_GLOBAL_API_KEY` and `CF_EMAIL` for the D1 queries, `STRIPE_SANDBOX_WEBHOOK_SECRET` to sign the two events, `ROOT_EMAIL` plus `BENCH_ROOT_PASSWORD` and `BENCH_ROOT_TOTP_SEED` for the root session that runs the digest) unless both are already bound. A missing sandbox webhook secret is a named error before any request. Secrets travel only in a child environment or a request body; the Stripe signature header carries an HMAC, never the secret. Plan: agent/plans/PLAN-email-sender-separation.md, box R1.

THE STEPS, each printing one evidence line `STEP <n> <name> rc=<rc> <detail>`:

  1  allowlist  `bench_access add-current`, so this host passes the bench WAF rule.
  2  contact    `POST /contact/submit` from `drill+<stamp>@rediacc.io`; the notification row is From the contact sender, Reply-To the drill address, `[Contact bench] ...`, To the contact list; the confirmation row is From the transactional sender with Reply-To the contact list.
  3  dispute    A signed `charge.dispute.created`; a row From the alerts sender, `[System bench] ...`, To the alerts list, appears within 60 s.
  4  checkout   A signed `checkout.session.expired`; no row names the session before the digest run (it was queued, not sent).
  5  digest     The root session calls `POST /admin/alert-digest/run`; the answer counts at least one item and exactly one `Daily digest` row names the session.
  6  rerun      The digest again: the answer counts 0 and no second digest row exists.
  7  cleanup    Always runs. Deletes the contact submission, the webhook markers, the digest items and every captured row this run made, and proves none is left.

Prints one JSON summary line after the steps. Exit 0 only when every step held; cleanup failing is a failure.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.ops import deploy_bench
from rediacc_ci.ops import free_to_registered as ftr
from rediacc_ci.ops.free_to_registered import API, DrillError, Evidence, Rows, q, sql_literal
from rediacc_ci.well_known import BENCH_ORIGIN, INFRA_DOMAIN

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

PROFILE = "deploy-bench-eu"
ADDRESS = re.compile(r"^drill\+\d{14}@" + re.escape(INFRA_DOMAIN) + "$")
CLOCK_SKEW_S = 60
ALERT_WAIT_S = 60.0
ALERT_POLL_S = 3.0
HOOK_KEY_ENV = "STRIPE_SANDBOX_WEBHOOK_SECRET"
CONTACT_FROM = "contact@notify.rediacc.cloud"
ALERTS_FROM = "alerts@notify.rediacc.cloud"
NOREPLY_FROM = "noreply@notify.rediacc.cloud"
CONTACT_TO = "contact@rediacc.com"
ALERTS_TO = "alerts@rediacc.io"
CONTACT_PREFIX = "[Contact bench] "
SYSTEM_PREFIX = "[System bench] "
DIGEST_MARK = "Daily digest"
STEPS = (
    ("1", "allowlist"),
    ("2", "contact"),
    ("3", "dispute"),
    ("4", "checkout"),
    ("5", "digest"),
    ("6", "rerun"),
    ("7", "cleanup"),
)

Webhook = Callable[[str, str], int]


def stamp_address(stamp: str) -> str:
    """The throwaway submitter address of one run."""
    return "drill+%s@%s" % (stamp, INFRA_DOMAIN)


def bench_target(origin: str = BENCH_ORIGIN) -> str:
    """The origin the drill talks to; DrillError for anything but the bench origin."""
    if origin != BENCH_ORIGIN:
        raise DrillError(
            "refusing a non-bench target %r; only %s is accepted" % (origin, BENCH_ORIGIN)
        )
    return origin


def require_secret(env: Mapping[str, str]) -> str:
    """The sandbox webhook secret, or a named DrillError before any request."""
    value = env.get(HOOK_KEY_ENV) or ""
    if not value:
        raise DrillError(
            "%s is not set (the %s profile binds it when bench has a Stripe sandbox pair)"
            % (HOOK_KEY_ENV, PROFILE)
        )
    return value


def stripe_signature(secret: str, body: str, timestamp: int) -> str:
    """Stripe's `Stripe-Signature` value: `t=<ts>,v1=<hex HMAC-SHA256 of "<ts>.<body>">`."""
    mac = hmac.new(secret.encode(), ("%d.%s" % (timestamp, body)).encode(), hashlib.sha256)
    return "t=%d,v1=%s" % (timestamp, mac.hexdigest())


def verify_signature(secret: str, body: str, header: str, now: int, tolerance: int = 300) -> bool:
    """Stripe's verification, as the account Worker performs it: the timestamp in tolerance and one `v1` equal to the recomputed HMAC."""
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        stamp = int(parts.get("t", ""))
    except ValueError:
        return False
    if abs(now - stamp) > tolerance:
        return False
    return hmac.compare_digest(
        parts.get("v1", ""), stripe_signature(secret, body, stamp).split("v1=")[1]
    )


def event_body(event_id: str, kind: str, obj: dict) -> str:
    """The raw JSON of one Stripe event; the exact string that is signed and posted."""
    return json.dumps(
        {"id": event_id, "object": "event", "type": kind, "data": {"object": obj}},
        separators=(",", ":"),
    )


def dispute_object(dispute_id: str) -> dict:
    """A `stripeDisputeObjectSchema` object (private/account/src/types/webhook.ts)."""
    return {
        "id": dispute_id,
        "charge": "ch_drill",
        "amount": 1000,
        "currency": "eur",
        "reason": "fraudulent",
        "status": "needs_response",
    }


def checkout_object(session_id: str) -> dict:
    """A `stripeCheckoutSessionObjectSchema` object with no customer."""
    return {"id": session_id, "metadata": {}}


def row_count(answer: Mapping[str, object]) -> int | None:
    """The item count of an `/admin/alert-digest/run` answer: an integer or a list's length; None when absent."""
    items = answer.get("items")
    if isinstance(items, bool):
        return None
    if isinstance(items, int):
        return items
    if isinstance(items, list):
        return len(items)
    return None


def contact_checks(mails: Sequence[dict], address: str) -> list[str]:
    """Reasons the contact notification and confirmation rows are wrong. Empty when both hold."""
    bad: list[str] = []
    note = [
        m
        for m in mails
        if m.get("recipient") == CONTACT_TO and address in str(m.get("text_body") or "")
    ]
    if len(note) != 1:
        bad.append("%d notification rows to %s name %s, want 1" % (len(note), CONTACT_TO, address))
    else:
        row = note[0]
        if row.get("from_address") != CONTACT_FROM:
            bad.append("notification From %r, want %r" % (row.get("from_address"), CONTACT_FROM))
        if row.get("reply_to") != address:
            bad.append("notification Reply-To %r, want the drill address" % row.get("reply_to"))
        if not str(row.get("subject") or "").startswith(CONTACT_PREFIX):
            bad.append("notification subject %r lacks %r" % (row.get("subject"), CONTACT_PREFIX))
    conf = [m for m in mails if m.get("recipient") == address]
    if len(conf) != 1:
        bad.append("%d confirmation rows to the drill address, want 1" % len(conf))
    else:
        row = conf[0]
        if row.get("from_address") != NOREPLY_FROM:
            bad.append("confirmation From %r, want %r" % (row.get("from_address"), NOREPLY_FROM))
        if row.get("reply_to") != CONTACT_TO:
            bad.append("confirmation Reply-To %r, want %r" % (row.get("reply_to"), CONTACT_TO))
        if str(row.get("subject") or "").startswith("["):
            bad.append("confirmation subject %r carries a team prefix" % row.get("subject"))
    return bad


def dispute_checks(mails: Sequence[dict], dispute_id: str) -> list[str]:
    """Reasons the urgent dispute alert is not exactly one row From the alerts sender, `[System bench]`, To the alerts list, no Reply-To."""
    named = [
        m
        for m in mails
        if dispute_id in str(m.get("subject") or "") + str(m.get("text_body") or "")
    ]
    if len(named) != 1:
        return ["%d alert rows name %s, want 1" % (len(named), dispute_id)]
    row = named[0]
    bad: list[str] = []
    if row.get("recipient") != ALERTS_TO:
        bad.append("dispute To %r, want %r" % (row.get("recipient"), ALERTS_TO))
    if row.get("from_address") != ALERTS_FROM:
        bad.append("dispute From %r, want %r" % (row.get("from_address"), ALERTS_FROM))
    if row.get("reply_to"):
        bad.append("dispute carries Reply-To %r" % row.get("reply_to"))
    if not str(row.get("subject") or "").startswith(SYSTEM_PREFIX):
        bad.append("dispute subject %r lacks %r" % (row.get("subject"), SYSTEM_PREFIX))
    return bad


def instant_checkout_rows(mails: Sequence[dict], session_id: str) -> list[str]:
    """Reasons the checkout alert went out before the digest run: any row naming the session, or any digest row, at all."""
    bad = [
        "a row names session %s before the digest run" % session_id
        for m in mails
        if session_id in str(m.get("subject") or "") + str(m.get("text_body") or "")
    ]
    bad += [
        "a digest row exists before the digest run"
        for m in mails
        if DIGEST_MARK in str(m.get("subject") or "")
    ]
    return bad


def digest_checks(mails: Sequence[dict], session_id: str) -> list[str]:
    """Reasons the mailbox does not hold exactly one digest row naming the session, From the alerts sender to the alerts list."""
    digests = [m for m in mails if DIGEST_MARK in str(m.get("subject") or "")]
    if len(digests) != 1:
        return ["%d digest rows, want 1" % len(digests)]
    row = digests[0]
    bad: list[str] = []
    if session_id not in str(row.get("text_body") or ""):
        bad.append("the digest does not name session %s" % session_id)
    if row.get("recipient") != ALERTS_TO:
        bad.append("digest To %r, want %r" % (row.get("recipient"), ALERTS_TO))
    if row.get("from_address") != ALERTS_FROM:
        bad.append("digest From %r, want %r" % (row.get("from_address"), ALERTS_FROM))
    if not str(row.get("subject") or "").startswith(SYSTEM_PREFIX):
        bad.append("digest subject %r lacks %r" % (row.get("subject"), SYSTEM_PREFIX))
    return bad


@dataclass
class State:
    """What the steps hand to each other and to the cleanup."""

    stamp: str
    address: str
    since: str
    dispute_id: str
    session_id: str
    event_ids: list[str] = field(default_factory=list)
    root_jar: str = ""
    submitted: bool = False
    summary: dict = field(default_factory=dict)


def _webhook(body: str, signature: str) -> int:
    """POST the raw body to the bench Stripe webhook with curl; the body travels on stdin."""
    argv = [
        "curl",
        "-sS",
        "--connect-timeout",
        "20",
        "--max-time",
        "60",
        "-o",
        os.devnull,
        "-w",
        "%{http_code}",
        "-X",
        "POST",
        bench_target() + API + "/webhooks/stripe",
        "-H",
        "Content-Type: application/json",
        "-H",
        "Stripe-Signature: " + signature,
        "--data-binary",
        "@-",
    ]
    proc = subprocess.run(argv, input=body, capture_output=True, text=True, check=False)
    try:
        return int((proc.stdout or "").strip())
    except ValueError:
        raise DrillError("no HTTP answer from the bench Stripe webhook") from None


def _root_creds() -> tuple[str, str]:
    email = os.environ.get("ROOT_EMAIL") or ""
    if not email:
        raise DrillError("ROOT_EMAIL is not set (the deploy-bench-eu profile binds it)")
    try:
        return email, deploy_bench.root_password()
    except deploy_bench.SeedError as exc:
        raise DrillError(str(exc)) from None


@dataclass
class Deps:
    http: ftr.Http = ftr._http
    call: ftr.Call = ftr._call
    rows: Rows = deploy_bench._d1_rows
    allowlist: Callable[[], int] = ftr._allowlist
    root_creds: Callable[[], tuple[str, str]] = _root_creds
    root_seed: Callable[[], str] = ftr.root_seed_from_env
    webhook: Webhook = _webhook
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    jar_path: Callable[[str], str] = lambda stamp: str(
        pathlib.Path(tempfile.gettempdir()) / ("erd-jar-%s-%s.txt" % (stamp, secrets.token_hex(4)))
    )
    unlink: Callable[[str], None] = lambda path: pathlib.Path(path).unlink(missing_ok=True)
    token: Callable[[], str] = lambda: secrets.token_hex(8)


def _mails(d: Deps, st: State) -> list[dict]:
    """Every captured row of this run: to the drill address, to either list, or naming the stamp, the dispute or the session."""
    return d.rows(
        q(
            "SELECT recipient, kind, subject, text_body, from_address, reply_to, created_at "
            "FROM captured_emails WHERE created_at >= $since AND "
            "(recipient = $a OR text_body LIKE $s OR text_body LIKE $d OR subject LIKE $d "
            "OR text_body LIKE $c OR subject LIKE $dg) ORDER BY created_at",
            since=sql_literal(st.since),
            a=sql_literal(st.address),
            s=sql_literal("%" + st.address + "%"),
            d=sql_literal("%" + st.dispute_id + "%"),
            c=sql_literal("%" + st.session_id + "%"),
            dg=sql_literal("%" + DIGEST_MARK + "%"),
        )
    )


def _send_event(d: Deps, secret: str, st: State, kind: str, obj: dict) -> int:
    event_id = "evt_drill_" + d.token()
    st.event_ids.append(event_id)
    body = event_body(event_id, kind, obj)
    return d.webhook(body, stripe_signature(secret, body, int(d.now().timestamp())))


def _step_contact(d: Deps, ev: Evidence, st: State) -> None:
    body = {
        "name": "Mail Drill",
        "email": st.address,
        "subject": "general",
        "message": "Email routing drill %s, safe to ignore." % st.stamp,
        "source": "email-routing-drill",
        "lang": "en",
    }
    try:
        status, _ = d.http(API + "/contact/submit", body)
    except DrillError:
        st.submitted = True  # no answer: the server may still have stored it
        raise
    st.submitted = status < 300 or status >= 500
    if status >= 300:
        ev.add(2, "contact", 1, "contact/submit http=%d" % status)
        raise DrillError("the contact submission was refused")
    bad: list[str] = []
    mails: list[dict] = []
    for _ in range(int(ALERT_WAIT_S / ALERT_POLL_S)):
        mails = _mails(d, st)
        bad = contact_checks(mails, st.address)
        if not bad:
            break
        d.sleep(ALERT_POLL_S)
    ev.add(
        2, "contact", 1 if bad else 0, "; ".join(bad) or "notification and confirmation rows hold"
    )
    if bad:
        raise DrillError("the contact mail routing is wrong")


def _step_dispute(d: Deps, ev: Evidence, secret: str, st: State) -> None:
    status = _send_event(d, secret, st, "charge.dispute.created", dispute_object(st.dispute_id))
    if status != 200:
        ev.add(3, "dispute", 1, "webhook http=%d" % status)
        raise DrillError("the dispute webhook was refused")
    waited = 0.0
    bad: list[str] = ["no row yet"]
    while waited <= ALERT_WAIT_S:
        bad = dispute_checks(_mails(d, st), st.dispute_id)
        if not bad:
            break
        d.sleep(ALERT_POLL_S)
        waited += ALERT_POLL_S
    ev.add(
        3, "dispute", 1 if bad else 0, "; ".join(bad) or "urgent alert row within %.0f s" % waited
    )
    if bad:
        raise DrillError("the urgent dispute alert is wrong or late")


def _step_checkout(d: Deps, ev: Evidence, secret: str, st: State) -> None:
    status = _send_event(d, secret, st, "checkout.session.expired", checkout_object(st.session_id))
    if status != 200:
        ev.add(4, "checkout", 1, "webhook http=%d" % status)
        raise DrillError("the checkout webhook was refused")
    # The queued alert has no instant mail; give a wrongly instant send time to land before looking.
    d.sleep(ALERT_POLL_S)
    bad = instant_checkout_rows(_mails(d, st), st.session_id)
    ev.add(
        4,
        "checkout",
        1 if bad else 0,
        "; ".join(bad) or "no row names the session before the digest",
    )
    if bad:
        raise DrillError("the checkout alert went out instantly")


def _open_root(d: Deps, ev: Evidence, st: State) -> str:
    creds = d.root_creds()
    jar = d.jar_path(st.stamp)
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
            ev.add(5, "digest", 1, "the root two-factor challenge failed: %s" % exc)
            raise
    elif status != 200:
        ev.add(5, "digest", 1, "root login http=%d" % status)
        raise DrillError("root login failed")
    return jar


def _digest_run(d: Deps, jar: str) -> tuple[int, int | None]:
    path = API + "/admin/alert-digest/run"
    status, answer = d.call("POST", path, {}, {}, jar)
    code = answer.get("code") if isinstance(answer, dict) else None
    if status == 403 and code == ftr.TERMS_REQUIRED:
        manifest = ftr.terms_manifest()
        d.call(
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
        status, answer = d.call("POST", path, {}, {}, jar)
    return status, row_count(answer)


def _step_digest(d: Deps, ev: Evidence, st: State) -> str:
    jar = _open_root(d, ev, st)
    status, count = _digest_run(d, jar)
    bad: list[str] = []
    if status != 200 or count is None or count < 1:
        bad.append("alert-digest/run http=%d items=%r want >= 1" % (status, count))
    else:
        bad += digest_checks(_mails(d, st), st.session_id)
    st.summary["digest_items"] = count
    ev.add(
        5,
        "digest",
        1 if bad else 0,
        "; ".join(bad) or "items=%d, one digest row names the session" % (count or 0),
    )
    if bad:
        raise DrillError("the digest run is wrong")
    return jar


def _step_rerun(d: Deps, ev: Evidence, st: State, jar: str) -> None:
    status, count = _digest_run(d, jar)
    bad: list[str] = []
    if status != 200 or count != 0:
        bad.append("second alert-digest/run http=%d items=%r want 0" % (status, count))
    bad += digest_checks(_mails(d, st), st.session_id)
    st.summary["rerun_items"] = count
    ev.add(6, "rerun", 1 if bad else 0, "; ".join(bad) or "items=0, still one digest row")
    if bad:
        raise DrillError("the second digest run mailed again")


def cleanup_sql(st: State) -> list[str]:
    """Deletes of everything this run adds, each bounded by the run's own identifiers and `created_at >= since`."""
    events = ", ".join(sql_literal(e) for e in st.event_ids) or "''"
    return [
        q("DELETE FROM contact_submissions WHERE email = $e", e=sql_literal(st.address)),
        q("DELETE FROM webhook_processed WHERE event_id IN ($ev)", ev=events),
        q(
            "DELETE FROM alert_digest_items WHERE body LIKE $c OR subject LIKE $d OR body LIKE $d",
            c=sql_literal("%" + st.session_id + "%"),
            d=sql_literal("%" + st.dispute_id + "%"),
        ),
        q(
            "DELETE FROM captured_emails WHERE created_at >= $since AND (recipient = $a "
            "OR text_body LIKE $s OR text_body LIKE $d OR subject LIKE $d OR text_body LIKE $c)",
            since=sql_literal(st.since),
            a=sql_literal(st.address),
            s=sql_literal("%" + st.address + "%"),
            d=sql_literal("%" + st.dispute_id + "%"),
            c=sql_literal("%" + st.session_id + "%"),
        ),
    ]


def leftover_sql(st: State) -> list[str]:
    """The reads that prove `cleanup_sql` removed everything."""
    events = ", ".join(sql_literal(e) for e in st.event_ids) or "''"
    return [
        q("SELECT id FROM contact_submissions WHERE email = $e", e=sql_literal(st.address)),
        q("SELECT event_id FROM webhook_processed WHERE event_id IN ($ev)", ev=events),
        q(
            "SELECT id FROM alert_digest_items WHERE body LIKE $c",
            c=sql_literal("%" + st.session_id + "%"),
        ),
        q(
            "SELECT recipient FROM captured_emails WHERE created_at >= $since AND (recipient = $a "
            "OR text_body LIKE $c OR subject LIKE $d)",
            since=sql_literal(st.since),
            a=sql_literal(st.address),
            c=sql_literal("%" + st.session_id + "%"),
            d=sql_literal("%" + st.dispute_id + "%"),
        ),
    ]


def cleanup(d: Deps, st: State, log: Callable[[str], None]) -> None:
    """Run the deletes, then the leftover reads; DrillError when any row remains."""
    for sql in cleanup_sql(st):
        d.rows(sql)
    left: list[dict] = []
    for sql in leftover_sql(st):
        left += d.rows(sql)
    log("deleted the contact, webhook, digest and mail rows of %s" % st.stamp)
    if left:
        raise DrillError("%d row(s) remain after the delete" % len(left))


def run(dry_run: bool, deps: Deps | None = None, env: Mapping[str, str] | None = None) -> int:
    d = deps or Deps()
    environ = os.environ if env is None else env
    ev = Evidence()
    started = d.now()
    stamp = ftr.stamp_now(started)
    st = State(
        stamp=stamp,
        address=stamp_address(stamp),
        since=datetime.fromtimestamp(started.timestamp() - CLOCK_SKEW_S, UTC).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        dispute_id="dp_drill_" + d.token(),
        session_id="cs_drill_" + d.token(),
    )
    if dry_run:
        for label, name in STEPS:
            print("DRY-RUN STEP %s %s address=%s" % (label, name, st.address))
        return 0
    try:
        bench_target()
        secret = require_secret(environ)
    except DrillError as exc:
        print("drill: %s" % exc, file=sys.stderr)
        return 1
    try:
        rc = d.allowlist()
        ev.add(1, "allowlist", rc)
        if rc != 0:
            raise DrillError("bench allowlist refresh failed")
        _step_contact(d, ev, st)
        _step_dispute(d, ev, secret, st)
        _step_checkout(d, ev, secret, st)
        jar = _step_digest(d, ev, st)
        _step_rerun(d, ev, st, jar)
    except DrillError as exc:
        ev.failed = True
        print("drill: %s" % exc, file=sys.stderr)
    finally:
        if st.root_jar:
            d.unlink(st.root_jar)
        notes: list[str] = []
        crc = 0
        if st.submitted or st.event_ids:
            try:
                cleanup(d, st, notes.append)
            except DrillError as exc:
                crc = 1
                notes.append(str(exc))
        ev.add(7, "cleanup", crc, "; ".join(notes) or "nothing to clean")
    st.summary.update(
        {
            "ok": not ev.failed,
            "address": st.address,
            "dispute": st.dispute_id,
            "session": st.session_id,
            "steps": ev.lines,
        }
    )
    print(json.dumps(st.summary, sort_keys=True))
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
            "rediacc_ci.ops.email_routing_drill",
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
        print("usage: email_routing_drill [--dry-run]", file=sys.stderr)
        return 2
    dry = "--dry-run" in args
    if not dry:
        rebound = _reexec_under_profile(args)
        if rebound is not None:
            return rebound
    return run(dry)


if __name__ == "__main__":
    sys.exit(main())
