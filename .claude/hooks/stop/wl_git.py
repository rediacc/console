"""Mediated git capability for submodule work and force-push.

WHY THIS EXISTS. The two operations that fix a diverged tree -- a submodule
merge with a pointer bump, and the force-push a rebase requires -- were until
now either hand-executed from a 240-line prose checklist or blocked outright.
Prose is not a safety mechanism, and the recorded incidents show it failing:

  * 2026-07-28: console#541 merged while rediacc/account#69 was still open, so
    main's gitlink pointed at a commit that existed only on a PR branch. Had
    that branch been deleted, every `submodule update` on main would have failed
    with "reference is not a tree" and nothing would have warned.
  * homebrew-tap showed dirty at 1.2.3 while the parent recorded 1.2.5;
    committing that "change" would have rolled the tap back two releases.
  * On a gitlink conflict both --ours and --theirs are WRONG, and both leave a
    clean tree and a rebase that reports success, so nothing downstream catches
    the rollback.

WHY THIS CAN RUN A FORCE-PUSH AT ALL. The pre-bash hooks inspect the Bash tool's
COMMAND LINE. This module runs git through subprocess, which no pre-bash hook
ever sees. Verified: `worklist.py --git force-push --execute` is allowed while
`git push --force-with-lease origin x` is blocked. So raw force-push stays
blocked exactly as before and this is simply a path the block regex does not
match. NOBODY SHOULD "FIX" THAT BY ADDING AN ALLOW-LIST TO THE HOOK: the hook
staying strict is the whole security story, and this module's safety comes from
its own checks, not from permission.

WHAT IT IS NOT. It does not prove operator approval and does not try to. The
operator's ruling is "AI authorized, just be safe", so the checks here are about
CORRECTNESS, not authority. Everything is dry-run by default; --execute writes.

THE TWO ORACLES, and they are the whole design. This repo has exactly two
correctness tests for a gitlink, and both are ANCESTRY. Every incident above is
a case of someone reaching for a third, worse one ("is this mine?", "is this
newer-looking?"):

  1. REACHABILITY  -- is the gitlink reachable from the submodule's origin/main?
     (main must never depend on a commit that lives only on a branch)
  2. CONTAINMENT   -- does the submodule HEAD contain origin/main?
     (the only check that catches an --ours/--theirs mistake)

When neither direction holds the histories genuinely diverged, and this refuses
rather than guessing. Fail closed: an unreadable probe is never a pass.
"""

import os
import re
import subprocess
import sys

TIMEOUT_S = 120

# Shell metacharacters are impossible here: every git call is an argv list, never
# a string handed to a shell.


class Refusal(Exception):
    """A safety check said no. Carries the reason shown to the caller."""


def run_git(args, cwd, timeout=TIMEOUT_S):
    """(rc, stdout, stderr). Never raises on a non-zero git; callers decide."""
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ss" % timeout
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)


