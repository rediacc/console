"""`rediacc_ci.deploy.console_executor`: the EXECUTOR_MODE switch, with a fake `npx wrangler` on PATH whose secret store is a JSON file.

Nothing reaches Cloudflare. The fake records every argv and the bytes on its stdin, keeps the secrets in `FAKE_STORE`, and can be told to fail or to lie (exit 0 without changing the store), which is what the read-back exists to catch. The same fake serves `test_deploy_deploy_record.py`, so it also answers `deployments list` and `d1 time-travel info` from `FAKE_SCENARIO`.
"""

from __future__ import annotations

import json
import os
import stat
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import console_executor as ce

if TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

FAKE_NPX = r"""#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
stdin = sys.stdin.read() if not sys.stdin.isatty() else ""
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": args, "stdin": stdin, "cwd": os.path.basename(os.getcwd())}) + "\n")
assert args[:2] == ["--no-install", "wrangler"], args
cmd = args[2:]
store_path = pathlib.Path(os.environ["FAKE_STORE"])
store = json.loads(store_path.read_text()) if store_path.is_file() else []
scenario_path = os.environ.get("FAKE_SCENARIO", "")
scenario = json.loads(pathlib.Path(scenario_path).read_text()) if scenario_path and pathlib.Path(scenario_path).is_file() else {}
def opt(name):
    return cmd[cmd.index(name) + 1] if name in cmd else ""
def answer(entry):
    sys.stdout.write(entry.get("out", ""))
    sys.stderr.write(entry.get("err", ""))
    sys.exit(int(entry.get("rc", 0)))
if cmd[:2] == ["secret", "put"]:
    rc = int(os.environ.get("FAKE_PUT_RC", "0"))
    if rc == 0 and not os.environ.get("FAKE_PUT_LIES"):
        store = sorted(set(store) | {cmd[2]})
        store_path.write_text(json.dumps(store))
    sys.exit(rc)
if cmd[:2] == ["secret", "delete"]:
    if os.environ.get("FAKE_DELETE_LIES"):
        sys.exit(0)
    if cmd[2] not in store:
        sys.stderr.write("X [ERROR] A request to the Cloudflare API failed. secret not found [code: 10056]\n")
        sys.exit(1)
    store_path.write_text(json.dumps([n for n in store if n != cmd[2]]))
    sys.exit(0)
if cmd[:2] == ["secret", "list"]:
    if os.environ.get("FAKE_LIST_RC"):
        sys.stderr.write("X [ERROR] Authentication error [code: 10000]\n")
        sys.exit(int(os.environ["FAKE_LIST_RC"]))
    if os.environ.get("FAKE_LIST_RAW") is not None:
        sys.stdout.write(os.environ["FAKE_LIST_RAW"])
        sys.exit(0)
    sys.stdout.write(" wrangler 4.152.0\n" + json.dumps([{"name": n, "type": "secret_text"} for n in store]) + "\n")
    sys.exit(0)
if cmd[:2] == ["deployments", "list"]:
    answer(scenario.get("deployments", {}).get(opt("--config"), {"rc": 1, "err": "no scenario for " + opt("--config")}))
if cmd[:3] == ["d1", "time-travel", "info"]:
    answer(scenario.get("time_travel", {"rc": 1, "err": "no scenario"}))
sys.stderr.write("fake npx: unhandled %r\n" % (args,))
sys.exit(97)
"""


def install_fake_npx(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """The fake on PATH, an empty store, a call log; returns the log path."""
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "npx"
    fake.write_text(FAKE_NPX)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("PATH", "%s%s%s" % (bin_dir, os.pathsep, os.environ["PATH"]))
    monkeypatch.setenv("FAKE_CALL_LOG", str(log))
    monkeypatch.setenv("FAKE_STORE", str(tmp_path / "store.json"))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fake-token-value")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "fake-account")
    for name in (
        "FAKE_PUT_RC",
        "FAKE_PUT_LIES",
        "FAKE_DELETE_LIES",
        "FAKE_LIST_RC",
        "FAKE_LIST_RAW",
    ):
        monkeypatch.delenv(name, raising=False)
    return log


def calls(log: pathlib.Path) -> list[dict]:
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line]


def store(tmp_path: pathlib.Path) -> list[str]:
    path = tmp_path / "store.json"
    return json.loads(path.read_text()) if path.is_file() else []


@pytest.fixture
def fake(tmp_path, monkeypatch):
    return install_fake_npx(tmp_path, monkeypatch)


# ---- naming -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "region", "config"),
    [
        ("stable", "us", "wrangler.us.toml"),
        ("edge", "asia", "wrangler.edge-asia.toml"),
        ("bench", "eu", "wrangler.bench.toml"),
    ],
)
def test_each_target_names_its_own_account_config_and_it_exists(target, region, config):
    assert ce.account_config(target, region) == config
    assert (ROOT / "workers" / "account" / config).is_file()


def test_bench_refuses_another_region_and_an_unknown_target_is_refused():
    with pytest.raises(ce.RefusedError, match="bench refuses --region us"):
        ce.resolve_target(ROOT, "bench", "us")
    with pytest.raises(ce.RefusedError, match="not one of"):
        ce.resolve_target(ROOT, "production", "eu")
    with pytest.raises(ce.RefusedError, match="--region mars"):
        ce.resolve_target(ROOT, "edge", "mars")


def test_secret_names_reads_past_a_banner_and_refuses_other_shapes():
    assert ce.secret_names(' wrangler 4\n[{"name": "A", "type": "secret_text"}]\n') == {"A"}
    assert ce.secret_names("[]") == set()
    assert ce.secret_names("not json") is None
    assert ce.secret_names('[{"type": "secret_text"}]') is None
    assert ce.secret_names('{"name": "A"}') is None


