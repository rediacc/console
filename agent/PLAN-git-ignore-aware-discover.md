# PLAN: make discover() git-tracked-only so a local machine's untracked files cannot contaminate a committed baseline

Status: done
Owner: d778be9d
Updated: 2026-09-16

## Tasks

- [x] Add gitx to the rediacc_ci import at .ci/rediacc_ci/quality/prose_style.py:81; add import tempfile.
- [x] Replace .ci/rediacc_ci/quality/prose_style.py:696-723 with tracked_files(), under_excluded_dir() and the git-driven discover() (section 4b).
- [x] Wrap the discover() call at .ci/rediacc_ci/quality/prose_style.py:962 in try/except RuleError -> log.error + return 1 (section 4c).
- [x] Same wrap at .ci/rediacc_ci/quality/prose_style.py:1164 in run_reflow (section 4d).
- [x] Delete ".claude/hooks/context/state" from exclude_dirs, .ci/config/prose-style-rules.json:85; optionally add the exclude_why paragraph (section 4e).
- [x] Add the six --selftest controls (section 6c).
- [x] Add _repo() and tests T1-T5, T7, T8 to .ci/rediacc_ci/tests/test_quality_prose_style.py; amend T6 (test_zero_files_is_a_failure) to git-init its fixture.
- [x] Prove the new tests can go red by temporarily restoring the os.walk body, then restore the fix (section 6d).
- [x] Run the verification block (section 7). Confirm 2499 -> 2495 file(s), 3542 baselined unchanged, baseline file untouched by git status.
- [x] Commit referencing worklist item #779ae9c1 and 944aa6210 -- this is the real fix that commit deferred.

## 1. Root cause

.ci/rediacc_ci/quality/prose_style.py:696-723 -- discover() enumerates the gate's
corpus with a raw os.walk and filters on two things only: globals_["exclude_dirs"]
and the file suffix. It has no git-awareness whatsoever.

