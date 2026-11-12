"""rediacc_ci.ops.free_to_registered with the network, the CLI and D1 faked: step order, the address pattern, the missing-mail refusal and a cleanup scoped to one email."""

import json
import re
import urllib.parse
from datetime import UTC, datetime

import pytest

from rediacc_ci.ops import free_to_registered as ftr

NOW = datetime(2026, 11, 11, 10, 30, 0, tzinfo=UTC)
FREE_GUID = "44444444-4444-4444-8444-444444444444"
FREE_SUBJECT = "free:" + "ab" * 16
ISSUED_AT = "2026-11-11T10:30:05.123Z"
MANIFEST = ftr.terms_manifest()
USER = "11111111-1111-4111-8111-111111111111"
ORG = "22222222-2222-4222-8222-222222222222"
SUB = "33333333-3333-4333-8333-333333333333"
OTHER_USER = "99999999-9999-4999-8999-999999999999"
LIMITS = ftr.community_limits()
USER_CODE = "ABCD-EFGH-JK"
DEVICE_DELETE = "DELETE FROM device_codes WHERE user_code = 'ABCD-EFGH-JK'"


def envelope(data=None, errors=None):
    return json.dumps({"success": not errors, "data": data, "errors": errors or []})


GOOD_STATUS = envelope(
    {
        "plan": "COMMUNITY",
        "repoLicenseIssuances": {"limit": LIMITS["maxRepoLicenseIssuancesPerMonth"], "used": 0},
    }
)
NOT_LOGGED_IN = envelope(
    errors=[{"message": "Not logged in. Humans should run `rdc subscription login`."}]
)


class FakeJob(ftr.Background):
    def __init__(self, fake):
        self.fake = fake
        self.killed = False

    def read_url(self):
        return self.fake.handoff_url()

    def finish(self, _timeout):
        self.fake.calls.append("register-finish")
        return self.fake.register_rc

    def kill(self):
        self.killed = True


