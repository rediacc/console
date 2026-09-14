"""`rediacc_ci.proxies.license_e2e` against its bash twin
`.ci/scripts/test/proxies/proxy-license-e2e.sh`, already wired as the registered
gate `check:ci-proxy-license-e2e` (`package.json:387`,
`scripts/ci-runner/manifest.ts:7435-7444`, `kind: 'local-only'` since CI runs
the identical subject at `.github/workflows/ct-tests.yml:1848`, a workflow
outside `paritySurface()`). The bash proxy is what the gate calls, unchanged
by this port -- same as every other proxy in this package, only the shim is
ported here, not the call site.

UNLIKE EVERY OTHER PROXY IN THIS PACKAGE, there is no synthetic fixture here:
both sides run the REAL subject, which installs license fixtures under
`/var/lib/rediacc/license` via `sudo -n` and takes ~16-40s. Only ONE test
drives it (`test_real_tree_agrees_byte_for_byte`), same discipline as
`test_proxies_ensure_nfpm.py`'s single network-touching case -- running the
real battery twice per CI run is already the cost this proxy accepts, and a
second real invocation buys nothing a fixture-driven test cannot check more
cheaply. The counting logic (`_count`) is covered separately, against
synthetic text, with no subprocess at all.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-license-e2e.observations.jsonl`, recorded
against a disposable scratch git repo built OUTSIDE this checkout (this
repo's own working tree is not clean; `shadow-gate.ts --record` refuses a
dirty tree).
"""

from __future__ import annotations

import os
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.proxies import license_e2e

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/test/proxies/proxy-license-e2e.sh"
PORT_MODULE = "rediacc_ci.proxies.license_e2e"
TWIN = ROOT / TWIN_REL


def _real_tree_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def test_selftest_is_byte_identical() -> None:
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN), "--selftest"], timeout=180, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, "--selftest"], timeout=180, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_real_tree_agrees_byte_for_byte() -> None:
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN)], timeout=120, check=False, **kwargs
    )
    if old.returncode == 77:
        pytest.skip(f"the twin reports cannot-run here: {old.stderr.strip()[:200]}")
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE], timeout=120, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "5 check(s) passed, 6 requirement(s) present" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


# ---------------------------------------------------------------------------
# The pure counting helper, against synthetic text -- no subprocess at all
# ---------------------------------------------------------------------------


def test_count_matches_each_control_class_independently() -> None:
    both = (
        "[enforcing] scenario A PASS\n"
        "[enforcing] scenario B PASS\n"
        "[enforcing] scenario C FAIL\n"
        "[nolicense] scenario D FAIL\n"
        "[nolicense] scenario E FAIL\n"
        "[wrong-key] scenario F FAIL\n"
        "unrelated chatter line"
    )
    assert license_e2e._count(license_e2e._ENFORCING_PASS_RE, both) == 2
    assert license_e2e._count(license_e2e._ENFORCING_FAIL_RE, both) == 1
    assert license_e2e._count(license_e2e._NOLICENSE_FAIL_RE, both) == 2
    assert license_e2e._count(license_e2e._WRONGKEY_FAIL_RE, both) == 1


def test_count_is_zero_on_text_with_no_matches() -> None:
    assert license_e2e._count(license_e2e._ENFORCING_PASS_RE, "nothing here") == 0
    assert license_e2e._count(license_e2e._NOLICENSE_FAIL_RE, "") == 0
