"""`check:ci-bws-pr-path` in both directions: each rule's planted fixture turns it red, the fixed fixture and the real tree stay green.

The module's selftest proves the evaluator and the rules on in-memory fixtures. This file adds the real tree: the CLI exits 0 on it, a copy of the real `.github/workflows` with one release-only fetch planted into a PR-reachable job exits red naming rule (i), and the shrink-only baseline refuses to absorb a new finding while it drains a fixed one.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import bws_pr_path as gate

if TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
# The deploy-preview fetch block, a job reachable on every same-repo pull request.
PREVIEW_FETCH_LINE = "            AWS_SES_CONFIGURATION_SET > BWS_AWS_SES_CONFIGURATION_SET\n"
PLANTED_NAME = "STRIPE_SECRET_KEY"


def _cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / ".ci")
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.quality.bws_pr_path", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _real_copy(tmp: pathlib.Path) -> pathlib.Path:
    """A scratch root holding a copy of the real workflows, so chain labels and baseline ids match the tree's."""
    shutil.copytree(ROOT / ".github" / "workflows", tmp / ".github" / "workflows")
    return tmp


def _evaluate_copy(tmp: pathlib.Path, config: pathlib.Path | None = None) -> gate.Outcome:
    return gate.evaluate_tree(
        tmp,
        config_path=config or ROOT / gate.CONFIG_REL,
        map_path=ROOT / gate.MAP_REL,
    )


def test_selftest_passes() -> None:
    assert gate.selftest() is False


def test_fixed_fixture_is_green(tmp_path: pathlib.Path) -> None:
    res = gate.run_fixture(tmp_path, gate.FIXED_CI, gate.FIXED_STAGE, gate.FIXTURE_CONFIG)
    assert res.rc == 0, res.stderr
    assert "1 PR root(s)" in res.stdout[0]


@pytest.mark.parametrize("rule", ["i", "ii", "iii"])
def test_each_plant_is_red_and_names_only_its_rule(tmp_path: pathlib.Path, rule: str) -> None:
    ci, stage, cfg = gate.plants()[rule]
    res = gate.run_fixture(tmp_path, ci, stage, cfg)
    assert res.rc == 1, res.stdout + res.stderr
    assert gate.fired_rules(res.stderr) == {rule}, res.stderr


def test_cli_is_green_on_the_real_tree() -> None:
    r = _cli()
    assert r.returncode == 0, r.stdout + r.stderr
    line = next(ln for ln in r.stdout.splitlines() if ln.startswith("✓ bws pr path:"))
    assert "none new, none fixed" in line
    assert "reachable job(s)" in line


def test_cli_selftest_flag_is_green() -> None:
    r = _cli("--selftest")
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_release_fetch_planted_into_the_real_preview_job_is_red(tmp_path: pathlib.Path) -> None:
    root = _real_copy(tmp_path)
    clean = _evaluate_copy(root)
    assert clean.rc == 0, clean.stderr
    ci = root / ".github" / "workflows" / "ci.yml"
    text = ci.read_text(encoding="utf-8")
    assert text.count(PREVIEW_FETCH_LINE) == 1, "the plant site moved; re-point PREVIEW_FETCH_LINE"
    ci.write_text(
        text.replace(
            PREVIEW_FETCH_LINE,
            PREVIEW_FETCH_LINE + "            %s > BWS_%s\n" % (PLANTED_NAME, PLANTED_NAME),
        ),
        encoding="utf-8",
    )
    res = _evaluate_copy(root)
    assert res.rc == 1
    assert gate.fired_rules(res.stderr) == {"i"}, res.stderr
    assert PLANTED_NAME in "\n".join(res.stderr)
    assert "ci.yml:deploy-preview" in "\n".join(res.stderr)


