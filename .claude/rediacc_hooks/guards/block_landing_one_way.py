"""Commits flow one way, landing into development: refuse, in the landing tree, an act that would take a development commit (PLAN-two-track-merge-dev LT19).

WHY. Operator ruling ASKED:2026-11-20T18:46Z: the development branch is STACKED on the landing branch, `git rebase <landing branch>` brings landing's fixes into development, and nothing goes back. A development commit on the landing branch rides the open PR unreviewed for that PR, and after the merge every development commit main absorbed would read as landed.

ACTIVE ONLY IN THE LANDING TREE, the linked tree the landing record binds (`commit_policy.tree_role`, box LT1), decided per command from that command's own `cd` and `-C`. With no record, or from any other tree, everything is admitted. The DEVELOPMENT BRANCH is the branch the main checkout holds (the first entry of `git worktree list`), unless that is `main` or the landing branch.

REFUSED IN THE LANDING TREE:

  git rebase | merge | cherry-pick | pull | reset  whose source names the development branch (`<dev>`, `origin/<dev>`, `refs/heads/<dev>`, with a `~`/`^` suffix or as either end of a range), or would bring a development-only commit: one reachable from the development branch and from none of HEAD, the landing branch, main, origin/main and origin/<landing>. For a cherry-pick only the picked commits count.
  git push  of anything but the development branch whose pushed commits (those its destination's remote-tracking ref, origin/<landing>, origin/main and main lack) include a commit reachable from the development branch, unless the landing branch's reflog or the landing tree's HEAD reflog shows that commit was made in the landing tree (a commit, a cherry-pick, a rebase pick). The reflog exception keeps the stacked flow open: the development branch may rebase onto a landing commit before the landing push.

OUT OF REACH, stated: a submodule of the landing tree (its repository carries no landing record), a cherry-pick of a development commit's patch under a new sha (only reachability is read), and a verb inside an interpreter program.
"""

import os
import re
import subprocess

from rediacc_hooks import commit_policy, hookio, shellscan

CHAIN = "pre-bash"
ORDER = 72

# The verdict itself. With it gone every act in the landing tree goes through.
DEFECT = ("    if reason:\n        ev.warn_raw", "    if False:\n        ev.warn_raw")

PREFILTER = re.compile(r"\b(?:rebase|merge|cherry-pick|pull|reset|push)\b")
JUDGED = frozenset(("rebase", "merge", "cherry-pick", "pull", "reset", "push"))
MESSAGE = (
    "BLOCKED: %s\n\n"
    "Commits flow one way, landing into development: the development branch takes landing's commits with "
    "`git rebase <landing branch>` in its own tree, and nothing development made reaches the landing branch "
    "(operator ruling ASKED:2026-11-20T18:46Z; PLAN-two-track-merge-dev LT19). A fix the landing PR needs is "
    "built on the landing branch (`./run.sh worktree lease --tree landing`).\n"
    "(block_landing_one_way)"
)
MADE_HERE = (
    "commit",
    "cherry-pick",
    "revert",
    "rebase (pick)",
    "rebase (reword)",
    "rebase (edit)",
    "rebase (squash)",
    "rebase (fixup)",
    "rebase (continue)",
)
# Options that take their value as the next word, per verb, for the verbs shellscan's tables do not parse (git 2.53.0 `-h`).
VALUED = {
    "cherry-pick": frozenset(("-m", "--mainline", "-X", "--strategy-option", "--strategy")),
    "reset": frozenset(("--pathspec-from-file",)),
    "pull": frozenset(
        (
            "-s",
            "--strategy",
            "-X",
            "--strategy-option",
            "--depth",
            "--deepen",
            "--shallow-since",
            "--shallow-exclude",
            "-j",
            "--jobs",
            "--upload-pack",
            "-o",
            "--server-option",
            "--negotiation-tip",
        )
    ),
}


def _operands(sub, args):
    """The positional words of `git <sub> <args>`, options and their values dropped; for reset, those before `--`."""
    if sub in ("rebase", "merge"):
        parsed = shellscan.git_args(sub, args)
        found = list(parsed.operands)
        if sub == "rebase" and parsed.last("onto"):
            found.append(parsed.last("onto"))
        return [w for w in found if w != "--"]
    out, k, valued = [], 0, VALUED.get(sub, frozenset())
    while k < len(args):
        word = args[k]
        if word == "--":
            if sub != "reset":
                out.extend(args[k + 1 :])
            break
        if word.startswith("-") and word != "-":
            k += 2 if word in valued else 1
            continue
        out.append(word)
        k += 1
    return out


