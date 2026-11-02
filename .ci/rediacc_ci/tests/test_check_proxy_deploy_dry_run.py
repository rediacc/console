"""`check:ci-proxy-deploy-dry-run` (`.ci/scripts/quality/check_proxy_deploy_dry_run.py`): every proxy target dry-runs with fake credentials.

The gate is driven through `--entry` with a FAKE deploy_proxy script and `--root` at a tmp tree holding only a copy of regions.json, so no wrangler runs and the real tree is never touched. The unplanted run must pass first, so a red on a plant is the plant's doing. The real entry point is exercised by the gate itself on the real tree (`npm run check:ci-proxy-deploy-dry-run`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
GATE = ROOT / ".ci" / "scripts" / "quality" / "check_proxy_deploy_dry_run.py"

# The fake obeys the deploy_proxy contract the gate relies on: --target/--region/--dry-run in, a `(config: X)` line and `Dry run passed` out. FAKE_MODE plants one defect for one target.
FAKE = r"""
import os, sys
args = sys.argv[1:]
target = args[args.index("--target") + 1]
region = args[args.index("--region") + 1] if "--region" in args else "eu"
key = "bench" if target == "bench" else ("edge-" + region if target == "edge" else region)
label = target + "/" + region
mode = os.environ.get("FAKE_MODE", "")
if os.environ.get("CLOUDFLARE_API_TOKEN") == os.environ.get("REAL_SENTINEL", "never"):
    print("the real credential reached the dry run"); sys.exit(1)
if not os.environ.get("CLOUDFLARE_API_TOKEN"):
    print("no fake credential"); sys.exit(1)
if mode == "fail:" + label:
    print("wrangler: unknown key"); sys.exit(1)
if mode == "silent:" + label:
    sys.exit(0)
if mode == "wrongconfig:" + label:
    key = "eu"
print("-> Dry run: compiling (config: wrangler.%s.toml)..." % key)
print("Dry run passed. Nothing was deployed.")
"""


def _tree(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    root = tmp_path / "root"
    root.mkdir()
    shutil.copy(ROOT / "regions.json", root / "regions.json")
    entry = tmp_path / "fake_entry.py"
    entry.write_text(FAKE, encoding="utf-8")
    return root, entry


def _run(root: pathlib.Path, entry: pathlib.Path | None, **env: str) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(GATE), "--root", str(root)]
    if entry is not None:
        argv += ["--entry", str(entry)]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={**os.environ, **env},
    )


def test_the_selftest_passes_on_its_own() -> None:
    proc = subprocess.run(
        [sys.executable, str(GATE), "--selftest"], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert "FAIL" not in proc.stderr


def test_the_unplanted_run_passes_over_seven_targets(tmp_path: pathlib.Path) -> None:
    root, entry = _tree(tmp_path)
    proc = _run(root, entry)
    assert proc.returncode == 0, proc.stderr
    assert "7 target(s) compiled" in proc.stdout
    for name in ("wrangler.edge-asia.toml", "wrangler.bench.toml", "wrangler.eu.toml"):
        assert name in proc.stdout


def test_a_real_credential_in_the_caller_env_never_reaches_the_entry(
    tmp_path: pathlib.Path,
) -> None:
    root, entry = _tree(tmp_path)
    proc = _run(root, entry, CLOUDFLARE_API_TOKEN="sentinel-real", REAL_SENTINEL="sentinel-real")
    assert proc.returncode == 0, proc.stderr


def test_a_failing_target_is_a_finding(tmp_path: pathlib.Path) -> None:
    root, entry = _tree(tmp_path)
    proc = _run(root, entry, FAKE_MODE="fail:edge/us")
    assert proc.returncode == 1
    assert "edge/us: deploy_proxy --dry-run exited 1" in proc.stderr
    assert "wrangler: unknown key" in proc.stderr
    assert "stable/us:" not in proc.stderr.replace("PASS  stable/us", "")


def test_a_silent_zero_exit_is_a_finding(tmp_path: pathlib.Path) -> None:
    root, entry = _tree(tmp_path)
    proc = _run(root, entry, FAKE_MODE="silent:stable/asia")
    assert proc.returncode == 1
    assert "stable/asia: exited 0 without printing" in proc.stderr


def test_a_target_compiling_the_wrong_config_is_a_finding(tmp_path: pathlib.Path) -> None:
    root, entry = _tree(tmp_path)
    proc = _run(root, entry, FAKE_MODE="wrongconfig:edge/asia")
    assert proc.returncode == 1
    assert "edge/asia: the run did not name `(config: wrangler.edge-asia.toml)`" in proc.stderr


def test_a_new_region_is_dry_run_without_an_edit(tmp_path: pathlib.Path) -> None:
    root, entry = _tree(tmp_path)
    doc = json.loads((root / "regions.json").read_text(encoding="utf-8"))
    doc["regions"].append({**doc["regions"][0], "id": "mars"})
    (root / "regions.json").write_text(json.dumps(doc), encoding="utf-8")
    proc = _run(root, entry)
    assert proc.returncode == 0, proc.stderr
    assert "9 target(s) compiled" in proc.stdout
    assert "wrangler.edge-mars.toml" in proc.stdout


def test_a_missing_regions_json_is_no_verdict(tmp_path: pathlib.Path) -> None:
    root, entry = _tree(tmp_path)
    (root / "regions.json").unlink()
    proc = _run(root, entry)
    assert proc.returncode == 2
    assert "cannot be read" in proc.stderr


def test_a_missing_wrangler_install_is_no_verdict_with_the_fix(tmp_path: pathlib.Path) -> None:
    root, _entry = _tree(tmp_path)
    proc = _run(root, None)
    assert proc.returncode == 2
    assert "npm ci --prefix workers/proxy" in proc.stderr
