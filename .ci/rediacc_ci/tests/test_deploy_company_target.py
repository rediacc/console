"""`--company` on the deploy modules (agent/plans/PLAN-enterprise-isolation.md, box D1).

One Enterprise company is a deploy target whose identity and config paths are PARAMETERS: the company config generator (box N4) is not imported, so these tests write the two configs a company deploy would be handed into a scratch tree. Nothing reaches Cloudflare, R2 or bws: wrangler, the aws CLI and the control-database transport are swapped for recording fakes, and a test fails the moment a company record reaches for the releases bucket.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.core import awscli, common
from rediacc_ci.deploy import console_executor as ce
from rediacc_ci.deploy import deploy_account as da
from rediacc_ci.deploy import deploy_proxy as dp
from rediacc_ci.deploy import deploy_record as dr
from rediacc_ci.deploy import executor_artifacts

if TYPE_CHECKING:
    import pathlib

NAME = "acmecorp"
COMPANY_ID = "c0a1b2c3d4e5f607"
DOMAIN = "example.cloud"
VERSION = "1.4.2"
BOOKMARK = "00000085-0000024c-00004c6d-8e61117bf38d7adb71b934ebbf891683"
ACCOUNT_LIVE = "aaaaaaaa-0000-4000-8000-000000000001"
PROXY_LIVE = "bbbbbbbb-0000-4000-8000-000000000001"

ACCOUNT_TOML = """name = "account-%s"
main = "src/index.ts"

[[d1_databases]]
binding = "DB"
database_name = "account-%s"
database_id = "00000000-0000-0000-0000-000000000000"
"""
PROXY_TOML = """name = "proxy-%s"
main = "src/index.ts"
routes = [{ pattern = "%s-proxy.%s", zone_name = "%s" }]
"""


@pytest.fixture
def root(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch repo root: `regions.json` and a company's two configs."""
    shutil.copy(paths.repo_root() / "regions.json", tmp_path / "regions.json")
    (tmp_path / "workers" / "account").mkdir(parents=True)
    (tmp_path / "workers" / "proxy").mkdir(parents=True)
    (tmp_path / "workers" / "account" / ("enterprise.%s.toml" % NAME)).write_text(
        ACCOUNT_TOML % (NAME, NAME)
    )
    (tmp_path / "workers" / "proxy" / ("enterprise.%s.toml" % NAME)).write_text(
        PROXY_TOML % (NAME, NAME, DOMAIN, DOMAIN)
    )
    return tmp_path


def account_cfg(root: pathlib.Path) -> pathlib.Path:
    return root / "workers" / "account" / ("enterprise.%s.toml" % NAME)


def proxy_cfg(root: pathlib.Path) -> pathlib.Path:
    return root / "workers" / "proxy" / ("enterprise.%s.toml" % NAME)


def target(root: pathlib.Path, **over) -> ce.CompanyTarget:
    args = {
        "name": NAME,
        "company_id": COMPANY_ID,
        "region": "eu",
        "domain": DOMAIN,
        "account_config": account_cfg(root),
        "proxy_config": proxy_cfg(root),
    }
    args.update(over)
    return ce.company_target(root, **args)


# ---- the shared seam: console_executor.company_target -----------------------------------


def test_a_valid_company_target_names_its_workers_and_hosts(root):
    company = target(root)
    assert company.account_worker == "account-acmecorp"
    assert company.proxy_worker == "proxy-acmecorp"
    assert company.hosts == ("acmecorp.example.cloud", "acmecorp-proxy.example.cloud")
    assert company.profile_target == "stable"
    assert target(root, bench=True).profile_target == "bench"


@pytest.mark.parametrize(
    ("over", "needle"),
    [
        ({"name": "eu"}, "reserved"),
        ({"name": "acme-proxy"}, "-proxy"),
        ({"name": "Bad Name"}, "DNS label"),
        ({"company_id": "acmecorp"}, "opaque id"),
        ({"company_id": "c12"}, "opaque id"),
        ({"region": "mars"}, "--region mars"),
        ({"domain": "nodot"}, "host domain"),
    ],
)
def test_company_target_refuses_a_bad_identity(root, over, needle):
    with pytest.raises(ce.RefusedError, match=needle):
        target(root, **over)


def test_a_company_target_refuses_a_shared_tier_config(root):
    shared = root / "workers" / "account" / "wrangler.eu.toml"
    shared.write_text(ACCOUNT_TOML % (NAME, NAME))
    with pytest.raises(ce.RefusedError, match="never a shared config"):
        target(root, account_config=shared)


def test_a_company_target_refuses_another_companys_worker_name(root):
    account_cfg(root).write_text(ACCOUNT_TOML % ("othercorp", "othercorp"))
    with pytest.raises(ce.RefusedError, match="account-%s" % COMPANY_ID):
        target(root)


def test_a_company_target_refuses_a_config_outside_its_worker_directory(root, tmp_path):
    stray = tmp_path / "elsewhere"
    stray.mkdir()
    moved = stray / ("enterprise.%s.toml" % NAME)
    moved.write_text(ACCOUNT_TOML % (NAME, NAME))
    with pytest.raises(ce.RefusedError, match="not under workers/account"):
        target(root, account_config=moved)


