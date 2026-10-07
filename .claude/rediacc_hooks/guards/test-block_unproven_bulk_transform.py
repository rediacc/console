#!/usr/bin/env python3
"""block_unproven_bulk_transform: both directions, against a real git repo.

HERMETIC BY CONSTRUCTION, the same shape as `test-block_unverified_push.py`: every case runs against a scratch repo with its own tree, its own staged index and (for the range cases) its own commit history and upstream, so this never touches the real repo's index or history. Commit and push are exercised as the guard actually sees them: the commit case stages real files
against a real HEAD before the commit runs, and the range cases build real commits with a real `@{u}` so `_push_target`/`_range_commits` resolve against genuine git state rather than a mock.

OWN_SUITE = True ON THE GUARD ITSELF, so this file is the whole differential, exactly as `test-block_prose_style_commit.py` is for its sibling. `check-hook-integrity.sh` reads this file's existence as crediting both directions.
"""

import importlib.util
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


# `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those): a pid-stamped run directory, removed at exit and swept by the next run when this one was killed before `atexit` could fire, which is how /tmp hit its inode cap on 2026-09-24.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("bulkxform-test-")


def git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=check)


def scratch_dir():
    """A temp directory under this run's RUN_TMP, removed at interpreter exit or by the next run's sweep. Every repo and bare remote this suite makes goes through here: it builds a dozen git fixtures at module scope, and before this helper not one of them was deleted, which is the `.git base.txt r0.py` shape that filled the /tmp inode cap on 2026-09-24."""
    return tempfile.mkdtemp(dir=RUN_TMP)


def scratch_repo():
    d = scratch_dir()
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
    total = 0


def case(name, command, cwd, want_blocked):
    got, err = run(command, cwd)
    Tally.total += 1
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
# #64c3e990: only the heredoc feeding the commit's own stdin is its message, so proof quoted in a chained python heredoc proves nothing.
case(
    "proof in a python heredoc before an unproven -F - commit is blocked",
    "python3 - <<'EOF'\n# shape-cluster diff: 0 files lost a shape\nEOF\n"
    "git commit -F - <<'EOF'\nstyle: reflow the tree\nEOF",
    repo,
    True,
)
case(
    "CONTROL: proof in the -F - commit's own heredoc is allowed",
    "git commit -F - <<'EOF'\nstyle: reflow the tree\n\nshape-cluster diff: 0 files lost a shape\nEOF",
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
    "an unresolvable `-C` hint INSIDE the root keeps guarding the ROOT (fail-safe, not fail-open); one outside it is a foreign directory (#5810a9f3)",
    'git -C no/such/path-xyz commit -m "style: reflow the tree"',
    bulk_root,
    True,
)

# ---- PUSH, range check over real commit history ----------------------------

push_repo = scratch_repo()
remote = scratch_dir()
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
# The same branch, still carrying that unproven commit: a DELETE-ONLY push carries none of it, so there is no range to prove. Paired with the block above on the SAME repo, so the allow is the exemption and not an empty range.
case(
    "a delete-only push carries no commits and is allowed",
    "git push origin --delete stale-branch",
    push_repo,
    False,
)
case(
    "a delete chained with a real push is still blocked",
    "git push origin --delete stale-branch && git push",
    push_repo,
    True,
)

# A follow-up commit naming the unproven SHA and quoting proof clears it -- the module docstring's own promised remedy ("attach the proof in a follow-up commit naming the one being proven").
followup_repo = scratch_repo()
remote_f = scratch_dir()
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
remote_u = scratch_dir()
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


