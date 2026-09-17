"""`rediacc_ci.proxies.license_e2e` against its bash twin
`.ci/scripts/test/proxies/proxy-license-e2e.sh`, already wired as the registered gate `check:ci-proxy-license-e2e` (`package.json:387`, `scripts/ci-runner/manifest.ts:7435-7444`, `kind: 'local-only'` since CI runs the identical subject at `.github/workflows/ct-tests.yml:1848`, a workflow outside `paritySurface()`). The bash proxy is what the gate calls, unchanged by this port --
same as every other proxy in this package, only the shim is ported here, not the call site.

UNLIKE EVERY OTHER PROXY IN THIS PACKAGE, there is no synthetic fixture here: both sides run the REAL subject, which installs license fixtures under `/var/lib/rediacc/license` via `sudo -n` and takes ~16-40s. Only ONE test drives it (`test_real_tree_agrees_byte_for_byte`), same discipline as `test_proxies_ensure_nfpm.py`'s single network-touching case -- running the real battery
twice per CI run is already the cost this proxy accepts, and a second real invocation buys nothing a fixture-driven test cannot check more cheaply. The counting logic (`_count`) is covered separately, against synthetic text, with no subprocess at all.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-license-e2e.observations.jsonl`, recorded
against a disposable scratch git repo built OUTSIDE this checkout (this repo's own working tree is not clean; `shadow-gate.ts --record` refuses a dirty tree).
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


#: The real-tree battery's budget. 120 -> 600 on 2026-09-15, on two consecutive
#: CI timeouts and a measurement, not on one red and a shrug.
#:
#: WHAT THE SUBJECT ACTUALLY DOES: three full runs of the renet licensing battery
#: -- an enforcing binary plus two deliberately broken controls that must fail.
#: That is real work, not a poll, so a timeout here is a budget question rather
#: than evidence of a wedge.
#:
#: THE EVIDENCE IT IS CONTENTION AND NOT A HANG, which is the distinction that
#: decides whether widening is a fix or a cover-up:
#:   - it PASSED in run 34970782616, when the suite took 1039.93s;
#:   - it timed out in 35009582358 AND 35015545136, after the suite grew to
#:     ~1250s because tests that used to fail fast now do real work;
#:   - the captured stdout shows it PROGRESSING, not stalled at startup --
#:     `toolchain complete, 6 requirement(s) satisfied` before the kill;
#:   - measured here on an idle machine: **33s**, not the 15.8s this proxy's own
#:     header still claims. So 120s was only ~3.6x the real cost, which is thin
#:     for a runner executing a 20-minute parallel suite across xdist workers.
#:
#: 600 is ~18x the measured cost: generous enough that contention cannot reach
#: it, bounded enough that a genuine hang -- which runs forever -- still dies
#: here with a named timeout rather than taking the job's own ceiling and
#: reporting nothing. If this EVER fires again, that is a wedge, not load.
#:
#: The `--selftest` budget above is deliberately left at 180s: it has never
#: fired, and widening a timer that is not failing buys nothing.
REAL_TREE_TIMEOUT_S = 600


def test_real_tree_agrees_byte_for_byte() -> None:
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN)], timeout=REAL_TREE_TIMEOUT_S, check=False, **kwargs
    )
    if old.returncode == 77:
        pytest.skip(f"the twin reports cannot-run here: {old.stderr.strip()[:200]}")
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE], timeout=REAL_TREE_TIMEOUT_S, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "5 check(s) passed, 6 requirement(s) present" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


# --------------------------------------------------------------------------- The pure counting helper, against synthetic text -- no subprocess at all ---------------------------------------------------------------------------


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
