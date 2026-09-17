"""Port of `.ci/scripts/test/gates/test-gate-paths-exist.sh`.

Gate: every hardcoded `packages/<name>/...` and `private/<name>/...` path constant in our tooling must resolve to something that exists in the tree.

WHY THIS EXISTS. PR #513 deleted `packages/web`, `packages/desktop`, `packages/e2e` and the middleware tree. 22+ scripts kept pointing at them. The paths did not throw -- they silently produced empty globs, empty Sets and empty file lists, so the gates built on top of them printed a checkmark for months
while asserting nothing at all (`check-www-only-translations.ts` compared two
empty sets). A dead path constant is the cheapest possible signal that a gate has gone vacuous, and it is fully static.

WHAT IT CHECKS.
  Tier A (package roots): the `packages/<name>` / `private/<name>` prefix of every
    literal must exist. Near-zero false-positive rate; this is the tier that
    catches a deleted workspace.
  Tier B (full paths): the whole literal must exist, but only when it is
    unambiguously a checked-in source path -- it carries a known source extension,
    or it ends in `/`. Anything else is left to Tier A.

WHAT IT DELIBERATELY DOES NOT CATCH, precision over recall, because a noisy gate gets suppressed and a suppressed gate is the bug being fixed: paths assembled at runtime from variables, glob patterns, anything inside a line comment, build outputs and vendored trees, extensionless paths, and submodule interiors when the submodule is not checked out.

THE SUBJECT IS THE SCAN ITSELF, which makes this port unlike most of the family. There is no separate `check-*.sh` to shell out to: the twin IS the detector, so porting it means re-expressing the detector in Python rather than driving a subject through a seam. The consequence is that parity here is a claim about two independent implementations agreeing on the same tree, which is
why the plant proof matters more than usual and why the extraction rules below are transcribed clause by clause from the twin's awk program rather than paraphrased.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Every case walks the working tree (`scripts/`, `packages/www/scripts/`, `.ci/scripts/`) and two of them PLANT a file inside `.ci/scripts/` and remove it again. A battery step reading that directory mid-plant, or a second scanner seeing a fixture that vanishes under it, is the flake that would be blamed on this port -- and the twin
carries `mutex: ["tree:repo"]` in `gates.lock.json` for exactly that reason.
`REAL_TREE_TWIN = True` buys the serialisation, and it is honoured ONLY because
this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in
`test_twin_parity.py`, which refuses that combination.

THE SELF-SCANNING TRAP, and this file is squarely in it. The detector reports dead `packages/...` literals found in source files, and a port of it is a source file full of dead `packages/...` literals. The twin is invisible to itself
because `scan_targets` excludes `.ci/scripts/test/*`; this module lives outside
every scanned root, so it is invisible for a different and less deliberate reason -- one that a future scanner widening its roots would quietly remove. So the fixture literal is RENDERED through a `%s` template and never appears whole in this file's bytes (`%` is outside the `[A-Za-z0-9._+-]` class the extractor uses, so the template cannot be extracted as a path), and
`test_this_module_is_not_itself_a_finding` points the real detector at this directory and fails BY NAME if that ever stops being true. Batch 3's
`label-references` port paid for this rule; any port of a self-scanning subject
owes the same treatment.
"""

import contextlib
import os
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-gate-paths-exist.sh"

# Every case walks the real tree and two of them plant a file inside `.ci/scripts/`. See the module docstring.
REAL_TREE_TWIN = True

ROOT = paths.repo_root()

# Where the two control cases plant their synthetic scan targets.
#
# NOT `scripts/`, and not a temp dir either. The controls have to sit inside a directory the scan actually walks, or the detector never sees them and the control silently stops firing -- so a temp dir outside the repo is not an
# option. But `scripts/` is ALSO linted (`eslint packages scripts private/account`,
# and knip's project glob `scripts/**/*.ts`), and a file that appears and vanishes mid-run raced a concurrent `npm run check:lint` into `ENOENT`, exit 2. That was
# never a lint failure; it was this gate polluting a linted tree. `.ci/scripts`
# satisfies both halves, measured rather than assumed by the twin on 2026-07-31.
FIXTURE_DIR = ROOT / ".ci" / "scripts"

