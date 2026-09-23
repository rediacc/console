"""block_unproven_bulk_transform: the proof obligation, at the three points a change leaves the tree.

WHY THIS EXISTS.
`wl_proofcheck.py` asks the stop judge whether a bulk mechanical transform proved it did not destroy structure it does not know about. That question rides an LLM call, which is right for a nuanced judgement and wrong for every commit -- a synchronous judge call on `git commit` would make every commit pay for a model round trip. This guard is the operator's ruling that the SAME
demand also lands here, on a cheap, deterministic, staged-scoped check: does a large enough change carry a quoted proof in its own message. It cannot judge WHETHER a transform is mechanical the way the LLM can and judges SCALE instead, which is the plan's own principle -- batch size scales with proof, not ambition -- applied literally: a diff above the threshold must show proof,
regardless of what produced it.

THREE SURFACES, ONE RULE. `git commit` checks the STAGED diff against the message being written. `git push` and `gh pr create` check every commit in the range about to leave the tree, because either one can carry a bulk commit this guard never saw at commit time -- an operator `!`-bypassed commit, a peer's commit merged in, or a commit made before this guard existed.

TWIN = None, the same sentinel and for the same reason as `block_prose_style_commit`/`block_prose_style_edit`: this is a fresh guard authored directly, with no bash original to port from and nothing to differential-test against. `test-block_unproven_bulk_transform.py` stands in for that differential, exactly as it does for its siblings.

WHAT COUNTS AS PROOF, kept identical to the phrases `wl_proofcheck.PROOF_PROMPT` asks the judge to look for: a shape-cluster diff, an AST-equality or AST-diff statement, a byte-identity claim, or an explicit statement that files were sampled and read. A bare file count or diff stat does NOT count -- "884 files changed" is exactly the assertion that shipped alongside a real incident
this rule exists for.

THE THRESHOLD IS A SCALE PROXY, NOT A MECHANISM DETECTOR. This guard cannot tell a hand-written 25-file fix from a script applied to 25 files; it does not try to. Above the threshold, EITHER shape must show proof, because the plan's own principle is that scale itself is the risk this proof obligation answers to.

FAILS OPEN ON AN UNRESOLVABLE RANGE, on the same reasoning `messages()`'s `-F <unreadable path>` arm already uses: a range this guard cannot compute is UNEXAMINED, not a finding. A branch with no upstream, or a push whose target this guard cannot resolve, is allowed rather than guessed at.
"""

import os
import re
import subprocess

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import block_prose_style_commit as PSC
from rediacc_hooks.guards import block_unverified_push as PUSH

CHAIN = "pre-bash"
TWIN = None
# Re-keyed from 41 to 42 on 2026-09-22 by the insertion of block_push_to_protected_branch.py at 39.
ORDER = 42

# The one branch the differential must be able to see: a commit at bulk scale whose own message quotes no proof. Planting `if False:` there lets every such commit through, which is the whole failure this guard exists to refuse.
DEFECT = (
    "if len(files) >= BULK_FILE_THRESHOLD and not _proof_shown(_commit_message_text(cmd, cwd)):",
    "if False:",
)

# Measured nowhere yet, chosen rather than derived: 20 files is comfortably above an ordinary multi-file hand fix (this session's own hand-written fixes touched 1-8 files) and comfortably below the smallest bulk transform this branch actually produced (884, then 221, then 6). A threshold this far from both boundaries costs false positives only if a future hand-written fix genuinely
# spans 20+ files, which is itself worth a moment's proof.
BULK_FILE_THRESHOLD = int(os.environ.get("WORKLIST_BULK_FILE_THRESHOLD", "20"))

# A push or PR range check walks every commit in the range; this is the ceiling on how many are inspected before the guard gives up and allows rather than spending unbounded subprocess time on a rebase or a stacked branch.
RANGE_COMMIT_CAP = 200

PROOF_PHRASE = re.compile(
    r"shape[-_ ]cluster[-_ ]diff|shape_cluster_diff\.py|ast[-_ ]equalit|ast[-_ ]diff"
    r"|byte[-_ ]identical|sampled\s+(?:\d+\s+)?files?|sampled\s+and\s+(?:diffed|read|compared)",
    re.IGNORECASE,
)

BLOCK_COMMIT = """BLOCKED: %d staged file(s) is a bulk transform's scale, and this commit's own
message carries no proof it did not destroy structure it does not know about.

A bare file count or diff stat does not count. Run
    .ci/scripts/quality/shape_cluster_diff.py --rev HEAD <path...>
(or the equivalent structural/AST proof for this kind of change) and quote its
real output in the commit message, or state explicitly which files were
sampled and read across both revisions.
"""

BLOCK_RANGE = """BLOCKED: %s carries %d commit(s) this proof obligation has not seen cleared,
including %s (%d files, no proof quoted in its own message).

Each commit whose own diff reaches the bulk threshold needs its proof quoted
in ITS OWN commit message before it reaches this point. Amend the commit (if
still local) or attach the proof in a follow-up commit naming the one being
proven, then retry.
"""


def _proof_shown(text):
    return bool(PROOF_PHRASE.search(text or ""))


def _commit_message_text(cmd, cwd):
    return "\n".join(body for _, body in PSC.messages(cmd, cwd))


def _staged_files(cwd):
    out = hookio.git_out(["diff", "--cached", "--name-only"], cwd=cwd)
    return [line for line in out.splitlines() if line.strip()]


def _commit_files(sha, cwd):
    out = hookio.git_out(["diff-tree", "--no-commit-id", "--name-only", "-r", sha], cwd=cwd)
    return [line for line in out.splitlines() if line.strip()]


def _commit_message(sha, cwd):
    return hookio.git_out(["log", "-1", "--format=%B", sha], cwd=cwd)


