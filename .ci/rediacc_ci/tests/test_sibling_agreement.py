"""Sibling agreement: two implementations of ONE decision, compared against each other.

THE DEFECT THIS EXISTS FOR, measured rather than imagined. `python_comment_lines` (the lint side, feeding rules R1-R19) read comments AND docstrings, while `_python_reflow_lines` (the reflow side, feeding the rewriter and R19's own detection) read comments only. Not duplicated text -- two pieces of code making the same decision about what counts as prose, and disagreeing. The
consequence was that 9,932 narrow docstring paragraphs across 1,021 of 1,024 in-scope files were invisible to the rule meant to find them and to the tool meant to fix them, and every gate stayed green throughout. It was found by a human asking why two code paths existed.

WHY A DUPLICATION DETECTOR CANNOT FIND THIS, which is the reason this module is not a second copy of `check-shape-duplication.ts`. That gate hashes 5-line windows with comments and literals stripped and identifiers left alone, so it finds two spans that LOOK alike. These two functions looked nothing alike; they were different code reaching different answers. The question a clone
detector asks is "is this the Nth copy", and the question that mattered was "do these two agree".

THE FORM IS A PAIR OF CALLABLES OVER A SHARED CORPUS, never a declarative list of paths that claim to agree. This repository already keeps roughly twelve executable parity gates that recompute both sides and compare, and that shape is honest by construction: a stale entry cannot go quiet, because both sides are recomputed on every run; a renamed function fails at import with
no allowlist to hide in; and a new sibling that nobody registered is caught by the coverage arm rather than silently omitted. A registry file has none of those three properties.

TWO ARMS, AND NEITHER ALONE IS ENOUGH. Containment asks whether the reflow ever folds a line the linter does not police, which catches a rewriter reaching past what the rules cover. Coverage asks whether each REGION KIND the linter sees is also seen by the reflow, which is the arm that catches the real incident: before the two scanners were unified the reflow side saw 17,826
docstring lines as zero, while the linter saw 39,019 of them. Containment alone would have passed that day, because a subset of nothing is still a subset.
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
    assert blind_to not in blind_kinds(lint_by_kind, dict(flow_by_kind, **{blind_to: lint_by_kind[blind_to]})), (
        "%s: the control's own healthy baseline already reads as blind" % label
    )
    assert blind_to in blind_kinds(lint_by_kind, flow_by_kind), (
        "%s: the planted blindness was NOT detected, so the coverage arm cannot fail" % label
    )
