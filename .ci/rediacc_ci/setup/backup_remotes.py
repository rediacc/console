"""The backup-remote step of the `git-hooks-path` setup phase: a `gitlab` remote at its pinned URL in private/renet, private/account and private/elite (box G4 of agent/plans/PLAN-local-first-delivery.md).

WHY. The backup worker (`./run.sh backup-ref sync`, started by the post-commit hook) pushes `refs/backup/<branch>/*` to each repository's `gitlab` remote, and the pre-push hook admits such a push only to the repository's pin. The console's `gitlab` remote already exists (the mirror push of .claude/commands/pr-merge.md); the submodules had none.

ONE DEFINITION OF THE PINS. `BACKUP_PATHS` and `MIRROR_HOST` live in .claude/rediacc_hooks/git/githooks.py, beside `MIRROR_PATH`, because the hook reads nothing outside `.claude`. This module loads that file BY PATH from THIS checkout's code (anchored on this file, like an import), so the URL written here is the URL the hook compares against.

IDEMPOTENT. A repository whose `gitlab` remote is already the pin is left alone and nothing is said. A `gitlab` remote at ANY OTHER URL is reported and left alone: replacing it could redirect someone's own remote, and the hook refuses a backup push to it anyway. A submodule that is not checked out is skipped, the same best-effort stance as the hooks path itself.

NO FETCH REFSPEC. The remote is added with `--no-tags`, its fetch refspec removed and `skipFetchAll` set, so neither `git fetch gitlab` nor `git fetch --all` writes `refs/remotes/gitlab/*`. Every "is it published" question in this tree reads `refs/remotes/*` as published, and nothing on the backup project is published.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import urllib.parse

REMOTE = "gitlab"
CODE_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS_FILE = CODE_ROOT / ".claude" / "rediacc_hooks" / "git" / "githooks.py"


def pins() -> dict[str, str]:
    """`{submodule path: pinned https URL}` for every submodule in the hook's `BACKUP_PATHS` (the console's own entry is the mirror remote, which this step does not add)."""
    name = "rediacc_setup_backup_remotes_githooks"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, HOOKS_FILE)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load %s" % HOOKS_FILE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return {
        rel: "https://%s%s" % (module.MIRROR_HOST, path)
        for rel, path in module.BACKUP_PATHS.items()
        if rel
    }


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False, timeout=30
    )


def _shown(url: str) -> str:
    """`url` without credentials, for a message."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "(an unparseable URL)"
    if not parts.scheme:
        return "(a local path)"
    return "%s://%s%s" % (parts.scheme, parts.hostname or "", parts.path)


def current(repo: pathlib.Path) -> str:
    return _git(repo, "config", "--get", "remote.%s.url" % REMOTE).stdout.strip()


def plan(root: pathlib.Path) -> list[tuple[str, pathlib.Path, str, str]]:
    """`(rel, repo, want, have)` for every pinned submodule that is checked out."""
    out = []
    for rel, want in pins().items():
        repo = root / rel
        if (repo / ".git").exists():
            out.append((rel, repo, want, current(repo)))
    return out


def fetchable(repo: pathlib.Path) -> bool:
    """Whether the `gitlab` remote still has a fetch refspec or lacks `skipFetchAll`, the half-done state of a `remote add` whose next step failed."""
    refspec = _git(repo, "config", "--get-all", "remote.%s.fetch" % REMOTE).stdout.strip()
    skip = _git(repo, "config", "--get", "remote.%s.skipFetchAll" % REMOTE).stdout.strip()
    return bool(refspec) or skip != "true"


def _lock_down(repo: pathlib.Path) -> tuple[str, ...] | None:
    """Remove the fetch refspec and set `skipFetchAll`; the failing step, or None."""
    for step in (
        ("config", "--unset-all", "remote.%s.fetch" % REMOTE),
        ("config", "remote.%s.skipFetchAll" % REMOTE, "true"),
    ):
        proc = _git(repo, *step)
        # `--unset-all` exits 5 when there was no such key, which is the state wanted.
        if proc.returncode not in (0, 5) or (proc.returncode == 5 and step[1] != "--unset-all"):
            return step
    return None


def install(root: pathlib.Path, say=print) -> int:
    """Add each missing pinned remote, and finish one an earlier run left with its fetch refspec. 0 on success, a foreign remote reported and left alone included; 1 when a git command failed."""
    failed = 0
    for rel, repo, want, have in plan(root):
        if have and have != want:
            say(
                "backup remotes: %s: `%s` points at %s, not the pin %s; left alone"
                % (rel, REMOTE, _shown(have), want)
            )
            continue
        if have == want:
            if not fetchable(repo):
                continue
            step = _lock_down(repo)
            if step:
                failed += 1
                say("backup remotes: %s: git %s failed" % (rel, " ".join(step)))
            else:
                say("backup remotes: %s: `%s` fetch refspec removed" % (rel, REMOTE))
            continue
        add = ("remote", "add", "--no-tags", REMOTE, want)
        proc = _git(repo, *add)
        if proc.returncode != 0:
            failed += 1
            say("backup remotes: %s: git %s failed: %s" % (rel, " ".join(add), proc.stderr.strip()))
            continue
        step = _lock_down(repo)
        if step:
            failed += 1
            say("backup remotes: %s: git %s failed" % (rel, " ".join(step)))
            continue
        say("backup remotes: %s: `%s` -> %s" % (rel, REMOTE, want))
    return 1 if failed else 0


def check_row(root: pathlib.Path) -> tuple[str, bool]:
    """`(row, is_pending)` for `./run.sh setup --check`, which mutates nothing. A foreign remote is named in every run, beside the pending rows too (97a4bd32.1), but is not pending itself: setup leaves it alone."""
    rows = plan(root)
    missing = [rel for rel, _repo, _want, have in rows if not have]
    foreign = [rel for rel, _repo, want, have in rows if have and have != want]
    unlocked = [rel for rel, repo, want, have in rows if have == want and fetchable(repo)]
    pending = []
    if unlocked:
        pending.append("keep a fetch refspec in %s (setup removes it)" % ", ".join(unlocked))
    if missing:
        pending.append("NOT added in %s (setup adds `%s`)" % (", ".join(missing), REMOTE))
    elsewhere = "%s point elsewhere (left alone)" % ", ".join(foreign) if foreign else ""
    if pending:
        return "  backup remotes " + "; ".join([*pending, *filter(None, [elsewhere])]), True
    if foreign:
        return "  backup remotes %s" % elsewhere, False
    return "  backup remotes pinned (`%s` in %d submodule(s))" % (REMOTE, len(rows)), False
