"""The commit policy, as one module both enforcement layers read (the commit-policy plan in agent/plans, sections 2, 4 and 5).

WHAT IT DECIDES. Four rules, each stated once here and enforced twice:

  * ONE BRANCH. Each repository (the console and every submodule under `private/`) holds at most one live non-`main` local branch, named `MMDD-N`, and a submodule's branch carries the console's name. `branch_creations` finds every spelling of creating a branch in a Bash command; `live_branches` and `next_branch_name` answer whether that creation is allowed.
  * `[hotfix]` ON `main` ONLY. A commit on `main` must carry the tag at the end of its subject, a `Hotfix-Evidence:` trailer and at most `hotfix_max_files` paths (`hotfix_ok`). Off `main` the tag is refused, so the audit stays clean.
  * `[no-review]` ONLY ON WRITING. Every path must match `no_review_eligible` and none `no_review_denied` (`no_review_eligible`). The tag never rides a `[hotfix]` (operator ruling 1, 2026-09-25: hotfixes are always reviewed).
  * NO CI SKIP TOKENS in a commit an agent writes (`skip_tokens`). A skipped workflow leaves the required `CI Complete` check at "Expected" forever.

WHO READS IT. The pre-bash guards `block_second_branch`, `block_commit_on_main`, `block_ci_skip_token`, `block_no_review_ineligible` and `block_nonstandard_branch_name`, which import it as `rediacc_hooks.commit_policy`; and the git-level hooks under `.claude/rediacc_hooks/git/`, which load it BY FILE because git runs them with no package context. That second reader is why this module is stdlib-only and why the one import of `shellscan` sits inside the functions that parse a Bash command: a git hook never parses one, so it never pays for (or depends on) the lexer.

WHY `branch_creations` IS BUILT ON THE LEXER. F1 of the plan: `block_nonstandard_branch_name` refused a read-only `grep -n -e "checkout -b" -e "git branch [a-z0-9]"` because its quote-blind regexes read the quoted pattern as a branch being created. `shellscan._analyse` walks what bash would RUN, so a quoted pattern is an argument of `grep` and never a `git` invocation, while a `sh -c '...'` payload and an `eval` are still walked.

THE CONFIG IS `.ci/config/commit-policy.json`. `load_config` falls back to `DEFAULTS` per key when the file is missing or unreadable, so a broken config never crashes a guard into letting everything through; the defaults are the file's own values, and `test-block_commit_on_main.py` asserts the two agree.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import typing

ZERO_OID = "0" * 40

# The one override for the GIT-LEVEL hooks (operator ruling 2, 2026-09-25). The pre-bash guards never honour it, and `block_git_hook_bypass` refuses an agent command that sets it.
OVERRIDE_ENV = "COMMIT_POLICY_OK"

CONFIG_REL = (".ci", "config", "commit-policy.json")

DEFAULTS: dict[str, typing.Any] = {
    "no_review_eligible": ["agent/**", "docs/**", "**/*.md"],
    "no_review_denied": [".claude/**", "CLAUDE.md", "**/CLAUDE.md"],
    "hotfix_max_files": 5,
    "skip_tokens": [
        "[skip ci]",
        "[ci skip]",
        "[no ci]",
        "[skip actions]",
        "[actions skip]",
        "[no-ci]",
    ],
    "branch_shape": "^[0-9]{4}-[0-9]+$",
}

# `skip-checks: true` is GitHub's trailer form of the same skip, matched on a line of its own.
SKIP_TRAILER = re.compile(r"(?im)^[ \t]*skip-checks[ \t]*:[ \t]*true[ \t]*$")

# A tag is a bracketed word in the SUBJECT line. Spaces are not allowed inside, so `[skip ci]` is never read as a tag; it is `skip_tokens`' business.
TAG = re.compile(r"\[([A-Za-z][A-Za-z0-9-]*)\]")

HOTFIX_EVIDENCE = re.compile(r"(?im)^[ \t]*Hotfix-Evidence[ \t]*:[ \t]*(\S.*?)[ \t]*$")
# A red main run: a bare run id, or an Actions run URL.
EVIDENCE_RUN = re.compile(
    r"^(?:[0-9]{6,}|https://github\.com/[^/\s]+/[^/\s]+/actions/runs/[0-9]+\S*)$"
)
# The operator called it a hotfix in this task, at this UTC minute.
EVIDENCE_ASKED = re.compile(r"^ASKED:[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z?$")


class Creation(typing.NamedTuple):
    """One branch a command would create.

    `kind` is how: checkout-b, switch-c, branch, copy, rename, worktree, push, gh-pr-create or gh-api-ref. `repo_root` is the repository it lands in ("" when the directory does not resolve to one).
    """

    repo_root: str
    name: str
    kind: str


class GhUnavailableError(RuntimeError):
    """`gh` could not answer, so liveness is unknown. A creation judged on an unknown answer is refused."""


# --------------------------------------------------------------------------- config ---------------------------------------------------------------------------


def config_path(root: str | os.PathLike | None = None) -> pathlib.Path:
    base = pathlib.Path(root) if root else pathlib.Path(__file__).resolve().parents[2]
    return base.joinpath(*CONFIG_REL)


def load_config(root: str | os.PathLike | None = None) -> dict[str, typing.Any]:
    """The config's `value`s by key, each falling back to `DEFAULTS` on its own."""
    out = dict(DEFAULTS)
    try:
        doc = json.loads(config_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    if not isinstance(doc, dict):
        return out
    for key, default in DEFAULTS.items():
        entry = doc.get(key)
        value = entry.get("value") if isinstance(entry, dict) else None
        if isinstance(value, type(default)):
            out[key] = value
    return out


# --------------------------------------------------------------------------- git, as a command substitution ---------------------------------------------------------------------------


# The variables that pin git to ONE repository. Git exports them to every hook it runs (a submodule's `reference-transaction` sees the submodule's `GIT_DIR`), so a hook asking about ANOTHER repository -- the superproject's branch -- has to drop them, or git answers about the submodule again.
REPO_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


def git(args: list[str], cwd: str | None = None, foreign: bool = False) -> str | None:
    """`git <args>` stdout with trailing newlines removed, or None on a non-zero exit or a missing git.

    `foreign=True` runs it with `REPO_ENV` removed, for a question about a repository other than the one git is running a hook in.
    """
    env = {k: v for k, v in os.environ.items() if k not in REPO_ENV} if foreign else None
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd or None, capture_output=True, check=False, timeout=30, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def toplevel(directory: str) -> str:
    """The repository `directory` sits in, "" when none."""
    if not directory or not os.path.isdir(directory):
        return ""
    return git(["rev-parse", "--show-toplevel"], cwd=directory) or ""


def current_branch(repo_root: str, foreign: bool = False) -> str:
    """The checked-out branch, "" when detached or unresolvable."""
    return git(["symbolic-ref", "--short", "-q", "HEAD"], cwd=repo_root, foreign=foreign) or ""


def local_branches(repo_root: str) -> list[str]:
    out = git(["for-each-ref", "--format=%(refname:short)", "refs/heads/"], cwd=repo_root)
    return [b for b in (out or "").split("\n") if b]


def is_inside(path: str, root: str) -> bool:
    """Whether `path` is `root` or below it, both resolved."""
    if not path or not root:
        return False
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base + os.sep)


