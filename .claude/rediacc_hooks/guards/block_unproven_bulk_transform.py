"""block_unproven_bulk_transform: the proof obligation, at the three points a change leaves the tree.

WHY THIS EXISTS.
`wl_proofcheck.py` asks the stop judge whether a bulk mechanical transform proved it did not destroy structure it does not know about. That question rides an LLM call, which is right for a nuanced judgement and wrong for every commit -- a synchronous judge call on `git commit` would make every commit pay for a model round trip.
This guard is the operator's ruling that the SAME demand also lands here, on a cheap, deterministic, staged-scoped check: does a large enough change carry a quoted proof in its own message.
It cannot judge WHETHER a transform is mechanical the way the LLM can and judges SCALE instead, which is the plan's own principle -- batch size scales with proof, not ambition -- applied literally: a diff above the threshold must show proof, regardless of what produced it.

THREE SURFACES, ONE RULE. `git commit` checks the STAGED diff against the message being written. `git push` and `gh pr create` check every commit in the range about to leave the tree, because either one can carry a bulk commit this guard never saw at commit time -- an operator `!`-bypassed commit, a peer's commit merged in, or a commit made before this guard existed.

TWIN = None, the same sentinel and for the same reason as `block_prose_style_commit`/`block_prose_style_edit`: this is a fresh guard authored directly, with no bash original to port from and nothing to differential-test against. `test-block_unproven_bulk_transform.py` stands in for that differential, exactly as it does for its siblings.

WHAT COUNTS AS PROOF, kept identical to the phrases `wl_proofcheck.PROOF_PROMPT` asks the judge to look for: a shape-cluster diff, an AST-equality or AST-diff statement, a byte-identity claim, or an explicit statement that files were sampled and read.
A bare file count or diff stat does NOT count -- "884 files changed" is exactly the assertion that shipped alongside a real incident this rule exists for.

THE THRESHOLD IS A SCALE PROXY, NOT A MECHANISM DETECTOR. This guard cannot tell a hand-written 25-file fix from a script applied to 25 files; it does not try to. Above the threshold, EITHER shape must show proof, because the plan's own principle is that scale itself is the risk this proof obligation answers to.

FAILS OPEN ON AN UNRESOLVABLE RANGE, on the same reasoning `messages()`'s `-F <unreadable path>` arm already uses: a range this guard cannot compute is UNEXAMINED, not a finding. A branch with no upstream, or a push whose target this guard cannot resolve, is allowed rather than guessed at.
"""

import json
import os
import pathlib
import re
import subprocess

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import block_prose_style_commit as PSC
from rediacc_hooks.guards import block_unverified_push as PUSH

CHAIN = "pre-bash"
TWIN = None
# Re-keyed from 41 to 42 on 2026-09-22 by the insertion of block_push_to_protected_branch.py at 39.
ORDER = 41

# The one branch the differential must be able to see: a commit at bulk scale whose own message quotes no proof. Planting `if False:` there lets every such commit through, which is the whole failure this guard exists to refuse.
DEFECT = (
    "if len(files) >= BULK_FILE_THRESHOLD and not _proof_shown(_commit_message_text(cmd, cwd)):",
    "if False:",
)

# Measured nowhere yet, chosen rather than derived: 20 files is comfortably above an ordinary multi-file hand fix (this session's own hand-written fixes touched 1-8 files) and comfortably below the smallest bulk transform this branch actually produced (884, then 221, then 6).
# A threshold this far from both boundaries costs false positives only if a future hand-written fix genuinely spans 20+ files, which is itself worth a moment's proof.
BULK_FILE_THRESHOLD = int(os.environ.get("WORKLIST_BULK_FILE_THRESHOLD", "20"))

# A push or PR range check walks every commit in the range; this is the ceiling on how many are inspected before the guard gives up and allows rather than spending unbounded subprocess time on a rebase or a stacked branch.
RANGE_COMMIT_CAP = 200

# The `-- <path>...` tail `block_pathspecless_git_commit.py` requires on every commit here. Its own `DDASH_PATHSPEC` only has to PROVE one is present, so it stops at the first character of the first path; this one has to capture the whole list, and stops at a clause or redirection boundary so a `--` in one clause cannot claim the next clause's words.
PATHSPEC_TAIL = hookio.rx(r"(^|[{S}])--([{S}]+[^{S};&|<>()]+)+")

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