def test_a_company_flag_without_company_is_refused(root):
    with pytest.raises(ce.RefusedError, match="--company-id needs --company"):
        ce.company_from_values(root, {"company_id": COMPANY_ID}, "eu")
    assert ce.company_from_values(root, {}, "eu") is None


def test_company_needs_its_id_domain_and_region(root):
    with pytest.raises(ce.RefusedError, match="--company-id, --company-domain"):
        ce.company_from_values(root, {"company": NAME}, "eu")
    with pytest.raises(ce.RefusedError, match="--region"):
        ce.company_from_values(
            root, {"company": NAME, "company_id": COMPANY_ID, "company_domain": DOMAIN}, None
        )


def test_company_argv_round_trips_through_company_from_values(root):
    company = target(root)
    parser = argparse.ArgumentParser()
    parser.add_argument("--region")
    ce.add_company_arguments(parser)
    ns = parser.parse_args(ce.company_argv(company))
    assert ce.company_from_values(root, vars(ns), ns.region) == company


# ---- console_executor ---------------------------------------------------------------------


def test_the_executor_switch_runs_in_the_company_directory_on_its_own_worker(
    root, monkeypatch, capsys
):
    seen = []
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")

    def fake_run(argv, cwd, stdin_text):
        seen.append((argv, cwd, stdin_text))
        return 0

    monkeypatch.setattr(ce, "_run", fake_run)
    monkeypatch.setattr(ce, "_list", lambda *_unused: {ce.MODE_KEY})
    assert ce.run("enable", "", None, root, company=target(root)) == 0
    argv, cwd, stdin = seen[0]
    assert argv[-4:] == ["--name", "account-acmecorp", "--config", "enterprise.acmecorp.toml"]
    assert cwd == root / "workers" / "account"
    assert stdin == ce.MODE_VALUE
    out = capsys.readouterr()
    assert NAME not in (out.out + out.err).replace("account-acmecorp", "")


def test_the_executor_switch_refuses_a_company_without_an_account_config(root):
    company = target(root, account_config=None)
    assert ce.run("enable", "", None, root, company=company) == 1


def test_console_executor_main_refuses_company_with_target(capsys):
    rc = ce.main(["--enable", "--target", "stable", "--company", NAME])
    assert rc == 1
    assert "--company also needs" in capsys.readouterr().err


def test_console_executor_main_still_requires_a_target_or_company():
    assert ce.main(["--enable"]) == 2


# ---- deploy_account -----------------------------------------------------------------------


def account_args(root: pathlib.Path, *extra: str) -> list[str]:
    return [
        "--company",
        NAME,
        "--company-id",
        COMPANY_ID,
        "--region",
        "eu",
        "--company-domain",
        DOMAIN,
        "--account-config",
        str(account_cfg(root)),
        *extra,
    ]


def test_account_dry_run_plans_the_companys_own_config(root, monkeypatch, capsys):
    monkeypatch.setattr(common, "repo_root", lambda: root)
    assert da.main(account_args(root, "--dry-run")) == 0
    out = capsys.readouterr()
    # The plan lines name the opaque id too: the label never reaches a console.
    assert "--config enterprise.%s.toml" % COMPANY_ID in out.out
    assert "account-%s" % COMPANY_ID in out.out
    assert NAME not in out.out
    assert "wrangler.eu.toml" not in out.out
    # A log line names the opaque id, never the label.
    assert COMPANY_ID in out.err
    assert NAME not in out.err


def test_account_company_refuses_a_shared_config_path(root, monkeypatch, capsys):
    monkeypatch.setattr(common, "repo_root", lambda: root)
    shared = root / "workers" / "account" / "wrangler.eu.toml"
    shared.write_text(ACCOUNT_TOML % (NAME, NAME))
    args = account_args(root, "--dry-run")
    args[args.index("--account-config") + 1] = str(shared)
    assert da.main(args) == 1
    assert "never a shared config" in capsys.readouterr().err


def test_account_company_flag_without_company_is_refused(root, monkeypatch, capsys):
    monkeypatch.setattr(common, "repo_root", lambda: root)
    assert da.main(["--region", "eu", "--company-id", COMPANY_ID, "--dry-run"]) == 1
    assert "--company-id needs --company" in capsys.readouterr().err


def test_account_company_needs_the_config_path(root, monkeypatch, capsys):
    monkeypatch.setattr(common, "repo_root", lambda: root)
    args = account_args(root, "--dry-run")
    i = args.index("--account-config")
    del args[i : i + 2]
    assert da.main(args) == 1
    assert "--account-config" in capsys.readouterr().err


# ---- deploy_proxy -------------------------------------------------------------------------


