"""Gates only at landing (PLAN-worktree-lease W9): `vm_check` and `live_proof record` refuse from a lease and reach their usual arg error in a main checkout.

Each run is a real process with `$REDIACC_CI_ROOT` on a throwaway repository, so no real checkout, gateway or ledger is involved. The same argv goes to both trees: the refusal is judged before the arguments, so the arg error in the main tree proves the refusal let it through.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, NamedTuple

import pytest

from rediacc_ci import paths
from rediacc_ci.dev import worktree_lease as lease
from rediacc_ci.dev import worktree_spike as spike

if TYPE_CHECKING:
    import pathlib

VM_CHECK = "rediacc_ci.drills.vm_check"
LIVE_PROOF = "rediacc_ci.ops.live_proof"
REFUSED = "REFUSED"
LANDING = "main checkout at landing"
QUICK_CLONE = paths.CI_DIR.parent / "scripts" / "ci-runner" / "quick-clone.ts"
TSX = paths.CI_DIR.parent / "node_modules" / ".bin" / "tsx"
RC_USAGE = 2


class Trees(NamedTuple):
    main: pathlib.Path
    lease: pathlib.Path
    operator: pathlib.Path


@pytest.fixture
def trees(tmp_path):
    root = spike.build_fixture(tmp_path, plant=False).root
    sha = spike.must(root, "rev-parse", "HEAD")
    held = root / spike.HOLDER / "gates-x"
    lease._add_tree(root, held, sha, "gates-x")
    operator = root / ".worktrees" / "0128-1"
    lease._add_tree(root, operator, sha, "gates-op")
    return Trees(root, held, operator)


def run(module, tree, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(PYTHONPATH=str(paths.CI_DIR), REDIACC_CI_ROOT=str(tree))
    return subprocess.run(
        [sys.executable, "-m", module, *argv],
        env=env,
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def is_refused(done):
    return done.returncode == 1 and REFUSED in done.stderr and LANDING in done.stderr


def test_gates_vm_check_refused_in_lease_and_arg_error_in_main(trees):
    argv = ("--only", "NOPE")
    leased = run(VM_CHECK, trees.lease, *argv)
    assert is_refused(leased), leased
    assert "--only names no step" not in leased.stderr
    for tree in (trees.main, trees.operator):
        done = run(VM_CHECK, tree, *argv)
        assert done.returncode == RC_USAGE, done
        assert "--only names no step" in done.stderr
        assert REFUSED not in done.stderr


def test_gates_vm_check_valid_run_starts_nothing_in_lease(trees, capsys):
    vm_check = importlib.import_module(VM_CHECK)
    unusable = object()
    rc = vm_check.main(
        ["--changed"], root=trees.lease, host=unusable, account=unusable, lock=unusable
    )
    assert rc == vm_check.EXIT_FAILED
    assert REFUSED in capsys.readouterr().err


@pytest.mark.parametrize("argv", [("--dry-run", "--paths", "x.txt"), ("--help",)])
def test_gates_vm_check_read_only_flags_stay_allowed_in_lease(trees, argv):
    done = run(VM_CHECK, trees.lease, *argv)
    assert done.returncode == 0, done
    assert REFUSED not in done.stderr


def test_gates_vm_check_selftest_stays_allowed_in_lease(trees):
    done = run(VM_CHECK, trees.lease, "--selftest")
    assert "fired as designed" in done.stdout, done
    assert REFUSED not in done.stderr


def test_gates_live_proof_record_refused_in_lease_and_arg_error_in_main(trees):
    leased = run(LIVE_PROOF, trees.lease, "record")
    assert is_refused(leased), leased
    for tree in (trees.main, trees.operator):
        done = run(LIVE_PROOF, tree, "record")
        assert done.returncode == RC_USAGE, done
        assert "required" in done.stderr
        assert REFUSED not in done.stderr


def test_gates_live_proof_record_write_leaves_no_ledger_in_lease(trees):
    argv = (
        *("record", "--plan", "verify", "--box", "b"),
        *("--target", "bench", "--check", "c", "--write"),
    )
    assert is_refused(run(LIVE_PROOF, trees.lease, *argv))
    assert not (trees.lease / "agent").exists()


def test_gates_live_proof_verify_stays_allowed_in_lease(trees):
    leased = run(LIVE_PROOF, trees.lease, "verify", "--plan", "agent/plans/none.md")
    main = run(LIVE_PROOF, trees.main, "verify", "--plan", "agent/plans/none.md")
    assert REFUSED not in leased.stderr
    assert (leased.returncode, leased.stdout) == (main.returncode, main.stdout)


def test_gates_lease_rule_matches_its_twin_in_quick_clone(trees, tmp_path):
    paths.on_sys_path(paths.hooks_stop_dir(paths.CI_DIR.parent))
    wl_core = importlib.import_module("wl_core")
    submodule = trees.main / "private" / "sub"
    plain = trees.main / spike.HOLDER / "plain"
    spike.must(tmp_path, "init", "-q", str(plain))
    candidates = [trees.main, trees.lease, trees.operator, submodule, plain, tmp_path]
    program = (
        "import(%s).then((m) => console.log(JSON.stringify(process.argv.slice(1).map((t) => m.leaseMainOf(t) ?? null))))"
        % json.dumps(str(QUICK_CLONE))
    )
    done = subprocess.run(
        [str(TSX), "--eval", program, "--", *map(str, candidates)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done
    answers = json.loads(done.stdout)
    expected = [wl_core.lease_main(tree) for tree in candidates]
    assert answers == [str(tree) if tree else None for tree in expected]
    assert answers.count(str(trees.main)) == 1, "the instrument must see one lease"


def test_spike_store_of_an_empty_submodule_directory_is_not_the_parent_store(tmp_path) -> None:
    root = (tmp_path / "main").resolve()
    (root / "private" / "empty").mkdir(parents=True)
    spike.must(root, "init", "-q")
    repo = spike.Repo(root, ["private/empty"])
    assert repo.store("private/empty") == root / ".git" / "modules" / "private/empty"
