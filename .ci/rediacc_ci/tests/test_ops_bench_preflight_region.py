"""bench_preflight `--region` helpers (agent/plans/PLAN-multi-region-bench.md W3): the per-region config name, the regions.json bench object, the argument reader and the `buckets --region` form."""

from __future__ import annotations

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import bench_preflight


def test_the_config_name_is_unsuffixed_for_the_home_region_only():
    assert bench_preflight.config_name() == "wrangler.bench.toml"
    assert bench_preflight.config_name("eu") == "wrangler.bench.toml"
    assert bench_preflight.config_name("us") == "wrangler.bench-us.toml"
    assert bench_preflight.config_rel("asia")[-1] == "wrangler.bench-asia.toml"
    assert bench_preflight.config_rel() == bench_preflight.BENCH_CONFIG_REL


def test_every_regions_json_bench_has_a_config_file():
    for region in bench_preflight.bench_regions():
        assert paths.repo_root().joinpath(*bench_preflight.config_rel(region)).is_file(), region


def test_bench_names_follow_the_region_config():
    assert bench_preflight.bench_names(region="us").database_name == "account-bench-us"
    assert bench_preflight.bench_names().database_name == "account-bench"


def test_bench_object_names_an_unknown_region():
    with pytest.raises(ValueError, match="no region 'mars'"):
        bench_preflight.bench_object("mars")


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], ("eu", [])),
        (["--yes"], ("eu", ["--yes"])),
        (["--region", "us", "--yes"], ("us", ["--yes"])),
        (["--yes", "--region=asia"], ("asia", ["--yes"])),
    ],
)
def test_take_region_reads_both_spellings(argv, expected):
    assert bench_preflight.take_region(argv) == expected


@pytest.mark.parametrize("argv", [["--region"], ["--region="], ["--region", "eu", "--region=us"]])
def test_take_region_refuses_a_missing_or_repeated_value(argv):
    with pytest.raises(ValueError, match="--region"):
        bench_preflight.take_region(argv)


def test_buckets_region_reads_that_regions_config(monkeypatch):
    seen = []

    def buckets(config):
        seen.append(config)
        return 0

    monkeypatch.setattr(bench_preflight, "buckets", buckets)
    assert bench_preflight.main(["buckets", "--region", "us"]) == 0
    assert seen[0].endswith("workers/account/wrangler.bench-us.toml")


def test_buckets_region_refuses_an_unknown_region(monkeypatch, capsys):
    monkeypatch.setattr(bench_preflight, "buckets", lambda _c: pytest.fail("ran"))
    assert bench_preflight.main(["buckets", "--region", "mars"]) == 2
    assert "no region 'mars'" in capsys.readouterr().err
