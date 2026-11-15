"""deploy_bench `--region` (agent/plans/PLAN-multi-region-bench.md W3): each regional bench has its own host, Worker, config, signer, control database and deploy record, the default region is the module's own constants, and a region not marked deployable is refused before any remote write."""

from __future__ import annotations

import json

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import bench_preflight, deploy_bench

VID = "0b1f2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
US_TOML = (
    '[assets]\ndirectory = "./bench/dist"\n'
    '\n[[d1_databases]]\nbinding = "DB"\ndatabase_name = "account-bench-us"\n'
    'database_id = "22222222-2222-4222-8222-222222222222"\n'
)


def _regions_root(tmp_path, us_deployable: bool):
    """A tmp repo root whose regions.json is the real one with the us bench's `deployable` set, and a us bench config."""
    data = json.loads((paths.repo_root() / "regions.json").read_text(encoding="utf-8"))
    for row in data["regions"]:
        if row["id"] == "us":
            row["bench"]["deployable"] = us_deployable
    (tmp_path / "regions.json").write_text(json.dumps(data), encoding="utf-8")
    worker = tmp_path / "workers" / "account"
    worker.mkdir(parents=True)
    (worker / "wrangler.bench-us.toml").write_text(US_TOML)
    (worker / "node_modules").mkdir()
    (tmp_path / "private/account/web/node_modules").mkdir(parents=True)
    return worker


def _world(monkeypatch, events):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "x")
    monkeypatch.setattr(deploy_bench, "secrets_payload", lambda *_a, **_k: {"K": "v"})
    monkeypatch.setattr(deploy_bench, "root_password", lambda: "p")
    monkeypatch.setattr(deploy_bench.cf_auth, "await_propagation", lambda _a: None)
    monkeypatch.setattr(deploy_bench.bench_preflight, "lockfile", lambda _p: 0)
    monkeypatch.setattr(
        deploy_bench.bench_preflight, "buckets", lambda c: events.append(["buckets", c]) or 0
    )
    monkeypatch.setattr(deploy_bench.deploy_account, "check_queues", lambda *_a: [])
    monkeypatch.setattr(deploy_bench, "capture_bookmark", lambda *_a, **_k: None)
    monkeypatch.setattr(deploy_bench, "_rotation_check", lambda _r: None)
    monkeypatch.setattr(
        deploy_bench, "_seed_and_report", lambda region="eu": events.append(["seed", region])
    )
    monkeypatch.setattr(
        deploy_bench.deploy_record,
        "worker_version",
        lambda _d, config, worker: events.append(["version", config, worker]) or (True, "live"),
    )
    monkeypatch.setattr(
        deploy_bench, "smoke", lambda region="eu", **_k: events.append(["smoke", region])
    )
    monkeypatch.setattr(
        deploy_bench,
        "record_version",
        lambda _r, _o, _v, region="eu": events.append(["record", region]),
    )
    monkeypatch.setattr(
        deploy_bench,
        "_remove_retired_secrets",
        lambda _d, _run=None, region="eu": events.append(["retired", region]) or [],
    )
    monkeypatch.setattr(
        deploy_bench,
        "_run",
        lambda argv, *_a, **_k: events.append(list(argv)) or "Current Version ID: " + VID,
    )


def test_the_default_region_target_is_the_module_constants_and_regions_json():
    eu = deploy_bench.target()
    assert (eu.config, eu.worker_name, eu.domain) == (
        deploy_bench.CONFIG,
        deploy_bench.WORKER_NAME,
        deploy_bench.DOMAIN,
    )
    bench = bench_preflight.bench_object("eu")
    assert (eu.worker_name, eu.domain) == (bench["workerName"], bench["host"])
    assert eu.record_rel == deploy_bench.VERSION_RECORD
    assert eu.signer_target == "bench-eu"


def test_a_regional_target_reads_its_regions_json_bench_object():
    us = deploy_bench.target("us")
    bench = bench_preflight.bench_object("us")
    assert us.config == "wrangler.bench-us.toml"
    assert (us.worker_name, us.domain) == (bench["workerName"], bench["host"])
    assert us.domain != deploy_bench.DOMAIN
    assert us.record_rel[-1] == "bench-us.json"
    assert us.signer_target == "bench-us"


def test_an_unknown_region_is_a_named_error():
    with pytest.raises(deploy_bench.DeployError, match="no region 'mars'"):
        deploy_bench.target("mars")


def test_a_region_not_marked_deployable_is_refused_before_any_remote_write(monkeypatch, tmp_path):
    events: list[list[str]] = []
    _regions_root(tmp_path, us_deployable=False)
    _world(monkeypatch, events)
    with pytest.raises(deploy_bench.DeployError, match="not deployable"):
        deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path, "us")
    assert events == []


