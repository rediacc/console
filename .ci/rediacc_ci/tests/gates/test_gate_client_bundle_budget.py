r"""Port of `.ci/scripts/test/gates/test-client-bundle-budget.sh`, retired in W7 P5.

`scripts/gates/check-client-bundle-budget.ts`, and, crucially, a MUTANT of it.

WHY THIS EXISTS. That gate was green for as long as it had existed while under-reporting the homepage by 124,673 B. `importSpecifiers` required whitespace after `import`, which minified side-effect imports do not have (`import"./x.js";import"./y.js";`), so the walk dead-ended at a 129-byte facade chunk and never saw the 122,110 B video player every homepage visitor downloads. It
reported 451,621 B for a page shipping 576,294 B, and printed a checkmark.

The gate's own fixture is why nothing caught it: it only ever wrote
`import { x } from "./heavy.js"` -- spaced, and via `from`. A fixture that never
writes the shape the real bundler emits cannot fail on it.

So the case that matters here is the MUTANT: revert the one quantifier and the selftest must go red and NAME the facade plant. Without it the plants are unfalsifiable, and their first draft genuinely was -- they asserted on chunks the fixture already reached by another path, so they passed against the very defect they were written for.

WHERE THE MUTANT LIVES. Outside the repo, with `node_modules` SYMLINKED in. Writing it to `scripts/` was the twin's first draft and `check:ci-pool-writer-safety` caught it: the battery would then schedule that file in the shared pool beside tests reading the same paths. The gate imports only node builtins plus `@rediacc/locales`, so one symlink resolves everything.

THE THIRD ARM IS REIMPLEMENTED, and the two spellings agree by measurement rather than by inspection. The twin counts the real build's no-space edges with `grep -rohE 'import"[^"]+"' | wc -l`; this port walks the same two directories with a BYTES regex applied LINE BY LINE. Line-by-line is what makes them the same question: `grep` cannot match across a newline, while Python's
`[^"]` matches one happily, so a whole-file `findall` would count edges grep never sees. Bytes rather than decoded text because a bundle is not guaranteed to be valid UTF-8 and a decode error is not a reason to report zero. Measured on this tree 2026-09-07: both spellings answer 49 in `dist/assets` and 0 in `dist/scripts`.

WHY IT IS A LOUD SKIP AND NOT A FAILURE when `dist` is absent, which is the one place this directory's "unknown is a failure" rule is deliberately not applied: the arm asks a question about a BUILD ARTIFACT, and a tree that has not been built has no answer rather than an unknown one. The twin says so in its own output and the port keeps that word-for-word, so the reader sees that
the arm asserted nothing.

NO `xdist_group`. Each case runs `tsx` in a subprocess against its own `tmp_path`;
the real-dist arm only reads. Nothing is bound and no module global is mutated.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts", "gates", "check-client-bundle-budget.ts")
DIST = paths.from_root("packages", "www", "dist")

# The one character the mutant takes back: `\s*` to `\s+` in the side-effect
# import matcher. `\bimport\s*\(` on the line above is a DIFFERENT matcher (the
# dynamic form) and is deliberately left alone, exactly as the twin's sed is anchored on the `["']` that follows.
FIXED = r"""/\bimport\s*["']"""
REVERTED = r"""/\bimport\s+["']"""

# `import"..."`: a side-effect import with NO space, which is what a minifier emits and what the gate was blind to.
NO_SPACE_EDGE = re.compile(rb'import"[^"]+"')

# The two directories the real build writes chunks into.
DIST_SUBDIRS = ("assets", "scripts")


def run_tsx(gate, script, *args: str) -> harness.RunResult:
    """Drive a TypeScript program through the workspace `npx tsx`, from the repo root.

    THE EXISTENCE REFUSAL IS NOT DECORATION. Both callers hand this a path, and one of them is a MUTANT written a moment earlier. A mutant that failed to be written would make `tsx` exit non-zero for a reason that has nothing to do with the plant, and the case asserting `exit 1` would go green on it.
    """
    if not pathlib.Path(script).is_file():
        gate.log_fail(
            "there is nothing to run at %s, so this case could not exercise the subject "
            "at all -- which is a FAILURE and not a pass" % script
        )
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(script), *args], cwd=paths.repo_root())


def count_no_space_edges() -> int:
    """`grep -rohE 'import"[^"]+"' <dir> | wc -l`, reimplemented. See the module docstring."""
    total = 0
    for name in DIST_SUBDIRS:
        root = DIST / name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            for line in path.read_bytes().split(b"\n"):
                total += len(NO_SPACE_EDGE.findall(line))
    return total


