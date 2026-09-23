#!/usr/bin/env python3
"""block_unproven_bulk_transform: both directions, against a real git repo.

HERMETIC BY CONSTRUCTION, the same shape as `test-block_unverified_push.py`: every case runs against a scratch repo with its own tree, its own staged index and (for the range cases) its own commit history and upstream, so this never touches the real repo's index or history. Commit and push are exercised as the guard actually sees them: the commit case stages real files
against a real HEAD before the commit runs, and the range cases build real commits with a real `@{u}` so `_push_target`/`_range_commits` resolve against genuine git state rather than a mock.

TWIN = None ON THE GUARD ITSELF, so this file is the whole differential, exactly as `test-block_prose_style_commit.py` is for its sibling. `check-hook-integrity.sh` reads this file's existence as crediting both directions.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_unproven_bulk_transform"]

BULK = 20  # must match BULK_FILE_THRESHOLD's default


def run(command, cwd):
    # CLAUDE_PROJECT_DIR is pinned to the same value carried as `cwd`, which is the honest simulation of the real harness invariant block_blanket_git_add.py:110-111 documents: the harness resets the shell's directory after every call, so `ev.cwd` is the project directory on every invocation. Left unset, `root` inside the guard resolved from whatever ambient environment the test
    # runner happened to hold, which was inert only while no case named a different repo via `-C`/`cd`.
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = cwd
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode != 0, proc.stderr


def git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=check)


def scratch_repo():
    d = tempfile.mkdtemp()
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "p@example.invalid")
    git(d, "config", "user.name", "p")
    with open(os.path.join(d, "base.txt"), "w", encoding="utf-8") as fh:
        fh.write("x\n")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "base")
    return d


def stage_files(repo, n, prefix="f"):
    for i in range(n):
        with open(os.path.join(repo, "%s%d.py" % (prefix, i)), "w", encoding="utf-8") as fh:
            fh.write("x = %d\n" % i)
    git(repo, "add", "-A")


class Tally:
    """A counter object rather than module globals, matching the sibling harnesses' shape."""

    fails = 0
    blocked = 0


