"""Which repositories a typed git command acts on, for a pre-bash guard whose rule is about this checkout and its submodules and not about every repository on the machine.

WHY. Guards refused a throwaway `git init` under /tmp as if it were the console (#a8ae93bd, #381462dc, measured 2026-11-11): block_worktree_add the backup-ref restore recipe's linked tree, block_git_empty_commit an empty commit, block_unlinked_commit_author a commit whose author is the scratch repository's own `-c user.email`, and block_blanket_git_add, block_pathspecless_git_commit and block_unproven_bulk_transform their verbs with the event's `cwd` in the scratch repository. Each rule is about rediacc/console: its CI runs, its second checkouts, its GitHub attribution, its shared index. A repository with a git common dir of its own is none of them.

ONE QUESTION, `git_targets`. It answers the directories the judged git runs of a command act on, or None when any part of that answer is unknown, and None is the caller's cue to judge the command as this checkout. `elsewhere` then asks git for each directory's common dir (`common_dir`) and compares it with this checkout's; block_worktree_add keeps its own stricter comparison (a directory naming no repository is a doubt there), in its own file where its own plant reaches it. None for every doubt:

  - a `GIT_*` repository variable (`GIT_REPO_ENV`) named anywhere in the command or present in the hook's own environment, or any `GIT_*` variable but an author or committer identity (`GIT_IDENTITY_ENV`) set on a judged run: `GIT_DIR` and its kin move git elsewhere whatever `-C` says;
  - any git run whose verb is a word the walk cannot know (`$v`, a substitution) or an alias the run sets for itself (`-c alias.X=V`, `GIT_CONFIG_KEY_n`);
  - a judged run with any global option before its verb but `-C <dir>` and `-c <key>=<value>` (`--git-dir`, `--work-tree`, an attached `-C<dir>`, `--namespace`), or a `-c alias.*` there;
  - a `cd` or `-C` directory holding an unresolved word or a leading `~`, a relative one with no absolute event `cwd` to anchor it, or one that does not exist and that the same command does not create (`created=True` only);
  - more text matches of the caller's own pattern than judged runs, so a spelling the walk did not turn into a run is never waved through;
  - no judged run at all.
"""

import os
import re

from rediacc_hooks import commit_policy, hookio, shellscan

GIT_REPO_ENV = (
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)
GIT_REPO_ENV_TEXT = re.compile(
    r"GIT_(?:DIR|COMMON_DIR|WORK_TREE|CEILING_DIRECTORIES|DISCOVERY_ACROSS_FILESYSTEM)\b"
)
# A commit's identity, which says who wrote it and nothing about which repository it lands in. Every other `GIT_*` on a run is a doubt: the repository variables above, the index and object stores, and `GIT_CONFIG_*`, which can carry an alias or a `core.worktree`.
GIT_IDENTITY_ENV = frozenset(
    (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "GIT_COMMITTER_DATE",
    )
)
GIT_ALIAS = re.compile(r"^alias\.([^=]+)=(.*)$", re.DOTALL)
GIT_CONFIG_KEY = re.compile(r"^GIT_CONFIG_KEY_(\d+)$")


def unknown_word(word):
    """Does `word` hold a part bash fills in at run time that the walk could not resolve?"""
    return any(mark in word for mark in ("$", "`", "\0"))


def git_aliases(run_, argv, at):
    """`{name: value}` for every alias the git run `run_` sets for itself before its verb at `at`: `-c alias.X=V` (also attached, `-calias.X=V`) and the GIT_CONFIG_KEY_n/VALUE_n pair in its environment."""
    found: dict[str, str] = {}
    k = 0
    while k < at:
        word = argv[k]
        setting = argv[k + 1] if word == "-c" and k + 1 < at else word[2:]
        if word.startswith("-c"):
            m = GIT_ALIAS.match(setting)
            if m:
                found[m.group(1)] = m.group(2)
            k += 2 if word == "-c" else 1
            continue
        k += 1
    env = getattr(run_, "env", None) or {}
    for name, key in env.items():
        m = GIT_CONFIG_KEY.match(name)
        if not m:
            continue
        alias = GIT_ALIAS.match("%s=%s" % (key, env.get("GIT_CONFIG_VALUE_%s" % m.group(1), "")))
        if alias:
            found[alias.group(1)] = alias.group(2)
    return found


