"""rediacc_ci.ops.email_routing_drill with the network and D1 faked: the Stripe signature, the secret and target refusals, the captured-row checks and the one-digest rules."""

import json
from datetime import UTC, datetime

import pytest

from rediacc_ci.ops import email_routing_drill as erd
from rediacc_ci.ops.free_to_registered import DrillError

HOOK_KEY = "whsec_test_fixture"
NOW = datetime(2026, 11, 19, 10, 30, 0, tzinfo=UTC)
STAMP = "20261119103000"
ADDRESS = "drill+%s@rediacc.io" % STAMP
DISPUTE = "dp_drill_aaaaaaaaaaaaaaaa"
SESSION = "cs_drill_bbbbbbbbbbbbbbbb"


def mail(recipient, subject, body="", sender=None, reply_to=None, kind="x"):
    return {
        "recipient": recipient,
        "kind": kind,
        "subject": subject,
        "text_body": body,
        "from_address": sender,
        "reply_to": reply_to,
        "created_at": "2026-11-19T10:30:01",
    }


GOOD_NOTE = mail(
    erd.CONTACT_TO, "[Contact bench] general", "From %s" % ADDRESS, erd.CONTACT_FROM, ADDRESS
)
GOOD_CONF = mail(ADDRESS, "We got your message", "", erd.NOREPLY_FROM, erd.CONTACT_TO)
GOOD_DISPUTE = mail(
    erd.ALERTS_TO, "[System bench] Dispute opened: %s" % DISPUTE, "x", erd.ALERTS_FROM, None
)
GOOD_DIGEST = mail(
    erd.ALERTS_TO,
    "[System bench] Daily digest: 1 alerts",
    "Session %s expired" % SESSION,
    erd.ALERTS_FROM,
    None,
)


class Fake:
    """Records calls; D1 is an in-memory list of captured rows filled by what the drill triggers."""

    def __init__(
        self,
        instant_checkout=False,
        first_items=1,
        second_items=0,
        second_digest_row=False,
        leftover=False,
        webhook_status=200,
        contact_status=201,
    ):
        self.instant_checkout = instant_checkout
        self.first_items, self.second_items = first_items, second_items
        self.second_digest_row = second_digest_row
        self.leftover = leftover
        self.webhook_status = webhook_status
        self.contact_status = contact_status
        self.store: list[dict] = []
        self.calls: list[str] = []
        self.sql: list[str] = []
        self.posted: list[tuple[str, str]] = []
        self.runs = 0
        self.tokens = iter(["a" * 16, "b" * 16, "e1", "e2", "e3"])

    def allowlist(self):
        self.calls.append("allowlist")
        return 0

    def http(self, path, body):
        self.calls.append("http " + path)
        assert body["email"] == ADDRESS
        if self.contact_status < 300:
            self.store += [GOOD_NOTE, GOOD_CONF]
        return self.contact_status, {}

    def webhook(self, body, signature):
        self.posted.append((body, signature))
        kind = json.loads(body)["type"]
        self.calls.append("webhook " + kind)
        if self.webhook_status == 200:
            if kind == "charge.dispute.created":
                self.store.append(GOOD_DISPUTE)
            if kind == "checkout.session.expired" and self.instant_checkout:
                self.store.append(mail(erd.ALERTS_TO, "[System bench] x", SESSION, erd.ALERTS_FROM))
        return self.webhook_status

    def call(self, method, path, _body, _headers, _jar):
        self.calls.append("%s %s" % (method, path))
        if path.endswith("/auth/login"):
            return 200, {}
        if path.endswith("/admin/alert-digest/run"):
            self.runs += 1
            if self.runs == 1:
                self.store.append(GOOD_DIGEST)
                return 200, {"items": self.first_items}
            if self.second_digest_row:
                self.store.append(GOOD_DIGEST)
            return 200, {"items": self.second_items}
        return 404, {}

    def rows(self, sql):
        self.sql.append(sql)
        if sql.startswith("DELETE"):
            if not self.leftover:
                self.store.clear()
            return []
        if "FROM captured_emails" in sql:
            return list(self.store)
        if sql.startswith("SELECT") and self.leftover:
            return [{"id": "left"}]
        return []

    def deps(self):
        return erd.Deps(
            http=self.http,
            call=self.call,
            rows=self.rows,
            allowlist=self.allowlist,
            root_creds=lambda: ("root@example.test", "unused"),
            root_seed=lambda: "JBSWY3DPEHPK3PXP",
            webhook=self.webhook,
            sleep=lambda _s: None,
            now=lambda: NOW,
            jar_path=lambda _stamp: "erd-test-jar",
            unlink=lambda _p: None,
            token=lambda: next(self.tokens),
        )