# ---- enable -----------------------------------------------------------------


def test_enable_puts_the_value_on_stdin_never_on_argv_and_reads_it_back(fake, tmp_path):
    assert ce.main(["--enable", "--target", "edge", "--region", "us"]) == 0
    log = calls(fake)
    put = log[0]
    assert put["argv"] == [
        "--no-install",
        "wrangler",
        "secret",
        "put",
        "EXECUTOR_MODE",
        "--name",
        "edge-rediacc-account-us",
        "--config",
        "wrangler.edge-us.toml",
    ]
    assert put["stdin"] == "proxy"
    assert put["cwd"] == "account"
    assert all("proxy" not in c["argv"] for c in log)
    assert log[1]["argv"][:4] == ["--no-install", "wrangler", "secret", "list"]
    assert "--format" in log[1]["argv"]
    assert store(tmp_path) == ["EXECUTOR_MODE"]


@pytest.mark.usefixtures("fake")
def test_enable_whose_put_exits_0_without_setting_the_secret_fails(monkeypatch):
    monkeypatch.setenv("FAKE_PUT_LIES", "1")
    assert ce.main(["--enable", "--target", "stable", "--region", "eu"]) == 1


@pytest.mark.usefixtures("fake")
def test_enable_whose_read_back_fails_is_unknown_and_fails(monkeypatch):
    monkeypatch.setenv("FAKE_LIST_RC", "1")
    assert ce.main(["--enable", "--target", "stable", "--region", "eu"]) == 1


def test_enable_whose_put_fails_stops_before_the_read_back(fake, monkeypatch):
    monkeypatch.setenv("FAKE_PUT_RC", "1")
    assert ce.main(["--enable", "--target", "stable", "--region", "eu"]) == 1
    assert len(calls(fake)) == 1


def test_missing_credentials_refuse_before_any_wrangler_call(fake, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "deploy-proxy")
    assert ce.main(["--enable", "--target", "edge", "--region", "eu"]) == 1
    assert calls(fake) == []


def test_missing_credentials_reexec_under_the_profile_when_unbound(fake, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    seen = []

    def fake_run(argv, **_kw):
        seen.append(argv)
        return type("P", (), {"returncode": 7})()

    monkeypatch.setattr(ce.subprocess, "run", fake_run)
    args = ["--enable", "--target", "bench"]
    assert ce.main(args) == 7
    assert seen[0][1:8] == [
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        "deploy-proxy-bench",
        "--",
        seen[0][7],
    ]
    assert seen[0][-5:] == ["-m", ce.SELF, *args]
    assert calls(fake) == []


def test_reexec_carries_the_callers_own_region_argv(fake, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    seen = []

    def fake_run(argv, **_kw):
        seen.append(argv)
        return type("P", (), {"returncode": 0})()

    monkeypatch.setattr(ce.subprocess, "run", fake_run)
    args = ["--enable", "--target", "stable", "--region", "asia"]
    assert ce.main(args) == 0
    assert seen[0][-7:] == ["-m", ce.SELF, *args]
    assert calls(fake) == []


def test_a_profile_list_with_spaces_still_reports_the_profile_bound(fake, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "deploy-proxy, deploy-proxy-bench")
    monkeypatch.setattr(ce.subprocess, "run", lambda *_a, **_k: pytest.fail("re-exec"))
    assert ce.profile_bound("deploy-proxy-bench")
    assert ce.main(["--enable", "--target", "bench"]) == 1
    assert calls(fake) == []


# ---- disable ----------------------------------------------------------------


def test_disable_deletes_the_secret_with_no_stdin_and_confirms_it_is_gone(fake, tmp_path):
    (tmp_path / "store.json").write_text(json.dumps(["EXECUTOR_MODE", "OTHER"]))
    assert ce.main(["--disable", "--target", "edge", "--region", "eu"]) == 0
    log = calls(fake)
    assert log[0]["argv"][:5] == ["--no-install", "wrangler", "secret", "delete", "EXECUTOR_MODE"]
    assert log[0]["stdin"] == ""
    assert store(tmp_path) == ["OTHER"]


@pytest.mark.usefixtures("fake")
def test_disable_of_a_secret_never_set_is_already_closed(tmp_path, capsys):
    (tmp_path / "store.json").write_text(json.dumps(["OTHER"]))
    assert ce.main(["--disable", "--target", "stable", "--region", "asia"]) == 0
    assert "already closed" in capsys.readouterr().err


@pytest.mark.usefixtures("fake")
def test_disable_whose_delete_lies_reports_the_region_open(tmp_path, monkeypatch):
    (tmp_path / "store.json").write_text(json.dumps(["EXECUTOR_MODE"]))
    monkeypatch.setenv("FAKE_DELETE_LIES", "1")
    assert ce.main(["--disable", "--target", "stable", "--region", "asia"]) == 1


@pytest.mark.usefixtures("fake")
def test_disable_with_an_unparseable_listing_is_unknown(monkeypatch):
    monkeypatch.setenv("FAKE_LIST_RAW", "Something went wrong")
    assert ce.main(["--disable", "--target", "bench"]) == 1


def test_bench_disable_names_the_bench_worker(fake):
    assert ce.main(["--disable", "--target", "bench"]) == 0
    assert calls(fake)[0]["argv"][5:9] == [
        "--name",
        "rediacc-account-bench",
        "--config",
        "wrangler.bench.toml",
    ]


def test_enable_and_disable_are_mutually_exclusive_and_one_is_required(fake):
    assert ce.main(["--enable", "--disable", "--target", "edge", "--region", "eu"]) == 2
    assert ce.main(["--target", "edge", "--region", "eu"]) == 2
    assert calls(fake) == []
