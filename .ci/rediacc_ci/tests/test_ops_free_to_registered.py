"""rediacc_ci.ops.free_to_registered with the network, the CLI and D1 faked: step order, the address pattern, the missing-mail refusal and a cleanup scoped to one email."""

import json
import re
from datetime import UTC, datetime

import pytest

from rediacc_ci.ops import free_to_registered as ftr

NOW = datetime(2026, 11, 11, 10, 30, 0, tzinfo=UTC)
USER = "11111111-1111-4111-8111-111111111111"
ORG = "22222222-2222-4222-8222-222222222222"
SUB = "33333333-3333-4333-8333-333333333333"
OTHER_USER = "99999999-9999-4999-8999-999999999999"
LIMITS = ftr.community_limits()


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
            return 200, {}
        return 200, {"user": {"email": self.email}}

    email = ""

    def rows(self, sql):
        self.sql.append(sql)
        if "FROM captured_emails WHERE recipient" in sql and sql.startswith("SELECT text_body"):
            return (
                [{"text_body": "open https://x/account/magic-link/verify?token=abc_DEF-1"}]
                if self.mail
                else []
            )
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
            http=self.http,
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
        "register",
        "magic-link",
        "verify",
        "login",
        "status",
        "config-delete",
    ]
    out = capsys.readouterr().out.splitlines()
    assert [line.split()[1:3] for line in out] == [
        ["1", "allowlist"],
        ["2", "config"],
        ["3", "anonymous"],
        ["4", "register"],
        ["5", "email"],
        ["6", "login"],
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
    assert capsys.readouterr().out.count("DRY-RUN STEP") == 7


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
