"""`rediacc_ci.deploy.deploy_record`: the before record, the bootstrap, the reverse-order rollback and the after record, against a fake `npx wrangler` and a fake `aws` on PATH.

Nothing reaches Cloudflare or R2. The wrangler fake is `test_deploy_console_executor.FAKE_NPX` (deployments, D1 time travel and secrets answered from files); the aws fake's bucket is a directory and answers a missing key with NoSuchKey, as R2 does. `deploy_proxy` children are swapped for a recording script through `deploy_record.deploy_proxy_argv`. The configs read are the real `workers/account` and `workers/proxy` files.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.deploy import deploy_record as dr
from rediacc_ci.tests.test_deploy_console_executor import calls, install_fake_npx

if TYPE_CHECKING:
    import pathlib

VERSION = "1.4.2"
PREV_RELEASE = "1.4.1"
ACCOUNT_OLD = "aaaaaaaa-0000-4000-8000-000000000001"
ACCOUNT_NEW = "aaaaaaaa-0000-4000-8000-000000000002"
PROXY_OLD = "bbbbbbbb-0000-4000-8000-000000000001"
PROXY_NEW = "bbbbbbbb-0000-4000-8000-000000000002"
BOOKMARK = "00000085-0000024c-00004c6d-8e61117bf38d7adb71b934ebbf891683"
SHA = {
    name: ("%x" % i) * 64
    for i, name in enumerate(
        ("cli-bundle.cjs", "node-natives-linux-x64.tar", "package.json", "renet-linux-amd64"),
        start=1,
    )
}

FAKE_AWS = r"""#!/usr/bin/env python3
import json, os, pathlib, sys
bucket = pathlib.Path(os.environ["FAKE_BUCKET"])
args = sys.argv[1:]
def opt(name):
    return args[args.index(name) + 1]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": ["aws", *args], "stdin": "", "cwd": ""}) + "\n")
if os.environ.get("FAKE_AWS_BROKEN"):
    sys.stderr.write("An error occurred (AccessDenied) when calling the GetObject operation\n")
    sys.exit(254)
verb = args[1]
if verb == "get-object":
    src = bucket / opt("--key")
    if not src.is_file():
        sys.stderr.write("An error occurred (NoSuchKey) when calling the GetObject operation: nope\n")
        sys.exit(254)
    pathlib.Path(args[-1]).write_bytes(src.read_bytes())
elif verb == "put-object":
    dst = bucket / opt("--key")
    if "--if-none-match" in args and dst.exists():
        sys.stderr.write("An error occurred (PreconditionFailed) when calling the PutObject operation: 412\n")
        sys.exit(254)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(pathlib.Path(opt("--body")).read_bytes())
    (bucket / (opt("--key") + ".cache-control")).write_text(opt("--cache-control"))
else:
    sys.exit(2)
"""

# The deploy_proxy stand-in: logs its argv, writes `--record` with FAKE_PROXY_VERSION when that is set, exits FAKE_PROXY_RC.
FAKE_PROXY = r"""
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": ["deploy_proxy", *args], "stdin": "", "cwd": ""}) + "\n")
if "--record" in args and os.environ.get("FAKE_PROXY_VERSION"):
    with open(args[args.index("--record") + 1], "w") as fh:
        json.dump({"version_id": os.environ["FAKE_PROXY_VERSION"]}, fh)
sys.exit(int(os.environ.get("FAKE_PROXY_RC", "0")))
"""


def deployments(version: str | None) -> dict:
    if version is None:
        return {
            "rc": 1,
            "err": "X [ERROR] This Worker does not exist on your account. [code: 10007]\n",
        }
    body = [
        {
            "created_on": "2026-10-01T00:00:00Z",
            "versions": [{"version_id": "older", "percentage": 100}],
        },
        {
            "created_on": "2026-10-20T00:00:00Z",
            "versions": [{"version_id": version, "percentage": 100}],
        },
    ]
    return {"rc": 0, "out": " wrangler 4.152.0\n" + json.dumps(body)}


class World:
    def __init__(self, tmp_path: pathlib.Path, log: pathlib.Path) -> None:
        self.tmp = tmp_path
        self.log = log
        self.bucket = tmp_path / "bucket"
        self.scenario = tmp_path / "scenario.json"
        self.dir = tmp_path / "records"
        self.dir.mkdir()
        self.set(account=ACCOUNT_OLD, proxy=PROXY_OLD)

    def set(
        self, *, account: str | None, proxy: str | None, time_travel: dict | None = None
    ) -> None:
        """The scenario the wrangler fake answers. Deployments are keyed on the cwd (`account` or `proxy`), because both Workers' configs are named wrangler.edge-eu.toml."""
        default_tt = {
            "rc": 0,
            "out": json.dumps({"bookmark": BOOKMARK, "timestamp": "2026-10-26T00:00:00Z"}),
        }
        self.scenario.write_text(
            json.dumps(
                {
                    "deployments": {"account": deployments(account), "proxy": deployments(proxy)},
                    "time_travel": time_travel or default_tt,
                }
            )
        )

    def stage(self, version: str = VERSION) -> None:
        path = self.bucket / "executor" / ("v%s" % version) / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        files = {name: {"sha256": sha, "size": 10} for name, sha in SHA.items()}
        path.write_text(json.dumps({"version": version, "git_sha": "deadbeef", "files": files}))

    def pointer(self, release: str) -> None:
        path = self.bucket / dr.pointer_key("edge", "eu")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"release_version": release, "version_id": PROXY_OLD}))

    def before(self) -> pathlib.Path:
        return self.dir / "before.json"


