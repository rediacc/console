"""scripts/ci-runner/path-trace.ts against a fixture repository, through the real CLI and a real strace.

PLAN-ciquick-cpu W2.1's acceptance: a fixture gate reading two files gets exactly those two plus the directory it listed, written into the manifest literal, the lock and the trace ledger. The controls run the other way: an untouched sibling stays out, a declared set is refused rather than overwritten, a red gate writes no paths, and a host without strace is refused loudly with the fix.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib

TOOL = paths.from_root("scripts", "ci-runner", "path-trace.ts")
TSX = paths.from_root("node_modules", ".bin", "tsx")
HAS_STRACE = shutil.which("strace") is not None
NO_STRACE = "strace is not installed; path-trace refuses such a host (tested below)"

MANIFEST = """export const GATES = [
  {
    id: 'g:fix',
    run: 'cat in/a.txt in/b.txt >/dev/null && ls listed >/dev/null',
    gate: true,
    leaves: ['tool.sh'],
  },
  {
    id: 'g:red',
    run: 'cat in/a.txt >/dev/null; exit 4',
    gate: true,
    leaves: ['tool.sh'],
  },
  {
    id: 'g:declared',
    run: 'cat in/a.txt >/dev/null',
    gate: true,
    paths: ['in/**'],
    pathsOrigin: 'declared',
    leaves: ['tool.sh'],
  },
  {
    id: 'g:flip',
    run: 'if [ -e flip ]; then ls . >/dev/null; fi; cat in/a.txt >/dev/null',
    gate: true,
    leaves: ['tool.sh'],
  },
];
"""


def _lock() -> list[dict[str, object]]:
    def entry(gid: str, run: str, extra: dict[str, object] | None = None) -> dict[str, object]:
        e: dict[str, object] = {"id": gid, "run": run, "gate": True}
        e.update(extra or {})
        e["leaves"] = ["tool.sh"]
        return e

    return [
        entry("g:fix", "cat in/a.txt in/b.txt >/dev/null && ls listed >/dev/null"),
        entry("g:red", "cat in/a.txt >/dev/null; exit 4"),
        entry(
            "g:declared", "cat in/a.txt >/dev/null", {"paths": ["in/**"], "pathsOrigin": "declared"}
        ),
        entry("g:flip", "if [ -e flip ]; then ls . >/dev/null; fi; cat in/a.txt >/dev/null"),
    ]


def _git(root: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def fixture_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "repo"
    files = {
        "in/a.txt": "a",
        "in/b.txt": "b",
        "in/c.txt": "untouched",
        "in/d.txt": "untouched",
        "in/e.txt": "untouched",
        "in/f.txt": "untouched",
        "listed/one.txt": "1",
        "listed/deep/two.txt": "2",
        "other/z.txt": "untouched",
        "tool.sh": "#!/bin/sh\n",
        "scripts/ci-runner/manifest.ts": MANIFEST,
        "scripts/ci-runner/gates.lock.json": json.dumps(_lock(), indent=2) + "\n",
    }
    # Enough untouched tree that three globs stay under path-trace's 30% whole-tree line.
    files.update({f"filler/f{i}.txt": "untouched" for i in range(40)})
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "fixture")
    return root


def _run(
    root: pathlib.Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(TSX), str(TOOL), "--root", str(root), *args],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        check=False,
    )


def _lock_of(root: pathlib.Path) -> dict[str, dict[str, object]]:
    return {
        e["id"]: e for e in json.loads((root / "scripts/ci-runner/gates.lock.json").read_text())
    }


@pytest.mark.skipif(not HAS_STRACE, reason=NO_STRACE)
def test_two_reads_and_one_listing_become_exactly_three_globs(fixture_repo: pathlib.Path) -> None:
    res = _run(fixture_repo, "--gate", "g:fix", "--write")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "g:fix\tin/a.txt in/b.txt listed/**", res.stderr
    lock = _lock_of(fixture_repo)
    assert lock["g:fix"]["paths"] == ["in/a.txt", "in/b.txt", "listed/**"]
    assert lock["g:fix"]["pathsOrigin"] == "traced"
    assert list(lock["g:fix"]) == ["id", "run", "gate", "paths", "pathsOrigin", "leaves"]
    manifest = (fixture_repo / "scripts/ci-runner/manifest.ts").read_text()
    assert (
        "    paths: ['in/a.txt', 'in/b.txt', 'listed/**'],\n    pathsOrigin: 'traced',\n    leaves:"
        in manifest
    )
    ledger = (fixture_repo / "scripts/ci-runner/trace-ledger.ts").read_text()
    assert "'g:fix': {" in ledger
    assert "verdict: 'paths'," in ledger


@pytest.mark.skipif(not HAS_STRACE, reason=NO_STRACE)
def test_untouched_siblings_stay_out(fixture_repo: pathlib.Path) -> None:
    res = _run(fixture_repo, "--gate", "g:fix")
    assert res.returncode == 0, res.stderr
    line = res.stdout.strip()
    assert line.startswith("g:fix\t"), line
    for absent in ("in/c.txt", "other/", "in/**", "tool.sh"):
        assert absent not in line, line
    # No --write: nothing on disk moved.
    assert not (fixture_repo / "scripts/ci-runner/trace-ledger.ts").exists()


@pytest.mark.skipif(not HAS_STRACE, reason=NO_STRACE)
def test_a_red_gate_writes_no_paths_and_records_why(fixture_repo: pathlib.Path) -> None:
    res = _run(fixture_repo, "--gate", "g:red", "--write")
    assert res.returncode == 1
    assert "exited 4 under the trace" in res.stderr
    assert "paths" not in _lock_of(fixture_repo)["g:red"]
    ledger = (fixture_repo / "scripts/ci-runner/trace-ledger.ts").read_text()
    assert "verdict: 'whole-tree'," in ledger
    assert "exited 4" in ledger


@pytest.mark.skipif(not HAS_STRACE, reason=NO_STRACE)
def test_a_declared_set_is_refused_not_overwritten(fixture_repo: pathlib.Path) -> None:
    before = (fixture_repo / "scripts/ci-runner/manifest.ts").read_text()
    res = _run(fixture_repo, "--gate", "g:declared", "--write")
    assert res.returncode != 0
    assert "declared" in res.stderr
    assert (fixture_repo / "scripts/ci-runner/manifest.ts").read_text() == before


@pytest.mark.skipif(not HAS_STRACE, reason=NO_STRACE)
def test_a_whole_tree_retrace_removes_the_earlier_traced_paths(fixture_repo: pathlib.Path) -> None:
    manifest = fixture_repo / "scripts/ci-runner/manifest.ts"
    first = _run(fixture_repo, "--gate", "g:flip", "--write")
    assert first.returncode == 0, first.stderr
    assert _lock_of(fixture_repo)["g:flip"]["paths"] == ["in/a.txt"]
    declared_before = manifest.read_text().split("id: 'g:declared',")[1].split("  },")[0]
    # The gate now lists the repository root, so its re-trace is whole-tree.
    (fixture_repo / "flip").write_text("")
    second = _run(fixture_repo, "--gate", "g:flip", "--write")
    assert second.returncode == 0, second.stderr
    assert "traced paths are removed" in second.stderr
    flip = _lock_of(fixture_repo)["g:flip"]
    assert "paths" not in flip
    assert "pathsOrigin" not in flip
    flip_text = manifest.read_text().split("id: 'g:flip',")[1].split("  },")[0]
    assert "paths" not in flip_text
    # Control: the declared gate's entry is untouched in both files.
    assert manifest.read_text().split("id: 'g:declared',")[1].split("  },")[0] == declared_before
    assert _lock_of(fixture_repo)["g:declared"]["pathsOrigin"] == "declared"
    ledger = (fixture_repo / "scripts/ci-runner/trace-ledger.ts").read_text()
    assert "lists the repository root" in ledger


def test_a_host_without_strace_is_refused_with_the_fix(
    fixture_repo: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    sealed = tmp_path / "bin"
    sealed.mkdir()
    for name in ("node", "git", "bash", "sh", "env"):
        real = shutil.which(name)
        assert real is not None, name
        (sealed / name).symlink_to(real)
    env = {k: v for k, v in os.environ.items() if k != "PATH"}
    env["PATH"] = str(sealed)
    res = _run(fixture_repo, "--gate", "g:fix", env=env)
    assert res.returncode == 1
    assert "strace is not installed" in res.stderr
    assert "apt-get install -y strace" in res.stderr
