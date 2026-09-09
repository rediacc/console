"""Drive every case in `hookcases.STATIC`, one pytest node each.

ANTI-VACUITY FIRST, and the floor is DERIVED rather than typed. A number written by
hand here would be wrong the day a case is added and, worse, would read green against
a corpus that had collapsed to nothing if it were ever set to zero. So the floor is
`case(` occurrences counted out of the module's own SOURCE TEXT and compared against
the list Python actually built: two independent derivations of the same number, which
disagree the moment an entry stops being constructed.
"""

import re

import pytest

from rediacc_hooks.tests import hookcases, hooklabels

# `case(` at list indent, with NO `$` anchor. Anchoring to end-of-line would tie this
# floor to one formatter decision: `ruff format` puts a short row on a single line and
# a long one across several, so an anchored count would drop rows the day a payload got
# shorter -- a floor failing for its own reasons rather than for the corpus's.
CASE_CALL_RE = re.compile(r"^ {4}case\(", re.MULTILINE)


def test_the_corpus_is_not_empty_and_matches_its_own_source():
    source = hookcases.__file__.replace(".pyc", ".py")
    with open(source, encoding="utf-8") as handle:
        written = len(CASE_CALL_RE.findall(handle.read()))
    assert hookcases.STATIC, (
        "the static corpus is EMPTY, so every parametrized case below would be skipped "
        "and this file would report a clean green over nothing"
    )
    assert written == len(hookcases.STATIC), (
        "%d `case(` call(s) are written in %s but %d landed in STATIC. One of them is "
        "not being constructed, and the difference is invisible in a passing run."
        % (written, source, len(hookcases.STATIC))
    )


def test_every_case_names_a_guard_that_exists():
    """A KEY THAT RESOLVES TO NOTHING MUST BE LOUD.

    `python3 dispatch.py <typo>` raises ModuleNotFoundError and exits 1, which a case
    expecting 2 would report as a plain miss and a case expecting 0 would report as a
    failure -- both wrong about the reason. Naming the missing module here says which
    of the two it is, once, instead of 300 confusing case failures.
    """
    missing = []
    for key in sorted({kase.key for kase in hookcases.STATIC}):
        try:
            hookcases.guard_cmd(key)
        except hookcases.GuardKeyError as exc:
            missing.append(str(exc))
    assert not missing, "\n".join(missing)


@pytest.mark.parametrize("kase", hookcases.STATIC, ids=[k.label for k in hookcases.STATIC])
def test_a_guard_case(kase):
    code, said = hookcases.run_guard(kase.key, kase.payload, want_stderr=kase.needle is not None)
    ok = code == kase.expected and (kase.needle is None or kase.needle in said)
    # Emitted BEFORE the assertion, and with the real verdict, so the label multiset a
    # failing run produces is still complete. A comparison that lost a label whenever a
    # case failed would report the failure twice and the shape of the run not at all.
    hooklabels.record(kase.expected, kase.label, ok=ok)
    assert code == kase.expected, "%s: expected exit %d, got %d%s" % (
        kase.label,
        kase.expected,
        code,
        ("\n" + said) if said else "",
    )
    assert kase.needle is None or kase.needle in said, (
        "%s: exit %d was right but the message never said %r. What it said:\n%s"
        % (kase.label, code, kase.needle, said)
    )
