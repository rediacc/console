"""The review-class index (agent/plans/PLAN-experience-feedback.md P1, box A1).

Controls first, each the half that must stay SILENT or uncounted: two fixed findings of a class earn no brief line, a `not-a-bug` finding is never counted as fixed, a low-severity finding is excluded, and a cache hit parses no record at all. Then the firing half: three fixed findings earn exactly one line, the line limit holds, a finding's own class beats the keyword table, and the cache rebuilds when a record lands.

Every record is a real `wl_review.render` output in a scratch tree, so the index reads exactly what the reviewer writes.
"""

from __future__ import annotations

import os

import pytest

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")
C = wlfix.import_wl("wl_reviewclass")

BRANCH = "1110-1"
ME8 = "abcdef01"
AT = "2026-11-10T00:00:00Z"
FIXED = "fixed %s | %s %s" % ("f" * 40, ME8, AT)
REFUTED = "not-a-bug | the code already does this on line 12 | %s %s" % (ME8, AT)
DOC = "The docstring says the guard refuses, but it returns ALLOW on that path."
TEST = "The new branch has no test, so a regression would pass the suite."
SWALLOW = "The read error is silently swallowed and the gate exits 0."


_N = [0]


def _record(root, findings):
    """One review file holding `findings` [(severity, file, claim, resolution)]; returns its path."""
    _N[0] += 1
    sha = ("%08x" % _N[0]) + "0" * 32
    review = R.Review(
        sha=sha,
        subject="s",
        branch=BRANCH,
        reviewed_at=AT,
        model="m",
        verdict="findings",
        findings=[
            R.Finding(
                id="%s.%d" % (sha[:8], n + 1),
                severity=sev,
                file=path,
                line=1,
                anchor="in-diff",
                claim=claim,
                resolution=res,
            )
            for n, (sev, path, claim, res) in enumerate(findings)
        ],
    )
    target = R.review_path(root, BRANCH, sha)
    R.write_atomic(target, R.render(review))
    return target


def _fresh(root):
    """The fold, never the cache: each test asks about the records it planted."""
    return C.index(root)


# ---------------------------------------------------------------- controls: what must stay silent


def test_two_fixed_findings_stay_silent(tmp_path):
    _record(tmp_path, [("medium", "a/x.py", DOC, FIXED), ("high", "a/y.py", DOC, FIXED)])
    idx = _fresh(tmp_path)
    assert C.class_counts(idx, ["a/**"])[0] == {"doc-contradicts-code": 2}
    assert C.brief_lines(idx, ["a/**"]) == []


def test_not_a_bug_is_not_counted_as_fixed(tmp_path):
    _record(tmp_path, [("medium", "a/x.py", DOC, REFUTED)] * 5)
    idx = _fresh(tmp_path)
    assert idx["files"]["a/x.py"] == {"fixed": {}, "refuted": {"doc-contradicts-code": 5}}
    assert C.brief_lines(idx, ["a/**"]) == []
    assert C.file_prior(idx, "a/x.py") == {"fixed": 0, "refuted": 5, "top": ""}


def test_low_severity_is_excluded(tmp_path):
    _record(tmp_path, [("low", "a/x.py", DOC, FIXED)] * 6)
    idx = _fresh(tmp_path)
    assert idx["files"] == {}
    assert idx["counted"] == 0
    assert C.brief_lines(idx, ["a/**"]) == []


def test_a_cache_hit_does_no_parse(tmp_path):
    _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)] * 3)
    first = C.index(tmp_path)
    assert first["cached"] is False
    assert (tmp_path / C.CACHE_REL).is_file()

    def refuse(_text):
        raise AssertionError("a cache hit must not parse a record")

    again = C.index(tmp_path, parse=refuse)
    assert again["cached"] is True
    assert again["files"] == first["files"]


def test_files_outside_the_owns_stay_silent(tmp_path):
    _record(tmp_path, [("medium", "b/z.py", DOC, FIXED)] * 4)
    assert C.brief_lines(_fresh(tmp_path), ["a/**"]) == []


def test_other_never_earns_a_line(tmp_path):
    _record(tmp_path, [("medium", "a/x.py", "Bsize is int32 on linux/386.", FIXED)] * 5)
    idx = _fresh(tmp_path)
    assert C.class_counts(idx, ["a/**"])[0] == {"other": 5}
    assert C.brief_lines(idx, ["a/**"]) == []


def test_no_store_folds_to_nothing(tmp_path):
    idx = C.index(tmp_path)
    assert idx["files"] == {}
    assert idx["records"] == 0


# ---------------------------------------------------------------- the firing half


def test_three_fixed_findings_earn_one_line(tmp_path):
    _record(tmp_path, [("medium", "a/x.py", DOC, FIXED), ("high", "a/y.py", DOC, FIXED)])
    _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)])
    lines = C.brief_lines(_fresh(tmp_path), ["a/**"])
    assert len(lines) == 1
    assert "3 'doc-contradicts-code'" in lines[0]
    assert "a/x.py, a/y.py" in lines[0]


