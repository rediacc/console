"""rediacc_ci.ops.notices_drill with the network, the CLI and D1 faked: step order, the one-mail rule, the no-name rule, the planted rows, and a cleanup that removes everything the drill made."""

import json
import re
from datetime import UTC, datetime

import pytest

from rediacc_ci.ops import notices_drill as nd

NOW = datetime(2026, 11, 12, 10, 30, 0, tzinfo=UTC)
HARD = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
FRESH = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
USER = "11111111-1111-4111-8111-111111111111"
ORG = "22222222-2222-4222-8222-222222222222"
SUB = "33333333-3333-4333-8333-333333333333"
TEAM = "44444444-4444-4444-8444-444444444444"
EV1 = "55555555-5555-4555-8555-555555555551"
EV2 = "55555555-5555-4555-8555-555555555552"
UUIDS = [HARD, FRESH, EV1, EV2]
MACHINE_ID = "ntc-mid-0123456789ab"
GOOD_MAIL = (
    "2 repository licences need attention.\n"
    "aaaaaaaa . grand . 10 GB . hard expiry 2026-11-11\n"
    "bbbbbbbb . grand . 10 GB . refresh by 2026-11-11\n"
    "Run: rdc subscription refresh -m <machine>\n"
    "https://bench.example/account/notices\n"
)


def planted():
    return nd.Planted(HARD, FRESH, MACHINE_ID, [EV1, EV2])