@pytest.fixture
def world(tmp_path, monkeypatch):
    log = install_fake_npx(tmp_path, monkeypatch)
    # The wrangler fake keys deployments on --config; both Workers' files are named wrangler.edge-eu.toml, so this wrapper rewrites the key to the cwd (account or proxy).
    npx = tmp_path / "fake-bin" / "npx"
    keyed_on_config = 'answer(scenario.get("deployments", {}).get(opt("--config")'
    assert keyed_on_config in npx.read_text()
    npx.write_text(
        npx.read_text().replace(
            keyed_on_config,
            'answer(scenario.get("deployments", {}).get(os.path.basename(os.getcwd())',
        )
    )
    aws = tmp_path / "fake-bin" / "aws"
    aws.write_text(FAKE_AWS)
    aws.chmod(aws.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "bucket").mkdir()
    monkeypatch.delenv("AWS_BIN", raising=False)
    monkeypatch.delenv("FAKE_AWS_BROKEN", raising=False)
    monkeypatch.setenv("FAKE_BUCKET", str(tmp_path / "bucket"))
    monkeypatch.setenv("FAKE_SCENARIO", str(tmp_path / "scenario.json"))
    monkeypatch.setenv("CLOUDFLARE_R2_ENDPOINT", "https://r2.example.invalid")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github_output"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    proxy = tmp_path / "fake_proxy.py"
    proxy.write_text(FAKE_PROXY)
    monkeypatch.setattr(dr, "deploy_proxy_argv", lambda *a: [sys.executable, str(proxy), *a])
    for name in ("FAKE_PROXY_RC", "FAKE_PROXY_VERSION"):
        monkeypatch.delenv(name, raising=False)
    w = World(tmp_path, log)
    w.stage()
    return w


def run_before(world: World) -> int:
    return dr.main(
        [
            "before",
            "--target",
            "edge",
            "--region",
            "eu",
            "--version",
            VERSION,
            "--out",
            str(world.before()),
        ]
    )


# ---- parsing ----------------------------------------------------------------


def test_deployed_version_reads_the_newest_100_percent_version_past_a_banner():
    assert dr.parse_deployed_version(deployments(PROXY_NEW)["out"]) == (True, PROXY_NEW)
    assert dr.parse_deployed_version("[]") == (True, None)
    split = [
        {
            "created_on": "2026-10-20",
            "versions": [
                {"version_id": "a", "percentage": 50},
                {"version_id": "b", "percentage": 50},
            ],
        }
    ]
    assert dr.parse_deployed_version(json.dumps(split)) == (False, None)
    assert dr.parse_deployed_version("Authentication error") == (False, None)


def test_bookmark_reads_json_then_falls_back_to_the_pattern_and_else_is_none():
    assert dr.parse_bookmark(json.dumps({"bookmark": BOOKMARK})) == BOOKMARK
    assert dr.parse_bookmark("Bookmark: %s\n" % BOOKMARK) == BOOKMARK
    assert dr.parse_bookmark('{"bookmark": ""}') is None
    assert dr.parse_bookmark("nothing") is None


# ---- before -----------------------------------------------------------------


def test_before_records_every_handle_and_the_rollback_commands(world):
    world.pointer(PREV_RELEASE)
    assert run_before(world) == 0
    rec = json.loads(world.before().read_text())
    assert rec["account"] == {
        "worker": "edge-rediacc-account-eu",
        "config": "workers/account/wrangler.edge-eu.toml",
        "version_before": ACCOUNT_OLD,
    }
    assert rec["d1"] == {"database": "edge-account-db-eu", "bookmark": BOOKMARK}
    assert rec["proxy"]["worker"] == "edge-rediacc-proxy-eu"
    assert rec["proxy"]["existed"] is True
    assert rec["proxy"]["version_before"] == PROXY_OLD
    assert rec["proxy"]["release_before"] == PREV_RELEASE
    assert rec["executor_manifest"]["sha256"] == SHA
    rb = rec["rollback"]
    assert sorted(rb) == ["1_console_executor", "2_proxy", "3_account", "4_d1"]
    assert rb["1_console_executor"].endswith("console_executor --disable --target edge --region eu")
    assert rb["2_proxy"].endswith(
        "deploy_proxy --target edge --region eu --version %s" % PREV_RELEASE
    )
    assert (
        rb["3_account"]
        == "cd workers/account && npx --no-install wrangler rollback %s --config wrangler.edge-eu.toml"
        % ACCOUNT_OLD
    )
    assert rb["4_d1"] == (
        "cd workers/account && npx --no-install wrangler d1 time-travel restore edge-account-db-eu --bookmark=%s --config wrangler.edge-eu.toml"
        % BOOKMARK
    )
    assert (world.tmp / "github_output").read_text() == "proxy_exists=true\n"
    tt = [c for c in calls(world.log) if c["argv"][2:5] == ["d1", "time-travel", "info"]]
    assert tt[0]["argv"][5:] == [
        "edge-account-db-eu",
        "--json",
        "--config",
        "wrangler.edge-eu.toml",
    ]
    assert tt[0]["cwd"] == "account"