# The fixture filenames carry THIS PROCESS's pid, and that is a correctness fix rather than tidiness. They used to be fixed names in the twin, so two concurrent invocations planted the same two paths and each cleanup deleted the OTHER run's
# fixture; on 2026-08-05 that surfaced as a false "detector broken".
#
# The dotfile prefix is load-bearing (it is what keeps eslint, biome and knip off
# these files) and the `.ts` suffix is what the scan globs for, so the pid goes between them. FIXTURE_NAME_PREFIX is the shape both fixtures share ACROSS pids and across the two LANGUAGES: the twin's fixtures are visible to this scan and this port's are visible to the twin's, so both sides scope themselves with it rather than assuming they are alone in the tree.
FIXTURE_PID_SUFFIX = str(os.getpid())
FIXTURE_NAME_PREFIX = ".gate-paths-exist-"

# Rendered, never written whole. See the self-scanning paragraph in the docstring.
MISSING_WORKSPACE = "definitely-not-a-workspace"
FIXTURE_BODY = 'const p = "packages/%s/src/index.ts";\n' % MISSING_WORKSPACE
# `DELETED_IN_513` is spliced in for the same reason: written whole, the comment line below would be a live unresolvable literal in this file's own bytes.
DELETED_IN_513 = "web/src/App.tsx"
NOISE_BODY = (
    "const a = `packages/${name}/src/index.ts`;\n"
    'const b = "packages/*/dist/**/*.js";\n'
    "// packages/%s was deleted in #513\n" % DELETED_IN_513
)

# Directory prefixes that are generated, vendored, or gitignored. A literal whose path traverses one of these is skipped in Tier B.
EPHEMERAL_SEGMENTS = re.compile(
    r"/(dist|build|bin|out|coverage|node_modules|\.astro|\.backups|\.cache)(/|$)"
)

# Extensions that mark a literal as a checked-in source path worth Tier B.
SOURCE_EXTENSIONS = re.compile(
    r"\.(ts|tsx|js|jsx|cjs|mjs|json|jsonc|md|mdx|sh|go|ya?ml|astro|css|html|toml|txt|py)$"
)

# The three clauses of the twin's awk program, one regex each.
#
# `PATH_RE` is the awk `match(s, /(packages|private)\/[A-Za-z0-9._+-]+(\/[A-Za-z0-9._+-]+)*\/?/)`. POSIX awk matches leftmost-LONGEST and Python matches leftmost-greedy-with-
# backtracking; for this pattern the two coincide, because the alternation has no
# shared prefix and the character class excludes `/`, so there is nothing for backtracking to give back.
PATH_RE = re.compile(r"(?:packages|private)/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*/?")
COMMENT_RE = re.compile(r"^\s*(//|#|\*|/\*)")
QUOTE_SPLIT_RE = re.compile("[\"'`]")
# awk's `[]*?{}$[]` bracket expression: a leading `]` is literal, so the members
# are `]`, `*`, `?`, `{`, `}`, `$`, `[`.
METACHARACTERS = "]*?{}$["

# The scan must be WHOLE before an empty result means anything. Every assertion here reads an empty finding list as "no dead paths", so a scan that silently walked a fraction of the tree hands back a clean bill of health from an instrument that barely ran.
#
# THIS IS NOT HYPOTHETICAL. Inside a full 168-gate `npm run ci` on 2026-08-05 the twin finished in 90.6s against 210-231s whenever it was healthy, and its own
# planted-defect control came back EMPTY. The signal was never a co-running gate;
# it was DURATION, the walk terminating around 40% of the way through under the pressure a full fleet applies. The floor converts that silent truncation into a loud refusal.
SCAN_FLOOR = int(os.environ.get("GATE_PATHS_SCAN_FLOOR", "150"))


def scan_targets() -> list[str]:
    """The tooling files whose path constants we police, repo-relative.

    The three legs are the twin's three `find` invocations. `.ci/scripts/test/**` is excluded on purpose: those files name planted fixture paths that do not exist by design. `*.py` is in the list because 45 quality gates exist ONLY as `check_*.py` with no `.sh` twin left to cover them by accident.
    """
    found: list[str] = []

    def walk(rel_root: str, suffixes: tuple[str, ...], exclude_prefix: str | None = None) -> None:
        base = ROOT / rel_root
        if not base.is_dir():
            return
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "node_modules"]
            for name in filenames:
                if not name.endswith(suffixes):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
                if exclude_prefix and rel.startswith(exclude_prefix):
                    continue
                if (ROOT / rel).is_file():
                    found.append(rel)

    walk("scripts", (".ts", ".sh", ".py"))
    walk("packages/www/scripts", (".js",))
    walk(".ci/scripts", (".ts", ".sh", ".py"), exclude_prefix=".ci/scripts/test/")
    return found


