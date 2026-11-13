"""rediacc_ci.ops.licence_expiry_drill with the network and D1 faked: step order, the one-mail rules, the planted cert, and a cleanup that removes everything the drill made."""

import re
from datetime import UTC, datetime

import pytest

from rediacc_ci.ops import licence_expiry_drill as led

NOW = datetime(2026, 11, 12, 10, 30, 0, tzinfo=UTC)
CERT = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
USER = "11111111-1111-4111-8111-111111111111"
ORG = "22222222-2222-4222-8222-222222222222"
SUB = "33333333-3333-4333-8333-333333333333"
SALES = "sales@bench.example"
ORG_NAME = "Lexp Co"
UNTIL_DAY = "2026-11-19"
OWNER_MAIL = "Your delegation certificate expires on %s.\n" % UNTIL_DAY
SALES_MAIL = (
    "%s | TEAM | cert cccccccc | expires within 7 days | validUntil 2026-11-19T09:30:00.000Z\n"
    % (ORG_NAME)
)


class Fake:
    """Records every call in order; D1 is a small in-memory store keyed by the SQL's shape."""

    def __init__(
        self,
        owner_mails=1,
        sales_mails=1,
        digest_lines=1,
        second_digest_lines=0,
        second_owner_mails=0,
        org_rows=1,
        org_name=ORG_NAME,
        shard=None,
        two_factor=False,
        sales_text=SALES_MAIL,
        unread=1,
    ):
        self.calls: list[str] = []
        self.sql: list[str] = []
        self.owner_mails = owner_mails
        self.sales_mails_n = sales_mails
        self.digest_lines = digest_lines
        self.second_digest_lines = second_digest_lines
        self.second_owner_mails = second_owner_mails
        self.org_rows = org_rows
        self.org_name = org_name
        self.shard = shard
        self.two_factor = two_factor
        self.sales_text = sales_text
        self.unread = unread
        self.digest_runs = 0
        self.reminder_runs = 0
        self.user_present = False
        self.cert = False
        self.notices = False
        self.log_rows = False
        self.owner: list[dict] = []
        self.sales: list[dict] = []
        self.deleted: list[str] = []
        self.uuids = iter([CERT] * 4)

    # --- injected seams
    def allowlist(self):
        self.calls.append("allowlist")
        return 0

    def http(self, path, _body):
        self.calls.append("http " + path)
        if path.endswith("/auth/register"):
            self.user_present = True
            return 201, {"subscription": {"planCode": "COMMUNITY"}}
        return 404, {}

    def call(self, method, path, body, _headers, _jar):
        self.calls.append("%s %s" % (method, path))
        if path.endswith("/auth/login"):
            if body["email"].startswith("root") and self.two_factor:
                return 200, {"requiresTwoFactor": True}
            return 200, {}
        if path.endswith("/portal/terms"):
            return 200, {"satisfied": False}
        if path.endswith("/portal/terms/accept"):
            return 201, {}
        if path.endswith("/admin/reminders/run"):
            self.reminder_runs += 1
            assert body == {"kinds": ["delegation"]}
            if self.reminder_runs == 1:
                self.owner = [
                    {"kind": "delegation-expiry", "subject": "s", "text_body": OWNER_MAIL}
                    for _ in range(self.owner_mails)
                ]
                self.notices = True
                self.log_rows = True
            else:
                self.owner += [
                    {"kind": "delegation-expiry", "subject": "s", "text_body": OWNER_MAIL}
                    for _ in range(self.second_owner_mails)
                ]
            return 200, {"kinds": ["delegation"], "counts": {"delegation": 1}}
        if path.endswith("/admin/sales-digest/run"):
            self.digest_runs += 1
            if self.digest_runs == 1:
                self.sales = [
                    {"kind": "sales", "subject": "s", "text_body": self.sales_text}
                    for _ in range(self.sales_mails_n)
                ]
                return 200, {"lines": self.digest_lines}
            return 200, {"lines": self.second_digest_lines}
        if path.endswith("/portal/notices/unread-count"):
            return 200, {"count": self.unread}
        return 404, {}

    def rows(self, sql):
        self.sql.append(sql)
        if sql.startswith("SELECT id FROM users"):
            return [{"id": USER}] if self.user_present else []
        if sql.startswith("SELECT id FROM subscriptions"):
            return [{"id": SUB}]
        if sql.startswith("SELECT shard FROM subscription_shards"):
            return [{"shard": self.shard}] if self.shard else []
        if sql.startswith("SELECT id, name FROM organizations WHERE customer_id"):
            return [{"id": ORG, "name": self.org_name}] * self.org_rows
        if sql.startswith("SELECT id FROM organizations"):
            return [{"id": ORG}]
        if sql.startswith("INSERT INTO delegation_certs"):
            self.cert = True
            return []
        if "FROM captured_emails WHERE recipient = " in sql and sql.startswith("SELECT kind"):
            return list(self.sales if SALES in sql else self.owner)
        if sql.startswith("SELECT count(*) AS n FROM captured_emails"):
            return [{"n": len(self.owner)}]
        if sql.startswith("DELETE"):
            if sql.startswith("DELETE FROM delegation_certs"):
                self.cert = False
            elif sql.startswith("DELETE FROM account_notices"):
                self.notices = False
            elif sql.startswith("DELETE FROM notification_reminder_log"):
                self.log_rows = False
            elif sql.startswith("DELETE FROM users"):
                self.user_present = False
            elif sql.startswith("DELETE FROM captured_emails") and SALES in sql:
                self.sales = []
            elif sql.startswith("DELETE FROM captured_emails"):
                self.owner = []
            self.deleted.append(sql.split(" WHERE")[0])
            return []
        if sql.startswith("SELECT id FROM delegation_certs"):
            return [{"id": CERT}] if self.cert else []
        if sql.startswith("SELECT id FROM account_notices"):
            return [{"id": "n"}] if self.notices else []
        if sql.startswith("SELECT id FROM notification_reminder_log"):
            return [{"id": "l"}] if self.log_rows else []
        if sql.startswith("SELECT recipient FROM captured_emails"):
            return [{"recipient": SALES}] if self.sales else []
        return []

    def deps(self):
        return led.Deps(
            http=self.http,
            call=self.call,
            rows=self.rows,
            allowlist=self.allowlist,
            root_creds=lambda: ("root@rediacc.io", "pw"),
            new_uuid=lambda: next(self.uuids),
            jar_path=lambda stamp: "/tmp/jar-" + stamp,
            unlink=lambda _p: None,
            now=lambda: NOW,
            password=lambda: "pw-throwaway",
        )