class Fake:
    """Records every call in order; D1 is a tiny in-memory table store keyed by the SQL's shape."""

    def __init__(self, mail=True, plan="COMMUNITY", status_out=GOOD_STATUS):
        self.calls: list[str] = []
        self.sql: list[str] = []
        self.mail = mail
        self.plan = plan
        self.status_out = status_out
        self.status_runs = 0
        self.user_present = False
        self.login_env: dict[str, str] = {}
        self.argvs: list[list[str]] = []
        self.dropped: list[str] = []
        self.window_n = 4
        self.bump_window_on_refusal = False
        self.free_acceptance_rows = 1
        self.free_row_override: dict = {}
        self.web_rows = 1
        self.issued = False
        self.free_deleted = False
        self.gate_status = 403
        self.terms_accepted = False
        self.register_rc = 0
        self.approve_status = 200
        self.url_has_email = True
        self.mail_carries_next = True
        self.last_next = None
        self.device_deleted = False
        self.spawned: list[list[str]] = []
        self.jobs: list[FakeJob] = []

    def handoff_url(self):
        url = "https://bench.example/account/authorize?code=" + USER_CODE
        if self.url_has_email:
            url += "&email=" + urllib.parse.quote(self.email, safe="")
        return url

    def spawn(self, argv, _env):
        self.spawned.append(list(argv))
        self.calls.append("register-spawn")
        job = FakeJob(self)
        self.jobs.append(job)
        return job

    def allowlist(self):
        self.calls.append("allowlist")
        return 0

    def rdc(self, argv, env):
        self.argvs.append(list(argv))
        if argv[0] == "config" and argv[1] == "init":
            self.calls.append("config-init")
            return 0, ""
        if argv[0] == "config" and argv[1] == "delete":
            self.calls.append("config-delete")
            return 0, ""
        if "login" in argv:
            self.calls.append("login")
            self.login_env = dict(env)
            return 0, ""
        self.status_runs += 1
        self.calls.append("status")
        if self.status_runs == 1:
            return 2, NOT_LOGGED_IN
        return 0, self.status_out

    def http(self, path, _body):
        self.calls.append(path.rsplit("/", 1)[-1])
        if path.endswith("/register"):
            self.user_present = True
            return 201, {"subscription": {"planCode": "COMMUNITY"}}
        if path.endswith("/magic-link"):
            self.last_next = _body.get("next")
            return 200, {}
        return 200, {"user": {"email": self.email}}

    email = ""

    def call(self, method, path, body, headers, jar):
        if path.startswith("/account/authorize"):
            assert jar is None  # anonymous: no session
            self.calls.append("GET authorize")
            return 200, {}
        tail = path.split("/api/v1", 1)[1]
        if tail == "/auth/magic-link/verify":
            assert jar
            assert body["token"]
            self.calls.append("POST verify")
            return 200, {}
        if tail == "/device-codes/%s/approve" % USER_CODE:
            assert jar
            self.calls.append("POST approve")
            return self.approve_status, {"approved": self.approve_status == 200}
        self.calls.append("%s %s" % (method, tail))
        if tail == "/licenses/free":
            assert headers.get("x-cli-version")
            if "termsAcceptance" not in body:
                if self.bump_window_on_refusal:
                    self.window_n += 1
                # The wire shape private/account/src/middleware/error-handler.ts writes: the
                # AppError details spread beside `error` and `code` (measured on bench 2026-11-12).
                return 403, {
                    "error": "Accept the Terms of Service (version 2026-11-11) to continue",
                    "code": "TERMS_ACCEPTANCE_REQUIRED",
                    "flag": "--accept-terms",
                    "env": "RDC_ACCEPT_TERMS=1",
                }
            assert body["termsAcceptance"]["method"] == "cli-flag-unattended"
            assert body["termsAcceptance"]["sha256"] == MANIFEST["sha256"]
            self.issued = True
            self.window_n += 1
            return 200, {"license": {"payload": "x"}, "signupUrl": "u"}
        if tail == "/auth/login":
            assert jar
            return 200, {}
        if tail == "/portal/terms":
            return 200, {"satisfied": self.terms_accepted}
        if tail == "/portal/subscription":
            return self.gate_status, {"error": {"code": "TERMS_ACCEPTANCE_REQUIRED"}}
        if tail == "/portal/terms/accept":
            self.terms_accepted = True
            return 201, {}
        raise AssertionError(tail)

    def rows(self, sql):
        self.sql.append(sql)
        if sql.startswith("SELECT count(*) AS window_rows"):
            return [{"n": 0, "window_rows": self.window_n}]
        if sql.startswith("SELECT free_subscription_id"):
            if not self.issued or self.free_deleted:
                return []
            return [{"free_subscription_id": FREE_SUBJECT, "issued_at": ISSUED_AT}]
        if sql.startswith("SELECT version, text_sha256"):
            row = {
                "version": MANIFEST["version"],
                "text_sha256": MANIFEST["sha256"],
                "method": "cli-flag-unattended",
                "client_ip": None,
                "cli_version": "0.0.0-drill",
                "notice_text": "I accept",
            }
            row.update(self.free_row_override)
            return [row] * self.free_acceptance_rows
        if sql.startswith("SELECT t.version"):
            row = {
                "version": MANIFEST["version"],
                "text_sha256": MANIFEST["sha256"],
                "method": "web-checkbox",
                "client_ip": "203.0.113.9",
                "user_agent": "curl/8",
            }
            return [row] * self.web_rows
        if sql.startswith(
            ("SELECT id FROM free_license_issuances", "SELECT id FROM terms_acceptances")
        ):
            return [] if self.free_deleted else [{"id": "x"}]
        if sql.startswith("DELETE FROM free_license_issuances"):
            self.free_deleted = True
        if sql.startswith("SELECT device_code FROM device_codes"):
            return [] if self.device_deleted else [{"device_code": "dc"}]
        if sql.startswith("DELETE FROM device_codes"):
            self.device_deleted = True
        if "FROM captured_emails WHERE recipient" in sql and sql.startswith("SELECT text_body"):
            link = "open https://x/account/magic-link/verify?token=abc_DEF-1"
            if self.last_next and self.mail_carries_next:
                link += "&next=" + urllib.parse.quote(self.last_next, safe="")
            return [{"text_body": link}] if self.mail else []
        if sql.startswith("SELECT count(*)"):
            return [{"n": 2}]
        if sql.startswith("SELECT id FROM users"):
            return [{"id": USER}] if self.user_present else []
        if sql.startswith("SELECT id FROM organizations"):
            return [{"id": ORG}]
        if sql.startswith("SELECT id FROM subscriptions"):
            return [{"id": SUB}]
        if sql.startswith("SELECT plan_code"):
            return [
                {
                    "plan_code": self.plan,
                    "max_repository_size_gb": None,
                    "max_repo_license_issuances_per_month": None,
                    "storage_quota_bytes": None,
                }
            ]
        if sql.startswith("DELETE FROM users"):
            self.user_present = False
        return []

    def _drop(self, config):
        self.dropped.append(config)
        return True

    def deps(self):
        return ftr.Deps(
            spawn=self.spawn,
            http=self.http,
            call=self.call,
            new_uuid=lambda: FREE_GUID,
            jar_path=lambda stamp: "/tmp/jar-" + stamp,
            unlink=lambda _p: None,
            rows=self.rows,
            rdc=self.rdc,
            drop_token_file=self._drop,
            allowlist=self.allowlist,
            sleep=lambda _s: None,
            now=lambda: NOW,
            password=lambda: "pw-random-0123456789",
        )


