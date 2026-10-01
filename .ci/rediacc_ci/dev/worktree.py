"""`./run.sh worktree`: create, list, remove, switch and prune console worktrees.

PORT OF `scripts/dev/worktree.sh`, under Rule T (PLAN-retire-bash-oracles): the commands, messages, streams and exit codes match the script wherever the script was right, and differ on purpose in the places below. Each difference has a test in `tests/test_dev_worktree.py` that fails on the bash.

THE INCIDENT THIS PORT EXISTS FOR (worklist #53f3f1c8, 2026-10-01 11:19Z). `./run.sh worktree prune --help` ran a REAL prune in the shared checkout. The script ignored `--help` for `prune`, so `sync_main_repo` ran `git stash --include-untracked` over 50 files of other sessions' live work, checked out `main`, pulled `origin/main` and updated the submodules.

THE DELIBERATE DIFFERENCES FROM THE BASH.

  D1. EVERY SUBCOMMAND HONOURS `-h` / `--help` and prints its usage on stdout with exit 0 BEFORE anything else happens: no git call, no root lookup, no network. The bash honoured it for `create` and `switch` only; `prune --help` ran a prune, `list --help` listed, `remove --help` looked for a worktree named `--help`.

  D2. THE CHECKOUT THE COMMAND RUNS FROM IS NEVER STASHED, SWITCHED, RESET OR PULLED WHILE IT HAS UNCOMMITTED OR UNTRACKED PATHS. `git status --porcelain` is the test, because the bash tested `git diff --quiet`, which cannot see an untracked file (the bash stashed only on a tracked change and then checked out `main` over a tree that held nothing but untracked work). The refusal names the NUMBER of dirty paths, and the command goes on with what needs no checkout: `create` branches from the fetched `origin/main`, `prune` asks GitHub.

  D3. THE CHECKOUT IS NEVER MOVED OFF ITS BRANCH. `create` and `prune` only need a current `origin/main`, so the sync fetches it and, only when the checkout is already on `main` and clean, fast-forwards it. The bash checked out `main` in whatever checkout invoked it, which under the one-branch rule is a session's own `MMDD-N` branch.

  D4. UNKNOWN COMMANDS, OPTIONS AND SURPLUS ARGUMENTS ARE REFUSED (exit 1) for every subcommand. The bash let `list`, `prune` swallow anything and `remove` take the first word.

  D5. `remove <name>` ACCEPTS A NAME, NOT A PATH. The bash joined it onto `.worktrees/` and tested only `-d`, so `remove ../../x` reached `git worktree remove --force`, then `sudo rm -rf` on the resolved directory, then `git branch -D` on whatever `HEAD` named there.

  D6. `prune` NEVER REMOVES A WORKTREE THAT HAS UNCOMMITTED OR UNTRACKED PATHS, and never one it is invoked from. The bash tested only tracked changes for the empty-branch case (an untracked-only worktree was deleted with `--force`) and none for the merged case.

  D7. A MERGED PR COUNTS ONLY WHEN THE LOCAL BRANCH TIP IS THE PR'S HEAD COMMIT. The bash deleted the branch on any merged PR of that name, so commits made after the merge went with `branch -D`.

  D8. `main`, `HEAD` and a detached worktree's branch are never deleted by the branch-cleanup step, and a worktree sitting on `main` is never pruned.

  D9. `switch` NEVER DISCARDS LOCAL COMMITS. The bash ran `checkout -B <branch> origin/<branch>`, which moves a local branch that is AHEAD of or DIVERGED from its remote back to the remote and strands the difference in the reflog. The port fast-forwards only when the local tip is an ancestor of the remote tip, and otherwise checks the local branch out as it is. The same helper serves the submodule branches. `switch` also treats untracked paths as dirty (D2) and validates the branch name.

  D10. `sudo rm -rf` runs as `sudo -n`, so a missing sudo credential fails at once instead of hanging on a prompt nobody watches, and only on a path the name check proved to sit directly under `.worktrees`.

  D11. `list` matches the worktree directory by path component, not by string prefix.

  D12. git runs with `GIT_TERMINAL_PROMPT=0`, so a credential prompt cannot hang a run that has no terminal.

NOT CHANGED ON PURPOSE. `prune` still removes a worktree whose branch has no commit beyond `origin/main` and no changes (a just-created empty worktree is "no commits, no changes" by the script's own definition), `remove` still force-removes the named worktree and deletes its branch, and the devbox teardown still runs BEFORE the directory goes (see `remove_worktree`).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rediacc_ci import log, paths

BASE_BRANCH = "main"
TMUX_PREFIX = "console"
GIT_TIMEOUT = 600.0

# A worktree name is one path component made of the characters `MMDD-N` uses and the few more a hand-made name needs. No slash, no leading dot or dash.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

CREATE_HELP = """\
Usage: ./run.sh worktree create [--teams] [--no-devbox]

