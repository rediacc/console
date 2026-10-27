"""Tests for `rediacc_ci.ops.rewrap_config_server_key` against a fake `npx` on a scratch PATH.

No Cloudflare credential, no network and no tsx: the fake answers `wrangler d1 time-travel info`, `wrangler d1 execute --command` (from a JSON state file of config_stores rows), `wrangler d1 execute --file` (applies the compare-and-swap UPDATEs to that state) and `tsx scripts/rewrap-config-server-key.ts kid|rewrap` (a stand-in seal: `csk1.<kid>.` plus the value reversed without its padding).
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import typing

import pytest

from rediacc_ci.ops import rewrap_config_server_key as mod

if typing.TYPE_CHECKING:
    import pathlib

KEY = "the-worker-key-value-0123456789abcdef"
KID = "abcdef12"
STORE_A = "storeaaaa-1111-2222"
STORE_B = "storebbbb-3333-4444"
VALUE_A = "QUJDREVGR0hJSktMTU5PUA=="
VALUE_B = "WllYV1ZVVFNSUVBPTk1MSw=="

FAKE_NPX = r"""#!PYTHON
import json, os, re, sys
args = sys.argv[1:]
state_path = os.environ["FAKE_STATE"]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
state = json.load(open(state_path))
def save():
    json.dump(state, open(state_path, "w"))
def ok(results):
    print("banner line")
    print(json.dumps([{"success": True, "results": results}]))
if os.environ.get("FAKE_FAIL") in args:
    sys.stderr.write("boom: echoed " + json.dumps(state["rows"]) + " key " + os.environ.get("ACCOUNT_CONFIG_SERVER_KEY", "") + "\n")
    sys.exit(7)
if args[:2] == ["tsx", "scripts/rewrap-config-server-key.ts"]:
    key = os.environ.get("ACCOUNT_CONFIG_SERVER_KEY")
    if key != os.environ["FAKE_KEY"]:
        sys.stderr.write("wrong key\n"); sys.exit(1)
    kid = os.environ["FAKE_KID"]
    if args[2] == "kid":
        print(json.dumps({"kid": kid})); sys.exit(0)
    rows = json.load(sys.stdin)["rows"]
    out = [{"id": r["id"], "old": r["value"], "new": os.environ.get("FAKE_NEW_PREFIX", "csk1.%s." % kid) + r["value"].rstrip("=")[::-1]} for r in rows]
    print(json.dumps({"kid": kid, "rows": out})); sys.exit(0)
if args[:4] == ["wrangler", "d1", "time-travel", "info"]:
    if os.environ.get("FAKE_NO_BOOKMARK"):
        sys.exit(1)
    print(json.dumps({"bookmark": "00000085-0000024c-00004c6d-8e61117bf38d7adb71b934ebbf891683"})); sys.exit(0)
if args[:3] == ["wrangler", "d1", "execute"]:
    if "--file" in args:
        sql = open(args[args.index("--file") + 1]).read()
        state["files"].append(sql)
        for row in state["rows"]:
            if row["id"] == os.environ.get("FAKE_RACE"):
                row["v"] = "UmFjZWQ" + row["v"]  # the Worker rewrote this row between the read and the CAS
        for new, sid, old in re.findall(r"SET server_recoverable_org_passphrase = '([^']*)' WHERE id = '([^']*)' AND server_recoverable_org_passphrase = '([^']*)';", sql):
            for row in state["rows"]:
                if row["id"] == sid and row["v"] == old:
                    row["v"] = new
        save(); ok([]); sys.exit(0)
    sql = args[args.index("--command") + 1]
    untagged = [r for r in state["rows"] if r["v"] is not None and not r["v"].startswith("csk1.")]
    if sql.startswith("SELECT id,"):
        ok([{"id": r["id"], "server_recoverable_org_passphrase": r["v"]} for r in untagged])
    elif sql.startswith("SELECT COUNT"):
        ok([{"n": len(untagged)}])
    elif sql.startswith("SELECT substr"):
        kids = {}
        for r in state["rows"]:
            if r["v"] and r["v"].startswith("csk1."):
                kids[r["v"][5:13]] = kids.get(r["v"][5:13], 0) + 1
        ok([{"kid": k, "n": n} for k, n in kids.items()])
    else:
        sys.exit(9)
    sys.exit(0)
