"""`check:ci-release-note-trailers` reads a PR range and the submodule gitlink deltas through `release_notes.collect` (agent/plans/PLAN-release-notes.md RN4).

Every case builds real git repositories (a console with `private/account` as a real submodule) and drives the gate's `evaluate`, plus one case through the real command line so the exit code a CI step reads is the one asserted. Each refusal has a passing twin built from the same range with one fact changed.
"""

import importlib.util
import os
import subprocess
import sys

import pytest

from rediacc_ci import paths

GATE_PATH = paths.repo_root() / ".ci" / "scripts" / "quality" / "check_release_note_trailers.py"
NOTE = "Backups now resume after a dropped connection"


@pytest.fixture(scope="module")
def gate():
    assert GATE_PATH.is_file(), "the gate moved: %s" % GATE_PATH
    paths.on_sys_path(GATE_PATH.parent)
    spec = importlib.util.spec_from_file_location("check_release_note_trailers_gate", GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fx(gate):
    with gate.fixture() as built:
        yield built


def test_zero_commits_is_77_never_0(gate, fx):
    rc, lines = gate.evaluate(fx.console, fx.base_sha)
    assert rc == 77, lines


def test_exempt_commits_after_the_gate_are_clean_and_pre_gate_feats_are_not_read(gate, fx):
    fx.commit(fx.console, ".github/workflows/x.yml", "feat(ci): an internal change")
    fx.commit(fx.console, "scripts/x.ts", "fix: an internal fix")
    fx.commit(fx.console, "packages/cli/src/x.ts", "chore: not a customer type")
    rc, lines = gate.evaluate(fx.console, fx.base_sha)
    assert rc == 0, lines


def test_a_valid_trailer_is_admitted(gate, fx):
    fx.commit(fx.console, "packages/cli/src/x.ts", "feat(cli): resume\n\nRelease-Note: %s" % NOTE)
    fx.commit(
        fx.console,
        "packages/cli/src/y.ts",
        "fix(cli): tidy\n\nRelease-Note: none -- an internal refactor, no visible change",
    )
    rc, lines = gate.evaluate(fx.console, fx.base_sha)
    assert rc == 0, lines


def test_a_trailer_less_submodule_feat_is_one_and_names_the_submodule_sha(gate, fx):
    sha = fx.commit(fx.sub, "src/new.ts", "feat: a submodule feature with no trailer")
    fx.bump()
    rc, lines = gate.evaluate(fx.console, fx.base_sha)
    text = "\n".join(lines)
    assert rc == 1
    assert sha[:10] in text
    assert "private/account" in text
    assert "Release-Note" in text


def test_the_same_submodule_commit_with_the_trailer_is_clean(gate, fx):
    fx.commit(fx.sub, "src/new.ts", "feat: a submodule feature\n\nRelease-Note: %s" % NOTE)
    fx.bump()
    rc, lines = gate.evaluate(fx.console, fx.base_sha)
    assert rc == 0, lines


def test_a_console_feat_with_no_trailer_is_one(gate, fx):
    sha = fx.commit(fx.console, "packages/cli/src/x.ts", "feat(cli): a feature")
    rc, lines = gate.evaluate(fx.console, fx.base_sha)
    assert rc == 1
    assert sha[:10] in "\n".join(lines)


def test_a_short_none_reason_and_a_note_naming_a_path_are_one(gate, fx):
    fx.commit(fx.console, "packages/cli/src/a.ts", "fix(cli): a\n\nRelease-Note: none -- n/a")
    fx.commit(
        fx.console,
        "packages/cli/src/b.ts",
        "fix(cli): b\n\nRelease-Note: Fixed a crash in packages/cli/src/b.ts",
    )
    rc, lines = gate.evaluate(fx.console, fx.base_sha)
    assert rc == 1
    assert "2 of 2" in "\n".join(lines)


def test_an_unreadable_base_and_a_gate_without_history_are_one(gate, fx):
    assert gate.evaluate(fx.console, "does-not-exist")[0] == 1
    assert gate.evaluate(fx.console, fx.base_sha, gate_rel="no/such/gate.py")[0] == 1


def test_a_submodule_that_is_not_checked_out_is_one_never_clean(gate, fx):
    fx.commit(fx.sub, "src/new.ts", "feat: a submodule feature with no trailer")
    fx.bump()
    fx.git(fx.console, "submodule", "deinit", "-f", "private/account")
    for child in fx.sub.iterdir():
        if child.is_dir():
            subprocess.run(["rm", "-rf", str(child)], check=True)
    rc, lines = gate.evaluate(fx.console, fx.base_sha)
    assert rc == 1, lines


def test_with_the_gate_on_the_base_the_range_is_the_plain_pr_range(gate, fx):
    fx.commit(fx.console, "packages/cli/src/x.ts", "feat(cli): a feature with no trailer")
    rc, lines = gate.evaluate(fx.console, fx.anchor())
    assert rc == 1
    assert "already on the base" in "\n".join(lines)


def test_the_command_line_exit_codes(gate, fx):
    env = {k: v for k, v in os.environ.items() if k not in gate.GIT_REPO_VARS}
    env.update(PR_BASE_REF=fx.base_sha, PR_HEAD_REF="topic")

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GATE_PATH), "--root", str(fx.console)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    assert run().returncode == 77
    fx.commit(fx.console, "packages/cli/src/x.ts", "feat(cli): a feature with no trailer")
    bad = run()
    assert bad.returncode == 1
    assert "Release-Note" in bad.stderr
    assert bad.stdout.count("✗") == 0
    env["PR_HEAD_REF"] = "main"
    assert run().returncode == 0


def test_the_selftest_controls_pass(gate):
    assert gate.run_controls() is True