def test_select_company_reads_its_own_proxy_config(root):
    spec, text = dp.select_company(root, target(root))
    assert spec.name == "proxy-acmecorp"
    assert spec.config == "enterprise.acmecorp.toml"
    assert spec.routes == ("acmecorp-proxy.example.cloud",)
    assert 'name = "proxy-acmecorp"' in text


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        (PROXY_TOML.replace("proxy-%s", "proxy-other") % (NAME, DOMAIN, DOMAIN), "name is"),
        (PROXY_TOML % (NAME, "other", DOMAIN, DOMAIN), "routes are"),
        (PROXY_TOML % (NAME, NAME, DOMAIN, DOMAIN) + "[env.x]\nname = 'y'\n", "[env.*]"),
        (PROXY_TOML % (NAME, NAME, DOMAIN, DOMAIN) + "# EXECUTOR_TOKEN\n", "EXECUTOR_TOKEN"),
        ("not = [toml", "TOML"),
    ],
)
def test_select_company_refuses_a_config_that_is_not_the_companys(root, text, needle):
    proxy_cfg(root).write_text(text)
    with pytest.raises(dp.RefusedError, match=needle):
        dp.select_company(root, _company_with(root))


def _company_with(root: pathlib.Path) -> ce.CompanyTarget:
    """The company with a proxy config already on disk, bypassing the worker-name check so the deploy-side gate is what refuses."""
    return ce.CompanyTarget(
        name=NAME,
        company_id=COMPANY_ID,
        region="eu",
        domain=DOMAIN,
        account_config=account_cfg(root),
        proxy_config=proxy_cfg(root),
    )


def test_select_company_applies_the_generators_own_spec_when_given(root):
    spec, _ = dp.select_company(root, target(root))
    stricter = dataclasses.replace(spec, name="proxy-different")
    with pytest.raises(dp.RefusedError, match="name is 'proxy-acmecorp'"):
        dp.select_company(root, target(root), stricter)


def test_proxy_company_dry_run_compiles_the_companys_config(root, monkeypatch):
    monkeypatch.setattr(common, "repo_root", lambda: root)
    monkeypatch.chdir(root)
    ran = []
    monkeypatch.setattr(dp, "_run", lambda argv, **_unused: ran.append(argv) or 0)
    rc = dp.main(
        [
            "--company",
            NAME,
            "--company-id",
            COMPANY_ID,
            "--region",
            "eu",
            "--company-domain",
            DOMAIN,
            "--proxy-config",
            str(proxy_cfg(root)),
            "--dry-run",
        ]
    )
    assert rc == 0
    assert ran
    assert "enterprise.acmecorp.toml" in ran[0]
    assert "wrangler.eu.toml" not in ran[0]


def test_proxy_company_refuses_var_and_target(root, monkeypatch, capsys):
    monkeypatch.setattr(common, "repo_root", lambda: root)
    base = [
        "--company",
        NAME,
        "--company-id",
        COMPANY_ID,
        "--region",
        "eu",
        "--company-domain",
        DOMAIN,
        "--proxy-config",
        str(proxy_cfg(root)),
        "--dry-run",
    ]
    assert dp.main([*base, "--var", "A=b"]) == 1
    assert "--var is refused with --company" in capsys.readouterr().err
    assert dp.main([*base, "--target", "stable"]) == 1
    assert "--company replaces --target" in capsys.readouterr().err


def test_proxy_main_still_requires_a_target_or_company():
    assert dp.main(["--dry-run"]) == 2


# ---- deploy_record: before ----------------------------------------------------------------


MANIFEST_FILES = {
    name: ("%x" % i) * 64
    for i, name in enumerate(
        ("cli-bundle.cjs", "node-natives-linux-x64.tar", "package.json", "renet-linux-amd64"),
        start=1,
    )
}


@pytest.fixture
def fakes(monkeypatch):
    """wrangler lookups, R2 reads, the control transport and any aws call, all recorded; an aws call or a pointer write fails the test."""
    state: dict[str, list] = {"reads": [], "control": [], "aws": [], "pointer": []}

    monkeypatch.setattr(
        dr,
        "worker_version",
        lambda _cwd, _cfg, worker: (True, ACCOUNT_LIVE if "account" in worker else PROXY_LIVE),
    )
    monkeypatch.setattr(dr, "d1_bookmark", lambda *_unused: BOOKMARK)

    def read(key):
        state["reads"].append(key)
        return {"manifest": True}

    monkeypatch.setattr(dr, "read_json_object", read)
    monkeypatch.setattr(dr, "manifest_sha256s", lambda *_unused: dict(MANIFEST_FILES))

    def no_aws(*a, **_unused):
        state["aws"].append(a)
        raise AssertionError("a company record reached the releases bucket through aws")

    monkeypatch.setattr(awscli, "run", no_aws)

    def no_pointer(*a, **_unused):
        state["pointer"].append(a)
        raise AssertionError("a company deploy wrote an executor-deployments pointer")

    monkeypatch.setattr(dr, "write_pointer", no_pointer)
    monkeypatch.setattr(dr, "control_write", lambda db, sql: state["control"].append((db, sql)))
    return state


def before_args(root: pathlib.Path, out: pathlib.Path, *extra: str) -> argparse.Namespace:
    return dr._parser().parse_args(
        [
            "before",
            *account_args(root),
            "--proxy-config",
            str(proxy_cfg(root)),
            "--version",
            VERSION,
            "--out",
            str(out),
            *extra,
        ]
    )


