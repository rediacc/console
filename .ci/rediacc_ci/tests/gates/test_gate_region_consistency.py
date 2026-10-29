"""`check:ci-region-consistency`, driven as a process over a fixture root copied from the real tree's own inputs.

WHAT THIS ADDS TO `--selftest`. The controls plant into parsed dicts; here the entry point reads real files through `--root`, so the TOML and JSON parsing, the file discovery for all fourteen tomls, the matrix and the exit codes are proven on the bytes the tree really has. The fixture starts from a copy and is made consistent first (`_clean`), so each plant below is judged against a green run, not against whatever the real tree currently carries.
"""

import pathlib
import shutil
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

ROOT = paths.repo_root()
GATE = paths.from_root(".ci", "scripts", "quality", "check_region_consistency.py")
STEMS = ("eu", "us", "asia", "edge-eu", "edge-us", "edge-asia", "bench")
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


def test_the_real_tree_is_judged_over_all_seven_targets():
    result = _gate()
    assert result.rc in (0, 1), result.combined
    assert "7 target(s), 7 account + 7 proxy toml(s), 7 profile(s)" in result.combined
    for target in (
        "stable-eu",
        "edge-eu",
        "stable-us",
        "edge-us",
        "stable-asia",
        "edge-asia",
        "bench",
    ):
        assert "\n  %s " % target in result.out, result.out


def test_a_consistent_fixture_is_green_and_prints_its_shape(tmp_path):
    result = _gate("--root", str(_clean(tmp_path)))
    assert result.rc == 0, result.combined
    assert "consistent: 7 target(s)" in result.out
    assert "exempt bench assets.directory" in result.out, (
        "an exemption must stay visible on a green run"
    )


PLANTS = [
    (
        "regions",
        "regions.json",
        '"edgeBackupR2": { "name": "edge-rediacc-backups-us" }',
        '"edgeBackupR2": { "name": "edge-rediacc-backup-us" }',
        "edge-us     regions",
    ),
    (
        "account-bucket",
        "workers/account/wrangler.asia.toml",
        'bucket_name = "rediacc-configs-asia"',
        'bucket_name = "rediacc-configs-us"',
        "stable-asia account",
    ),
    (
        "account-jurisdiction",
        "workers/account/wrangler.edge-eu.toml",
        'bucket_name = "edge-rediacc-backups-eu"\njurisdiction = "eu"',
        'bucket_name = "edge-rediacc-backups-eu"',
        "edge-eu     account",
    ),
    (
        "account-executor",
        "workers/account/wrangler.edge-us.toml",
        'service = "edge-rediacc-proxy-us"',
        'service = "rediacc-proxy-us"',
        "edge-us     account",
    ),
    (
        "account-shape",
        "workers/account/wrangler.us.toml",
        'crons = ["0 3 * * *"]',
        'crons = ["0 4 * * *"]',
        "stable-us   account",
    ),
    (
        "proxy",
        "workers/proxy/wrangler.edge-asia.toml",
        'service = "edge-rediacc-account-asia"\nentrypoint = "ExecutorIssuer"',
        'service = "rediacc-account-asia"\nentrypoint = "ExecutorIssuer"',
        "edge-asia   proxy",
    ),
    # The last name of the us-edge profile is the one line carrying it without a trailing comma (mirror-config-store's copy has one).
    (
        "profile",
        ".ci/config/secret-supply.json",
        '        "ACCOUNT_CONFIG_SERVER_KEY_US_EDGE"\n',
        '        "ACCOUNT_CONFIG_SERVER_KEY_EU_EDGE"\n',
        "edge-us     profile",
    ),
    (
        "bench-jwt-aliased",
        ".ci/config/secret-supply.json",
        '        "ACCOUNT_JWT_SECRET",\n        "ACCOUNT_CONFIG_SERVER_KEY_BENCH',
        '        "ACCOUNT_JWT_SECRET_DEV > ACCOUNT_JWT_SECRET",\n        "ACCOUNT_CONFIG_SERVER_KEY_BENCH',
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
    (root / "workers/proxy/wrangler.edge-us.toml").unlink()
    result = _gate("--root", str(root))
    assert result.rc == 2, result.combined
    assert "NO VERDICT" in result.err
    assert "wrangler.edge-us.toml" in result.err


def test_live_without_a_credential_is_unchecked_not_green(tmp_path, monkeypatch):
    for name in ("CLOUDFLARE_API_TOKEN", "CF_GLOBAL_API_KEY", "CF_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    result = _gate("--root", str(_clean(tmp_path)), "--live")
    assert result.rc == 2, result.combined
    assert "UNCHECKED r2" in result.err
    assert "consistent" not in result.out
