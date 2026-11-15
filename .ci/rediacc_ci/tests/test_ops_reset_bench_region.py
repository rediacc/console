"""reset_bench `--region` (agent/plans/PLAN-multi-region-bench.md W3): a wipe names its region, reads that region's config, asks that region's confirmation phrase, and is stopped only by a subscription declared in that region."""

from __future__ import annotations

import types

import pytest

from rediacc_ci.ops import bench_preflight, bench_production, reset_bench

SUB = "33333333-3333-4333-8333-333333333333"
NAMES = bench_preflight.BenchNames("account-bench-us", "id-us", "configs-bench-us", "", "b", "")


def _auth() -> types.SimpleNamespace:
    return types.SimpleNamespace(headers={})


class CredentialReadError(Exception):
    """Raised by a seam that would read or mint a credential."""


def _world(monkeypatch, declared, asked):
    monkeypatch.setattr(bench_production, "load", lambda *_a: declared)
    monkeypatch.setattr(reset_bench.shutil, "which", lambda _c: "/usr/bin/true")
    monkeypatch.setattr(reset_bench, "_reexec_under_profile", lambda _a: None)
    monkeypatch.setattr(reset_bench.cf_auth, "resolve", lambda _a: _auth())
    monkeypatch.setattr(reset_bench.cf_auth, "wrangler_env", lambda *_a, **_k: {})
    monkeypatch.setattr(reset_bench.cf_auth, "await_propagation", lambda _a: None)
    monkeypatch.setattr(reset_bench.cf_auth, "self_destruct", lambda _a: None)
    monkeypatch.setattr(
        reset_bench, "_names", lambda region="eu": asked.append(("names", region)) or NAMES
    )

    class Creds:
        bucket = "configs-bench-us"

        def __init__(self, region="eu"):
            asked.append(("creds", region))

        def missing(self):
            return []

    monkeypatch.setattr(reset_bench, "R2Credentials", Creds)
    monkeypatch.setattr(
        reset_bench, "_wipe_d1", lambda _a, _e, region="eu": asked.append(("wipe_d1", region))
    )
    monkeypatch.setattr(reset_bench, "_wipe_r2", lambda _c: asked.append(("wipe_r2",)))
    monkeypatch.setattr(reset_bench, "_rows", lambda _a, _s, _region="eu": [])


def test_the_confirmation_phrase_names_every_region():
    assert reset_bench.confirmation() == "wipe bench-eu"
    assert reset_bench.confirmation("eu") == "wipe bench-eu"
    assert reset_bench.confirmation("us") == "wipe bench-us"


def test_a_us_wipe_reads_the_us_config_and_asks_the_us_phrase(monkeypatch):
    asked: list[tuple] = []
    _world(monkeypatch, [], asked)
    monkeypatch.setattr("builtins.input", lambda: "wipe bench-eu")
    assert reset_bench.main(["--region", "us"]) == 1
    assert ("wipe_d1", "us") not in asked
    monkeypatch.setattr("builtins.input", lambda: "wipe bench-us")
    assert reset_bench.main(["--region", "us"]) == 0
    for step in (("names", "us"), ("creds", "us"), ("wipe_d1", "us")):
        assert step in asked


def test_the_default_region_asks_its_own_suffixed_phrase(monkeypatch):
    asked: list[tuple] = []
    _world(monkeypatch, [], asked)
    monkeypatch.setattr("builtins.input", lambda: "wipe bench")
    assert reset_bench.main([]) == 1
    assert ("wipe_d1", "eu") not in asked
    monkeypatch.setattr("builtins.input", lambda: "wipe bench-eu")
    assert reset_bench.main([]) == 0
    assert ("wipe_d1", "eu") in asked


def test_a_us_declaration_stops_the_us_wipe_and_not_the_eu_one(monkeypatch):
    asked: list[tuple] = []
    declared = [bench_production.Protected(SUB, "hostinger", "backups", "us")]
    _world(monkeypatch, declared, asked)
    assert reset_bench.main(["--region", "us", "--yes"]) == bench_production.REFUSAL_EXIT
    assert asked == []
    # control: the same declaration leaves an eu wipe alone
    assert reset_bench.main(["--yes"]) == 0
    assert ("wipe_d1", "eu") in asked


@pytest.mark.parametrize("argv", [["--region", "all"], ["--region", "mars"], ["--region"]])
def test_an_unknown_or_missing_region_exits_2_before_anything(monkeypatch, argv):
    asked: list[tuple] = []
    _world(monkeypatch, [], asked)
    assert reset_bench.main([*argv, "--yes"]) == 2
    assert asked == []


def test_the_help_names_the_region_flag():
    assert "--region" in reset_bench.HELP