def test_before_with_no_proxy_worker_says_bootstrap_and_has_no_proxy_rollback(world):
    world.set(account=ACCOUNT_OLD, proxy=None)
    assert run_before(world) == 0
    rec = json.loads(world.before().read_text())
    assert rec["proxy"]["existed"] is False
    assert rec["proxy"]["release_before"] is None
    assert rec["rollback"]["2_proxy"].startswith("none:")
    assert (world.tmp / "github_output").read_text() == "proxy_exists=false\n"


def test_before_without_a_pointer_offers_only_the_worker_script_rollback(world):
    assert run_before(world) == 0
    rb = json.loads(world.before().read_text())["rollback"]["2_proxy"]
    assert rb.startswith("cd workers/proxy && npx --no-install wrangler rollback %s" % PROXY_OLD)
    assert "Worker script only" in rb


@pytest.mark.parametrize(
    "case",
    [
        "no-bookmark",
        "bookmark-rc",
        "proxy-unknown",
        "split-rollout",
        "not-staged",
        "r2-broken",
        "bad-version",
        "bad-pointer",
    ],
)
def test_before_refuses_every_unknown_and_writes_nothing(world, monkeypatch, case):
    if case == "no-bookmark":
        world.set(account=ACCOUNT_OLD, proxy=PROXY_OLD, time_travel={"rc": 0, "out": "{}"})
    elif case == "bookmark-rc":
        world.set(
            account=ACCOUNT_OLD, proxy=PROXY_OLD, time_travel={"rc": 1, "err": "rate limited"}
        )
    elif case == "proxy-unknown":
        data = json.loads(world.scenario.read_text())
        data["deployments"]["proxy"] = {
            "rc": 1,
            "err": "X [ERROR] Authentication error [code: 10000]",
        }
        world.scenario.write_text(json.dumps(data))
    elif case == "split-rollout":
        data = json.loads(world.scenario.read_text())
        split = [
            {
                "created_on": "2026-10-20",
                "versions": [
                    {"version_id": "a", "percentage": 10},
                    {"version_id": "b", "percentage": 90},
                ],
            }
        ]
        data["deployments"]["proxy"] = {"rc": 0, "out": json.dumps(split)}
        world.scenario.write_text(json.dumps(data))
    elif case == "not-staged":
        (world.bucket / "executor" / ("v%s" % VERSION) / "manifest.json").unlink()
    elif case == "r2-broken":
        monkeypatch.setenv("FAKE_AWS_BROKEN", "1")
    elif case == "bad-pointer":
        world.pointer("latest")
    if case == "bad-version":
        rc = dr.main(
            [
                "before",
                "--target",
                "edge",
                "--region",
                "eu",
                "--version",
                "v1.4",
                "--out",
                str(world.before()),
            ]
        )
    else:
        rc = run_before(world)
    assert rc == 1
    assert not world.before().exists()
    assert not (world.tmp / "github_output").exists()


# ---- before --account-only ---------------------------------------------------


def run_account_before(world: World) -> int:
    return dr.main(
        [
            "before",
            "--target",
            "edge",
            "--region",
            "eu",
            "--account-only",
            "--out",
            str(world.before()),
        ]
    )


def test_account_only_before_needs_no_staged_executor_and_no_proxy(world, capsys):
    """The 2026-10-27 eu edge deploy: no executor/v<V>/ was staged anywhere, and the account-only deploy still needs its bookmark first."""
    (world.bucket / "executor" / ("v%s" % VERSION) / "manifest.json").unlink()
    world.set(account=ACCOUNT_OLD, proxy=None)
    assert run_account_before(world) == 0
    rec = json.loads(world.before().read_text())
    assert rec["account_only"] is True
    assert rec["version"] is None
    assert rec["account"] == {
        "worker": "edge-rediacc-account-eu",
        "config": "workers/account/wrangler.edge-eu.toml",
        "version_before": ACCOUNT_OLD,
    }
    assert rec["d1"] == {"database": "edge-account-db-eu", "bookmark": BOOKMARK}
    assert rec["rollback"] == {
        "3_account": "cd workers/account && npx --no-install wrangler rollback %s --config wrangler.edge-eu.toml"
        % ACCOUNT_OLD,
        "4_d1": "cd workers/account && npx --no-install wrangler d1 time-travel restore edge-account-db-eu --bookmark=%s --config wrangler.edge-eu.toml"
        % BOOKMARK,
    }
    assert "proxy" not in rec
    assert "executor_manifest" not in rec
    seen = calls(world.log)
    assert not [c for c in seen if c["argv"][0] == "aws"], "R2 is not read"
    assert not [c for c in seen if c["cwd"] == "proxy"], "the proxy Worker is not looked up"
    out = capsys.readouterr().out
    assert (
        "restore D1: cd workers/account && npx --no-install wrangler d1 time-travel restore edge-account-db-eu"
        in out
    )


