"""`rediacc_ci.shacite`: the one rule for writing a short sha into a citation and for reading one back (#0241c97d).

Pure functions, so every case is a literal in and a literal out. Each READ case is a pair: a token that must be judged and the same digits that must not, because a predicate that answers the same for both cannot tell a sha from a run id. The git-backed halves (a reader really resolving such a citation, a verb really writing one) are in `test_gate_plan_citations.py`, `test-planrec.py` and `test_wl_tick_commit_ref.py`.
"""

import re

from rediacc_ci import paths
from rediacc_ci import shacite as SC

DIGITS = "325389306" + "4ab" + "0" * 28


def test_a_commit_prefixed_digit_run_is_read_as_a_sha():
    text = "(ticked) commit:325389306 rc=0"
    assert not SC.skip_as_number(text, text.index("3"), "325389306")
    assert SC.commit_cited(text, text.index("3"))


def test_a_bare_digit_run_is_still_skipped():
    text = "(ticked) run 325389306 rc=0"
    assert SC.skip_as_number(text, text.index("3"), "325389306")


def test_a_look_alike_prefix_does_not_license_a_digit_run():
    for text in ("nocommit:325389306", "xcommit:325389306", "re-commit:325389306"):
        assert SC.skip_as_number(text, text.index("3"), "325389306"), text


def test_the_prefix_at_the_very_start_of_the_text_counts():
    assert SC.commit_cited("commit:325389306", 7)
    assert not SC.commit_cited("ommit:325389306", 6)


def test_a_letter_bearing_token_is_never_skipped_whatever_its_prefix():
    assert not SC.skip_as_number("see c6d3af163", 4, "c6d3af163")


def test_citable_token_lengthens_until_a_letter():
    assert SC.citable_token(DIGITS, DIGITS[:9]) == DIGITS[:11]
    assert SC.citable_token("abc" + "0" * 37, "abc000000") == "abc000000"
    assert SC.citable_token("1" * 40, "1" * 9) == "1" * 40


def test_lengthen_commit_refs_rewrites_only_the_all_digit_refs_it_can_expand():
    text = "commit:%s and commit:abc000000 and commit:111111111 and run 325389306" % DIGITS[:9]
    full = {DIGITS[:9]: DIGITS}
    got = SC.lengthen_commit_refs(text, lambda tok: full.get(tok, ""))
    assert got == (
        "commit:%s and commit:abc000000 and commit:111111111 and run 325389306" % DIGITS[:11]
    )


def test_lengthen_ignores_an_expansion_that_does_not_extend_the_token():
    """A resolver that answered for a different object must not rewrite the citation into it."""
    assert SC.lengthen_commit_refs("commit:325389306", lambda _t: "ab" * 20) == "commit:325389306"


def test_the_ref_shape_is_the_tick_verbs_own():
    """`worklist.COMMIT_REF_RE` validates a tick; the writer here must agree with it about which tokens are refs, or a lengthened ref could be one the validator never saw."""
    src = (paths.hooks_stop_dir() / "worklist.py").read_text(encoding="utf-8")
    m = re.search(r'^COMMIT_REF_RE = re\.compile\(r"(.+)"\)$', src, re.MULTILINE)
    assert m, "worklist.COMMIT_REF_RE was not found; the comparison would assert nothing"
    assert m.group(1) == SC.COMMIT_REF_RE.pattern
