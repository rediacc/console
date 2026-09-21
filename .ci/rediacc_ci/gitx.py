"""Asking git a question, once, in the spelling that is not wrong.

WHY THIS MODULE IS MOSTLY ABOUT TRAPS. Every function here has a shorter, more obvious spelling that most of this tree already uses, and each of those spellings is wrong in a way that produces a WRONG ANSWER rather than an error. That is the whole reason to have one implementation: an error announces itself and a wrong answer does not.

------------------------------------------------------------------------------
TRAP 1: `git ls-files` READS THE INDEX, NOT THE WORKING TREE.
------------------------------------------------------------------------------
It cannot see a file you created and have not staged, and it still lists a file you deleted with `rm` rather than `git rm`. Both directions bite here:

  * `.ci/scripts/quality/check-python-lint.sh` shipped green on 2026-08-09
    reporting "27 files, All checks passed!" while `wl_checklist.py` -- the
    newest and second-largest module of the Stop-hook program -- was untracked
    and therefore never in the list. The fix was `--others --exclude-standard`.
  * `check-shell-declared-commands.ts` CRASHED on six unstaged deletions on
    2026-09-06 (docs/ci-overhaul/08-driver-contract.md section 5b), and
    `check-python-lint.sh:89` and `.ci/scripts/security/shellcheck.sh:91-95` are
    the only two consumers in the tree that filter the listing through
    `[ -e "$f" ]`.

Of 23 `git ls-files` call sites measured across `.ci`, `scripts` and `.claude`, exactly ONE passes `--cached --others --exclude-standard` and exactly TWO guard
for the deleted case. So `ls_files()` here takes `untracked` and `existing` as
explicit arguments and documents which default hides which failure.

------------------------------------------------------------------------------
TRAP 2: THE DEFAULT PATHSPEC `*` ALREADY CROSSES `/`, SO `a/**/*.sh` IS NARROWER.
------------------------------------------------------------------------------
git's default wildmatch is NOT fnmatch: a bare `*` matches slashes. `.ci/*.sh` therefore reaches every depth under `.ci`, while `.ci/**/*.sh` requires at least one intermediate directory and SILENTLY SKIPS everything sitting directly under `.ci` -- `.ci/bootstrap.sh`, for one. `check-go-tool-path.sh:96-102` records the measurement: the two spellings return the same 453 tracked
files, and only the second one drops bootstrap.sh.

The failure is silent in the narrowing direction, which is the dangerous one: a gate keeps passing while its corpus quietly shrinks. `.ci/scripts/quality/check_pathspec_scope.py:73` bans `**/` in a pathspec for exactly this reason, and `pathspec_warning()` below carries the same rule so a caller of this module is told before the answer is wrong rather than after.

------------------------------------------------------------------------------
TRAP 3: `rev-parse --abbrev-ref HEAD` PRINTS THE LITERAL STRING "HEAD" WHEN
DETACHED, AND EXITS 0.
------------------------------------------------------------------------------
So `branch="$(git rev-parse --abbrev-ref HEAD)" || branch=unknown` never takes
its fallback, and neither does `... or "(detached or unknown)"`. 13 sites use that spelling; 6 are unguarded, including four in `scripts/dev/worktree.sh` (`:66,:488,:527,:567`) whose `|| echo unknown` / `|| echo ""` fallbacks are dead code. `.ci/lib/devbox.sh:151-156` records what it cost: the sanitised string `head.localhost` became one traefik router name shared by every detached
worktree on the box.

`branch()` here uses `symbolic-ref --short -q HEAD`, which exits non-zero and prints nothing when detached, and returns None. The repo has already converged on "empty is the honest answer" twice independently -- `.ci/lib/devbox.sh:157` and `.claude/hooks/stop/wl_core.py:528-553` -- so this adopts rather than proposes. A gate already enforces the guard on the bad spelling:
`.ci/scripts/quality/check-git-op-conditionals.sh:104-115`.

------------------------------------------------------------------------------
TRAP 4: "IS IT DIRTY" IS FOUR DIFFERENT QUESTIONS.
------------------------------------------------------------------------------
Measured across 21 sites: `git status --porcelain` counts untracked;
`git diff --quiet` sees only UNSTAGED changes to TRACKED files, so it calls a
tree with staged changes clean; `git diff --cached --quiet` is the mirror image;
and the battery runner's `tree_state` deliberately filters `^??` out because a scratch file is not a tree change. `scripts/dev/worktree.sh` pairs the two `--quiet` forms at four sites and therefore treats an untracked-only tree as clean at all four. All four are legitimate questions and this module makes the caller name which one it is asking.

------------------------------------------------------------------------------
TRAP 5: A PROBE THAT FAILED IS NOT AN ANSWER OF "NO".
------------------------------------------------------------------------------
`merge-base --is-ancestor` exits 0 for yes, 1 for no, and 128 for "one of those refs does not exist" -- a shallow clone, a typo, a tag that was never fetched. All seven shell sites collapse anything non-zero into "no", so a shallow CI checkout silently reports "this commit is not on main" and the gate keyed on it does the wrong thing quietly. `.claude/hooks/stop/wl_git.py:173-186`
already returns tri-state and says so in its own words: "None is NOT False". This module generalises that: every probe that can be BLIND returns None for blind.

------------------------------------------------------------------------------
TRAP 6: A HARDCODED SUBMODULE LIST GOES BLIND TO THE FIFTH SUBMODULE.
------------------------------------------------------------------------------
`.gitmodules` declares four (`private/renet`, `private/homebrew-tap`, `private/elite`, `private/account`) and three independent hardcoded copies exist -- `check-submodule-branches.sh:418` and `:457`, `.ci/scripts/ci/scope-map.cjs:123`, `.ci/scripts/ci/greenlight.cjs:270` -- plus a repo-name list at `.ci/scripts/autopilot/linked-sub-prs.sh:43`. They all AGREE today; two of the files
already document that as a live defect rather than a state of grace (`wl_git.py:115-119`: "READ, NEVER HARDCODE"; `linked-sub-prs.sh:41-42`: "A submodule missing here is invisible to this scan"). `submodules()` reads `.gitmodules`, and `test_gitx.py` asserts the hardcoded lists still match it, so the day one of them drifts is the day something says so.

AND ITS BLIND SPOT, stated because reading `.gitmodules` does not remove it: `private/growth` and `private/generative` are independent git repositories under `private/` that are gitignored and are NOT submodules, so no enumeration of any kind sees them. `.claude/hooks/stop/wl_git.py:149` `sibling_repos()` exists for that, and `sibling_repos()` here is its counterpart.

------------------------------------------------------------------------------
WHY GIT IS RUN THROUGH `rediacc_ci.proc`
------------------------------------------------------------------------------
For the bounded, stdin-closed, streams-separate contract that module documents. The environment additions are lifted verbatim from `.claude/hooks/stop/wl_git.py:84-89`, which learned them the hard way: without
`GIT_TERMINAL_PROMPT=0` a git that wants credentials blocks on a terminal
nobody is watching, and the symptom is a CI job that hangs to its own cap having printed nothing.
"""

