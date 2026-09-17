"""Port of `.ci/scripts/test/gates/test-fetch-depth-safety.sh`.

No git operation may quietly reshape the repository a later step measures, and no fixture may be built in a shape that measures nothing.

WHAT THIS IS ABOUT, measured 2026-09-03 rather than reasoned about. `--depth` on a fetch is not a limit on what that fetch transfers; on a complete repository it WRITES A GRAFT and truncates the whole history. Against the real remote::

    $ git rev-list --count refs/remotes/pull/585/merge   # 2467
    $ git fetch --no-tags --depth=50 origin +refs/heads/main:refs/remotes/origin/main
    $ git rev-list --count refs/remotes/pull/585/merge   # 114, .git/shallow: 1 graft

The line that did it lived in `packages/www/scripts/lib/translation-freshness-git.js` and ran inside `check:i18n`. The job's `actions/checkout` had deliberately taken `fetch-depth: 0`. Four steps later `check:ci-plan-housekeeping` refused with "SHALLOW at a boundary that 58 plan(s) sit on", and the checkout -- which was innocent, and correct -- is what every reader went to look at.

THE DAMAGE IS ALWAYS SOMEBODY ELSE'S, which is what makes this class worth a gate: the script that truncates history is not the script that fails.

A FLAT TWIN, so the parity floor is its runtime `PASS:` count rather than a case set. The twin prints ten; this module records at least ten controls, one per `pass` the twin emits, in the twin's order.

WHERE THIS REIMPLEMENTS awk, grep AND sed, AND WHY THE ANSWERS AGREE. Two awk programs carry the whole sweep, and they are subtle enough to be worth spelling out.

  `real_fetch_depth` is::

      { line = $0; sub(/^[ \\t-]+/, "", line) }
      line ~ /^(#|\\/\\/|\\*)/ { next }
      /git +fetch[^|&;]*--depth/ { found = 1 }
      END { exit found ? 0 : 1 }

  Three things about it are easy to get wrong and are preserved exactly. First, the
  comment test runs against the STRIPPED copy while the match runs against `$0`, the
  ORIGINAL line -- so indentation is irrelevant to the match but decides nothing
  about the strip. Second, the strip class is `[ \\t-]`, space, tab and HYPHEN, which
  is what lets a YAML list item `  - git fetch ...` be seen as a comment when it
  begins `- # ...`. Third, it is a FILE-level predicate returning found/not-found,
  not a line list. `RealFetchDepth` below mirrors all three.

  `bare_hits` and the bare-offender loop are NOT the same program, and the twin
  writes them out separately for a reason worth keeping: the offender loop skips
  lines beginning `printf` or `echo` (a script WRITING a fixture, not running git)
  and the control's counter does not. Collapsing them into one helper would silently
  give the control a filter it was never written with, and the control's whole job is
  to be the simpler instrument. Both are here, both spelled out.

  `sed 's/^[[:space:]]*//'` on the offender text is `str.lstrip()` over the same
  ASCII whitespace class.

  `grep -qE 'is-shallow-repository|/shallow|isShallow'` is a FILE-level alternation,
  which is `any(token in text)`. The two forms cannot disagree: there is no anchor in
  the pattern, so ugrep's alternated-anchor defect (`grep -E` returning silent false
  zeros when `^` is alternated with a negated class) cannot apply, and the port would
  not inherit it in any case.

  `git ls-files '*.sh' ...` is driven as the real command. Enumerating the corpus in
  Python would be a second opinion about what "tracked" means.

WHY THIS FILE EXCLUDES ITSELF FROM THE SWEEP AS WELL AS THE TWIN. The twin excludes exactly one path, its own. This module contains the same planted string
(`git fetch --depth=1 origin main`) inside a fixture, so once it is tracked the sweep
would reach it. It would in fact be exempted anyway, because it asks `git rev-parse --is-shallow-repository` and therefore satisfies the file-level guard -- but an exemption that depends on a token appearing somewhere in the file is the accidental kind, and the twin's own comment records that a file-level exemption is what let a planted violation survive once. So the exclusion is
BY NAME, beside the twin's, where a reader can see it.

`node` IS REQUIRED and its absence is a loud failure carrying the fix, never a skip.

NO `xdist_group`. Every git fixture is built under pytest's own `tmp_path`; nothing is written inside the checkout, and the two reads of it (`git ls-files` and `git rev-parse --is-shallow-repository`) do not mutate anything.
"""