Options:
  --no-devbox  Skip starting the devbox container
  --teams, -t  Enable Claude agent teams (experimental)
               Spawns lead with --teammate-mode tmux so
               teammates get their own tmux panes
"""

LIST_HELP = """\
Usage: ./run.sh worktree list

List the console worktrees under .worktrees with branch and tmux status.
"""

REMOVE_HELP = """\
Usage: ./run.sh worktree remove <name>

Remove the worktree .worktrees/<name> (devbox, tmux session, directory and
branch). <name> is a directory name such as 0128-1, never a path.
"""

SWITCH_HELP = """\
Usage: ./run.sh worktree switch <branch>

Switch the current repo to <branch> and sync submodules.

For each submodule:
  - If the branch has pointer changes (submodule commit differs
    from origin/main), the submodule is switched to a matching branch.
  - Otherwise, the submodule is updated to the recorded commit.

Refuses while the checkout or a submodule has uncommitted or untracked paths,
and never moves a local branch that has commits its remote lacks.

Options:
  --help, -h  Show this help message
"""

PRUNE_HELP = """\
Usage: ./run.sh worktree prune

Remove the worktrees whose PR is merged, or whose branch has no commit beyond
origin/main and no changes. A worktree with uncommitted or untracked paths is
kept. The checkout this runs from is only fetched, never stashed, switched or
reset.
"""

SUBCOMMAND_HELP = {
    "create": CREATE_HELP,
    "list": LIST_HELP,
    "remove": REMOVE_HELP,
    "switch": SWITCH_HELP,
    "prune": PRUNE_HELP,
}

MAIN_HELP = """\
Usage: ./run.sh worktree <command> [options]

Commands:
  create [options]  Create a new worktree with MMDD-X naming format
  list              List all console worktrees with branch and tmux status
  remove <name>     Remove a specific worktree by name
  switch <branch>   Switch current repo to branch and sync submodules
  prune             Cleanup of worktrees with merged PRs

Every command accepts --help.

Create Options:
  --teams, -t  Enable Claude agent teams (experimental).
               Sets CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
               and launches lead with --teammate-mode tmux.
               Teammates spawn in their own tmux panes.

Examples:
  ./run.sh worktree create           # Creates 0128-1 with tmux session
  ./run.sh worktree create -t        # Creates with agent teams enabled
  ./run.sh worktree list             # Shows all worktrees
  ./run.sh worktree remove 0128-1    # Remove specific worktree
  ./run.sh worktree switch 0204-1    # Switch branch and sync submodules
  ./run.sh worktree prune            # Cleanup worktrees with merged PRs

After create:
  tmux attach -t console-0128-1
