"""`./run.sh backup-ref sync`: an off-machine copy of the checked-out branch under `refs/backup/<branch>/` on the repository's GitLab remote (Design G of agent/plans/PLAN-local-first-delivery.md, operator ruling R1).

WHAT A SYNC DOES, in one repository, under one flock (`<git-dir>/rediacc-backup/lock`), each step appended to `<git-dir>/rediacc-backup/log`:

  1. Reads the remote's `refs/backup/<branch>/*` with `git ls-remote`, NEVER through a remote-tracking ref. Every "is it published" question in this tree (`--not --remotes`, the pre-push session scan, `block_unpushed_submodule_pin`) reads `refs/remotes/*` as published, so a backup ref fetched there would make unpublished commits look published. Nothing here writes `refs/remotes/*`.
  2. `live` absent: creates it at HEAD. HEAD descends from `live`: fast-forwards it. Otherwise history was rewritten: the old tip is fetched into FETCH_HEAD when it is not here (`--refmap=` so no remote-tracking ref moves), kept as an immutable `pre-rewrite-<YYYYMMDDTHHMMZ>` in one atomic push that also deletes `live`, and `live` is then created at HEAD. A delete and two creates, never a force.
  3. The first sync of a UTC day also creates `daily-<YYYY-MM-DD>` at HEAD.

`main` is never backed up (the mirror push covers it), nor a detached HEAD, nor a lease tree (a lease never pushes). Every push runs with `GIT_TERMINAL_PROMPT=0`, and no argv this module builds carries `--force`, `-f` or a `+` refspec: `_git` refuses one before it runs. The pre-push hook (`backup_ref_refusal` in .claude/rediacc_hooks/git/githooks.py) judges each push again: the pinned URL, nothing but `refs/backup/**`, the incremental session and secret scans.

A FAILED PUSH IS RETRIED BY THE NEXT TRIGGER. The post-commit, post-rewrite and post-merge hooks start this module detached; it always pushes the CURRENT tip, so a missed sync is caught up by the next one.

Exit codes: 0 synced (or nothing to do), 1 a step failed (the log names it), 2 usage.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import fcntl
import os
import pathlib
import subprocess
import sys
import time

REMOTE = "gitlab"
SPACE = "refs/backup/"
ZERO = "0" * 40
STATE_DIR = "rediacc-backup"
LOCK_WAIT_S = 600
GIT_TIMEOUT_S = 900
LEASE_HOLDER = "/.claude/worktrees/"
# The repositories `--repo` names, by their path below the console root.
REPOS = {
    "console": ".",
    "renet": "private/renet",
    "account": "private/account",
    "elite": "private/elite",
}
# Inherited from a git hook, these would point every `git -C <repo>` at the hook's repository instead.
_REPO_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
    "GIT_QUARANTINE_PATH",
)

USAGE = """\
Usage: ./run.sh backup-ref sync [--repo console|renet|account|elite]... [--all] [--remote <name>]