def test_an_id_token_grant_planted_into_the_real_preview_job_is_red(tmp_path: pathlib.Path) -> None:
    root = _real_copy(tmp_path)
    ci = root / ".github" / "workflows" / "ci.yml"
    text = ci.read_text(encoding="utf-8")
    anchor = "  deploy-preview:\n"
    head, tail = text.split(anchor, 1)
    tail = tail.replace(
        "    permissions:\n      contents: read\n",
        "    permissions:\n      contents: read\n      id-token: write\n",
        1,
    )
    ci.write_text(head + anchor + tail, encoding="utf-8")
    res = _evaluate_copy(root)
    assert res.rc == 1
    assert gate.fired_rules(res.stderr) == {"iii"}, res.stderr


def _scratch_config(tmp: pathlib.Path) -> pathlib.Path:
    path = tmp / "bws-pr-path.json"
    shutil.copyfile(ROOT / gate.CONFIG_REL, path)
    return path


def test_write_baseline_drains_a_fixed_finding_and_adds_nothing(tmp_path: pathlib.Path) -> None:
    root = _real_copy(tmp_path / "tree")
    cfg = _scratch_config(tmp_path)
    before = json.loads(cfg.read_text(encoding="utf-8"))["baseline"]["ids"]
    stage = root / ".github" / "workflows" / "cd-stage.yml"
    text = stage.read_text(encoding="utf-8")
    fetch = "      - name: Fetch the step-scoped signing key(s) for the next step only\n        uses: ./.github/actions/bws-secrets\n"
    assert text.count(fetch) == 1, "the plant site moved; re-point the cd-stage fetch anchor"
    guarded = text.replace(
        fetch,
        fetch.replace("        uses:", "        if: inputs.signing == 'release'\n        uses:"),
    )
    guarded = guarded.replace(
        "        if: inputs.channel != ''\n        uses: ./.github/actions/bws-secrets",
        "        if: inputs.channel != '' && inputs.signing == 'release'\n        uses: ./.github/actions/bws-secrets",
    )
    stage.write_text(guarded, encoding="utf-8")
    red = _evaluate_copy(root, cfg)
    assert red.rc == 1, red.stderr
    assert "--write-baseline" in "\n".join(red.stderr), red.stderr
    rc = gate.write_baseline(root, config_path=cfg, map_path=ROOT / gate.MAP_REL)
    assert rc == 0
    after = json.loads(cfg.read_text(encoding="utf-8"))["baseline"]["ids"]
    assert set(after) < set(before)
    assert not set(after) - set(before), "a drain added an id"
    assert _evaluate_copy(root, cfg).rc == 0


def test_write_baseline_refuses_while_a_new_finding_exists(tmp_path: pathlib.Path) -> None:
    root = _real_copy(tmp_path / "tree")
    cfg = _scratch_config(tmp_path)
    before = cfg.read_text(encoding="utf-8")
    ci = root / ".github" / "workflows" / "ci.yml"
    ci.write_text(
        ci.read_text(encoding="utf-8").replace(
            PREVIEW_FETCH_LINE,
            PREVIEW_FETCH_LINE + "            %s > BWS_%s\n" % (PLANTED_NAME, PLANTED_NAME),
        ),
        encoding="utf-8",
    )
    rc = gate.write_baseline(root, config_path=cfg, map_path=ROOT / gate.MAP_REL)
    assert rc == 1
    assert cfg.read_text(encoding="utf-8") == before


def test_every_store_name_is_classed_and_the_release_reasons_carry_blocker() -> None:
    doc = json.loads((ROOT / gate.CONFIG_REL).read_text(encoding="utf-8"))
    mapped = set(json.loads((ROOT / gate.MAP_REL).read_text(encoding="utf-8"))["secrets"])
    assert set(doc["names"]) == mapped
    for name, rec in doc["names"].items():
        assert rec["class"] in gate.CLASSES, name
        if rec["class"] == gate.RELEASE_ONLY:
            assert rec["reason"].startswith("BLOCKER:"), name


def test_the_signing_key_is_release_only() -> None:
    doc = json.loads((ROOT / gate.CONFIG_REL).read_text(encoding="utf-8"))
    for name in ("RELEASE_GPG_PRIVATE_KEY", "ACCOUNT_ED25519_PRIVATE_KEY", "CLOUDFLARE_API_TOKEN"):
        assert doc["names"][name]["class"] == gate.RELEASE_ONLY
