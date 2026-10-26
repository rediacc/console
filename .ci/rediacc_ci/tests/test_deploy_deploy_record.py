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
        == "npx wrangler rollback %s --config workers/account/wrangler.edge-eu.toml" % ACCOUNT_OLD
    )
    assert rb["4_d1"] == (
        "npx wrangler d1 time-travel restore edge-account-db-eu --bookmark=%s --config workers/account/wrangler.edge-eu.toml"
        % BOOKMARK
    )
    assert (world.tmp / "github_output").read_text() == "proxy_exists=true\n"
    tt = [c for c in calls(world.log) if c["argv"][1:4] == ["d1", "time-travel", "info"]]
    assert tt[0]["argv"][4:] == [
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
    assert rb.startswith("npx wrangler rollback %s" % PROXY_OLD)
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
        elif c["argv"][1:3] == ["secret", "delete"]:
            out.append("secret delete " + c["argv"][3])
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
        out.index("account Worker: npx wrangler rollback %s" % ACCOUNT_OLD),
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
    assert "npx wrangler rollback %s" % PROXY_OLD in capsys.readouterr().err


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