import os
import pathlib
import re

from rediacc_ci import proc

# Verbatim from .claude/hooks/stop/wl_git.py:84-89. Each one closes a way git can decide to wait for a human: GIT_EDITOR / GIT_SEQUENCE_EDITOR a rebase or commit that wants a message
#   GIT_TERMINAL_PROMPT=0             a fetch that wants credentials
#   GIT_PAGER=cat                     a long output that wants a pager on a tty
NONINTERACTIVE = {
    "GIT_EDITOR": "true",
    "GIT_SEQUENCE_EDITOR": "true",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_PAGER": "cat",
}

# The observed timeouts in this tree are 10, 15, 25 and 30 seconds, always an explicit literal at the call site. 30 is the largest of them and is used here as the default so no existing behaviour gets tighter by being ported.
DEFAULT_TIMEOUT = 30.0

# The `**/` ban from .ci/scripts/quality/check_pathspec_scope.py:73, restated so a caller of this module is warned at the call site instead of by a gate later. `:(` prefixed magic pathspecs are exempt there and here: `:(glob)a/**/*.sh` opts INTO fnmatch semantics deliberately, which is a different statement from the accidental narrowing this rule is about.
_DOUBLESTAR = "**/"


def pathspec_warning(spec: str) -> str | None:
    """Why `spec` is probably narrower than its author intended, or None.

    Returned as a STRING rather than raised, because a pathspec can be deliberately narrow and this module is not the place to overrule that. A caller that wants it fatal raises; a gate that wants it visible prints it.
    """
    if _DOUBLESTAR in spec and not spec.startswith(":("):
        return (
            "%r contains '**/', which in git's default wildmatch requires at least one "
            "intermediate directory and therefore SKIPS files sitting directly under the "
            "prefix. A bare '*' already crosses '/', so the wider spelling is the shorter "
            "one. See check-go-tool-path.sh:96-102." % spec
        )
    return None


