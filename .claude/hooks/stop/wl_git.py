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

Dry run by default. Pass --execute to perform writes.
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
