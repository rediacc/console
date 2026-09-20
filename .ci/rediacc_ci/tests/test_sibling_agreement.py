"""Sibling agreement: two implementations of ONE decision, compared against each other.

THE DEFECT THIS EXISTS FOR, measured rather than imagined. `python_comment_lines` (the lint side, feeding rules R1-R19) read comments AND docstrings, while `_python_reflow_lines` (the reflow side, feeding the rewriter and R19's own detection) read comments only. Not duplicated text -- two pieces of code making the same decision about what counts as prose, and disagreeing. The
consequence was that 9,932 narrow docstring paragraphs across 1,021 of 1,024 in-scope files were invisible to the rule meant to find them and to the tool meant to fix them, and every gate stayed green throughout. It was found by a human asking why two code paths existed.

WHY A DUPLICATION DETECTOR CANNOT FIND THIS, which is the reason this module is not a second copy of `check-shape-duplication.ts`. That gate hashes 5-line windows with comments and literals stripped and identifiers left alone, so it finds two spans that LOOK alike. These two functions looked nothing alike; they were different code reaching different answers. The question a clone
detector asks is "is this the Nth copy", and the question that mattered was "do these two agree".

THE FORM IS A PAIR OF CALLABLES OVER A SHARED CORPUS, never a declarative list of paths that claim to agree. This repository already keeps roughly twelve executable parity gates that recompute both sides and compare, and that shape is honest by construction: a stale entry cannot go quiet, because both sides are recomputed on every run; a renamed function fails at import with no
allowlist to hide in; and a new sibling that nobody registered is caught by the coverage arm rather than silently omitted. A registry file has none of those three properties.

TWO ARMS, AND NEITHER ALONE IS ENOUGH. Containment asks whether the reflow ever folds a line the linter does not police, which catches a rewriter reaching past what the rules cover. Coverage asks whether the reflow sees close to what the linter sees, which is the arm that catches the real incident: before the two scanners were unified the reflow side saw 17,826 docstring lines as
zero, while the linter saw 39,019 of them. Containment alone would have passed that day, because a subset of nothing is still a subset.

A SECOND PAIR, LOWER IN THIS FILE, covers `cstyle_comment_lines` against `_cstyle_reflow_lines` for `.ts`/`.js`/`.go`. It has no region-kind axis to measure coverage against -- a C-style language carries one comment convention, not two -- so its coverage arm is a SHARE of whole-line comments instead, guarding against the incident that would recur if `_cstyle_scan`'s single shared
walk were ever re-split back into the two independently maintained copies it replaced.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci.quality import prose_style as ps

GLOBALS, RULES = ps.load_rules_file(ps.paths.repo_root() if hasattr(ps, "paths") else ".")

# A kind whose reflow-side share falls under this is treated as BLINDNESS rather than as conservatism. Measured 2026-09-17 the real shares are 72% for comments and 46% for docstrings, the gap being the boundary and structural lines the reflow deliberately declines to fold, so a floor of one in ten is far below anything legitimate and far above the zero that the incident produced.
COVERAGE_FLOOR = 0.10


def tracked_python_files():
    """The in-scope corpus, from git rather than from a filesystem walk."""
    return [f for f in ps.discover(".", GLOBALS) if f.endswith(".py")]


def sides(text):
    """(lint linenos, {folded lineno: body}, {lineno: region kind}) for one file.

    The folded map is taken from `comment_segments` rather than from `_python_reflow_lines`, and the difference is load-bearing: the latter is the set of lines ELIGIBLE to be considered, while the former is what the stops actually leave foldable. Comparing against eligibility reports a `style-ok` directive as a disagreement when the rewriter was never going to touch it.
    """
    lint = {line.lineno for line in ps.python_comment_lines(text)}
    folded = {}
    for segment in ps.comment_segments(text, ".py"):
        if segment[0] == "para":
            start, bodies = segment[1], segment[4]
            for offset, body in enumerate(bodies):
                folded[start + offset] = body
    kinds = {}
    for chunk in ps._python_scan(text):
        for offset in range(len(chunk.text.splitlines()) or 1):
            kinds[chunk.start + offset] = chunk.kind
    return lint, folded, kinds


def blind_kinds(lint_by_kind, flow_by_kind):
    """The coverage verdict, as ONE function both the real arm and its planted control call.

    Factored out rather than written twice on purpose: a control that re-implements the arithmetic it is meant to be testing proves that the control's copy works, which is the same class of defect this whole module exists to catch.
    """
    return {
        kind: (seen, flow_by_kind.get(kind, 0))
        for kind, seen in lint_by_kind.items()
        if kind != "?" and flow_by_kind.get(kind, 0) < seen * COVERAGE_FLOOR
    }


def test_the_reflow_never_folds_prose_the_linter_does_not_police():
    """CONTAINMENT. A line the rewriter joins into a paragraph is a line the rules have judged.

    The filter is the linter's OWN content test rather than a re-derivation of it: a comment that is entirely a backticked code span, or a bare `#` separator, scrubs to nothing and the linter drops it having nothing to say. Treating those as disagreements produced 277 false positives on the first run of this check, which is a useful reminder that the two sides are allowed to differ
    about what is WORTH SAYING and are never allowed to differ about what prose IS.
    """
    offenders = []
    for rel in tracked_python_files():
        try:
            text = pathlib.Path(rel).read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            lint, folded, _ = sides(text)
        except (SyntaxError, ValueError):
            continue
        extra = sorted(
            n
            for n, body in folded.items()
            if n not in lint and ps.scrub(ps._strip_quotes(body)).strip()
        )
        if extra:
            offenders.append((rel, extra[:3]))
    assert not offenders, (
        "the reflow folds %d file(s) worth of prose the linter never sees, so the rewriter is "
        "reaching past the rules: %s" % (len(offenders), offenders[:5])
    )


def test_every_region_kind_the_linter_sees_is_also_seen_by_the_reflow():
    """COVERAGE, and this is the arm that would have caught the real incident.

    A whole KIND of prose region going unseen by one side is precisely the shape of the defect: the reflow side read comments and never once read a docstring, so the rule fed by it could not report a single narrow docstring paragraph in the entire tree. The floor is a share rather than a count because the reflow legitimately declines the boundary and structural lines, and a share
    is what distinguishes conservatism from blindness.
    """
    lint_by_kind, flow_by_kind = {}, {}
    for rel in tracked_python_files():
        try:
            text = pathlib.Path(rel).read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            lint, folded, kinds = sides(text)
        except (SyntaxError, ValueError):
            continue
        for n in lint:
            lint_by_kind[kinds.get(n, "?")] = lint_by_kind.get(kinds.get(n, "?"), 0) + 1
        for n in folded:
            flow_by_kind[kinds.get(n, "?")] = flow_by_kind.get(kinds.get(n, "?"), 0) + 1

    assert lint_by_kind, "the linter saw no prose at all, so this comparison is vacuous"
    blind = blind_kinds(lint_by_kind, flow_by_kind)
    assert not blind, (
        "one side is blind to a whole region kind, which is how 9,932 docstring paragraphs "
        "went unseen: %s (floor is %.0f%% of the linter's count)" % (blind, COVERAGE_FLOOR * 100)
    )


@pytest.mark.parametrize(
    ("label", "blind_to"),
    [("a reflow blind to docstrings", "docstring"), ("a reflow blind to comments", "comment")],
)
def test_the_coverage_arm_can_actually_fail(label, blind_to):
    """THE ANTI-VACUITY CONTROL, planting the real defect rather than asserting the check is sound.

    Both arms above pass on a healthy tree, which is exactly what a check incapable of failing also does. Here the reflow side is filtered to drop one region kind entirely, reproducing the pre-unification state, and the coverage arithmetic must call it blindness. Running this for BOTH kinds rather than the historical one keeps the control from encoding the accident that the
    incident happened to a docstring.
    """
    lint_by_kind, flow_by_kind = {}, {}
    for rel in tracked_python_files()[:120]:
        try:
            text = pathlib.Path(rel).read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            lint, folded, kinds = sides(text)
        except (SyntaxError, ValueError):
            continue
        for n in lint:
            kind = kinds.get(n, "?")
            lint_by_kind[kind] = lint_by_kind.get(kind, 0) + 1
        for n in folded:
            kind = kinds.get(n, "?")
            # THE PLANT: the reflow side simply never reports this kind, which is what the pre-unification `_python_reflow_lines` did to every docstring in the tree. Everything else runs unchanged, including the verdict function the real arm calls.
            if kind == blind_to:
                continue
            flow_by_kind[kind] = flow_by_kind.get(kind, 0) + 1

    assert lint_by_kind.get(blind_to, 0) > 0, "%s: the corpus carries no %s to be blind to" % (
        label,
        blind_to,
    )
    # HEALTHY FIRST, so the plant is shown to be what changed the answer rather than the corpus slice.
    assert blind_to not in blind_kinds(
        lint_by_kind, dict(flow_by_kind, **{blind_to: lint_by_kind[blind_to]})
    ), "%s: the control's own healthy baseline already reads as blind" % label
    assert blind_to in blind_kinds(lint_by_kind, flow_by_kind), (
        "%s: the planted blindness was NOT detected, so the coverage arm cannot fail" % label
    )


# --------------------------------------------------------------------------- THE C-STYLE PAIR: cstyle_comment_lines against _cstyle_reflow_lines ---------------------------------------------------------------------------
#
# NO REGION-KIND AXIS HERE, which is why the Python pair's coverage arm does not simply generalise. A `.ts`/`.js`/`.go` file has one comment convention, not two: there is no docstring for a reflow side to go blind to. Both functions already derive from the SAME `_cstyle_scan` walk (unified for exactly the reason `test_sibling_agreement.py`'s header names -- two independently
# maintained copies of one quote/template state machine disagreed on a line-continuation edge case neither author had noticed), so the incident this pair specifically guards against is a FUTURE re-split back into two scanners, not a currently-live docstring-shaped blind spot.
#
# THE COVERAGE SIGNAL IS THEREFORE A SHARE OF WHOLE-LINE COMMENTS, not of region kinds. `cstyle_comment_lines` reports every comment, whole-line AND trailing (`x = 1; // note`), so comparing its raw total against the reflow side's whole-line-only total measures the wrong thing -- trailing comments are never eligible for folding by design, and a naive share came out at 27%
# purely from that mismatch, not from any blindness. The correct baseline restricts the lint side to WHOLE-LINE `//` comments only, which both functions are equally positioned to see. Measured 2026-09-17 across 1,196 tracked `.ts`/`.tsx`/`.js`/`.cjs`/`.mjs`/`.go` files: 11,454 whole-line comments, 10,634 reflow-eligible lines, a 92.8% share -- the gap being `COMMENT_DIRECTIVE`/
# `CODE_SHAPED_COMMENT` exclusions the reflow side applies and the plain lint side does not, which is conservatism, not blindness.

CSTYLE_SUFFIXES = (".ts", ".tsx", ".js", ".cjs", ".mjs", ".go")
CSTYLE_COVERAGE_FLOOR = 0.50  # measured share is 0.93; the floor sits far below it and far above the zero a re-split scanner would produce


def tracked_cstyle_files():
    return [f for f in ps.discover(".", GLOBALS) if pathlib.Path(f).suffix in CSTYLE_SUFFIXES]


def cstyle_whole_line_count(text):
    """Whole-line `//` comments only, the shape both sides are equally positioned to see."""
    return sum(1 for item in ps._cstyle_scan(text) if item[0] == "line" and not item[2].strip())


def test_the_cstyle_reflow_never_folds_a_line_the_linter_does_not_police():
    """CONTAINMENT, the C-style twin of the Python arm above."""
    offenders = []
    for rel in tracked_cstyle_files():
        try:
            text = pathlib.Path(rel).read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            lint = {line.lineno for line in ps.cstyle_comment_lines(text)}
            flow = ps._cstyle_reflow_lines(text)
        except (SyntaxError, ValueError):
            continue
        extra = sorted(
            n
            for n, (_i, body, _m, _d) in flow.items()
            if n not in lint and ps.scrub(ps._strip_quotes(body)).strip()
        )
        if extra:
            offenders.append((rel, extra[:3]))
    assert not offenders, (
        "the C-style reflow folds %d file(s) worth of prose the linter never sees: %s"
        % (len(offenders), offenders[:5])
    )


def cstyle_coverage_ok(whole_total, flow_total):
    """The verdict BOTH the real arm and its planted control call, on the same reasoning `blind_kinds` above does: a control that re-implements the arithmetic it is meant to be testing proves the control's copy works, not the arm's."""
    assert whole_total > 0, "no whole-line // comments to measure coverage against"
    return (flow_total / whole_total) >= CSTYLE_COVERAGE_FLOOR


def test_the_cstyle_reflow_sees_most_whole_line_comments_the_linter_sees():
    """COVERAGE, expressed as a SHARE of whole-line comments rather than a region-kind axis, since a `//` language has only one comment convention to be blind to. This is the arm that would catch a future re-split of `_cstyle_scan` back into two independently maintained copies -- the exact history this pair's own docstring records."""
    whole_total = flow_total = 0
    for rel in tracked_cstyle_files():
        try:
            text = pathlib.Path(rel).read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            whole_total += cstyle_whole_line_count(text)
            flow_total += len(ps._cstyle_reflow_lines(text))
        except (SyntaxError, ValueError):
            continue
    assert cstyle_coverage_ok(whole_total, flow_total), (
        "the C-style reflow sees only %.1f%% of whole-line comments the linter sees (floor %.0f%%), "
        "which is the shape a re-split scanner would produce"
        % (100 * flow_total / whole_total, CSTYLE_COVERAGE_FLOOR * 100)
    )


def test_the_cstyle_coverage_arm_can_actually_fail():
    """THE ANTI-VACUITY CONTROL: plant the historical defect (the reflow side blind to line comments entirely, as it would be if a future edit re-split `_cstyle_scan` into two copies and the reflow copy lost its `line` branch) and confirm the SAME verdict function the real arm calls actually calls it."""
    whole_total = 0
    for rel in tracked_cstyle_files()[:150]:
        try:
            text = pathlib.Path(rel).read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            whole_total += cstyle_whole_line_count(text)
        except (SyntaxError, ValueError):
            continue
    assert whole_total > 0, "the sampled corpus carries no whole-line // comments to be blind to"
    healthy_flow_total = whole_total  # a 100% share must read as healthy before trusting the plant
    assert cstyle_coverage_ok(whole_total, healthy_flow_total), (
        "the control's own healthy baseline already reads as blind"
    )
    planted_flow_total = 0  # the historical defect: the reflow side sees nothing at all
    assert not cstyle_coverage_ok(whole_total, planted_flow_total), (
        "the planted blindness (0 reflow-eligible lines against %d whole-line comments) was not "
        "detected, so the coverage arm cannot fail" % whole_total
    )