def test_a_deployable_region_deploys_its_own_config_worker_signer_and_record(monkeypatch, tmp_path):
    events: list[list[str]] = []
    _regions_root(tmp_path, us_deployable=True)
    _world(monkeypatch, events)
    deploy_bench._deploy(deploy_bench.cf_auth.Auth(token="t"), tmp_path, "us")
    joined = [" ".join(map(str, e)) for e in events]
    assert any(e.endswith("control_db ensure --bench --region us") for e in joined), joined
    assert [e.rsplit(" ", 1)[1] for e in joined if "deploy_signer --target" in e] == ["bench-us"]
    assert any(e.endswith("deploy --config wrangler.bench-us.toml") for e in joined)
    assert any("migrations apply account-bench-us" in e for e in joined)
    assert any(e.endswith("secret bulk --name account-bench-us") for e in joined)
    for step in (["record", "us"], ["smoke", "us"], ["seed", "us"]):
        assert step in events
    assert ["version", "wrangler.bench-us.toml", "account-bench-us"] in events
    # control: nothing of the eu bench was touched
    assert not any("wrangler.bench.toml" in e or "bench-eu" in e for e in joined)


def test_the_deploy_record_path_follows_the_region(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(deploy_bench.receipt, "identity", lambda _r, _s: {"sha": "s"})
    monkeypatch.setattr(deploy_bench.receipt, "write_atomic", lambda path, _t: seen.append(path))
    out = "Current Version ID: " + VID
    deploy_bench.record_version(tmp_path, out, "live")
    deploy_bench.record_version(tmp_path, out, "live", "us")
    assert [p.name for p in seen] == ["bench.json", "bench-us.json"]


def test_seeding_a_region_posts_to_that_regions_host(monkeypatch):
    posted = []
    monkeypatch.setattr(deploy_bench, "root_password", lambda: "password-1")

    def post(url, _body):
        posted.append(url)
        return 201, {}

    monkeypatch.setattr(deploy_bench, "_post_json", post)
    deploy_bench.seed_root(email="a@b.c")
    deploy_bench.seed_root(email="a@b.c", region="us")
    assert posted == [
        "https://%s/account/api/v1/auth/register" % deploy_bench.DOMAIN,
        "https://%s/account/api/v1/auth/register" % deploy_bench.target("us").domain,
    ]


def _main_world(monkeypatch, root, children=None):
    """`children` collects the region of each re-exec; the stub returns None (profile bound) so a single-region run proceeds in process."""
    monkeypatch.setattr(deploy_bench.shutil, "which", lambda _c: "/usr/bin/true")

    def reexec(_argv, region="eu"):
        if children is not None:
            children.append(region)

    monkeypatch.setattr(deploy_bench, "_reexec_under_profile", reexec)
    monkeypatch.setattr(deploy_bench.paths, "repo_root", lambda: root)
    monkeypatch.setattr(deploy_bench.cf_auth, "resolve", lambda _a: deploy_bench.cf_auth.Auth("t"))
    monkeypatch.setattr(deploy_bench.cf_auth, "self_destruct", lambda _a: None)
    ran: list[str] = []
    monkeypatch.setattr(deploy_bench, "_deploy", lambda _a, _r, region="eu": ran.append(region))
    return ran


def test_region_all_runs_one_child_per_deployable_region(monkeypatch, tmp_path):
    """Each region deploys in its own child under its own profile; the parent deploys nothing itself."""
    _regions_root(tmp_path, us_deployable=True)
    children: list[str] = []
    ran = _main_world(monkeypatch, tmp_path, children)
    assert deploy_bench.main(["--region", "all"]) == 0
    assert children == ["eu", "us"]
    assert ran == []


def test_region_all_skips_a_not_deployable_region_by_name(monkeypatch, tmp_path, capsys):
    _regions_root(tmp_path, us_deployable=False)
    children: list[str] = []
    _main_world(monkeypatch, tmp_path, children)
    assert deploy_bench.main(["--region", "all"]) == 0
    assert children == ["eu"]
    assert "skipping bench us" in capsys.readouterr().err


def test_region_all_returns_the_first_failing_childs_status(monkeypatch, tmp_path):
    _regions_root(tmp_path, us_deployable=True)
    _main_world(monkeypatch, tmp_path)
    monkeypatch.setattr(
        deploy_bench, "_reexec_under_profile", lambda _a, r="eu": 0 if r == "eu" else 3
    )
    assert deploy_bench.main(["--region", "all"]) == 3


def test_region_all_under_a_bound_bench_profile_is_refused(monkeypatch, tmp_path):
    _regions_root(tmp_path, us_deployable=True)
    children: list[str] = []
    _main_world(monkeypatch, tmp_path, children)
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "deploy-bench")
    assert deploy_bench.main(["--region", "all"]) == 2
    assert children == []