def drill(capsys, env=None, **kw):
    fake = Fake(**kw)
    rc = led.run(False, fake.deps(), env={"SALES_NOTIFY_EMAIL": SALES} if env is None else env)
    return fake, rc, capsys.readouterr()


def test_dry_run_lists_the_step_names_and_touches_nothing(capsys):
    class Boom(led.Deps):
        def __getattribute__(self, name):
            if name in ("http", "call", "rows", "allowlist", "root_creds"):
                raise AssertionError("dry run touched " + name)
            return super().__getattribute__(name)

    assert led.run(True, Boom(), env={}) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [ln.split()[3] for ln in lines] == [name for _, name in led.STEPS]
    assert all(led.ADDRESS.match(ln.split("email=")[1]) for ln in lines)


def test_a_clean_run_holds_every_step_and_cleans_up(capsys):
    fake, rc, out = drill(capsys)
    assert rc == 0, out.err
    steps = [ln.split()[1] for ln in out.out.splitlines() if ln.startswith("STEP")]
    assert steps == [label for label, _ in led.STEPS][0:1] + [str(i) for i in range(2, 12)]
    assert all("rc=0" in ln for ln in out.out.splitlines())
    assert (fake.reminder_runs, fake.digest_runs) == (2, 2)
    assert not any((fake.cert, fake.notices, fake.log_rows, fake.sales, fake.owner))
    assert not fake.user_present


def test_the_planted_cert_is_active_and_a_hair_under_seven_days_out(capsys):
    fake, rc, _ = drill(capsys)
    inserts = [s for s in fake.sql if s.startswith("INSERT INTO delegation_certs")]
    assert rc == 0
    assert len(inserts) == 1
    assert CERT in inserts[0]
    assert SUB in inserts[0]
    assert "'active'" in inserts[0]
    assert "2026-11-19T09:30:00.000Z" in inserts[0]


def test_a_second_owner_mail_fails_the_run(capsys):
    fake, rc, out = drill(capsys, owner_mails=2)
    assert rc == 1
    assert "STEP 7 owner-mail rc=1" in out.out
    assert "2 owner mails" in out.out
    assert fake.digest_runs == 1


def test_a_missing_sales_digest_mail_fails_the_run(capsys):
    _, rc, out = drill(capsys, sales_mails=0)
    assert rc == 1
    assert "STEP 8 sales-mail rc=1" in out.out
    assert "0 sales mails" in out.out


def test_a_digest_that_counts_no_line_fails_the_run(capsys):
    _, rc, out = drill(capsys, digest_lines=0)
    assert rc == 1
    assert "STEP 6 digest rc=1" in out.out


def test_a_digest_line_without_the_org_name_fails_the_run(capsys):
    _, rc, out = drill(capsys, sales_text="someone else | TEAM | cert cccccccc | validUntil x\n")
    assert rc == 1
    assert "does not name the org" in out.out


def test_an_unread_count_other_than_one_fails(capsys):
    _, rc, out = drill(capsys, unread=2)
    assert rc == 1
    assert "STEP 9 unread rc=1" in out.out


def test_a_second_run_that_mails_again_fails(capsys):
    _, rc, out = drill(capsys, second_digest_lines=1)
    assert rc == 1
    assert "STEP 10 rerun rc=1" in out.out
    assert "want 0" in out.out