def go(fake):
    fake.email = ftr.address_for(ftr.stamp_now(NOW))
    return ftr.run(False, fake.deps(), env={"PATH": "/usr/bin", "REDIACC_CONFIG": "eu-bench"})


def test_happy_path_order_and_evidence(capsys):
    fake = Fake()
    assert go(fake) == 0
    assert fake.calls == [
        "allowlist",
        "config-init",
        "status",
        "POST /licenses/free",
        "POST /licenses/free",
        "register",
        "POST /auth/login",
        "GET /portal/terms",
        "GET /portal/subscription",
        "POST /portal/terms/accept",
        "magic-link",
        "verify",
        "login",
        "status",
        "register-spawn",
        "GET authorize",
        "magic-link",
        "POST verify",
        "GET /portal/terms",
        "POST approve",
        "register-finish",
        "status",
        "config-delete",
    ]
    out = capsys.readouterr().out.splitlines()
    assert [line.split()[1:3] for line in out] == [
        ["1", "allowlist"],
        ["2", "config"],
        ["3", "anonymous"],
        ["3b", "free-refused"],
        ["3c", "free-accepted"],
        ["4", "register"],
        ["4b", "terms-gate"],
        ["5", "email"],
        ["6", "login"],
        ["6b", "handoff"],
        ["7", "cleanup"],
    ]
    assert all(" rc=0" in line for line in out)


def test_address_pattern_and_throwaway_config():
    email = ftr.address_for("20261111103000")
    assert ftr.ADDRESS.match(email)
    assert email == "ftr+20261111103000@rediacc.io"
    assert not ftr.ADDRESS.match("someone@rediacc.io")
    fake = Fake()
    go(fake)
    init = next(a for a in fake.argvs if a[:2] == ["config", "init"])
    assert init[2] == "ftr-20261111103000"
    assert "eu-bench" not in " ".join(" ".join(a) for a in fake.argvs)


def test_login_env_carries_credentials_not_argv_and_selectors_are_scrubbed():
    fake = Fake()
    go(fake)
    assert fake.login_env[ftr.LOGIN_PW_ENV] == "pw-random-0123456789"
    assert "REDIACC_CONFIG" not in fake.login_env
    assert not any("pw-random" in " ".join(a) for a in fake.argvs)


def test_missing_captured_email_refuses_and_still_cleans_up(capsys):
    fake = Fake(mail=False)
    assert go(fake) == 1
    assert "login" not in fake.calls
    assert fake.calls[-1] == "config-delete"
    out = capsys.readouterr().out
    assert re.search(r"STEP 5 email rc=1 no magic-link mail", out)
    assert re.search(r"STEP 7 cleanup rc=0", out)
    assert any(s.startswith("DELETE FROM users") for s in fake.sql)


def test_wrong_plan_fails_the_assertion(capsys):
    fake = Fake(plan="FREE")
    assert go(fake) == 1
    assert "STEP 6 login rc=1" in capsys.readouterr().out