def test_account_only_before_still_refuses_a_missing_bookmark(world):
    world.set(account=ACCOUNT_OLD, proxy=None, time_travel={"rc": 1, "err": "rate limited"})
    assert run_account_before(world) == 1
    assert not world.before().exists()


def test_before_without_account_only_still_needs_a_version(world):
    rc = dr.main(["before", "--target", "edge", "--region", "eu", "--out", str(world.before())])
    assert rc == 1
    assert not world.before().exists()


def test_an_account_only_record_rolls_back_by_printing_and_refuses_bootstrap_and_after(
    world, capsys
):
    assert run_account_before(world) == 0
    capsys.readouterr()
    before_calls = len(calls(world.log))
    assert dr.main(["rollback", "--before", str(world.before())]) == 0
    out = capsys.readouterr().out
    assert "npx --no-install wrangler rollback %s" % ACCOUNT_OLD in out
    assert "--bookmark=%s" % BOOKMARK in out
    assert len(calls(world.log)) == before_calls, "an account-only rollback runs nothing"
    assert (
        dr.main(
            [
                "bootstrap",
                "--before",
                str(world.before()),
                "--record",
                str(world.dir / "proxy-bootstrap.json"),
            ]
        )
        == 1
    )
    assert (
        dr.main(
            [
                "after",
                "--before",
                str(world.before()),
                "--proxy-record",
                str(world.dir / "proxy.json"),
                "--manifest",
                str(world.dir / "manifest.json"),
                "--out",
                str(world.dir / "record.json"),
            ]
        )
        == 1
    )
    assert not (world.dir / "record.json").exists()


# ---- bootstrap --------------------------------------------------------------


def bootstrap(world: World) -> int:
    return dr.main(
        [
            "bootstrap",
            "--before",
            str(world.before()),
            "--record",
            str(world.dir / "proxy-bootstrap.json"),
        ]
    )


def test_bootstrap_runs_deploy_proxy_with_the_target_and_version(world):
    world.set(account=ACCOUNT_OLD, proxy=None)
    assert run_before(world) == 0
    assert bootstrap(world) == 0
    proxy_calls = [c["argv"] for c in calls(world.log) if c["argv"][0] == "deploy_proxy"]
    assert proxy_calls == [
        [
            "deploy_proxy",
            "--target",
            "edge",
            "--region",
            "eu",
            "--version",
            VERSION,
            "--record",
            str(world.dir / "proxy-bootstrap.json"),
        ]
    ]


def test_bootstrap_accepts_a_failed_smoke_only_when_a_version_landed(world, monkeypatch):
    world.set(account=ACCOUNT_OLD, proxy=None)
    assert run_before(world) == 0
    monkeypatch.setenv("FAKE_PROXY_RC", "1")
    monkeypatch.setenv("FAKE_PROXY_VERSION", PROXY_NEW)
    assert bootstrap(world) == 0
    monkeypatch.delenv("FAKE_PROXY_VERSION")
    assert bootstrap(world) == 1


def test_bootstrap_refuses_when_the_proxy_already_existed(world):
    assert run_before(world) == 0
    assert bootstrap(world) == 1
    assert not [c for c in calls(world.log) if c["argv"][0] == "deploy_proxy"]


# ---- rollback ---------------------------------------------------------------


def rollback(world: World) -> int:
    return dr.main(["rollback", "--before", str(world.before())])


def actions(world: World) -> list[str]:
    """The state-changing calls in order: secret deletes and deploy_proxy runs."""
    out = []
    for c in calls(world.log):
        if c["argv"][0] == "deploy_proxy":
            out.append("deploy_proxy " + " ".join(c["argv"][1:]))
        elif c["argv"][2:4] == ["secret", "delete"]:
            out.append("secret delete " + c["argv"][4])
    return out


def test_rollback_closes_the_executor_first_then_redeploys_the_previous_release(
    world, tmp_path, capsys
):
    world.pointer(PREV_RELEASE)
    assert run_before(world) == 0
    (tmp_path / "store.json").write_text(json.dumps(["EXECUTOR_MODE"]))
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert rollback(world) == 0
    assert actions(world) == [
        "secret delete EXECUTOR_MODE",
        "deploy_proxy --target edge --region eu --version %s" % PREV_RELEASE,
    ]
    out = capsys.readouterr().out
    account_at, d1_at = (
        out.index(
            "account Worker: cd workers/account && npx --no-install wrangler rollback %s"
            % ACCOUNT_OLD
        ),
        out.index("D1 restore:"),
    )
    assert account_at < d1_at
    assert BOOKMARK in out[d1_at:]