def _pathspec_files(cwd, paths):
    """What `git commit -- <paths>` will really commit, or [] when that cannot be resolved.

    A PATHSPEC COMMIT DOES NOT COMMIT THE INDEX. git's own wording: "git commit [--] <paths>... commits the contents of the files given on the command line", ignoring what is staged.
    In a tree several sessions share, the index routinely carries a hundred paths nobody in this command mentioned, so the staged count is a fact about the TREE rather than about the commit -- the same class of blindness the repo-context note in `run` records, one scope narrower.

    `HEAD`, not `--cached`, because the content committed comes from the WORKTREE: a path modified but never staged still lands in that commit, and `--cached` would not see it. `want_rc=True` keeps an unresolvable pathspec (a bogus path, a `--` belonging to some other clause) as None rather than as an empty list that would read as "this commit changes nothing".

    `git diff` NEVER REPORTS AN UNTRACKED FILE, staged or not -- that is not a `HEAD`-vs-`--cached` nuance, it is a property of `diff` itself, which only compares TRACKED content.
    Reproduced live 2026-09-23: a single brand-new file, `git add`ed then committed as `git commit -m ... -- <that file>`, made `diff HEAD --name-only -- <path>` print nothing (empty string, not None), so the caller's `paths and _pathspec_files(...)` was falsy and fell through to `_staged_files` -- the FULL shared index, 177 unrelated paths, on a one-file commit.
    `git status --porcelain -- <paths>` sees the file (`??`) where `diff` cannot, so it is unioned in below; the file's own new content is what would land in the commit either way.
    """
    out = hookio.git_out(["diff", "HEAD", "--name-only", "--", *paths], cwd=cwd, want_rc=True)
    if out is None:
        return []
    tracked = [line for line in out.splitlines() if line.strip()]

    status_out = hookio.git_out(["status", "--porcelain", "--", *paths], cwd=cwd, want_rc=True)
    untracked: list[str] = []
    if status_out is not None:
        untracked.extend(
            line[3:].strip() for line in status_out.splitlines() if line.startswith("??")
        )

    seen = set(tracked)
    for path in untracked:
        if path not in seen:
            seen.add(path)
            tracked.append(path)
    return tracked


def _pathspecs_resolve(cwd, paths):
    """Does every pathspec token name something this repository knows?

    THE TAIL WAS READ CORRECTLY IS NOT THE SAME CLAIM AS THE PATHS HAVE CHANGES, and `_pathspec_files` cannot tell them apart: it answers `[]` both for a `--` that belonged to some other clause and for a real path with nothing pending. The caller used to treat every `[]` as the first case and fall back to the whole shared index.
    Reproduced live 2026-09-23: one bash command ran `worklist.py --plan-investigate ... --write` and THEN `git commit -- agent/ledgers/plan-investigation.jsonl`. This guard runs BEFORE the command, so at that instant the ledger was clean, the narrowed set was empty, and a one-file commit was refused citing 174 staged files belonging to other sessions.

    `ls-files --error-unmatch` is the tracked answer and an on-disk probe is the untracked one, which together are exactly the paths a commit can name. A token neither knows -- a bogus path, a stray `--` -- still returns False here, so the fallback that stops a real bulk commit walking past is untouched.
    """
    for path in paths:
        if (
            hookio.git_out(["ls-files", "--error-unmatch", "--", path], cwd=cwd, want_rc=True)
            is not None
        ):
            continue
        try:
            if (pathlib.Path(cwd) / path).exists():
                continue
        except OSError:
            pass
        return False
    return True


def _commit_pathspecs(scan):
    """The `-- <path>...` tail of the command, as a list of tokens."""
    matches = hookio.grep_o(PATHSPEC_TAIL, scan)
    if not matches:
        return []
    return [word for word in matches[-1].split() if word != "--"]


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


def _grandfathered_shas(cwd):
    """{full-sha} named in .ci/config/bulk-transform-proof-baseline.json, or empty.

    SHRINK-ONLY, the same convention every other baseline in this repo already follows: pre-existing debt at the moment the baseline landed, never a general escape hatch for a NEW bulk commit.

    Missing file, unreadable JSON, or a wrong shape all read as empty -- a fixture repo with no such file must behave exactly as it did before this existed, and a corrupt baseline must fail toward MORE checking, not less.
    """
    path = pathlib.Path(cwd) / ".ci" / "config" / "bulk-transform-proof-baseline.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    shas = data.get("grandfathered")
    return set(shas) if isinstance(shas, list) else set()


