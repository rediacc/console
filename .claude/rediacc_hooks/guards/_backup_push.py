"""The shared backup-ref predicate of the pre-bash push guards (box G5 of agent/plans/PLAN-local-first-delivery.md).

WHY. A backup push (`git push gitlab <tip>:refs/backup/<branch>/live`, Design G of that plan) sends unpushed work to the repository's own pinned GitLab project. It moves no branch, triggers no CI and needs no receipt (operator ruling R1), and the git-level `pre-push` hook judges it in full (`githooks.backup_ref_refusal`: the pin, nothing else in the push, create or fast-forward, immutable snapshots, the session-link and secret scans). Before this the pre-bash guards read it as an ordinary push: a ci:quick receipt was asked for it, and `block_second_branch` read `refs/backup/<b>/live` as a second remote branch.

ONE FUNCTION, `admitted(ev, cmd)`. Each push guard calls it first and returns ALLOW when it is true; every other command is judged exactly as before. It is True only when ALL of these hold, and anything it cannot read makes it False, so a doubtful push is judged as before rather than waved through:

  - every simple command bash would run is a `cd` or a `git push`, at least one push, every word literal (no expansion the walk could not evaluate, no `eval`, `sh -c`, pipeline partner or command substitution doing anything else);
  - no `GIT_*` variable in a push's environment and no global option but `-C <dir>`: `-c remote.<r>.pushurl=...` or `GIT_CONFIG_*` would send the push somewhere the URL check below never saw;
  - no flag but `--quiet`, `--verbose`, `--porcelain` and `--atomic` (`--force`, `--force-with-lease`, `--mirror`, `--all`, `--tags`, `--delete`, `--no-verify`, `--push-option` and every other one are refused), and every refspec is `<src>:refs/backup/<branch>/<leaf>` with no `+`, no glob and no pin source (`refs/worktrees/`);
  - an empty source (a delete) only in the worker's rewrite form: `:refs/backup/<b>/live` under `--atomic` beside a refspec creating `refs/backup/<b>/pre-rewrite-*`, the pairing `pre-push` itself checks;
  - the push runs in this checkout (the console or a submodule below it), names a configured remote, and every push URL `git remote get-url --push --all <remote>` reports is that repository's pin (`githooks.backup_url_refusal`, whose map `BACKUP_PATHS` and URL rule are the git hook's own, so both layers agree on what the pin is). `origin` (public GitHub) is never it.
"""

import importlib.util
import os
import re
import subprocess
import sys

from rediacc_hooks import commit_policy, hookio, shellscan
from rediacc_hooks.wellknown import GH_ORIGIN, GH_REPO

_GITHOOKS_NAME = "rediacc_hooks._githooks"
_GITHOOKS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(hookio.__file__)), "git", "githooks.py"
)

ALLOWED_FLAGS = frozenset(("quiet", "verbose", "porcelain", "atomic"))
REMOTE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# `refs/backup/<branch>/<leaf>`, the branch at least one component: `githooks._split_backup_ref` reads the last component as the leaf.
BACKUP_DST = re.compile(
    r"^refs/backup/(?:[A-Za-z0-9_-][A-Za-z0-9._-]*/)+[A-Za-z0-9_-][A-Za-z0-9._-]*$"
)
SOURCE = re.compile(r"^[A-Za-z0-9_./^~@{}-]+$")


def githooks():
    """The git-level hook module, loaded by file once per process (the name block_push_to_protected_branch loads it under), None when it cannot load."""
    module = sys.modules.get(_GITHOOKS_NAME)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(_GITHOOKS_NAME, _GITHOOKS_FILE)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError, SystemExit):
        return None
    sys.modules[_GITHOOKS_NAME] = module
    return module


def _literal(run):
    """Whether every word of a walked command is the word bash will pass."""
    return (
        run.xargv is not None
        and run.xargv == run.argv
        and not any(shellscan.unresolved(w) for w in run.xargv)
    )


def _refspecs(specs):
    """The refspecs when every one is an admitted backup destination (module docstring), else None. Each is `(src, dst)`, `src` "" for a delete."""
    out = []
    for spec in specs:
        if spec.startswith("+") or spec.count(":") != 1:
            return None
        src, _, dst = spec.partition(":")
        if not BACKUP_DST.match(dst) or ".." in dst or dst.endswith(".lock"):
            return None
        if src and (not SOURCE.match(src) or src.startswith("refs/worktrees/") or ".." in src):
            return None
        out.append((src, dst))
    return out


def _deletes_paired(pairs, atomic):
    """Whether every delete is the rewrite form: `live`, under `--atomic`, beside a created `pre-rewrite-*` of the same branch."""
    for src, dst in pairs:
        if src:
            continue
        branch, _, leaf = dst[len("refs/backup/") :].rpartition("/")
        if not atomic or leaf != "live":
            return False
        if not any(s and d.startswith("refs/backup/%s/pre-rewrite-" % branch) for s, d in pairs):
            return False
    return True