def _range_commits(base, head, cwd):
    """SHAs base..head, oldest excluded, or None when the range cannot be resolved.

    `want_rc=True` is what makes an unresolvable range (no such ref, no
    upstream) come back as None rather than as an empty string that would read as "nothing to check" -- the same distinction `git_out`'s own docstring names as the reason the two modes exist.
    """
    out = hookio.git_out(["rev-list", "%s..%s" % (base, head)], cwd=cwd, want_rc=True)
    if out is None:
        return None
    shas = [line for line in out.splitlines() if line.strip()]
    return shas[:RANGE_COMMIT_CAP]


def _first_unproven(shas, cwd):
    """The first (sha, file_count) over threshold with no proof, or None."""
    for sha in shas:
        files = _commit_files(sha, cwd)
        if len(files) < BULK_FILE_THRESHOLD:
            continue
        if _proof_shown(_commit_message(sha, cwd)):
            continue
        return sha, len(files)
    return None


def _push_target(scan, cwd):
    """(base_ref, head) for the range about to leave via `git push`, or None.

    Prefers the configured upstream (`@{u}`), which is what a plain `git push`
    actually compares against. A branch with none -- a first push, a detached checkout -- is UNRESOLVABLE, and this guard allows rather than guesses which remote branch a bare push would even create.
    """
    del scan  # the branch name on the command line is not trusted over the real upstream
    upstream = hookio.git_out(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=cwd, want_rc=True
    )
    if not upstream:
        return None
    return upstream, "HEAD"


def _pr_base(cmd, cwd):
    """The PR's base branch: `--base <ref>` if given, else this repo's `main`."""
    tokens = cmd.split()
    for index, token in enumerate(tokens):
        if token in ("--base", "-B") and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith("--base="):
            return token.split("=", 1)[1]
    remote = hookio.git_out(["rev-parse", "--verify", "origin/main"], cwd=cwd, want_rc=True)
    return "origin/main" if remote is not None else "main"


def run(ev):
    cmd = ev.field("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    root = ev.env("CLAUDE_PROJECT_DIR", "") or hookio.git_out(["rev-parse", "--show-toplevel"])

    # ANOTHER REPO'S STAGED COUNT IS NOT THIS GUARD'S BUSINESS. Same class of defect as block_untagged_commit / block_unverified_push / block_blanket_git_add (see shellscan.target_root's own docstring): reproduced live 2026-09-23, a writer's `git -C <scratchpad fixture> commit` (equally: a leading `cd <fixture> &&`) was refused citing 255 staged files, which was CONSOLE's own
    # count, never the fixture's. `root`/CLAUDE_PROJECT_DIR is only the right tree to judge when the command does not name a different one itself. `target_root` returns "" for an unresolvable hint, so a bogus `-C` path does NOT exempt a command: the guard falls through and keeps judging `root`.
    if shellscan.target_root(scan, root) != "":
        return hookio.ALLOW

    cwd = ev.field("cwd") or root

    if PSC.GIT_COMMIT.search(scan):
        files = _staged_files(cwd)
        if len(files) >= BULK_FILE_THRESHOLD and not _proof_shown(_commit_message_text(cmd, cwd)):
            ev.warn(BLOCK_COMMIT % len(files))
            return hookio.DENY
        return hookio.ALLOW

    if hookio.grep_q(PUSH.PUSH_AT_COMMAND_POS, scan):
        target = _push_target(scan, cwd)
        if target is None:
            return hookio.ALLOW
        base, head = target
        shas = _range_commits(base, head, cwd)
        if shas:
            hit = _first_unproven(shas, cwd)
            if hit:
                sha, count = hit
                ev.warn(BLOCK_RANGE % (base, len(shas), sha[:10], count))
                return hookio.DENY
        return hookio.ALLOW

    if shellscan.gh_pr_at_command_pos(scan, "create"):
        base = _pr_base(cmd, cwd)
        shas = _range_commits(base, "HEAD", cwd)
        if shas:
            hit = _first_unproven(shas, cwd)
            if hit:
                sha, count = hit
                ev.warn(BLOCK_RANGE % (base, len(shas), sha[:10], count))
                return hookio.DENY
        return hookio.ALLOW

    return hookio.ALLOW


EDGE_CASES = [
    ("a bulk commit with no proof quoted", 'git commit -m "reflow the tree"'),
    ("a small commit, well under threshold", 'git commit -m "fix: a small thing"'),
    ("a plain command is not a target", "ls -la"),
    ("gh pr view is not a write", "gh pr view 1"),
    ("git log is not git commit", 'git log --grep "shape_cluster_diff.py"'),
]


def _bulk_staged_world(target):
    """A scratch repo with a bulk-sized change already staged, so the commit branch has something to refuse."""
    target.mkdir(parents=True, exist_ok=True)
    quiet = {
        "capture_output": True,
        "env": {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": "/nonexistent",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    }

    def run_git(*args):
        subprocess.run(["git", "-C", str(target), *args], check=True, **quiet)

    run_git("init", "-q", "-b", "main")
    (target / "base.txt").write_text("x\n", encoding="utf-8")
    run_git("add", ".")
    run_git("commit", "-q", "-m", "base")
    for i in range(BULK_FILE_THRESHOLD + 2):
        (target / ("bulk-%02d.py" % i)).write_text("x = %d\n" % i, encoding="utf-8")
    run_git("add", ".")
    return target


FIXTURES = {"bulk-staged": _bulk_staged_world}

# CLAUDE_PROJECT_DIR is the guard's fallback working directory when the payload carries none, so pointing it at the fixture is what puts the staged files under the commit case.
ENVS = [("bulk-staged", {"CLAUDE_PROJECT_DIR": "{FIXTURE:bulk-staged}"}, {})]