def git(
    args: list[str],
    *,
    root: os.PathLike[str] | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> proc.Result:
    """Run `git <args>` non-interactively under `root`. Never raises on non-zero.

    `-C <root>` rather than `cwd=`, matching every call site in the tree that
    reaches into a submodule. The two are equivalent for a plain run and differ when the caller's own cwd matters, and naming the repo explicitly is the spelling that survives being copied somewhere else.
    """
    env = dict(os.environ)
    env.update(NONINTERACTIVE)
    prefix = ["git"] if root is None else ["git", "-C", str(root)]
    return proc.run([*prefix, *args], env=env, timeout=timeout)


# --------------------------------------------------------------------------- Where the repository is ---------------------------------------------------------------------------


def toplevel(start: os.PathLike[str] | str | None = None) -> pathlib.Path | None:
    """`git rev-parse --show-toplevel`, or None outside a work tree.

    None rather than a guess, and note what it does NOT do: this answers with the innermost repository containing `start`, so inside `private/renet` it answers
    with the submodule. `rediacc_ci.paths.repo_root()` is derived from this
    package's own location and is the right answer for a gate; this is for the
    caller that genuinely has only a directory.
    """
    result = git(["rev-parse", "--show-toplevel"], root=start)
    if not result.ok:
        return None
    text = result.stdout.strip()
    return pathlib.Path(text) if text else None


def is_work_tree(root: os.PathLike[str] | str | None = None) -> bool:
    """Is this a git work tree at all?

    `check-python-lint.sh:80-85` asks this first and refuses to report a pass when the answer is no, because `git ls-files` outside a repository returns nothing and an empty corpus reads exactly like a clean tree.
    """
    return git(["rev-parse", "--is-inside-work-tree"], root=root).stdout.strip() == "true"


# --------------------------------------------------------------------------- Which branch ---------------------------------------------------------------------------


def branch(root: os.PathLike[str] | str | None = None) -> str | None:
    """The current branch, or None when detached. See TRAP 3.

    `symbolic-ref --short -q HEAD`, never `rev-parse --abbrev-ref HEAD`. The difference only shows up in a detached worktree, which is where this repo actually got burned.
    """
    result = git(["symbolic-ref", "--short", "-q", "HEAD"], root=root)
    if not result.ok:
        return None
    return result.stdout.strip() or None


def branch_from_ci(env: dict[str, str] | None = None) -> str | None:
    """The branch CI thinks we are on, from the environment, or None.

    THE ORDER IS NOT ARBITRARY. `PR_HEAD_REF` first because this repo sets it explicitly; `GITHUB_HEAD_REF` second because it is populated only for a `pull_request` event and, per `check_pr_head_ref_completeness.py:11-13`, does NOT reliably materialise down a `workflow_call` chain; `GITHUB_REF_NAME` last because on a `pull_request` it is the artificial `<n>/merge`, which is a real
    ref and the wrong answer to this question.

    Deliberately does NOT fall through to `branch()`. On the merge-commit checkout CI uses, git's answer is a detached HEAD and therefore None, and a caller that silently blends the two cannot tell "CI did not tell me" from "we are detached". `branch_from_ci(...) or branch(...)` at the call site says which the caller prefers, in one readable line.
    """
    environ = os.environ if env is None else env
    for name in ("PR_HEAD_REF", "GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        value = environ.get(name)
        if value:
            return value
    return None


def head_sha(root: os.PathLike[str] | str | None = None, ref: str = "HEAD") -> str | None:
    """The full sha of `ref`, or None when it does not resolve."""
    result = git(["rev-parse", "--verify", "--quiet", "%s^{commit}" % ref], root=root)
    return result.stdout.strip() or None if result.ok else None


def ref_exists(ref: str, root: os.PathLike[str] | str | None = None) -> bool:
    """Does `ref` resolve here? The precondition `is_ancestor` needs."""
    return head_sha(root, ref) is not None


# --------------------------------------------------------------------------- Is it dirty -- four questions, named ---------------------------------------------------------------------------


def status_entries(root: os.PathLike[str] | str | None = None) -> list[tuple[str, str]] | None:
    """`git status --porcelain=v1 -z` as (xy, path) pairs, or None if git failed.

    NUL-SEPARATED, and the rename field is consumed rather than skipped. `git status -z` emits an EXTRA field after a rename or copy entry (the origin path), so a naive split leaves the parser one field out of phase for every entry after the first rename -- and it then reports a status code that is
    really half of a filename. `wl_git.py:643-647` handles the same thing;
    `.ci/scripts/autopilot/validate-handoff.cjs:106` documents the format.

    None, NOT [], when git failed. An empty list means "clean"; a failed probe means "I do not know", and collapsing the two is TRAP 5 in the dirt-check's clothing.
    """
    result = git(["status", "--porcelain=v1", "-z"], root=root)
    if not result.ok:
        return None
    fields = result.stdout.split("\0")
    out: list[tuple[str, str]] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        # FIXED WIDTH, NOT `partition(" ")`. The status code is exactly two characters and either may be a SPACE -- ` M`, `R `, `??`. Splitting on
        # the first space therefore yields xy="R" and path=" renamed.txt" for
        # every entry whose second column is blank, which is most of them, and the leading space then survives into every path comparison downstream.
        xy = entry[:2]
        path = entry[3:]
        # A rename or copy is followed by its ORIGIN path as a separate field.
        if "R" in xy or "C" in xy:
            index += 1
        out.append((xy, path))
    return out


def dirty_paths(
    root: os.PathLike[str] | str | None = None, *, untracked: bool = True
) -> list[str] | None:
    """Paths the working tree has changed. None when git could not be asked.

    `untracked=False` reproduces the battery runner's `grep -v '^??'` -- a scratch file is not a change to the tree -- which `.ci/rediacc_ci/quality/battery_clean_tree.py` pins.
    """
    entries = status_entries(root)
    if entries is None:
        return None
    return [path for xy, path in entries if untracked or xy != "??"]


def is_dirty(root: os.PathLike[str] | str | None = None, *, untracked: bool = True) -> bool | None:
    """Tri-state. True dirty, False clean, None unknown."""
    paths = dirty_paths(root, untracked=untracked)
    return None if paths is None else bool(paths)


def has_staged_changes(root: os.PathLike[str] | str | None = None) -> bool | None:
    """`git diff --cached --quiet` inverted. None when git failed.

    Separate from `is_dirty` because they are genuinely different questions, and because `scripts/dev/worktree.sh` needs both at all four of its sites.
    """
    result = git(["diff", "--cached", "--quiet"], root=root)
    if result.returncode in (0, 1):
        return result.returncode == 1
    return None


def has_unstaged_changes(root: os.PathLike[str] | str | None = None) -> bool | None:
    """`git diff --quiet` inverted: TRACKED files only, UNSTAGED changes only.

    This is the one that surprises people. A tree whose every change is staged answers False here and True from `is_dirty`, and both are correct.
    """
    result = git(["diff", "--quiet"], root=root)
    if result.returncode in (0, 1):
        return result.returncode == 1
    return None


# --------------------------------------------------------------------------- Ancestry ---------------------------------------------------------------------------


def is_ancestor(
    ancestor: str, descendant: str, root: os.PathLike[str] | str | None = None
) -> bool | None:
    """Tri-state ancestry. TRAP 5.

    0 -> True, 1 -> False, anything else -> None. Generalised from `.claude/hooks/stop/wl_git.py:173-186`, whose docstring puts it best: "None is NOT False". The seven shell sites collapse 128 into False, so on a shallow clone they conclude "not on main" and act on it.
    """
    result = git(["merge-base", "--is-ancestor", ancestor, descendant], root=root)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def merge_base(a: str, b: str, root: os.PathLike[str] | str | None = None) -> str | None:
    """The common ancestor sha, or None when there is none or git failed."""
    result = git(["merge-base", a, b], root=root)
    return result.stdout.strip() or None if result.ok else None


def count_commits(rev_range: str, root: os.PathLike[str] | str | None = None) -> int | None:
    """`git rev-list --count <range>`, or None when the probe failed.

    None rather than 0, and `.ci/scripts/quality/check-branch.sh:67-71` is the receipt: a `|| echo "0"` on this exact call once made a broken probe read as "up to date with main", which is the answer that lets a stale branch through.

    On a shallow clone this returns a number that is real but not the truth, which no return type can express -- `check_git_history_depth.py:88` is the gate that requires `fetch-depth: 0` wherever this is called in a workflow.
    """
    result = git(["rev-list", "--count", rev_range], root=root)
    if not result.ok:
        return None
    text = result.stdout.strip()
    return int(text) if text.isdigit() else None


# --------------------------------------------------------------------------- Listing files ---------------------------------------------------------------------------


def ls_files(
    *pathspecs: str,
    root: os.PathLike[str] | str | None = None,
    untracked: bool = False,
    existing: bool = False,
    recurse_submodules: bool = False,
) -> list[str]:
    """Repo-relative paths from `git ls-files`. TRAPS 1 and 2.

    `untracked=True` adds `--others --exclude-standard`, which is what
    `check-python-lint.sh:88` needed after shipping green over an untracked file
    for an unknown period. Gitignored files stay out, which is what keeps
    node_modules and build output from arriving.

    `existing=True` drops paths that are not on disk -- a file deleted with `rm`
    rather than `git rm` is still in the index and every consumer that opens it then crashes with ENOENT. Only two of 23 call sites in this tree do this.

    `recurse_submodules` cannot be combined with `untracked`: git itself rejects `--others` with `--recurse-submodules`, and the error it gives names neither option clearly, so it is refused here with a sentence instead.

    RETURNS A SORTED, DEDUPLICATED LIST. `--cached` and `--others` are one invocation so nothing is double-listed, but a pathspec set can still overlap, and a caller comparing two enumerations wants a stable order rather than git's.
    """
    if recurse_submodules and untracked:
        raise ValueError(
            "git refuses --others together with --recurse-submodules. Enumerate the "
            "submodules with submodules() and list each one separately."
        )
    args = ["ls-files", "-z"]
    if untracked:
        args += ["--cached", "--others", "--exclude-standard"]
    if recurse_submodules:
        args.append("--recurse-submodules")
    if pathspecs:
        args.append("--")
        args.extend(pathspecs)
    result = git(args, root=root)
    if not result.ok:
        return []
    paths = sorted({p for p in result.stdout.split("\0") if p})
    if not existing:
        return paths
    base = pathlib.Path(str(root)) if root is not None else pathlib.Path.cwd()
    return [p for p in paths if (base / p).exists()]


def file_modes(*pathspecs: str, root: os.PathLike[str] | str | None = None) -> dict[str, str]:
    """`git ls-files -s` as {path: mode}. The mode git RECORDED, not the disk's.

    THE DISTINCTION IS THE WHOLE POINT, and `check-python-lint.sh` pays for it in prose: CI lints a fresh checkout, so what CI sees is whatever git recorded. A file chmod +x on disk AFTER `git add` is 755 locally and 644 in CI, which is exactly how two files passed a local gate and failed the same gate in CI on 2026-08-28.
    """
    args = ["ls-files", "-s", "-z"]
    if pathspecs:
        args.append("--")
        args.extend(pathspecs)
    result = git(args, root=root)
    if not result.ok:
        return {}
    out: dict[str, str] = {}
    for entry in result.stdout.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        fields = meta.split()
        if len(fields) >= 1 and path:
            out[path] = fields[0]
    return out


# --------------------------------------------------------------------------- Submodules and siblings ---------------------------------------------------------------------------

# A `[submodule "name"]` header, and the two keys inside it this module reads.
_SECTION_RE = re.compile(r'^\s*\[submodule\s+"(?P<name>[^"]+)"\]\s*$')
_KEY_RE = re.compile(r"^\s*(?P<key>path|url|branch)\s*=\s*(?P<value>.+?)\s*$")


class Submodule:
    """One declared submodule: its name, path, url and declared branch."""

    __slots__ = ("branch", "name", "path", "url")

    def __init__(self, name: str, path: str, url: str = "", branch: str = "main") -> None:
        self.name = name
        self.path = path
        self.url = url
        self.branch = branch

    def __repr__(self) -> str:
        return "Submodule(name=%r, path=%r, branch=%r)" % (self.name, self.path, self.branch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Submodule):
            return NotImplemented
        return (self.name, self.path, self.url, self.branch) == (
            other.name,
            other.path,
            other.url,
            other.branch,
        )

    def __hash__(self) -> int:
        return hash((self.name, self.path, self.url, self.branch))


def parse_gitmodules(text: str) -> list[Submodule]:
    """Parse `.gitmodules` text. A section with no `path` is skipped.

    A TEXT PARSER RATHER THAN `git config -f`, for one reason that matters: this works on a `.gitmodules` read from any commit, any fixture, or a string in a test, with no repository and no git binary. The three `git config -f .gitmodules --get-regexp` call sites in this tree cannot be unit-tested without building a repository first, which is why none of them is.

    The default branch is "main", matching `wl_git.py:113-138`, because git's own default when `.gitmodules` omits `branch` is the remote's HEAD and this repo's is main. A submodule that really tracks something else declares it.
    """
    out: list[Submodule] = []
    name = None
    fields: dict[str, str] = {}

    def flush() -> None:
        if name is not None and fields.get("path"):
            out.append(
                Submodule(
                    name,
                    fields["path"],
                    fields.get("url", ""),
                    fields.get("branch", "main"),
                )
            )

    for line in text.splitlines():
        header = _SECTION_RE.match(line)
        if header:
            flush()
            name = header.group("name")
            fields = {}
            continue
        if name is None:
            continue
        pair = _KEY_RE.match(line)
        if pair:
            fields[pair.group("key")] = pair.group("value")
    flush()
    return out


def submodules(root: os.PathLike[str] | str | None = None) -> list[Submodule]:
    """The declared submodules, read from `.gitmodules`. NEVER a hardcoded list.

    Returns [] when the file is absent, which is the right answer for a repo with no submodules and is indistinguishable from a repo whose `.gitmodules` was deleted. A caller that must tell those apart checks for the file; a gate that must not go blind puts a floor under the count, which is what
    `check_scope_completeness.py:58` does with `MIN_SUBMODULES = 2`.
    """
    base = pathlib.Path(str(root)) if root is not None else pathlib.Path.cwd()
    path = base / ".gitmodules"
    try:
        return parse_gitmodules(path.read_text(encoding="utf-8"))
    except OSError:
        return []


def sibling_repos(root: os.PathLike[str] | str | None = None) -> list[str]:
    """Independent git repositories under `private/` that are NOT submodules.

    THE BLIND SPOT NOTHING ELSE COVERS. `private/growth` and `private/generative` are gitignored checkouts, so `git status`, `git submodule` and `.gitmodules` all report nothing about them -- while `private/growth` holds the media pipeline whose publish gate console CI cannot run. Counterpart to `.claude/hooks/stop/wl_git.py:149`.

    Sorted, and it does not recurse: a repository inside a sibling is that sibling's business.
    """
    base = pathlib.Path(str(root)) if root is not None else pathlib.Path.cwd()
    declared = {s.path for s in submodules(base)}
    private = base / "private"
    if not private.is_dir():
        return []
    out = []
    for child in sorted(private.iterdir()):
        if not child.is_dir() or not (child / ".git").exists():
            continue
        relative = "private/%s" % child.name
        if relative not in declared:
            out.append(relative)
    return out


__all__ = [
    "DEFAULT_TIMEOUT",
    "NONINTERACTIVE",
    "Submodule",
    "branch",
    "branch_from_ci",
    "count_commits",
    "dirty_paths",
    "file_modes",
    "git",
    "has_staged_changes",
    "has_unstaged_changes",
    "head_sha",
    "is_ancestor",
    "is_dirty",
    "is_work_tree",
    "ls_files",
    "merge_base",
    "parse_gitmodules",
    "pathspec_warning",
    "ref_exists",
    "sibling_repos",
    "status_entries",
    "submodules",
    "toplevel",
]