def superproject(repo_root: str) -> str:
    """The superproject's toplevel when `repo_root` is a submodule, else ""."""
    return git(["rev-parse", "--show-superproject-working-tree"], cwd=repo_root) or ""


# --------------------------------------------------------------------------- branches ---------------------------------------------------------------------------


def _gh_lines(repo_root: str, args: list[str]) -> list[str]:
    """`gh <args>` stdout words, raising `GhUnavailableError` when gh cannot answer."""
    try:
        proc = subprocess.run(
            ["gh", *args], cwd=repo_root, capture_output=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GhUnavailableError(str(exc)) from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise GhUnavailableError(err or "gh exited %d" % proc.returncode)
    return proc.stdout.decode("utf-8", "replace").split()


# `gh pr list --head <branch> ...` (the branch goes after `--head`) and the day's consumed heads.
GH_PR_STATES = ("pr", "list", "--head", "--state", "all", "--json", "state", "--jq", ".[].state")
GH_PR_HEADS = (
    *("pr", "list", "--state", "all", "--limit", "100"),
    *("--json", "headRefName", "--jq", ".[].headRefName"),
)


def _gone_upstream(repo_root: str, branch: str) -> bool:
    track = git(
        ["for-each-ref", "--format=%(upstream:track)", "refs/heads/" + branch], cwd=repo_root
    )
    return (track or "").strip() == "[gone]"


def live_branches(repo_root: str, gh: bool = True) -> list[str]:
    """The live non-`main` local branches.

    A branch stops being live once its PR is MERGED or CLOSED and none is OPEN (`gh=True`, raising `GhUnavailableError` when gh cannot answer). With `gh=False`, the git-level reading, the only local signal is an upstream that is configured and gone (`[gone]` after a prune), which is what a merged-and-deleted PR head leaves behind.
    """
    out = []
    for branch in local_branches(repo_root):
        if branch == "main":
            continue
        if gh:
            states = _gh_lines(repo_root, [*GH_PR_STATES[:3], branch, *GH_PR_STATES[3:]])
            if states and "OPEN" not in states:
                continue
        elif _gone_upstream(repo_root, branch):
            continue
        out.append(branch)
    return out


def next_branch_name(repo_root: str, today: str, gh: bool = True) -> str:
    """Today's `MMDD-(MAX+1)`.

    MAX comes from every name the day has consumed: PR heads (a merged PR's branch is deleted, so only `gh` still remembers it; the 2026-08-26 double pick of 0826-1 is why), local branches and remote-tracking refs. `today` is passed in rather than read here, so the guard that calls this is the one holding the clock and the differential's frozen clock reaches it. With `gh=True` a `gh` that cannot answer raises `GhUnavailableError`: a MAX computed without the consumed heads is exactly how a name gets picked twice.
    """
    names = list(local_branches(repo_root))
    remotes = git(["for-each-ref", "--format=%(refname:lstrip=3)", "refs/remotes/"], cwd=repo_root)
    names.extend(r for r in (remotes or "").split("\n") if r)
    if gh:
        names.extend(_gh_lines(repo_root, list(GH_PR_HEADS)))
    top = 0
    pat = re.compile(r"^%s-([0-9]+)$" % re.escape(today))
    for name in names:
        match = pat.match(name)
        if match:
            top = max(top, int(match.group(1)))
    return "%s-%d" % (today, top + 1)


# --------------------------------------------------------------------------- parsing git invocations ---------------------------------------------------------------------------

_GIT_GLOBAL_WITH_VALUE = frozenset(
    (
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--super-prefix",
        "--config-env",
        "--exec-path",
    )
)


def git_split(argv: list[str]) -> tuple[list[str], str, list[str]]:
    """`(global options, subcommand, subcommand args)` for a `git` argv (the name excluded)."""
    k = 0
    while k < len(argv):
        arg = argv[k]
        if arg in _GIT_GLOBAL_WITH_VALUE and k + 1 < len(argv):
            k += 2
            continue
        if arg.startswith("-"):
            k += 1
            continue
        return argv[:k], arg, argv[k + 1 :]
    return argv, "", []


def _base(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def runs(cmd: str) -> list:
    """Every simple command bash would run in `cmd`, from the shared lexer's walk."""
    from rediacc_hooks import shellscan  # noqa: PLC0415 -- see the module docstring

    return list(shellscan._analyse(cmd).runs)


def run_dir(run, base: str) -> str:
    """The absolute directory a walked command runs in, from `base`."""
    rel = run.git_dir if run.git_sub is not None else run.cwd
    if rel in (None, "", "."):
        return base
    return os.path.normpath(rel if rel.startswith("/") else os.path.join(base, rel))


def git_runs(cmd: str, sub: str | None = None) -> list:
    """Every `git` invocation bash would run in `cmd` (optionally only subcommand `sub`), in order."""
    return [r for r in runs(cmd) if _base(r.name) == "git" and (sub is None or r.git_sub == sub)]


def run_repo(run, base: str) -> str:
    """The toplevel of the repository a walked command acts on, "" when it resolves to none."""
    return toplevel(run_dir(run, base))


_BRANCH_READS = frozenset(
    (
        "-d",
        "-D",
        "--delete",
        "-r",
        "--remotes",
        "-a",
        "--all",
        "-v",
        "-vv",
        "--verbose",
        "-l",
        "--list",
        "--show-current",
        "--contains",
        "--no-contains",
        "--merged",
        "--no-merged",
        "--points-at",
        "--edit-description",
        "-u",
        "--set-upstream-to",
        "--unset-upstream",
        "--sort",
        "--format",
        "--column",
    )
)
_BRANCH_RENAME = frozenset(("-m", "-M", "--move"))
_BRANCH_COPY = frozenset(("-c", "-C", "--copy"))


def _branch_creation(args: list[str]) -> tuple[str, str] | None:
    """`(name, kind)` for `git branch <args>`, or None for a read, a delete or a list."""
    flags = [a for a in args if a.startswith("-")]
    positionals = [a for a in args if not a.startswith("-")]
    if any(f.split("=", 1)[0] in _BRANCH_READS for f in flags):
        return None
    if not positionals:
        return None
    if any(f in _BRANCH_RENAME for f in flags):
        return positionals[-1], "rename"
    if any(f in _BRANCH_COPY for f in flags):
        return positionals[-1], "copy"
    return positionals[0], "branch"


def _flag_value(args: list[str], names: tuple[str, ...]) -> str | None:
    """The value of the first of `names` in `args`: `-b x`, `-bx` (short) or `--flag=x` / `--flag x`."""
    for k, arg in enumerate(args):
        if arg == "--":
            return None
        for name in names:
            if arg == name:
                return args[k + 1] if k + 1 < len(args) else None
            if name.startswith("--") and arg.startswith(name + "="):
                return arg[len(name) + 1 :]
            if not name.startswith("--") and arg.startswith(name) and len(arg) > len(name):
                return arg[len(name) :]
    return None


_PUSH_WITH_VALUE = frozenset(("--repo", "-o", "--push-option", "--receive-pack", "--exec"))


def push_destinations(args: list[str]) -> list[tuple[str, str]]:
    """`(src, dst)` branch names for `git push <args>`, `refs/heads/` stripped.

    Delete forms, `--all`, `--mirror` and `--tags` name no branch being created and give nothing; so does a destination outside `refs/heads/`.
    """
    if any(a in ("--delete", "-d", "--all", "--mirror", "--tags") for a in args):
        return []
    positionals = []
    k = 0
    while k < len(args):
        arg = args[k]
        if arg == "--":
            positionals.extend(args[k + 1 :])
            break
        if arg in _PUSH_WITH_VALUE:
            k += 2
            continue
        if arg.startswith("-"):
            k += 1
            continue
        positionals.append(arg)
        k += 1
    out = []
    for raw in positionals[1:]:
        spec = raw.removeprefix("+")
        src, colon, dst = spec.partition(":")
        if not colon:
            dst = src
        if src == "" and colon:
            continue
        if dst.startswith("refs/") and not dst.startswith("refs/heads/"):
            continue
        out.append((src, dst.removeprefix("refs/heads/")))
    return out


def _git_creations(run, start: str) -> list[Creation]:
    _, sub, args = git_split(run.argv)
    found: list[tuple[str, str]] = []
    if sub == "checkout":
        value = _flag_value(args, ("-b", "-B", "--orphan"))
        if value:
            found.append((value, "checkout-b"))
    elif sub == "switch":
        value = _flag_value(args, ("-c", "-C", "--create", "--force-create", "--orphan"))
        if value:
            found.append((value, "switch-c"))
    elif sub == "branch":
        hit = _branch_creation(args)
        if hit:
            found.append(hit)
    elif sub == "worktree" and args[:1] == ["add"]:
        value = _flag_value(args[1:], ("-b", "-B"))
        if value:
            found.append((value, "worktree"))
    elif sub == "push":
        repo = run_repo(run, start)
        heads = set(local_branches(repo)) if repo else set()
        for src, dst in push_destinations(args):
            # `git push origin v1.2` pushes a TAG, and so does `v1.2:v1.2`: a destination is a branch being named only when its source is not a tag, and a bare refspec only when it IS a local branch (anything else is a tag, a sha, or a refspec git itself will refuse).
            if not dst or (
                repo
                and git(["show-ref", "--verify", "-q", "refs/tags/" + src], cwd=repo) is not None
            ):
                continue
            if src == dst and src not in heads:
                continue
            found.append((dst, "push"))
        return [Creation(repo, name, kind) for name, kind in found]
    if not found:
        return []
    repo = run_repo(run, start)
    return [Creation(repo, name, kind) for name, kind in found]


def _gh_creations(run, start: str) -> list[Creation]:
    argv = run.argv
    if argv[:2] == ["pr", "create"]:
        value = _flag_value(argv[2:], ("--head", "-H"))
        if value:
            return [
                Creation(toplevel(run_dir(run, start)), value.rsplit(":", 1)[-1], "gh-pr-create")
            ]
        return []
    if argv[:1] == ["api"] and any("git/refs" in a for a in argv[1:]):
        method = _flag_value(argv[1:], ("--method", "-X")) or ""
        fields = [
            a
            for k, a in enumerate(argv)
            if k > 0 and argv[k - 1] in ("-f", "-F", "--field", "--raw-field")
        ]
        if method.upper() == "POST" or (not method and fields):
            ref = next((f.split("=", 1)[1] for f in fields if f.startswith("ref=")), "")
            name = ref.removeprefix("refs/heads/")
            return [Creation(toplevel(run_dir(run, start)), name, "gh-api-ref")]
    return []


def branch_creations(cmd: str, root: str, base: str | None = None) -> list[Creation]:
    """Every branch `cmd` would create, in every spelling, as bash would run it.

    `root` is this checkout; `base` is the directory the command starts in (the Bash tool's `cwd`), defaulting to `root`. A creation's `repo_root` is resolved from each invocation's own `cd`/`-C`, so the caller can exempt a repository outside `root` and apply the submodule rule inside it. A `rename` is reported too, so a name check still sees the new name; the one-branch rule lets it through, because the count stays at one.
    """
    start = base or root
    out: list[Creation] = []
    for run in runs(cmd):
        name = _base(run.name)
        if name == "git":
            out.extend(_git_creations(run, start))
        elif name == "gh":
            out.extend(_gh_creations(run, start))
    return out


# --------------------------------------------------------------------------- commit messages and paths ---------------------------------------------------------------------------

_COMMIT_WITH_VALUE = frozenset(
    (
        "--message",
        "--file",
        "--reuse-message",
        "--reedit-message",
        "--author",
        "--date",
        "--cleanup",
        "--fixup",
        "--squash",
        "--template",
        "--trailer",
        "--pathspec-from-file",
    )
)
# Short options whose value is the rest of the bundle or the next word: `-m`, `-F`, `-C`, `-c`, `-t`.
_COMMIT_SHORT_WITH_VALUE = "mFCct"

_CAT_HEREDOC = re.compile(
    r"^\$\(\s*cat\s+<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\n(.*?)\n[ \t]*\1[ \t]*\n?\s*\)$",
    re.DOTALL,
)


class CommitArgs(typing.NamedTuple):
    messages: list[str]
    files: list[str]
    trailers: list[str]
    paths: list[str]
    flags: list[str]


def parse_commit_args(args: list[str]) -> CommitArgs:
    """`git commit <args>` into its message values, `-F` files, trailers, pathspecs and bare flags (short bundles split into one flag per letter)."""
    messages: list[str] = []
    files: list[str] = []
    trailers: list[str] = []
    paths: list[str] = []
    flags: list[str] = []
    k = 0
    while k < len(args):
        arg = args[k]
        if arg == "--":
            paths.extend(args[k + 1 :])
            break
        if arg.startswith("--"):
            key, eq, value = arg.partition("=")
            if key in _COMMIT_WITH_VALUE:
                if not eq:
                    value = args[k + 1] if k + 1 < len(args) else ""
                    k += 1
                if key == "--message":
                    messages.append(value)
                elif key == "--file":
                    files.append(value)
                elif key == "--trailer":
                    trailers.append(value)
            else:
                flags.append(arg)
            k += 1
            continue
        if arg.startswith("-") and len(arg) > 1:
            letters = arg[1:]
            for i, letter in enumerate(letters):
                if letter in _COMMIT_SHORT_WITH_VALUE:
                    value = letters[i + 1 :]
                    if value == "":
                        value = args[k + 1] if k + 1 < len(args) else ""
                        k += 1
                    if letter == "m":
                        messages.append(value)
                    elif letter == "F":
                        files.append(value)
                    break
                flags.append("-" + letter)
            k += 1
            continue
        paths.append(arg)
        k += 1
    return CommitArgs(messages, files, trailers, paths, flags)


def _unwrap(value: str) -> str:
    match = _CAT_HEREDOC.match(value.strip())
    return match.group(2) if match else value


def _heredoc_bodies(cmd: str) -> list[str]:
    from rediacc_hooks import shellscan  # noqa: PLC0415 -- see the module docstring

    lexer = shellscan._Lexer(cmd)
    try:
        lexer.tokens()
    except Exception:  # noqa: BLE001 -- an unlexable command has no readable heredoc
        return []
    return [
        lexer.src[h.body_start : h.body_end]
        for h in lexer.heredocs
        if h.body_start is not None and h.body_end is not None
    ]


def commit_message_text(cmd: str, root: str, run=None) -> str:
    """The message a `git commit` in `cmd` would write, "" when it cannot be read.

    The three readable shapes `block_untagged_commit` established: `-m`/`--message` values (a `"$(cat <<'EOF' ... EOF)"` wrapper unwrapped), `-F -` fed by a heredoc, and `-F <file>` read off disk relative to the command's directory. `--trailer` values are appended as trailer lines, because git writes them into the same message. A piped stdin, an editor session or any other command substitution is opaque, and "" says so.
    """
    commits = [run] if run is not None else git_runs(cmd, "commit")
    parts: list[str] = []
    for commit in commits:
        _, _, args = git_split(commit.argv)
        parsed = parse_commit_args(args)
        body = [_unwrap(m) for m in parsed.messages]
        for name in parsed.files:
            if name == "-":
                body.extend(_heredoc_bodies(cmd))
                continue
            directory = run_dir(commit, root)
            path = pathlib.Path(name if name.startswith("/") else os.path.join(directory, name))
            try:
                body.append(path.read_text(encoding="utf-8", errors="surrogateescape"))
            except OSError:
                continue
        text = "\n\n".join(b.rstrip("\n") for b in body)
        if parsed.trailers:
            text = text + "\n\n" + "\n".join(parsed.trailers)
        if text.strip():
            parts.append(text)
    return "\n\n".join(parts)


def commit_paths(cmd: str, run=None) -> list[str]:
    """The pathspecs a `git commit` in `cmd` names (after `--`, or bare positionals)."""
    commits = [run] if run is not None else git_runs(cmd, "commit")
    out: list[str] = []
    for commit in commits:
        _, _, args = git_split(commit.argv)
        out.extend(parse_commit_args(args).paths)
    return out


def commit_flags(run) -> list[str]:
    _, _, args = git_split(run.argv)
    return parse_commit_args(args).flags


def staged_paths(repo_root: str, include_worktree: bool = False) -> list[str]:
    """What a pathspec-less commit would take: the index, plus modified tracked files for `-a`."""
    names = (git(["diff", "--cached", "--name-only"], cwd=repo_root) or "").split("\n")
    if include_worktree:
        names += (git(["diff", "--name-only"], cwd=repo_root) or "").split("\n")
    return sorted({n for n in names if n})


def expand_paths(repo_root: str, paths: list[str], cwd: str | None = None) -> list[str]:
    """Pathspecs as repository-relative file paths.

    A directory or a glob becomes the files under it that git knows (tracked, or untracked and not ignored); a plain path stays itself.
    """
    out: list[str] = []
    here = cwd or repo_root
    for spec in paths:
        absolute = spec if spec.startswith("/") else os.path.join(here, spec)
        rel = os.path.relpath(absolute, repo_root)
        if os.path.isdir(absolute) or any(ch in spec for ch in "*?["):
            listed = git(
                ["ls-files", "--cached", "--others", "--exclude-standard", "--", rel],
                cwd=repo_root,
            )
            files = [f for f in (listed or "").split("\n") if f]
            out.extend(files or [rel])
        else:
            out.append(rel)
    return sorted(dict.fromkeys(out))


def judged_paths(run, cmd: str, repo_root: str, base: str) -> list[str]:
    """The files a walked `git commit` would commit: its pathspecs expanded, else the index (plus the worktree under `-a`)."""
    named = commit_paths(cmd, run=run)
    if named:
        return expand_paths(repo_root, named, cwd=run_dir(run, base))
    flags = commit_flags(run)
    return staged_paths(repo_root, include_worktree="-a" in flags or "--all" in flags)


# --------------------------------------------------------------------------- tags and tokens ---------------------------------------------------------------------------


def subject(msg: str) -> str:
    """The first line that is neither blank nor a `#` comment."""
    for line in msg.split("\n"):
        if line.strip() and not line.lstrip().startswith("#"):
            return line.strip()
    return ""


def tags(msg: str) -> set[str]:
    """The bracketed tags in the subject line, lowercased: `{"hotfix", "no-review"}`."""
    return {t.lower() for t in TAG.findall(subject(msg))}


def skip_tokens(msg: str, cfg: dict[str, typing.Any] | None = None) -> list[str]:
    """Every CI skip token in `msg`, case-insensitive, plus the `skip-checks: true` trailer."""
    cfg = cfg or DEFAULTS
    low = msg.lower()
    found = [t for t in cfg.get("skip_tokens", DEFAULTS["skip_tokens"]) if t.lower() in low]
    if SKIP_TRAILER.search(msg):
        found.append("skip-checks: true")
    return found


def _glob_rx(pattern: str) -> re.Pattern:
    out = []
    k = 0
    while k < len(pattern):
        if pattern.startswith("**/", k):
            out.append("(?:.*/)?")
            k += 3
        elif pattern.startswith("**", k):
            out.append(".*")
            k += 2
        elif pattern[k] == "*":
            out.append("[^/]*")
            k += 1
        elif pattern[k] == "?":
            out.append("[^/]")
            k += 1
        else:
            out.append(re.escape(pattern[k]))
            k += 1
    return re.compile("^" + "".join(out) + "$")


def glob_match(path: str, patterns: list[str]) -> bool:
    """`**/` spans any number of directories (none included), `*` and `?` stay inside one."""
    return any(_glob_rx(p).match(path) for p in patterns)


def no_review_eligible(
    paths: list[str], cfg: dict[str, typing.Any] | None = None
) -> tuple[bool, list[str]]:
    """`(eligible, offenders)`: every path matches an eligible glob and no denied one. No paths at all is not eligible, because nothing was shown to be writing."""
    cfg = cfg or DEFAULTS
    allow = cfg.get("no_review_eligible", DEFAULTS["no_review_eligible"])
    deny = cfg.get("no_review_denied", DEFAULTS["no_review_denied"])
    offenders = [p for p in paths if glob_match(p, deny) or not glob_match(p, allow)]
    return bool(paths) and not offenders, offenders


def hotfix_ok(
    msg: str, paths: list[str], cfg: dict[str, typing.Any] | None = None
) -> tuple[bool, str]:
    """Whether a commit is a well-formed `[hotfix]`: `(True, "")` or `(False, reason)`.

    The tag, a `Hotfix-Evidence:` trailer of a known shape (a red main run id or URL, or `ASKED:<ISO minute>`), and at most `hotfix_max_files` paths. The ASKED form is checked for SHAPE here; whether the operator really asked is the transcript's to confirm, not a pure function's.
    """
    cfg = cfg or DEFAULTS
    if "hotfix" not in tags(msg):
        return False, "the subject carries no [hotfix] tag"
    match = HOTFIX_EVIDENCE.search(msg)
    if not match:
        return False, "no `Hotfix-Evidence:` trailer"
    evidence = match.group(1).strip()
    if not (EVIDENCE_RUN.match(evidence) or EVIDENCE_ASKED.match(evidence)):
        return False, (
            "`Hotfix-Evidence: %s` is neither a red main run (id or actions/runs URL) nor "
            "`ASKED:<YYYY-MM-DDTHH:MMZ>`" % evidence
        )
    limit = int(cfg.get("hotfix_max_files", DEFAULTS["hotfix_max_files"]))
    if len(paths) > limit:
        return False, "%d paths, above the hotfix limit of %d" % (len(paths), limit)
    return True, ""


def override(env: typing.Mapping[str, str]) -> bool:
    """The operator's git-level override, `COMMIT_POLICY_OK=1`."""
    return env.get(OVERRIDE_ENV, "") == "1"