That corpus is what --write-baseline freezes into
.ci/config/prose-style-baseline.json, a COMMITTED, shrink-only artifact. So every
file that happens to sit on the writing developer's disk -- gitignored, untracked,
a stale peer worktree, a .pytest_cache -- gets its findings baked into a file that
CI must later satisfy from a fresh checkout that does not contain those files. The
second half of the shrink-only guard (.ci/rediacc_ci/quality/prose_style.py:1081-1091, "N baselined
finding(s) no longer fire") then reds CI for a drain nobody can perform, attributed
to whoever pushed next.

This already happened. Commit 944aa6210 ("fix(ci): --write-baseline froze six
GITIGNORED local files into a committed baseline") records six
.claude/hooks/context/state/*-precompact-facts.md entries frozen from one machine;
that directory carries a .gitignore of * (verified:
.claude/hooks/context/state/.gitignore:1:*). Its commit body already names the real
fix and files it as worklist item (consolidated as #779ae9c1):

> THE CAUSE IS NOT THIS BASELINE, IT IS discover(). It walks with os.walk and
> knows nothing about git [...] the real fix is for discover() to skip
> git-ignored paths.

The workaround landed as one line -- .claude/hooks/context/state appended to
exclude_dirs at .ci/config/prose-style-rules.json:85. That closes one directory on
one machine. Any other gitignored or untracked directory, on any other machine,
reopens it.

This is the second time this class has bitten the repo. The first was 2026-09-13:
stale .claude/worktrees/ sibling checkouts reddened three gates, patched by
creating paths.walk_tree(). That helper prunes a hardcoded list only -- .ci/rediacc_ci/paths.py:237
PRUNED_DIR_NAMES = (".git", "node_modules", ".worktrees") and .ci/rediacc_ci/paths.py:244
PRUNED_DIR_PAIRS = ((".claude", "worktrees"),). It would not have caught
.claude/hooks/context/state. So switching discover() to paths.walk_tree() is not
the fix and must not be mistaken for one; only asking git is general.

## 2. The convention to follow (sibling evidence)

Four gates in this repo carry a --write-baseline mechanism. Three of them already
derive their corpus from git ls-files and refuse rather than fall back when git
cannot answer. prose_style.py is the only one that reinvented a filesystem walk.

| Gate | Corpus function | Spelling | Behaviour when git cannot answer |
|---|---|---|---|
| .ci/rediacc_ci/quality/plant_proofs.py:860-878 | tracked_files(root) | git -C ROOT ls-files -z | raises RefusalError on FileNotFoundError and on non-zero exit; scan() at :885-890 additionally refuses a ZERO-path corpus |
| .ci/rediacc_ci/quality/python_env_registry.py:332-352 | tracked_python(root) | git -C ROOT ls-files -z -- '*.py' | same two refusals |
| .ci/scripts/quality/check_language_policy.py:224-242 | tracked_files(root) | git ls-files -z -- ROOTS | raises CannotRun |
| .ci/rediacc_ci/quality/prose_style.py:696 | discover() | os.walk | -- (the defect) |

Two more data points on which spelling to write:

- .ci/rediacc_ci/gitx.py exists precisely to consolidate this. Its header counts
  23 git ls-files call sites measured across .ci, scripts and .claude, of which
  exactly one passes --cached --others --exclude-standard and exactly two guard for
  the deleted case (.ci/rediacc_ci/gitx.py:11-28, TRAP 1). gitx.ls_files() (.ci/rediacc_ci/gitx.py:412-460) takes
  existing= for the deleted case and returns a sorted, de-duplicated list.
- .ci/rediacc_ci/quality/plan_housekeeping.py is a quality gate in the same package
  that already uses the consolidated spelling throughout: gitx.ls_files(plan_glob,
  root=root) at :652, and gitx.git(["init", "-q", ctldir]) at :503 to build a
  control repo inside its own selftest.

So: the fix follows the three baseline gates' semantics (git-tracked corpus,
refuse when git cannot answer) using rediacc_ci.gitx's spelling, which is the
in-package consolidation of exactly those three raw call sites. gitx.is_work_tree()
is the documented way to ask the refusal question (.ci/rediacc_ci/gitx.py:207) -- verified
present, matching signature is_work_tree(root: os.PathLike[str] | str | None =
None) -> bool.

## 3. Tracked vs. explicitly-named target

The distinction already exists structurally and must be preserved, not invented:

- .ci/rediacc_ci/quality/prose_style.py:962 -- files = targets or discover(root, globals_)
- .ci/rediacc_ci/quality/prose_style.py:1164 -- same, in run_reflow

An explicit CLI target bypasses discover() entirely. That is the correct behaviour
and the change must not touch it: the caller named the file, and a brand-new file
being created for the first time is untracked by definition. Neither hook guard
(block_prose_style_edit.py, block_prose_style_commit.py) uses discover() -- they
lint bytes going to disk / message text directly, unaffected.

So the rule is one sentence: broad corpus discovery is git-tracked-only; an
explicitly-named target is scanned regardless.

### Tracked, not "not-ignored"

Plain git ls-files (index only) is used, not --others --exclude-standard.
.ci/rediacc_ci/quality/dead_python.py:240-249 adds --others because it is a whole-tree reachability scan
where a new module must not read as dead. This gate is the opposite case: it
writes a committed artifact that CI must satisfy from a checkout. An
untracked-but-not-ignored file (a fresh plan file never `git add`-ed) is the
same contamination class as a gitignored one. Tracked-only is the only rule under
which the baseline can never reference a path a fresh checkout lacks.

No git check-ignore anywhere: per-file it is ~2,500 subprocesses (tens of
seconds), --stdin is one call but answers only "ignored", missing the
untracked-not-ignored half. git ls-files answers both in one call. Measured on
this tree: gitx.is_work_tree() ~6ms, gitx.ls_files() returns 6,141 paths in
~20ms. Total ~26ms against an os.walk of ~30ms -- the change is free, and it
deletes the walk.

existing=True is passed (TRAP 1's second half). A file removed with rm rather
than git rm is still in the index; without it read_text raises, run_check
appends an UNCHECKED note, and .ci/rediacc_ci/quality/prose_style.py:1068-1074 turns that into rc = 1.
A developer with one stray deletion would red the gate.

## 4. The exact code change

### 4a. .ci/rediacc_ci/quality/prose_style.py:81 -- import

    from rediacc_ci import gitx, log, paths

(currently `from rediacc_ci import log, paths`)

### 4b. .ci/rediacc_ci/quality/prose_style.py:696-723 -- replace discover() and add two helpers

Replace the whole body of lines 696-723 with the following. RuleError is already
defined at .ci/rediacc_ci/quality/prose_style.py:165 and is already the module's refusal type (raised at
:174-221 and :743, caught in main() at :1284).

```python
def tracked_files(root):
    """Every path git TRACKS under `root`, repo-relative, present on disk.

    GIT, NOT A FILESYSTEM WALK, and the reason is the artifact this gate writes.
    `.ci/config/prose-style-baseline.json` is COMMITTED and SHRINK-ONLY, so
    every path in it must exist in a fresh checkout. A walk enumerates whatever
    the machine happens to hold -- a gitignored scratch directory, a file not
    yet added, a peer's stale worktree -- and `--write-baseline` then freezes
    rows CI is structurally incapable of satisfying. 944aa6210 is the receipt:
    six `.claude/hooks/context/state/*-precompact-facts.md` entries, ignored by
    a `.gitignore` of `*`, reded CI with "6 baselined finding(s) no longer fire".

    TRACKED, NOT MERELY NOT-IGNORED. `.ci/rediacc_ci/quality/dead_python.py:249` adds
    `--others --exclude-standard` and is right to: a reachability scan that
    could not see a brand-new module would call it dead. Here the claim is
    about what the repository SHIPS, and an untracked-but-unignored file is the
    same contamination as an ignored one -- it is on one disk and in no
    checkout.

    REFUSES RATHER THAN RETURNING NOTHING, which is what
    `.ci/rediacc_ci/quality/plant_proofs.py:867-877`, `.ci/rediacc_ci/quality/python_env_registry.py:345-355` and
    `.ci/scripts/quality/check_language_policy.py:235-241` all do at this exact call. An empty
    corpus and a clean tree are indistinguishable by exit code, and only one is
    good news.

    `existing=True` drops index entries whose file is gone -- gitx TRAP 1's
    second half. A file removed with `rm` rather than `git rm` would otherwise
    arrive here, fail to open, and land in the UNCHECKED list that `run_check`
    treats as a failure.
    """
    if not gitx.is_work_tree(root):
        msg = (
            "%s is not a git checkout, so the tracked corpus this gate is built on cannot be "
            "enumerated. Reporting zero files would report zero INPUTS, which reads exactly "
            "like a clean tree." % root
        )
        raise RuleError(msg)
    return gitx.ls_files(root=root, existing=True)


def under_excluded_dir(rel, skip):
    """Does any ANCESTOR directory of `rel` appear in `skip`?

    BOTH SPELLINGS, because `exclude_dirs` has always carried both and the walk
    this replaces honoured both: a BARE NAME prunes at every depth, a
    repo-relative PATH prunes once. Dropping the bare-name arm is not a
    tidy-up, it is a corpus change -- `build` alone admits the 18 tracked
    modules under `.ci/rediacc_ci/build/`, `private` admits
    `.ci/rediacc_ci/private/`, and measured on this tree the two arms together
    hold 1,057 tracked files out.

    A FILE is never matched, only its ancestors, so a tracked `docs/build.md`
    survives an entry of `build`.
    """
    parts = rel.split("/")
    for index in range(len(parts) - 1):
        if parts[index] in skip or "/".join(parts[: index + 1]) in skip:
            return True
    return False


def discover(root, globals_, subtrees=None):
    """Every TRACKED file the globals admit, sorted.

    EXPLICIT TARGETS DO NOT COME THROUGH HERE, and that is the distinction this
    function exists on one side of. `run_check` and `run_reflow` both spell it
    `targets or discover(...)`: a path named on the command line is scanned
    whatever git thinks of it, because the caller named it and a file being
    written for the first time is untracked by definition. Only the BROAD
    sweep -- the default `check`, and every `--write-baseline` -- is narrowed
    to what git tracks, because only the broad sweep writes the committed
    baseline.

    SORTED, NOT READDIR ORDER. `check_content_quality.py` records measuring
    the same thing on this tree: raw `find` is not lexicographic here, so an
    unsorted walk makes the output depend on filesystem state rather than on
    repository content, and two runs on two machines disagree for no reason a
    reader can act on. git's own order is not this order either, so the sort
    stays.
    """
    suffixes = {os.path.splitext(p)[1] for p in (globals_.get("include") or ())}
    skip = set(globals_.get("exclude_dirs") or ())
    prefixes = tuple(str(s).rstrip("/") + "/" for s in (subtrees or ()))
    out = []
    for path in tracked_files(root):
        rel = path.replace(os.sep, "/")
        if os.path.splitext(rel)[1] not in suffixes:
            continue
        if under_excluded_dir(rel, skip):
            continue
        if prefixes and not rel.startswith(prefixes):
            continue
        out.append(rel)
    return sorted(set(out))
```

Notes for the implementer:
- pathlib stays imported (used elsewhere); os stays (used for splitext/sep). The
  `root = pathlib.Path(root)` line is dropped -- gitx accepts str or PathLike.
- subtrees has no caller anywhere in the tree (verified: the only two hits for
  the identifier are the definition and its own use). The parameter stays,
  reimplemented as a path-prefix filter, rather than churning a signature.
- The new comments are themselves linted by this gate under scope comment: no
  second person, and no line over 384 characters.

### 4c. .ci/rediacc_ci/quality/prose_style.py:962 -- run_check, surface the refusal as an exit code

```python
    # TARGETS BYPASS DISCOVERY DELIBERATELY. A path named on the command line
    # is scanned whether or not git tracks it; only the broad sweep is
    # narrowed.
    try:
        files = targets or discover(root, globals_)
    except RuleError as exc:
        log.error(str(exc))
        return 1
```

### 4d. .ci/rediacc_ci/quality/prose_style.py:1164 -- run_reflow, the same three lines

```python
    try:
        files = targets or discover(root, globals_)
    except RuleError as exc:
        log.error(str(exc))
        return 1
    files = [f for f in files if f.endswith(".md")]
```

Catching inside run_check/run_reflow rather than in main() keeps the
return-code contract the pytest module drives them by.

### 4e. .ci/config/prose-style-rules.json:85 -- retire the workaround

Delete the ".claude/hooks/context/state" entry from exclude_dirs (and the
trailing comma on line 84). It was added by 944aa6210 only to paper over this
defect and is now subsumed: the directory is ignored by *, so git never lists
it.

Verified corpus-neutral: the only tracked path under that directory is
.claude/hooks/context/state/.gitignore, whose splitext extension is "" and
therefore matches no entry in include.

Every other exclude_dirs entry stays untouched -- several are load-bearing over
tracked files (private, packages/www, build) and the rest cost nothing.

Optionally append to exclude_why (.ci/config/prose-style-rules.json:114) one paragraph, in
the file's own voice:

```
"",
"exclude_dirs NOW ONLY DESCRIBES TRACKED DIRECTORIES THAT ARE OUT OF SCOPE. discover()",
"enumerates `git ls-files`, so a gitignored or never-added path is excluded structurally",
"and needs no entry here. `.claude/hooks/context/state` was one such entry, added after",
"944aa6210 froze six of its ignored files into this gate's committed baseline; it is gone",
"because the corpus itself is now git's answer rather than the walking machine's."
```

## 5. Measured effect on the real tree (verified before touching anything)

- Current gate output: 2499 file(s), no new findings (3542 baselined) -- green.
- Proposed discover() computed against the real tree yields 2,495 files, adding
  nothing and dropping exactly four:
  - .claude/hooks/stop/capfix-at/docs/agent-reference/TRAPS.md (untracked)
  - .claude/hooks/stop/capfix-over/docs/agent-reference/TRAPS.md (untracked)
  - .pytest_cache/README.md (gitignored)
  - agent/d778be9d/STATE.md (untracked -- this session's own scratch)
- The committed baseline currently contains zero paths git does not track (the
  944aa6210 drain), so no baseline rewrite is required by this change and no
  --write-baseline should be run as part of it.
- Independently re-verified during planning-review (session d778be9d,
  2026-09-16): reproducing the tracked+suffix+exclude_dirs filter directly
  against the live tree returns exactly 2495, matching this plan's claim
  precisely.
- Two independent formulations -- "walk intersected with tracked" and "filter
  tracked by suffix + exclude_dirs" -- were computed and are set-identical
  (2,495 = 2,495, symmetric difference empty). The pure-git form is the one
  specified above because it deletes os.walk from the gate outright, which is
  the only way this defect class cannot return here.

## 6. Test plan

All tests use the repo's plant-and-verify convention: every PLANT has a
MIRROR, so a discover() that returned nothing at all could not pass.

### 6a. Fixture helper -- .ci/rediacc_ci/tests/test_quality_prose_style.py

Add beside _tree (currently at :361). A real checkout needs only git init +
git add; no commit, therefore no author identity and no signing -- git
ls-files reads the INDEX. Isolate ambient config the way .ci/rediacc_ci/tests/test_gitx.py:36-44
does.

```python
GIT_ISOLATED = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def _repo(tmp_path, tracked, *, ignore=(), untracked=()):
    """A real checkout: `tracked` staged, `ignore` written to .gitignore,
    `untracked` planted AFTER the add so git never sees it.

    NO COMMIT. `git ls-files` reads the index, so `git add` is the whole
    requirement, and skipping the commit skips every way a developer's global
    identity or signing configuration could make this fixture
    machine-dependent.
    """
    root = _tree(tmp_path, tracked)
    if ignore:
        (root / ".gitignore").write_text("".join(p + "\n" for p in ignore), encoding="utf-8")
    env = {**os.environ, **GIT_ISOLATED}
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=root, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
    for rel, text in dict(untracked).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root
```

DIRTY = "Did you run the tests?\n" (R1's own bad example, <!-- style-ok -->
.ci/config/prose-style-rules.json:147) and CLEAN = "The tests were run.\n" as the two
payloads.

### 6b. Cases

T1, test_a_gitignored_file_is_not_discovered: plant a repo with kept.md
tracked and clean, a .gitignore of local/, and local/dirty.md untracked and
dirty. Today's os.walk returns both files, red. After the fix, discover()
returns only kept.md. The MIRROR is kept.md's presence, so a discover() that
returned nothing at all could not pass.

T2, test_an_untracked_file_is_not_discovered: same repo, but plant fresh.md
untracked and dirty with no .gitignore entry at all. Today fresh.md is
discovered, red. After the fix it is absent. This is the half the exclude_dirs
workaround could never cover.

T3, test_a_gitignored_finding_cannot_enter_the_baseline: T1's repo, but
kept.md also carries the dirty text; then run_check(root, GLOBALS, RULES, [],
write_baseline=True). Today the baseline's findings would contain
local/dirty.md, red. After the fix, rc is 0 and the baseline has a key for
kept.md (the MIRROR, proving the write was not vacuous) and no key for
local/dirty.md. This is the payload assertion: the incident, reproduced and
refused.

T4, test_an_explicitly_named_untracked_file_is_still_scanned: a repo with
kept.md tracked and clean, brand-new.md untracked and dirty. This passes today
and must keep passing: run_check(root, GLOBALS, RULES, ["brand-new.md"])
returns 1, and stderr carries "Do not add them to the baseline". The MIRROR in
the same test is that "brand-new.md" is absent from discover(root, GLOBALS) --
the tracked-vs-explicit distinction pinned in one place.

T5, test_discovery_outside_a_checkout_refuses_rather_than_reporting_nothing: a
plain tree with a.md, no git init at all. Today discover() returns ["a.md"].
After the fix, discover() raises RuleError, and run_check(root, GLOBALS,
RULES, []) returns 1 with "not a git checkout" in stderr.

T6, amending test_zero_files_is_a_failure (:370): change its fixture from
_tree(tmp_path, {}) to _repo(tmp_path, {}), a git-initialised empty repo. The
expectation is unchanged -- rc 1, "VACUOUS" -- but this keeps the empty-corpus
arm reachable now that a non-checkout refuses earlier with a different
message.

T7, test_the_real_corpus_is_a_subset_of_what_git_tracks: run against the real
tree, no plant needed. This fails today (4 untracked paths would slip in).
After the fix, set(discover(ROOT, GLOBALS)) is a subset of
set(gitx.ls_files(root=ROOT)), and its length exceeds 2000 as an anti-vacuity
floor. This is the control that would have caught the original incident on
the real tree.

T8, test_exclude_dirs_prunes_by_bare_name_and_by_path: a pure predicate test,
no repo needed. under_excluded_dir("a/node_modules/b.md", {"node_modules"})
is True; under_excluded_dir("packages/www/x.md", {"packages/www"}) is True.
The mirrors: under_excluded_dir("docs/build.md", {"build"}) is False because
build names a file's own basename component only when it is a directory
segment, not the file itself, and under_excluded_dir("node_modules",
{"node_modules"}) is False because a root-level name has no ancestor to
match. This pins the re-derived predicate against the 1,057-file regression.

T6 is the only existing test that needs touching: it is the only one reaching
discover() at all -- every other run_check/run_reflow test already passes
explicit targets, which is itself evidence the targets path is the common
one.

Add `import os` and `import subprocess` to the test module's imports
(currently json, pathlib, pytest, rediacc_ci.paths,
rediacc_ci.quality.prose_style), plus `from rediacc_ci import gitx` for T7.

### 6c. --selftest controls -- prose_style.py:selftest()

The gate's own controls must go red too, since check_prose_style.py's
docstring makes --selftest the gate's primary evidence. Add a section after
"# ---- the baseline's composition guard ----" (:1603). `import tempfile` at
the top; tempfile.TemporaryDirectory() inside a selftest is established
(.ci/rediacc_ci/quality/editorconfig.py:402, .ci/rediacc_ci/quality/ci_scans_tracked_paths.py:451), and
ci_scans_tracked_paths.build_control_tree (:313-328) is the precedent for git
init inside one. The _MINI globals (include: ["*.md"], exclude_dirs: []) are
exactly the right shape.

The section adds six controls: a tracked .md is discovered (the MIRROR); a
gitignored .md is NOT discovered (a plant); an untracked, unignored .md is NOT
discovered (a plant); discovery outside a checkout raises RuleError; a bare
name in exclude_dirs prunes at depth; and a FILE whose stem matches an
exclude_dirs entry still survives (the mirror for that last one).

Controls("prose-style", floor=40) at :1387 stays as-is; the suite already
runs 67.

### 6d. Proving the tests can fail

The repo's own standard, from check_prose_style.py's docstring: a green that
has never been shown to be able to go red is not evidence. Before committing,
the os.walk body of discover() is temporarily restored and T1, T2, T3, T7 and
the three new selftest plants are confirmed to go red; then the fix is
restored. The reverted state is never committed.

## 7. Verification

    python3 .ci/scripts/quality/check_prose_style.py --selftest
    python3 .ci/scripts/quality/check_prose_style.py check
    python3 -m pytest .ci/rediacc_ci/tests/test_quality_prose_style.py -q
    git status --porcelain .ci/config/prose-style-baseline.json

The check command should print 2495 file(s), no new findings (3542
baselined). The last command's output must be empty: this change rewrites no
baseline. A short script also loads the baseline and gitx.ls_files() and
asserts every baselined path is git-tracked; its exact form is in the
plan-review record rather than repeated here since it is a one-off sanity
check, not a permanent gate.

## 9. Rejected alternatives, with the reason

paths.walk_tree() instead of os.walk was rejected because it prunes a
hardcoded list only (.ci/rediacc_ci/paths.py:237,244); it would not have caught
.claude/hooks/context/state and will not catch the next one. It is the
2026-09-13 patch for a narrower symptom of this same class.

Per-file git check-ignore was rejected: roughly 2,500 subprocesses. Even
batched through --stdin it answers only "ignored", leaving the
untracked-but-unignored contamination class open.

gitx.ls_files(untracked=True), which adds --others --exclude-standard, was
rejected because it fixes the gitignored half and leaves the untracked half --
a never-added plan file would still enter a committed baseline. That
spelling is correct for .ci/rediacc_ci/quality/dead_python.py:240 and wrong for a baseline writer.

Falling back to a walk outside a checkout, the accommodation dead_python.py's
own fixture makes at :249-260, was rejected because all three sibling
baseline gates refuse instead, and because a silent fallback is a silent
return of the defect on any machine where git is missing or broken. Refusing
costs one amended test, T6.

Distinguishing "tracked but would be ignored if untracked" is not needed and
not implemented. A tracked file is in the repository by definition; that is
the whole question the baseline asks.

Keeping os.walk and intersecting with the tracked set is set-identical on the
real tree, measured, and would be a smaller diff -- but it leaves a raw
filesystem walk inside the gate, which is the exact construct this fix exists
to remove.
</content>
