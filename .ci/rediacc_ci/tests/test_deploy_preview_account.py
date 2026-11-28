"""Tests for `rediacc_ci.deploy.preview_account` (PLAN-preview-signer P1). No test reaches Cloudflare: wrangler is a recording fake."""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import re
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.deploy import preview_account as pa
from rediacc_ci.deploy import preview_name as pn

if TYPE_CHECKING:
    from pathlib import Path

KEY_B64 = base64.b64encode(bytes(range(32))).decode()
KEY = pn.load_key({pn.KEY_ENV: KEY_B64})
NOW = datetime.datetime(2026, 11, 26, 12, 0, 0, tzinfo=datetime.UTC)


class FakeWrangler:
    """Answers `d1 list` with one database and records every call."""

    def __init__(
        self, *, list_rc: int = 0, execute_rc: int = 0, dbs: list[dict[str, str]] | None = None
    ):
        self.calls: list[list[str]] = []
        self.list_rc = list_rc
        self.execute_rc = execute_rc
        self.dbs = [{"name": "account-pr-7", "uuid": "u-7"}] if dbs is None else dbs

    def __call__(self, argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        if "list" in argv:
            return subprocess.CompletedProcess(argv, self.list_rc, json.dumps(self.dbs), "boom")
        return subprocess.CompletedProcess(argv, self.execute_rc, "", "exec failed")


def sql_of(fake: FakeWrangler) -> str:
    execute = next(c for c in fake.calls if "execute" in c)
    return execute[execute.index("--command") + 1]


def test_subscription_id_is_in_the_preview_namespace_and_ends_in_seven_days() -> None:
    name = pn.preview_name(7, KEY)
    sql, sub_id = pa.build_sql(name, "Cust@Example.com", NOW, "h" * 64)
    assert re.fullmatch(rf"{re.escape(name)}-[0-9a-f]{{8}}", sub_id)
    assert "'2026-12-03T12:00:00.000Z'" in sql
    assert "'PROFESSIONAL'" in sql
    assert "'trial', 'active'" in sql
    assert "cust@example.com" in sql
    assert "Cust@Example.com" not in sql


def test_two_calls_mint_two_subscription_ids() -> None:
    name = pn.preview_name(7, KEY)
    assert pa.build_sql(name, "a@b.co", NOW, "h")[1] != pa.build_sql(name, "a@b.co", NOW, "h")[1]


def test_no_password_columns_are_written() -> None:
    sql, _ = pa.build_sql(pn.preview_name(7, KEY), "a@b.co", NOW, "h")
    assert "password" not in sql


@pytest.mark.parametrize("name", ["pr-7", "signer-bench-eu", "pv-aa-bb-cc-signer", "pv-aa-bb"])
def test_a_name_outside_the_preview_pattern_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="not a preview Worker name"):
        pa.build_sql(name, "a@b.co", NOW, "h")


@pytest.mark.parametrize("email", ["", "no-at", "o'brien@x.io", "a@b", "a b@c.io"])
def test_a_bad_email_is_refused(email: str) -> None:
    with pytest.raises(ValueError, match="not an acceptable email"):
        pa.build_sql(pn.preview_name(7, KEY), email, NOW, "h")


def test_run_executes_one_remote_batch_and_prints_the_link_once(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    fake = FakeWrangler()
    rc = pa.run(7, "a@b.co", KEY, now=NOW, runner=fake, worker_dir=tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    name = pn.preview_name(7, KEY)
    link = re.search(
        rf"https://{name}\.rediacc\.workers\.dev/account/magic-link/verify\?token=(\S+)", out
    )
    assert link
    token = link.group(1)
    assert len(token) == 43
    assert out.count(token) == 1
    sql = sql_of(fake)
    assert token not in sql
    assert hashlib.sha256(token.encode()).hexdigest() in sql
    assert "'2026-11-26T12:15:00.000Z'" in sql
    execute = next(c for c in fake.calls if "execute" in c)
    assert "--remote" in execute
    assert execute[execute.index("execute") + 1] == "account-pr-7"
    assert "password" not in out.lower()


def test_a_failed_batch_prints_no_link(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    rc = pa.run(7, "a@b.co", KEY, now=NOW, runner=FakeWrangler(execute_rc=3), worker_dir=tmp_path)
    assert rc == 3
    assert "magic-link" not in capsys.readouterr().out


def test_a_missing_database_and_a_failed_list_execute_nothing(tmp_path: Path) -> None:
    missing = FakeWrangler(dbs=[])
    assert pa.run(7, "a@b.co", KEY, now=NOW, runner=missing, worker_dir=tmp_path) == 1
    assert not any("execute" in c for c in missing.calls)
    failed = FakeWrangler(list_rc=1)
    assert pa.run(7, "a@b.co", KEY, now=NOW, runner=failed, worker_dir=tmp_path) == 1
    assert not any("execute" in c for c in failed.calls)


def test_main_refuses_without_the_name_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(pn.KEY_ENV, raising=False)
    assert pa.main(["--pr", "7", "--email", "a@b.co"]) == 1


def test_main_refuses_a_non_positive_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(pn.KEY_ENV, KEY_B64)
    assert pa.main(["--pr", "0", "--email", "a@b.co"]) == 1