class Fake:
    """Records every call in order; D1 is a small in-memory store keyed by the SQL's shape."""

    def __init__(
        self, tmp_path, mails_per_run=1, mail_text=GOOD_MAIL, shard=None, two_factor=False
    ):
        self.calls: list[str] = []
        self.sql: list[str] = []
        self.argvs: list[list[str]] = []
        self.mails: list[dict] = []
        self.mails_per_run = mails_per_run
        self.mail_text = mail_text
        self.shard = shard
        self.two_factor = two_factor
        self.runs = 0
        self.user_present = False
        self.events: set[str] = set()
        self.notices = False
        self.log_rows = False
        self.retired = False
        self.retire_rc = 0
        self.unread = 1
        self.notice_name = "drill@drillbox"
        self.config_file = tmp_path / "ntc.json"
        self.deleted: list[str] = []
        self.uuids = iter(UUIDS * 3)

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
                return 200, {"requiresTwoFactor": True, "challengeToken": "x"}
            return 200, {}
        if path.endswith("/portal/terms"):
            return 200, {"satisfied": False}
        if path.endswith("/portal/terms/accept"):
            return 201, {}
        if path.endswith("/admin/reminders/run"):
            self.runs += 1
            if self.runs == 1:
                for _ in range(self.mails_per_run):
                    self.mails.append(
                        {"kind": "repo-digest", "subject": "s", "text_body": self.mail_text}
                    )
            return 200, {"sent": 1}
        if path.endswith("/portal/notices/unread-count"):
            return 200, {"count": self.unread}
        return 404, {}

    def rdc(self, argv, _env):
        self.argvs.append(list(argv))
        if argv[0] == "config" and argv[1] == "init":
            self.calls.append("config-init")
            self.config_file.write_text(json.dumps({"schemaVersion": 3, "resources": {}}))
            return 0, ""
        if argv[0] == "config" and argv[1] == "delete":
            self.calls.append("config-delete")
            return 0, ""
        verb = argv[2:4]
        if verb == ["subscription", "login"]:
            return 0, ""
        if argv[2] == "machine":
            cfg = json.loads(self.config_file.read_text())
            cfg["resources"]["machines"] = {"drillbox": {"ip": "192.0.2.10", "user": "drill"}}
            self.config_file.write_text(json.dumps(cfg))
            self.calls.append("machine-add")
            return 0, ""
        if argv[3] == "notices":
            item = {"guid": HARD, "name": self.notice_name, "machine": "drillbox"}
            return 0, json.dumps(
                {"success": True, "data": {"notices": [{"payload": {"items": [item]}}]}}
            )
        if argv[3] == "retire":
            self.calls.append("retire " + " ".join(argv[4:]))
            self.retired = self.retire_rc == 0
            return self.retire_rc, ""
        if argv[3] == "status":
            licences = [{"guid": FRESH}] + ([] if self.retired else [{"guid": HARD}])
            return 0, json.dumps({"success": True, "data": {"licences": licences}})
        return 1, ""

    def rows(self, sql):
        self.sql.append(sql)
        if sql.startswith("SELECT id FROM users"):
            return [{"id": USER}] if self.user_present else []
        if sql.startswith("SELECT id, org_id FROM subscriptions"):
            return [{"id": SUB, "org_id": ORG}]
        if sql.startswith("SELECT id FROM subscriptions"):
            return [{"id": SUB}]
        if sql.startswith("SELECT shard FROM subscription_shards"):
            return [{"shard": self.shard}] if self.shard else []
        if sql.startswith("SELECT id FROM teams"):
            return [{"id": TEAM}]
        if sql.startswith("SELECT id FROM organizations"):
            return [{"id": ORG}]
        if sql.startswith("INSERT INTO event_log"):
            self.events.update(re.findall(r"VALUES \('([0-9a-f-]{36})'", sql))
            self.notices = True
            self.log_rows = True
            return []
        if sql.startswith("SELECT kind, subject, text_body FROM captured_emails"):
            return list(self.mails)
        if sql.startswith("SELECT count(*) AS n FROM captured_emails"):
            return [{"n": len(self.mails)}]
        if sql.startswith("DELETE FROM account_notices"):
            self.notices = False
        elif sql.startswith("DELETE FROM notification_reminder_log"):
            self.log_rows = False
        elif sql.startswith("DELETE FROM event_log WHERE id IN"):
            self.events.clear()
        elif sql.startswith("DELETE FROM users"):
            self.user_present = False
        elif sql.startswith("DELETE FROM captured_emails"):
            self.mails.clear()
        if sql.startswith("DELETE"):
            self.deleted.append(sql.split(" WHERE")[0])
            return []
        if sql.startswith("SELECT id FROM account_notices"):
            return [{"id": "n"}] if self.notices else []
        if sql.startswith("SELECT id FROM notification_reminder_log"):
            return [{"id": "l"}] if self.log_rows else []
        if sql.startswith("SELECT id FROM event_log WHERE id IN"):
            return [{"id": e} for e in self.events]
        return []

    def deps(self):
        return nd.Deps(
            http=self.http,
            call=self.call,
            rows=self.rows,
            rdc=self.rdc,
            allowlist=self.allowlist,
            drop_token_file=lambda _c: False,
            config_path=lambda _c: self.config_file,
            root_creds=lambda: ("root@rediacc.io", "pw"),
            new_uuid=lambda: next(self.uuids),
            jar_path=lambda stamp: "/tmp/jar-" + stamp,
            unlink=lambda _p: None,
            sleep=lambda _s: None,
            now=lambda: NOW,
            password=lambda: "pw-throwaway",
            token_hex=lambda: "0123456789ab",
        )


def drill(tmp_path, capsys, **kw):
    init = ("mails_per_run", "mail_text", "shard", "two_factor")
    fake = Fake(tmp_path, **{k: v for k, v in kw.items() if k in init})
    for key in ("unread", "notice_name"):
        if key in kw:
            setattr(fake, key, kw[key])
    rc = nd.run(False, fake.deps(), env={}, wait_cron=kw.get("wait_cron", False))
    out = capsys.readouterr()
    return fake, rc, out


def test_dry_run_lists_the_step_names(capsys):
    assert nd.run(True, nd.Deps(), env={}) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [ln.split()[3] for ln in lines] == [name for _, name in nd.STEPS]
    assert all(ADDR.match(ln.split("email=")[1]) for ln in lines)


