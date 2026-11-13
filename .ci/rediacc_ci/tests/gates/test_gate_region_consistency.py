"""`check:ci-region-consistency`, driven as a process over a fixture root copied from the real tree's own inputs.

WHAT THIS ADDS TO `--selftest`. The controls plant into parsed dicts; here the entry point reads real files through `--root`, so the TOML and JSON parsing, the file discovery for all eight tomls, the matrix and the exit codes are proven on the bytes the tree really has. The fixture starts from a copy and is made consistent first (`_clean`), so each plant below is judged against a green run, not against whatever the real tree currently carries.
"""

import copy
import json
import pathlib
import shutil
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import region_consistency_offline as rco
from rediacc_ci.tests.gates import harness

ROOT = paths.repo_root()
GATE = paths.from_root(".ci", "scripts", "quality", "check_region_consistency.py")
STEMS = ("eu", "us", "asia", "bench", "bench-us", "bench-asia")
COPIED = (
    "regions.json",
    ".ci/config/secret-supply.json",
    ".ci/rediacc_ci/ops/deploy_bench.py",
    *("workers/account/wrangler.%s.toml" % s for s in STEMS),
    *("workers/proxy/wrangler.%s.toml" % s for s in STEMS),
)
BENCH_TOML = "workers/account/wrangler.bench.toml"


def _plant(root: pathlib.Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        "the plant's needle is not exactly once in %s; the fixture drifted" % rel
    )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _root(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "root"
    for rel in COPIED:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, root / rel)
    return root


def _clean(tmp_path: pathlib.Path) -> pathlib.Path:
    """The copy of the real tree, unaltered: it is consistent since bench's invocation logs were aligned (581206c7b)."""
    return _root(tmp_path)


def _gate(*args: str) -> harness.RunResult:
    return harness.run([sys.executable, str(GATE), *args], cwd=ROOT)


def test_selftest_passes():
    result = _gate("--selftest")
    assert result.rc == 0, result.combined
    assert "control(s) passed" in result.out


def test_the_real_tree_is_judged_over_all_four_targets():
    result = _gate()
    assert result.rc in (0, 1), result.combined
    assert "4 target(s), 4 account + 4 proxy toml(s), 4 profile(s)" in result.combined
    for target in ("eu", "us", "asia", "bench"):
        assert "\n  %s " % target in result.out, result.out


def test_a_consistent_fixture_is_green_and_prints_its_shape(tmp_path):
    result = _gate("--root", str(_clean(tmp_path)))
    assert result.rc == 0, result.combined
    assert "consistent: 4 target(s)" in result.out
    assert "exempt bench assets.directory" in result.out, (
        "an exemption must stay visible on a green run"
    )