def case(name, command, cwd, want_blocked):
    got, err = run(command, cwd)
    Tally.blocked += got
    ok = got == want_blocked
    Tally.fails += not ok
    print(
        "%-70s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want_blocked else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[-3:])


# ---- COMMIT, direct staged-diff check --------------------------------------

repo = scratch_repo()
case("a small commit under threshold", 'git commit -m "fix: a small thing"', repo, False)

stage_files(repo, BULK)
case(
    "a bulk commit with NO proof in its message is blocked",
    'git commit -m "style: reflow the tree"',
    repo,
    True,
)
case(
    "the same staged files, proof quoted, is allowed",
    'git commit -m "style: reflow the tree\n\nshape-cluster diff: 0 files lost a shape"',
    repo,
    False,
)
case(
    "a bare file count is NOT proof",
    'git commit -m "style: reflow the tree, %d files changed"' % BULK,
    repo,
    True,
)
git(repo, "reset", "-q")  # unstage so the next case starts clean
for name in os.listdir(repo):
    if name.startswith("f") and name.endswith(".py"):
        os.remove(os.path.join(repo, name))

stage_files(repo, BULK - 1, prefix="g")
case(
    "one file under threshold is allowed with no proof",
    'git commit -m "fix: several files"',
    repo,
    False,
)
git(repo, "reset", "-q")

# ---- SCOPE: a pathspec commits ITS paths, not the index ---------------------
# Reproduced live 2026-09-23: a three-file `git commit -F <msg> -- <three paths>` in this checkout was refused citing 183 staged files, none of which that commit would have touched. The tree is shared, so the index routinely carries other sessions' work; judging a pathspec commit by it is a fact about the tree, not about the commit. Both directions, because the narrowing must
# not become a way past the guard: a pathspec naming BULK files is still bulk.
pathspec_repo = scratch_repo()
# TRACKED AND THEN MODIFIED, because that is what a pathspec commit can name: git refuses `commit -- <path>` for a path it does not know, so an untracked fixture would test a command nobody can run.
for i in range(3):
    with open(os.path.join(pathspec_repo, "own%d.py" % i), "w", encoding="utf-8") as fh:
        fh.write("y = %d\n" % i)
# CLEAN AND STAYS CLEAN, for the case this guard runs BEFORE the command that writes it.
# Reproduced live 2026-09-23: one bash command ran a ledger-writing verb and then committed that ledger by pathspec, and at hook time the path had no diff at all, so an empty narrowed set fell through to 174 staged files belonging to other sessions.
with open(os.path.join(pathspec_repo, "clean0.py"), "w", encoding="utf-8") as fh:
    fh.write("clean = True\n")
git(pathspec_repo, "add", "-A")
git(pathspec_repo, "commit", "-qm", "seed the three paths")
for i in range(3):
    with open(os.path.join(pathspec_repo, "own%d.py" % i), "w", encoding="utf-8") as fh:
        fh.write("y = %d  # edited\n" % i)
stage_files(pathspec_repo, BULK, prefix="idx")
case(
    "a three-path commit is judged on its three paths, not the loaded index",
    'git commit -m "fix: a small thing" -- own0.py own1.py own2.py',
    pathspec_repo,
    False,
)
case(
    "a pathspec naming BULK files is still bulk, and still needs proof",
    'git commit -m "style: reflow" -- %s' % " ".join("idx%d.py" % i for i in range(BULK)),
    pathspec_repo,
    True,
)
case(
    "a pathspec git cannot resolve falls back to the index rather than allowing",
    'git commit -m "style: reflow" -- ../outside-this-repo.py',
    pathspec_repo,
    True,
)
case(
    "a tracked pathspec with nothing pending YET is judged on itself, not the loaded index",
    'git commit -m "docs: record a row" -- clean0.py',
    pathspec_repo,
    False,
)
git(pathspec_repo, "reset", "-q")

# ---- SCOPE: a brand-new, never-staged path is still just its own path ------
# Reproduced live 2026-09-23: `diff HEAD --name-only -- <path>` reports NOTHING for a genuinely untracked path.
# That is not a HEAD-vs-cached nuance -- `diff` never reports untracked content at all, staged or not.
# A single new file, never staged, named in `git commit -m ... -- <that file>` made the empty `_pathspec_files` result fall through `paths and _pathspec_files(...)` into the full shared-index fallback (177 unrelated files that day).
# `git status --porcelain` sees the `??` entry `diff` cannot. Git itself still refuses to COMMIT an untracked pathspec, so this case checks only that the GUARD stops blaming a one-file attempt on an unrelated bulk index, not that the commit succeeds.
new_file_repo = scratch_repo()
stage_files(new_file_repo, BULK, prefix="idx")
# WRITTEN AFTER `stage_files`, DELIBERATELY: that helper's own `git add -A` would otherwise stage this file too, leaving it indistinguishable from the tracked case the earlier block already covers.
with open(os.path.join(new_file_repo, "brand_new.py"), "w", encoding="utf-8") as fh:
    fh.write("z = 1\n")
case(
    "one brand-new, never-staged path is judged on itself, not the loaded index",
    'git commit -m "feat: add brand_new.py" -- brand_new.py',
    new_file_repo,
    False,
)
git(new_file_repo, "reset", "-q")

case("a plain command is not a target", "ls -la", repo, False)
case("gh pr view is not a write", "gh pr view 1", repo, False)
case(
    "a commit message MENTIONING the phrase, but few files, is fine either way",
    'git commit -m "docs: explain shape_cluster_diff.py"',
    repo,
    False,
)

# ---- SCOPE: a command reached via `-C`/`cd` into a repo that is not this checkout ----
# Reproduces the 2026-09-23 near-miss directly: CLAUDE_PROJECT_DIR points at a repo carrying an unproven bulk-sized staged change (standing in for the real console checkout's 255 staged files that day), and a `git -C <disposable fixture> commit` was refused citing THAT count -- the fixture's own tiny commit was never examined.
bulk_root = scratch_repo()
stage_files(bulk_root, BULK, prefix="w")

foreign = scratch_repo()
stage_files(foreign, 1, prefix="tiny")

case(
    "a bulk-staged CLAUDE_PROJECT_DIR does not leak into a `-C <foreign>` commit",
    'git -C %s commit -m "fix: a small thing"' % foreign,
    bulk_root,
    False,
)
case(
    "the same shape via a leading `cd <foreign> &&` is also not this guard's business",
    'cd %s && git commit -m "fix: a small thing"' % foreign,
    bulk_root,
    False,
)
case(
    "an unresolvable `-C` hint keeps guarding the ROOT (fail-safe, not fail-open)",
    'git -C /no/such/path-xyz commit -m "style: reflow the tree"',
    bulk_root,
    True,
)

# ---- PUSH, range check over real commit history ----------------------------

push_repo = scratch_repo()
remote = tempfile.mkdtemp()
git(remote, "init", "-q", "--bare")
git(push_repo, "remote", "add", "origin", remote)
git(push_repo, "push", "-q", "-u", "origin", "main")

stage_files(push_repo, BULK, prefix="p")
git(push_repo, "commit", "-qm", "style: bulk rewrite with no proof")
case(
    "a push carrying an unproven bulk commit is blocked",
    "git push",
    push_repo,
    True,
)

# A follow-up commit naming the unproven SHA and quoting proof clears it -- the module docstring's own promised remedy ("attach the proof in a follow-up commit naming the one being proven").
followup_repo = scratch_repo()
remote_f = tempfile.mkdtemp()
git(remote_f, "init", "-q", "--bare")
git(followup_repo, "remote", "add", "origin", remote_f)
git(followup_repo, "push", "-q", "-u", "origin", "main")
stage_files(followup_repo, BULK, prefix="r")
git(followup_repo, "commit", "-qm", "style: bulk rewrite with no proof")
bulk_sha = git(followup_repo, "rev-parse", "HEAD").stdout.strip()[:10]
with open(os.path.join(followup_repo, "tiny.txt"), "w", encoding="utf-8") as fh:
    fh.write("x\n")
git(followup_repo, "add", "-A")
git(
    followup_repo,
    "commit",
    "-qm",
    "docs: sampled and read %s by hand, no structural loss" % bulk_sha,
)
case(
    "a follow-up commit naming the unproven SHA with proof clears it",
    "git push",
    followup_repo,
    False,
)

# The same shape, but the follow-up NEVER NAMES the SHA -- proof text alone must not clear an unrelated commit, or this guard would accept any later commit that merely mentions the phrase.
unnamed_repo = scratch_repo()
remote_u = tempfile.mkdtemp()
git(remote_u, "init", "-q", "--bare")
git(unnamed_repo, "remote", "add", "origin", remote_u)
git(unnamed_repo, "push", "-q", "-u", "origin", "main")
stage_files(unnamed_repo, BULK, prefix="s")
git(unnamed_repo, "commit", "-qm", "style: bulk rewrite with no proof")
with open(os.path.join(unnamed_repo, "tiny.txt"), "w", encoding="utf-8") as fh:
    fh.write("x\n")
git(unnamed_repo, "add", "-A")
git(unnamed_repo, "commit", "-qm", "docs: sampled and read the diff by hand")
case(
    "a follow-up commit with proof text but no SHA reference does NOT clear it",
    "git push",
    unnamed_repo,
    True,
)

# A SHA listed in the repo's own bulk-transform-proof-baseline.json is grandfathered -- pre-existing debt at the moment the baseline landed, the same shrink-only shape every other baseline in this repo uses.
baseline_repo = scratch_repo()
remote_b = tempfile.mkdtemp()
git(remote_b, "init", "-q", "--bare")
git(baseline_repo, "remote", "add", "origin", remote_b)
git(baseline_repo, "push", "-q", "-u", "origin", "main")
stage_files(baseline_repo, BULK, prefix="t")
git(baseline_repo, "commit", "-qm", "style: bulk rewrite with no proof")
baseline_sha = git(baseline_repo, "rev-parse", "HEAD").stdout.strip()
config_dir = os.path.join(baseline_repo, ".ci", "config")
os.makedirs(config_dir, exist_ok=True)
with open(
    os.path.join(config_dir, "bulk-transform-proof-baseline.json"), "w", encoding="utf-8"
) as fh:
    json.dump({"grandfathered": [baseline_sha]}, fh)
case(
    "a SHA listed in bulk-transform-proof-baseline.json is grandfathered",
    "git push",
    baseline_repo,
    False,
)

# A DIFFERENT unproven bulk commit made AFTER the grandfathered one, in the same push, still blocks -- the baseline is shrink-only and must not become a blanket exemption for the whole range.
stage_files(baseline_repo, BULK, prefix="u")
git(baseline_repo, "commit", "-qm", "style: a second bulk rewrite with no proof")
case(
    "a NEW unproven bulk commit after the grandfathered one still blocks",
    "git push",
    baseline_repo,
    True,
)

# A second scratch repo for the ALLOWED push, so the first repo's now-diverged history (it was blocked, never actually pushed) does not contaminate this case.
push_repo2 = scratch_repo()
remote2 = tempfile.mkdtemp()
git(remote2, "init", "-q", "--bare")
git(push_repo2, "remote", "add", "origin", remote2)
git(push_repo2, "push", "-q", "-u", "origin", "main")
stage_files(push_repo2, BULK, prefix="q")
git(push_repo2, "commit", "-qm", "style: bulk rewrite\n\nast-equality proof: 0 mismatches")
case(
    "a push whose bulk commit already quotes proof is allowed",
    "git push",
    push_repo2,
    False,
)

# A push with no upstream at all: UNRESOLVABLE, so allowed rather than guessed.
detached = scratch_repo()
case(
    "a push with no upstream configured is allowed (unresolvable)",
    "git push origin main",
    detached,
    False,
)

# ---- GH PR CREATE, range check against the default base --------------------

pr_repo = scratch_repo()
git(pr_repo, "branch", "-m", "main")  # already main; documents the base this case relies on
stage_files(pr_repo, BULK, prefix="r")
git(pr_repo, "commit", "-qm", "style: bulk rewrite with no proof")
case(
    "gh pr create against an unresolvable base is allowed (no origin/main exists)",
    "gh pr create --title x --body y",
    pr_repo,
    False,
)

print()
TOTAL_CASES = 16
if Tally.blocked in (0, TOTAL_CASES):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every "
        "input, so this suite compared it against a constant." % (Tally.blocked, TOTAL_CASES),
        file=sys.stderr,
    )
    Tally.fails += 1
print(
    "%d case(s), %d blocked, %d allowed" % (TOTAL_CASES, Tally.blocked, TOTAL_CASES - Tally.blocked)
)
print("FAILURES: %d" % Tally.fails)
sys.exit(1 if Tally.fails else 0)