"""

HELP_FLAGS = ("-h", "--help")


# --------------------------------------------------------------------------- process helpers ---------------------------------------------------------------------------


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if extra:
        env.update(extra)
    return env


def _capture(
    argv: list[str], cwd: Path | str | None = None, extra_env: dict[str, str] | None = None
) -> tuple[int, str]:
    """Run quietly. (rc, stdout); 127 when the program is absent. stderr is dropped, as the script's `2>/dev/null` did."""
    try:
        proc = subprocess.run(
            argv,
            cwd=None if cwd is None else str(cwd),
            env=_env(extra_env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    return proc.returncode, proc.stdout


def _passthrough(
    argv: list[str],
    cwd: Path | str | None = None,
    extra_env: dict[str, str] | None = None,
    quiet: bool = False,
) -> int:
    """Run with the caller's stdout and stderr, as a script line does. `quiet` drops stderr."""
    _flush()
    try:
        return subprocess.run(
            argv,
            cwd=None if cwd is None else str(cwd),
            env=_env(extra_env),
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL if quiet else None,
            timeout=GIT_TIMEOUT,
            check=False,
        ).returncode
    except OSError as exc:
        log.error("%s: %s" % (argv[0], exc.strerror or exc))
        return 127
    except subprocess.TimeoutExpired:
        log.error("%s: timed out" % argv[0])
        return 124


def _git(cwd: Path | str, *args: str) -> tuple[int, str]:
    return _capture(["git", "-C", str(cwd), *args])


def _git_ok(cwd: Path | str, *args: str) -> bool:
    return _git(cwd, *args)[0] == 0


def _out(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def dirty_paths(path: Path | str) -> list[str]:
    """Every path `git status` reports in `path`: modified, staged, deleted, untracked. Empty when clean or not a repository."""
    rc, out = _git(path, "status", "--porcelain")
    if rc != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def worktree_base() -> Path:
    return paths.repo_root() / ".worktrees"


def tmux_session_exists(name: str) -> bool:
    return _capture(["tmux", "has-session", "-t", name])[0] == 0


def listed_worktrees(root: Path) -> list[str]:
    """Every worktree path git knows, in git's order."""
    _rc, out = _git(root, "worktree", "list", "--porcelain")
    return [line[len("worktree ") :] for line in out.splitlines() if line.startswith("worktree ")]


def under_base(path: str, base: Path) -> bool:
    prefix = str(base)
    return path.startswith(prefix + os.sep)


def current_branch(path: Path | str) -> str:
    rc, out = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    return out.strip() if rc == 0 else ""


def base_ref(root: Path) -> str:
    """`origin/main` once fetched, else the local `main`: the ref a branch is compared with."""
    return (
        f"origin/{BASE_BRANCH}"
        if _git_ok(root, "rev-parse", "--verify", f"origin/{BASE_BRANCH}")
        else BASE_BRANCH
    )


# --------------------------------------------------------------------------- the sync of the invoking checkout ---------------------------------------------------------------------------


def sync_main_repo(root: Path) -> None:
    """Bring `origin/main` up to date, and the checkout with it only when that touches nothing of anyone's.

    D2 and D3: a dirty checkout is left exactly as it is (the message names the count), and a checkout on another branch is never switched.
    """
    log.step("Syncing main repo to latest origin/%s..." % BASE_BRANCH)
    branch = current_branch(root)
    if not branch:
        log.warn("Could not determine branch in %s, skipping sync" % root)
        return
    if _git(root, "fetch", "origin", BASE_BRANCH, "--quiet")[0] != 0:
        log.warn("Fetch failed, continuing with cached state")
    dirty = dirty_paths(root)
    if dirty:
        log.warn(
            "Main worktree has %d uncommitted or untracked path(s): refusing to stash, check out or pull it. Left untouched."
            % len(dirty)
        )
        return
    if branch != BASE_BRANCH:
        log.info(
            "Main checkout is on '%s', not '%s': left on its branch (only origin/%s was fetched)"
            % (branch, BASE_BRANCH, BASE_BRANCH)
        )
        return
    if (
        _passthrough(
            ["git", "-C", str(root), "pull", "--ff-only", "origin", BASE_BRANCH, "--quiet"],
            quiet=True,
        )
        != 0
    ):
        log.warn("Pull failed (diverged or network issue), continuing with the fetched state")
        return
    log.info("Pulled latest origin/%s" % BASE_BRANCH)
    log.info("Updating submodules...")
    _git(root, "submodule", "sync", "--quiet")
    if (
        _passthrough(
            ["git", "-C", str(root), "submodule", "update", "--init", "--recursive", "--quiet"],
            quiet=True,
        )
        != 0
    ):
        log.warn("Submodule update failed for some modules, continuing")
    log.info("Main repo sync complete")


# --------------------------------------------------------------------------- tmux, devbox, removal ---------------------------------------------------------------------------


def create_tmux_session(session: str, work_dir: Path, teams: bool) -> None:
    if not _have("tmux"):
        log.warn("tmux not installed, skipping session creation")
        return
    if tmux_session_exists(session):
        log.warn("tmux session '%s' already exists" % session)
        return
    _passthrough(["tmux", "new-session", "-d", "-s", session, "-n", session, "-c", str(work_dir)])
    if teams:
        _passthrough(
            ["tmux", "set-environment", "-t", session, "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1"]
        )
    claude_cmd = (
        "claude --dangerously-skip-permissions --teammate-mode tmux"
        if teams
        else "claude --dangerously-skip-permissions"
    )
    # New windows (Ctrl+b c) auto-layout: 75% top (claude) + 25% bottom (cli).
    _passthrough(
        [
            "tmux",
            "set-hook",
            "-t",
            session,
            "after-new-window",
            "split-window -v -l 25%% -c '#{pane_current_path}' ; select-pane -U ; send-keys '%s' C-m"
            % claude_cmd,
        ]
    )
    log.info("Created tmux session: %s" % session)
    if teams:
        log.info("Agent teams enabled (teammates will spawn in tmux panes)")


def pr_merged_at_tip(root: Path, branch: str) -> bool:
    """True when a merged PR names this branch AND the local tip is that PR's head commit (D7). A branch with later commits is not merged work."""
    rc, out = _capture(
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "merged",
            "--json",
            "headRefOid",
            "--jq",
            ".[].headRefOid",
        ],
        cwd=root,
    )
    if rc != 0:
        return False
    heads = {line.strip() for line in out.splitlines() if line.strip()}
    if not heads:
        return False
    rc, tip = _git(root, "rev-parse", "--verify", f"refs/heads/{branch}")
    return rc == 0 and tip.strip() in heads


def devbox_teardown_available(root: Path) -> bool:
    """A docker-less machine keeps the old behaviour: no run.sh, no docker or no daemon means no container to orphan."""
    run_sh = root / "run.sh"
    if not (run_sh.is_file() and os.access(run_sh, os.X_OK)):
        return False
    if not _have("docker"):
        return False
    return _capture(["docker", "info"])[0] == 0


def remove_worktree(root: Path, wt_path: Path, session: str, branch: str) -> int:
    """Remove one worktree. 1 when the devbox teardown failed and nothing was removed.

    THE DEVBOX GOES FIRST, and the order is the whole point: the container is found by a label whose value is this directory, so deleting the directory first orphans it with nothing able to name it again. A SUBPROCESS and `$ROOT/run.sh`, never `$wt/run.sh`, as the script explains. Refusing is recoverable, orphaning is not, so a failed teardown aborts the removal.
    """
    if devbox_teardown_available(root):
        log.info("Stopping devbox for %s" % wt_path)
        if _devbox(root, wt_path, "remove")[0] != 0:
            log.error("devbox teardown FAILED for %s; refusing to delete the worktree." % wt_path)
            log.error("  The directory is the container's only lookup key, so deleting it now")
            log.error("  would orphan the container permanently. Investigate, then retry:")
            log.error("    CONSOLE_ROOT_DIR='%s' '%s/run.sh' devbox remove" % (wt_path, root))
            return 1
        log.info("Devbox stopped")

    if _have("tmux") and tmux_session_exists(session):
        _capture(["tmux", "kill-session", "-t", session])
        log.info("Killed tmux session: %s" % session)

    if (
        _passthrough(
            ["git", "-C", str(root), "worktree", "remove", "--force", str(wt_path)], quiet=True
        )
        != 0
    ):
        log.warn("Could not remove worktree normally, trying sudo removal")
        # D10: `-n`, and the caller proved the path sits directly under `.worktrees`.
        _passthrough(["sudo", "-n", "rm", "-rf", "--", str(wt_path)])
        _passthrough(["git", "-C", str(root), "worktree", "prune"])
    log.info("Removed worktree: %s" % wt_path)

    # D8: never the base branch, never a detached HEAD.
    if (
        branch
        and branch not in (BASE_BRANCH, "HEAD")
        and _git_ok(root, "rev-parse", "--verify", f"refs/heads/{branch}")
    ):
        # `branch -D` reports "Deleted branch X (was <sha>)" on stdout; the script let it through.
        _passthrough(["git", "-C", str(root), "branch", "-D", branch], quiet=True)
        log.info("Deleted branch: %s" % branch)
    return 0


def _devbox(root: Path, wt_path: Path, verb: str) -> tuple[int, str]:
    rc, out = _capture(
        [str(root / "run.sh"), "devbox", verb], extra_env={"CONSOLE_ROOT_DIR": str(wt_path)}
    )
    return rc, out


# --------------------------------------------------------------------------- submodules ---------------------------------------------------------------------------


def list_submodules(path: Path | str) -> list[str]:
    rc, out = _capture(
        ["git", "config", "--file", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"],
        cwd=path,
    )
    if rc != 0:
        return []
    return [line.split(" ", 1)[1] for line in out.splitlines() if " " in line]


def _is_ancestor(path: Path | str, older: str, newer: str) -> bool:
    return _git_ok(path, "merge-base", "--is-ancestor", older, newer)


def checkout_branch_keeping_commits(path: Path | str, branch: str, label: str) -> int:
    """Check `branch` out, tracking `origin/<branch>`, WITHOUT discarding local commits (D9).

    Remote only, or local at-or-behind the remote: `checkout -B` (a fast-forward). Local ahead of or diverged from the remote: the local branch as it is.
    """
    has_remote = _git_ok(path, "rev-parse", "--verify", f"origin/{branch}")
    has_local = _git_ok(path, "rev-parse", "--verify", f"refs/heads/{branch}")
    if has_remote and (
        not has_local or _is_ancestor(path, f"refs/heads/{branch}", f"origin/{branch}")
    ):
        rc = _passthrough(
            ["git", "-C", str(path), "checkout", "-B", branch, f"origin/{branch}", "--quiet"]
        )
        if rc == 0:
            log.info("%sChecked out '%s' (tracking origin/%s)" % (label, branch, branch))
        return rc
    if has_local:
        rc = _passthrough(["git", "-C", str(path), "checkout", branch, "--quiet"])
        if rc == 0:
            if has_remote:
                log.warn(
                    "%sLocal '%s' has commits origin/%s lacks: kept as it is, not reset"
                    % (label, branch, branch)
                )
            else:
                log.info("%sChecked out local branch '%s'" % (label, branch))
        return rc
    log.info("%sCreating new branch '%s'" % (label, branch))
    return _passthrough(["git", "-C", str(path), "checkout", "-b", branch, "--quiet"])


def setup_submodule_branch(sm_path: str, branch: str, base: Path) -> int:
    full = base / sm_path
    if not (full / ".git").exists():
        log.warn("Submodule %s not initialized, skipping" % sm_path)
        return 0
    if _git(full, "fetch", "origin", "--quiet")[0] != 0:
        log.warn("Could not fetch origin for %s" % sm_path)
    return _submodule_checkout(full, sm_path, branch)


def _submodule_checkout(full: Path, sm_path: str, branch: str) -> int:
    has_remote = _git_ok(full, "rev-parse", "--verify", f"origin/{branch}")
    has_local = _git_ok(full, "rev-parse", "--verify", f"refs/heads/{branch}")
    if has_remote:
        log.info("  Checking out existing branch '%s' in %s" % (branch, sm_path))
    elif has_local:
        log.info("  Checking out local branch '%s' in %s" % (branch, sm_path))
    else:
        log.info("  Creating new branch '%s' in %s" % (branch, sm_path))
    if (
        has_remote
        and has_local
        and not _is_ancestor(full, f"refs/heads/{branch}", f"origin/{branch}")
    ):
        log.warn(
            "  Local '%s' in %s has commits origin/%s lacks: kept as it is, not reset"
            % (branch, sm_path, branch)
        )
        return _passthrough(["git", "-C", str(full), "checkout", branch, "--quiet"])
    if has_remote:
        return _passthrough(
            ["git", "-C", str(full), "checkout", "-B", branch, f"origin/{branch}", "--quiet"]
        )
    if has_local:
        return _passthrough(["git", "-C", str(full), "checkout", branch, "--quiet"])
    return _passthrough(["git", "-C", str(full), "checkout", "-b", branch, "--quiet"])


def setup_submodule_branches(branch: str, wt_path: Path) -> int:
    log.step("Setting up submodule branches...")
    for sm_path in list_submodules(wt_path):
        rc = setup_submodule_branch(sm_path, branch, wt_path)
        if rc != 0:
            return rc
    return 0


# --------------------------------------------------------------------------- commands ---------------------------------------------------------------------------


def next_sequence_number(base: Path, prefix: str) -> int:
    top = 0
    if base.is_dir():
        for entry in base.glob(f"{prefix}-*"):
            seq = entry.name[len(prefix) + 1 :]
            if entry.is_dir() and seq.isascii() and seq.isdigit():
                top = max(top, int(seq))
    return top + 1


def cmd_create(args: list[str]) -> int:
    teams = False
    no_devbox = False
    for arg in args:
        if arg in ("--teams", "-t"):
            teams = True
        elif arg == "--no-devbox":
            no_devbox = True
        else:
            log.error("Unknown option: %s" % arg)
            return 1

    root = paths.repo_root()
    base = worktree_base()
    sync_main_repo(root)

    wt_name = "%s-%d" % (time.strftime("%m%d"), next_sequence_number(base, time.strftime("%m%d")))
    wt_path = base / wt_name
    session = "%s-%s" % (TMUX_PREFIX, wt_name)

    log.step("Creating worktree: %s" % wt_name)
    base.mkdir(parents=True, exist_ok=True)

    if _git_ok(root, "rev-parse", "--verify", wt_name):
        log.error("Branch '%s' already exists" % wt_name)
        log.info("Delete it with: git branch -D %s" % wt_name)
        return 1

    log.info("Creating worktree at %s" % wt_path)
    rc = _passthrough(
        [
            "git",
            "-C",
            str(root),
            "worktree",
            "add",
            "-b",
            wt_name,
            str(wt_path),
            f"origin/{BASE_BRANCH}",
        ]
    )
    if rc != 0:
        return rc

    log.info("Initializing submodules...")
    rc = _passthrough(["git", "-C", str(wt_path), "submodule", "update", "--init", "--recursive"])
    if rc != 0:
        return rc
    rc = setup_submodule_branches(wt_name, wt_path)
    if rc != 0:
        return rc

    # A failure of the devbox does not roll the worktree back: by now the tree holds a branch plus per-submodule branches, and unwinding all of it because an image pull timed out destroys more than it saves.
    devbox_url = ""
    if not no_devbox and devbox_teardown_available(root):
        log.step("Starting devbox for %s" % wt_path)
        if _devbox(root, wt_path, "up")[0] == 0:
            _rc, url = _devbox(root, wt_path, "url")
            devbox_url = url.strip()
            log.info("Devbox started")
        else:
            log.warn("devbox did not start for %s (the worktree itself is fine)" % wt_path)
            log.warn("  retry with: CONSOLE_ROOT_DIR='%s' '%s/run.sh' devbox up" % (wt_path, root))

    create_tmux_session(session, wt_path, teams)

    private_install = (
        "for pj in $(find private/ -maxdepth 2 -name package.json ! -path '*/node_modules/*' 2>/dev/null); "
        'do echo "Installing deps in $(dirname $pj)..." && (cd $(dirname $pj) && npm install) || true; done'
    )
    if _have("tmux") and tmux_session_exists(session):
        log.info("Running npm install + build:packages in tmux session...")
        if teams:
            keys = (
                "npm install && npm run build:packages && %s && tmux split-window -v -l 25%% -c '%s' && clear && "
                "claude --dangerously-skip-permissions --teammate-mode tmux"
                % (private_install, wt_path)
            )
        else:
            keys = (
                "npm install && npm run build:packages && %s && tmux split-window -v -l 25%% -c '%s' && "
                "RIGHT_PANE=$(tmux split-window -h -c '%s' -P -F '#{pane_id}') && "
                "tmux send-keys -t \"$RIGHT_PANE\" 'claude --dangerously-skip-permissions' C-m && "
                "clear && claude --dangerously-skip-permissions"
                % (private_install, wt_path, wt_path)
            )
        _passthrough(["tmux", "send-keys", "-t", f"{session}:0", keys, "C-m"])
    else:
        log.info("Run the following in the worktree to set up dependencies:")
        log.info("  npm install && npm run build:packages")
        log.info("  # Install submodule deps (not in npm workspaces):")
        log.info("  (cd private/account && npm install)")

    _out()
    log.info("Worktree created successfully!")
    _out()
    _out("  Path:    %s" % wt_path)
    _out("  Branch:  %s" % wt_name)
    if devbox_url:
        _out("  Devbox:  %s" % devbox_url)
    elif no_devbox:
        _out("  Devbox:  skipped (--no-devbox)")
    if teams:
        _out("  Teams:   enabled (lead + teammate tmux panes)")
    if _have("tmux"):
        _out("  Session: %s" % session)
        _out()
        _out("Attach with: tmux attach -t %s" % session)
    return 0


def cmd_list(args: list[str]) -> int:
    if args:
        log.error("Unexpected argument: %s" % args[0])
        return 1
    root = paths.repo_root()
    base = worktree_base()
    log.step("Console worktrees")
    _out()
    if not base.is_dir():
        log.info("No worktrees found")
        return 0
    found = False
    for line in listed_worktrees(root):
        if not under_base(line, base):
            continue
        found = True
        wt_name = os.path.basename(line)
        branch = ""
        if os.path.isdir(line):
            branch = current_branch(line) or "unknown"
        status = "no session"
        session = "%s-%s" % (TMUX_PREFIX, wt_name)
        if _have("tmux") and tmux_session_exists(session):
            status = session
        _out("  %-12s  branch: %-12s  tmux: %s" % (wt_name, branch, status))
    if not found:
        log.info("No worktrees found in %s" % base)
    return 0


def cmd_remove(args: list[str]) -> int:
    if not args:
        log.error("Usage: ./run.sh worktree remove <name>")
        log.info("Use './run.sh worktree list' to see available worktrees")
        return 1
    if len(args) > 1:
        log.error("Unexpected argument: %s" % args[1])
        return 1
    wt_name = args[0]
    if not NAME_RE.match(wt_name):
        log.error(
            "Invalid worktree name: %s (a directory name under .worktrees, not a path)" % wt_name
        )
        return 1
    root = paths.repo_root()
    wt_path = worktree_base() / wt_name
    if wt_path.is_symlink() or not wt_path.is_dir():
        log.error("Worktree not found: %s" % wt_name)
        log.info("Use './run.sh worktree list' to see available worktrees")
        return 1
    rc, out = _git(wt_path, "rev-parse", "--abbrev-ref", "HEAD")
    branch = out.strip() if rc == 0 and out.strip() else wt_name
    dirty = dirty_paths(wt_path)
    log.step("Removing worktree: %s" % wt_name)
    if dirty:
        log.warn("Discarding %d uncommitted or untracked path(s) in %s" % (len(dirty), wt_name))
    rc = remove_worktree(root, wt_path, "%s-%s" % (TMUX_PREFIX, wt_name), branch)
    if rc != 0:
        return rc
    log.info("Done")
    return 0


def cmd_prune(args: list[str]) -> int:
    if args:
        log.error("Unexpected argument: %s" % args[0])
        return 1
    if not _have("gh"):
        log.error("gh CLI is required for prune command")
        log.info("Install from: https://cli.github.com/")
        return 1
    root = paths.repo_root()
    base = worktree_base()
    sync_main_repo(root)

    log.step("Checking for worktrees to clean up...")
    _out()
    if not base.is_dir():
        log.info("No worktrees found")
        return 0

    found = False
    failed: list[str] = []
    ref = base_ref(root)
    here = os.path.realpath(os.getcwd())
    for line in listed_worktrees(root):
        if not under_base(line, base):
            continue
        wt_name = os.path.basename(line)
        session = "%s-%s" % (TMUX_PREFIX, wt_name)
        branch = current_branch(line) if os.path.isdir(line) else ""
        if not branch or branch in (BASE_BRANCH, "HEAD"):
            continue
        reason = ""
        if pr_merged_at_tip(root, branch):
            reason = "PR MERGED"
        else:
            rc, ahead = _git(root, "rev-list", "--count", f"{ref}..{branch}")
            if rc == 0 and ahead.strip() == "0":
                reason = "NO COMMITS, NO CHANGES"
        if not reason:
            continue
        dirty = dirty_paths(line)
        if dirty:
            found = True
            _out(
                "  %s (branch: %s) - kept, %d uncommitted or untracked path(s)"
                % (wt_name, branch, len(dirty))
            )
            _out()
            continue
        if here == os.path.realpath(line) or here.startswith(os.path.realpath(line) + os.sep):
            found = True
            _out("  %s (branch: %s) - kept, this command runs from it" % (wt_name, branch))
            _out()
            continue
        found = True
        _out("  %s (branch: %s) - %s" % (wt_name, branch, reason))
        # COLLECT, do not abort: one wedged devbox must not stop the sweep, and the summary must not read as a completed prune.
        if remove_worktree(root, Path(line), session, branch) != 0:
            failed.append(wt_name)
        _out()

    if failed:
        log.error("%d worktree(s) could NOT be removed:" % len(failed))
        for name in failed:
            log.error("  %s" % name)
        log.error("Their devbox containers are still running and their directories are intact.")
        log.error("A partial sweep must not exit 0, or a caller reads it as a completed prune.")
        return 1
    if not found:
        log.info("No worktrees to clean up")
    _git(root, "worktree", "prune")
    return 0


def cmd_switch(args: list[str]) -> int:
    branch = ""
    for arg in args:
        if arg.startswith("-"):
            log.error("Unknown option: %s" % arg)
            return 1
        if not branch:
            branch = arg
        else:
            log.error("Unexpected argument: %s" % arg)
            return 1
    if not branch:
        log.error("Usage: ./run.sh worktree switch <branch>")
        log.info("Specify the branch name to switch to.")
        return 1

    rc, out = _capture(["git", "rev-parse", "--show-toplevel"])
    if rc != 0 or not out.strip():
        log.error("Not inside a git repository")
        return 1
    repo_dir = Path(out.strip())

    if _capture(["git", "check-ref-format", "--branch", branch])[0] != 0:
        log.error("Invalid branch name: %s" % branch)
        return 1

    dirty = dirty_paths(repo_dir)
    if dirty:
        log.warn("%s has %d uncommitted or untracked path(s)" % (repo_dir, len(dirty)))
        log.warn("Please commit or stash them before switching branches.")
        return 1
    for sm_path in list_submodules(repo_dir):
        full = repo_dir / sm_path
        if (full / ".git").exists():
            sm_dirty = dirty_paths(full)
            if sm_dirty:
                log.warn(
                    "Submodule %s has %d uncommitted or untracked path(s)"
                    % (sm_path, len(sm_dirty))
                )
                log.warn("Please commit or stash them before switching branches.")
                return 1

    log.step("Fetching latest changes...")
    rc = _passthrough(["git", "-C", str(repo_dir), "fetch", "origin", "--quiet"])
    if rc != 0:
        return rc

    if not _git_ok(repo_dir, "rev-parse", "--verify", f"origin/{branch}") and not _git_ok(
        repo_dir, "rev-parse", "--verify", f"refs/heads/{branch}"
    ):
        log.error("Branch '%s' not found (checked both local and origin)" % branch)
        return 1

    log.step("Switching to branch '%s'..." % branch)
    rc = checkout_branch_keeping_commits(repo_dir, branch, "")
    if rc != 0:
        return rc

    log.step("Syncing submodules...")
    rc = _passthrough(["git", "-C", str(repo_dir), "submodule", "sync", "--quiet"])
    if rc == 0:
        rc = _passthrough(["git", "-C", str(repo_dir), "submodule", "update", "--init", "--quiet"])
    if rc != 0:
        return rc
    for sm_path in list_submodules(repo_dir):
        rc = setup_submodule_branch(sm_path, branch, repo_dir)
        if rc != 0:
            return rc

    _out()
    log.info("Switched to branch '%s'" % branch)
    _out("  Path: %s" % repo_dir)
    return 0


COMMANDS = {
    "create": cmd_create,
    "list": cmd_list,
    "remove": cmd_remove,
    "switch": cmd_switch,
    "prune": cmd_prune,
}


def main(argv: list[str]) -> int:
    """`worktree <command> [args]`. Help is decided from argv alone, before any git call (D1)."""
    command = argv[0] if argv else ""
    rest = argv[1:]
    if command in ("", "help", *HELP_FLAGS):
        sys.stdout.write(MAIN_HELP)
        return 0
    handler = COMMANDS.get(command)
    if handler is None:
        log.error("Unknown command: %s" % command)
        _out()
        sys.stdout.write(MAIN_HELP)
        return 1
    if any(arg in HELP_FLAGS for arg in rest):
        sys.stdout.write(SUBCOMMAND_HELP[command])
        return 0
    return handler(rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