def drive(fake, env=None):
    return erd.run(False, fake.deps(), {erd.HOOK_KEY_ENV: HOOK_KEY} if env is None else env)


def test_a_full_good_run_passes_and_prints_one_json_summary(capsys):
    fake = Fake()
    assert drive(fake) == 0
    out = capsys.readouterr().out
    summary = json.loads(out.strip().splitlines()[-1])
    assert summary["ok"] is True
    assert summary["digest_items"] == 1
    assert summary["rerun_items"] == 0
    assert [ln.split()[1] for ln in out.splitlines() if ln.startswith("STEP")] == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
    ]
    assert fake.store == []


def test_signature_matches_stripes_scheme_and_a_tampered_body_fails():
    body = erd.event_body("evt_1", "charge.dispute.created", erd.dispute_object("dp_1"))
    header = erd.stripe_signature(HOOK_KEY, body, 1_800_000_000)
    assert header.startswith("t=1800000000,v1=")
    assert erd.verify_signature(HOOK_KEY, body, header, 1_800_000_000)
    assert not erd.verify_signature(HOOK_KEY, body + " ", header, 1_800_000_000)
    assert not erd.verify_signature("other", body, header, 1_800_000_000)
    assert not erd.verify_signature(HOOK_KEY, body, header, 1_800_000_000 + 301)


def test_posted_events_verify_against_the_secret(capsys):
    fake = Fake()
    drive(fake)
    kinds = [json.loads(b)["type"] for b, _ in fake.posted]
    assert kinds == ["charge.dispute.created", "checkout.session.expired"]
    for body, header in fake.posted:
        assert erd.verify_signature(HOOK_KEY, body, header, int(NOW.timestamp()))
        assert HOOK_KEY not in body
        assert HOOK_KEY not in header
    capsys.readouterr()


def test_a_missing_secret_is_a_named_error_before_any_request(capsys):
    fake = Fake()
    assert drive(fake, env={}) == 1
    assert fake.calls == []
    assert fake.sql == []
    assert erd.HOOK_KEY_ENV in capsys.readouterr().err
    with pytest.raises(DrillError, match=erd.HOOK_KEY_ENV):
        erd.require_secret({})
    assert erd.require_secret({erd.HOOK_KEY_ENV: HOOK_KEY}) == HOOK_KEY


def test_a_non_bench_target_is_refused():
    with pytest.raises(DrillError, match="non-bench"):
        erd.bench_target("https://eu.rediacc.cloud")
    assert erd.bench_target() == erd.BENCH_ORIGIN


def test_the_drill_address_shape():
    assert erd.ADDRESS.match(erd.stamp_address(STAMP))
    assert not erd.ADDRESS.match("someone@rediacc.io")


def test_dry_run_prints_every_step_and_touches_nothing(capsys):
    fake = Fake()
    assert erd.run(True, fake.deps(), {}) == 0
    assert capsys.readouterr().out.count("DRY-RUN STEP") == len(erd.STEPS)
    assert fake.calls == []


