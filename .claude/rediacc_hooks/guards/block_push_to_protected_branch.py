"""Refuse `git push` when its destination resolves to `main`, in any spelling.

THE INCIDENT THIS CLOSES, 2026-09-22. A background sub-agent ran `.ci/scripts/release/update-homebrew-tap.sh --push` as a W7P5-a real-run rehearsal. That script's `update_submodule_pointer()` does, from the REAL working checkout (not an isolated clone):

    git -c user.name=... -c user.email=... commit -m "chore(release): update homebrew-tap ..."
    git push origin HEAD:main

Nobody typed `git push origin HEAD:main` that day. A shell script three process-levels down the Bash tool call did, and NOTHING in the pre-bash chain inspected it, because every guard in this package (including `block_git_force_push.py`, the nearest thing) reads the literal command TEXT the Bash tool was invoked with -- `.ci/scripts/release/update-homebrew-tap.sh --push` -- which
never contains the string "git push" at all. The dangerous command lived inside a file on disk, not on the command line, and a text scanner cannot see into a file it was never asked to read. That gap is NOT closed by this guard either: it is recorded here so it is not mistaken for closed, and the real, durable fix is the class of fix CLAUDE.md's worklist owns (the script itself
must never push from `$REPO_ROOT` -- it is out of this guard's reach, `.ci/scripts/release/**` is explicitly off limits to it).

What this guard DOES close is the other half: an agent's own Bash tool typing `git push` straight at `main`, or a wrapper (`eval`, `sh -c`) doing the same. GitHub's own ruleset let the push through as an ADMIN BYPASS (`gh api repos/rediacc/console/rulesets/12344707`: `bypass_actors` grants `RepositoryRole` id 5 "always" bypass of both the pull-request rule and the
required-status-checks rule; the push output's own text, "Bypassed rule violations... 2 of 2 required status checks are expected", is that bypass firing) -- so GitHub-side protection was never going to stop a credential that already has bypass rights, and a hook that only fires from THIS tool's own Bash calls is the one lever that does not depend on GitHub's configuration at all.
The open PR for the branch then auto-flipped to MERGED, even though `ci.yml`'s last several runs on that branch were red: GitHub does that whenever a PR branch's commits land on the base branch by ANY means, push included, which is a second reason "check CI before push" is the wrong shape of fix here -- CI's colour was never consulted by GitHub either, once the commits were on
`main`.

WHY "CHECK CI FIRST" WAS NOT THE FIX, and is still not the whole of it. A guard conditioned only on CI colour would have let this exact incident through: nothing asked GitHub what colour CI was, the push simply ran, from a script, with HEAD as its source. So the default stays a refusal of every direct push to `main`, in every spelling below, and normal landings go through `gh pr merge <n> --rebase --auto` (`.claude/commands/pr-merge.md`).

THE ONE ADMITTED DIRECT PUSH, box M2 of PLAN-plan-per-pr-loop (operator ruling 2026-10-02, worklist #7c70e8b9). When GitHub cannot rebase the open PR ("This branch can't be rebased"), `main` may move by a fast-forward to the live branch's pushed tip. Every condition below must hold, and any one that cannot be READ is a refusal:

  (a) one `git push` in the command, to `origin`, with exactly one refspec `<src>:main` (or `:refs/heads/main`) and no flag but -q/-v: no --force, --force-with-lease, `+`, --delete, --tags, --follow-tags, --all or --mirror;
  (b) `<src>` is the live branch (`<b>`, `origin/<b>`, their `refs/` spellings) or a commit sha, never `HEAD` (the incident's shape), and the checkout is the console's own, on its `MMDD-N` branch;
  (c) the commit is exactly `origin/<b>`, the branch's pushed tip, and `origin/main` is its ancestor (`commit_policy.ff_fallback_refusal`, shared with the git-level `pre-push` hook);
  (d) it is the head of the OPEN PR for `<b>` (`gh pr view`), and CI Complete is SUCCESS on it, read through `.ci/scripts/ci/ci-trace.py --json --ref <b>`, the sanctioned tracer, never a raw check read;
  (e) the plan gate (box L2, `plan_gate.plan_merge_refusal`, shared with `block_admin_merge`): the PR body's `Plan: agent/plans/PLAN-<slug>.md` line names a plan whose boxes are all ticked in the commit being pushed (with `turbo: on` in agent/plans/QUEUE.md in that same commit, any number of plans, each with every box ticked, agent/plans/PLAN-stop-hook-turbo.md D6), or the body carries an `Operational-Reason:` line. A body that cannot be read, or that names no plan and gives no reason, is refused.

THE GITLAB MIRROR PUSH (operator ruling 2026-10-03, worklist #1cad85a1: "Allow the agent to push it"). Step 6b of `.claude/commands/pr-merge.md` copies GitHub's `main` to the self-hosted mirror after each merge. It is admitted only as:

  (f) one `git push` to the remote named `gitlab`, with exactly one refspec `main:main` or `refs/heads/main:refs/heads/main` and no flag but `--follow-tags`, -q and -v: no --force, --force-with-lease, `+`, --delete, --tags, --all or --mirror;
  (g) every fetch and push URL `git remote get-url --all [--push] gitlab` reports is the console mirror (`githooks.mirror_url_refusal`, the pin and why it is a literal are there);
  (h) the push runs in the console checkout itself (not a submodule, not `-C` elsewhere), and local `main` is exactly `origin/main` (`githooks.mirror_main_refusal`, shared with the git-level `pre-push` hook): the mirror only ever copies what GitHub's `main` already has.

The receipt rule (`block_unverified_push`, later in this chain) still applies to the push. GitHub's own rulesets (24351140: deletion, non_fast_forward, required_linear_history; 12344707: required CI Complete) back the same shape server-side.

A DRY RUN IS EXEMPT ONLY WHEN EVERY PUSH IN THE COMMAND IS ONE. Until 2026-10-02 a `--dry-run` anywhere in the text exempted the whole command, so `git push --dry-run origin x; git push origin HEAD:main` passed.

WHAT COUNTS AS "main", explicit or not:
  git push origin main                     bare destination name
  git push origin HEAD:main                the incident's own shape
  git push origin refs/heads/main          the long form
  git push origin <anything>:main          any source, explicit destination
  git push origin :main                    the empty-source delete form
  git push origin --delete main            the flagged delete form
  git push --all origin                    every branch, main included
  git push --mirror gitlab                 every ref, main included (until 2026-10-03 this
                                            fell through to the implicit-branch check and
                                            passed from any branch but main)
  git push                                 no refspec at all -- git's own
  git push origin                          fallback (push.default) is the
  git push origin HEAD                     CURRENT branch, or its remote-
                                            side alias HEAD; this checkout's
                                            actual branch decides these three

Each form is matched in the command text AND in the lexer's canonical spelling of every push (`commit_policy.push_texts`), so `git -C <dir> push ...`, `git -c k=v push ...` and `git --no-pager push ...` are judged like `git push ...`: measured 2026-10-02, `git -C . push origin HEAD:main` passed this guard at rc 0 because a word sat between `git` and `push`.

A bare `--tags` push moves no branch ref at all and is let through even while sitting on `main`; `--follow-tags` is NOT exempted, because unlike `--tags` it also pushes the current branch.

FAILS OPEN on the branch lookup for the three implicit forms (`git symbolic-ref` itself failing, a detached HEAD, no such repo): the same command would fail at the real `git` layer too, so refusing here buys nothing and an outage over a broken lookup is the wrong direction for a guard whose whole job is to stay out of the way of everything except main.
"""