def test_rollback_with_an_unchanged_proxy_redeploys_nothing(world):
    world.pointer(PREV_RELEASE)
    assert run_before(world) == 0
    assert rollback(world) == 0
    assert actions(world) == ["secret delete EXECUTOR_MODE"]


def test_rollback_of_a_first_deploy_has_no_proxy_to_return_to(world):
    world.set(account=ACCOUNT_OLD, proxy=None)
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert rollback(world) == 0
    assert actions(world) == ["secret delete EXECUTOR_MODE"]


def test_rollback_without_a_release_on_record_prints_the_worker_rollback_and_runs_none(
    world, capsys
):
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert rollback(world) == 0
    assert actions(world) == ["secret delete EXECUTOR_MODE"]
    assert "npx --no-install wrangler rollback %s" % PROXY_OLD in capsys.readouterr().err


def test_rollback_reports_a_failed_redeploy_and_an_unconfirmed_close(world, monkeypatch):
    world.pointer(PREV_RELEASE)
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    monkeypatch.setenv("FAKE_PROXY_RC", "1")
    monkeypatch.setenv("FAKE_LIST_RC", "1")
    assert rollback(world) == 1


# ---- after ------------------------------------------------------------------


def after(
    world: World,
    *,
    smoke: int | None = 0,
    enable: str = "success",
    rollback_outcome: str = "skipped",
    fetched: dict | None = None,
) -> int:
    proxy_record = world.dir / "proxy.json"
    if smoke is not None:
        proxy_record.write_text(
            json.dumps(
                {
                    "version_id": PROXY_NEW,
                    "previous_version_id": PROXY_OLD,
                    "smoke_rc": smoke,
                    "rollback": "npx wrangler rollback x",
                }
            )
        )
    manifest = world.tmp / "stage-manifest.json"
    files = fetched if fetched is not None else SHA
    manifest.write_text(
        json.dumps({"version": VERSION, "files": {k: {"sha256": v} for k, v in files.items()}})
    )
    return dr.main(
        [
            "after",
            "--before",
            str(world.before()),
            "--proxy-record",
            str(proxy_record),
            "--manifest",
            str(manifest),
            "--enable-outcome",
            enable,
            "--rollback-outcome",
            rollback_outcome,
            "--out",
            str(world.dir / "deploy-record-edge-eu.json"),
        ]
    )


def pointer(world: World) -> dict | None:
    path = world.bucket / dr.pointer_key("edge", "eu")
    return json.loads(path.read_text()) if path.is_file() else None


def test_after_writes_the_full_record_the_summary_and_the_pointer(world):
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert after(world) == 0
    rec = json.loads((world.dir / "deploy-record-edge-eu.json").read_text())
    assert rec["good"] is True
    assert rec["account"]["version_before"] == ACCOUNT_OLD
    assert rec["account"]["version_after"] == ACCOUNT_NEW
    assert rec["proxy"]["version_after"] == PROXY_NEW
    assert rec["smoke_rc"] == 0
    assert rec["executor_manifest"]["fetched_sha256"] == SHA
    summary = (world.tmp / "summary.md").read_text()
    assert "Deploy record: edge eu (v%s)" % VERSION in summary
    assert BOOKMARK in summary
    assert "NOT GOOD" not in summary
    assert pointer(world) == {
        "release_version": VERSION,
        "version_id": PROXY_NEW,
        "worker": "edge-rediacc-proxy-eu",
        "recorded_at": rec["recorded_at"],
    }
    cache = (world.bucket / (dr.pointer_key("edge", "eu") + ".cache-control")).read_text()
    assert cache == "no-store"


@pytest.mark.parametrize(
    ("smoke", "enable", "rollback_outcome"),
    [
        (1, "skipped", "success"),
        (None, "skipped", "success"),
        (0, "skipped", "skipped"),
        (0, "success", "success"),
    ],
)
def test_after_of_a_deploy_that_is_not_good_records_it_and_writes_no_pointer(
    world, smoke, enable, rollback_outcome
):
    world.pointer(PREV_RELEASE)
    assert run_before(world) == 0
    assert after(world, smoke=smoke, enable=enable, rollback_outcome=rollback_outcome) == 0
    rec = json.loads((world.dir / "deploy-record-edge-eu.json").read_text())
    assert rec["good"] is False
    assert "NOT GOOD" in (world.tmp / "summary.md").read_text()
    kept = pointer(world)
    assert kept is not None
    assert kept["release_version"] == PREV_RELEASE


def test_after_refuses_a_fetched_manifest_that_differs_from_the_staged_one(world):
    assert run_before(world) == 0
    assert after(world, fetched={**SHA, "renet-linux-amd64": "0" * 64}) == 1
    assert pointer(world) is None