def _proven_by_a_later_commit(sha, newer_messages):
    """Whether a commit NEWER than `sha` in the same range names it and shows proof.

    `newer_messages` is every message strictly closer to HEAD than `sha` -- the shape the module docstring promises ("attach the proof in a follow-up commit naming the one being proven").

    `_commit_message(sha, cwd)` alone, reading only the offending commit's own text, cannot see a follow-up; this is what makes that promise real.

    `sha[:10]` matches how this guard already abbreviates a SHA everywhere else it prints one (`BLOCK_RANGE`), so a follow-up commit only has to spell the same short form.
    """
    short = sha[:10]
    return any(short in msg and _proof_shown(msg) for msg in newer_messages)


def _first_unproven(shas, cwd):
    """The first (sha, file_count) over threshold with no proof anywhere in the range, or None.

    `shas` is newest-first (git rev-list's own order), so a commit's "later, in the same push/PR" proof sits at a LOWER index -- collected once, up front, so an N-commit range costs one pass rather than a quadratic re-scan.
    """
    grandfathered = _grandfathered_shas(cwd)
    messages = [_commit_message(sha, cwd) for sha in shas]
    for i, sha in enumerate(shas):
        if sha in grandfathered:
            continue
        files = _commit_files(sha, cwd)
        if len(files) < BULK_FILE_THRESHOLD:
            continue
        if _proof_shown(messages[i]):
            continue
        if _proven_by_a_later_commit(sha, messages[:i]):
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
    # THE LITERAL "HEAD" IS A SEPARATE FAILURE FROM THE EMPTY ONE, and emptiness alone does not catch it.
    # `rev-parse --abbrev-ref` answers with the string "HEAD" rather than failing when there is nothing symbolic to shorten, and this guard would then compare the range "HEAD..HEAD", which is EMPTY: every commit in the push would go unexamined and the push would be allowed, silently, in exactly the case the docstring above calls unresolvable.
    if not upstream or upstream == "HEAD":
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

    # ANOTHER REPO'S STAGED COUNT IS NOT THIS GUARD'S BUSINESS.
    # Same class of defect as block_untagged_commit / block_unverified_push / block_blanket_git_add (see shellscan.target_root's own docstring): reproduced live 2026-09-23, a writer's `git -C <scratchpad fixture> commit` (equally: a leading `cd <fixture> &&`) was refused citing 255 staged files, which was CONSOLE's own count, never the fixture's.
    # `root`/CLAUDE_PROJECT_DIR is only the right tree to judge when the command does not name a different one itself. `target_root` returns "" for an unresolvable hint, so a bogus `-C` path does NOT exempt a command: the guard falls through and keeps judging `root`.
    if shellscan.target_root(scan, root) != "":
        return hookio.ALLOW

    cwd = ev.field("cwd") or root

    if PSC.GIT_COMMIT.search(scan):
        # A PATHSPEC NARROWS THE COMMIT, SO IT NARROWS THIS COUNT. Reproduced live 2026-09-23: a three-file `git commit -F <msg> -- <three paths>` was refused citing 183 staged files, none of which that commit would have touched -- the index belonged to other sessions' work in the same tree, which is the normal state here and the reason `block_blanket_git_add.py` exists.
        # An EMPTY narrowed set falls back to the staged count ONLY when the tail did not resolve.
        # Guessing in the permissive direction is how a real bulk commit walks past a guard whose whole subject is scale, so a `--` belonging to some other clause still gets judged on the index. A pathspec naming paths this repository knows is a different answer: the commit really is that narrow, and it reads as empty only because this guard runs BEFORE the command that writes
        # those paths. See `_pathspecs_resolve`.
        paths = _commit_pathspecs(scan)
        files = _pathspec_files(cwd, paths) if paths else []
        if not files and not (paths and _pathspecs_resolve(cwd, paths)):
            files = _staged_files(cwd)
        if len(files) >= BULK_FILE_THRESHOLD and not _proof_shown(_commit_message_text(cmd, cwd)):
            ev.warn(BLOCK_COMMIT % len(files))
            return hookio.DENY
        return hookio.ALLOW

    # A DELETE-ONLY PUSH carries no commits, so there is no range to prove; block_unverified_push.every_push_deletes_only is the one definition both push guards read.
    if hookio.grep_q(PUSH.PUSH_AT_COMMAND_POS, scan) and not PUSH.every_push_deletes_only(scan):
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