def _reexec_argv(monkeypatch, region, bound=""):
    seen: list[list[str]] = []

    class Done:
        returncode = 0

    monkeypatch.setenv("REDIACC_BWS_PROFILES", bound)

    def run(argv, **_k):
        seen.append(argv)
        return Done()

    monkeypatch.setattr(deploy_bench.subprocess, "run", run)
    rc = deploy_bench._reexec_under_profile(["--region", region], region)
    return rc, seen


def test_a_us_deploy_reexecutes_under_the_us_profile(monkeypatch):
    """deploy-bench binds the eu bench's server key, KEK, S3 pair and root password; a us deploy under it pushed those to account-bench-us."""
    rc, seen = _reexec_argv(monkeypatch, "us")
    assert rc == 0
    assert seen[0][seen[0].index("--profile") + 1] == "deploy-bench-us"


def test_an_eu_deploy_keeps_the_unsuffixed_profile(monkeypatch):
    _rc, seen = _reexec_argv(monkeypatch, "eu")
    assert seen[0][seen[0].index("--profile") + 1] == "deploy-bench"


def test_a_us_deploy_under_the_eu_profile_is_refused(monkeypatch):
    """`bws_env exec` keeps a name already set, so nesting deploy-bench-us under deploy-bench would keep the eu keys."""
    with pytest.raises(deploy_bench.ForeignProfileError, match="deploy-bench"):
        _reexec_argv(monkeypatch, "us", bound="deploy-bench")


def test_the_own_profile_bound_runs_in_place(monkeypatch):
    rc, seen = _reexec_argv(monkeypatch, "us", bound="deploy-bench-us,bench-access")
    assert rc is None
    assert seen == []


def test_the_default_run_deploys_eu_only(monkeypatch, tmp_path):
    _regions_root(tmp_path, us_deployable=True)
    ran = _main_world(monkeypatch, tmp_path)
    assert deploy_bench.main([]) == 0
    assert ran == ["eu"]


@pytest.mark.parametrize(
    "argv", [["--region", "mars"], ["--region"], ["--region", "eu", "--region", "us"]]
)
def test_a_bad_region_argument_exits_2_before_any_deploy(monkeypatch, tmp_path, argv):
    _regions_root(tmp_path, us_deployable=True)
    ran = _main_world(monkeypatch, tmp_path)
    assert deploy_bench.main(argv) == 2
    assert ran == []


def test_region_all_with_seed_root_is_refused(monkeypatch, tmp_path):
    _regions_root(tmp_path, us_deployable=True)
    ran = _main_world(monkeypatch, tmp_path)
    assert deploy_bench.main(["--region", "all", "--seed-root"]) == 2
    assert ran == []


def test_the_help_names_the_region_flag():
    assert "--region" in deploy_bench.HELP


def test_the_module_docstring_names_no_retired_database():
    assert "account-db-bench" not in (deploy_bench.__doc__ or "")


@pytest.mark.parametrize("extra", [[], ["--seed-root"], ["--set-root-password"]])
def test_a_not_deployable_region_is_refused_before_any_credential_or_post(
    monkeypatch, tmp_path, extra
):
    _regions_root(tmp_path, us_deployable=False)
    ran = _main_world(monkeypatch, tmp_path)
    calls: list[str] = []

    def minted(_a):
        calls.append("resolve")
        pytest.fail("minted")

    def posted(*_a):
        calls.append("post")
        return 201, {}

    monkeypatch.setattr(deploy_bench.cf_auth, "resolve", minted)
    monkeypatch.setattr(deploy_bench, "_post_json", posted)
    monkeypatch.setattr(deploy_bench, "root_password", lambda: "p")
    assert deploy_bench.main(["--region", "us", *extra]) == 2
    assert calls == []
    assert ran == []


@pytest.mark.parametrize("extra", [[], ["--seed-root"], ["--set-root-password"]])
def test_a_deployable_region_still_proceeds_past_the_refusal(monkeypatch, tmp_path, extra):
    _regions_root(tmp_path, us_deployable=True)
    ran = _main_world(monkeypatch, tmp_path)
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(deploy_bench, "_seed_and_report", lambda r="eu": seen.append(("seed", r)))
    monkeypatch.setattr(
        deploy_bench, "_set_password_and_report", lambda r="eu": seen.append(("pw", r))
    )
    assert deploy_bench.main(["--region", "us", *extra]) == 0
    expected = {
        (): [],
        ("--seed-root",): [("seed", "us")],
        ("--set-root-password",): [("pw", "us")],
    }
    assert seen == expected[tuple(extra)]
    assert ran == ([] if extra else ["us"])