def test_after_with_an_unknown_account_version_fails_but_still_writes_the_record(world):
    assert run_before(world) == 0
    data = json.loads(world.scenario.read_text())
    data["deployments"]["account"] = {"rc": 1, "err": "X [ERROR] rate limited [code: 971]"}
    world.scenario.write_text(json.dumps(data))
    assert after(world) == 1
    rec = json.loads((world.dir / "deploy-record-edge-eu.json").read_text())
    assert rec["account"]["version_after"] == "UNKNOWN"
    assert pointer(world) is None


def test_no_secret_value_reaches_any_child_argv(world, tmp_path):
    world.pointer(PREV_RELEASE)
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    (tmp_path / "store.json").write_text(json.dumps(["EXECUTOR_MODE"]))
    assert rollback(world) == 0
    assert after(world) == 0
    for c in calls(world.log):
        assert os.environ["CLOUDFLARE_API_TOKEN"] not in " ".join(c["argv"])


def test_a_worker_with_an_empty_deployments_list_did_not_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(dr, "_capture", lambda *_a, **_k: (0, "[]", ""))
    assert dr.worker_version(tmp_path, "wrangler.toml", "w") == (False, None)


# ---- the durable sink and the www record (plan local-release W2-D) ---------------


def record_keys(world: World) -> list[str]:
    return sorted(
        str(p.relative_to(world.bucket)) for p in (world.bucket / "release-records").rglob("*.json")
    )


def sink_after(world: World) -> int:
    return dr.main(
        [
            "after",
            "--before",
            str(world.before()),
            "--proxy-record",
            str(world.dir / "proxy.json"),
            "--manifest",
            str(world.tmp / "stage-manifest.json"),
            "--enable-outcome",
            "success",
            "--rollback-outcome",
            "skipped",
            "--account-smoke-rc",
            "0",
            "--sink",
            "r2",
            "--channel",
            "edge",
            "--out",
            str(world.dir / "deploy-record-edge-eu.json"),
        ]
    )