# ANY PREFIX of 7+ characters names the commit, not only the 10-character one: git's own `--short` form here is 9, and a follow-up spelling that form stayed refused (2026-09-26). The inverse keeps a hex word that is NOT a prefix of the bulk SHA from clearing it.
def followup_naming(prefix, token_of):
    repo = scratch_repo()
    remote = scratch_dir()
    git(remote, "init", "-q", "--bare")
    git(repo, "remote", "add", "origin", remote)
    git(repo, "push", "-q", "-u", "origin", "main")
    stage_files(repo, BULK, prefix=prefix)
    git(repo, "commit", "-qm", "style: bulk rewrite with no proof")
    full = git(repo, "rev-parse", "HEAD").stdout.strip()
    with open(os.path.join(repo, "tiny.txt"), "w", encoding="utf-8") as fh:
        fh.write("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "docs: sampled and read %s by hand" % token_of(full))
    return repo


case(
    "a follow-up naming the SHA by a 7-character prefix clears it",
    "git push",
    followup_naming("t", lambda full: full[:7]),
    False,
)
case(
    "a follow-up naming a hex word that is not a prefix of the SHA does NOT clear it",
    "git push",
    followup_naming("u", lambda full: ("0" if full[0] != "0" else "1") + full[1:9]),
    True,
)

# A SHA listed in the repo's own bulk-transform-proof-baseline.json is grandfathered -- pre-existing debt at the moment the baseline landed, the same shrink-only shape every other baseline in this repo uses.
baseline_repo = scratch_repo()
remote_b = scratch_dir()
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
remote2 = scratch_dir()
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

# A STALE LOCAL `main` IS NOT THE PR'S BASE (2026-10-04, private/renet). `--base main` names the REMOTE branch the PR targets. renet's local `main` sat 135 commits behind origin/main, so `main..HEAD` swept in an old, already-merged bulk commit and refused a one-commit PR. Shape: origin/main carries an unproven bulk commit, local `main` predates it, and the feature branch adds one small file on top of origin/main.
stale_repo = scratch_repo()
stale_remote = scratch_dir()
git(stale_remote, "init", "-q", "--bare")
git(stale_repo, "remote", "add", "origin", stale_remote)
git(stale_repo, "push", "-q", "-u", "origin", "main")
git(stale_repo, "checkout", "-q", "-b", "landed")
stage_files(stale_repo, BULK, prefix="m")
git(stale_repo, "commit", "-qm", "style: an old bulk rewrite, merged upstream long ago")
git(stale_repo, "push", "-q", "origin", "landed:main")
git(stale_repo, "fetch", "-q", "origin")
git(stale_repo, "checkout", "-q", "-b", "feature", "origin/main")
stage_files(stale_repo, 1, prefix="s")
git(stale_repo, "commit", "-qm", "fix: one small change")
case(
    "gh pr create --base main judges the range from origin/main, not a stale local main",
    "gh pr create --base main --title x --body y",
    stale_repo,
    False,
)

# ---- ONE RULE: the commit arm and the push arm agree on the same commit -------
# 3a5f3a188 (2026-09-26, 28 files, no proof) was ALLOWED at commit and REFUSED at push. Its command was `node scripts/generate-search-index.js ...; git commit -F <msg> -- docs/design/06-cli-reshape.md packages/www 2>&1 | tail -1`: the guard runs before the first clause, so the 14 search indexes the generator had not yet written counted as unchanged, 14 < 20.
# Each shape below drives BOTH arms through the dispatcher on one repo: the commit command as the guard sees it BEFORE it runs, then the same clauses really run, then `git push` over the commit they made. The two verdicts must match each other and the expected one.
LOCALES = ["ar", "de", "en", "es", "et", "fr", "it", "ja", "ko", "pt", "ru", "tr", "zh"]


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path) or repo, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def upstream_repo():
    repo = scratch_repo()
    bare = scratch_dir()
    git(bare, "init", "-q", "--bare")
    git(repo, "remote", "add", "origin", bare)
    return repo