def test_a_company_before_record_reads_its_own_configs_and_no_pointer(root, fakes, tmp_path):
    out = tmp_path / "before.json"
    assert dr.cmd_before(before_args(root, out, "--previous-release", "1.4.1"), root) == 0
    record = json.loads(out.read_text())
    assert record["target"] == "company"
    assert record["region"] == "eu"
    assert record["company"]["id"] == COMPANY_ID
    assert record["account"]["worker"] == "account-acmecorp"
    assert record["proxy"]["worker"] == "proxy-acmecorp"
    assert record["proxy"]["release_before"] == "1.4.1"
    assert record["d1"]["database"] == "account-acmecorp"
    assert not any(k.startswith(dr.POINTER_PREFIX) for k in fakes["reads"])
    # The rollback commands name the company, never a shared target.
    assert "--company acmecorp" in record["rollback"]["1_console_executor"]
    assert "--company acmecorp" in record["rollback"]["2_proxy"]
    assert "--target" not in record["rollback"]["2_proxy"]


@pytest.mark.usefixtures("fakes")
def test_a_company_before_record_refuses_a_malformed_previous_release(root, tmp_path):
    with pytest.raises(dr.RecordError, match="--previous-release"):
        dr.cmd_before(before_args(root, tmp_path / "b.json", "--previous-release", "latest"), root)


@pytest.mark.usefixtures("fakes")
def test_before_refuses_company_with_target_and_neither(root, tmp_path):
    with pytest.raises(dr.RecordError, match="replaces --target"):
        dr.cmd_before(before_args(root, tmp_path / "b.json", "--target", "stable"), root)
    ns = dr._parser().parse_args(
        ["before", "--version", VERSION, "--out", str(tmp_path / "b.json")]
    )
    with pytest.raises(dr.RecordError, match="--target is required"):
        dr.cmd_before(ns, root)


@pytest.mark.usefixtures("fakes")
def test_a_company_account_only_record_carries_no_proxy_half(root, tmp_path):
    out = tmp_path / "before.json"
    ns = dr._parser().parse_args(
        ["before", *account_args(root), "--account-only", "--out", str(out)]
    )
    assert dr.cmd_before(ns, root) == 0
    record = json.loads(out.read_text())
    assert record["account_only"] is True
    assert record["target"] == "company"
    assert "proxy_config" not in record["company"]
    assert "proxy" not in record


# ---- deploy_record: after, and the sink is the control database -------------------------


def company_before(root, tmp_path, *extra) -> pathlib.Path:
    out = tmp_path / "before.json"
    dr.cmd_before(before_args(root, out, *extra), root)
    return out


def after_args(before: pathlib.Path, tmp_path: pathlib.Path, *extra: str) -> argparse.Namespace:
    proxy = tmp_path / "proxy.json"
    proxy.write_text(json.dumps({"smoke_rc": 0, "version_id": PROXY_LIVE}))
    return dr._parser().parse_args(
        [
            "after",
            "--before",
            str(before),
            "--proxy-record",
            str(proxy),
            "--manifest",
            str(tmp_path / "none.json"),
            "--enable-outcome",
            "success",
            "--account-smoke-rc",
            "0",
            "--out",
            str(tmp_path / "record.json"),
            *extra,
        ]
    )


def test_a_company_record_goes_to_the_control_database_and_never_names_the_releases_bucket(
    root, fakes, tmp_path
):
    before = company_before(root, tmp_path)
    ns = after_args(before, tmp_path, "--sink", "control", "--ring", "canary")
    assert dr.cmd_after(ns, root) == 0
    assert len(fakes["control"]) == 1
    database, sql = fakes["control"][0]
    assert database == "control-eu"
    assert "INSERT INTO rollout" in sql
    assert "INSERT INTO audit" in sql
    assert "'%s'" % COMPANY_ID in sql
    assert "'canary'" in sql
    assert "'deployed'" in sql
    # The bucket, the pointer prefix and the record prefix of the releases bucket appear nowhere.
    written = (tmp_path / "record.json").read_text()
    for blob in (sql, written, database):
        assert executor_artifacts.BUCKET not in blob
        assert dr.POINTER_PREFIX not in blob
        assert dr.RECORD_PREFIX not in blob
    assert fakes["aws"] == []
    assert fakes["pointer"] == []


def test_a_bench_company_record_goes_to_the_bench_control_database(root, fakes, tmp_path):
    out = tmp_path / "before.json"
    ns = dr._parser().parse_args(
        [
            "before",
            *account_args(root),
            "--company-bench",
            "--proxy-config",
            str(proxy_cfg(root)),
            "--version",
            VERSION,
            "--out",
            str(out),
        ]
    )
    dr.cmd_before(ns, root)
    assert (
        dr.cmd_after(after_args(out, tmp_path, "--sink", "control", "--ring", "small"), root) == 0
    )
    assert fakes["control"][0][0] == "control-bench-eu"


@pytest.mark.parametrize("sink", [[], ["--sink", "r2", "--channel", "edge"]])
def test_a_company_record_refuses_every_sink_but_control(root, fakes, tmp_path, sink):
    before = company_before(root, tmp_path)
    with pytest.raises(dr.RecordError, match="control database"):
        dr.cmd_after(after_args(before, tmp_path, *sink, "--ring", "canary"), root)
    assert fakes["control"] == []
    assert fakes["aws"] == []