def _push_admitted(run, base, root, hooks):
    if any(name.startswith("GIT_") for name in (run.env or {})):
        return False
    globals_, sub, args = commit_policy.git_split(run.argv)
    if sub != "push":
        return False
    k = 0
    while k < len(globals_):
        if globals_[k] != "-C" or k + 1 >= len(globals_):
            return False
        k += 2
    parsed = shellscan.git_push_args(args)
    if parsed.problems:
        return False
    atomic = False
    for name, value in parsed.flags:
        if name not in ALLOWED_FLAGS:
            return False
        if name == "atomic":
            atomic = value == "true"
    operands = list(parsed.operands)
    if len(operands) < 2 or not REMOTE_NAME.match(operands[0]):
        return False
    pairs = _refspecs(operands[1:])
    if pairs is None or not _deletes_paired(pairs, atomic):
        return False
    repo = commit_policy.run_repo(run, base)
    if not repo or not commit_policy.is_inside(repo, root):
        return False
    urls = commit_policy.git(["remote", "get-url", "--push", "--all", operands[0]], cwd=repo)
    lines = [u for u in (urls or "").split("\n") if u.strip()]
    if not lines:
        return False
    return all(hooks.backup_url_refusal(repo, url) == "" for url in lines)


def admitted(ev, cmd):
    """True only when every push in `cmd` is an admitted backup-ref push to its repository's pin, and the command does nothing else (module docstring). False whenever unsure."""
    pushes = []
    for run in commit_policy.runs(cmd):
        if not _literal(run):
            return False
        # The bare program names only (review 2577b833.1): `./git` or `/tmp/x/git` is another program, never git.
        name = run.name or ""
        if name == "cd":
            continue
        if name == "git" and run.git_sub == "push":
            pushes.append(run)
            continue
        return False
    if not pushes:
        return False
    root = ev.env("CLAUDE_PROJECT_DIR") or commit_policy.git(["rev-parse", "--show-toplevel"]) or ""
    if not root:
        return False
    hooks = githooks()
    if hooks is None:
        return False
    base = ev.field("cwd") or root
    return all(_push_admitted(run, base, root, hooks) for run in pushes)


# --------------------------------------------------------------------------- the harness fixture ---------------------------------------------------------------------------
#
# THE SHARED CASES (box G5). Every push guard's harness plants these remotes into one of its own worlds where an ordinary push is refused, and runs `CASES` through its own driver: the admitted case must be allowed, and every other one judged as before, which in that world is a refusal. `pinned` names the world: True is `plant(repo)`, False is `plant(repo, pinned=False)`, a `gitlab` remote whose URL is NOT the pin.
FIXTURE_ORIGIN = "%s/%s.git" % (GH_ORIGIN, GH_REPO)
# An origin that is not the console, shared by every fixture repository that needs a remote the pin does not match.
OTHER_ORIGIN = "%s/fixture/console.git" % GH_ORIGIN
NOT_PIN_PATH = "/rediacc-org/github/not-console.git"
BACKUP_PUSH = "git push gitlab HEAD:refs/backup/1104-1/live"
CASES = (
    # (label, command, pinned world, admitted)
    ("G5 refs/backup to the pinned gitlab", BACKUP_PUSH, True, True),
    (
        "G5 control: refs/backup to origin",
        "git push origin HEAD:refs/backup/1104-1/live",
        True,
        False,
    ),
    (
        "G5 control: refs/heads to the pinned gitlab",
        "git push gitlab HEAD:refs/heads/x",
        True,
        False,
    ),
    (
        "G5 a mixed push, refs/backup plus refs/heads",
        "git push gitlab HEAD:refs/backup/1104-1/live HEAD:refs/heads/y",
        True,
        False,
    ),
    ("G5 a + refspec to refs/backup", "git push gitlab +HEAD:refs/backup/1104-1/live", True, False),
    (
        "G5 --force to refs/backup",
        "git push --force gitlab HEAD:refs/backup/1104-1/live",
        True,
        False,
    ),
    ("G5 a gitlab remote that is not the pin", BACKUP_PUSH, False, False),
)


def plant(repo, pinned=True):
    """Make the fixture repository `repo` console-shaped for `admitted`: a `.gitmodules` file (kept out of `git status` through `info/exclude` when it was not there), a `gitlab` remote at the pin (or, with `pinned=False`, at another project on the same host), and an `origin` at GitHub when it has none. Returns `repo`."""
    hooks = githooks()
    if hooks is None:
        raise SystemExit("_backup_push.plant: %s does not load" % _GITHOOKS_FILE)
    repo = str(repo)
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=env
        ).stdout.strip()

    gitmodules = os.path.join(repo, ".gitmodules")
    if not os.path.exists(gitmodules):
        with open(gitmodules, "w", encoding="utf-8"):
            pass
        exclude = os.path.join(repo, git("rev-parse", "--git-path", "info/exclude"))
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as fh:
            fh.write("\n/.gitmodules\n")
    url = "https://%s%s" % (hooks.MIRROR_HOST, hooks.BACKUP_PATHS[""] if pinned else NOT_PIN_PATH)
    remotes = git("remote").split()
    git("remote", "set-url" if "gitlab" in remotes else "add", "gitlab", url)
    if "origin" not in remotes:
        git("remote", "add", "origin", FIXTURE_ORIGIN)
    return repo
