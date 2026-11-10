"""The reviewer's history line and finding class (agent/plans/PLAN-experience-feedback.md P6, box B6).

Controls first, each the half that must stay SILENT or unchanged: an old record (no `Class:` line) parses and renders byte-identically, a file with no history adds no prior line, and a schema answer without `class` is refused. Then the firing half: a record with a `Class:` line round-trips, the prior line names the fixed and refuted counts and the top class, and the schema's class list is the A1 index's.
"""

from __future__ import annotations

import pathlib

import pytest

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")
C = wlfix.import_wl("wl_reviewclass")

AT = "2026-11-10T00:00:00Z"
SHA = "ab" * 20


def _review(klass=""):
    return R.Review(
        sha=SHA,
        subject="s",
        branch="1110-1",
        reviewed_at=AT,
        model="m",
        verdict="findings",
        findings=[
            R.Finding(
                id=SHA[:8] + ".1",
                severity="high",
                file="f.py",
                line=3,
                anchor="in-diff",
                claim="the branch has no test",
                resolution="open",
                klass=klass,
            )
        ],
    )


def _without_class(text):
    return "".join(ln for ln in text.splitlines(True) if not ln.startswith("Class: "))


def test_an_old_record_parses_and_renders_byte_identically():
    old = _without_class(R.render(_review("missing-control-test")))
    assert "Class: " not in old
    parsed = R.parse(old)
    assert parsed.findings[0].klass == ""
    assert R.render(parsed) == old


def test_a_record_with_a_class_round_trips_between_claim_and_resolution():
    text = R.render(_review("missing-control-test"))
    lines = text.splitlines()
    i = lines.index("Class: missing-control-test")
    assert lines[i - 1].startswith("Claim: ")
    assert lines[i + 1].startswith("Resolution: ")
    parsed = R.parse(text)
    assert parsed.findings[0].klass == "missing-control-test"
    assert R.render(parsed) == text
    # The class is not part of body_sig: the same findings sign the same with or without it.
    assert parsed.body_sig == R.body_sig(_review("").findings)


def test_an_unknown_class_in_a_record_is_malformed():
    text = R.render(_review("missing-control-test")).replace(
        "Class: missing-control-test", "Class: made-up"
    )
    with pytest.raises(R.MalformedReviewError, match="Class"):
        R.parse(text)


def test_the_schema_class_enum_is_the_a1_class_list_ending_in_other():
    item = R.SCHEMA["properties"]["findings"]["items"]
    assert "class" in item["required"]
    enum = tuple(item["properties"]["class"]["enum"])
    assert set(enum) == set(C.CLASS_NAMES)
    assert enum[-1] == "other"


def test_a_schema_answer_without_class_is_refused_and_one_with_it_is_kept():
    diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1,2 +1,3 @@\n x\n+y\n z\n"
    base = {"severity": "high", "file": "f.py", "line": 2, "claim": "no test covers this"}
    answer = {"verdict": "findings", "labels": None}
    _v, kept, _l, dropped = R.validate({**answer, "findings": [base]}, {"f.py"}, diff, SHA)
    assert (kept, dropped) == ([], 1)
    _v, kept, _l, dropped = R.validate(
        {**answer, "findings": [{**base, "class": "nonsense"}]}, {"f.py"}, diff, SHA
    )
    assert (kept, dropped) == ([], 1)
    _v, kept, _l, dropped = R.validate(
        {**answer, "findings": [{**base, "class": "missing-control-test"}]}, {"f.py"}, diff, SHA
    )
    assert dropped == 0
    assert kept[0].klass == "missing-control-test"


IDX = {
    "files": {
        "a.py": {"fixed": {"swallowed-error": 3, "other": 1}, "refuted": {"other": 2}},
        "b.py": {"fixed": {}, "refuted": {"other": 1}},
    }
}


def test_a_file_with_no_history_adds_no_prior_line(tmp_path):
    assert R.prior_lines(IDX, ["never-reviewed.py"]) == []
    assert R.prior_text(tmp_path, ["never-reviewed.py"], log=lambda *_: None) == ""
    prompt = R.PROMPT % {
        "prior": "",
        "message": "m",
        "stat": "s",
        "truncated": "(none)",
        "diff": "d",
    }
    assert "Prior on this file:" not in prompt


def test_a_file_with_history_gets_one_short_line_with_counts_and_top_class():
    lines = R.prior_lines(IDX, ["b.py", "a.py", "never.py"])
    assert lines == [
        "Prior on this file: a.py: 4 fixed, 2 refuted, top class swallowed-error.",
        "Prior on this file: b.py: 0 fixed, 1 refuted.",
    ]


def test_the_prior_block_is_capped():
    idx = {"files": {"f%d.py" % n: {"fixed": {"other": 1}, "refuted": {}} for n in range(20)}}
    assert len(R.prior_lines(idx, list(idx["files"]))) == R.PRIOR_MAX_FILES


def test_every_historical_record_survives_the_new_parser_byte_identically():
    root = pathlib.Path(__file__).resolve().parents[3]
    paths = sorted((root / "agent" / "reviews").glob("*/*.md"))[:300]
    if not paths:
        pytest.skip("no review records in this tree")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        review, err = R.read_review(path)
        assert err is None, "%s: %s" % (path, err)
        assert R.render(review) == text, path.name
