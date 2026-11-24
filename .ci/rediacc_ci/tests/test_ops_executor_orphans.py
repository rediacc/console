"""Tests for `rediacc_ci.ops.executor_orphans`: the SQL runs against a seeded SQLite with executor and non-executor events, and the D1 path against a fake `npx` (wrangler) on a scratch PATH. No credential, no network."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import stat
import typing

import pytest

from rediacc_ci.ops import executor_orphans as mod

if typing.TYPE_CHECKING:
    import pathlib

ORG = "org12345678-aaaa-bbbb"
OTHER_ORG = "orgabcdefgh-cccc-dddd"

SCHEMA = (
    "CREATE TABLE event_log (id TEXT PRIMARY KEY, type TEXT NOT NULL, source TEXT NOT NULL, "
    "org_id TEXT, data TEXT, timestamp TEXT NOT NULL)"
)

# The GUID the executor ships on a fork event (audit.ts repositoryIdentity), passed through unchanged.
FORK_GUID = "e9304ffc-0c96-47f2-a2fb-6076c1df6f52"
EXECUTOR = {"commandPath": "repo create", "functionName": "x", "success": True}
# (id, type, source, org, data, timestamp)
SEED = [
    (
        "e1",
        "cli.repo.create",
        "cli",
        ORG,
        {"machineName": "m1", "repoName": "alpha", **EXECUTOR},
        "2026-11-20T10:00:00Z",
    ),
    (
        "e2",
        "cli.repo.fork",
        "cli",
        ORG,
        {"machineName": "m1", "repoName": "alpha", "guid": FORK_GUID, **EXECUTOR},
        "2026-11-20T11:00:00Z",
    ),
    (
        "e3",
        "cli.machine.provision",
        "cli",
        OTHER_ORG,
        {"machineName": "vm9", **EXECUTOR},
        "2026-11-20T12:00:00Z",
    ),
    # Controls that must not appear: a CLI's own event (no commandPath), a type outside the three, another source.
    (
        "c1",
        "cli.repo.create",
        "cli",
        ORG,
        {"machineName": "m1", "repoName": "own-cli"},
        "2026-11-20T09:00:00Z",
    ),
    (
        "c2",
        "cli.repo.up",
        "cli",
        ORG,
        {"machineName": "m1", "repoName": "alpha", **EXECUTOR},
        "2026-11-20T13:00:00Z",
    ),
    (
        "c3",
        "cli.repo.create",
        "portal",
        ORG,
        {"machineName": "m1", "repoName": "portal", **EXECUTOR},
        "2026-11-20T14:00:00Z",
    ),
]


def seed(path: pathlib.Path, rows: list[tuple] | None = None) -> pathlib.Path:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute(SCHEMA)
        for rid, kind, source, org, data, at in SEED if rows is None else rows:
            conn.execute(
                "INSERT INTO event_log VALUES (?, ?, ?, ?, ?, ?)",
                (rid, kind, source, org, json.dumps(data), at),
            )
        conn.commit()
    return path


@pytest.fixture
def db(tmp_path: pathlib.Path) -> pathlib.Path:
    return seed(tmp_path / "account.db")


def _run(*argv: str) -> int:
    return mod.main(list(argv))


def test_sql_selects_only_executor_events(db: pathlib.Path) -> None:
    events = [mod.to_event(r) for r in mod.read_sqlite(db)]
    assert [e["function"] for e in events] == [
        "repository_create",
        "repository_fork",
        "machine_provision",
    ]
    repos = {e["repo"] for e in events}
    assert "own-cli" not in repos
    assert "portal" not in repos


def test_json_contract_is_one_line_per_event(
    db: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    assert _run("list", "--target", "onprem", "--sqlite", str(db), "--json") == 0
    out = capsys.readouterr()
    lines = out.out.splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert list(first) == ["org", "machine", "repo", "guid", "at", "function"]
    assert first == {
        "org": "org12345",
        "machine": "m1",
        "repo": "alpha",
        "guid": None,
        "at": "2026-11-20T10:00:00Z",
        "function": "repository_create",
    }
    assert json.loads(lines[1])["guid"] == FORK_GUID
    assert json.loads(lines[2])["repo"] is None
    assert ORG not in out.out
    assert ORG not in out.err


def test_table_has_a_header_and_a_row_per_event(
    db: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    assert _run("list", "--target", "onprem", "--sqlite", str(db)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == list(mod.FIELDS)
    assert len(lines) == 4
    assert "repository_fork" in lines[2]


def test_no_events_prints_no_stdout(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    empty = seed(tmp_path / "empty.db", [SEED[3]])
    assert _run("list", "--target", "onprem", "--sqlite", str(empty), "--json") == 0
    out = capsys.readouterr()
    assert out.out == ""
    assert "0 executor event" in out.err


def test_env_file_names_the_sqlite(
    db: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    env = tmp_path / "stack.env"
    env.write_text("OTHER=1\n%s=%s\n" % (mod.SQLITE_ENV_KEY, db), encoding="utf-8")
    assert _run("list", "--target", "onprem", "--env", str(env), "--json") == 0
    assert len(capsys.readouterr().out.splitlines()) == 3


def test_env_file_without_the_key_is_refused(tmp_path: pathlib.Path) -> None:
    env = tmp_path / "stack.env"
    env.write_text("OTHER=1\n", encoding="utf-8")
    assert _run("list", "--target", "onprem", "--env", str(env)) == 1


def test_missing_or_foreign_sqlite_is_refused(tmp_path: pathlib.Path) -> None:
    assert _run("list", "--target", "onprem", "--sqlite", str(tmp_path / "none.db")) == 1
    other = tmp_path / "other.db"
    with contextlib.closing(sqlite3.connect(other)) as conn:
        conn.execute("CREATE TABLE t (a)")
    assert _run("list", "--target", "onprem", "--sqlite", str(other)) == 1


def test_onprem_needs_exactly_one_source(db: pathlib.Path) -> None:
    assert _run("list", "--target", "onprem") == 1
    assert _run("list", "--target", "onprem", "--sqlite", str(db), "--env", "x") == 1


def test_sqlite_flag_on_a_remote_target_is_refused(db: pathlib.Path) -> None:
    assert _run("list", "--target", "stable", "--region", "eu", "--sqlite", str(db)) == 1


def test_the_source_is_opened_read_only(db: pathlib.Path) -> None:
    before = db.read_bytes()
    mod.read_sqlite(db)
    assert db.read_bytes() == before
    assert not list(db.parent.glob("account.db-*"))


FAKE_NPX = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(["npx"] + sys.argv[1:]) + "\\n")
sys.stdout.write(os.environ.get("FAKE_NPX_OUT", ""))
sys.exit(int(os.environ.get("FAKE_NPX_RC", "0")))
"""