def both_arms(name, seed, pre, command, really_run, want_blocked, message=None):
    """Commit-arm verdict before `command` runs, then the range arm after it ran, at `git push` and at `gh pr create`; all three must equal `want_blocked`.

    `command` and `really_run` may also use `%(list)s`, a scratch file `pre` can fill with paths.
    """
    repo = upstream_repo()
    seed(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    git(repo, "push", "-q", "-u", "origin", "main")
    scratch = scratch_dir()
    msg = os.path.join(scratch, "msg.txt")
    with open(msg, "w", encoding="utf-8") as fh:
        fh.write(message or "docs(cli): regenerate the reference\n\nEvidence: check exit 0.\n")
    pre(repo)
    fill = {"msg": msg, "list": os.path.join(scratch, "list.txt")}
    with open(fill["list"], "w", encoding="utf-8") as fh:
        fh.write(git(repo, "diff", "--name-only").stdout)
    at_commit, err = run(command % fill, repo)
    really_run(repo, msg)
    at_push, _ = run("git push", repo)
    at_pr, _ = run("gh pr create --draft --title t --body b", repo)
    Tally.total += 3
    Tally.blocked += at_commit + at_push + at_pr
    ok = at_commit == at_push == at_pr == want_blocked
    Tally.fails += 3 * (not ok)
    print(
        "%-70s want=%-9s commit=%-9s push=%-9s pr=%-9s %s"
        % (
            name,
            "BLOCKED" if want_blocked else "allowed",
            "BLOCKED" if at_commit else "allowed",
            "BLOCKED" if at_push else "allowed",
            "BLOCKED" if at_pr else "allowed",
            "ok" if ok else "*** FAIL *** (the arms disagree or all are wrong)",
        )
    )
    if not ok and err:
        print("    commit stderr: %s" % err.strip().splitlines()[-3:])


def seed_3a5f(repo):
    write(repo, "docs/design/06-cli-reshape.md", "# reshape\n")
    for loc in LOCALES:
        write(repo, "packages/www/src/content/docs/%s/cli-application.md" % loc, "# cli\n")
        write(repo, "packages/www/public/search-index-%s.json" % loc, "[]\n")
    write(repo, "packages/www/public/search-index.json", "[]\n")
    write(repo, "packages/www/scripts/generate-search-index.js", "// gen\n")


def pre_3a5f(repo):
    """What the tree held when the guard ran: the design doc and the 13 cli pages edited, the 14 indexes not yet regenerated."""
    write(repo, "docs/design/06-cli-reshape.md", "# reshape\nversions restore\n")
    for loc in LOCALES:
        write(repo, "packages/www/src/content/docs/%s/cli-application.md" % loc, "# cli\nv\n")


def run_3a5f(repo, msg):
    for loc in LOCALES:  # the generator clause
        write(repo, "packages/www/public/search-index-%s.json" % loc, "[1]\n")
    write(repo, "packages/www/public/search-index.json", "[1]\n")
    git(repo, "commit", "-q", "-F", msg, "--", "docs/design/06-cli-reshape.md", "packages/www")


both_arms(
    "3a5f3a188's shape: a generator clause, then 28 files by directory pathspec",
    seed_3a5f,
    pre_3a5f,
    "cd packages/www && node scripts/generate-search-index.js >/dev/null 2>&1; cd ../.. && "
    "git commit -F %(msg)s -- docs/design/06-cli-reshape.md packages/www 2>&1 | tail -1",
    run_3a5f,
    True,
)


def seed_many(repo):
    for i in range(BULK + 5):
        write(repo, "src/m%02d.py" % i, "x = %d\n" % i)


def pre_many(repo):
    for i in range(BULK + 5):
        write(repo, "src/m%02d.py" % i, "x = %d  # edited\n" % i)


both_arms(
    "control: 25 edited files, no earlier clause, no proof, refused on both",
    seed_many,
    pre_many,
    "git commit -F %(msg)s -- src",
    lambda repo, msg: git(repo, "commit", "-q", "-F", msg, "--", "src"),
    True,
)


def seed_few(repo):
    seed_many(repo)
    for i in range(3):
        write(repo, "small/s%d.md" % i, "s\n")


def pre_few(repo):
    write(repo, "small/s0.md", "s edited\n")


def run_few(repo, msg):
    write(repo, "small/s1.md", "s regenerated\n")
    git(repo, "commit", "-q", "-F", msg, "--", "small")


both_arms(
    "control: a generator clause, then a 3-file directory, allowed on both",
    seed_few,
    pre_few,
    "node gen.js > /dev/null; S=/tmp; cat > $S/notes.txt <<'EOF'\nx\nEOF\n"
    "git commit -F %(msg)s -- small",
    run_few,
    False,
)


def seed_renames(repo):
    for i in range(BULK // 2 + 2):
        write(repo, "old/r%02d.py" % i, "value = %d\n" % i)


def pre_renames(repo):
    git(repo, "mv", "old", "new")


# A RENAME COUNTS AS A DELETE PLUS AN ADD ON BOTH ARMS. 12 renames are 24 paths to `diff-tree`, which the push arm reads; the commit arm's porcelain `git diff` paired them into 12 and let the commit through.
both_arms(
    "12 staged renames are 24 paths at commit exactly as at push",
    seed_renames,
    pre_renames,
    "git commit -F %(msg)s -- old new",
    lambda repo, msg: git(repo, "commit", "-q", "-F", msg, "--", "old", "new"),
    True,
)

# THE PURE FUNCTIONS, on 3a5f3a188's own file list and message. Imported in a child with PYTHONPATH rather than a `sys.path` hop in this file (test_canonical_sys_path_hop.py freezes those).
MSG_3A5F = (
    "docs(cli): the reshape transcript and the www CLI reference list `config remote versions` "
    "and `restore`\n\nEvidence: check:ci-design-tree exit 0 (175 leaves, both directions); "
    "check:ci-i18n-www-cli-docs 0; check:ci-search-index 0.\n\nPR-TASK: e4eaf80b\n"
)
PURE = r"""
import json, sys
from rediacc_hooks.guards import block_unproven_bulk_transform as G
repo, stage, cmd, msg = sys.argv[1:5]
paths = ["docs/design/06-cli-reshape.md", "packages/www"]
if stage == "pre":
    pending = G._pathspec_files(repo, paths)
    out = {"pending": pending, "writers": G._earlier_writers(cmd, repo, paths),
           "ceiling": G._pathspec_ceiling(repo, paths, pending)}
else:
    sha = G.hookio.git_out(["rev-parse", "HEAD"], cwd=repo)
    out = {"committed": G._commit_files(sha, repo)}
for key, files in list(out.items()):
    if key != "writers":
        out[key + "_unproven"] = G._bulk_unproven(files, msg)
print(json.dumps(out))
"""


def pure(repo, stage, command):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pathlib.Path(__file__).resolve().parents[2])
    proc = subprocess.run(
        [sys.executable, "-c", PURE, repo, stage, command, MSG_3A5F],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        raise SystemExit("pure-function child failed: %s" % proc.stderr)
    return json.loads(proc.stdout)


pure_repo = upstream_repo()
seed_3a5f(pure_repo)
git(pure_repo, "add", "-A")
git(pure_repo, "commit", "-qm", "seed")
pre_3a5f(pure_repo)
CMD_3A5F = (
    "cd packages/www && node scripts/generate-search-index.js >/dev/null 2>&1; cd ../.. && "
    "git commit -F m -- docs/design/06-cli-reshape.md packages/www"
)
before = pure(pure_repo, "pre", CMD_3A5F)
msg_path = os.path.join(scratch_dir(), "m.txt")
with open(msg_path, "w", encoding="utf-8") as fh:
    fh.write(MSG_3A5F)
run_3a5f(pure_repo, msg_path)
after = pure(pure_repo, "post", CMD_3A5F)
checks = [
    (
        "the pending set before the generator is the 14 files 3a5f3a188's commit arm counted",
        len(before["pending"]) == 14,
    ),
    ("the commit the push arm reads is 28 files", len(after["committed"]) == 28),
    (
        "the generator clause is named as an earlier writer",
        before["writers"][:1] == ["node scripts/generate-search-index.js"],
    ),
    (
        "every committed file sits inside the commit arm's ceiling",
        set(after["committed"]) <= set(before["ceiling"]),
    ),
    (
        "the one rule refuses the ceiling and the committed set alike",
        before["ceiling_unproven"] and after["committed_unproven"],
    ),
    ("the pending set alone is the divergence: the rule allows it", not before["pending_unproven"]),
]
for label, good in checks:
    Tally.total += 1
    Tally.fails += not good
    print("%-70s %s" % ("pure: " + label, "ok" if good else "*** FAIL ***"))


# ---- AN INDEX COMMIT COMMITS WHAT ITS OWN `git add` STAGED ------------------
# Worklist #8333146d: with no pathspec the commit arm counted the index as it stood BEFORE the command, so `node gen.js && git add -A && git commit` over 25 regenerated files counted nothing staged and was refused only at push.
def seed_gen(repo):
    for i in range(BULK + 5):
        write(repo, "gen/g%02d.json" % i, "[%d]\n" % i)


def no_pre(repo):
    """Nothing pending before the command runs."""
    del repo


def run_gen_add_all(repo, msg):
    for i in range(BULK + 5):  # the generator clause
        write(repo, "gen/g%02d.json" % i, "[%d, 1]\n" % i)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-F", msg)


both_arms(
    "a generator, `git add -A`, then an index commit of 25 files: refused on both",
    seed_gen,
    no_pre,
    "node gen.js && git add -A && git commit -F %(msg)s",
    run_gen_add_all,
    True,
)


def pre_new_untracked(repo):
    for i in range(BULK + 5):
        write(repo, "fresh/n%02d.py" % i, "n = %d\n" % i)


def run_add_all(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-F", msg)


both_arms(
    "`git add -A` of 25 untracked files, then an index commit: refused on both",
    lambda repo: write(repo, "README.md", "r\n"),
    pre_new_untracked,
    "git add -A && git commit -F %(msg)s",
    run_add_all,
    True,
)


def run_add_three(repo, msg):
    git(repo, "add", "src/m00.py", "src/m01.py", "src/m02.py")
    git(repo, "commit", "-q", "-F", msg)


both_arms(
    "control: `git add` of 3 files beside 25 unstaged edits, allowed on both",
    seed_many,
    pre_many,
    "git add src/m00.py src/m01.py src/m02.py && git commit -F %(msg)s",
    run_add_three,
    False,
)


def run_add_update(repo, msg):
    git(repo, "add", "-u")
    git(repo, "commit", "-q", "-F", msg)


both_arms(
    "`git add -u` over 25 modified tracked files: refused on both",
    seed_many,
    pre_many,
    "git add -u && git commit -F %(msg)s",
    run_add_update,
    True,
)


def pre_three_and_untracked(repo):
    for i in range(3):
        write(repo, "src/m%02d.py" % i, "x = %d  # edited\n" % i)
    pre_new_untracked(repo)


both_arms(
    "control: `git add -u` stages 3 tracked edits, not 25 untracked files",
    seed_many,
    pre_three_and_untracked,
    "git add -u && git commit -F %(msg)s",
    run_add_update,
    False,
)


def pre_stage_many(repo):
    pre_many(repo)
    git(repo, "add", "-A")


both_arms(
    "control: 25 files ALREADY staged, no add clause, keeps its refusal",
    seed_many,
    pre_stage_many,
    "git commit -F %(msg)s",
    lambda repo, msg: git(repo, "commit", "-q", "-F", msg),
    True,
)


def seed_sub(repo):
    seed_many(repo)
    for i in range(2):
        write(repo, "sub/k%d.md" % i, "k\n")


def pre_sub(repo):
    pre_many(repo)
    for i in range(2):
        write(repo, "sub/k%d.md" % i, "k edited\n")


def run_sub(repo, msg):
    git(os.path.join(repo, "sub"), "add", ".")
    git(repo, "commit", "-q", "-F", msg)


both_arms(
    "control: `cd sub && git add .` stages sub's 2 files, not the 25 elsewhere",
    seed_sub,
    pre_sub,
    "cd sub && git add . && cd .. && git commit -F %(msg)s",
    run_sub,
    False,
)

both_arms(
    "`git commit -a` over 25 modified tracked files: refused on both",
    seed_many,
    pre_many,
    "git commit -a -F %(msg)s",
    lambda repo, msg: git(repo, "commit", "-q", "-a", "-F", msg),
    True,
)


def run_rm_dir(repo, msg):
    git(repo, "rm", "-r", "-q", "src")
    git(repo, "commit", "-q", "-F", msg)


both_arms(
    "`git rm -r src` of 25 tracked files, then an index commit: refused on both",
    seed_many,
    no_pre,
    "git rm -r -q src && git commit -F %(msg)s",
    run_rm_dir,
    True,
)

# ---- 69b1f2f145: ONE MESSAGE, ONE VERDICT, ON EVERY ARM (#c17c47c3) ---------
# The commit arm admitted `git commit -F msg -- $(cat list)` over 45 files and `gh pr create` refused the same commit. The proof rule was never the split: a literal pathspec with this message was refused at commit too. The `$(cat list)` pathspec reached the guard as the bare token `$`, and the commit arm fell back to the shared INDEX (3 unrelated staged paths), which a pathspec commit never commits.
# The message is 69b1f2f145's own, verbatim, so the case survives the object's loss.
MSG_69B1 = """\
chore(plans): lift the 2026-09-26 holds and run-alone markers that turbo cannot see past

With turbo on and writer_cap 10, plan_gate.next_turbo picked one plan out of the whole queue. Two temporary rulings from 2026-09-26 stood in the way:
- 30 plans read "Status: held -- ... held until CI is green".
- 40 plans read "Concurrency: exclusive -- ... every plan runs alone while the token budget is limited (for the next few days)".

The hold's own condition is met: main CI is green at 01d3583e1. The run-alone reason was a token budget, and the operator's 2026-10-04 ask is the opposite: as many plans in parallel as possible.
- Each held plan gets back the Status it named ("it was `<status>`"), with a note that the hold was lifted.
- Each run-alone marker becomes `Concurrency: parallel`, and Owns: decides overlaps.
- PLAN-gate-drop-receipt-verify's exclusive reason was an Owns overlap with PLAN-ci-quick-cpu-scheduling, which block_plan_concurrency already handles, so it is parallel too.
- Two plans keep a genuine exclusive reason: PLAN-program-state-in-repo and PLAN-ci-quick-cpu-scheduling.
- agent/INDEX.md, the QUEUE.md generated block and plan-boxes.json are regenerated.

Proof: a script rewrote only the two header shapes, matched by exact regex. `git diff -U0 -- agent/plans` shows no changed line other than `Status:` and `Concurrency:` lines (70 insertions, 70 deletions across 40 plan files), and every file was sampled in that diff.

Verification:
- npm run check:ci-plan-record, check:ci-plan-boxes, check:ci-plan-folders, check:ci-plan-citations -> rc=0
- plan_gate.next_turbo('.', [], 10, in_set=[turbo plan]) -> 8 plans, where it picked 1 before

PR-TASK: db1be6c2
"""
PROVEN_69B1 = MSG_69B1.replace(
    "and every file was sampled in that diff.",
    "and all 45 files were sampled and read across both revisions.",
)


def seed_plans(repo):
    for i in range(45):
        write(repo, "agent/plans/PLAN-%02d.md" % i, "Status: held\n")
    for i in range(3):
        write(repo, "other%d.txt" % i, "x\n")


def pre_plans(repo):
    """The 45 header edits, plus the shared index: 3 unrelated paths another session staged."""
    for i in range(45):
        write(repo, "agent/plans/PLAN-%02d.md" % i, "Status: draft\n")
    for i in range(3):
        write(repo, "other%d.txt" % i, "y\n")
    git(repo, "add", "other0.txt", "other1.txt", "other2.txt")


def pre_two_plans(repo):
    for i in range(2):
        write(repo, "agent/plans/PLAN-%02d.md" % i, "Status: draft\n")


def run_listed(repo, msg):
    listed = git(repo, "diff", "--name-only", "HEAD").stdout.split()
    git(repo, "commit", "-q", "-F", msg, "--", *[p for p in listed if p.startswith("agent/")])


both_arms(
    "69b1f2f145: `-- $(cat list)`, 45 files, its own message: refused on every arm",
    seed_plans,
    pre_plans,
    "git commit -q -F %(msg)s -- $(cat %(list)s) 2>&1 | tail -5; git log --oneline -1",
    run_listed,
    True,
    MSG_69B1,
)
both_arms(
    "control: the same message, a literal `-- agent/plans` pathspec: refused",
    seed_plans,
    pre_plans,
    "git commit -q -F %(msg)s -- agent/plans",
    run_listed,
    True,
    MSG_69B1,
)
both_arms(
    "control: `-- $(cat list)` with a named sample read across both revisions: allowed",
    seed_plans,
    pre_plans,
    "git commit -q -F %(msg)s -- $(cat %(list)s)",
    run_listed,
    False,
    PROVEN_69B1,
)
both_arms(
    "control: `-- $(cat list)` in a tree with 2 pending files: allowed",
    seed_plans,
    pre_two_plans,
    "git commit -q -F %(msg)s -- $(cat %(list)s)",
    run_listed,
    False,
    MSG_69B1,
)

# EVERY SHAPE WHOSE PATHSPEC ONLY THE SHELL CAN READ is judged at the tree's pending ceiling, never at the index. Each of these was admitted over a 3-path index with 45 pending files.
opaque_repo = scratch_repo()
seed_plans(opaque_repo)
git(opaque_repo, "add", "-A")
git(opaque_repo, "commit", "-qm", "seed")
pre_plans(opaque_repo)
for label, command in (
    ("backticks", "git commit -m 'chore: x' -- `cat list.txt`"),
    ("`$(git diff --name-only)`", "git commit -m 'chore: x' -- $(git diff --name-only)"),
    ("an unassigned `$FILES`", "git commit -m 'chore: x' -- $FILES"),
    ("`--pathspec-from-file=list.txt`", "git commit -m 'chore: x' --pathspec-from-file=list.txt"),
    ("`--pathspec-from-file list.txt`", "git commit -m 'chore: x' --pathspec-from-file list.txt"),
    ("`cat list | xargs git commit --`", "cat list.txt | xargs git commit -m 'chore: x' --"),
    ("`xargs -a list git commit`", "xargs -a list.txt git commit -m 'chore: x'"),
    (
        "a generator before `$(cat list)` is judged at the repository's ceiling",
        "node gen.js; git commit -m 'chore: x' -- $(cat list.txt)",
    ),
):
    case("opaque pathspec, %s: refused" % label, command, opaque_repo, True)
case(
    "control: the same tree's 3-path index commit is allowed",
    "git commit -m 'chore: x'",
    opaque_repo,
    False,
)
case(
    "control: a literal 1-file pathspec in the same tree is allowed",
    "git commit -m 'chore: x' -- agent/plans/PLAN-00.md",
    opaque_repo,
    False,
)

# UNREADABLE ARGUMENTS FAIL CLOSED to the repository's pending changes, never to "stages nothing".
unread_repo = scratch_repo()
for i in range(BULK + 5):
    write(unread_repo, "w/u%02d.py" % i, "u = %d\n" % i)
case(
    "`git add --pathspec-from-file=list` is judged at the repository's ceiling",
    'git add --pathspec-from-file=list && git commit -m "fix: a small thing"',
    unread_repo,
    True,
)
case(
    "`git add $UNSET_VAR` is judged at the repository's ceiling",
    'git add $UNSET_VAR && git commit -m "fix: a small thing"',
    unread_repo,
    True,
)
case(
    "`git add -n -A` stages nothing, so the empty index is judged",
    'git add -n -A && git commit -m "fix: a small thing"',
    unread_repo,
    False,
)
case(
    '`git commit -m -a` is the message "-a", not --all',
    "git commit -m -a",
    unread_repo,
    False,
)

# `2>&1` AFTER THE PATHSPEC IS A REDIRECTION, NOT A PATH. The tail used to capture `2`, which no repo knows, so a one-file commit of a path with nothing pending YET fell back to the loaded index.
fd_repo = scratch_repo()
write(fd_repo, "one.md", "a\n")
git(fd_repo, "add", "-A")
git(fd_repo, "commit", "-qm", "seed one.md")
stage_files(fd_repo, BULK, prefix="fd")
case(
    "`-- one.md 2>&1` is one path, not one path plus a `2` that falls back to the index",
    'git commit -m "docs: a row" -- one.md 2>&1 | tail -1',
    fd_repo,
    False,
)

print()
# COUNTED, NOT TYPED. This used to be the literal 16 while 26 cases ran, so the summary misreported the suite and the constant-answer check below compared against a number the suite had outgrown.
TOTAL_CASES = Tally.total
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
