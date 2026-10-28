"""`rediacc_ci.deploy.proxy_configs`: six proxy configs generated from one template, bench and dev held to the same refusals (agent/plans/PLAN-proxy-cd-six-targets.md box K1).

CONTROL FIRST. The real tree must pass `--check`, and every unplanted config must carry no refusal, so a refusal on a plant is the plant's doing. Each plant changes ONE thing in a copy of a real config and must be refused by name. The real files are never written: the stale-file case runs `--check` over a copy of the tree under `tmp_path`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import proxy_configs as pc
from rediacc_ci.well_known import (
    PROXY_ASIA_HOST,
    PROXY_EDGE_ASIA_HOST,
    PROXY_EDGE_EU_HOST,
    PROXY_EDGE_US_HOST,
    PROXY_EU_HOST,
    PROXY_US_HOST,
)

US_DOMAIN = PROXY_US_HOST.removeprefix("proxy.")


if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PROXY = ROOT.joinpath(*pc.PROXY_REL)
REGIONS = pc.load_regions(ROOT)
TARGETS = pc.targets(REGIONS)
ALL_REGIONS = frozenset(str(r["id"]) for r in REGIONS)


def real(key: str) -> str:
    return (PROXY / TARGETS[key].config).read_text(encoding="utf-8")


def refusals(text: str, key: str) -> list[str]:
    return pc.config_refusals(text, TARGETS[key], ALL_REGIONS)


def plant(text: str, old: str, new: str) -> str:
    assert old in text, "fixture drift: %r is not in the config" % old
    return text.replace(old, new, 1)


def copy_tree(dest: pathlib.Path) -> pathlib.Path:
    shutil.copy2(ROOT / pc.REGIONS_REL, dest / pc.REGIONS_REL)
    for rel in (pc.PROXY_REL, pc.ACCOUNT_REL):
        target = dest.joinpath(*rel)
        target.mkdir(parents=True)
        for path in ROOT.joinpath(*rel).glob(pc.CONFIG_GLOB):
            shutil.copy2(path, target / path.name)
    return dest


# --- controls -------------------------------------------------------------------------------


def test_the_real_tree_passes_check() -> None:
    assert pc.check(ROOT) == []


def test_the_cli_check_exits_zero_on_the_real_tree() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", pc.SELF, "--check"],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / ".ci"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "8 proxy configs hold" in proc.stdout


@pytest.mark.parametrize("key", sorted(TARGETS))
def test_every_unplanted_config_carries_no_refusal(key: str) -> None:
    assert refusals(real(key), key) == []


def test_eight_targets_and_six_generated() -> None:
    assert sorted(TARGETS) == sorted(
        ["eu", "us", "asia", "edge-eu", "edge-us", "edge-asia", "bench", "dev"]
    )
    assert sorted(t.key for t in TARGETS.values() if t.generated) == sorted(
        ["eu", "us", "asia", "edge-eu", "edge-us", "edge-asia"]
    )


@pytest.mark.parametrize(
    ("key", "name", "route", "account"),
    [
        ("eu", "rediacc-proxy-eu", PROXY_EU_HOST, "rediacc-account-eu"),
        ("us", "rediacc-proxy-us", PROXY_US_HOST, "rediacc-account-us"),
        ("asia", "rediacc-proxy-asia", PROXY_ASIA_HOST, "rediacc-account-asia"),
        (
            "edge-eu",
            "edge-rediacc-proxy-eu",
            PROXY_EDGE_EU_HOST,
            "edge-rediacc-account-eu",
        ),
        (
            "edge-us",
            "edge-rediacc-proxy-us",
            PROXY_EDGE_US_HOST,
            "edge-rediacc-account-us",
        ),
        (
            "edge-asia",
            "edge-rediacc-proxy-asia",
            PROXY_EDGE_ASIA_HOST,
            "edge-rediacc-account-asia",
        ),
    ],
)
def test_generated_targets_name_their_own_worker_route_and_account(
    key: str, name: str, route: str, account: str
) -> None:
    target = TARGETS[key]
    assert target.name == name
    assert target.routes == (route,)
    assert {s for _, s, _ in target.services} == {account}
    assert dict(target.variables)["ENVIRONMENT"] == (
        "edge" if key.startswith("edge-") else "production"
    )


def test_no_proxy_config_or_template_names_executor_token() -> None:
    for path in PROXY.glob(pc.CONFIG_GLOB):
        assert pc.FORBIDDEN_TEXT not in path.read_text(encoding="utf-8"), path.name


# --- the planted refusals, one at a time ----------------------------------------------------------


def test_an_eu_account_service_in_the_us_config_is_refused() -> None:
    text = plant(
        real("us"),
        'binding = "ACCOUNT"\nservice = "rediacc-account-us"',
        'binding = "ACCOUNT"\nservice = "rediacc-account-eu"',
    )
    out = refusals(text, "us")
    assert any(
        "ACCOUNT service 'rediacc-account-eu' names eu, which is not us" in r for r in out
    ), out


def test_an_edge_service_in_a_stable_config_is_refused() -> None:
    text = plant(
        real("eu"),
        'binding = "ISSUER"\nservice = "rediacc-account-eu"',
        'binding = "ISSUER"\nservice = "edge-rediacc-account-eu"',
    )
    out = refusals(text, "eu")
    assert any(
        "ISSUER service 'edge-rediacc-account-eu' names edge, which is not eu" in r for r in out
    ), out


def test_a_proxy_eu_route_in_asia_is_refused() -> None:
    text = plant(real("asia"), f'"{PROXY_ASIA_HOST}"', f'"{PROXY_EU_HOST}"')
    out = refusals(text, "asia")
    assert any(f"route '{PROXY_EU_HOST}' names eu, which is not asia" in r for r in out), out


def test_environment_production_in_an_edge_config_is_refused() -> None:
    text = plant(real("edge-us"), 'ENVIRONMENT = "edge"', 'ENVIRONMENT = "production"')
    out = refusals(text, "edge-us")
    assert "vars.ENVIRONMENT is 'production', not 'edge'" in out, out


def test_an_otlp_eu_destination_in_us_is_refused() -> None:
    text = plant(real("us"), '"otlp-us-logs"', '"otlp-eu-logs"')
    out = refusals(text, "us")
    assert any("destination 'otlp-eu-logs' names eu, which is not us" in r for r in out), out
    assert any("observability.logs.destinations is ['otlp-eu-logs']" in r for r in out), out


def test_persist_true_is_refused() -> None:
    text = plant(real("asia"), "\npersist = false\n", "\npersist = true\n")
    out = refusals(text, "asia")
    assert any("observability.logs.persist is True" in r for r in out), out


def test_max_instances_twenty_six_is_refused() -> None:
    text = plant(real("edge-eu"), "max_instances = 25", "max_instances = 26")
    out = refusals(text, "edge-eu")
    assert "[[containers]] max_instances is 26, not 25" in out, out


def test_max_instances_on_the_durable_entry_is_refused() -> None:
    text = plant(
        real("eu"),
        'scheduling_policy = "durable_object"\n',
        'scheduling_policy = "durable_object"\nmax_instances = 25\n',
    )
    out = refusals(text, "eu")
    assert any("OrgExecutor sets max_instances" in r for r in out), out


def test_instance_type_on_the_durable_entry_is_refused() -> None:
    text = plant(
        real("bench"),
        'scheduling_policy = "durable_object"\n',
        'scheduling_policy = "durable_object"\ninstance_type = "basic"\n',
    )
    out = refusals(text, "bench")
    assert any("OrgExecutor sets instance_type" in r for r in out), out


def test_executor_cap_twenty_six_is_refused() -> None:
    text = plant(real("us"), 'EXECUTOR_CAP = "25"', 'EXECUTOR_CAP = "26"')
    out = refusals(text, "us")
    assert "vars.EXECUTOR_CAP is '26', over the ceiling of 25" in out, out


def test_executor_heavy_cap_six_is_refused() -> None:
    text = plant(real("us"), 'EXECUTOR_HEAVY_CAP = "5"', 'EXECUTOR_HEAVY_CAP = "6"')
    out = refusals(text, "us")
    assert "vars.EXECUTOR_HEAVY_CAP is '6', over the ceiling of 5" in out, out


def test_a_non_decimal_cap_is_refused() -> None:
    text = plant(real("dev"), 'EXECUTOR_CAP = "25"', "EXECUTOR_CAP = 25")
    out = refusals(text, "dev")
    assert "vars.EXECUTOR_CAP is 25, not a decimal string" in out, out


def test_executor_backend_both_is_refused() -> None:
    text = plant(real("edge-eu"), 'EXECUTOR_BACKEND = "container"', 'EXECUTOR_BACKEND = "both"')
    out = refusals(text, "edge-eu")
    assert "vars.EXECUTOR_BACKEND is 'both', not one of container/durable" in out, out


def test_executor_backend_durable_is_accepted() -> None:
    text = plant(real("eu"), 'EXECUTOR_BACKEND = "container"', 'EXECUTOR_BACKEND = "durable"')
    assert refusals(text, "eu") == []


def test_a_missing_v2_migration_is_refused() -> None:
    text = plant(
        real("eu"),
        '[[migrations]]\ntag = "v2"\nnew_sqlite_classes = ["OrgExecutor", "ExecutorCapacity"]\n',
        "",
    )
    out = refusals(text, "eu")
    assert any("[[migrations]] is" in r and "not v1, v2" in r for r in out), out


def test_a_missing_capacity_binding_is_refused() -> None:
    text = plant(
        real("asia"),
        '[[durable_objects.bindings]]\nname = "EXECUTOR_CAPACITY"\nclass_name = "ExecutorCapacity"\n',
        "",
    )
    out = refusals(text, "asia")
    assert any("[[durable_objects.bindings]] is" in r for r in out), out


def test_a_missing_durable_entry_is_refused() -> None:
    text = plant(
        real("eu"),
        '[[containers]]\nclass_name = "OrgExecutor"\nscheduling_policy = "durable_object"\n\n'
        '[containers.images.executor]\ndockerfile = "./Dockerfile"\nbuild_context = "../.."\n',
        "",
    )
    out = refusals(text, "eu")
    assert any("[[containers]] is ['ExecutorContainer']" in r for r in out), out


def test_a_wrong_durable_image_is_refused() -> None:
    text = plant(
        real("eu"), 'build_context = "../.."\n\n[[durable', 'build_context = "."\n\n[[durable'
    )
    out = refusals(text, "eu")
    assert any("OrgExecutor images is" in r for r in out), out


def test_the_one_entry_shape_after_phase_three_is_accepted() -> None:
    text = real("bench")
    legacy = text[
        text.index('[[containers]]\nclass_name = "ExecutorContainer"') : text.index(
            "# The `durable_object`"
        )
    ]
    text = text.replace(legacy, "")
    text = plant(
        text,
        '[[durable_objects.bindings]]\nname = "EXECUTOR"\nclass_name = "ExecutorContainer"\n\n',
        "",
    )
    text = plant(
        text,
        'new_sqlite_classes = ["OrgExecutor", "ExecutorCapacity"]\n',
        'new_sqlite_classes = ["OrgExecutor", "ExecutorCapacity"]\n\n[[migrations]]\ntag = "v3"\ndeleted_classes = ["ExecutorContainer"]\n',
    )
    assert refusals(text, "bench") == []


def test_an_env_table_is_refused() -> None:
    text = real("eu") + '\n[env.x]\nname = "rediacc-proxy-x"\n'
    out = refusals(text, "eu")
    assert any("[env.*] table" in r for r in out), out


def test_an_account_id_key_is_refused() -> None:
    text = 'account_id = "0123456789abcdef"\n' + real("bench")
    out = refusals(text, "bench")
    assert "top-level key 'account_id' is not one a proxy config may carry" in out, out


def test_executor_token_in_bench_is_refused() -> None:
    text = plant(real("bench"), "[vars]\n", '[vars]\nEXECUTOR_TOKEN = "rdt_x"\n')
    out = refusals(text, "bench")
    assert any("names EXECUTOR_TOKEN" in r for r in out), out
    assert "vars.EXECUTOR_TOKEN is not one a bench config may carry" in out, out


def test_a_missing_issuer_binding_is_refused() -> None:
    text = plant(real("us"), 'binding = "ISSUER"', 'binding = "OTHER"')
    out = refusals(text, "us")
    assert any("the ISSUER service binding is []" in r for r in out), out
    assert "[[services]] binding 'OTHER' is not one a us config may carry" in out, out


def test_a_wrong_entrypoint_is_refused() -> None:
    text = plant(real("eu"), 'entrypoint = "ExecutorIssuer"', 'entrypoint = "CloudflareInternal"')
    out = refusals(text, "eu")
    assert (
        "the ISSUER service binding's entrypoint is 'CloudflareInternal', not 'ExecutorIssuer'"
        in out
    ), out


def test_a_production_word_in_the_bench_name_is_refused() -> None:
    text = plant(real("bench"), 'name = "rediacc-proxy-bench"', 'name = "rediacc-proxy-bench-prod"')
    out = refusals(text, "bench")
    assert any(
        "name 'rediacc-proxy-bench-prod' names prod, which is not bench" in r for r in out
    ), out


def test_a_stale_generated_file_is_refused(tmp_path: pathlib.Path) -> None:
    root = copy_tree(tmp_path)
    assert pc.check(root) == []
    path = root.joinpath(*pc.PROXY_REL) / "wrangler.us.toml"
    path.write_text(path.read_text(encoding="utf-8") + "# hand edit\n", encoding="utf-8")
    out = pc.check(root)
    stale = (
        "workers/proxy/wrangler.us.toml is stale: it differs from what wrangler.template.toml and "
        "regions.json generate; run `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.proxy_configs`"
    )
    assert out == [stale], out


def test_generate_repairs_a_stale_file(tmp_path: pathlib.Path) -> None:
    root = copy_tree(tmp_path)
    path = root.joinpath(*pc.PROXY_REL) / "wrangler.edge-asia.toml"
    path.write_text("stale\n", encoding="utf-8")
    assert pc.write(root) == ["wrangler.edge-asia.toml"]
    assert pc.check(root) == []


def test_a_stray_wrangler_toml_is_refused(tmp_path: pathlib.Path) -> None:
    root = copy_tree(tmp_path)
    shutil.copy2(PROXY / "wrangler.eu.toml", root.joinpath(*pc.PROXY_REL) / "wrangler.toml")
    out = pc.check(root)
    assert any(r.startswith("workers/proxy/wrangler.toml is no known proxy target") for r in out), (
        out
    )


def test_an_account_config_bound_to_another_regions_proxy_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    root = copy_tree(tmp_path)
    path = root.joinpath(*pc.ACCOUNT_REL) / "wrangler.us.toml"
    path.write_text(
        plant(
            path.read_text(encoding="utf-8"),
            'service = "rediacc-proxy-us"',
            'service = "rediacc-proxy-eu"',
        ),
        encoding="utf-8",
    )
    out = pc.check(root)
    assert any(
        "workers/account/wrangler.us.toml: the EXECUTOR service binding is ['rediacc-proxy-eu']"
        in r
        for r in out
    ), out
    assert any("EXECUTOR service 'rediacc-proxy-eu' names eu, which is not us" in r for r in out), (
        out
    )


def test_a_well_known_host_disagreeing_with_regions_json_is_refused(tmp_path: pathlib.Path) -> None:
    root = copy_tree(tmp_path)
    path = root / pc.REGIONS_REL
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f'"domain": "{US_DOMAIN}"', '"domain": "usa.rediacc.com"'
        ),
        encoding="utf-8",
    )
    out = pc.check(root)
    assert any(
        f"the us production proxy host is '{PROXY_US_HOST}', not 'proxy.usa.rediacc.com'" in r
        for r in out
    ), out