@pytest.mark.usefixtures("fakes")
def test_a_company_record_needs_a_ring(root, tmp_path):
    before = company_before(root, tmp_path)
    with pytest.raises(dr.RecordError, match="--ring"):
        dr.cmd_after(after_args(before, tmp_path, "--sink", "control"), root)


@pytest.mark.usefixtures("fakes")
def test_a_shared_record_refuses_the_control_sink(root, tmp_path):
    shared = {
        "schema": 1,
        "phase": "before",
        "target": "stable",
        "region": "eu",
        "version": VERSION,
        "account": {"worker": "account-eu", "config": "workers/account/wrangler.eu.toml"},
        "proxy": {"worker": "proxy-eu", "config": "workers/proxy/wrangler.eu.toml"},
    }
    before = tmp_path / "shared.json"
    before.write_text(json.dumps(shared))
    with pytest.raises(dr.RecordError, match="company record"):
        dr.cmd_after(after_args(before, tmp_path, "--sink", "control", "--ring", "canary"), root)


def test_sink_record_refuses_a_company_target_outright():
    with pytest.raises(dr.RecordError, match="never the releases bucket"):
        dr.sink_record({"version": VERSION}, "r2", "edge", "company", "eu")


def test_a_failed_company_deploy_is_recorded_as_failed(root, fakes, tmp_path):
    before = company_before(root, tmp_path)
    ns = after_args(before, tmp_path, "--sink", "control", "--ring", "canary")
    proxy = tmp_path / "proxy.json"
    proxy.write_text(json.dumps({"smoke_rc": 1, "version_id": PROXY_LIVE}))
    assert dr.cmd_after(ns, root) == 0
    assert "'failed'" in fakes["control"][0][1]


@pytest.mark.usefixtures("fakes")
def test_a_control_write_failure_fails_the_after_step(root, tmp_path, monkeypatch):
    def boom(db, _sql):
        raise dr.RecordError("the rollout row already exists in %s" % db)

    monkeypatch.setattr(dr, "control_write", boom)
    before = company_before(root, tmp_path)
    ns = after_args(before, tmp_path, "--sink", "control", "--ring", "canary")
    assert dr.cmd_after(ns, root) == 1


def test_the_statements_quote_a_value_carrying_a_single_quote():
    sql = dr.control_statements(
        {"version": "1.0.0", "good": True, "note": "it's"}, COMPANY_ID, "canary", "v1.0.0"
    )
    assert "it''s" in sql
    assert dr.sql_text("a'b") == "'a''b'"


def test_the_control_transport_runs_wrangler_d1_execute_remote_from_a_neutral_directory(
    monkeypatch,
):
    calls = []

    def fake(argv, **kw):
        calls.append((argv, kw))
        return subprocess.CompletedProcess(argv, 0, "[]", "")

    monkeypatch.setattr(subprocess, "run", fake)
    dr.wrangler_control_write("control-eu", "SELECT 1;")
    argv, kw = calls[0]
    assert argv[-7:] == [
        "d1",
        "execute",
        "control-eu",
        "--remote",
        "--json",
        "--command",
        "SELECT 1;",
    ]
    assert kw["cwd"] != str(paths.repo_root())


def test_the_control_transport_maps_a_duplicate_row_to_write_once(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **_unused: subprocess.CompletedProcess(
            argv, 1, "", "D1_ERROR: UNIQUE constraint failed: rollout.release_id"
        ),
    )
    with pytest.raises(dr.RecordError, match="written once"):
        dr.wrangler_control_write("control-eu", "x")


# ---- deploy_record: bootstrap, rollback and the credentials profile ------------------------


@pytest.mark.usefixtures("fakes")
def test_bootstrap_and_rollback_name_the_company_in_their_children(root, tmp_path, monkeypatch):
    record = json.loads(company_before(root, tmp_path).read_text())
    record["proxy"]["existed"] = False
    before = tmp_path / "nb.json"
    before.write_text(json.dumps(record))
    children = []
    monkeypatch.setattr(dr, "_run_child", lambda argv: children.append(argv) or 0)
    ns = argparse.Namespace(before=str(before), record=str(tmp_path / "pr.json"))
    assert dr.cmd_bootstrap(ns, root) == 0
    argv = children[0]
    assert "--company" in argv
    assert COMPANY_ID in argv
    assert "--target" not in argv

    closed = []
    monkeypatch.setattr(
        ce,
        "run",
        lambda action, *_unused, company=None, **_kw: closed.append((action, company)) or 0,
    )
    live = json.loads(before.read_text())
    live["proxy"]["existed"] = True
    live["proxy"]["version_before"] = "old-version"
    live["proxy"]["release_before"] = "1.4.1"
    before.write_text(json.dumps(live))
    children.clear()
    assert dr.cmd_rollback(argparse.Namespace(before=str(before)), root) == 0
    assert closed[0][0] == "disable"
    assert closed[0][1].company_id == COMPANY_ID
    assert children
    assert "--company" in children[0]
    assert "1.4.1" in children[0]