@pytest.fixture
def fake(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    path = bin_dir / "npx"
    path.write_text(FAKE_NPX, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.jsonl"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token-secret-value")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    row = {
        "org_id": ORG,
        "type": "cli.repo.create",
        "at": "2026-11-20T10:00:00Z",
        "machine": "m1",
        "repo": "alpha",
        "guid": None,
    }
    monkeypatch.setenv("FAKE_NPX_OUT", json.dumps([{"success": True, "results": [row]}]))
    return log


def test_d1_read_is_one_select_and_prints_the_contract(
    fake: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    assert _run("list", "--target", "stable", "--region", "eu", "--json") == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["org"] == "org12345"
    assert ORG not in out.out + out.err
    (call,) = [json.loads(line) for line in fake.read_text().splitlines()]
    assert call[:6] == ["npx", "--no-install", "wrangler", "d1", "execute", "account-eu"]
    assert "--remote" in call
    command = call[call.index("--command") + 1]
    assert command.startswith("SELECT ")
    assert "commandPath" in command
    assert "INSERT" not in command.upper()
    assert "cf-token-secret-value" not in " ".join(call)


@pytest.mark.usefixtures("fake")
def test_d1_failure_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_NPX_RC", "1")
    assert _run("list", "--target", "stable", "--region", "eu") == 1


@pytest.mark.usefixtures("fake")
def test_d1_output_without_rows_is_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_NPX_OUT", "no json here")
    assert _run("list", "--target", "stable", "--region", "eu") == 1


def test_stable_without_a_region_reads_every_region(fake: pathlib.Path) -> None:
    assert _run("list", "--target", "stable", "--json") == 0
    calls = [json.loads(line) for line in fake.read_text().splitlines()]
    assert {c[5] for c in calls} == {"account-eu", "account-us", "account-asia"}


def test_missing_credentials_under_a_bound_profile_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("REDIACC_BWS_PROFILES", mod.PROFILE)
    assert _run("list", "--target", "stable", "--region", "eu") == 1