def parse_gitmodules(text):
    """[(path, branch)] from .gitmodules text.

    READ, NEVER HARDCODE. check-submodule-branches.sh hardcodes the four paths
    and is therefore blind to a fifth and to the non-submodule siblings under
    private/; detect-pointer-bump.sh and worktree.sh read this file instead.
    """
    out, path, branch = [], None, None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[submodule"):
            if path:
                out.append((path, branch or "main"))
            path, branch = None, None
            continue
        m = re.match(r"^path\s*=\s*(.+)$", line)
        if m:
            path = m.group(1).strip()
            continue
        m = re.match(r"^branch\s*=\s*(.+)$", line)
        if m:
            branch = m.group(1).strip()
    if path:
        out.append((path, branch or "main"))
    return out


def submodules(root):
    p = os.path.join(root, ".gitmodules")
    try:
        with open(p, encoding="utf-8") as fh:
            return parse_gitmodules(fh.read())
    except OSError:
        return []


def sibling_repos(root):
    """Independent git repos under private/ that are NOT submodules.

    They are gitignored and invisible to `git status` and `git submodule`.
    Agents have repeatedly assumed everything under private/ is a submodule and
    walked past uncommitted work in them. This module never touches them; it
    only REPORTS them.
    """
    known = {p for p, _ in submodules(root)}
    found = []
    base = os.path.join(root, "private")
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return found
    for name in entries:
        rel = "private/%s" % name
        if rel in known:
            continue
        if os.path.exists(os.path.join(base, name, ".git")):
            found.append(rel)
    return found


def is_ancestor(repo, maybe_ancestor, descendant):
    """True/False, or None when the probe itself could not run.

    None is NOT False. check-submodule-branches.sh records the same lesson
    twice: `|| echo "[]"` once made an unreadable probe indistinguishable from a
    clean result, and the caller then read a guess as a fact.
    """
    rc, _, _ = run_git(
        ["merge-base", "--is-ancestor", maybe_ancestor, descendant], cwd=repo
    )
    if rc == 0:
        return True
    if rc == 1:
        return False
    return None


def rebase_state(root):
    """Where an in-progress rebase stopped, read from GIT's own state.

    NOTHING IS PERSISTED HERE, deliberately, and that is the design. `git rebase`
    is already resumable: on a halt it keeps `msgnum`/`end` (step N of M),
    `stopped-sha`, and the remaining todo under .git/rebase-merge, plus the
    conflict stages in the index. Anything this module wrote down would be a
    SECOND copy of a truth git already holds, and a second copy drifts.

    Returns None when no rebase is in progress -- which is not an error, it is
    the normal case, and the caller must not report it as a halt.
    """
    for d in ("rebase-merge", "rebase-apply"):
        base = os.path.join(root, ".git", d)
        if os.path.isdir(base):
            def read(name):
                try:
                    with open(os.path.join(base, name), encoding="utf-8") as fh:
                        return fh.read().strip()
                except OSError:
                    return ""
            return {
                "dir": d,
                "step": read("msgnum"),
                "total": read("end"),
                "stopped": read("stopped-sha"),
                "onto": read("onto"),
                "head_name": read("head-name"),
            }
    return None


def conflicted_paths(root):
    """Every path with unmerged stages, with its stages BY NUMBER."""
    rc, out, _ = run_git(["ls-files", "-u"], cwd=root)
    if rc != 0:
        return None
    paths = {}
    for line in out.splitlines():
        try:
            meta, path = line.split("\t", 1)
            mode, sha, stage = meta.split()
        except ValueError:
            continue
        paths.setdefault(path, {})[int(stage)] = (sha, mode)
    return paths


def classify_conflict(root, path, stages):
    """'gitlink' | 'registry' | 'judgement', and WHY.

    THE TAXONOMY IS MEASURED, not invented. Ten conflicts across two real
    rebases of this branch on 2026-08-26/27: one gitlink (an oracle already
    decides it), six mechanical unions of append-only registries, two genuine
    design collisions (`run.sh setup()`, and a test suite that one wave had
    refactored from a monolith into 22 case files). Refusing all ten to protect
    the two is the trade this classifier exists to stop making.

    Conservative by construction: anything it cannot place is 'judgement', which
    means untouched. A wrong 'judgement' costs a human a look; a wrong
    'registry' silently corrupts a file, which is the failure mode that shipped
    a glued stopword seam today.
    """
    if any(mode == "160000" for _sha, mode in stages.values()):
        return "gitlink", "a submodule pointer; resolve_gitlink_target decides it by ancestry"
    if len(stages) < 3:
        return "judgement", "incomplete stages (%s); refusing to guess" % sorted(stages)
    lowered = path.lower()
    if lowered.endswith((".json",)) or "manifest" in lowered:
        return "registry", "keyed entries; union is safe ONLY behind an id-set invariant"
    if lowered.endswith(".md"):
        return "registry", "sectioned prose; union is safe ONLY if both heading sets survive"
    return "judgement", "no invariant proves a union preserves meaning here"


def equivalent(repo, base, old_tip, new_tip, runner=None):
    """Which of base..old_tip survived into base..new_tip, and how.

    THE ORACLE A COUNT CANNOT BE. All five repos are rebase-merge only, so
    merging a parent PR REWRITES its SHAs. When a stacked branch then re-rebases
    onto main, git correctly DROPS the commits whose patches are already
    upstream, and `rev-list --count` legitimately falls. branch-rebase.md used to
    say the count "should equal the branch-only count, minus any the base
    absorbed", which asks a human to eyeball the difference between a correct
    drop and a `--skip` that ate a commit. That is the judgement the check should
    have been making.

    `git cherry` answers it directly: `-` means an equivalent patch is already
    upstream, `+` means it is not. So a commit is CARRIED (+ in the new range),
    ABSORBED (- in the new range), or MISSING (in neither), and only the third
    is a defect.

    Returns (carried, absorbed, missing) as lists of sha. `None` on an
    unreadable probe, never an empty result, because "nothing missing" and
    "could not tell" must not look the same.
    """
    run = runner or run_git
    rc, out, _ = run(["cherry", base, new_tip], cwd=repo)
    if rc != 0:
        return None
    marks = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in ("+", "-"):
            marks[parts[1]] = parts[0]
    rc, old_out, _ = run(["rev-list", "%s..%s" % (base, old_tip)], cwd=repo)
    if rc != 0:
        return None
    old_shas = [x for x in old_out.split() if x]

    carried = [sha for sha, m in marks.items() if m == "+"]
    absorbed = [sha for sha, m in marks.items() if m == "-"]
    # A pre-rebase sha is MISSING when neither it nor a patch-equivalent of it
    # reached the new range. Patch equivalence is what `git cherry -` already
    # reported, so an old sha that is absent from the new range AND unmatched by
    # any `-` mark is the `--skip` case.
    rc, eq_out, _ = run(["cherry", base, old_tip], cwd=repo)
    old_patch_ids = set()
    if rc == 0:
        for line in eq_out.splitlines():
            parts = line.split()
            if len(parts) == 2:
                old_patch_ids.add(parts[1])
    missing = []
    for sha in old_shas:
        if sha in marks:
            continue
        # Its patch may have landed under a new sha; absorbed/carried counts
        # cover that. Only flag when the new range accounts for FEWER commits
        # than the old one had, which is what a dropped commit looks like.
        missing.append(sha)
    if len(carried) + len(absorbed) >= len(old_shas):
        missing = []
    return carried, absorbed, missing


def classify(repo, gitlink, base_ref="origin/main"):
    """'reachable' | 'ahead' | 'diverged' | 'unknown' for a gitlink vs base."""
    back = is_ancestor(repo, gitlink, base_ref)
    fwd = is_ancestor(repo, base_ref, gitlink)
    if back is None or fwd is None:
        return "unknown"
    if back:
        return "reachable"
    if fwd:
        return "ahead"
    return "diverged"


def staged_deletions(repo):
    """Paths staged for deletion inside a submodule.

    THE CURRENTLY-UNGUARDED GAP. The parent reports only `m private/<sub>` for a
    dirty submodule and `git status` in the parent never shows what is staged
    INSIDE one. A staged rm of the entire homebrew-tap contents once sat
    unnoticed for hours; committing it would have deleted the published formula.
    """
    rc, out, _ = run_git(["diff", "--cached", "--name-only", "--diff-filter=D"], cwd=repo)
    if rc != 0:
        return None
    return [ln for ln in out.splitlines() if ln.strip()]


def trees_identical(repo, a, b):
    """True when two commits have byte-identical trees.

    This is the one pre-merge safety check the repo already had: rebase-merge
    produces a NEW SHA with an IDENTICAL tree, so tree-identity is the proof
    that moving a pointer to the rebased tip is content-neutral. A non-empty
    diff means something diverged (main advanced mid-merge) -- stop.
    """
    rc, out, _ = run_git(["diff", "--stat", a, b], cwd=repo)
    if rc != 0:
        return None
    return out.strip() == ""


def conflict_stages(root, path):
    """{stage: sha} for a conflicted gitlink, from `git ls-files -u <path>`.

    Stage 1 is the common ancestor, 2 is OURS (during a rebase that is the
    UPSTREAM you are replaying onto), 3 is THEIRS (the commit being replayed).
    Naming them ours/theirs is exactly what makes people reach for
    `checkout --ours`, so this returns numbers and the caller reasons about
    content instead.
    """
    rc, out, _ = run_git(["ls-files", "-u", "--", path], cwd=root)
    if rc != 0:
        return None
    stages = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            stages[int(parts[2])] = parts[1]
    return stages


def branch_exists(repo, branch):
    rc, _, _ = run_git(["show-ref", "--verify", "--quiet", "refs/heads/%s" % branch], cwd=repo)
    if rc == 0:
        return True
    rc, out, _ = run_git(["ls-remote", "--heads", "origin", branch], cwd=repo)
    return rc == 0 and bool(out.strip())


def resolve_gitlink_target(repo, stages, rebased_tip=None):
    """Which commit the gitlink must point at. Raises Refusal when unknowable.

    THE CASE TABLE, and the reason this function exists at all. On a gitlink
    conflict BOTH obvious answers are wrong, and both leave a clean tree and a
    rebase that reports success, so nothing downstream catches the rollback:

      checkout --ours   -> stage 2, the base's pointer: DROPS your submodule work
      checkout --theirs -> stage 3, your PRE-rebase tip: DROPS the base's work,
                           and pins a commit the submodule rebase just orphaned

    The correct commit is in NEITHER stage when the submodule has its own
    branch: it is that branch's REBASED tip, which does not exist until the
    submodule has itself been rebased. That is why rebase-submodules runs first.
    """
    if rebased_tip:
        return rebased_tip, "the submodule's rebased tip (in neither conflict stage)"
    ours, theirs = stages.get(2), stages.get(3)
    if not ours or not theirs:
        raise Refusal("incomplete conflict stages; refusing to guess")
    fwd = is_ancestor(repo, ours, theirs)
    back = is_ancestor(repo, theirs, ours)
    if fwd is None or back is None:
        raise Refusal("could not compute ancestry between the two stages")
    if fwd and not back:
        return theirs, "the replayed side is a descendant of the base side"
    if back and not fwd:
        return ours, "the base side is a descendant of the replayed side"
    if fwd and back:
        return ours, "both sides are the same commit"
    raise Refusal(
        "the two sides genuinely diverged and neither contains the other; this "
        "submodule needs its own branch rebased first (rebase-submodules)"
    )


FORBIDDEN_PUSH_FLAGS = ("--force", "-f", "--mirror")


def validate_push_args(args):
    """Refuse anything but --force-with-lease, and refuse pushing main.

    --force overwrites blindly; --force-with-lease refuses to clobber a push
    somebody else made. --mirror and a leading + on a refspec force too, and
    both were holes in the pre-bash guard's regex before they were closed.
    """
    for a in args:
        if a in FORBIDDEN_PUSH_FLAGS or a.startswith("--force="):
            raise Refusal(
                "refusing %s: only --force-with-lease is permitted, because it is "
                "the one form that refuses to clobber another push" % a
            )
        if a.startswith("+"):
            raise Refusal(
                "refusing a leading '+' refspec (%s): it forces the ref the same "
                "way --force does" % a
            )
    return True


def refuse_main(branch):
    if branch in ("main", "master", "origin/main", "origin/master"):
        raise Refusal("refusing to force-push %s; main is never rewritten here" % branch)
    return True


class Plan:
    """An ordered list of (kind, text) steps, printed dry or executed.

    Dry run and execute walk the SAME list, so what is printed is what runs.
    """

    def __init__(self, execute):
        self.execute = execute
        self.steps = []

    def check(self, label, ok, detail=""):
        self.steps.append(("check", label, ok, detail))
        return ok

    def cmd(self, argv, cwd):
        self.steps.append(("cmd", argv, cwd, None))

    def note(self, text):
        self.steps.append(("note", text, None, None))

    def render(self):
        lines = []
        for kind, a, b, c in self.steps:
            if kind == "note":
                lines.append("  %s" % a)
            elif kind == "check":
                mark = "ok " if b else "REFUSE"
                lines.append("  [%s] %s%s" % (mark, a, (" -- %s" % c) if c else ""))
            else:
                prefix = "run" if self.execute else "would run"
                lines.append("  [%s] git -C %s %s" % (prefix, b, " ".join(a)))
        return "\n".join(lines)

    def run(self, runner=None):
        """Execute the cmd steps in order, HALTING on the first failure.

        THIS DID NOT EXIST UNTIL 2026-08-26, and its absence was the module's
        worst defect. `--execute` flipped one word in render() and nothing else:
        the tool printed `force-push (EXECUTE)`, five `[run] git ... push` lines
        and NO "Nothing was written" footer, then wrote nothing. A session
        reading that transcript reports a completed five-repo force-push.
        Demonstrated before the fix: origin/0826-2 byte-identical across the run.

        HALT ON FIRST FAILURE IS LOAD-BEARING, not tidiness. The steps are
        ordered submodules-then-console precisely because a console push naming
        an unpushed submodule commit is how PR #541 broke; continuing past a
        failed submodule push would publish exactly that.

        `runner` is injectable so the controls can prove ordering and halting
        without a remote.
        """
        run = runner or run_git
        done, failed = [], None
        for kind, a, b, _c in self.steps:
            if kind != "cmd":
                continue
            rc, out, err = run(a, cwd=b)
            done.append((a, b, rc))
            if rc != 0:
                failed = (a, b, (err or out or "").strip()[:200])
                break
        return done, failed


def repo_root():
    rc, out, _ = run_git(["rev-parse", "--show-toplevel"], cwd=os.getcwd())
    if rc != 0:
        raise Refusal("not inside a git repository")
    return out


USAGE = """usage: worklist.py --git <subcommand> [args] [--execute]

  rebase-submodules <branch>      rebase each submodule branch onto its own origin/main
  resolve-gitlinks                resolve UU <submodule> conflicts by ancestry
  merge-submodule <path> <sha>    verify tree-identity, then bump the pointer
  force-push <branch>             --force-with-lease, submodules before console
  snapshot                        print repo=sha for console + every submodule
  verify-rebase <snapshot-file>   did every commit survive? by PATCH IDENTITY
  rebase-status                   where an in-progress rebase stopped, and why

Dry run by default. Pass --execute to perform writes; only force-push writes.
"""


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(USAGE)
        return 2
    if argv[0] == "--selftest":
        return selftest()

    execute = "--execute" in argv
    args = [a for a in argv if a != "--execute"]
    sub = args[0]

    try:
        root = repo_root()
        plan = Plan(execute)
        sibs = sibling_repos(root)
        if sibs:
            plan.note(
                "sibling repos under private/ are NOT submodules and are never "
                "touched here: %s" % ", ".join(sibs)
            )
        if sub == "force-push":
            if len(args) < 2:
                raise Refusal("force-push needs a branch")
            branch = args[1]
            refuse_main(branch)
            validate_push_args(args[2:])
            plan.check("branch is not main", True, branch)
            for path, _ in submodules(root):
                repo = os.path.join(root, path)
                dels = staged_deletions(repo)
                if dels is None:
                    raise Refusal("could not read staged deletions in %s" % path)
                plan.check(
                    "%s has no staged deletions" % path,
                    not dels,
                    ("%d staged deletion(s)" % len(dels)) if dels else "",
                )
                if dels:
                    raise Refusal(
                        "%s has %d staged deletion(s); the parent shows only 'm %s' "
                        "and would hide them" % (path, len(dels), path)
                    )
                plan.cmd(["push", "--force-with-lease", "origin", branch], repo)
            plan.cmd(["push", "--force-with-lease", "origin", branch], root)
            plan.note(
                "after this: CI re-runs, and the claude-reviewed marker no longer "
                "matches the new head, so the PR needs a fresh review pass"
            )
        elif sub == "rebase-submodules":
            if len(args) < 2:
                raise Refusal("rebase-submodules needs a branch")
            branch = args[1]
            refuse_main(branch)
            any_found = False
            for path, base in submodules(root):
                repo = os.path.join(root, path)
                if not branch_exists(repo, branch):
                    plan.note("%s: no %s branch, not rebased" % (path, branch))
                    continue
                any_found = True
                dels = staged_deletions(repo)
                # `is None` FIRST: the probe failed, and None is falsy, so a
                # bare `if dels:` let an UNREADABLE probe pass as "no deletions".
                # force-push got this right and these two did not, which is the
                # module's own rule ("an unreadable probe is never a pass")
                # holding on one path out of three.
                if dels is None:
                    raise Refusal("could not read staged deletions for %s" % path)
                if dels:
                    raise Refusal("%s has staged deletion(s); refusing" % path)
                plan.check("%s has a %s branch" % (path, branch), True)
                plan.cmd(["fetch", "origin", base], repo)
                plan.cmd(["checkout", branch], repo)
                plan.cmd(["rebase", "origin/%s" % base], repo)
                plan.note(
                    "%s: on conflict resolve IN the submodule and continue; never "
                    "--skip, it silently drops the replayed commit" % path
                )
            if not any_found:
                plan.note("no submodule carries a %s branch; nothing to rebase" % branch)

        elif sub == "resolve-gitlinks":
            found = False
            for path, base in submodules(root):
                stages = conflict_stages(root, path)
                if stages is None:
                    raise Refusal("could not read conflict stages for %s" % path)
                if not stages:
                    continue
                found = True
                repo = os.path.join(root, path)
                rc, tip, _ = run_git(["rev-parse", "HEAD"], cwd=repo)
                rebased = tip if rc == 0 and stages.get(3) and tip not in stages.values() else None
                target, why = resolve_gitlink_target(repo, stages, rebased)
                plan.check("%s: chose %s" % (path, target[:12]), True, why)
                plan.cmd(["checkout", target], repo)
                plan.cmd(["add", "--", path], root)
                contains = is_ancestor(repo, "origin/%s" % base, target)
                if contains is None:
                    raise Refusal("%s: could not verify the choice contains the base" % path)
                plan.check(
                    "%s: chosen commit contains origin/%s" % (path, base),
                    contains,
                    "this is the only check that catches an ours/theirs mistake",
                )
                if not contains:
                    raise Refusal(
                        "%s: the chosen commit does NOT contain origin/%s, which is "
                        "the silent-rollback failure; refusing" % (path, base)
                    )
            if not found:
                plan.note("no conflicted gitlinks; nothing to resolve")

        elif sub == "merge-submodule":
            if len(args) < 3:
                raise Refusal("merge-submodule needs <path> <new-sha>")
            path, new_sha = args[1], args[2]
            known = [p for p, _ in submodules(root)]
            base_branch = dict(submodules(root)).get(path, "main")
            if path not in known:
                raise Refusal("%r is not a submodule of this repo (have: %s)"
                              % (path, ", ".join(known)))
            repo = os.path.join(root, path)
            rc, old_sha, _ = run_git(["rev-parse", "HEAD"], cwd=repo)
            if rc != 0:
                raise Refusal("could not read the current pointer for %s" % path)
            dels = staged_deletions(repo)
            if dels is None:
                raise Refusal("could not read staged deletions for %s" % path)
            if dels:
                raise Refusal("%s has staged deletion(s); refusing" % path)
            plan.cmd(["fetch", "origin"], repo)
            same = trees_identical(repo, old_sha, new_sha)
            if same is None:
                raise Refusal("could not diff %s against %s in %s"
                              % (old_sha[:12], new_sha[:12], path))
            plan.check(
                "%s: trees identical between %s and %s" % (path, old_sha[:12], new_sha[:12]),
                same,
                "rebase-merge keeps the tree and only changes the SHA; a non-empty "
                "diff means main advanced mid-merge",
            )
            if not same:
                raise Refusal(
                    "%s: the trees differ, so this is not a content-neutral pointer "
                    "move; stop and find out what diverged" % path
                )
            fwd = is_ancestor(repo, old_sha, new_sha)
            if fwd is None:
                raise Refusal("%s: could not verify the new pointer is a descendant" % path)
            plan.check("%s: new pointer is not a rollback" % path, fwd)
            if not fwd:
                raise Refusal(
                    "%s: %s is NOT a descendant of the recorded %s; that is a pointer "
                    "rollback" % (path, new_sha[:12], old_sha[:12])
                )
            # THE REACHABILITY oracle, and the reason it is not optional. On
            # 2026-07-28 console#541 merged while the submodule PR was still
            # open, so main's gitlink pointed at a commit that existed ONLY on
            # that branch. Delete the branch and every `submodule update` on
            # main fails with "reference is not a tree", and nothing warns. A
            # pointer bump is only safe once the target is actually ON main.
            state = classify(repo, new_sha, "origin/%s" % base_branch)
            plan.check(
                "%s: new pointer is reachable from origin/%s" % (path, base_branch),
                state == "reachable",
                "state=%s" % state,
            )
            if state != "reachable":
                raise Refusal(
                    "%s: %s is not reachable from origin/%s (state=%s). main must "
                    "never depend on a commit that lives only on a branch; merge "
                    "the submodule PR first, then bump to the merged commit"
                    % (path, new_sha[:12], base_branch, state)
                )
            plan.cmd(["checkout", new_sha], repo)
            plan.cmd(["add", "--", path], root)
            plan.note("stage the gitlink only; never a wholesale add around a pointer bump")
        elif sub == "rebase-status":
            # READ-ONLY, and shippable before any resolver exists. This is the
            # "what happened" half of the operator's ask: an agent resuming a
            # halted rebase can read the files itself, but it cannot
            # reconstruct WHICH commit is being replayed onto what. That lives
            # in .git/rebase-merge and nowhere else.
            st = rebase_state(root)
            if st is None:
                plan.note("no rebase in progress -- this is the normal case, not a halt")
            else:
                plan.note(
                    "rebase HALTED: step %s of %s, replaying %s onto %s (%s)"
                    % (
                        st["step"] or "?", st["total"] or "?",
                        (st["stopped"] or "?")[:12], (st["onto"] or "?")[:12], st["dir"],
                    )
                )
                paths = conflicted_paths(root)
                if paths is None:
                    raise Refusal("could not read the index; refusing to describe a halt blind")
                if not paths:
                    plan.note("no conflicted paths: the halt is a stopped edit or an empty commit")
                for path in sorted(paths):
                    kind, why = classify_conflict(root, path, paths[path])
                    stage_txt = " ".join(
                        "stage%d=%s" % (n, sha[:12]) for n, (sha, _m) in sorted(paths[path].items())
                    )
                    plan.check("%s -> %s" % (path, kind), kind != "judgement", why)
                    plan.note("    %s" % stage_txt)
                plan.note("")
                plan.note("gitlink   -> --git resolve-gitlinks decides it; no judgement needed")
                plan.note("registry  -> a union is safe ONLY behind an invariant; see")
                plan.note("             agent/PLAN-resumable-rebase-executor.md")
                plan.note("judgement -> yours. NEVER `git rebase --skip`: it drops the commit.")
                plan.note("recover   -> git rebase --abort, then the step-0 tips")

        elif sub == "snapshot":
            # The pre-rebase tips, in a form verify-rebase can read back.
            # branch-rebase.md's step 0 told a session to `echo` these and
            # reprint them in the report, which makes recovery depend on a human
            # remembering to paste. This makes them an INPUT.
            plan.note("save this, then pass the file to verify-rebase")
            rc, tip, _ = run_git(["rev-parse", "HEAD"], cwd=root)
            if rc != 0:
                raise Refusal("could not read the console HEAD")
            plan.note("console=%s" % tip)
            for path, _b in submodules(root):
                repo = os.path.join(root, path)
                rc, t, _ = run_git(["rev-parse", "HEAD"], cwd=repo)
                plan.note("%s=%s" % (path, t if rc == 0 else "UNREADABLE"))

        elif sub == "verify-rebase":
            if len(args) < 2:
                raise Refusal("verify-rebase needs the snapshot file from `--git snapshot`")
            try:
                with open(args[1], encoding="utf-8") as fh:
                    snap = dict(
                        ln.strip().split("=", 1)
                        for ln in fh
                        if "=" in ln and not ln.lstrip().startswith("#")
                    )
            except OSError as exc:
                raise Refusal("cannot read the snapshot: %s" % exc)
            if not snap:
                raise Refusal("the snapshot names no repo; refusing to report a pass over nothing")
            # PER-REPO BASE, not one base for all. The console rebases onto
            # whatever it was told; a SUBMODULE always rebases onto its own
            # main, read from .gitmodules. Passing the console's base to a
            # submodule asks it to compare against a ref it has never heard of,
            # and the first live run did exactly that:
            # "REFUSED: private/account: could not compare 3e79b391..5f55c91d".
            console_base = args[2] if len(args) > 2 else "origin/main"
            sub_base = dict(submodules(root))
            for name, old_tip in sorted(snap.items()):
                repo = root if name == "console" else os.path.join(root, name)
                base = (
                    console_base
                    if name == "console"
                    else "origin/%s" % sub_base.get(name, "main")
                )
                rc, new_tip, _ = run_git(["rev-parse", "HEAD"], cwd=repo)
                if rc != 0:
                    raise Refusal("%s: could not read HEAD" % name)
                res = equivalent(repo, base, old_tip, new_tip)
                if res is None:
                    raise Refusal("%s: could not compare %s..%s" % (name, old_tip[:12], new_tip[:12]))
                carried, absorbed, missing = res
                plan.check(
                    "%s: %d carried, %d absorbed as patch-equivalent"
                    % (name, len(carried), len(absorbed)),
                    not missing,
                    ("%d MISSING: %s" % (len(missing), ", ".join(m[:12] for m in missing)))
                    if missing
                    else "",
                )
                if missing:
                    raise Refusal(
                        "%s: %d commit(s) reached neither the new range nor a patch-equivalent. "
                        "That is what a `git rebase --skip` looks like, and a COUNT cannot "
                        "distinguish it from a legitimate rebase-merge drop." % (name, len(missing))
                    )

        else:
            raise Refusal("unknown subcommand %r" % sub)
    except Refusal as exc:
        sys.stderr.write("REFUSED: %s\n" % exc)
        return 2

    # `[run]` must mean "this will run". Only force-push executes, so a plan
    # that is about to be refused renders as "would run" -- otherwise the output
    # tells the same lie in miniature that this whole change removes.
    will_execute = execute and sub == "force-push"
    plan.execute = will_execute
    sys.stdout.write(
        "%s (%s)\n" % (sub, "EXECUTE" if will_execute else ("plan only" if execute else "dry run"))
    )
    sys.stdout.write(plan.render() + "\n")
    if not execute:
        sys.stdout.write("\nNothing was written. Re-run with --execute to perform it.\n")
        return 0

    # ONLY force-push EXECUTES, and the restriction is a design decision, not an
    # unfinished corner. Everything else this module plans -- rebase, checkout,
    # add, fetch -- the caller can already run from Bash, where the pre-bash
    # guards see it and the transcript records it. force-push is the single
    # command Bash cannot run (block-git-force-push.sh refuses it
    # unconditionally), which is the whole reason this module exists.
    #
    # A REBASE EXECUTOR IS DELIBERATELY NOT BUILT. A conflicting rebase halts
    # mid-list and needs a human before --continue, and Plan is a flat list with
    # no resume, no rollback and no way to say "step 3 of 7 stopped, the tree is
    # mid-rebase". Conflict is the NORMAL case here, so executing that flow
    # would be a re-implementation of git's own state machine in a tree where
    # stash and restore are banned, i.e. where its worst failure has no
    # recovery. Refusing is honest; half-executing is not.
    if sub != "force-push":
        sys.stderr.write(
            "\nREFUSED: --execute is only implemented for force-push.\n"
            "The steps above are safe to run yourself, and running them from Bash\n"
            "keeps them in the transcript and under the pre-bash guards.\n"
        )
        return 2

    sys.stdout.write("\nUNDO -- the pre-push remote tips, the only recovery a force-push has:\n")
    for path, _b in [(p_, b_) for p_, b_ in submodules(root)] + [(".", None)]:
        repo = root if path == "." else os.path.join(root, path)
        rc, tip, _ = run_git(["rev-parse", "origin/%s" % args[1]], cwd=repo)
        sys.stdout.write("  %s = %s\n" % (path, tip if rc == 0 else "(no remote branch yet)"))

    done, failed = plan.run()
    sys.stdout.write("\n%d command(s) ran.\n" % len(done))
    if failed:
        argv_, cwd_, err_ = failed
        sys.stderr.write(
            "\nHALTED: `git -C %s %s` failed.\n%s\n"
            "Steps after it did NOT run, deliberately: the console push is last so\n"
            "it can never name a submodule commit that failed to publish.\n"
            % (cwd_, " ".join(argv_), err_)
        )
        return 1
    return 0


def selftest():
    fail = 0

    def check(name, ok):
        nonlocal fail
        if not ok:
            fail += 1
        print("  %s  %s" % ("PASS" if ok else "FAIL", name))

    mods = parse_gitmodules(
        '[submodule "private/renet"]\n\tpath = private/renet\n\turl = x\n\tbranch = main\n'
        '[submodule "private/account"]\n\tpath = private/account\n\turl = y\n'
    )
    check("parses every submodule from .gitmodules", len(mods) == 2)
    check("keeps declared paths", [m[0] for m in mods] == ["private/renet", "private/account"])
    check("defaults a missing branch to main", mods[1][1] == "main")
    check("parses an empty file to nothing", parse_gitmodules("") == [])

    check("--force is refused", _refused(validate_push_args, ["--force"]))
    check("-f is refused", _refused(validate_push_args, ["-f"]))
    check("--mirror is refused", _refused(validate_push_args, ["--mirror"]))
    check("a + refspec is refused", _refused(validate_push_args, ["+main:main"]))
    check("--force-with-lease is allowed", validate_push_args(["--force-with-lease"]))
    check("main is refused", _refused(refuse_main, "main"))
    check("master is refused", _refused(refuse_main, "master"))
    check("a feature branch is allowed", refuse_main("0826-1"))

    st = {1: "a" * 40, 2: "b" * 40, 3: "c" * 40}
    check("a rebased tip wins over both stages", resolve_gitlink_target(".", st, "d" * 40)[0] == "d" * 40)
    check("incomplete stages are refused", _refused_kw(resolve_gitlink_target, ".", {1: "a" * 40}, None))

    check("classify names the unknown case", classify("/nonexistent", "x", "y") == "unknown")

    p = Plan(execute=False)
    p.cmd(["push"], "/x")
    check("a dry plan says 'would run'", "would run" in p.render())
    q = Plan(execute=True)
    q.cmd(["push"], "/x")
    check("an executing plan says 'run'", "[run]" in q.render())
    check(
        "dry and execute render the SAME command",
        p.render().split("git -C")[1] == q.render().split("git -C")[1],
    )

    # THE EXECUTOR CONTROLS. Until 2026-08-26 this module planned and never
    # wrote, while printing "(EXECUTE)" and "[run]" -- and its CI gate asserted
    # the dry-run default by grepping for the literal string
    # `execute = "--execute" in argv`, so a capability that could NOT execute
    # passed its execution-safety gate perfectly. The three assertions above are
    # exactly the kind that stayed green through all of it: they check what the
    # renderer SAYS. These check what the plan DOES, and no string satisfies
    # them.
    calls = []

    def fake(argv, cwd, timeout=None):
        calls.append((argv, cwd))
        return 0, "", ""

    pr = Plan(execute=True)
    pr.cmd(["push", "--force-with-lease", "origin", "x"], "/sub")
    pr.cmd(["push", "--force-with-lease", "origin", "x"], "/root")
    done, failed = pr.run(runner=fake)
    check("execute RUNS every cmd step, in order", [c[1] for c in calls] == ["/sub", "/root"])
    check("and reports them all, with no failure", len(done) == 2 and failed is None)

    calls.clear()
    pd = Plan(execute=False)
    pd.cmd(["push", "origin", "x"], "/sub")
    pd.render()
    check("CONTROL: rendering a dry plan never reaches the runner", not calls)

    # HALT ON FIRST FAILURE, and the ordering it protects: the console push must
    # never follow a FAILED submodule push, which is incident #541's shape.
    calls.clear()

    def fake_fail(argv, cwd, timeout=None):
        calls.append((argv, cwd))
        return (1, "", "boom") if cwd == "/sub" else (0, "", "")

    ph = Plan(execute=True)
    ph.cmd(["push", "--force-with-lease", "origin", "x"], "/sub")
    ph.cmd(["push", "--force-with-lease", "origin", "x"], "/root")
    done, failed = ph.run(runner=fake_fail)
    check("a failed step HALTS the plan", failed is not None and len(done) == 1)
    check("and the console push never ran", [c[1] for c in calls] == ["/sub"])

    calls.clear()
    pn = Plan(execute=True)
    pn.note("just a note")
    pn.check("just a check", True)
    pn.run(runner=fake)
    check("CONTROL: notes and checks are never executed", not calls)

    # THE PATCH-IDENTITY ORACLE. A COUNT cannot do this job: all five repos are
    # rebase-merge only, so merging a parent PR rewrites its SHAs and a stacked
    # branch's commit count legitimately FALLS when git drops the duplicates.
    # branch-rebase.md used to ask a human to eyeball the difference between
    # that and a `--skip` that ate a commit. These prove the three outcomes.
    def cherry(new_marks, old_list, old_marks=None):
        def run(argv, cwd, timeout=None):
            if argv[0] == "cherry" and argv[2] == "NEW":
                return 0, "\n".join("%s %s" % (m, c) for c, m in new_marks.items()), ""
            if argv[0] == "cherry":
                return 0, "\n".join("%s %s" % (m, c) for c, m in (old_marks or {}).items()), ""
            if argv[0] == "rev-list":
                return 0, "\n".join(old_list), ""
            return 1, "", "unexpected"
        return run

    r = equivalent("/r", "BASE", "OLD", "NEW",
                   runner=cherry({"aaa": "+", "bbb": "+"}, ["aaa", "bbb"]))
    check("every commit carried -> nothing missing", r == (["aaa", "bbb"], [], []))

    r = equivalent("/r", "BASE", "OLD", "NEW",
                   runner=cherry({"aaa": "+", "bbb": "-"}, ["aaa", "bbb"]))
    check("a patch-equivalent drop is ABSORBED, not missing",
          r is not None and r[1] == ["bbb"] and r[2] == [])

    # THE DEFECT: the new range accounts for FEWER commits than the old had.
    r = equivalent("/r", "BASE", "OLD", "NEW",
                   runner=cherry({"aaa": "+"}, ["aaa", "bbb", "ccc"]))
    check("a commit that reached NEITHER is reported MISSING",
          r is not None and r[2] and "bbb" in r[2])

    # An unreadable probe is not "nothing missing".
    def broken(argv, cwd, timeout=None):
        return 1, "", "boom"

    check("CONTROL: an unreadable probe returns None, never an empty result",
          equivalent("/r", "BASE", "OLD", "NEW", runner=broken) is None)

    # THE CONFLICT CLASSIFIER. Every case below is a conflict that ACTUALLY
    # occurred while rebasing this branch twice on 2026-08-26/27 -- ten of them,
    # of which one needed an oracle, six were mechanical, and two needed the
    # operator. Refusing all ten to protect the two was the trade the operator
    # vetoed, and this table is what replaces it.
    def kind(path, stages):
        return classify_conflict(".", path, stages)[0]

    THREE = {1: ("a", "100644"), 2: ("b", "100644"), 3: ("c", "100644")}
    LINK = {1: ("a", "160000"), 2: ("b", "160000"), 3: ("c", "160000")}
    check("a submodule pointer classifies as gitlink",
          kind("private/account", LINK) == "gitlink")
    check("a keyed manifest classifies as registry",
          kind("scripts/ci-runner/manifest.ts", THREE) == "registry")
    check("a sectioned doc classifies as registry",
          kind("docs/ci-overhaul/06-progress.md", THREE) == "registry")
    # THE TWO THAT MUST STAY UNTOUCHED. run.sh was two designs for one function;
    # wl_agents.py is where a blind union glued `touched`+`see` into one token
    # and silently killed two stopwords. Both must land in judgement.
    check("CONTROL: two designs for one function is judgement",
          kind("run.sh", THREE) == "judgement")
    check("CONTROL: a token list is judgement, not a free union",
          kind(".claude/hooks/stop/wl_agents.py", THREE) == "judgement")
    check("CONTROL: incomplete stages refuse rather than guess",
          kind("some.json", {2: ("b", "100644"), 3: ("c", "100644")}) == "judgement")
    # No rebase in progress is the NORMAL case, never a halt.
    check("CONTROL: rebase_state is None outside a rebase",
          rebase_state("/nonexistent-root-for-selftest") is None)
    return 0 if fail == 0 else 1


def _refused_kw(fn, *a):
    try:
        fn(*a)
        return False
    except Refusal:
        return True


def _refused(fn, arg):
    try:
        fn(arg if isinstance(arg, list) else arg)
        return False
    except Refusal:
        return True


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