def test_a_row_before_the_digest_run_fails_the_drill(capsys):
    fake = Fake(instant_checkout=True)
    assert drive(fake) == 1
    assert "went out instantly" in capsys.readouterr().err
    assert not any("alert-digest" in c for c in fake.calls)
    assert fake.store == []


def test_a_second_digest_run_that_mails_anything_fails(capsys):
    assert drive(Fake(second_items=2)) == 1
    capsys.readouterr()
    assert drive(Fake(second_digest_row=True)) == 1
    assert "second digest run mailed again" in capsys.readouterr().err


def test_wrong_sender_reply_to_and_prefix_are_each_named():
    bad_note = dict(GOOD_NOTE, from_address=erd.NOREPLY_FROM, reply_to=None, subject="x")
    reasons = " ".join(erd.contact_checks([bad_note, GOOD_CONF], ADDRESS))
    assert "notification From" in reasons
    assert "Reply-To" in reasons
    assert "lacks" in reasons
    assert erd.contact_checks([GOOD_NOTE, GOOD_CONF], ADDRESS) == []
    bad_conf = dict(GOOD_CONF, reply_to="x@y.z", subject="[Contact bench] z")
    reasons = " ".join(erd.contact_checks([GOOD_NOTE, bad_conf], ADDRESS))
    assert "confirmation Reply-To" in reasons
    assert "team prefix" in reasons


def test_dispute_and_digest_checks_name_each_defect():
    assert erd.dispute_checks([GOOD_DISPUTE], DISPUTE) == []
    assert erd.dispute_checks([], DISPUTE)
    bad = dict(
        GOOD_DISPUTE, recipient="x@y.z", from_address="a@b.c", reply_to="r@s.t", subject=DISPUTE
    )
    reasons = " ".join(erd.dispute_checks([bad], DISPUTE))
    assert "dispute To" in reasons
    assert "dispute From" in reasons
    assert "Reply-To" in reasons
    assert "lacks" in reasons
    assert erd.digest_checks([GOOD_DIGEST], SESSION) == []
    assert erd.digest_checks([GOOD_DIGEST, GOOD_DIGEST], SESSION)
    assert erd.digest_checks([dict(GOOD_DIGEST, text_body="nothing")], SESSION)


def test_instant_checkout_rows_is_silent_when_nothing_names_the_session():
    assert erd.instant_checkout_rows([GOOD_DISPUTE, GOOD_NOTE], SESSION) == []
    assert erd.instant_checkout_rows([GOOD_DIGEST], SESSION)


def test_row_count_parses_the_digest_answer():
    assert erd.row_count({"items": 3}) == 3
    assert erd.row_count({"items": [1, 2]}) == 2
    assert erd.row_count({}) is None
    assert erd.row_count({"items": True}) is None


def test_a_refused_webhook_fails_and_still_cleans_up(capsys):
    fake = Fake(webhook_status=401)
    assert drive(fake) == 1
    assert "dispute webhook was refused" in capsys.readouterr().err
    assert any(s.startswith("DELETE") for s in fake.sql)


def test_leftover_rows_after_cleanup_fail_the_run(capsys):
    assert drive(Fake(leftover=True)) == 1
    assert "STEP 7 cleanup rc=1" in capsys.readouterr().out


def test_cleanup_sql_is_bounded_by_the_run_identifiers():
    st = erd.State(
        stamp=STAMP,
        address=ADDRESS,
        since="2026-11-19T10:29:00",
        dispute_id=DISPUTE,
        session_id=SESSION,
        event_ids=["evt_drill_1"],
    )
    sqls = erd.cleanup_sql(st)
    assert all(s.startswith("DELETE") for s in sqls)
    assert all(any(tok in s for tok in (ADDRESS, "evt_drill_1", SESSION)) for s in sqls)
    assert "created_at >= '2026-11-19T10:29:00'" in sqls[-1]


def test_usage_error_and_help(capsys):
    assert erd.main(["--bogus"]) == 2
    assert "usage:" in capsys.readouterr().err
    assert erd.main(["--help"]) == 0