def _git(repo, *args):
    return commit_policy.git(list(args), cwd=repo, foreign=True)


def _sha(repo, rev):
    return _git(repo, "rev-parse", "--verify", "-q", "%s^{commit}" % rev) or ""


def _revs(repo, *args):
    got = _git(repo, "rev-list", *args)
    return set((got or "").split()) if got is not None else None


def _development_branch(repo, landing):
    listing = _git(repo, "worktree", "list", "--porcelain") or ""
    for block in listing.split("\n\n"):
        lines = block.splitlines()
        if not lines:
            continue
        branch = next(
            (
                ln[len("branch refs/heads/") :]
                for ln in lines
                if ln.startswith("branch refs/heads/")
            ),
            "",
        )
        return branch if branch not in ("", "main", landing) else ""
    return ""


def _existing(repo, refs):
    return [r for r in refs if _sha(repo, r)]


def _names_development(word, dev):
    """Does `word` name the development branch, a revision off it, or a range ending at it?"""
    for end in re.split(r"\.\.\.?", word.lstrip("^")):
        base = re.split(r"[~^@]", end, maxsplit=1)[0]
        if base in (
            dev,
            "heads/" + dev,
            "refs/heads/" + dev,
            "origin/" + dev,
            "remotes/origin/" + dev,
            "refs/remotes/origin/" + dev,
        ):
            return True
    return False


def _short(shas, repo):
    names = [_git(repo, "log", "-1", "--format=%h %s", sha) or sha[:9] for sha in sorted(shas)[:4]]
    more = " (and %d more)" % (len(shas) - 4) if len(shas) > 4 else ""
    return "; ".join(names) + more


def _take_reason(sub, args, repo, landing, dev):
    words = _operands(sub, args)
    if sub == "pull":
        remote, specs = (words[0], words[1:]) if words else ("", [])
        sources = []
        for spec in specs:
            src = spec.lstrip("+").partition(":")[0]
            if _names_development(src, dev):
                return "`git pull` takes the development branch `%s` into the landing tree." % dev
            sources.append("refs/remotes/%s/%s" % (remote, src))
        words = sources
    elif sub == "reset":
        words = [w for w in words[:1] if _sha(repo, w)]
    for word in words:
        if _names_development(word, dev):
            return "`git %s %s` takes the development branch `%s` into the landing tree." % (
                sub,
                word,
                dev,
            )
    excl = _existing(
        repo,
        [
            "HEAD",
            "refs/heads/" + landing,
            "refs/heads/main",
            "refs/remotes/origin/main",
            "refs/remotes/origin/" + landing,
        ],
    )
    dev_only = _revs(repo, "refs/heads/" + dev, "--not", *excl)
    if not dev_only:
        return ""
    if sub == "cherry-pick":
        if any(".." in w or w.startswith("^") for w in words):
            picked = _revs(repo, *words) or set()
        else:
            picked = {s for s in (_sha(repo, w) for w in words) if s}
        offenders = picked & dev_only
    else:
        offenders = set()
        for word in words:
            sha = _sha(repo, word)
            if sha:
                offenders |= (_revs(repo, sha, "--not", *excl) or set()) & dev_only
    if offenders:
        return (
            "`git %s` would bring %d development-only commit(s) into the landing branch `%s`: %s."
            % (sub, len(offenders), landing, _short(offenders, repo))
        )
    return ""


def _made_here(repo, landing):
    made = set()
    for ref in ("refs/heads/" + landing, "HEAD"):
        for line in (_git(repo, "log", "-g", "--format=%H\t%gs", ref) or "").splitlines():
            sha, _, subject = line.partition("\t")
            if subject.startswith(MADE_HERE):
                made.add(sha)
    return made