def test_at_most_three_lines_strongest_first(tmp_path):
    seam = "The monkeypatch is never restored, so it leaks into the next case."
    _record(
        tmp_path,
        [("medium", "a/x.py", DOC, FIXED)] * 3
        + [("medium", "a/x.py", TEST, FIXED)] * 5
        + [("medium", "a/x.py", SWALLOW, FIXED)] * 4,
    )
    _record(tmp_path, [("medium", "a/x.py", seam, FIXED)] * 3)
    lines = C.brief_lines(_fresh(tmp_path), ["a/**"])
    assert len(lines) == 3
    assert "'missing-control-test'" in lines[0]
    assert "'swallowed-error'" in lines[1]
    # 3 doc and 3 seam tie; the tie breaks on the class name, so doc wins the last slot.
    assert "'doc-contradicts-code'" in lines[2]


def test_a_findings_own_class_beats_the_table():
    finding = R.Finding("x.1", "medium", "a.py", 1, "in-diff", DOC)
    assert C.finding_class(finding) == "doc-contradicts-code"
    setattr(finding, C.CLASS_ATTR, "swallowed-error")
    assert C.finding_class(finding) == "swallowed-error"
    # An unknown class name is not believed.
    setattr(finding, C.CLASS_ATTR, "made-up")
    assert C.finding_class(finding) == "doc-contradicts-code"


@pytest.mark.parametrize(
    ("claim", "want"),
    [
        (DOC, "doc-contradicts-code"),
        (TEST, "missing-control-test"),
        (SWALLOW, "swallowed-error"),
        ("The env var is not restored after the case.", "seam-not-restored"),
        ("The seam exception is attached as __context__.", "other"),
        ("Bsize is int32 on linux/386.", "other"),
    ],
)
def test_the_keyword_table(claim, want):
    assert C.classify(claim) == want


def test_a_new_record_rebuilds_the_cache(tmp_path):
    _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)] * 2)
    assert C.index(tmp_path)["cached"] is False
    assert C.index(tmp_path)["cached"] is True
    path = _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)])
    # The directory mtime moves with the rename; pin it forward in case the clock's granularity hid the move.
    st = os.stat(path.parent)
    os.utime(path.parent, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    again = C.index(tmp_path)
    assert again["cached"] is False
    assert len(C.brief_lines(again, ["a/**"])) == 1


def test_an_in_place_same_size_rewrite_rebuilds_the_fold(tmp_path):
    path = _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)] * 3)
    assert len(C.brief_lines(C.index(tmp_path), ["a/**"])) == 1
    assert C.index(tmp_path)["cached"] is True
    dir_st = os.stat(path.parent)
    file_st = os.stat(path)
    text = path.read_text(encoding="utf-8")
    assert text.count("Resolution: fixed ") == 3
    # Same byte length, so only the record's own mtime can tell; the directory mtime is put back.
    path.write_text(text.replace("Resolution: fixed ", "Resolution: fixeX "), encoding="utf-8")
    os.utime(path, ns=(file_st.st_atime_ns, file_st.st_mtime_ns + 10_000_000))
    os.utime(path.parent, ns=(dir_st.st_atime_ns, dir_st.st_mtime_ns))
    assert os.stat(path).st_size == file_st.st_size
    again = C.index(tmp_path)
    assert again["cached"] is False
    assert C.brief_lines(again, ["a/**"]) == []


def test_an_atime_only_change_keeps_the_cache(tmp_path):
    """A read moves the access time and nothing else, so the store's signature (size and mtime) holds."""
    path = _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)] * 3)
    C.index(tmp_path)
    assert C.index(tmp_path)["cached"] is True
    for target in (path, path.parent):
        st = os.stat(target)
        os.utime(target, ns=(st.st_atime_ns + 10_000_000, st.st_mtime_ns))
    assert C.index(tmp_path)["cached"] is True


def test_a_changed_parser_signature_invalidates_the_cache(tmp_path, monkeypatch):
    _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)] * 3)
    C.index(tmp_path)
    assert C.index(tmp_path)["cached"] is True
    monkeypatch.setattr(C, "parse_sig", lambda: [1, 2])
    assert C.index(tmp_path)["cached"] is False
    assert C.index(tmp_path)["cached"] is True


def test_a_corrupt_cache_is_rebuilt_and_named(tmp_path):
    _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)] * 3)
    cache = tmp_path / C.CACHE_REL
    cache.parent.mkdir(parents=True)
    cache.write_text("{not json", encoding="utf-8")
    notes: list[str] = []
    idx = C.index(tmp_path, notes=notes)
    assert idx["cached"] is False
    assert len(C.brief_lines(idx, ["a/**"])) == 1
    assert notes
    assert "unreadable" in notes[0]


def test_a_malformed_record_is_counted_not_fatal(tmp_path):
    _record(tmp_path, [("medium", "a/x.py", DOC, FIXED)] * 3)
    bad = tmp_path / R.REVIEWS_REL / BRANCH / ("b" * 40 + ".md")
    bad.write_text("# not a review\n", encoding="utf-8")
    idx = _fresh(tmp_path)
    assert idx["malformed"] == 1
    assert idx["records"] == 1
