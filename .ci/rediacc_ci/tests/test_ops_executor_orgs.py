"""Tests for `rediacc_ci.ops.executor_orgs` against a fake `npx` (wrangler) on a scratch PATH.

No Cloudflare credential and no network: the fake wrangler records its argv and prints the next canned `d1 execute --json` answer of `FAKE_NPX_SEQ` (or `FAKE_NPX_OUT` every time).
"""

from __future__ import annotations

import json
import os
import stat
import typing

import pytest

from rediacc_ci.ops import executor_orgs as mod

if typing.TYPE_CHECKING:
    import pathlib

NOW = "2026-10-26T00:00:00.000Z"
ORG_A = "orgaaaaaaaa-1111"
ORG_B = "orgbbbbbbbb-2222"
ORG_C = "orgcccccccc-3333"
ORG_D = "orgdddddddd-4444"
ORG_E = "orgeeeeeeee-5555"


def _row(org: str, plan: str = "BUSINESS", status: str = "active", **extra: object) -> dict:
    row: dict[str, object] = {
        "id": org,
        "blocked_at": None,
        "sub_id": "sub-" + org,
        "plan_code": plan,
        "status": status,
        "type": "subscription",
        "expires_at": None,
        "sub_created_at": "2026-01-01T00:00:00Z",
        "store_count": 1,
    }
    row.update(extra)
    return row


ROWS = [
    _row(ORG_A),
    _row(ORG_B, "ENTERPRISE", "grace"),
    _row(ORG_C, "COMMUNITY"),
    _row(ORG_D, blocked_at="2026-10-01T00:00:00Z"),
    _row(ORG_E, store_count=0),
]

FAKE_NPX = """#!/usr/bin/env python3
import json, os, sys
log = os.environ["FAKE_LOG"]
with open(log, "a") as f:
    f.write(json.dumps(["npx"] + sys.argv[1:]) + "\\n")
seq = os.environ.get("FAKE_NPX_SEQ")
if seq:
    counter = log + ".n"
    n = int(open(counter).read()) if os.path.exists(counter) else 0
    open(counter, "w").write(str(n + 1))
    out = json.loads(seq)[min(n, len(json.loads(seq)) - 1)]
else:
    out = os.environ.get("FAKE_NPX_OUT", "")
sys.stdout.write(out)
sys.exit(int(os.environ.get("FAKE_NPX_RC", "0")))
"""


@pytest.fixture
def fake(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("npx", FAKE_NPX),):
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.jsonl"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token-secret-value")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("FAKE_NPX_OUT", json.dumps([{"success": True, "results": ROWS}]))
    return log


def _calls(log: pathlib.Path) -> list[list]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _run(*argv: str) -> int:
    return mod.main(list(argv))


def test_verdicts_cover_each_refusal() -> None:
    by = {v.org_id: v for v in mod.verdicts(ROWS, NOW)}
    assert by[ORG_A].entitled
    assert by[ORG_B].entitled
    assert by[ORG_B].plan == "ENTERPRISE"
    assert by[ORG_C].reason == "plan"
    assert by[ORG_D].reason == "blocked"
    assert by[ORG_E].reason == "store"


def test_expired_or_missing_subscription_is_refused() -> None:
    expired = _row("orgexpired-0001", expires_at="2026-01-01T00:00:00Z")
    none = {"id": "orgnosub-00001", "sub_id": None, "store_count": 1, "blocked_at": None}
    by = {v.org_id: v for v in mod.verdicts([expired, none], NOW)}
    assert by["orgexpired-0001"].reason == "subscription"
    assert by["orgnosub-00001"].reason == "subscription"


def test_primary_subscription_is_the_best_ranked_live_one() -> None:
    community = _row("orgmulti-00001", "COMMUNITY", "inactive", sub_id="s1")
    paid = _row("orgmulti-00001", "PROFESSIONAL", "active", sub_id="s2")
    (verdict,) = mod.verdicts([community, paid], NOW)
    assert verdict.entitled
    assert verdict.plan == "PROFESSIONAL"


def test_list_prints_prefixes_only(fake, capsys) -> None:
    assert _run("list", "--target", "edge", "--region", "eu") == 0
    out = capsys.readouterr()
    text = out.out + out.err
    assert mod.prefix(ORG_A) in text
    assert mod.prefix(ORG_B) in text
    assert mod.prefix(ORG_C) not in text
    assert ORG_A not in text
    assert ORG_B not in text
    assert "2 of 5 orgs entitled" in text
    (call,) = _calls(fake)
    assert call[:5] == ["npx", "wrangler", "d1", "execute", "edge-account-db-eu"]
    assert "--remote" in call
    assert "--json" in call
    assert "server_recoverable_org_passphrase IS NOT NULL" in " ".join(call)


@pytest.mark.usefixtures("fake")
def test_verify_passes_for_two_entitled_orgs(capsys) -> None:
    assert _run("verify", "--target", "edge", "--region", "eu", "--org", ORG_A, "--org", ORG_B) == 0
    text = capsys.readouterr()
    assert ORG_A not in text.out + text.err


@pytest.mark.usefixtures("fake")
def test_verify_fails_when_one_org_is_not_entitled(capsys) -> None:
    rc = _run(
        "verify", "--target", "edge", "--region", "eu", "--org", mod.prefix(ORG_A), "--org", ORG_D
    )
    assert rc == 1
    text = capsys.readouterr()
    assert "NOT entitled: blocked" in text.out + text.err


