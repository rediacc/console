"""reset_bench fails closed (agent/plans/PLAN-hostinger-to-bench.md L5, the 2026-11-27 defect): with an empty `.ci/config/bench-production.json` a `reset_bench --yes` wiped the bench D1 that held hostinger's backup manifests. A wipe now needs every positive condition, and each refusal exits 2 with nothing wiped: an armed declaration with nothing in the wiped region, a bench-named target no production config binds, and a live D1 without a single backup manifest. Every Cloudflare and credential seam is a fake from `test_ops_reset_bench_region._world`; nothing here reaches a real bench."""

from __future__ import annotations

import dataclasses
import json
import shutil

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import bench_preflight, bench_production, reset_bench
from rediacc_ci.tests.test_ops_reset_bench_region import ARMED, NAMES, SUB, _world

OTHER = "99999999-9999-4999-8999-999999999999"
ALL_MODES = [["--yes"], ["--yes", "--d1-only"], ["--yes", "--r2-only"]]


def _wiped(asked: list[tuple]) -> list[tuple]:
    return [step for step in asked if step[0] in ("wipe_d1", "wipe_r2")]


def _track_cloudflare(monkeypatch) -> list[str]:
    """Record every credential resolve: a static refusal must come before the first one."""
    calls: list[str] = []
    real = reset_bench.cf_auth.resolve

    def resolve(account):
        calls.append(account)
        return real(account)

    monkeypatch.setattr(reset_bench.cf_auth, "resolve", resolve)
    return calls


# --- the declaration


@pytest.mark.parametrize("argv", ALL_MODES)
def test_an_empty_declaration_refuses_every_mode_before_cloudflare(monkeypatch, capsys, argv):
    asked: list[tuple] = []
    _world(monkeypatch, [], asked)
    cf = _track_cloudflare(monkeypatch)
    assert reset_bench.main(argv) == bench_production.REFUSAL_EXIT
    assert "unarmed" in capsys.readouterr().err
    assert asked == []
    assert cf == []


def test_an_unreadable_declaration_refuses(monkeypatch, capsys):
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)

    def unreadable(*_a):
        raise bench_production.ProductionRefusalError("cannot read; the guard fails closed")

    monkeypatch.setattr(bench_production, "load", unreadable)
    cf = _track_cloudflare(monkeypatch)
    assert reset_bench.main(["--yes"]) == bench_production.REFUSAL_EXIT
    assert "fails closed" in capsys.readouterr().err
    assert asked == []
    assert cf == []


@pytest.mark.parametrize("argv", ALL_MODES)
def test_a_declaration_in_the_wiped_region_refuses_every_mode(monkeypatch, capsys, argv):
    asked: list[tuple] = []
    _world(monkeypatch, [bench_production.Protected(SUB, "hostinger", "backups", "us")], asked)
    cf = _track_cloudflare(monkeypatch)
    assert reset_bench.main(["--region", "us", *argv]) == bench_production.REFUSAL_EXIT
    assert SUB in capsys.readouterr().err
    assert asked == []
    assert cf == []


# --- the target


@pytest.mark.parametrize(
    "field",
    ["database_name", "config_bucket", "audit_bucket"],
)
def test_a_target_that_is_not_bench_named_refuses_before_cloudflare(monkeypatch, capsys, field):
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)
    names = dataclasses.replace(NAMES, **{"audit_bucket": "audit-bench-us", field: "account-eu"})
    monkeypatch.setattr(reset_bench, "_names", lambda _region="eu": names)
    cf = _track_cloudflare(monkeypatch)
    assert reset_bench.main(["--region", "us", "--yes"]) == bench_production.REFUSAL_EXIT
    err = capsys.readouterr().err
    assert "not bench-named" in err
    assert "account-eu" in err
    assert _wiped(asked) == []
    assert cf == []


def _tree(tmp_path, production_toml: str) -> None:
    (tmp_path / "workers/account").mkdir(parents=True)
    (tmp_path / "regions.json").write_text(
        json.dumps({"regions": [{"id": "eu"}, {"id": "us"}]}), encoding="utf-8"
    )
    (tmp_path / "workers/account/wrangler.us.toml").write_text(production_toml, encoding="utf-8")


PRODUCTION_US = (
    '[[d1_databases]]\nbinding = "DB"\ndatabase_name = "account-us"\ndatabase_id = "id-us"\n\n'
    '[[r2_buckets]]\nbinding = "CONFIG_BUCKET"\nbucket_name = "configs-us"\n'
)


def test_a_target_a_production_config_also_binds_refuses(monkeypatch, capsys, tmp_path):
    # NAMES carries database_id "id-us": bench-named everywhere, yet the id is production us's.
    _tree(tmp_path, PRODUCTION_US)
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(bench_preflight, "bench_object", lambda *_a, **_k: {})
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)
    cf = _track_cloudflare(monkeypatch)
    assert reset_bench.main(["--region", "us", "--yes"]) == bench_production.REFUSAL_EXIT
    err = capsys.readouterr().err
    assert "'id-us' is also bound by wrangler.us.toml" in err
    assert _wiped(asked) == []
    assert cf == []