ADDR = nd.ADDRESS


def test_a_clean_run_holds_every_step(tmp_path, capsys):
    fake, rc, out = drill(tmp_path, capsys)
    assert rc == 0, out.err
    steps = [ln.split()[1] for ln in out.out.splitlines() if ln.startswith("STEP")]
    assert steps == [label for label, _ in nd.STEPS][0:1] + [str(i) for i in range(2, 13)]
    assert all("rc=0" in ln for ln in out.out.splitlines())
    assert "retire %s --yes" % HARD in fake.calls
    # the repository record carries the planted GUID next to the machine
    cfg = json.loads(fake.config_file.read_text())
    assert cfg["resources"]["repositories"]["drill"]["tags"]["latest"]["repositoryGuid"] == HARD
    assert cfg["resources"]["repositories"]["drill"]["placement"] == {"machine": "drillbox"}


def test_planted_events_are_two_realistic_issued_rows(tmp_path, capsys):
    fake, rc, _ = drill(tmp_path, capsys)
    inserts = [s for s in fake.sql if s.startswith("INSERT INTO event_log")]
    assert len(inserts) == 2
    assert rc == 0
    for sql in inserts:
        assert "'repo_license_issued'" in sql
        assert SUB in sql
        assert ORG in sql
        assert TEAM in sql
        assert MACHINE_ID in sql
    assert HARD in inserts[0]
    assert FRESH in inserts[1]
    assert nd.iso(NOW) == "2026-11-12T10:30:00.000Z"


def test_a_second_captured_mail_fails_the_run(tmp_path, capsys):
    fake, rc, out = drill(tmp_path, capsys, mails_per_run=2)
    assert rc == 1
    assert "STEP 7 mail rc=1" in out.out
    assert "2 mails" in out.out
    assert not any(a[3:4] == ["retire"] for a in fake.argvs if len(a) > 3)


def test_a_repo_name_inside_the_mail_fails_the_run(tmp_path, capsys):
    _, rc, out = drill(tmp_path, capsys, mail_text=GOOD_MAIL + "repository drill on machine x\n")
    assert rc == 1
    assert "STEP 7 mail rc=1" in out.out
    assert "repository name" in out.out


def test_the_machine_id_inside_the_mail_fails_the_run(tmp_path, capsys):
    _, rc, out = drill(tmp_path, capsys, mail_text=GOOD_MAIL + MACHINE_ID + "\n")
    assert rc == 1
    assert "machine id" in out.out


def test_a_mail_without_the_fix_command_or_link_fails(tmp_path, capsys):
    _, rc, out = drill(tmp_path, capsys, mail_text="aaaaaaaa bbbbbbbb")
    assert rc == 1
    assert "rdc subscription refresh" in out.out
    assert "/account/notices" in out.out


def test_a_second_run_that_mails_again_fails(tmp_path, capsys):
    fake = Fake(tmp_path)
    orig = fake.call

    def second_mails(method, path, body, headers, jar):
        out = orig(method, path, body, headers, jar)
        if path.endswith("/admin/reminders/run") and fake.runs == 2:
            fake.mails.append({"kind": "repo-digest", "subject": "s", "text_body": GOOD_MAIL})
        return out

    fake.call = second_mails
    rc = nd.run(False, fake.deps(), env={})
    out = capsys.readouterr().out
    assert rc == 1
    assert "STEP 10 rerun rc=1" in out


def test_an_unread_count_other_than_one_fails(tmp_path, capsys):
    _, rc, out = drill(tmp_path, capsys, unread=2)
    assert rc == 1
    assert "STEP 8 unread rc=1" in out.out


def test_a_notice_that_names_the_wrong_repo_fails(tmp_path, capsys):
    _, rc, out = drill(tmp_path, capsys, notice_name=nd.REPO_NAME + "x@drillbox")
    assert rc == 1
    assert "STEP 9 notices rc=1" in out.out