def test_selftest_green(gate):
    gate.log_test("the gate's own controls cover the shape that hid 124,673 B")
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    result = run_tsx(gate, GATE, "--selftest")
    gate.assert_exit_code(0, result.rc, "the gate's selftest must pass on a clean tree")
    gate.assert_contains(
        result.combined, "no-space side-effect facade", "and exercise the facade shape"
    )
    gate.assert_contains(
        result.combined, "ONLY through such a facade", "and the dynamic edge behind it"
    )
    gate.log_pass("the selftest covers the shape that hid 124,673 B")


def test_mutant_reverts_the_fix(gate, tmp_path):
    """THE MUTANT. The control that proves the controls can fail."""
    gate.log_test("CONTROL: reverting the quantifier must make the gate's own plants go red")
    (tmp_path / "node_modules").symlink_to(paths.from_root("node_modules"))
    source = GATE.read_text(encoding="utf-8")
    mutated = source.replace(FIXED, REVERTED)
    # VACUITY GUARD: if the replacement stopped matching, the mutant IS the gate and a green run below would mean nothing.
    if mutated == source:
        gate.log_fail(
            "the mutation did not apply (%r is no longer in the gate); this control would "
            "be testing the unmutated gate" % FIXED
        )
    mutant = tmp_path / "mutant.ts"
    mutant.write_text(mutated, encoding="utf-8")
    result = run_tsx(gate, mutant, "--selftest")
    gate.assert_exit_code(1, result.rc, r"reverting \s* to \s+ must make the selftest FAIL")
    gate.assert_contains(
        result.combined,
        "FAIL  PLANT: a no-space side-effect facade",
        "naming the facade plant",
    )
    gate.log_pass("CONTROL: the plants detect the exact defect, not merely pass beside it")


def test_real_dist_has_the_shape(gate):
    """ANTI-VACUITY against the real build, when one exists.

    49 no-space edges across 20 files in the dist as measured on 2026-09-03, and 49 again on 2026-09-07. A floor of ONE is anti-vacuous and goes red the instant the regex regresses; an absent dist is a LOUD skip, never a silent pass.
    """
    gate.log_test("the real build must still emit the shape the fix exists for")
    if not DIST.is_dir():
        gate.log_pass(
            "SKIP (loudly): %s absent, so the real-build arm asserted NOTHING"
            % paths.relative_to_root(DIST)
        )
        return
    found = count_no_space_edges()
    if found < 1:
        gate.log_fail(
            "found %d no-space side-effect edge(s) in the real dist; this gate's whole "
            "subject is gone, so its green would mean nothing" % found
        )
    gate.assertions += 1
    gate.log_pass(
        "the real build still emits the shape (%d edge(s)); the fix is not measuring a "
        "fixture only" % found
    )


def test_the_reimplemented_count_agrees_with_grep(gate):
    """ADDED BY THE PORT, because the arm above stopped being a `grep`.

    The twin runs `grep -rohE 'import\"[^\"]+\"' | wc -l`; this module runs a Python regex. Two spellings of one question is two answers, and the expensive half is that both look right, so the two are driven side by side on the real dist and required to agree. It also catches the direction a floor of one cannot: a Python count that is far too HIGH (the whole-file `[^\"]`-spans-
    newlines mistake) would satisfy the floor and be wrong.
    """
    gate.log_test("the Python count and the twin's grep must answer the same number")
    if not DIST.is_dir():
        gate.log_pass("SKIP (loudly): no dist, so there was nothing to compare the two on")
        return
    grep = harness.require_tool("grep", "install grep; the twin's spelling is the reference")
    reference = 0
    for name in DIST_SUBDIRS:
        root = DIST / name
        if not root.is_dir():
            continue
        result = harness.run([grep, "-rohE", 'import"[^"]+"', str(root)])
        # 0 = matched, 1 = matched nothing. Anything else is grep itself failing,
        # and folding that into "zero edges" is the vacuity this case exists for.
        if result.rc not in (0, 1):
            gate.log_fail(
                "grep exited %d over %s (stderr: %s), so the reference count was never "
                "taken" % (result.rc, root, result.err.strip())
            )
        reference += len([line for line in result.out.splitlines() if line])
    gate.assert_eq(
        count_no_space_edges(),
        reference,
        "the port's line-by-line bytes regex must count exactly what grep -o counts",
    )
    gate.log_pass(
        "the reimplemented count agrees with the twin's grep on the real dist (%d edge(s))"
        % reference
    )
