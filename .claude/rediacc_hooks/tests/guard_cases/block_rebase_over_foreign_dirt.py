"""The test tables of `block_rebase_over_foreign_dirt`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.git import fixture_git
from rediacc_hooks.tests.fixtures.guards.loader import load_table


def _fixture_git(cwd, *args):
    return fixture_git(cwd, *args, date="2026-01-01T00:00:00+00:00")


# Every path the worlds below commit, so each world differs from the others only in what it then modifies.
_SEEDED = (
    "src/app.ts",
    "agent/d00dfeed/STATE.md",
    "agent/ledgers/judge.jsonl",
    "agent/worklist/d00dfeed.jsonl",
    "agent/plans/QUEUE.md",
    "agent/reviews/0831-1/clean.jsonl",
    "agent/reggate/0831-1.jsonl",
    "agent/plans/PLAN-x.md",
)


def _seeded(path):
    path.mkdir(parents=True)
    _fixture_git(path, "init", "-q", "--initial-branch=main")
    for rel in _SEEDED:
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text("v1\n", encoding="utf-8")
    _fixture_git(path, "add", "-A")
    _fixture_git(path, "commit", "-qm", "seed")
    _fixture_git(path, "checkout", "-q", "-b", "0831-1")
    return path


def _clean(path):
    """Nothing modified, one untracked file: untracked work is not what a rebase touches."""
    _seeded(path)
    (path / "notes.txt").write_text("untracked\n", encoding="utf-8")
    return path


def _volatile(path):
    """Only the hook's own session state is modified: allowed here, though git itself still refuses."""
    _seeded(path)
    for rel in _SEEDED:
        if rel.startswith("agent/") and rel != "agent/plans/PLAN-x.md":
            (path / rel).write_text("v2\n", encoding="utf-8")
    return path


def _dirty(path):
    """A peer's modified source file and a modified plan beside the volatile state: the two real paths are named, the volatile ones are not."""
    _volatile(path)
    (path / "src/app.ts").write_text("peer edit\n", encoding="utf-8")
    (path / "agent/plans/PLAN-x.md").write_text("v2\n", encoding="utf-8")
    return path


def _staged(path):
    """Staged and not committed is uncommitted too: `git rebase` refuses a dirty index as well."""
    _seeded(path)
    (path / "src/app.ts").write_text("staged\n", encoding="utf-8")
    _fixture_git(path, "add", "src/app.ts")
    return path


def _gitlink(path):
    """Only a STAGED submodule pointer moved: git's up-front check passes it and the rebase then stops partway, so it refuses (worklist #dbbed0b6). `--ignore-submodules=all` hid it from the old probe."""
    _seeded(path)
    _fixture_git(path, "update-index", "--add", "--cacheinfo", "160000,%s,private/sub" % ("1" * 40))
    _fixture_git(path, "commit", "-qm", "pin a submodule")
    _fixture_git(path, "update-index", "--cacheinfo", "160000,%s,private/sub" % ("2" * 40))
    return path


FIXTURES = {
    "rebase-clean": _clean,
    "rebase-volatile": _volatile,
    "rebase-dirty": _dirty,
    "rebase-staged": _staged,
    "rebase-gitlink": _gitlink,
}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (name, {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in sorted(FIXTURES)
]


EDGE_CASES = load_table("block_rebase_over_foreign_dirt", "EDGE_CASES")