def _push_reason(args, repo, landing, dev):
    parsed = shellscan.git_push_args(args)
    current = commit_policy.current_branch(repo, foreign=True)
    remote = parsed.operands[0] if parsed.operands else commit_policy._default_push_remote(repo)
    pairs = commit_policy.push_destinations(args)
    if not parsed.operands[1:] and not (
        parsed.on("delete") or parsed.on("all") or parsed.on("mirror")
    ):
        pairs = [(current, current)] if current else []
    offenders: set[str] = set()
    for spec_src, spec_dst in pairs:
        src = (current or "HEAD") if spec_src == "HEAD" else spec_src
        dst = current if spec_dst == "HEAD" else spec_dst
        if (dst or "").removeprefix("refs/heads/") == dev:
            continue
        sha = _sha(repo, src)
        if not sha:
            continue
        excl = _existing(
            repo,
            [
                "refs/remotes/%s/%s" % (remote, dst),
                "refs/remotes/%s/%s" % (remote, landing),
                "refs/remotes/%s/main" % remote,
                "refs/heads/main",
            ],
        )
        pushed = _revs(repo, sha, "--not", *excl) or set()
        reach = _revs(repo, "refs/heads/" + dev, "--not", *excl) or set()
        offenders |= pushed & reach
    offenders -= _made_here(repo, landing) if offenders else set()
    if offenders:
        return (
            "this push would publish %d development-only commit(s) from the landing tree: %s."
            % (len(offenders), _short(offenders, repo))
        )
    return ""


def _verdict(cmd, base):
    runs = [
        r
        for r in shellscan.every_run(cmd)
        if r.name.rsplit("/", 1)[-1] == "git" and r.git_sub in JUDGED
    ]
    if not runs:
        return ""
    created = commit_policy.created_dirs(cmd, base)
    for run_ in runs:
        here = commit_policy.effective_dir(run_, base, created)
        repo = commit_policy.toplevel(here)
        if not repo or commit_policy.tree_role(repo) != commit_policy.ROLE_LANDING:
            continue
        record = commit_policy.landing_record(repo)
        if record is None:
            continue
        landing = record["branch"]
        dev = _development_branch(repo, landing)
        if not dev or not _sha(repo, "refs/heads/" + dev):
            continue
        _, sub, args = commit_policy.git_split(run_.argv)
        if sub == "push":
            reason = _push_reason(args, repo, landing, dev)
        else:
            reason = _take_reason(sub, args, repo, landing, dev)
        if reason:
            return reason
    return ""


# ---- the differential's world: a main checkout on the development branch 1121-1 (one development-only commit) and a linked landing tree on 1120-1, bound by the landing record ----
_FIXED_ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _landing_world(path):
    """`path`/main on 1121-1 (seed, then `dev`), `path`/landing a linked tree on 1120-1 at seed, and the record binding it; the landing tree is returned, so an event with no `cwd` starts inside it."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_FIXED_ENV)
    main, landing = path / "main", path / "landing"
    main.mkdir(parents=True)
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["commit", "-q", "--allow-empty", "-m", "seed"],
        ["worktree", "add", "-q", "-b", "1120-1", str(landing), "HEAD"],
        ["checkout", "-q", "-b", "1121-1"],
        ["commit", "-q", "--allow-empty", "-m", "dev"],
    ):
        subprocess.run(["git", *argv], cwd=str(main), check=True, capture_output=True, env=env)
    commit_policy.write_landing_record(str(main), str(landing), "1120-1")
    return os.path.realpath(landing)


FIXTURES = {"landing-world": _landing_world}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("landing", {"CLAUDE_PROJECT_DIR": "{FIXTURE:landing-world}"}, {}),
]

EDGE_CASES = [
    ("rebase onto development", "git rebase 1121-1"),
    ("merge development", "git merge --ff-only 1121-1"),
    ("cherry-pick development", "git cherry-pick 1121-1"),
    ("reset to development", "git reset --hard 1121-1"),
    ("pull development", "git pull origin 1121-1"),
    ("a range ending at development", "git cherry-pick 1120-1..1121-1"),
    ("control: -C into the main checkout", "git -C ../main rebase 1121-1"),
    ("control: rebase continue", "git rebase --continue"),
    ("control: reset to HEAD", "git reset --hard HEAD"),
    ("control: merge main", "git merge main"),
    ("control: push the landing branch", "git push origin 1120-1"),
    ("control: push the development branch", "git push origin 1121-1"),
    ("control: prose", "echo git merge 1121-1"),
    ("control: status", "git status"),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "" or not PREFILTER.search(cmd):
        return hookio.ALLOW
    base = ev.field("cwd") or ev.env("CLAUDE_PROJECT_DIR") or os.getcwd()
    reason = _verdict(cmd, base)
    if reason:
        ev.warn_raw(MESSAGE % reason)
        return hookio.DENY
    return hookio.ALLOW