sys.exit(3)
"""


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    root = tmp_path / "repo"
    (root / "workers" / "account").mkdir(parents=True)
    (root / "private" / "account").mkdir(parents=True)
    (root / "regions.json").write_text(
        json.dumps({"regions": [{"id": "eu", "secretSuffix": "EU"}]}), encoding="utf-8"
    )
    for name, db in (
        ("wrangler.edge-eu.toml", "edge-account-db-eu"),
        ("wrangler.eu.toml", "account-db-eu"),
        ("wrangler.bench.toml", "account-db-bench"),
    ):
        (root / "workers" / "account" / name).write_text(
            '[[d1_databases]]\nbinding = "DB"\ndatabase_name = "%s"\n' % db, encoding="utf-8"
        )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    npx = bindir / "npx"
    npx.write_text(FAKE_NPX.replace("PYTHON", sys.executable), encoding="utf-8")
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)
    state = tmp_path / "state.json"
    rows = [
        {"id": STORE_A, "v": VALUE_A},
        {"id": STORE_B, "v": VALUE_B},
        {"id": "storecccc-tagged", "v": "csk1.%s.Zm9v" % KID},
        {"id": "storedddd-null", "v": None},
    ]
    state.write_text(json.dumps({"rows": rows, "files": []}), encoding="utf-8")
    log = tmp_path / "npx.log"
    monkeypatch.setenv("PATH", "%s%s%s" % (bindir, os.pathsep, os.environ["PATH"]))
    monkeypatch.setenv("FAKE_STATE", str(state))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("FAKE_KEY", KEY)
    monkeypatch.setenv("FAKE_KID", KID)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "cf-account")
    monkeypatch.setenv("ACCOUNT_CONFIG_SERVER_KEY_EU_EDGE", KEY)
    monkeypatch.setenv("ACCOUNT_CONFIG_SERVER_KEY_BENCH", KEY)
    monkeypatch.delenv("ACCOUNT_CONFIG_SERVER_KEY", raising=False)
    monkeypatch.delenv("FAKE_FAIL", raising=False)
    return {"root": root, "state": state, "log": log}


def _args(**kw: object) -> argparse.Namespace:
    base = {"target": "edge", "region": "eu", "apply": False, "verify": False}
    base.update(kw)
    return argparse.Namespace(**base)


def _run(world: dict, capsys: pytest.CaptureFixture[str], **kw: object) -> tuple[int, str]:
    code = mod.run(_args(**kw), root=world["root"])
    out = capsys.readouterr()
    return code, out.out + out.err


def _state(world: dict) -> dict:
    return json.loads(world["state"].read_text(encoding="utf-8"))


def _calls(world: dict) -> list[list[str]]:
    if not world["log"].exists():
        return []
    return [json.loads(ln) for ln in world["log"].read_text(encoding="utf-8").splitlines()]


def sealed(value: str) -> str:
    return value.rstrip("=")[::-1]


def _assert_no_value(text: str) -> None:
    for secret in (KEY, VALUE_A, VALUE_B, sealed(VALUE_A), sealed(VALUE_B), STORE_A, STORE_B):
        assert secret not in text


def test_key_env_name_per_target(world) -> None:
    root = world["root"]
    assert mod.key_env_name(root, "edge", "eu") == "ACCOUNT_CONFIG_SERVER_KEY_EU_EDGE"
    assert mod.key_env_name(root, "stable", "eu") == "ACCOUNT_CONFIG_SERVER_KEY_EU_STABLE"
    assert mod.key_env_name(root, "bench", "eu") == "ACCOUNT_CONFIG_SERVER_KEY_BENCH"
    with pytest.raises(mod.RefusedError):
        mod.key_env_name(root, "edge", "mars")


def test_untagged_select_is_the_plan_query() -> None:
    assert mod.UNTAGGED_SQL == (
        "SELECT id, server_recoverable_org_passphrase FROM config_stores "
        "WHERE server_recoverable_org_passphrase IS NOT NULL "
        "AND server_recoverable_org_passphrase NOT LIKE 'csk1.%'"
    )


def test_cas_sql_compares_the_old_value_and_refuses_a_quote() -> None:
    sql = mod.cas_sql([{"id": STORE_A, "old": VALUE_A, "new": "csk1.%s.eHl6" % KID}])
    expected = (
        mod.CAS_SQL.replace("@NEW@", "csk1.%s.eHl6" % KID)
        .replace("@ID@", STORE_A)
        .replace("@OLD@", VALUE_A)
    )
    assert sql == expected + "\n"
    assert expected == (
        "UPDATE config_stores SET server_recoverable_org_passphrase = 'csk1.abcdef12.eHl6' "
        "WHERE id = 'storeaaaa-1111-2222' "
        "AND server_recoverable_org_passphrase = 'QUJDREVGR0hJSktMTU5PUA==';"
    )
    with pytest.raises(mod.RefusedError):
        mod.cas_sql([{"id": "x'y", "old": VALUE_A, "new": "csk1.%s.eHl6" % KID}])


def test_dry_run_writes_nothing_and_prints_prefixes_only(world, capsys) -> None:
    code, text = _run(world, capsys)
    assert code == 0
    assert "2 untagged row(s)" in text
    assert "storeaaa" in text
    assert "storebbb" in text
    assert "dry run" in text
    _assert_no_value(text)
    calls = _calls(world)
    assert not any("--file" in c for c in calls)
    assert not any(c[:4] == ["wrangler", "d1", "time-travel", "info"] for c in calls)
    assert _state(world)["rows"][0]["v"] == VALUE_A


def test_key_travels_in_the_environment_never_argv(world, capsys) -> None:
    _run(world, capsys)
    assert all(KEY not in " ".join(c) for c in _calls(world))


def test_apply_bookmarks_first_then_writes_cas_and_verifies(world, capsys) -> None:
    code, text = _run(world, capsys, apply=True, verify=True)
    assert code == 0, text
    calls = _calls(world)
    bookmark_at = next(
        i for i, c in enumerate(calls) if c[:4] == ["wrangler", "d1", "time-travel", "info"]
    )
    select_at = next(
        i for i, c in enumerate(calls) if "--command" in c and c[-3].startswith("SELECT id,")
    )
    file_at = next(i for i, c in enumerate(calls) if "--file" in c)
    assert bookmark_at < select_at < file_at
    assert "time-travel restore account-db-eu" not in text  # edge target names the edge database
    assert "time-travel restore edge-account-db-eu --bookmark=" in text
    state = _state(world)
    assert [r["v"] for r in state["rows"][:2]] == [
        "csk1.%s.%s" % (KID, sealed(VALUE_A)),
        "csk1.%s.%s" % (KID, sealed(VALUE_B)),
    ]
    assert state["rows"][3]["v"] is None
    (sql,) = state["files"]
    assert sql.count("UPDATE config_stores") == 2
    assert "AND server_recoverable_org_passphrase = '%s';" % VALUE_A in sql
    assert "no untagged row; 3 row(s) under csk1.%s" % KID in text
    _assert_no_value(text)


def test_apply_without_verify_exits_0_when_every_row_is_written(world, capsys) -> None:
    code, text = _run(world, capsys, apply=True)
    assert code == 0, text
    assert "remain after the write" not in text


def test_apply_without_verify_exits_1_when_a_row_moved_under_its_cas(
    world, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("FAKE_RACE", STORE_B)
    code, text = _run(world, capsys, apply=True)
    assert code == 1
    assert "1 untagged row(s) remain after the write" in text
    rows = _state(world)["rows"]
    assert rows[0]["v"] == "csk1.%s.%s" % (KID, sealed(VALUE_A))
    assert not rows[1]["v"].startswith("csk1.")
    _assert_no_value(text)


def test_apply_temp_file_is_removed(world, capsys) -> None:
    _run(world, capsys, apply=True)
    path = next(c for c in _calls(world) if "--file" in c)
    assert not os.path.exists(path[path.index("--file") + 1])


def test_no_bookmark_writes_nothing(world, capsys, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_NO_BOOKMARK", "1")
    code, text = _run(world, capsys, apply=True)
    assert code == 1
    assert "NO D1 BOOKMARK" in text
    assert not any("--file" in c for c in _calls(world))


def test_verify_exits_1_while_an_untagged_row_is_left(world, capsys) -> None:
    code, text = _run(world, capsys, verify=True)
    assert code == 1
    assert "2 untagged row(s)" in text
    _assert_no_value(text)


def test_verify_exits_0_when_clean(world, capsys) -> None:
    data = _state(world)
    data["rows"] = [r for r in data["rows"] if r["id"] not in (STORE_A, STORE_B)]
    world["state"].write_text(json.dumps(data), encoding="utf-8")
    code, text = _run(world, capsys, verify=True)
    assert code == 0, text


def test_verify_exits_1_on_a_foreign_kid(world, capsys) -> None:
    data = _state(world)
    data["rows"] = [{"id": STORE_A, "v": "csk1.99999999.Zm9v"}]
    world["state"].write_text(json.dumps(data), encoding="utf-8")
    code, text = _run(world, capsys, verify=True)
    assert code == 1
    assert "foreign kid (99999999)" in text


def test_helper_sealing_under_another_kid_refuses_before_any_write(
    world, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("FAKE_NEW_PREFIX", "csk1.00000000.")
    code, text = _run(world, capsys, apply=True)
    assert code == 1
    assert "did not come back sealed" in text
    assert not any("--file" in c for c in _calls(world))
    _assert_no_value(text)


def test_wrangler_failure_output_is_masked(world, capsys, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_FAIL", "--file")
    code, text = _run(world, capsys, apply=True)
    assert code == 1
    assert "exited 7" in text
    assert mod.REDACTED in text
    assert "storeaaa" in text
    _assert_no_value(text)


def test_helper_failure_output_is_masked(world, capsys, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_FAIL", "rewrap")
    code, text = _run(world, capsys)
    assert code == 1
    assert "the rewrap helper (rewrap) exited 7" in text
    assert mod.REDACTED in text
    _assert_no_value(text)


def test_missing_key_refuses_when_the_profile_is_bound(world, capsys, monkeypatch) -> None:
    monkeypatch.delenv("ACCOUNT_CONFIG_SERVER_KEY_EU_EDGE")
    monkeypatch.setenv("REDIACC_BWS_PROFILES", mod.PROFILE)
    code, text = _run(world, capsys)
    assert code == 1
    assert "ACCOUNT_CONFIG_SERVER_KEY_EU_EDGE must be set" in text
    assert _calls(world) == []


def test_bench_reads_the_bench_key_and_database(world, capsys) -> None:
    code, text = _run(world, capsys, target="bench", region=None)
    assert code == 0, text
    assert any("account-db-bench" in c for c in _calls(world))


def test_reexec_argv_names_the_profile_and_self() -> None:
    argv = mod.reexec_argv(["--target", "edge", "--region", "eu"])
    assert argv[argv.index("--profile") + 1] == "rewrap-config-server-key"
    assert argv[-5:] == [mod.SELF, "--target", "edge", "--region", "eu"]