def extract_literals(rel_path: str) -> list[tuple[str, int, str]]:
    """`(<file>, <line>, <path>)` for every quoted path literal in one file.

    A CLAUSE-BY-CLAUSE transcription of the twin's `EXTRACT_AWK`, in its order, because the order is what makes it correct: the Python docstring state machine runs BEFORE the comment skip, and the selftest cut runs before both.

    PYTHON NEEDS TWO SKIPS THAT BASH DOES NOT, and without them widening the scan to `*.py` is worse than not widening it. `.ci/scripts/test/**` is excluded wholesale by `scan_targets`, but a Python gate carries its selftest INSIDE the module, so that exclusion cannot be done by directory. Measured 2026-09-08 on the twin's first widened run, both findings were false: a path quoted
    in a DOCSTRING explaining a control, and a fixture in a selftest table whose whole point is that the path is NOT covered.

    Only text inside a quote pair is considered, which is what keeps prose out. Splitting each line on the three quote characters and dropping field 1 reproduces the twin's "a leading quote plus a run of non-quote characters" exactly: field N+1 is the run that followed the Nth quote.
    """
    try:
        text = (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        # A scan target can VANISH mid-run: a concurrent invocation of this same detector plants and removes fixtures inside the scanned tree. The twin's awk retries file by file for the same reason. An unreadable neighbour is not this gate's finding.
        return []
    is_py = rel_path.endswith(".py")
    out: list[tuple[str, int, str]] = []
    in_doc = False
    in_self = False
    for number, line in enumerate(text.split("\n"), start=1):
        if is_py and line.startswith("def selftest("):
            in_self = True
        if in_self:
            continue
        if is_py:
            quotes = line.count('"""') + line.count("'''")
            if in_doc:
                if quotes % 2 == 1:
                    in_doc = False
                continue
            if quotes % 2 == 1:
                in_doc = True
                continue
        if COMMENT_RE.match(line):
            continue
        for segment in QUOTE_SPLIT_RE.split(line)[1:]:
            if any(ch in segment for ch in METACHARACTERS):
                continue
            for match in PATH_RE.finditer(segment):
                candidate = match.group(0).rstrip(".")
                if candidate:
                    out.append((rel_path, number, candidate))
    return out


def declared_submodule(root: str) -> bool:
    """True when `.gitmodules` declares this path.

    A `private/<name>` that is NOT declared is an EXTERNAL repository this one does not track (private/growth and private/generative are separate GitLab repos). Such a root is legitimately missing from a fresh checkout, so its absence is not a dead path -- CI has no private/growth at all, which is what made the twin fail there while passing locally.
    """
    try:
        text = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    except OSError:
        return False
    pattern = re.compile(r"^[ \t]*path[ \t]*=[ \t]*%s[ \t]*$" % re.escape(root), re.MULTILINE)
    return bool(pattern.search(text))


def submodule_checked_out(root: str) -> bool:
    """False when the `private/<name>` root is empty, meaning the submodule was
    never initialised in this checkout."""
    directory = ROOT / root
    if not directory.is_dir():
        return False
    return any(directory.iterdir())


def path_resolves(candidate: str) -> bool:
    """Existence check with the NodeNext `.js` -> `.ts` fallback: a `./x.js`
    specifier legitimately resolves to `x.ts`."""
    target = ROOT / candidate
    if target.exists():
        return True
    if candidate.endswith(".js"):
        return (ROOT / (candidate[: -len(".js")] + ".ts")).exists()
    if candidate.endswith(".jsx"):
        return (ROOT / (candidate[: -len(".jsx")] + ".tsx")).exists()
    return False


def collect_dead_paths() -> list[str]:
    """The twin's `collect_dead_paths`, findings sorted and de-duplicated."""
    findings: set[str] = set()
    declared_cache: dict[str, bool] = {}
    checkout_cache: dict[str, bool] = {}
    for rel_path in scan_targets():
        for file_name, line, candidate in extract_literals(rel_path):
            rest = candidate.split("/", 1)[1] if "/" in candidate else ""
            root = candidate.split("/", 1)[0] + "/" + rest.split("/", 1)[0]
            if not (ROOT / root).is_dir():
                if root.startswith("private/"):
                    if root not in declared_cache:
                        declared_cache[root] = declared_submodule(root)
                    if not declared_cache[root]:
                        continue
                findings.add(
                    "TIER-A %s:%d: %s (workspace root %s does not exist)"
                    % (file_name, line, candidate, root)
                )
                continue
            # Tier B only: an uninitialised submodule is not a dead path.
            if root.startswith("private/"):
                if root not in checkout_cache:
                    checkout_cache[root] = submodule_checked_out(root)
                if not checkout_cache[root]:
                    continue
            if candidate == root:
                continue
            if EPHEMERAL_SEGMENTS.search(candidate):
                continue
            if not SOURCE_EXTENSIONS.search(candidate) and not candidate.endswith("/"):
                continue
            if path_resolves(candidate):
                continue
            findings.add("TIER-B %s:%d: %s" % (file_name, line, candidate))
    return sorted(findings)


def assert_scan_is_whole(gate) -> int:
    """Zero inputs is a FAILURE, never a pass, and so is a truncated walk."""
    count = len(scan_targets())
    if count < SCAN_FLOOR:
        gate.log_fail(
            "scan_targets yielded only %d file(s), floor %d: the walk TRUNCATED, so an "
            "empty finding list here would be a false clean bill rather than a clean tree"
            % (count, SCAN_FLOOR)
        )
    gate.log_pass("the scan is whole (%d files, floor %d)" % (count, SCAN_FLOOR))
    return count


@contextlib.contextmanager
def planted_fixture(stem: str, body: str):
    """Plant one scan target, yield its basename, and remove it whatever happens.

    A context manager rather than the twin's `trap ... RETURN`, for the reason `harness.temp_dir` gives: the trap is scaffolding for a language feature Python has. The removal is what keeps a killed run from leaving a synthetic dead path in a tracked directory, where the next reader would investigate a finding nobody introduced.
    """
    name = "%s%s.%s.ts" % (FIXTURE_NAME_PREFIX, stem, FIXTURE_PID_SUFFIX)
    path = FIXTURE_DIR / name
    path.write_text(body, encoding="utf-8")
    try:
        yield name
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------


def test_detector_fires_on_a_deleted_workspace(gate):
    """Control: prove the instrument can FAIL. A synthetic scan target naming a
    workspace that has never existed must be reported, otherwise this gate is
    exactly the vacuous check it was written to prevent."""
    with planted_fixture("fixture", FIXTURE_BODY) as planted:
        # Guard the CONTROL too, and for the sharper reason: this is the case that actually failed under load in the twin. Without the floor its failure message was "not in ''", which reads as "the detector is broken" when the truth was "the walk never reached the fixture".
        assert_scan_is_whole(gate)
        dead = collect_dead_paths()
        # Scoped to OUR fixture by name. A concurrent invocation plants the same dead path under its own pid, and an unscoped assertion would pass off that one -- a control that can be satisfied by somebody else's fixture is not a control. Anchored on the full fixture basename: a suffix match also catches this pid's noise fixture, whose name ends the same way.
        own = "\n".join(line for line in dead if planted in line)
        gate.assert_contains(
            own,
            "packages/%s" % MISSING_WORKSPACE,
            "detector must report a path under a nonexistent workspace",
        )
    gate.log_pass("detector fires on a deleted workspace (control case)")


def test_detector_ignores_runtime_and_glob_paths(gate):
    """Shape check: the two biggest false-positive sources must stay silent.

    Template literals carry `${}`, globs carry `*`, and comment prose names deleted
    paths on purpose. A detector that reported any of the three would be suppressed within a week, and a suppressed gate is the bug this whole file is about.
    """
    with planted_fixture("noise-fixture", NOISE_BODY):
        dead = collect_dead_paths()
        gate.assert_not_contains(
            "\n".join(dead),
            "gate-paths-exist-noise-fixture",
            "template literals, globs and comment prose must not be reported",
        )
    gate.log_pass("runtime-built paths, globs and comments are ignored")


def test_no_dead_path_constants(gate):
    """The real-tree verdict: every hardcoded workspace path still resolves."""
    assert_scan_is_whole(gate)
    # A CONCURRENT invocation of the twin plants its own control fixture, which is a deliberate dead path and would read here as a real finding. Filtering by the fixture filename shape is precise: nothing but this detector and its twin writes a `.gate-paths-exist-*` file into the scanned tree.
    dead = [line for line in collect_dead_paths() if FIXTURE_NAME_PREFIX not in line]
    if dead:
        for line in dead:
            gate.log_error(line)
        gate.log_fail("dead path constants found (see list above)")
    gate.log_pass("every hardcoded packages/* and private/* path constant resolves")


def test_this_module_is_not_itself_a_finding(gate):
    """THE SELF-SCANNING CONTROL, which the twin does not need and this port does.

    The twin is excluded from its own walk by `! -path '.ci/scripts/test/*'`, a deliberate line someone would have to delete. This module is excluded only because `.ci/rediacc_ci/` happens to be outside all three scanned roots, which a future widening would remove without anyone connecting the two. So the literals in this file are rendered through `%s` templates, and this case reds
    BY NAME if a template ever starts matching.
    """
    own = paths.relative_to_root(pathlib.Path(__file__))
    hits = ["%s:%d: %s" % (f, n, p) for f, n, p in extract_literals(own) if not path_resolves(p)]
    if hits:
        gate.log_fail(
            "this port's own source yields %d unresolvable path literal(s): %s. The "
            "fixture bodies must stay behind a `%%s` template, or a scanner that ever "
            "widens its roots to %s will report this file as a finding."
            % (len(hits), "; ".join(hits), os.path.dirname(own))
        )
    gate.log_pass("the port's own literals are all rendered, so it cannot flag itself")


def test_scripts_tsconfig_covers_both_tooling_trees(gate):
    """Same failure class, one level up: an `include` GLOB that resolves to nothing.

    A dead path constant and a dead include pattern fail identically -- both produce an empty set that every downstream check reports a checkmark over. `scripts/tsconfig.json` is the live example. It sat in the tree from creation until 2026-08-05 covering 70 files that nothing type-checked, and when it was
    finally run it produced 512 errors, ~99% of them artifacts of its own stale
    settings. A config that LOOKS like coverage is worse than no config, because it answers "is this tree type-checked?" with a yes.

    `--listFilesOnly` resolves the includes without type-checking. This is deliberately a COVERAGE assertion, not the type-check itself.
    """
    config = ROOT / "scripts" / "tsconfig.json"
    if not config.is_file():
        gate.log_fail(
            "scripts/tsconfig.json is gone; the tooling trees have no type-check target at all"
        )
    npx = harness.require_tool(
        "npx",
        "install node (the lane's setup-workspace step provides it); tsc is resolved through npx",
    )
    result = harness.run(
        [npx, "tsc", "-p", "scripts/tsconfig.json", "--listFilesOnly"], cwd=ROOT, timeout=600
    )
    if result.rc != 0:
        gate.log_fail(
            "could not resolve scripts/tsconfig.json's file list; a config that cannot be "
            "loaded checks nothing: %s" % (result.err.strip() or result.out.strip())
        )
    listed = result.out
    # CONTROL: an unresolvable or empty include would also produce a quiet pass below if we only checked for absence, so assert the list is non-trivial first. Anchored at the repo root: an unanchored "/scripts/" also matches packages/www/scripts/, which allowJs pulls in.
    prefix = os.fspath(ROOT)
    lines = listed.splitlines()
    n_scripts = len([x for x in lines if x.startswith(prefix + "/scripts/") and x.endswith(".ts")])
    n_ci = len([x for x in lines if x.startswith(prefix + "/.ci/scripts/") and x.endswith(".ts")])
    if n_scripts < 10:
        gate.log_fail(
            "scripts/tsconfig.json resolves only %d file(s) under scripts/; the include "
            "glob has gone empty or near-empty" % n_scripts
        )
    if n_ci < 1:
        gate.log_fail(
            "scripts/tsconfig.json resolves NO file under .ci/scripts/; that tree has no "
            "other tsconfig, so it is now unchecked by anything"
        )
    # And name one known file per tree, so a glob narrowed to a subdirectory still fails even while the counts stay healthy.
    gate.assert_contains(
        listed,
        "/scripts/gates/check-cli-docs.ts",
        "a known scripts/ file must be in the resolved set",
    )
    gate.assert_contains(
        listed,
        "/.ci/scripts/test/smoke-test-preview.ts",
        "the only .ci/scripts/ TypeScript file must be in the resolved set",
    )
    gate.log_pass(
        "scripts/tsconfig.json covers both tooling trees (%d under scripts/, %d under .ci/scripts/)"
        % (n_scripts, n_ci)
    )