def test_a_production_config_that_cannot_be_parsed_refuses(monkeypatch, capsys, tmp_path):
    _tree(tmp_path, "[[d1_databases\nnot toml")
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(bench_preflight, "bench_object", lambda *_a, **_k: {})
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)
    assert reset_bench.main(["--region", "us", "--yes"]) == bench_production.REFUSAL_EXIT
    assert "fails closed" in capsys.readouterr().err
    assert _wiped(asked) == []


def test_an_unreadable_regions_file_refuses(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(bench_preflight, "bench_object", lambda *_a, **_k: {})
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)
    assert reset_bench.main(["--region", "us", "--yes"]) == bench_production.REFUSAL_EXIT
    assert "wipe target check cannot run" in capsys.readouterr().err
    assert _wiped(asked) == []


def test_an_unreadable_bench_config_refuses(monkeypatch, capsys):
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)

    def unreadable(_region="eu"):
        raise reset_bench.ResetError("cannot read the bench names")

    monkeypatch.setattr(reset_bench, "_names", unreadable)
    assert reset_bench.main(["--region", "us", "--yes"]) == bench_production.REFUSAL_EXIT
    assert "fails closed" in capsys.readouterr().err
    assert _wiped(asked) == []


def test_the_committed_bench_configs_pass_the_target_check():
    for region in bench_preflight.bench_regions():
        assert reset_bench._target_refusal(region) is None, region


def test_a_bench_config_reusing_the_production_eu_database_id_refuses(tmp_path, monkeypatch):
    # The committed production config is the oracle: a bench-named database carrying account-eu's id is refused.
    root = paths.repo_root()
    (tmp_path / "workers/account").mkdir(parents=True)
    shutil.copy2(root / "regions.json", tmp_path / "regions.json")
    shutil.copy2(
        root / "workers/account/wrangler.eu.toml", tmp_path / "workers/account/wrangler.eu.toml"
    )
    production = bench_production._bindings(tmp_path / "workers/account/wrangler.eu.toml")
    eu_id = next(v for v in production if len(v) == 36 and v.count("-") == 4)
    names = bench_preflight.BenchNames("account-bench", eu_id, "configs-bench", "", "b", "")
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(reset_bench, "_names", lambda _region="eu": names)
    refusal = reset_bench._target_refusal("eu")
    assert refusal is not None
    assert "wrangler.eu.toml" in refusal
    # control: the bench's own id passes against the same production config
    monkeypatch.setattr(
        reset_bench,
        "_names",
        lambda _region="eu": dataclasses.replace(names, database_id="bench-own-id"),
    )
    assert reset_bench._target_refusal("eu") is None


# --- the live production signal


@pytest.mark.parametrize("argv", ALL_MODES)
def test_any_backup_manifest_in_the_live_d1_refuses_every_mode(monkeypatch, capsys, argv):
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)
    seen: list[str] = []

    def rows(_auth, sql, _region="eu"):
        seen.append(sql)
        return [{"subscription_id": OTHER, "manifests": 4}]

    monkeypatch.setattr(reset_bench, "_rows", rows)
    assert reset_bench.main(["--region", "us", *argv]) == bench_production.REFUSAL_EXIT
    err = capsys.readouterr().err
    assert "production signal" in err
    assert OTHER in err
    assert seen == [bench_production.MANIFEST_QUERY]
    assert _wiped(asked) == []


def test_a_failed_live_d1_read_refuses(monkeypatch, capsys):
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)

    def rows(*_a):
        raise reset_bench.ResetError("D1 query failed")

    monkeypatch.setattr(reset_bench, "_rows", rows)
    assert reset_bench.main(["--region", "us", "--yes"]) == bench_production.REFUSAL_EXIT
    assert "could not run" in capsys.readouterr().err
    assert _wiped(asked) == []


# --- the fully-qualified case


def test_only_the_fully_qualified_case_wipes(monkeypatch):
    # Armed declaration with nothing in us, a bench-named us target, and a live D1 whose manifest query answers no row.
    asked: list[tuple] = []
    _world(monkeypatch, ARMED, asked)
    seen: list[str] = []

    def rows(_auth, sql, _region="eu"):
        seen.append(sql)
        return []

    monkeypatch.setattr(reset_bench, "_rows", rows)
    assert reset_bench.main(["--region", "us", "--yes"]) == 0
    assert seen == [bench_production.MANIFEST_QUERY]
    assert _wiped(asked) == [
        ("wipe_d1", "us"),
        ("wipe_r2", "configs-bench-us"),
        ("wipe_r2", "audit-bench-us"),
    ]