def test_after_sink_r2_writes_the_record_once_at_the_documented_key(world, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY")
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert after(world) == 0  # writes proxy.json and stage-manifest.json
    assert sink_after(world) == 0
    key = "release-records/v%s/edge/deploy-record-edge-eu.json" % VERSION
    assert record_keys(world) == [key]
    stored = json.loads((world.bucket / key).read_text())
    assert stored["account"]["smoke_rc"] == 0
    assert stored["smoke_rc"] == 0
    assert (world.bucket / (key + ".cache-control")).read_text().endswith("immutable")
    puts = [c["argv"] for c in calls(world.log) if c["argv"][:2] == ["aws", "s3api"]]
    assert any("put-object" in a and key in a for a in puts)


def test_after_sink_r2_refuses_to_overwrite_an_existing_record(world, capsys):
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert after(world) == 0
    assert sink_after(world) == 0
    key = world.bucket / ("release-records/v%s/edge/deploy-record-edge-eu.json" % VERSION)
    first = key.read_bytes()
    assert sink_after(world) == 1
    assert key.read_bytes() == first
    assert "written once" in capsys.readouterr().err


def test_after_sink_r2_needs_a_channel(world):
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert after(world) == 0
    args = [
        "after", "--before", str(world.before()),
        "--proxy-record", str(world.dir / "proxy.json"),
        "--manifest", str(world.tmp / "stage-manifest.json"),
        "--sink", "r2", "--out", str(world.dir / "x.json"),
    ]  # fmt: skip
    assert dr.main(args) == 1
    assert record_keys(world) == []


def test_a_record_carrying_a_secret_value_is_refused(world, monkeypatch):
    monkeypatch.setenv("SOME_API_TOKEN", "CANARY-secret-value-123")
    record = {"version": VERSION, "note": "oops CANARY-secret-value-123"}
    with pytest.raises(dr.RecordError, match="SOME_API_TOKEN"):
        dr.write_record_once(record, "release-records/v1.0.0/edge/x.json")
    assert not (world.bucket / "release-records").exists()


def test_the_account_record_carries_the_account_smoke_rc_and_no_secret(world, monkeypatch):
    monkeypatch.setenv("SOME_API_TOKEN", "CANARY-secret-value-123")
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert after(world) == 0
    rec = json.loads((world.dir / "deploy-record-edge-eu.json").read_text())
    assert "smoke_rc" in rec["account"]
    assert "CANARY-secret-value-123" not in json.dumps(rec)
    assert "account smoke rc" in (world.tmp / "summary.md").read_text()


def www_after(record) -> int:
    return dr.main(
        [
            "www-after",
            "--record",
            str(record),
            "--smoke-rc",
            "0",
            "--sink",
            "r2",
            "--channel",
            "edge",
        ]
    )


def test_the_www_record_carries_the_version_ids_the_rollback_command_and_the_smoke_rc(
    world, monkeypatch, tmp_path
):
    cwd = tmp_path / "www"
    cwd.mkdir()
    (cwd / "wrangler.edge.toml").write_text('name = "edge-rediacc-www"\n')
    ids = iter([(True, "wv-1"), (True, "wv-2")])
    monkeypatch.setattr(dr, "worker_version", lambda *_a: next(ids))
    out = tmp_path / "www-record.json"
    monkeypatch.setenv("DEPLOY_RECORD_OUT", str(out))
    monkeypatch.setenv("DEPLOY_RECORD_VERSION", VERSION)
    assert dr.record_www_deploy(cwd, "wrangler.edge.toml", "www-edge", lambda: 0) == 0
    rec = json.loads(out.read_text())
    assert rec["version_before"] == "wv-1"
    assert rec["version_after"] == "wv-2"
    assert rec["worker"] == "edge-rediacc-www"
    assert rec["rollback_command"] == (
        "cd workers/www && npx --no-install wrangler rollback wv-1 --config wrangler.edge.toml"
    )
    assert rec["smoke_rc"] is None
    assert www_after(out) == 0
    key = "release-records/v%s/edge/deploy-record-www-edge-global.json" % VERSION
    assert record_keys(world) == [key]
    stored = json.loads((world.bucket / key).read_text())
    assert stored["smoke_rc"] == 0
    assert stored["version_before"] == "wv-1"
    assert www_after(out) == 1


def test_the_www_record_is_inactive_without_the_env_and_refuses_before_a_deploy(
    monkeypatch, tmp_path
):
    ran = []
    monkeypatch.delenv("DEPLOY_RECORD_OUT", raising=False)
    assert dr.record_www_deploy(tmp_path, "c.toml", "www-edge", lambda: ran.append(1) or 7) == 7
    monkeypatch.setenv("DEPLOY_RECORD_OUT", str(tmp_path / "r.json"))
    monkeypatch.setenv("DEPLOY_RECORD_VERSION", "not-a-version")
    ran.clear()
    assert dr.record_www_deploy(tmp_path, "c.toml", "www-edge", lambda: ran.append(1) or 0) == 1
    assert ran == []


def test_the_conditional_put_carries_if_none_match(world, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY")
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    assert after(world) == 0
    assert sink_after(world) == 0
    put = next(
        c["argv"]
        for c in calls(world.log)
        if "put-object" in c["argv"] and "release-records" in " ".join(c["argv"])
    )
    assert put[put.index("--if-none-match") + 1] == "*"


@pytest.mark.parametrize(
    "secret", ['has"quote-12345', "back\\slash-12345", "ctl\nline-12345", "caf\u00e9-secret-12345"]
)
def test_an_escaped_secret_value_is_still_found(monkeypatch, secret):
    monkeypatch.setenv("SOME_API_TOKEN", secret)
    with pytest.raises(dr.RecordError, match="SOME_API_TOKEN"):
        dr.refuse_secret_values({"note": "x " + secret + " y"})
    with pytest.raises(dr.RecordError, match="SOME_API_TOKEN"):
        dr.refuse_secret_values({"nested": [{"k": secret}]})


def test_after_with_a_secret_in_the_record_emits_nothing(world, monkeypatch, capsys):
    assert run_before(world) == 0
    world.set(account=ACCOUNT_NEW, proxy=PROXY_NEW)
    monkeypatch.setenv("SOME_API_TOKEN", ACCOUNT_NEW)
    out = world.dir / "deploy-record-edge-eu.json"
    out.unlink(missing_ok=True)
    (world.tmp / "summary.md").unlink(missing_ok=True)
    capsys.readouterr()
    assert after(world) == 1
    assert not out.exists()
    assert not (world.tmp / "summary.md").exists()
    assert capsys.readouterr().out == ""
    assert record_keys(world) == []


def test_www_after_with_a_secret_emits_nothing(world, monkeypatch, tmp_path, capsys):
    rec = tmp_path / "w.json"
    rec.write_text(
        json.dumps(
            {
                "target": "www-edge",
                "region": "global",
                "version": VERSION,
                "version_after": "v2",
                "note": "CANARY-secret-value-123",
            }
        )
    )
    monkeypatch.setenv("SOME_API_TOKEN", "CANARY-secret-value-123")
    assert www_after(rec) == 1
    assert capsys.readouterr().out == ""
    assert "smoke_rc" not in json.loads(rec.read_text())
    assert record_keys(world) == []


def test_a_failed_after_lookup_is_marked_and_not_sunk_unless_accepted(world, monkeypatch, tmp_path):
    cwd = tmp_path / "www"
    cwd.mkdir()
    (cwd / "wrangler.edge.toml").write_text('name = "edge-rediacc-www"\n')
    seq = [(True, "wv-1"), dr.RecordError("rate limited")]

    def fake(*_a):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(dr, "worker_version", fake)
    out = tmp_path / "r.json"
    monkeypatch.setenv("DEPLOY_RECORD_OUT", str(out))
    monkeypatch.setenv("DEPLOY_RECORD_VERSION", VERSION)
    assert dr.record_www_deploy(cwd, "wrangler.edge.toml", "www-edge", lambda: 0) == 0
    rec = json.loads(out.read_text())
    assert rec["version_after"] is None
    assert "rate limited" in rec["version_after_error"]
    assert www_after(out) == 1
    assert record_keys(world) == []
    args = [
        "www-after",
        "--record",
        str(out),
        "--smoke-rc",
        "0",
        "--sink",
        "r2",
        "--channel",
        "edge",
        "--accept-missing-after",
    ]
    assert dr.main(args) == 0
    assert len(record_keys(world)) == 1


def test_a_secret_of_digits_matching_a_number_field_is_refused(monkeypatch):
    monkeypatch.setenv("SOME_API_TOKEN", "1234567890")
    with pytest.raises(dr.RecordError, match="SOME_API_TOKEN"):
        dr.refuse_secret_values({"deploy_rc": 1234567890})


def test_the_leaf_walk_follows_a_tuple(monkeypatch):
    """A tuple is walked like a list, so its member is compared on its decoded text, not on a repr."""
    secret = 'q"uote\\caf\u00e9-12345'
    monkeypatch.setenv("SOME_API_TOKEN", secret)
    assert secret in list(dr._string_leaves({"t": ("pre", secret)}))
    with pytest.raises(dr.RecordError, match="SOME_API_TOKEN"):
        dr.refuse_secret_values({"t": ("pre", secret)})


def test_a_value_matching_only_the_json_punctuation_is_not_a_leak(monkeypatch):
    """`, "region` occurs in the serialized body only across a separator and a key, inside no key or leaf, so the record is emitted."""
    monkeypatch.setenv("SOME_API_TOKEN", ', "region')
    dr.refuse_secret_values({"a": "x", "region": "eu"})


def test_an_awscli_that_cannot_run_is_a_record_error(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_R2_ENDPOINT", "https://r2.example.invalid")

    def boom(*_a, **_k):
        raise FileNotFoundError("aws")

    monkeypatch.setattr(dr.awscli, "run", boom)
    with pytest.raises(dr.RecordError, match="could not run"):
        dr.write_record_once({"version": VERSION}, "release-records/v1.0.0/edge/x.json")


def test_digits_412_in_stderr_are_not_an_existing_record(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_R2_ENDPOINT", "https://r2.example.invalid")

    class Proc:
        returncode = 254
        stderr = b"An error occurred (InternalError): request id 4120 failed"

    monkeypatch.setattr(dr.awscli, "run", lambda *_a, **_k: Proc())
    with pytest.raises(dr.RecordError) as exc:
        dr.write_record_once({"version": VERSION}, "release-records/v1.0.0/edge/x.json")
    assert "already exists" not in str(exc.value)


# ---- bws profile re-exec ----------------------------------------------------


def _recording_run(monkeypatch, rc: int) -> list[list[str]]:
    seen: list[list[str]] = []

    def fake_run(argv, **_kw):
        seen.append(argv)
        return type("P", (), {"returncode": rc})()

    monkeypatch.setattr(dr.subprocess, "run", fake_run)
    return seen


def test_missing_credentials_reexec_under_the_deploy_proxy_profile_when_unbound(world, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    seen = _recording_run(monkeypatch, 7)
    args = ["before", "--target", "edge", "--region", "eu", "--account-only", "--out", "x.json"]
    assert dr.main(args) == 7
    assert seen[0][1:7] == [
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        "deploy-proxy",
        "--",
    ]
    assert seen[0][-(len(args) + 2) :] == ["-m", dr.SELF, *args]
    assert calls(world.log) == []


def test_reexec_reads_the_target_from_the_before_record(world, monkeypatch, tmp_path):
    before = tmp_path / "bench-before.json"
    before.write_text(json.dumps({"target": "bench", "region": "eu"}))
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID")
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    seen = _recording_run(monkeypatch, 0)
    assert dr.main(["rollback", "--before", str(before)]) == 0
    assert seen[0][5] == "deploy-proxy-bench"
    assert calls(world.log) == []


@pytest.mark.usefixtures("world")
def test_a_bound_profile_with_missing_credentials_does_not_reexec_again(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "deploy-proxy")
    monkeypatch.setattr(dr.subprocess, "run", lambda *_a, **_k: pytest.fail("re-exec"))
    monkeypatch.setitem(dr.VERBS, "before", lambda _args, _root: 3)
    assert (
        dr.main(["before", "--target", "edge", "--region", "eu", "--account-only", "--out", "x"])
        == 3
    )


@pytest.mark.usefixtures("world")
def test_credentials_present_run_in_process_with_no_reexec(monkeypatch):
    monkeypatch.setattr(dr.subprocess, "run", lambda *_a, **_k: pytest.fail("re-exec"))
    monkeypatch.setitem(dr.VERBS, "before", lambda _args, _root: 0)
    assert (
        dr.main(["before", "--target", "edge", "--region", "eu", "--account-only", "--out", "x"])
        == 0
    )