import os
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-fetch-depth-safety.sh"

ROOT = paths.repo_root()
MODULE = ROOT / "packages" / "www" / "scripts" / "lib" / "translation-freshness-git.js"

# A fixture with MORE than 50 commits, or --depth=50 truncates nothing and every case
# below passes for the wrong reason.
FIXTURE_COMMITS = 60

# Both paths the sweep must not judge. See the module docstring for why the second is named rather than left to the file-level guard.
SWEEP_EXCLUSIONS = (
    ".ci/scripts/test/gates/test-fetch-depth-safety.sh",
    ".ci/rediacc_ci/tests/gates/test_gate_fetch_depth_safety.py",
)

SWEEP_GLOBS = ("*.sh", "*.js", "*.cjs", "*.mjs", "*.ts", "*.py", "*.yml")

STRIP_RE = re.compile(r"^[ \t-]+")
COMMENT_RE = re.compile(r"^(#|//|\*)")
PRINTF_RE = re.compile(r"^(printf|echo)[ \t]")
FETCH_DEPTH_RE = re.compile(r"git +fetch[^|&;]*--depth")
BARE_INIT_RE = re.compile(r"git +[^|;]*init[^|;]*--bare")
PINNED_LONG_RE = re.compile(r"--initial-branch")
PINNED_SHORT_RE = re.compile(r" -b [A-Za-z]")
SHALLOW_AWARE = ("is-shallow-repository", "/shallow", "isShallow")


def git(gate) -> str:  # noqa: ARG001 - `gate` keeps every caller uniform
    return harness.require_tool("git", "install git")


def node(gate) -> str:  # noqa: ARG001 - `gate` keeps every caller uniform
    return harness.require_tool(
        "node",
        "install Node 22 (the version .devcontainer/toolchain.env pins), or run this "
        "under the devbox where it is already on PATH",
    )


def real_fetch_depth(path: pathlib.Path) -> bool:
    """The twin's `real_fetch_depth` awk, file-level, comments excluded.

    COMMENTS ARE NOT CODE, and the first run of the twin's sweep proved it: it named `claude-review-reusable.yml`, whose only match is PROSE describing what a third-party action does inside its own workspace. A gate whose first finding is a false positive teaches the reader to skim its output. Stated blind spot, carried over unchanged: a real command sitting inside a heredoc that
    opens with `#` is missed.
    """
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if COMMENT_RE.match(STRIP_RE.sub("", raw)):
            continue
        if FETCH_DEPTH_RE.search(raw):
            return True
    return False


def bare_offender_lines(path: pathlib.Path) -> list[str]:
    """The offender loop's awk: unpinned bare inits, comments and fixture WRITES skipped."""
    hits = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = STRIP_RE.sub("", raw)
        if COMMENT_RE.match(stripped):
            continue
        if PRINTF_RE.match(stripped):  # writing a fixture, not running git
            continue
        if (
            BARE_INIT_RE.search(raw)
            and not PINNED_LONG_RE.search(raw)
            and not PINNED_SHORT_RE.search(raw)
        ):
            hits.append(raw.lstrip())
    return hits


def bare_hits(path: pathlib.Path) -> int:
    """The CONTROL's counter, deliberately WITHOUT the printf/echo filter.

    See the module docstring: the control is the simpler instrument on purpose, and handing it the offender loop's extra filter would quietly change what it proves.
    """
    count = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if COMMENT_RE.match(STRIP_RE.sub("", raw)):
            continue
        if (
            BARE_INIT_RE.search(raw)
            and not PINNED_LONG_RE.search(raw)
            and not PINNED_SHORT_RE.search(raw)
        ):
            count += 1
    return count


