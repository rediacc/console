"""scripts/gen/generate-third-party-licenses.ts driven over a fixture repo root.

The generator also fetches the Node.js LICENSE from GitHub, so every run preloads a stub that makes `fetch` fail at once: nothing here reaches the network, and the generator's own offline placeholder takes the Node section.
"""

from __future__ import annotations

import json
import os
import subprocess

from rediacc_ci import paths

SCRIPT = "scripts/gen/generate-third-party-licenses.ts"
CSV_REL = "private/bin/renet-go-licenses.csv"


def _generate(tmp_path, csv: str, with_renet: bool = False) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "root"
    data = root / "packages" / "cli" / "src" / "data"
    data.mkdir(parents=True)
    inventory = {
        "gplWrittenOffer": "offer",
        "components": [
            {"kind": "runtime", "name": "Node.js", "spdx": "MIT", "license": "MIT License"},
            {
                "kind": "embedded-binary",
                "name": "zot",
                "version": "2.1.23",
                "spdx": "Apache-2.0",
                "license": "Apache",
            },
        ],
    }
    (data / "third-party-credits.json").write_text(json.dumps(inventory))
    csv_path = root / CSV_REL
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text(csv)
    if with_renet:
        (root / "private" / "renet").mkdir(parents=True)
        (root / "private" / "renet" / "go.mod").write_text("module x\n")
    stub = tmp_path / "offline.mjs"
    stub.write_text("globalThis.fetch = async () => { throw new Error('offline stub'); };\n")
    env = dict(os.environ, NODE_OPTIONS="--import %s" % stub)
    out = tmp_path / "out" / "THIRD_PARTY_LICENSES"
    proc = subprocess.run(
        [
            str(paths.repo_root() / "node_modules" / ".bin" / "tsx"),
            str(paths.repo_root() / SCRIPT),
            "--repo-root",
            str(root),
            "--output",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(tmp_path),
    )
    proc.stdout = out.read_text() if out.exists() else proc.stdout
    return proc


def test_a_credit_without_a_version_prints_its_name_only(tmp_path):
    proc = _generate(tmp_path, "github.com/x/y,https://x/y,MIT\n")
    assert "undefined" not in proc.stdout.split("RENET GO DEPENDENCIES")[0]
    assert "\nNode.js\n  SPDX:    MIT" in proc.stdout


def test_a_module_that_only_shares_the_renet_prefix_stays_in_the_notice(tmp_path):
    csv = (
        "github.com/rediacc/renet,https://r,MIT\n"
        "github.com/rediacc/renet/pkg/x,https://r/x,MIT\n"
        "github.com/rediacc/renet-utils,https://r/u,Apache-2.0\n"
    )
    proc = _generate(tmp_path, csv)
    assert "github.com/rediacc/renet-utils  [Apache-2.0]" in proc.stdout
    assert "github.com/rediacc/renet  [MIT]" not in proc.stdout
    assert "github.com/rediacc/renet/pkg/x" not in proc.stdout


def test_an_empty_csv_without_the_renet_submodule_points_at_the_artifact(tmp_path):
    proc = _generate(tmp_path, "github.com/rediacc/renet,https://r,MIT\n")
    assert "go-licenses produced no rows" in proc.stdout
    assert "renet-binaries CI artifact" in proc.stdout


def test_an_empty_csv_with_the_renet_submodule_names_the_verb_only(tmp_path):
    proc = _generate(tmp_path, "github.com/rediacc/renet,https://r,MIT\n", with_renet=True)
    assert "Check the go-licenses output, then run:" in proc.stdout
    assert "renet-binaries CI artifact" not in proc.stdout
