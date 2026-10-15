"""`check:ci-backup-credential-isolation`, driven as a process over a fixture root built from the real tree's own files.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. The controls prove each rule as a function on small fixtures. Here the entry point runs end to end with `--root` pointing at a scratch copy of the five real inputs (deploy_bench.py, secret-supply.json, regions.json, wrangler.bench.toml, cd-deploy-account.yml) plus a rotation-scopes file, so the corpus discovery, the census, the SKIP for an absent scopes file and the exit codes are proven on the shapes the tree really has. One plant per rule must turn the run red.
"""

import json
import pathlib
import shutil
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

ROOT = paths.repo_root()
GATE = paths.from_root(".ci", "scripts", "quality", "check_backup_credential_isolation.py")
COPIED = (
    ".ci/rediacc_ci/ops/deploy_bench.py",
    ".ci/config/secret-supply.json",
    "regions.json",
    "workers/account/wrangler.bench.toml",
    ".github/workflows/cd-deploy-account.yml",
)
SCOPES_REL = "private/account/scripts/rotation/r2-backup-tokens.json"
ITEM_PERMS = ["Workers R2 Storage Bucket Item Read", "Workers R2 Storage Bucket Item Write"]


def _scopes() -> dict:
    regions = json.loads((ROOT / "regions.json").read_text(encoding="utf-8"))["regions"]

    def buckets(field: str) -> list[dict]:
        out = []
        for r in regions:
            entry = {"name": r[field]["name"]}
            if r.get("r2Jurisdiction"):
                entry["jurisdiction"] = r["r2Jurisdiction"]
            out.append(entry)
        return out

    def names(env: str) -> list[str]:
        return [
            "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_" + env,
            "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_" + env,
        ]

    # The shape B1 writes (private/account/scripts/rotation/r2-backup-tokens.json): one shared permission list and a `tokens` table with camelCase name lists.
    return {
        "$comment": "fixture",
        "permissions": ITEM_PERMS,
        "tokens": {
            "cf-r2-backup-stable": {
                "environment": "stable",
                "buckets": buckets("backupR2"),
                "bitwardenSecretNames": names("STABLE"),
            },
            "cf-r2-backup-edge": {
                "environment": "edge",
                "buckets": buckets("edgeBackupR2"),
                "bitwardenSecretNames": names("EDGE"),
            },
            "cf-r2-backup-bench": {
                "environment": "bench",
                "buckets": [{"name": "rediacc-backups-bench"}],
                "bitwardenSecretNames": names("BENCH"),
            },
        },
    }


def _root(tmp_path: pathlib.Path, *, scopes: bool = True) -> pathlib.Path:
    root = tmp_path / "root"
    for rel in COPIED:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, root / rel)
    (root / "private" / "account").mkdir(parents=True)
    (root / "private" / "account" / "README.md").write_text("fixture\n", encoding="utf-8")
    if scopes:
        (root / SCOPES_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / SCOPES_REL).write_text(json.dumps(_scopes(), indent=2), encoding="utf-8")
    return root


def _gate(root: pathlib.Path) -> harness.RunResult:
    return harness.run([sys.executable, str(GATE), "--root", str(root)], cwd=ROOT)


def _plant(root: pathlib.Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, "the plant's needle is not in %s; the fixture drifted" % rel
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_selftest_passes():
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=ROOT)
    assert result.rc == 0, result.combined
    assert "control(s) ran" in result.out


def test_the_real_tree_is_clean():
    result = harness.run([sys.executable, str(GATE)], cwd=ROOT)
    assert result.rc == 0, result.combined
    assert "1 stable fetches, 1 edge fetches" in result.err


def test_a_fixture_of_the_real_inputs_is_clean_and_compares_the_scopes(tmp_path):
    result = _gate(_root(tmp_path))
    assert result.rc == 0, result.combined
    assert "3 token scopes" in result.err
    assert "SKIP" not in result.combined


def test_an_absent_scopes_file_is_a_loud_skip_not_a_pass(tmp_path):
    result = _gate(_root(tmp_path, scopes=False))
    assert result.rc == 0, result.combined
    assert "rotation-scopes: SKIP" in result.err
    assert "NOT compared" in result.err
    assert "1 rule(s) SKIPPED" in result.err


PLANTS = [
    (
        "bench-no-fallback",
        ".ci/rediacc_ci/ops/deploy_bench.py",
        'endpoint = os.environ.get("ACCOUNT_BACKUP_S3_ENDPOINT") or ""',
        'endpoint = os.environ.get("ACCOUNT_BACKUP_S3_ENDPOINT") or os.environ.get("CLOUDFLARE_R2_ENDPOINT") or ""',
    ),
    (
        "profile-source",
        ".ci/config/secret-supply.json",
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"',
        '"CLOUDFLARE_R2_ACCESS_KEY_ID > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"',
    ),
    (
        "profile-pair",
        ".ci/config/secret-supply.json",
        '"ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_STABLE > ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"',
        '"ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_EDGE > ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"',
    ),
    (
        "workflow-pair",
        ".github/workflows/cd-deploy-account.yml",
        "if: inputs.target != 'stable'",
        "if: inputs.target == 'stable'",
    ),
    (
        "workflow-source",
        ".github/workflows/cd-deploy-account.yml",
        "ACCOUNT_BACKUP_S3_ENDPOINT: ${{ env.BWS_ACCOUNT_BACKUP_S3_ENDPOINT }}",
        "ACCOUNT_BACKUP_S3_ENDPOINT: ${{ env.BWS_CLOUDFLARE_R2_ENDPOINT }}",
    ),
    (
        "rotation-scopes",
        SCOPES_REL,
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH"',
        '"ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE"',
    ),
]


@pytest.mark.parametrize(("rule", "rel", "old", "new"), PLANTS, ids=[p[0] for p in PLANTS])
def test_one_plant_per_rule_turns_the_run_red(tmp_path, rule, rel, old, new):
    root = _root(tmp_path)
    _plant(root, rel, old, new)
    result = _gate(root)
    assert result.rc == 1, result.combined
    assert "✗ %s " % rule in result.err or "%s  " % rule in result.err, result.err


def test_no_workflow_file_cannot_run(tmp_path):
    root = _root(tmp_path)
    (root / ".github" / "workflows" / "cd-deploy-account.yml").unlink()
    result = _gate(root)
    assert result.rc == 2, result.combined
    assert "CANNOT RUN" in result.err