PLANTS = [
    (
        "regions",
        "regions.json",
        '"backupR2": { "name": "backups-us" }',
        '"backupR2": { "name": "backup-us" }',
        "us          regions",
    ),
    (
        "account-bucket",
        "workers/account/wrangler.asia.toml",
        'bucket_name = "configs-asia"',
        'bucket_name = "configs-us"',
        "asia        account",
    ),
    (
        "account-jurisdiction",
        "workers/account/wrangler.eu.toml",
        'bucket_name = "backups-eu"\njurisdiction = "eu"',
        'bucket_name = "backups-eu"',
        "eu          account",
    ),
    (
        "account-executor",
        "workers/account/wrangler.us.toml",
        'service = "proxy-us"',
        'service = "proxy-eu"',
        "us          account",
    ),
    (
        "account-shape",
        "workers/account/wrangler.us.toml",
        'crons = ["17 * * * *", "0 3 * * *"]',
        'crons = ["17 * * * *", "0 4 * * *"]',
        "us          account",
    ),
    (
        "proxy",
        "workers/proxy/wrangler.asia.toml",
        'service = "account-asia"\nentrypoint = "ExecutorIssuer"',
        'service = "account-eu"\nentrypoint = "ExecutorIssuer"',
        "asia        proxy",
    ),
    # The us profile is the one place its backup KEK sits directly above FREE_LICENSE_HMAC_KEY (its vault entry is the _EDGE one, bound under the _STABLE local name).
    (
        "profile",
        ".ci/config/secret-supply.json",
        '        "ACCOUNT_BACKUP_STORE_KEK_US_EDGE > ACCOUNT_BACKUP_STORE_KEK_US_STABLE",\n        "FREE_LICENSE_HMAC_KEY",\n',
        '        "ACCOUNT_BACKUP_STORE_KEK_EU_STABLE",\n        "FREE_LICENSE_HMAC_KEY",\n',
        "us          profile",
    ),
    (
        "bench-jwt-aliased",
        ".ci/config/secret-supply.json",
        '        "ACCOUNT_JWT_SECRET",\n        "ACCOUNT_CONFIG_SERVER_KEY_BENCH',
        '        "ACCOUNT_JWT_SECRET_DEV > ACCOUNT_JWT_SECRET",\n        "ACCOUNT_CONFIG_SERVER_KEY_BENCH',
        "bench       profile",
    ),
    (
        "bench-licence-key-bound",
        ".ci/config/secret-supply.json",
        '        "ACCOUNT_JWT_SECRET",\n        "ACCOUNT_CONFIG_SERVER_KEY_BENCH',
        '        "ACCOUNT_JWT_SECRET",\n        "ACCOUNT_ED25519_PRIVATE_KEY",\n        "ACCOUNT_CONFIG_SERVER_KEY_BENCH',
        "bench       profile",
    ),
    (
        "bench-licence-key-aliased",
        ".ci/config/secret-supply.json",
        '        "ACCOUNT_JWT_SECRET",\n        "ACCOUNT_CONFIG_SERVER_KEY_BENCH',
        '        "ACCOUNT_JWT_SECRET",\n        "ACCOUNT_ED25519_PRIVATE_KEY_DEV > ACCOUNT_ED25519_PRIVATE_KEY",\n        "ACCOUNT_CONFIG_SERVER_KEY_BENCH',
        "bench       profile",
    ),
    (
        "bench-payload",
        ".ci/rediacc_ci/ops/deploy_bench.py",
        '        "STRIPE_WEBHOOK_SECRET": "",\n',
        "",
        "bench       profile",
    ),
]


@pytest.mark.parametrize(("rule", "rel", "old", "new", "line"), PLANTS, ids=[p[0] for p in PLANTS])
def test_one_plant_per_class_turns_the_run_red(tmp_path, rule, rel, old, new, line):
    root = _clean(tmp_path)
    _plant(root, rel, old, new)
    result = _gate("--root", str(root))
    assert result.rc == 1, "plant %s: %s" % (rule, result.combined)
    assert line in result.err, "plant %s: %s" % (rule, result.err)


def test_a_missing_toml_is_no_verdict(tmp_path):
    root = _clean(tmp_path)
    (root / "workers/proxy/wrangler.us.toml").unlink()
    result = _gate("--root", str(root))
    assert result.rc == 2, result.combined
    assert "NO VERDICT" in result.err
    assert "wrangler.us.toml" in result.err