import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

from rediacc_hooks import commit_policy, hookio, plan_gate, shellscan
from rediacc_hooks.wellknown import GH_REPO

CHAIN = "pre-bash"
OWN_SUITE = True
# AHEAD OF block_unverified_push (its old position, now 40), deliberately: "this branch may not be pushed to at all" is the more fundamental refusal, and telling a session to go run `npm run ci:quick` for a push it was never going to be allowed to make, regardless of that run's colour, is the wrong message to lead with. Every guard from here on was re-keyed by one to make room.
ORDER = 38

# `run` reaching the branch check is the whole reason this guard exists for the IMPLICIT forms; the header records why the check itself must fire on "main" rather than skip it.
DEFECT = ('if branch == "main":', "if False:")

# THE THREE GIT WORLDS THE IMPLICIT FORMS DISTINGUISH, same reasoning as block_merge_with_unpushed.py's own ENVS: run against THIS checkout (whatever feature branch a session happens to be on) a bare `git push` always takes the "not main" branch of the fallback logic, so the corpus alone proves nothing about the branch check -- and the defect above would pass
# silently planted, exactly as it did before this was added (test_the_differential_can_fail caught it live on 2026-09-22).
ENVS = [
    ("main-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("feature-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    # A FROZEN clone of this checkout rather than the live one, for the reason block_merge_with_unpushed.py:31 records: a shared tree's branch moves under a running differential. Same snapshot, built once per session.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
]

GIT_AT_CMD = hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+")
GIT_PUSH_AT_CMD = GIT_AT_CMD + hookio.rx(r"push([{S}]|$)")


# Explicit destination "main": a colon-qualified refspec (`<src>:main`, `<src>:refs/heads/main`, the empty-source delete form `:main`) or a BARE token naming it directly (`git push origin main`, `git push origin refs/heads/main`). Left boundary is a run's start, whitespace, or the refspec colon; right boundary is whitespace, a closing paren, or the end of the statement. `[^;&|)]*`
# bounds the match to THIS invocation, the same convention `block_git_force_push.py` and `block_unverified_push.py` already use for "the rest of this command, not the rest of the line".
DEST_MAIN = hookio.rx(r"git push[^;&|)]*[{S}:](refs/heads/)?main([{S})]|$)")

# `--all` pushes every branch, main included, and `--mirror` every ref.
ALL_BRANCHES = hookio.rx(r"git push[^;&|)]*[{S}]--(all|mirror)([{S})]|$)")

# `--tags` pushes only tag refs -- no branch ref moves, so this is not this guard's business even while sitting on main. `--follow-tags` is deliberately NOT matched here: unlike `--tags` it also pushes the current branch, so it falls through to BARE_PUSH below instead.
TAGS_ONLY = hookio.rx(r"git push[^;&|)]*[{S}]--tags([{S})]|$)")

# No destination named at all: `git push`, or `git push <remote>` with only recognised flags and at most one bare word (the remote). Git's own fallback (push.default, "simple" since Git 2.0) is to push the CURRENT branch to its upstream, so whether that lands on `main` depends on what branch this checkout is on -- read below rather than guessed here.
BARE_PUSH = hookio.rx(
    r"git push([{S}]+(--[A-Za-z-]+(=[^{S};&|)]*)?|-[A-Za-z]+))*([{S}]+[A-Za-z0-9_.-]+)?[{S}]*([;&|)]|$)"
)

# `git push <remote> HEAD` (no colon) is git's documented alias for "the remote branch of the SAME NAME as the branch checked out here" -- the colon-less twin of the incident's own `HEAD:main`, just as blind to which branch that resolves to without reading this checkout.
BARE_HEAD = hookio.rx(r"git push[^;&|)]*[{S}]HEAD([{S})]|$)")

# One match per `git push` statement in the text, to compare against what the lexer placed.
ANY_PUSH = hookio.rx(r"git push([{S};&|)]|$)")

# The fast-forward fallback (box M2): the one tracer it reads CI through, the flags it tolerates, and the proof line it requires in the PR body.
# Anchored on the rediacc_hooks package, not on this file: the differential suite runs a planted copy of a guard from a temporary directory, where `__file__`'s parents name nothing in the repository.
HOOKS_PKG = pathlib.Path(hookio.__file__).resolve().parent
CI_TRACE = HOOKS_PKG.parents[1] / ".ci" / "scripts" / "ci" / "ci-trace.py"
FF_QUIET = frozenset(("-q", "--quiet", "-v", "--verbose"))
MAIN_NAMES = ("main", "refs/heads/main")
SHA = re.compile(r"^[0-9a-f]{7,40}$")
# The GitLab mirror push (operator ruling 2026-10-03): its flags, and the git-level hook module whose URL pin and ref check it shares, loaded BY FILE like the hook shims load it.
MIRROR_FLAGS = FF_QUIET | {"--follow-tags"}
_GITHOOKS_SPEC = importlib.util.spec_from_file_location(
    "rediacc_hooks._githooks", HOOKS_PKG / "git" / "githooks.py"
)
if _GITHOOKS_SPEC is None or _GITHOOKS_SPEC.loader is None:
    raise ImportError("block_push_to_protected_branch: git/githooks.py is missing")
githooks = importlib.util.module_from_spec(_GITHOOKS_SPEC)
_GITHOOKS_SPEC.loader.exec_module(githooks)
# Every field of the `gh pr view` answer the fallback reads. A missing one is refused by name (65f2a27e.2: it used to read "PR #None").
PR_FIELDS = ("number", "state", "headRefOid", "body")

MESSAGE = (
    "BLOCKED: this pushes straight to a PROTECTED branch (main). Direct pushes bypass code review and required status checks -- which is exactly what happened on 2026-09-22, when a script run through this tool's own Bash access (update-homebrew-tap.sh's update_submodule_pointer()) ran `git push origin HEAD:main` from the real working checkout, GitHub let it through as an admin bypass, and the branch's open PR auto-flipped to MERGED with red CI on its last several runs.\n"
    "\n"
    "Refused in every spelling: explicit (`git push origin main`, `HEAD:main`, `refs/heads/main`, `:main`, `--delete main`, `--all`, with or without `-C`/`-c` before `push`) or implicit (a bare `git push` / `git push origin` / `git push origin HEAD` while this checkout is ON main).\n"
    "\n"
    "Land through the PR: `gh pr merge <n> --rebase --auto` (.claude/commands/pr-merge.md). The GitLab mirror push of step 6b (operator ruling 2026-10-03) is admitted as `git push gitlab refs/heads/main:refs/heads/main --follow-tags` (or `main:main`), nothing forced, from the console checkout, where `gitlab` is the console mirror and local `main` is exactly `origin/main`. The ONE admitted direct push to GitHub (operator ruling 2026-10-02) is the fast-forward fallback for a PR GitHub cannot rebase: `git push origin origin/<live MMDD-N branch>:main` (or `<branch>:main`, or `<sha>:main`), one refspec, no force/lease/`+`/delete/tags, from the console checkout on that branch, where the commit is the branch's pushed tip AND the open PR's head, `origin/main` is its ancestor, CI Complete is SUCCESS on it (read through .ci/scripts/ci/ci-trace.py), and the PR body names its plan (`Plan: agent/plans/PLAN-<slug>.md`; several under `turbo: on` in agent/plans/QUEUE.md at that commit) with every box ticked, or carries an `Operational-Reason:` line."
)

EDGE_CASES = [
    ("the incident's own shape", "git push origin HEAD:main"),
    ("a bare destination name", "git push origin main"),
    ("an explicit source, destination main", "git push origin 0914-1:main"),
    ("the refs-qualified long form", "git push origin refs/heads/main"),
    ("the empty-source delete form", "git push origin :main"),
    ("the flagged delete form", "git push origin --delete main"),
    ("--all pushes every branch, main included", "git push --all origin"),
    ("a bare push with no refspec at all", "git push"),
    ("a remote with no refspec", "git push origin"),
    ("HEAD with no colon aliases the current branch's own name", "git push origin HEAD"),
    ("a wrapper payload is still scanned", 'eval "git push origin main"'),
    # Controls: none of these are this guard's business.
    ("an ordinary push to a feature branch", "git push origin 0914-1"),
    ("a branch merely prefixed with main", "git push origin main-2"),
    ("a branch merely suffixed onto main", "git push origin not-main"),
    ("an explicit non-main destination overrides ambiguity", "git push origin feature-x"),
    ("a dry run publishes nothing", "git push --dry-run origin main"),
    ("tags only, no branch ref moves", "git push --tags origin"),
    ("prose about pushing is not a push", "echo 'never push straight to main'"),
    ("git pull is not git push", "git pull --rebase"),
    (
        "cd into a submodule pushing its own feature branch",
        "cd private/renet && git push origin 0914-1",
    ),
    # Global options before `push` (measured rc 0 on 2026-10-02), and a dry run beside a real push.
    ("-C before push, destination main", "git -C . push origin HEAD:main"),
    ("-c before push, destination main", "git -c a=b push origin main"),
    ("a dry run beside a real push", "git push --dry-run origin x; git push origin HEAD:main"),
    # M2: the fallback's shape refused before any gh read (no PR world here, so every spelling refuses).
    ("M2 the fallback shape with --force", "git push --force origin 0914-1:main"),
    ("M2 the fallback shape with two refspecs", "git push origin 0914-1:main 0914-1"),
    # The GitLab mirror push: no fixture here carries a `gitlab` remote, so every spelling refuses; the admitted worlds are in this guard's own suite.
    ("mirror the 6b spelling", "git push gitlab refs/heads/main:refs/heads/main --follow-tags"),
    ("mirror with --force", "git push --force gitlab main:main"),
    ("mirror a bare --mirror push", "git push --mirror gitlab"),
]


def _count(pattern, text, distinct=False):
    compiled = re.compile(pattern)
    records, _ = hookio._records(text)
    if distinct:
        # `shellscan.scan_target` appends a wrapper's payload as a record of its own, so `timeout 120 git push gitlab main:main` shows the same statement twice (measured 2026-10-03: the step-6b spelling inside pr-merge.md's own timeout wrapper was refused as "2 pushes"). The lexer's count of runs still catches two real pushes, identical or not.
        return len({m.group(0) for record in records for m in compiled.finditer(record)})
    return sum(len(list(compiled.finditer(record))) for record in records)


def _push_parts(run):
    _, _, args = commit_policy.git_split(run.argv)
    return [a for a in args if a.startswith("-")], [a for a in args if not a.startswith("-")]


def _names_main(run):
    _, positionals = _push_parts(run)
    for raw in positionals[1:]:
        src, colon, dst = raw.removeprefix("+").partition(":")
        if (dst if colon else src) in MAIN_NAMES:
            return True
    return False


def _dry_run_only(cmd, text_scan):
    """Every push the command runs is a dry run, and the lexer placed every push its text shows."""
    pushes = commit_policy.git_runs(cmd, "push")
    if not pushes or len(pushes) < _count(ANY_PUSH, text_scan):
        return False
    return all("--dry-run" in _push_parts(run)[0] or "-n" in _push_parts(run)[0] for run in pushes)


def _gh_pr(live):
    """(pr dict, "") for the live branch's PR, or (None, why not)."""
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", live, "--repo", GH_REPO, "--json", "number,state,headRefOid,body"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "`gh pr view %s` could not run (%s)" % (live, exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().split("\n")[0][:160]
        return None, "no PR for `%s` could be read (gh: %s)" % (live, err or proc.returncode)
    try:
        pr = json.loads(proc.stdout)
    except ValueError:
        return None, "`gh pr view %s` returned no JSON" % live
    if not isinstance(pr, dict):
        return None, "`gh pr view %s` returned no PR" % live
    missing = [f for f in PR_FIELDS if f not in pr or pr[f] is None]
    if missing:
        return None, "`gh pr view %s` answered without %s" % (
            live,
            ", ".join("`%s`" % f for f in missing),
        )
    return pr, ""


def _ci_green(live, number, sha):
    """ "" when ci-trace reads CI Complete SUCCESS on `sha` as the head of PR `number`, else why not."""
    # 65f2a27e.4: the tracer's path is fixed relative to this file; its absence is named, never searched for elsewhere.
    if not CI_TRACE.is_file():
        return "the CI tracer is missing at %s, so CI Complete cannot be read" % CI_TRACE
    try:
        proc = subprocess.run(
            [sys.executable, str(CI_TRACE), "--json", "--ref", live],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "ci-trace could not run (%s)" % exc
    try:
        trace = json.loads(proc.stdout)
    except ValueError:
        err = (proc.stderr or "").strip().split("\n")[-1][:160]
        return "ci-trace gave no verdict (rc %d: %s)" % (proc.returncode, err)
    if not isinstance(trace, dict) or trace.get("source") != "pr" or trace.get("pr") != number:
        return "ci-trace did not read the open PR #%s" % number
    if trace.get("head") != sha:
        return "ci-trace read head `%s`, not `%s`" % (str(trace.get("head"))[:12], sha[:12])
    # CI COMPLETE, NOT THE TRACER'S WHOLE VERDICT (operator ruling 2026-10-03, for the unattended merge cycle). `main`'s ruleset requires CI Complete alone, and it aggregates the PR's own CI. The whole verdict also counted contexts no workflow on the head defines: on #591 the base branch's retired review-status.yml kept posting a failing "Review Complete", which refused this push while CI Complete was SUCCESS (run 37089591716).
    # Exit 1 is a red whole verdict, which CI Complete then decides; exit 2 (no verdict) and 3 (head moved) are never a pass (review 2effee58.1).
    if proc.returncode not in (0, 1):
        return "ci-trace gave no verdict on `%s` (rc %d)" % (sha[:12], proc.returncode)
    if trace.get("ci_complete") != "success":
        return "CI Complete on `%s` is %s, not success" % (sha[:12], trace.get("ci_complete"))
    return ""


def mirror_refusal(ev, run, flags, positionals):
    """ "" when this push is the GitLab mirror push of step 6b (conditions f-h of the header), else why not."""
    for flag in flags:
        if flag not in MIRROR_FLAGS:
            return "`%s` is not part of the mirror push (one plain refspec, nothing forced)" % flag
    if len(positionals) != 2:
        return "the mirror push names `%s` and exactly one refspec" % githooks.MIRROR_REMOTE
    src, colon, dst = positionals[1].partition(":")
    if not colon or src not in MAIN_NAMES or dst not in MAIN_NAMES:
        return "the refspec `%s` is not `refs/heads/main:refs/heads/main`" % positionals[1]
    root = ev.project_dir
    repo = commit_policy.run_repo(run, ev.field("cwd") or root)
    top = commit_policy.toplevel(root)
    if not repo or not top or os.path.realpath(repo) != os.path.realpath(top):
        return "only the console checkout's own main has the mirror"
    urls: list[str] = []
    for extra in ([], ["--push"]):
        out = commit_policy.git(
            ["remote", "get-url", "--all", *extra, githooks.MIRROR_REMOTE], cwd=repo
        )
        if not out:
            return "the `%s` remote's URL cannot be read here" % githooks.MIRROR_REMOTE
        urls.extend(u for u in out.split("\n") if u)
    for url in urls:
        why = githooks.mirror_url_refusal(url)
        if why:
            return why
    sha = commit_policy.git(["rev-parse", "--verify", "-q", "refs/heads/main^{commit}"], cwd=repo)
    if not sha:
        return "local `main` does not resolve to a commit"
    return githooks.mirror_main_refusal(repo, sha)


def ff_fallback_refusal(ev, cmd, scan, text_scan):
    """ "" when this push to main is the admitted fast-forward fallback (box M2), else why not."""
    if hookio.grep_q(ALL_BRANCHES, scan):
        return "`--all` or `--mirror` pushes every branch"
    mains = [r for r in commit_policy.git_runs(cmd, "push") if _names_main(r)]
    shown = _count(DEST_MAIN, text_scan, distinct=True)
    if len(mains) != 1 or shown > 1:
        return "the fallback is ONE push to main, and this command shows %d" % max(
            len(mains), shown
        )
    run = mains[0]
    flags, positionals = _push_parts(run)
    if positionals[:1] == [githooks.MIRROR_REMOTE]:
        return mirror_refusal(ev, run, flags, positionals)
    for flag in flags:
        if flag not in FF_QUIET:
            return "`%s` is not part of the fallback (one plain refspec, nothing forced)" % flag
    if len(positionals) != 2:
        return "the fallback names `origin` and exactly one refspec"
    remote, refspec = positionals
    if remote != "origin":
        return "the remote is `%s`, not origin" % remote
    src, colon, dst = refspec.partition(":")
    if refspec.startswith("+") or not colon or not src or dst not in MAIN_NAMES:
        return "the refspec `%s` is not `<live branch or sha>:main`" % refspec
    root = ev.project_dir
    repo = commit_policy.run_repo(run, ev.field("cwd") or root)
    top = commit_policy.toplevel(root)
    if not repo or not top or os.path.realpath(repo) != os.path.realpath(top):
        return "only the console checkout's own main has the fallback"
    live = commit_policy.current_branch(repo)
    named = (live, "refs/heads/" + live, "origin/" + live, "refs/remotes/origin/" + live)
    if src not in named and not SHA.match(src):
        return "the source `%s` is not the live branch `%s`, its pushed tip or a sha" % (
            src,
            live or "(detached)",
        )
    sha = commit_policy.git(["rev-parse", "--verify", "-q", src + "^{commit}"], cwd=repo)
    if not sha:
        return "`%s` does not resolve to a commit" % src
    local = commit_policy.ff_fallback_refusal(repo, "origin", live, sha, "refs/remotes/origin/main")
    if local:
        return local
    pr, why = _gh_pr(live)
    if pr is None:
        return why
    if pr.get("state") != "OPEN":
        return "PR #%s for `%s` is %s, not open" % (pr.get("number"), live, pr.get("state"))
    if pr.get("headRefOid") != sha:
        return "`%s` is not the head of PR #%s (`%s`)" % (
            sha[:12],
            pr.get("number"),
            str(pr.get("headRefOid"))[:12],
        )
    plan = plan_gate.plan_merge_refusal(repo, pr.get("body"), rev=sha)
    if plan:
        return "PR #%s fails the plan gate: %s" % (pr.get("number"), plan)
    return _ci_green(live, pr.get("number"), sha)


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW

    text_scan = scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not hookio.grep_q(GIT_PUSH_AT_CMD, scan):
        return hookio.ALLOW
    canon = commit_policy.push_texts(cmd)
    if canon:
        scan = scan + "\n" + canon

    if _dry_run_only(cmd, text_scan):
        return hookio.ALLOW

    if hookio.grep_q(DEST_MAIN, scan) or hookio.grep_q(ALL_BRANCHES, scan):
        reason = ff_fallback_refusal(ev, cmd, scan, text_scan)
        if reason == "":
            return hookio.ALLOW
        ev.warn(MESSAGE + "\n\nNot the fast-forward fallback because: " + reason + ".")
        return hookio.DENY

    if hookio.grep_q(TAGS_ONLY, scan):
        return hookio.ALLOW

    if not (hookio.grep_q(BARE_PUSH, scan) or hookio.grep_q(BARE_HEAD, scan)):
        return hookio.ALLOW

    # `cd "${CLAUDE_PROJECT_DIR:-.}"`, same convention as block_merge_with_unpushed.py, then
    # resolve any `-C <dir>` / `cd <dir>` hint the command itself carries (a chained dispatcher runs several guards in one interpreter, so this reads cwd rather than changing it).
    root = ev.project_dir
    target = shellscan.target_root(scan, root, verb="push")
    git_root = target if target != "" else root

    branch = hookio.git_out(["symbolic-ref", "--short", "-q", "HEAD"], cwd=git_root, want_rc=True)
    if branch is None or branch == "":
        return hookio.ALLOW
    if branch == "main":
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