def test_a_second_owner_mail_on_the_rerun_fails_step_ten(capsys):
    """Review b1b05295.1: the rerun recounts the owner's mail, so a second reminder send is caught."""
    _, rc, out = drill(capsys, second_owner_mails=1)
    assert rc == 1
    rerun = [ln for ln in out.out.splitlines() if ln.startswith("STEP 10 rerun rc=1")]
    assert len(rerun) == 1
    assert "2 owner mails name" in rerun[0]
    assert "want exactly 1" in rerun[0]
    # control: the clean rerun holds
    _, rc0, out0 = drill(capsys)
    assert rc0 == 0
    assert "STEP 10 rerun rc=0" in out0.out


@pytest.mark.parametrize("rows", [0, 2])
def test_the_customer_org_must_be_exactly_one_row(capsys, rows):
    """Bench 2026-11-13: STEP 4 read the org through subscriptions.org_id, which registration leaves null."""
    fake, rc, out = drill(capsys, org_rows=rows)
    assert rc == 1
    assert "STEP 4 plant rc=1 organization rows=%d for the customer" % rows in out.out
    assert not fake.cert


def test_a_customer_org_with_no_name_refuses_the_plant(capsys):
    """Review 12803257.1: the digest line names the org, so a nameless org is refused before planting."""
    fake, rc, out = drill(capsys, org_name="")
    assert rc == 1
    assert "STEP 4 plant rc=1 organization '%s' has no name" % ORG in out.out
    assert not fake.cert


def test_a_tenant_shard_other_than_zero_is_refused_and_nothing_is_planted(capsys):
    fake, rc, out = drill(capsys, shard="2")
    assert rc == 1
    assert "STEP 4 plant rc=1" in out.out
    assert not any(s.startswith("INSERT INTO delegation_certs") for s in fake.sql)
    assert fake.reminder_runs == 0


def test_root_two_factor_fails_the_step(capsys):
    fake, rc, out = drill(capsys, two_factor=True)
    assert rc == 1
    assert "two-factor" in out.out
    assert fake.reminder_runs == 0


def test_an_unset_sales_address_is_refused_before_anything_runs(capsys):
    fake, rc, out = drill(capsys, env={})
    assert rc == 1
    assert "SALES_NOTIFY_EMAIL is not set" in out.err
    assert fake.calls == []


def test_cleanup_deletes_every_planted_row(capsys):
    fake, rc, out = drill(capsys)
    assert rc == 0
    deleted = " | ".join(fake.deleted)
    for table in (
        "delegation_certs",
        "account_notices",
        "notification_reminder_log",
        "captured_emails",
        "users",
        "organizations",
        "subscriptions",
    ):
        assert ("FROM " + table) in deleted, table
    assert "STEP 11 cleanup rc=0" in out.out


def test_cleanup_runs_after_a_failed_step_and_scopes_the_sales_delete(capsys):
    fake, rc, _ = drill(capsys, owner_mails=2)
    assert rc == 1
    assert not any((fake.cert, fake.notices, fake.log_rows, fake.sales, fake.owner))
    sales_delete = [
        s for s in fake.sql if s.startswith("DELETE FROM captured_emails") and SALES in s
    ]
    assert len(sales_delete) == 1
    assert "LIKE '%cccccccc%'" in sales_delete[0]
    assert "created_at >=" in sales_delete[0]


def test_a_leftover_after_the_delete_fails_the_cleanup(capsys, monkeypatch):
    fake = Fake()
    real = fake.rows

    def sticky(sql):
        if sql.startswith("DELETE FROM delegation_certs"):
            return []
        return real(sql)

    monkeypatch.setattr(fake, "rows", sticky)
    # the sticky fake keeps the cert on delete, so the proof read finds it
    fake.cert = True
    rc = led.run(False, fake.deps(), env={"SALES_NOTIFY_EMAIL": SALES})
    out = capsys.readouterr().out
    assert rc == 1
    assert "STEP 11 cleanup rc=1" in out
    assert "remain after the delete" in out


def test_cleanup_refuses_a_non_uuid_id():
    with pytest.raises(led.DrillError):
        led.cleanup_sql("a@b.c", SALES, USER, ["not-a-uuid"], led.Planted(CERT), "2026")


def test_a_409_register_does_not_clean_up_the_foreign_account(capsys, monkeypatch):
    fake = Fake()
    monkeypatch.setattr(fake, "http", lambda _path, _body: (409, {}))
    rc = led.run(False, fake.deps(), env={"SALES_NOTIFY_EMAIL": SALES})
    out = capsys.readouterr().out
    assert rc == 1
    assert not any(s.startswith("DELETE") for s in fake.sql)
    assert "STEP 11 cleanup rc=0" in out


def test_the_address_pattern_and_main_usage(capsys):
    assert re.match(led.ADDRESS, led.stamp_address("20261112103000"))
    assert led.main(["--nope"]) == 2
    assert "usage" in capsys.readouterr().err