def test_live_without_a_credential_is_unchecked_not_green(tmp_path, monkeypatch):
    for name in ("CLOUDFLARE_API_TOKEN", "CF_GLOBAL_API_KEY", "CF_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    result = _gate("--root", str(_clean(tmp_path)), "--live")
    assert result.rc == 2, result.combined
    assert "UNCHECKED r2" in result.err
    assert "consistent" not in result.out


def test_the_bench_only_payload_keys_are_exempt_and_an_unknown_one_is_not():
    """594bf5b2.1: the sandbox pair is the bench-only exemption; any other payload key no regional Worker gets is a finding."""
    pushed = sorted({k for k, _var, _src in rco.pusher.KEYS})
    base = [*pushed, *rco.BENCH_ONLY_PAYLOAD]
    assert rco.BENCH_ONLY_PAYLOAD
    assert not [f for f in rco.check_profiles([], {}, base) if "pushes" in f.message]
    extra = rco.check_profiles([], {}, [*base, "ZZZ_UNKNOWN_KEY"])
    assert [f.message for f in extra if "ZZZ_UNKNOWN_KEY" in f.message]


def test_load_reads_the_other_benches_as_extra_targets():
    """The us and asia benches are not among the four targets but load() reads their tomls, so a drift in them is judged; a dropped extras list would leave the selftest green."""
    inputs, targets, _found = rco.load(ROOT)
    assert [t.id for t in targets] == ["eu", "us", "asia", "bench"]
    assert [t.id for t, _a, _p in inputs.bench_regions] == ["bench-us", "bench-asia"]
    for _t, account, proxy in inputs.bench_regions:
        assert "d1_databases" in account
        assert "containers" in proxy


def _regions_with_d1(d1):
    doc = json.loads((ROOT / rco.REGIONS_REL).read_text(encoding="utf-8"))
    doc["regions"][0]["d1"] = d1
    return doc


def test_a_d1_written_as_a_bare_string_is_a_missing_jurisdiction_key():
    """4d34bc89.2: only a dict d1 was checked for the key; a bare string passed silently."""
    _targets, found = rco.targets_from(_regions_with_d1("account-eu"))
    assert [f for f in found if "d1 carries no jurisdiction key" in f.message]


def test_a_d1_dict_with_the_key_has_no_such_finding():
    """Control: the dict form carrying `jurisdiction` raises no missing-key finding."""
    _targets, found = rco.targets_from(_regions_with_d1({"name": "x", "jurisdiction": None}))
    assert not [f for f in found if "d1 carries no jurisdiction key" in f.message]


# --- the regional benches (PLAN-multi-region-bench.md boxes W1 and W2) ---
# Control first: `test_the_real_tree_is_clean` judges the real inputs clean; each plant changes ONE thing in a deep copy and must add a finding on the named bench and class.


def _judge(inputs: rco.Inputs, targets: list[rco.Target], found: list[rco.Finding]):
    return rco.offline(inputs, targets, found)


def _loaded():
    inputs, targets, found = rco.load(ROOT)
    return inputs, targets, found


def _row(inputs: rco.Inputs, rid: str) -> dict:
    return next(r for r in inputs.regions["regions"] if r["id"] == rid)


def _extra(inputs: rco.Inputs, key: str):
    return next(e for e in inputs.bench_regions if e[0].id == key)


def _new(inputs: rco.Inputs, targets, found, mutate) -> set[tuple[str, str]]:
    base = {(f.target, f.cls) for f in _judge(inputs, targets, found)}
    inputs2 = copy.deepcopy(inputs)
    found2 = list(found)
    out = mutate(inputs2, found2) or found2
    # a regions.json plant is re-derived the way the gate does it
    return {(f.target, f.cls) for f in _judge(inputs2, targets, out)} - base


def _regions_plant(fn):
    def mutate(inputs: rco.Inputs, _found):
        fn(inputs)
        return rco.targets_from(inputs.regions)[1]

    return mutate


def test_the_real_tree_is_clean() -> None:
    inputs, targets, found = _loaded()
    assert _judge(inputs, targets, found) == []
    assert [t.id for t, _a, _p in inputs.bench_regions] == ["bench-us", "bench-asia"]


def test_the_home_bench_target_is_read_from_the_eu_bench_object() -> None:
    inputs, targets, _found = _loaded()
    bench = _row(inputs, "eu")["bench"]
    t = next(t for t in targets if t.id == "bench")
    assert (t.account_worker, t.proxy_worker, t.domain) == (
        bench["workerName"],
        bench["proxyWorkerName"],
        bench["host"],
    )
    assert t.serves == "eu"


@pytest.mark.parametrize("rid", ["us", "asia"])
def test_a_regional_account_serving_another_region_fires(rid: str) -> None:
    inputs, targets, found = _loaded()

    def mutate(i, f):
        _extra(i, "bench-" + rid)[1]["vars"]["REGION"] = "eu"
        return f

    assert ("bench-" + rid, "account") in _new(inputs, targets, found, mutate)


def test_the_us_bench_binding_the_eu_signer_fires() -> None:
    inputs, targets, found = _loaded()

    def mutate(i, f):
        for s in _extra(i, "bench-us")[1]["services"]:
            if s["binding"] == "LICENSE_SIGNER":
                s["service"] = "signer-bench-eu"
        return f

    assert ("bench-us", "account") in _new(inputs, targets, found, mutate)


def test_a_signer_prop_naming_another_region_fires() -> None:
    inputs, targets, found = _loaded()

    def mutate(i, f):
        for s in _extra(i, "bench-asia")[1]["services"]:
            if s["binding"] == "LICENSE_SIGNER":
                s["props"] = {"tier": "shared", "region": "eu"}
        return f

    assert ("bench-asia", "account") in _new(inputs, targets, found, mutate)


def test_a_queue_dataset_or_rate_limit_that_differs_from_the_object_fires() -> None:
    inputs, targets, found = _loaded()

    def queue(i, f):
        _extra(i, "bench-us")[1]["queues"]["producers"][0]["queue"] = "backup-replicate-bench"
        return f

    def dataset(i, f):
        _extra(i, "bench-us")[1]["analytics_engine_datasets"][0]["dataset"] = "telemetry_bench"
        return f

    def limit(i, f):
        _extra(i, "bench-us")[1]["ratelimits"][0]["namespace_id"] = "1104"
        return f

    for mutate in (queue, dataset, limit):
        assert ("bench-us", "account") in _new(inputs, targets, found, mutate)


def test_a_placeholder_id_on_a_deployable_bench_and_a_real_id_on_an_undeployable_one_fire() -> None:
    inputs, targets, found = _loaded()

    def deployable(i, f):
        _row(i, "us")["bench"]["deployable"] = True
        return f

    def real_id(i, f):
        _extra(i, "bench-us")[1]["d1_databases"][0]["database_id"] = (
            "11111111-2222-3333-4444-555555555555"
        )
        return f

    assert ("bench-us", "account") in _new(inputs, targets, found, deployable)
    assert ("bench-us", "account") in _new(inputs, targets, found, real_id)


def test_two_placeholders_are_not_a_shared_database_id() -> None:
    """Control: us and asia both carry TO-BE-CREATED-L1 and the real tree is clean; a real id shared with the eu bench is the finding."""
    inputs, targets, found = _loaded()
    assert not [f for f in _judge(inputs, targets, found) if "also" in f.message]

    def shared(i, f):
        eu_id = i.account["bench"]["d1_databases"][0]["database_id"]
        _extra(i, "bench-us")[1]["d1_databases"][0]["database_id"] = eu_id
        _row(i, "us")["bench"]["deployable"] = True
        return f

    new = rco.offline(_mut(inputs, shared), targets, found)
    assert any("also bench's" in f.message for f in new)


def _mut(inputs: rco.Inputs, mutate) -> rco.Inputs:
    inputs2 = copy.deepcopy(inputs)
    mutate(inputs2, [])
    return inputs2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", "bench.rediacc.cloud"),
        ("workerName", "account-bench"),
        ("queue", "backup-replicate-bench"),
        ("signerWorkerName", "signer-bench-eu"),
        ("config", "eu-bench"),
    ],
)
def test_a_us_bench_object_off_its_pattern_fires(field: str, value: str) -> None:
    inputs, targets, found = _loaded()
    new = _new(
        inputs,
        targets,
        found,
        _regions_plant(lambda i: _row(i, "us")["bench"].update({field: value})),
    )
    assert ("bench-us", "regions") in new