@pytest.mark.usefixtures("fakes")
def test_a_company_record_picks_the_credentials_profile_of_its_bench_flag(root, tmp_path):
    before = company_before(root, tmp_path)
    ns = argparse.Namespace(verb="after", before=str(before))
    assert dr.record_target(ns) == "stable"
    record = json.loads(before.read_text())
    record["company"]["bench"] = True
    before.write_text(json.dumps(record))
    assert dr.record_target(ns) == "bench"
    live = dr._parser().parse_args(["before", *account_args(root), "--company-bench", "--out", "x"])
    assert dr.record_target(live) == "bench"


# ---- the label never reaches stdout or stderr ---------------------------------------------

LABEL = "zorkmidlabel"
LABEL_ID = "c9f8e7d6c5b4a392"


@pytest.fixture
def lroot(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch repo root whose company carries a distinctive label."""
    shutil.copy(paths.repo_root() / "regions.json", tmp_path / "regions.json")
    for kind, text in (
        ("account", ACCOUNT_TOML % (LABEL, LABEL)),
        ("proxy", PROXY_TOML % (LABEL, LABEL, DOMAIN, DOMAIN)),
    ):
        folder = tmp_path / "workers" / kind
        folder.mkdir(parents=True)
        (folder / ("enterprise.%s.toml" % LABEL)).write_text(text)
    return tmp_path


def ltarget(root: pathlib.Path, **over) -> ce.CompanyTarget:
    args = {
        "name": LABEL,
        "company_id": LABEL_ID,
        "region": "eu",
        "domain": DOMAIN,
        "account_config": root / "workers" / "account" / ("enterprise.%s.toml" % LABEL),
        "proxy_config": root / "workers" / "proxy" / ("enterprise.%s.toml" % LABEL),
    }
    args.update(over)
    return ce.company_target(root, **args)


def lflags(root: pathlib.Path, kind: str) -> list[str]:
    return [
        "--company",
        LABEL,
        "--company-id",
        LABEL_ID,
        "--region",
        "eu",
        "--company-domain",
        DOMAIN,
        "--%s-config" % kind,
        str(root / "workers" / kind / ("enterprise.%s.toml" % LABEL)),
    ]


def assert_label_free(capsys) -> None:
    out = capsys.readouterr()
    assert LABEL not in out.out
    assert LABEL not in out.err


@pytest.mark.parametrize("action", ["enable", "disable"])
@pytest.mark.parametrize("shape", ["ok", "put-fails", "list-fails", "still-open"])
def test_the_executor_switch_logs_no_label_on_any_path(lroot, monkeypatch, capsys, action, shape):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setattr(ce, "_run", lambda *_unused: 1 if shape == "put-fails" else 0)
    listed = {
        "ok": {ce.MODE_KEY} if action == "enable" else set(),
        "put-fails": {ce.MODE_KEY},
        "list-fails": None,
        "still-open": set() if action == "enable" else {ce.MODE_KEY},
    }[shape]
    monkeypatch.setattr(ce, "_list", lambda *_unused: listed)
    ce.run(action, "", None, lroot, company=ltarget(lroot))
    assert_label_free(capsys)


def test_the_executor_switch_names_the_opaque_id_in_its_log_lines(lroot, monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setattr(ce, "_run", lambda *_unused: 0)
    monkeypatch.setattr(ce, "_list", lambda *_unused: {ce.MODE_KEY})
    assert ce.run("enable", "", None, lroot, company=ltarget(lroot)) == 0
    assert LABEL_ID in capsys.readouterr().err


@pytest.mark.parametrize("file_name", ["wrangler.eu.toml", "enterprise.other.toml"])
def test_a_company_config_refusal_names_no_label(lroot, file_name):
    wrong = lroot / "workers" / "account" / file_name
    wrong.write_text(ACCOUNT_TOML % (LABEL, LABEL))
    with pytest.raises(ce.RefusedError) as caught:
        ltarget(lroot, account_config=wrong)
    assert LABEL not in str(caught.value)


def test_a_company_config_naming_another_worker_refuses_without_the_label(lroot):
    cfg = lroot / "workers" / "account" / ("enterprise.%s.toml" % LABEL)
    cfg.write_text(ACCOUNT_TOML % ("someoneelse", "someoneelse"))
    with pytest.raises(ce.RefusedError) as caught:
        ltarget(lroot)
    assert LABEL not in str(caught.value)


def test_the_account_deploy_logs_no_label_in_a_dry_run(lroot, monkeypatch, capsys):
    monkeypatch.setattr(common, "repo_root", lambda: lroot)
    assert da.main([*lflags(lroot, "account"), "--dry-run"]) == 0
    first = capsys.readouterr()
    assert LABEL_ID in first.err
    assert LABEL not in first.out + first.err
    cfg = lroot / "workers" / "account" / ("enterprise.%s.toml" % LABEL)
    cfg.write_text('compatibility_date = "2026-01-01"\n' + cfg.read_text())
    assert da.main([*lflags(lroot, "account"), "--dry-run", "--stub"]) == 0
    assert_label_free(capsys)


def test_the_account_deploy_logs_no_label_on_a_refusal(lroot, monkeypatch, capsys):
    monkeypatch.setattr(common, "repo_root", lambda: lroot)
    args = lflags(lroot, "account")
    shared = lroot / "workers" / "account" / "wrangler.eu.toml"
    shared.write_text(ACCOUNT_TOML % (LABEL, LABEL))
    args[args.index("--account-config") + 1] = str(shared)
    assert da.main([*args, "--dry-run"]) == 1
    assert_label_free(capsys)


def test_the_account_deploy_logs_no_label_when_its_config_is_missing(lroot, monkeypatch, capsys):
    monkeypatch.setattr(common, "repo_root", lambda: lroot)
    company = ltarget(lroot)
    company.account_config.unlink()
    monkeypatch.setattr(da, "company_from_args", lambda *_unused: company)
    assert da.main([*lflags(lroot, "account"), "--dry-run"]) == 1
    err = capsys.readouterr().err
    assert "not found" in err
    assert LABEL not in err


@pytest.fixture
def account_fakes(lroot, monkeypatch):
    monkeypatch.setattr(common, "repo_root", lambda: lroot)
    monkeypatch.chdir(lroot)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setattr(da, "_run", lambda _argv, **_unused: 0)
    monkeypatch.setattr(da, "needs_npm_install", lambda *_unused: False)
    monkeypatch.setattr(da, "portal_sitekey_refusal", lambda *_unused: None)
    monkeypatch.setattr(da, "check_services", lambda *_unused: None)
    monkeypatch.setattr(da, "check_queues", lambda *_unused, **_kw: [])
    monkeypatch.setattr(da, "portal_smoke", lambda *_unused: None)


@pytest.mark.usefixtures("account_fakes")
def test_the_account_deploy_logs_no_label_on_success(lroot, capsys):
    assert da.main(lflags(lroot, "account")) == 0
    out = capsys.readouterr()
    assert LABEL_ID in out.err
    assert LABEL not in out.out + out.err


@pytest.mark.usefixtures("account_fakes")
def test_the_account_deploy_logs_no_label_when_a_check_refuses(lroot, monkeypatch, capsys):
    def refuse(*_unused):
        raise da.ServiceBindingError("binding of enterprise.%s.toml is missing" % LABEL)

    monkeypatch.setattr(da, "check_services", refuse)
    assert da.main(lflags(lroot, "account")) == 1
    assert_label_free(capsys)
    monkeypatch.setattr(da, "check_services", lambda *_unused: None)
    monkeypatch.setattr(da, "portal_smoke", lambda *_unused: "the portal of %s is keyless" % LABEL)
    assert da.main(lflags(lroot, "account")) == 1
    assert_label_free(capsys)


class FakeFetcher:
    pin = None

    def __init__(self, _host):
        pass

    def code(self, url):
        return "401" if url.endswith("/v1/server-info") else "200"


@pytest.fixture
def proxy_fakes(lroot, monkeypatch):
    """Everything under deploy_proxy that would reach wrangler, the network or the image build."""
    monkeypatch.setattr(common, "repo_root", lambda: lroot)
    monkeypatch.chdir(lroot)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setattr(dp, "_run", lambda _argv, **_unused: 0)
    monkeypatch.setattr(
        dp, "_run_tee", lambda _argv, **_unused: (0, "Current Version ID: %s\n" % PROXY_LIVE)
    )
    monkeypatch.setattr(dp, "deployed_version", lambda *_unused: PROXY_LIVE)
    monkeypatch.setattr(dp, "stage_release", lambda *_unused: 0)
    monkeypatch.setattr(dp, "forward_only_state", lambda *_a, **_kw: (False, None))
    monkeypatch.setattr(dp, "_Fetcher", FakeFetcher)
    ready = json.dumps({"ready": True, "workerVersion": PROXY_LIVE})
    monkeypatch.setattr(dp, "_curl_body", lambda *_unused: (ready, "200"))


@pytest.mark.usefixtures("proxy_fakes")
def test_the_proxy_deploy_logs_no_label_in_a_dry_run(lroot, capsys):
    assert dp.main([*lflags(lroot, "proxy"), "--dry-run"]) == 0
    out = capsys.readouterr()
    assert LABEL_ID in out.err
    assert LABEL not in out.out + out.err


@pytest.mark.usefixtures("proxy_fakes")
def test_the_proxy_deploy_logs_no_label_on_success(lroot, capsys):
    assert dp.main([*lflags(lroot, "proxy"), "--version", VERSION]) == 0
    out = capsys.readouterr()
    assert LABEL_ID in out.err
    assert LABEL not in out.out + out.err


@pytest.mark.usefixtures("proxy_fakes")
def test_the_proxy_deploy_logs_no_label_on_a_failed_listing(lroot, monkeypatch, capsys):
    other = "dddddddd-0000-4000-8000-000000000009"
    monkeypatch.setattr(dp, "deployed_version", lambda *_unused: other)
    assert dp.main([*lflags(lroot, "proxy"), "--version", VERSION]) == 1
    assert_label_free(capsys)


@pytest.mark.usefixtures("proxy_fakes")
def test_the_proxy_rollback_logs_no_label(lroot, capsys):
    assert dp.main([*lflags(lroot, "proxy"), "--rollback", PROXY_LIVE]) == 0
    out = capsys.readouterr()
    assert LABEL_ID in out.err
    assert LABEL not in out.out + out.err


@pytest.mark.usefixtures("proxy_fakes")
def test_the_proxy_deploy_logs_no_label_on_a_refusal(lroot, capsys):
    cfg = lroot / "workers" / "proxy" / ("enterprise.%s.toml" % LABEL)
    cfg.write_text(PROXY_TOML % (LABEL, "intruder", DOMAIN, DOMAIN))
    assert dp.main([*lflags(lroot, "proxy"), "--dry-run"]) == 1
    err = capsys.readouterr().err
    assert "routes are" in err
    assert LABEL not in err


@pytest.mark.usefixtures("proxy_fakes")
def test_the_proxy_deploy_logs_no_label_on_a_var_refusal(lroot, capsys):
    assert dp.main([*lflags(lroot, "proxy"), "--dry-run", "--var", "A=b"]) == 1
    assert_label_free(capsys)


@pytest.mark.usefixtures("fakes")
def test_the_record_steps_log_no_label(lroot, tmp_path, capsys):
    out = tmp_path / "before.json"
    ns = dr._parser().parse_args(
        [
            "before",
            *lflags(lroot, "account"),
            "--proxy-config",
            str(lroot / "workers" / "proxy" / ("enterprise.%s.toml" % LABEL)),
            "--version",
            VERSION,
            "--out",
            str(out),
        ]
    )
    assert dr.cmd_before(ns, lroot) == 0
    assert_label_free(capsys)
    after = after_args(out, tmp_path, "--sink", "control", "--ring", "canary")
    assert dr.cmd_after(after, lroot) == 0
    assert_label_free(capsys)


# ---- findings 0f1d42ca.3 and .4 ------------------------------------------------------------


def shared_before_fakes(monkeypatch, pointer):
    monkeypatch.setattr(dr, "read_toml", lambda _p: {"name": "account-x"})
    monkeypatch.setattr(dr, "database_name", lambda *_unused: "db")
    monkeypatch.setattr(dr, "worker_name", lambda doc, _p: str(doc["name"]))
    monkeypatch.setattr(
        dr,
        "read_json_object",
        lambda key: pointer if key.startswith(dr.POINTER_PREFIX) else {"manifest": True},
    )


@pytest.mark.usefixtures("fakes")
def test_a_shared_before_drops_an_unvalidated_previous_release_when_the_pointer_names_one(
    monkeypatch,
):
    shared_before_fakes(monkeypatch, {"release_version": "1.2.3"})
    record = dr.take_before(paths.repo_root(), "stable", "eu", VERSION, None, "not;a version")
    assert record["proxy"]["release_before"] == "1.2.3"
    assert "not;a version" not in json.dumps(record)


@pytest.mark.usefixtures("fakes")
def test_a_shared_before_without_a_pointer_has_no_previous_release(monkeypatch):
    shared_before_fakes(monkeypatch, None)
    record = dr.take_before(paths.repo_root(), "stable", "eu", VERSION, None, "not;a version")
    assert record["proxy"]["release_before"] is None
    assert "not;a version" not in json.dumps(record)


@pytest.mark.parametrize("region", ["us", "asia"])
def test_a_bench_company_is_refused_outside_the_bench_region(root, region):
    with pytest.raises(ce.RefusedError, match="bench"):
        target(root, region=region, bench=True)


def test_a_bench_company_is_accepted_in_the_bench_region(root):
    assert target(root, region=ce.BENCH_REGION, bench=True).bench is True


@pytest.mark.usefixtures("fakes")
def test_a_company_rollback_points_at_the_runnable_commands_instead_of_printing_masked_ones(
    lroot, tmp_path, capsys
):
    """Review a55df887.1: a masked `wrangler rollback` line named `enterprise.<id>.toml`, a config that does not exist, so a copied command failed mid-incident. The human-run commands are pointed at in the before record, which keeps them runnable, and the label stays out of the console."""
    out = tmp_path / ("before-%s.json" % LABEL)
    ns = dr._parser().parse_args(
        [
            "before",
            *lflags(lroot, "account"),
            "--proxy-config",
            str(lroot / "workers" / "proxy" / ("enterprise.%s.toml" % LABEL)),
            "--version",
            VERSION,
            "--out",
            str(out),
        ]
    )
    assert dr.cmd_before(ns, lroot) == 0
    capsys.readouterr()
    record = json.loads(out.read_text())
    assert LABEL in record["rollback"]["3_account"]
    record["account_only"] = True
    out.write_text(json.dumps(record))
    assert dr.cmd_rollback(argparse.Namespace(before=str(out)), lroot) == 0
    got = capsys.readouterr()
    assert "rollback.3_account" in got.out
    assert "rollback.4_d1" in got.out
    assert "enterprise.%s.toml" % LABEL_ID not in got.out
    assert LABEL not in got.out + got.err


def test_mask_label_replaces_a_label_joined_to_a_suffix():
    """Review a55df887.3: a whole-token match left `acmecorpdb` unmasked."""
    assert ce.mask_label("acmecorpdb and account-AcmeCorp", "acmecorp", "c0123456789abcdef") == (
        "c0123456789abcdefdb and account-c0123456789abcdef"
    )
