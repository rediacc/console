"""The `git-hooks-path` setup phase: point `core.hooksPath` at the commit-policy hooks, in the console and in every checked-out submodule.

WHY (the commit-policy plan in agent/plans, section 5.3; operator ruling 2, 2026-09-25: git-level hooks for everyone, with the `COMMIT_POLICY_OK=1` override). The hooks live in `.claude/rediacc_hooks/git/` and enforce the commit policy on commands the agents' pre-bash guards never see: the operator's terminal, `!` commands, and subprocesses.

LOCAL CONFIG ONLY. `git config --local core.hooksPath <abs>` changes nothing for a `/tmp` fixture repository or a CI checkout, which never run setup. An ABSOLUTE path, because a submodule's hooks run with the submodule as their working directory and a relative `core.hooksPath` would resolve inside it.

IDEMPOTENT, like every phase (`.ci/lib/setup.sh:17`): a repository already pointing at the directory is left alone, so a second run does no work. A submodule that is not checked out (no `.git` entry) is skipped, the same best-effort stance `init-submodules.sh` takes for a developer without access to every private submodule.

THE BACKUP REMOTES RIDE THIS PHASE. After the hooks path, `backup_remotes.py` beside this file adds a `gitlab` remote at its pinned URL to each checked-out pinned submodule (box G4 of agent/plans/PLAN-local-first-delivery.md), since the backup refs it serves are pushed by these hooks.

A DIFFERENT EXISTING VALUE IS REPLACED AND SAID SO. There is no other hooks directory in this repository (no husky, no lefthook, no `.githooks`; `.git/hooks` holds only samples), so a foreign value is a leftover rather than a second tool, and leaving it would leave the policy silently unenforced.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

HOOKS_REL = (".claude", "rediacc_hooks", "git")
HOOK_NAMES = (
    "commit-msg",
    "reference-transaction",
    "pre-push",
    "pre-commit",
    "post-commit",
    "post-rewrite",
    "post-merge",
)


def hooks_dir(root: pathlib.Path) -> pathlib.Path:
    return root.joinpath(*HOOKS_REL)


def submodule_paths(root: pathlib.Path) -> list[str]:
    """The `path = ...` entries of `.gitmodules`, in file order."""
    try:
        text = (root / ".gitmodules").read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.split("\n"):
        key, _, value = line.strip().partition("=")
        if key.strip() == "path" and value.strip():
            out.append(value.strip())
    return out


def repositories(root: pathlib.Path) -> list[pathlib.Path]:
    """The console and every submodule that is checked out."""
    repos = [root]
    for rel in submodule_paths(root):
        path = root / rel
        if (path / ".git").exists():
            repos.append(path)
    return repos


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False, timeout=30
    )


def current(repo: pathlib.Path) -> str:
    return _git(repo, "config", "--local", "--get", "core.hooksPath").stdout.strip()


def pending(root: pathlib.Path) -> list[tuple[pathlib.Path, str]]:
    """`(repository, current value)` for every repository not yet pointing at the hooks."""
    want = str(hooks_dir(root))
    return [(repo, value) for repo in repositories(root) if (value := current(repo)) != want]


def missing_hooks(root: pathlib.Path) -> list[str]:
    """Hook files that are absent or not executable: installing a path to them would enforce nothing."""
    base = hooks_dir(root)
    return [
        name
        for name in HOOK_NAMES
        if not (base / name).is_file() or not ((base / name).stat().st_mode & 0o111)
    ]


def install(root: pathlib.Path, say=print) -> int:
    """Point every repository at the hooks. 0 on success (including nothing to do), 1 on a failure."""
    missing = missing_hooks(root)
    if missing:
        say(
            "git hooks: %s missing or not executable under %s"
            % (", ".join(missing), hooks_dir(root))
        )
        return 1
    want = str(hooks_dir(root))
    failed = 0
    for repo, value in pending(root):
        proc = _git(repo, "config", "--local", "core.hooksPath", want)
        rel = repo.relative_to(root) if repo != root else pathlib.Path(".")
        if proc.returncode != 0:
            failed += 1
            say("git hooks: %s: git config failed: %s" % (rel, proc.stderr.strip()))
        elif value:
            say("git hooks: %s: core.hooksPath %s -> %s" % (rel, value, want))
        else:
            say("git hooks: %s: core.hooksPath -> %s" % (rel, want))
    if _backup_remotes().install(root, say=say) != 0:
        failed += 1
    return 1 if failed else 0


def _backup_remotes():
    """`backup_remotes.py` beside this file, loaded BY PATH: this module is itself loaded by path from guard tests that put no `.ci` on sys.path. The step runs inside this phase because the backup refs it serves are pushed by these hooks (box G4 of PLAN-local-first-delivery)."""
    name = "rediacc_setup_backup_remotes"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(
            name, pathlib.Path(__file__).with_name("backup_remotes.py")
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("backup_remotes.py is missing beside %s" % __file__)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


def check_row(root: pathlib.Path) -> tuple[str, bool]:
    """`(row, is_pending)` for `./run.sh setup --check`, which mutates nothing."""
    todo = pending(root)
    if not todo:
        return "  git hooks   installed (core.hooksPath in %d repo(s))" % len(
            repositories(root)
        ), False
    names = ", ".join(str(r.relative_to(root)) if r != root else "." for r, _ in todo)
    return "  git hooks   NOT installed in %s (setup sets core.hooksPath)" % names, True