def common_dir(directory):
    """The absolute, resolved git common dir of the repository `directory` sits in, "" when git cannot say (no repository, no directory, git not answering)."""
    if not directory or not os.path.isdir(directory):
        return ""
    got = commit_policy.git(
        ["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=directory, foreign=True
    )
    return os.path.realpath(got) if got else ""


def text_matches(pattern, scan):
    """How many times `pattern` matches the scanned text, record by record: the `expected` a guard whose refusal reads text hands `git_targets`."""
    records, _ = hookio._records(scan)
    return sum(len(list(re.finditer(pattern, record))) for record in records)


_NO_ANCHOR = "/\0"


def _made(directory, created):
    return any(directory == c or directory.startswith(c.rstrip("/") + "/") for c in created)


def run_target(run_, argv, at, base, created=frozenset()):
    """The directory the git run `run_` (verb at `at` of `argv`) acts on, or None when it cannot be known exactly.

    Only `-C <dir>` and `-c <key>=<value>` may precede the verb, and `-c alias.*` may not. The run's persisted `cd` and its `-C` directories compose onto `base`, which is needed only when they leave the path relative. The directory must exist, or be one `created` names (made by the same command before the run).
    """
    k = 0
    while k < at:
        word = argv[k]
        if word in ("-C", "-c") and k + 1 < at:
            if word == "-c" and argv[k + 1].lower().startswith("alias."):
                return None
            k += 2
            continue
        # `--git-dir`, `--work-tree`, `--namespace`, an attached `-C<dir>`, `-calias...`: each could move git elsewhere or rename the verb, and none is needed for a scratch repository.
        return None
    _, where = shellscan._git_verb_at(argv)
    parts = [run_.cwd or "", where]
    if any(unknown_word(p) or p.startswith("~") for p in parts):
        return None
    joined = os.path.join(*parts)
    if not os.path.isabs(joined):
        if not base or not os.path.isabs(base):
            return None
        joined = os.path.join(base, joined)
    directory = os.path.normpath(joined)
    if os.path.isdir(directory) or _made(directory, created):
        return directory
    return None


def git_targets(cmd, base, pick, expected, created=False):
    """The directories every git run of `cmd` that `pick` selects acts on, in order, or None when any part of that is unknown (the module docstring lists each doubt).

    `pick(verb, rest)` answers True to judge the run, False to pass over it, None for a doubt. `expected` is how many runs the caller's own text pattern matched; more matches than judged runs is a doubt. `base` is the event's `cwd`. `created=True` admits a directory the same command makes before the run (`git init <dir>`, `mkdir`), which a caller resolving such a directory to "no repository" must then judge itself.
    """
    if GIT_REPO_ENV_TEXT.search(cmd) or any(os.environ.get(name) for name in GIT_REPO_ENV):
        return None
    made: frozenset[str] = frozenset()
    if created:
        # With no absolute `cwd` a relative `git init x` lands nowhere this reading can name, so it is anchored at a prefix no real path carries and dropped; an absolute one counts either way.
        anchor = base if base and os.path.isabs(base) else _NO_ANCHOR
        made = frozenset(
            d
            for d in shellscan._created_dirs(commit_policy.runs(cmd), anchor)
            if not d.startswith(_NO_ANCHOR)
        )
    targets = []
    for run_ in shellscan.every_run(cmd):
        if run_.name.rsplit("/", 1)[-1] != "git":
            continue
        argv = list(run_.xargv if run_.xargv is not None else run_.argv)
        at, _ = shellscan._git_verb_at(argv)
        if at is None:
            continue
        verb, rest = argv[at], argv[at + 1 :]
        if unknown_word(verb) or git_aliases(run_, argv, at).get(verb) is not None:
            return None
        chosen = pick(verb, rest)
        if chosen is None:
            return None
        if not chosen:
            continue
        if any(n.startswith("GIT_") and n not in GIT_IDENTITY_ENV for n in (run_.env or {})):
            return None
        target = run_target(run_, argv, at, base, made)
        if target is None:
            return None
        targets.append(target)
    if not targets or expected > len(targets):
        return None
    return targets


def elsewhere(cmd, base, root, pick, expected):
    """Does every git run of `cmd` that `pick` selects act outside this checkout and its submodules? `root` is this checkout's toplevel; the rest is `git_targets`'s, with `created=True`. False on every doubt, so the caller judges the command as this checkout.

    A target outside means one of two things: a repository whose git common dir is neither this checkout's nor under it, or a directory outside `root` naming no repository (git refuses to run there, or the same command `git init`s it first). A directory inside `root` always judges as this checkout, and so does every repository when this checkout's own common dir cannot be read.
    """
    if not root:
        return False
    targets = git_targets(cmd, base, pick, expected, created=True)
    if targets is None:
        return False
    ours = common_dir(root)
    for target in targets:
        # Inside this tree is this checkout, whatever repository the directory holds: a nested independent repo (a gitignored sibling under private/) is still work in this tree, and the guards judge it as ours.
        if commit_policy.is_inside(target, root):
            return False
        common = common_dir(target)
        if common and (not ours or commit_policy.is_inside(common, ours)):
            return False
    return True


def walked_commit_flag(cmd, flag, adjacent=True):
    """Does a `git commit` bash would run in `cmd` set the boolean option `flag` (a long name: "allow-empty", "amend"), read by git's own option parse? A text pattern anchored on `git commit` does not read past `git -C <dir> commit`, `git -c k=v commit` or `git -c alias.ci=commit ci`; the walk places each of them, and an alias the run sets for itself is expanded first.

    `adjacent=False` passes over a run spelled `git commit` with nothing between the two words, for a caller whose own text arms already read that spelling everywhere bash runs it (block_git_amend's lifted commands), so its declared defect on those arms still changes an answer.
    """
    for r in commit_policy.git_runs(cmd):
        argv = list(r.argv)
        at, _ = shellscan._git_verb_at(argv)
        if at is None:
            continue
        verb, rest = argv[at], argv[at + 1 :]
        alias = git_aliases(r, argv, at).get(verb)
        if not adjacent and at == 0 and alias is None:
            continue
        if alias and not alias.startswith("!") and alias.split():
            words = alias.split()
            verb, rest = words[0], words[1:] + rest
        if verb == "commit" and shellscan.git_commit_args(rest).on(flag):
            return True
    return False


def verb_is(*verbs):
    """A `pick` for `git_targets` and `elsewhere`: judge every run of one of `verbs`."""
    return lambda verb, _rest: verb in verbs