@pytest.mark.usefixtures("fake")
def test_verify_refuses_one_org_and_duplicates() -> None:
    assert _run("verify", "--target", "edge", "--region", "eu", "--org", ORG_A) == 1
    assert _run("verify", "--target", "edge", "--region", "eu", "--org", ORG_A, "--org", ORG_A) == 1


@pytest.mark.usefixtures("fake")
def test_short_or_unknown_prefix_is_refused() -> None:
    assert _run("verify", "--target", "edge", "--region", "eu", "--org", "org", "--org", ORG_B) == 1
    assert (
        _run("verify", "--target", "edge", "--region", "eu", "--org", "nomatch-xyz", "--org", ORG_B)
        == 1
    )


def _ok(rows: list[dict] | None = None) -> str:
    return json.dumps([{"success": True, "results": rows or []}])


def _after(org: str, blocked: bool) -> str:
    return _ok([_row(org, blocked_at="2026-10-26T00:00:00Z" if blocked else None)])


def _sequence(monkeypatch, *outputs: str) -> None:
    monkeypatch.setenv("FAKE_NPX_SEQ", json.dumps(list(outputs)))


def test_block_writes_through_d1_and_confirms_with_a_reread(fake, monkeypatch, capsys) -> None:
    _sequence(monkeypatch, _ok(ROWS), _ok(), _after(ORG_A, True))
    assert _run("block", "--target", "edge", "--region", "eu", "--org", mod.prefix(ORG_A)) == 0
    read, write, reread = _calls(fake)
    assert read[:5] == write[:5] == reread[:5]
    assert "--remote" in write
    command = write[write.index("--command") + 1]
    assert "SELECT o.id" in read[read.index("--command") + 1]
    assert command.count("UPDATE ") == 2
    assert "DELETE FROM config_executor_grants" in command
    assert "'console_executor.blocked'" in command
    assert "issuer_key LIKE 'executor:%'" in command
    assert "'%s'" % ORG_A in command
    assert "@ORG@" not in command
    assert "@NOW@" not in command
    shown = capsys.readouterr()
    assert mod.prefix(ORG_A) in shown.out + shown.err
    assert ORG_A not in shown.out + shown.err


def test_unblock_writes_the_clear_and_the_audit_row(fake, monkeypatch) -> None:
    _sequence(monkeypatch, _ok(ROWS), _ok(), _after(ORG_D, False))
    assert _run("unblock", "--target", "edge", "--region", "eu", "--org", ORG_D) == 0
    command = _calls(fake)[1][_calls(fake)[1].index("--command") + 1]
    assert "console_executor_blocked_at = NULL" in command
    assert "'console_executor.unblocked'" in command
    assert "api_tokens" not in command


def test_block_that_a_reread_does_not_show_is_unverified(monkeypatch, fake, capsys) -> None:
    _sequence(monkeypatch, _ok(ROWS), _ok(), _after(ORG_A, False))
    assert _run("block", "--target", "edge", "--region", "eu", "--org", ORG_A) == 1
    text = capsys.readouterr()
    assert "UNVERIFIED" in text.out + text.err
    assert len(_calls(fake)) == 3


def test_failed_write_statement_is_refused(monkeypatch, fake) -> None:
    _sequence(monkeypatch, _ok(ROWS), json.dumps([{"success": False, "results": []}]))
    assert _run("block", "--target", "edge", "--region", "eu", "--org", ORG_A) == 1
    assert len(_calls(fake)) == 2


def test_block_of_an_unknown_org_writes_nothing(fake) -> None:
    assert _run("block", "--target", "edge", "--region", "eu", "--org", "nomatch-xyz") == 1
    assert len(_calls(fake)) == 1


def test_statements_refuse_an_org_id_that_is_unsafe_in_sql() -> None:
    with pytest.raises(mod.RefusedError):
        mod.statements("block", "x'; DROP TABLE organizations; --", NOW)
    text = mod.statements("block", ORG_A, NOW)
    assert text.count(ORG_A) >= 5
    assert NOW in text


@pytest.mark.usefixtures("fake")
def test_unreadable_wrangler_output_is_unverified(monkeypatch, capsys) -> None:
    monkeypatch.setenv("FAKE_NPX_OUT", "not json")
    assert _run("list", "--target", "edge", "--region", "eu") == 1
    text = capsys.readouterr()
    assert "UNVERIFIED" in text.out + text.err


@pytest.mark.usefixtures("fake")
def test_wrangler_failure_exits_one(monkeypatch) -> None:
    monkeypatch.setenv("FAKE_NPX_RC", "1")
    assert _run("list", "--target", "stable", "--region", "us") == 1


def test_bad_target_is_refused_before_any_call(fake) -> None:
    assert _run("list", "--target", "bench", "--region", "us") == 1
    assert _calls(fake) == []


def test_bench_reads_the_bench_database(fake) -> None:
    assert _run("list", "--target", "bench") == 0
    assert _calls(fake)[0][4] == "account-db-bench"


def test_reexec_runs_this_module_under_the_profile() -> None:
    argv = mod.reexec_argv("deploy-proxy", ["list", "--target", "edge"])
    assert argv[argv.index("--profile") + 1] == "deploy-proxy"
    assert argv[argv.index("-m", 3) + 1] == mod.SELF
    assert argv[-3:] == ["list", "--target", "edge"]


def test_missing_cloudflare_env_with_a_bound_profile_is_an_error(fake, monkeypatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "deploy-proxy")
    assert _run("list", "--target", "edge", "--region", "eu") == 1
    assert _calls(fake) == []
