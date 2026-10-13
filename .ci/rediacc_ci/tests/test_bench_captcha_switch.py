"""Bench alone carries the captcha-off switch; no production account worker config may."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from rediacc_ci.ops import deploy_bench

ROOT = Path(__file__).resolve().parents[3]
CONFIGS = sorted((ROOT / "workers" / "account").glob("wrangler.*.toml"))
SWITCHES = ("TURNSTILE_ENABLED", "CI_MODE", "TEST_MODE")


def _vars(path: Path) -> dict:
    return tomllib.loads(path.read_text()).get("vars", {})


def test_bench_disables_turnstile():
    assert _vars(ROOT / "workers/account/wrangler.bench.toml")["TURNSTILE_ENABLED"] == "false"
    assert deploy_bench.TURNSTILE_SITEKEY == ""


def test_no_other_config_carries_a_captcha_or_test_switch():
    others = [p for p in CONFIGS if p.name != "wrangler.bench.toml"]
    assert len(others) >= 6
    for path in others:
        found = [k for k in SWITCHES if k in _vars(path)]
        assert not found, "%s sets %s" % (path.name, found)


def test_bench_does_not_enable_the_test_surface():
    assert not {"TEST_MODE", "CI_MODE"} & set(_vars(ROOT / "workers/account/wrangler.bench.toml"))


def test_deploy_secrets_never_push_the_switch():
    src = Path(deploy_bench.__file__).read_text()
    assert not re.search(r'"TURNSTILE_ENABLED"\s*:', src)
