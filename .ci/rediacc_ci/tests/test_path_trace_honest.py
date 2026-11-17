"""scripts/ci-runner/trace-honest.ts against a fixture repository, through the real CLI.

PLAN-ciquick-cpu W3.1's acceptance: the undeclared-read fixture fails both the trace mode and the sparse mode, and the declared fixture passes both. The anti-vacuity controls run beside it: a lock with no paths-bearing gate is a failure, a quick run whose push base cannot resolve is a failure, and a quick run that touches nothing says how many candidates it saw.
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

TOOL = paths.from_root("scripts", "ci-runner", "trace-honest.ts")
TSX = paths.from_root("node_modules", ".bin", "tsx")
HAS_STRACE = shutil.which("strace") is not None
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def _gate(gid: str, run: str, gate_paths: list[str] | None) -> dict[str, object]:
    e: dict[str, object] = {"id": gid, "run": run, "gate": True}
    if gate_paths is not None:
        e["paths"] = gate_paths
        e["pathsOrigin"] = "traced"
    e["leaves"] = ["tool.sh"]
    return e


def _repo(root: pathlib.Path, lock: list[dict[str, object]]) -> pathlib.Path:
    files = {"a.txt": "a", "b.txt": "b", "tool.sh": "#!/bin/sh\n"}
    files.update({f"filler/f{i}.txt": "x" for i in range(20)})
    files["scripts/ci-runner/gates.lock.json"] = json.dumps(lock, indent=2) + "\n"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    env = {**os.environ, **GIT_ENV}
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)
    return root


@pytest.fixture
def fixture_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    return _repo(
        tmp_path / "repo",
        [
            _gate("g:honest", "cat a.txt >/dev/null", ["a.txt"]),
            _gate("g:liar", "cat a.txt b.txt >/dev/null", ["a.txt"]),
        ],
    )


def _run(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(TSX), str(TOOL), "--root", str(root), *args],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.mark.skipif(
    not HAS_STRACE, reason="strace is not installed; trace mode refuses such a host"
)
def test_trace_mode_fails_the_undeclared_read_and_names_it(fixture_repo: pathlib.Path) -> None:
    res = _run(fixture_repo, "--mode", "trace", "--gate", "g:liar")
    assert res.returncode == 1, res.stderr
    assert "reads b.txt, outside its paths" in res.stderr
    assert "path-trace.ts --gate g:liar --write" in res.stderr


@pytest.mark.skipif(
    not HAS_STRACE, reason="strace is not installed; trace mode refuses such a host"
)
def test_trace_mode_passes_the_declared_fixture(fixture_repo: pathlib.Path) -> None:
    res = _run(fixture_repo, "--mode", "trace", "--gate", "g:honest")
    assert res.returncode == 0, res.stderr
    assert "1 traced" in res.stdout


def test_sparse_mode_fails_the_undeclared_read(fixture_repo: pathlib.Path) -> None:
    res = _run(fixture_repo, "--mode", "sparse", "--gate", "g:liar")
    assert res.returncode == 1, res.stderr
    assert "holding only its declared inputs" in res.stderr


def test_sparse_mode_passes_the_declared_fixture(fixture_repo: pathlib.Path) -> None:
    res = _run(fixture_repo, "--mode", "sparse", "--gate", "g:honest")
    assert res.returncode == 0, res.stderr
    assert "1 sparse-run" in res.stdout


def test_a_lock_with_no_paths_bearing_gate_is_a_failure(tmp_path: pathlib.Path) -> None:
    root = _repo(tmp_path / "empty", [_gate("g:whole", "true", None)])
    res = _run(root, "--mode", "sparse")
    assert res.returncode == 1
    assert "ZERO paths-bearing gates" in res.stderr


def test_quick_without_a_push_base_is_a_failure_not_an_empty_pass(
    fixture_repo: pathlib.Path,
) -> None:
    res = _run(fixture_repo, "--mode", "sparse", "--quick")
    assert res.returncode == 1
    assert "change set is UNKNOWN" in res.stderr


def test_quick_with_nothing_touched_names_what_it_saw(fixture_repo: pathlib.Path) -> None:
    res = _run(fixture_repo, "--mode", "sparse", "--quick", "--base", "HEAD")
    assert res.returncode == 0, res.stderr
    assert "0 of 2 candidates touched" in res.stdout


def _with_node_modules(root: pathlib.Path) -> pathlib.Path:
    (root / ".gitignore").write_text("node_modules\n")
    pkg = root / "node_modules" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "f.js").write_text("ORIGINAL\n")
    return pkg / "f.js"


def _reflinks_work(root: pathlib.Path) -> bool:
    src = root / "a.txt"
    dst = root.parent / "reflink-probe"
    ok = (
        subprocess.run(
            ["cp", "--reflink=always", str(src), str(dst)], capture_output=True, check=False
        ).returncode
        == 0
    )
    dst.unlink(missing_ok=True)
    return ok


# b.txt exists only in the real tree: the sparse tree holds a.txt alone, so the rewrite happens in the sparse run only.
_REWRITE = "if [ ! -e b.txt ]; then printf 'CLOBBERED\\n' > node_modules/pkg/f.js; fi; cat a.txt >/dev/null"


def test_sparse_run_cannot_rewrite_the_real_node_modules(tmp_path: pathlib.Path) -> None:
    root = _repo(tmp_path / "repo", [_gate("g:writer", _REWRITE, ["a.txt"])])
    real = _with_node_modules(root)
    res = _run(root, "--mode", "sparse", "--gate", "g:writer")
    if _reflinks_work(root):
        assert real.read_text() == "ORIGINAL\n", "reflink copy must isolate the real file"
        assert res.returncode == 0, res.stderr
    else:
        assert res.returncode == 1, res.stdout + res.stderr
        assert "node_modules/pkg/f.js" in res.stderr
        assert "REAL file" in res.stderr


def test_sparse_run_that_only_reads_node_modules_passes(tmp_path: pathlib.Path) -> None:
    root = _repo(
        tmp_path / "repo", [_gate("g:reader", "cat node_modules/pkg/f.js >/dev/null", ["a.txt"])]
    )
    real = _with_node_modules(root)
    res = _run(root, "--mode", "sparse", "--gate", "g:reader")
    assert res.returncode == 0, res.stderr
    assert real.read_text() == "ORIGINAL\n"