def test_a_us_bench_placed_away_from_production_us_fires() -> None:
    inputs, targets, found = _loaded()

    def d1_location(i):
        _row(i, "us")["bench"]["d1"]["location"] = "weur"

    def r2_hint(i):
        _row(i, "asia")["bench"]["r2Location"] = "enam"

    def jurisdiction(i):
        _row(i, "us")["bench"]["r2Jurisdiction"] = "eu"

    for plant in (d1_location, r2_hint, jurisdiction):
        new = _new(inputs, targets, found, _regions_plant(plant))
        assert ("bench-us", "regions") in new or ("bench-asia", "regions") in new


def test_a_bench_object_missing_a_key_or_sharing_a_rate_limit_fires() -> None:
    inputs, targets, found = _loaded()
    missing = _new(
        inputs, targets, found, _regions_plant(lambda i: _row(i, "us")["bench"].pop("queue"))
    )
    assert ("bench-us", "regions") in missing
    dup = _new(
        inputs,
        targets,
        found,
        _regions_plant(lambda i: _row(i, "asia")["bench"]["rateLimits"].update({"audit": "1105"})),
    )
    assert ("bench-asia", "regions") in dup


def test_the_eu_bench_is_not_held_to_production_eu_placement() -> None:
    """Control for the placement rule: the home bench carries no location hint today and is clean; only the other regions copy production."""
    inputs, targets, found = _loaded()
    assert _row(inputs, "eu")["bench"]["d1"]["location"] is None
    assert _judge(inputs, targets, found) == []