def test_wrong_status_limit_fails(capsys):
    bad = envelope({"plan": "COMMUNITY", "repoLicenseIssuances": {"limit": 1}})
    assert go(Fake(status_out=bad)) == 1
    assert "repoLicenseIssuances.limit=1" in capsys.readouterr().out


def test_anonymous_step_requires_the_refusal(capsys):
    fake = Fake()
    fake.status_runs = 1  # the first status call now answers success
    assert go(fake) == 1
    assert "STEP 3 anonymous rc=1" in capsys.readouterr().out
    assert "register" not in fake.calls


def test_cleanup_is_scoped_to_the_one_email():
    email = "ftr+20261111103000@rediacc.io"
    sql = ftr.cleanup_sql(email, USER, [ORG], [SUB])
    joined = "\n".join(sql)
    assert OTHER_USER not in joined
    assert "recipient = '%s'" % email in joined
    for stmt in sql:
        assert " WHERE " in stmt
        assert "'" in stmt  # every delete names a literal id or address
    # control: a second user's id or address is never in any statement
    assert "someone@rediacc.io" not in joined
    users_delete = next(s for s in sql if s.startswith("DELETE FROM users"))
    assert USER in users_delete
    assert email in users_delete


def test_cleanup_removes_only_the_looked_up_user():
    fake = Fake()
    fake.user_present = True
    fake.email = "ftr+20261111103000@rediacc.io"
    notes: list[str] = []
    ftr.cleanup(fake.email, fake.rows, notes.append)
    deletes = [s for s in fake.sql if s.startswith("DELETE")]
    assert deletes
    assert all(OTHER_USER not in s for s in deletes)
    assert any(USER in n for n in notes)


def test_cleanup_refuses_a_non_uuid_id():
    with pytest.raises(ftr.DrillError):
        ftr.cleanup_sql("a@rediacc.io", "1' OR '1'='1", [], [])


def test_cleanup_fails_when_the_user_remains():
    class Stuck(Fake):
        def rows(self, sql):
            if sql.startswith("DELETE FROM users"):
                return []
            self.user_present = True
            return super().rows(sql)

    stuck = Stuck()
    with pytest.raises(ftr.DrillError):
        ftr.cleanup("ftr+20261111103000@rediacc.io", stuck.rows, lambda _m: None)


def test_dry_run_touches_nothing(capsys):
    fake = Fake()
    assert ftr.run(True, fake.deps(), env={}) == 0
    assert fake.calls == []
    assert capsys.readouterr().out.count("DRY-RUN STEP") == 11


def test_community_limits_parse_the_shared_constants():
    assert LIMITS["maxRepositorySizeGb"] == 10
    assert LIMITS["storageQuotaBytes"] == 10 * 1024**3


def test_token_file_of_the_throwaway_config_is_dropped():
    fake = Fake()
    go(fake)
    assert fake.dropped == ["ftr-20261111103000"]