def test_a_retire_that_leaves_the_licence_in_the_summary_fails(tmp_path, capsys):
    fake = Fake(tmp_path)
    orig = fake.rdc

    def keeps(argv, env):
        if len(argv) > 3 and argv[3] == "retire":
            fake.calls.append("retire")
            return 0, ""
        return orig(argv, env)

    fake.rdc = keeps
    rc = nd.run(False, fake.deps(), env={})
    out = capsys.readouterr().out
    assert rc == 1
    assert "STEP 11 retire rc=1" in out
    assert "still in the status summary" in out


def test_a_tenant_shard_other_than_zero_is_refused_and_nothing_is_planted(tmp_path, capsys):
    fake, rc, out = drill(tmp_path, capsys, shard="3")
    assert rc == 1
    assert "tenant shard 3" in out.out
    assert not any(s.startswith("INSERT") for s in fake.sql)


def test_root_two_factor_points_at_wait_cron(tmp_path, capsys):
    fake = Fake(tmp_path, two_factor=True)
    deps = fake.deps()
    deps.root_creds = lambda: ("root-x@rediacc.io", "pw")
    rc = nd.run(False, deps, env={})
    out = capsys.readouterr()
    assert rc == 1
    assert "--wait-cron" in out.err


def test_wait_cron_skips_the_trigger_and_waits_for_the_mail(tmp_path, capsys):
    fake = Fake(tmp_path)
    fake.mails.append({"kind": "repo-digest", "subject": "s", "text_body": GOOD_MAIL})
    rc = nd.run(False, fake.deps(), env={}, wait_cron=True)
    capsys.readouterr()
    assert rc == 0
    assert not any(c.endswith("/admin/reminders/run") for c in fake.calls)


def test_cleanup_removes_user_org_subscription_events_notices_and_mail(tmp_path, capsys):
    fake, rc, _ = drill(tmp_path, capsys)
    assert rc == 0
    assert not fake.user_present
    assert not fake.events
    assert not fake.notices
    assert not fake.log_rows
    assert not fake.mails
    for table in (
        "account_notices",
        "notification_reminder_log",
        "event_log",
        "subscriptions",
        "organizations",
        "users",
        "captured_emails",
    ):
        assert any(d.split()[2] == table for d in fake.deleted), table
    assert "config-delete" in fake.calls


def test_cleanup_runs_after_a_failed_step_and_scopes_deletes_to_the_exact_email(tmp_path, capsys):
    fake, rc, out = drill(tmp_path, capsys, mails_per_run=2)
    assert rc == 1
    assert "STEP 12 cleanup rc=0" in out.out
    assert not fake.user_present
    assert not fake.events
    for sql in fake.sql:
        if sql.startswith("DELETE FROM notification_reminder_log"):
            assert "recipient_email = 'ntc+" in sql
            assert "LIKE" not in sql


def test_a_leftover_after_the_delete_fails_the_cleanup(tmp_path, capsys):
    fake = Fake(tmp_path)
    orig = fake.rows

    def sticky(sql):
        if sql.startswith("DELETE FROM account_notices"):
            fake.sql.append(sql)
            return []
        return orig(sql)

    fake.rows = sticky
    rc = nd.run(False, fake.deps(), env={})
    out = capsys.readouterr().out
    assert rc == 1
    assert "STEP 12 cleanup rc=1" in out


def test_cleanup_refuses_a_non_uuid_id():
    with pytest.raises(nd.DrillError):
        nd.notice_cleanup_sql("a@b.c", "x'; DROP TABLE users;--", [], [])


def test_patch_config_needs_the_machine():
    with pytest.raises(nd.DrillError):
        nd.patch_config(json.dumps({"resources": {}}), HARD)


def test_the_address_pattern_and_main_usage(capsys):
    assert nd.ADDRESS.match(nd.stamp_address("20261112103000"))
    assert nd.main(["--bogus"]) == 2
    assert "usage" in capsys.readouterr().err