Back up the checked-out branch of each repository as refs/backup/<branch>/live
(plus a daily-<YYYY-MM-DD> once per UTC day, and a pre-rewrite-<stamp> after a
history rewrite) on its GitLab remote. Never forced, never refs/remotes/*.
With no --repo, the repository the current directory sits in.
"""


class StepError(RuntimeError):
    """A git step failed; the message names it."""


class ForcedArgvError(RuntimeError):
    """An argv this module built would force a ref; refused before it runs."""


def forced(argv: list[str]) -> bool:
    """Whether a git argv forces a ref update: `--force`, `--force-with-lease`, `--force-if-includes`, a short `-f` cluster on push, or a `+` refspec."""
    if not argv:
        return False
    for arg in argv:
        if arg.startswith("--force"):
            return True
        if argv[0] == "push" and arg.startswith("-") and not arg.startswith("--") and "f" in arg:
            return True
        if arg.startswith("+"):
            return True
    return False


#: Every argv `_git` ran in this process, in order. Read by the tests, which assert no forced shape ever reached git.
RAN: list[list[str]] = []


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _REPO_ENV}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(repo: pathlib.Path, argv: list[str], check: bool = True) -> subprocess.CompletedProcess:
    if forced(argv):
        raise ForcedArgvError("refused to run a forced git argv: git %s" % " ".join(argv))
    RAN.append(list(argv))
    proc = subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        env=_env(),
        timeout=GIT_TIMEOUT_S,
        check=False,
    )
    if check and proc.returncode != 0:
        raise StepError(
            "git %s exited %d: %s"
            % (" ".join(argv), proc.returncode, (proc.stderr or proc.stdout).strip()[-800:])
        )
    return proc


def _out(repo: pathlib.Path, argv: list[str]) -> str:
    return _git(repo, argv).stdout.strip()


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class Log:
    """Appends stamped lines to `<git-dir>/rediacc-backup/log`, and to stderr when asked."""

    def __init__(self, path: pathlib.Path, echo: bool) -> None:
        self.path = path
        self.echo = echo

    def __call__(self, text: str) -> None:
        line = "%s %s" % (_utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), text)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        if self.echo:
            sys.stderr.write("backup-ref: %s\n" % text)


@contextlib.contextmanager
def _locked(path: pathlib.Path, wait_s: float):
    """One sync per repository. Waits rather than skipping: a waiter that gets the lock pushes the tip as it is THEN, so a commit made during another sync is not missed."""
    with path.open("a+") as handle:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise StepError("another sync held %s for %ds" % (path, wait_s)) from None
                time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def remote_refs(repo: pathlib.Path, remote: str, branch: str) -> dict[str, str]:
    """`{leaf: oid}` of `refs/backup/<branch>/*` on `remote`, read with `git ls-remote` (never a remote-tracking ref)."""
    prefix = "%s%s/" % (SPACE, branch)
    out = _out(repo, ["ls-remote", remote, prefix + "*"])
    refs: dict[str, str] = {}
    for line in out.splitlines():
        oid, _tab, ref = line.partition("\t")
        if ref.startswith(prefix) and "/" not in ref[len(prefix) :]:
            refs[ref[len(prefix) :]] = oid
    return refs


def _has_commit(repo: pathlib.Path, oid: str) -> bool:
    return _git(repo, ["cat-file", "-e", "%s^{commit}" % oid], check=False).returncode == 0


def _is_ancestor(repo: pathlib.Path, old: str, new: str) -> bool:
    return _git(repo, ["merge-base", "--is-ancestor", old, new], check=False).returncode == 0


def sync(repo: pathlib.Path, remote: str = REMOTE, echo: bool = False) -> int:
    """One sync of `repo` (the steps in the module docstring). 0 synced or nothing to do, 1 a step failed."""
    real = os.path.realpath(repo)
    if LEASE_HOLDER in real + "/":
        sys.stderr.write("backup-ref: %s is a lease tree, and a lease never pushes\n" % real)
        return 0
    try:
        git_dir = pathlib.Path(_out(repo, ["rev-parse", "--absolute-git-dir"]))
    except StepError as exc:
        sys.stderr.write("backup-ref: %s\n" % exc)
        return 1
    state = git_dir / STATE_DIR
    state.mkdir(parents=True, exist_ok=True)
    log = Log(state / "log", echo)
    try:
        with _locked(state / "lock", LOCK_WAIT_S):
            return _sync_locked(repo, remote, log)
    except (StepError, ForcedArgvError, subprocess.TimeoutExpired, OSError) as exc:
        log("FAILED %s" % exc)
        return 1


def _sync_locked(repo: pathlib.Path, remote: str, log: Log) -> int:
    branch = _git(repo, ["symbolic-ref", "--short", "-q", "HEAD"], check=False).stdout.strip()
    if not branch:
        log("skip: detached HEAD")
        return 0
    if branch == "main":
        log("skip: main is covered by the mirror push")
        return 0
    if _git(repo, ["remote", "get-url", remote], check=False).returncode != 0:
        log("skip: no `%s` remote" % remote)
        return 1
    tip = _out(repo, ["rev-parse", "--verify", "HEAD^{commit}"])
    base = "%s%s/" % (SPACE, branch)
    refs = remote_refs(repo, remote, branch)
    live = refs.get("live")
    daily = "daily-%s" % _utcnow().strftime("%Y-%m-%d")
    want_daily = daily not in refs
    if live and live != tip and not _is_ancestor(repo, live, tip):
        if not _has_commit(repo, live):
            _git(repo, ["fetch", "--no-tags", "--refmap=", remote, base + "live"])
        stamp = _utcnow().strftime("%Y%m%dT%H%MZ")
        kept = "%spre-rewrite-%s" % (base, stamp)
        _git(repo, ["push", "--atomic", remote, "%s:%s" % (live, kept), ":%slive" % base])
        log("rewrite: kept %s at %s, live restarted" % (kept, live[:12]))
        live = None
    specs = []
    if live != tip:
        specs.append("%s:%slive" % (tip, base))
    if want_daily:
        specs.append("%s:%s%s" % (tip, base, daily))
    if not specs:
        log("up to date: %s live == %s" % (branch, tip[:12]))
        return 0
    _git(repo, ["push", "--atomic", remote, *specs])
    log("pushed %s -> %s" % (tip[:12], ", ".join(s.split(":", 1)[1] for s in specs)))
    return 0


def _console_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3]


def _targets(args: argparse.Namespace) -> list[pathlib.Path]:
    names = list(REPOS) if args.all else (args.repo or [])
    if names:
        root = _console_root()
        return [root / REPOS[name] for name in names]
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    if top.returncode != 0:
        raise StepError("the current directory is not in a git repository")
    return [pathlib.Path(top.stdout.strip())]


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0 if argv else 2
    verb, rest = argv[0], argv[1:]
    if verb != "sync":
        sys.stderr.write("backup-ref: unknown subcommand `%s`\n%s" % (verb, USAGE))
        return 2
    parser = argparse.ArgumentParser(prog="./run.sh backup-ref sync", add_help=True)
    parser.add_argument("--repo", action="append", choices=sorted(REPOS))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--remote", default=REMOTE)
    parser.add_argument("--quiet", action="store_true", help="log only to the log file")
    args = parser.parse_args(rest)
    try:
        targets = _targets(args)
    except StepError as exc:
        sys.stderr.write("backup-ref: %s\n" % exc)
        return 1
    worst = 0
    for repo in targets:
        worst = max(worst, sync(repo, args.remote, echo=not args.quiet))
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