def test_token_file_path_names_only_that_config(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert ftr.token_file("ftr-1") == tmp_path / "rediacc" / "api-token-ftr-1.json"


def test_a_refusal_raised_before_its_step_line_still_fails_the_run(capsys, monkeypatch):
    """Review 23c783db.1: _http raises DrillError on no HTTP answer before step 4 prints its line; the run must exit 1, not 0."""
    fake = Fake()

    def no_answer(path, _body):
        raise ftr.DrillError("no HTTP answer from the bench origin%s" % path)

    monkeypatch.setattr(fake, "http", no_answer)
    assert go(fake) == 1
    assert "no HTTP answer" in capsys.readouterr().err


def test_dry_run_lists_the_terms_steps(capsys):
    assert ftr.run(True, Fake().deps(), env={}) == 0
    out = capsys.readouterr().out
    for label, name in (("3b", "free-refused"), ("3c", "free-accepted"), ("4b", "terms-gate")):
        assert "DRY-RUN STEP %s %s " % (label, name) in out


def test_a_window_count_change_on_the_refusal_fails_the_run(capsys):
    fake = Fake()
    fake.bump_window_on_refusal = True
    assert go(fake) == 1
    out = capsys.readouterr().out
    assert re.search(r"STEP 3b free-refused rc=1 .*window rows 4 -> 5", out)
    assert fake.calls.count("POST /licenses/free") == 1  # 3c never ran
    assert "STEP 7 cleanup rc=0" in out


def test_a_missing_free_acceptance_row_fails_the_run(capsys):
    fake = Fake()
    fake.free_acceptance_rows = 0
    assert go(fake) == 1
    out = capsys.readouterr().out
    assert "STEP 3c free-accepted rc=1" in out
    assert "acceptance rows=0 want 1" in out
    assert "register" not in fake.calls
    # the issuance that did happen is still removed
    assert any(s.startswith("DELETE FROM free_license_issuances") for s in fake.sql)


def test_a_free_acceptance_row_with_a_client_ip_fails(capsys):
    fake = Fake()
    fake.free_row_override = {"client_ip": "203.0.113.9", "notice_text": ""}
    assert go(fake) == 1
    out = capsys.readouterr().out
    assert "client_ip is not NULL" in out
    assert "notice_text empty" in out


def test_a_missing_web_acceptance_row_fails_the_run(capsys):
    fake = Fake()
    fake.web_rows = 0
    assert go(fake) == 1
    assert "STEP 4b terms-gate rc=1" in capsys.readouterr().out
    assert "magic-link" not in fake.calls
    assert any(s.startswith("DELETE FROM users") for s in fake.sql)


def test_an_ungated_portal_read_fails_the_gate(capsys):
    fake = Fake()
    fake.gate_status = 200
    assert go(fake) == 1
    assert "gated read http=200" in capsys.readouterr().out


def test_free_cleanup_deletes_only_the_free_rows():
    item = ftr.FreeIssued(FREE_GUID, FREE_SUBJECT, ISSUED_AT)
    sql = ftr.free_cleanup_sql(item)
    assert sorted(s.split(" WHERE ")[0] for s in sql) == [
        "DELETE FROM free_license_ip_window",
        "DELETE FROM free_license_issuances",
        "DELETE FROM terms_acceptances",
    ]
    joined = "\n".join(sql)
    assert FREE_SUBJECT in joined
    assert ISSUED_AT in joined
    assert FREE_GUID in joined
    assert USER not in joined


def test_free_cleanup_refuses_malformed_ids():
    with pytest.raises(ftr.DrillError):
        ftr.free_cleanup_sql(ftr.FreeIssued("x' OR '1'='1"))
    with pytest.raises(ftr.DrillError):
        ftr.free_cleanup_sql(ftr.FreeIssued(FREE_GUID, "free:x' OR 1=1 --"))


def test_both_subjects_acceptance_rows_are_deleted_in_a_full_run():
    fake = Fake()
    assert go(fake) == 0
    deletes = [s for s in fake.sql if s.startswith("DELETE FROM terms_acceptances")]
    assert len(deletes) == 2
    assert any(FREE_SUBJECT in s for s in deletes)
    assert any(USER in s for s in deletes)
    assert any(
        s.startswith("DELETE FROM free_license_ip_window") and ISSUED_AT in s for s in fake.sql
    )


def test_user_cleanup_sql_includes_the_user_acceptance_rows():
    sql = ftr.cleanup_sql("ftr+20261111103000@rediacc.io", USER, [ORG], [SUB])
    assert any(s.startswith("DELETE FROM terms_acceptances") and USER in s for s in sql)


def test_dry_run_lists_the_handoff_step_and_spawns_nothing(capsys):
    fake = Fake()
    assert ftr.run(True, fake.deps(), env={}) == 0
    assert "DRY-RUN STEP 6b handoff " in capsys.readouterr().out
    assert fake.spawned == []
    assert fake.sql == []
    assert fake.calls == []


def test_handoff_runs_register_under_the_throwaway_config_with_the_email():
    fake = Fake()
    assert go(fake) == 0
    argv = fake.spawned[0]
    assert argv[:2] == ["--config", "ftr-20261111103000"]
    assert argv[2:6] == ["subscription", "register", "--email", fake.email]
    assert argv[-2:] == ["--server", ftr.BENCH_ORIGIN]
    assert fake.last_next == "/account/authorize?code=%s&email=%s" % (
        USER_CODE,
        urllib.parse.quote(fake.email, safe=""),
    )
    assert fake.jobs[0].killed


def test_a_url_without_the_email_fails_the_step(capsys):
    fake = Fake()
    fake.url_has_email = False
    assert go(fake) == 1
    out = capsys.readouterr().out
    assert re.search(r"STEP 6b handoff rc=1 .*email param is not", out)
    assert "POST approve" not in fake.calls
    assert fake.jobs[0].killed
    assert re.search(r"STEP 7 cleanup rc=0", out)


def test_a_url_with_an_unencoded_email_fails_the_check():
    email = "ftr+20261111103000@rediacc.io"
    plain = "https://b/account/authorize?code=%s&email=%s" % (USER_CODE, email)
    # a raw '+' parses back as a space, so the email no longer matches
    assert ftr.handoff_url_check(plain, email)
    good = "https://b/account/authorize?code=%s&email=%s" % (
        USER_CODE,
        urllib.parse.quote(email, safe=""),
    )
    assert ftr.handoff_url_check(good, email) == []
    assert ftr.handoff_url_check(good.replace(USER_CODE, "nope"), email)


def test_a_magic_link_without_next_fails_the_step(capsys):
    fake = Fake()
    fake.mail_carries_next = False
    assert go(fake) == 1
    out = capsys.readouterr().out
    assert re.search(r"STEP 6b handoff rc=1 .*magic link next=''", out)
    assert "POST verify" not in fake.calls


def test_a_register_process_that_fails_fails_the_step(capsys):
    fake = Fake()
    fake.register_rc = 1
    assert go(fake) == 1
    assert "register exit=1 want 0" in capsys.readouterr().out


def test_an_approve_refusal_fails_the_step(capsys):
    fake = Fake()
    fake.approve_status = 404
    assert go(fake) == 1
    assert "approve http=404" in capsys.readouterr().out


def test_terms_are_accepted_in_the_handoff_only_when_not_already_accepted():
    fake = Fake()
    assert go(fake) == 0
    assert fake.calls.count("POST /portal/terms/accept") == 1  # 4b's; 6b saw it satisfied


def test_the_device_code_row_is_deleted_by_its_exact_code_in_a_full_run():
    fake = Fake()
    assert go(fake) == 0
    deletes = [s for s in fake.sql if s.startswith("DELETE FROM device_codes")]
    assert deletes == [DEVICE_DELETE]


def test_device_code_cleanup_deletes_only_the_captured_codes():
    sql = ftr.device_code_cleanup_sql([USER_CODE])
    assert sql == [DEVICE_DELETE]
    assert ftr.device_code_cleanup_sql([]) == []
    with pytest.raises(ftr.DrillError):
        ftr.device_code_cleanup_sql(["x' OR '1'='1"])


def test_cleanup_fails_when_the_device_code_row_remains():
    class Stuck(Fake):
        def rows(self, sql):
            if sql.startswith("DELETE FROM device_codes"):
                return []
            return super().rows(sql)

    with pytest.raises(ftr.DrillError):
        ftr.cleanup("ftr+20261111103000@rediacc.io", Stuck().rows, lambda _m: None, [USER_CODE])


def _stub(tmp_path, body):
    script = tmp_path / "stub.sh"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(0o755)
    return script


URL_LINE = "  https://bench.example/account/authorize?code=ABCD-EFGH-JK&email=a%40b.co"


def test_the_process_reads_the_url_the_cli_prints_on_stderr(tmp_path):
    # The CLI writes the verification URL through outputService.info, which is stderr.
    script = _stub(tmp_path, 'echo "Open this URL:" >&2\necho "%s" >&2\n' % URL_LINE)
    job = ftr._Process(["x"], {}, program=script)
    assert job.read_url() == URL_LINE.strip()
    assert job.finish(10) == 0


def test_the_process_still_reads_a_url_printed_on_stdout(tmp_path):
    script = _stub(tmp_path, 'echo "%s"\n' % URL_LINE)
    job = ftr._Process(["x"], {}, program=script)
    assert job.read_url() == URL_LINE.strip()
    job.finish(10)


def test_the_process_without_a_url_line_is_refused(tmp_path):
    script = _stub(tmp_path, "echo nothing here >&2\necho nor here\n")
    job = ftr._Process(["x"], {}, program=script)
    with pytest.raises(ftr.DrillError, match="no verification URL"):
        job.read_url()
    job.finish(10)