def shallow_aware(path: pathlib.Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    return any(token in text for token in SHALLOW_AWARE)


def is_shallow(gate, directory: pathlib.Path) -> bool:
    probe = harness.run([git(gate), "-C", str(directory), "rev-parse", "--is-shallow-repository"])
    return probe.out.strip() == "true"


def commit_count(gate, directory: pathlib.Path) -> int:
    probe = harness.run([git(gate), "-C", str(directory), "rev-list", "--count", "HEAD"])
    return int(probe.out.strip()) if probe.rc == 0 and probe.out.strip().isdigit() else 0


def make_fixture(gate, directory: pathlib.Path) -> pathlib.Path:
    """origin (bare) + work (60 commits) + clone, with the fixture asserting its own shape.

    BOTH PRECAUTIONS WERE PAID FOR on this gate's FIRST CI run (job 100707433574). The runner's `init.defaultBranch` is not this machine's: a bare `git init` there left origin's HEAD pointing at a nonexistent `master`, so `git clone` reported "you appear to have cloned an empty repository" and the whole battery ran against a 1-commit tree. One case then FAILED honestly and another
    PASSED VACUOUSLY, which is the worse of the two outcomes.

    So the default branch is pinned in three places (both inits and an explicit `symbolic-ref`, because which of them a given git honours has changed across versions), and the commit count is a hard precondition rather than a hope.
    """
    binary = git(gate)
    origin = directory / "origin"
    work = directory / "work"
    clone = directory / "clone"
    origin.mkdir(parents=True, exist_ok=True)

    def run(*argv, cwd=None):
        result = harness.run([binary, *argv], cwd=cwd, timeout=600)
        if result.rc != 0:
            gate.log_fail("git %s failed building the fixture: %s" % (" ".join(argv), result.err))
        return result

    run("init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    run("init", "--quiet", "--initial-branch=main", str(work))
    run("-C", str(work), "config", "user.email", "t@example.com")
    run("-C", str(work), "config", "user.name", "t")
    for index in range(1, FIXTURE_COMMITS + 1):
        (work / "f.txt").write_text("%d\n" % index, encoding="utf-8")
        run("-C", str(work), "add", "f.txt")
        run("-C", str(work), "commit", "--quiet", "-m", "c%d" % index)
    run("-C", str(work), "remote", "add", "origin", str(origin))
    run("-C", str(work), "push", "--quiet", "origin", "main")
    run("-C", str(origin), "symbolic-ref", "HEAD", "refs/heads/main")
    run("clone", "--quiet", str(origin), str(clone))
    run("-C", str(clone), "config", "user.email", "t@example.com")
    run("-C", str(clone), "config", "user.name", "t")

    # PRECONDITION, not a case: a fixture shallower than the --depth this gate tests cannot demonstrate anything, and a broken one must never pass.
    count = commit_count(gate, clone)
    if count < FIXTURE_COMMITS:
        gate.log_fail(
            "FIXTURE BROKEN: %s holds %d commit(s), expected %d -- every verdict below "
            "would be vacuous; check the clone's default branch" % (clone, count, FIXTURE_COMMITS)
        )
    return clone


def detect_changed_files(gate, clone: pathlib.Path) -> harness.RunResult:
    """The REAL entry point. `detectChangedFiles` is what `validate:translation-freshness`
    calls, and `tryFetchBaseRef` is private to the module, so this drives the thing that actually runs in CI.

    `TRANSLATION_FRESHNESS_CHANGED_FILES` is UNSET rather than left inherited: the module short-circuits on it, and inheriting a value from an outer run would make the fetch this whole file is about never happen.
    """
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "TRANSLATION_FRESHNESS_CHANGED_FILES"
    }
    return harness.run(
        [
            node(gate),
            "--input-type=module",
            "-e",
            "import { detectChangedFiles } from '%s';\n"
            "detectChangedFiles('%s', 'main');" % (MODULE, clone),
        ],
        env=environment,
        env_replace=True,
        timeout=600,
    )


def test_the_pre_fix_command_truncates_a_full_clone(gate, tmp_path):
    # CONTROL: the fixture must be able to SHOW the defect. Without this every case below is a check that cannot fail.
    clone = make_fixture(gate, tmp_path / "plant")
    before = commit_count(gate, clone)
    harness.run(
        [
            git(gate),
            "-C",
            str(clone),
            "fetch",
            "--no-tags",
            "--depth=50",
            "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        ],
        timeout=600,
    )
    after = commit_count(gate, clone)
    if not (is_shallow(gate, clone) and after < before):
        gate.log_fail(
            "CONTROL: the pre-fix command did NOT truncate the fixture (shallow=%s %d -> %d)"
            % (is_shallow(gate, clone), before, after)
        )
    gate.log_pass(
        "CONTROL: the pre-fix command truncates a full clone (%d -> %d commits)" % (before, after)
    )


def test_detect_changed_files_leaves_a_full_clone_full(gate, tmp_path):
    clone = make_fixture(gate, tmp_path / "real")
    binary = git(gate)
    harness.run([binary, "-C", str(clone), "checkout", "--quiet", "-b", "feature"])
    (clone / "g.txt").write_text("change\n", encoding="utf-8")
    harness.run([binary, "-C", str(clone), "add", "g.txt"])
    harness.run([binary, "-C", str(clone), "commit", "--quiet", "-m", "feature commit"])
    before = commit_count(gate, clone)
    if not MODULE.is_file():
        gate.log_fail("the module under test is missing: %s" % MODULE)
    detect_changed_files(gate, clone)
    after = commit_count(gate, clone)
    if is_shallow(gate, clone):
        gate.log_fail(
            "detectChangedFiles SHALLOWIFIED a full clone (%d -> %d commits) -- the "
            "--depth must be conditional on the clone already being shallow" % (before, after)
        )
    gate.log_pass("detectChangedFiles leaves a full clone full (%d commits, no graft)" % after)


def test_an_already_shallow_clone_is_still_handled(gate, tmp_path):
    # CONTROL ON THE FIX: the depth was an optimisation for exactly this case, and removing it everywhere would be the other kind of wrong.
    directory = tmp_path / "shallow"
    make_fixture(gate, directory)
    binary = git(gate)
    clone = directory / "clone"
    harness.run(["rm", "-rf", str(clone)])
    harness.run(
        [
            binary,
            "clone",
            "--quiet",
            "--depth",
            "5",
            "--branch",
            "main",
            "file://%s" % (directory / "origin"),
            str(clone),
        ],
        timeout=600,
    )
    harness.run([binary, "-C", str(clone), "config", "user.email", "t@example.com"])
    harness.run([binary, "-C", str(clone), "config", "user.name", "t"])
    if not is_shallow(gate, clone):
        gate.log_fail("CONTROL: the shallow fixture is not shallow, so the case proves nothing")
    result = detect_changed_files(gate, clone)
    if result.rc != 0:
        gate.log_fail("an already-shallow clone now fails (exit %d)" % result.rc)
    gate.log_pass("CONTROL: an already-shallow clone is still handled (exit 0)")


def tracked(gate, *globs: str) -> list[str]:
    result = harness.run([git(gate), "-C", str(ROOT), "ls-files", *globs], timeout=600)
    if result.rc != 0:
        gate.log_fail("git ls-files failed, so the sweep has no corpus: %s" % result.err)
    return [line for line in result.out.splitlines() if line]


def test_every_git_fetch_depth_site_can_tell_whether_the_repo_is_shallow(gate):
    # THE CLASS, not the instance. A weak rule on purpose: it does not try to prove the guard is correctly placed, only that the author knew the question existed.
    offenders = []
    for relative in tracked(gate, *SWEEP_GLOBS):
        if relative in SWEEP_EXCLUSIONS:
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        if not real_fetch_depth(path):
            continue
        if shallow_aware(path):
            continue
        offenders.append("    %s" % relative)
    if offenders:
        gate.log_fail(
            "these hand --depth to git fetch with no notion of shallowness:\n%s"
            % "\n".join(offenders)
        )
    gate.log_pass("every git-fetch --depth site can tell whether the repo is already shallow")


def test_every_bare_fixture_repo_pins_its_default_branch(gate):
    # THE SECOND SHAPE OF THE SAME CLASS: a fixture whose HEAD points nowhere.
    #
    # PER LINE, not per file, and the first draft of the twin's rule got it wrong. A file-level "does it mention a pin anywhere" test exempted the whole file as soon as ONE bare init was pinned, so the mutant that stripped the pin from the gate itself still passed, because a `symbolic-ref HEAD` further down satisfied the grep. A rule whose own planted violation survives is not a
    # rule.
    offenders = []
    for relative in tracked(gate, "*.sh"):
        if relative in SWEEP_EXCLUSIONS:
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        offenders.extend("    %s: %s" % (relative, hit) for hit in bare_offender_lines(path))
    if offenders:
        gate.log_fail(
            "these create a BARE fixture repo without pinning its default branch:\n%s\n"
            "        A clone of it comes back EMPTY on a runner whose init.defaultBranch "
            "differs, and the battery then passes against nothing." % "\n".join(offenders)
        )
    gate.log_pass("every bare fixture repo pins its default branch")


def test_the_sweep_enumerated_a_real_corpus(gate):
    # CONTROL ON THAT SWEEP: it must be looking at a real corpus. A scan over an empty file list passes silently forever.
    scanned = len(tracked(gate, *SWEEP_GLOBS))
    if scanned < 500:
        gate.log_fail(
            "CONTROL: the sweep enumerated only %d file(s); the corpus was lost" % scanned
        )
    gate.log_pass("CONTROL: the sweep enumerated %d tracked file(s)" % scanned)


def test_a_planted_unguarded_depth_is_detected(gate, tmp_path):
    planted = tmp_path / "planted.sh"
    planted.write_text("git fetch --depth=1 origin main\n", encoding="utf-8")
    if not (real_fetch_depth(planted) and not shallow_aware(planted)):
        gate.log_fail("CONTROL: the sweep's own expressions do not flag a planted violation")
    gate.log_pass("CONTROL: a planted unguarded --depth is detected by the same expressions")


def test_a_commented_mention_is_not_counted_as_a_command(gate, tmp_path):
    # ... and the comment filter must not swallow real code: a commented mention is skipped, a command is not.
    prose = tmp_path / "prose.sh"
    prose.write_text(
        "# git fetch --depth=1 origin main -- prose about someone else\n", encoding="utf-8"
    )
    if real_fetch_depth(prose):
        gate.log_fail("CONTROL: a commented mention is still counted as a command")
    gate.log_pass("CONTROL: a commented mention is not counted as a command")


def test_an_unpinned_bare_init_is_caught_beside_a_symbolic_ref(gate, tmp_path):
    # The bad fixture deliberately carries a symbolic-ref line: that is what defeated the file-level draft of this rule, so the control plants it on purpose.
    bad = tmp_path / "bare-bad.sh"
    bad.write_text(
        'git init --bare "$d/origin.git"\ngit symbolic-ref HEAD refs/heads/main\n',
        encoding="utf-8",
    )
    got = bare_hits(bad)
    if got != 1:
        gate.log_fail(
            "CONTROL: the bare-fixture rule does not flag a planted violation (got %d "
            "hit(s), want 1)" % got
        )
    gate.log_pass("CONTROL: an unpinned bare init is caught even beside a symbolic-ref line")


def test_both_pinned_spellings_are_accepted(gate, tmp_path):
    good = tmp_path / "bare-ok.sh"
    good.write_text(
        'git init -q --bare -b main "$d/o.git"\n'
        'git init --quiet --bare --initial-branch=main "$d/p.git"\n',
        encoding="utf-8",
    )
    if bare_hits(good) != 0:
        gate.log_fail("CONTROL: a pinned bare init is flagged, so the rule is unusable")
    gate.log_pass("CONTROL: both pinned spellings are accepted")
    # Stated blind spot, carried over: the sweep enumerates THIS repository only. Checked by hand on 2026-09-03 -- account, renet, elite and homebrew-tap carry no `git fetch --depth` at all -- and a submodule script runs against the submodule's own git dir anyway, so it cannot truncate the superproject.
    gate.log_info(
        "Blind spot: submodules are not swept (checked by hand 2026-09-03: none carry one)"
    )
