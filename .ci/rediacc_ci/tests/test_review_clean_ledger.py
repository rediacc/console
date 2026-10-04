"""`rediacc_ci.review.clean_ledger`: the CI-side reader of `agent/reviews/<branch>/clean.jsonl` (agent/plans/PLAN-clean-review-ledger.md T9).

THE CONTRACT CASE is the reason this file exists: CI cannot import the writer, so the two readers of one format could drift apart unseen. Every line here is written by the writer's own `wl_review.ledger_line` (or `append_clean`), and the CI reader must hand back the same fields.
"""

import json
import pathlib
from typing import Any

from rediacc_ci import paths
from rediacc_ci.review import clean_ledger as C

paths.on_sys_path(paths.hooks_stop_dir())
import wl_review  # noqa: E402

BRANCH = "1004-1"


def review(n: int, verdict: str = "clean", **kw) -> "wl_review.Review":
    fields: dict[str, Any] = {
        "sha": ("%x" % n) * 40,
        "subject": "fix: commit %d, été" % n,
        "branch": BRANCH,
        "parent": "b" * 40,
        "patch_id": "c" * 40,
        "reviewed_at": "2026-10-04T08:00:%02dZ" % n,
        "model": "m",
        "diff_bytes": 100 + n,
        "diff_files": n,
        "verdict": verdict,
        "labels": {"bump": "minor", "kind": ["feature"], "why": "adds a verb"}
        if verdict == "clean"
        else None,
        "cost": {"usd": 0.0123, "calls": 1, "seconds": 12.3},
    }
    fields.update(kw)
    return wl_review.Review(**fields)


def test_contract_lines_the_writer_writes_read_back_identically(tmp_path):
    reviews = [
        review(1),
        review(2, "skipped (gitlink-only)", model="(none)", cost=None),
        review(3, "skipped (no-review)", model="(none)", cost=None),
        review(4, labels=None),
    ]
    for r in reviews:
        assert wl_review.append_clean(tmp_path, BRANCH, r)
    path = wl_review.ledger_path(tmp_path, BRANCH)
    assert path.name == C.NAME
    got = C.read(path)
    assert [d["line"] for d in got] == [1, 2, 3, 4]
    for r, doc in zip(reviews, got, strict=True):
        want = wl_review.ledger_doc(r)
        assert {k: v for k, v in doc.items() if k != "line"} == want
    # The writer's strict reader agrees with the CI reader on the same file.
    strict, errors = wl_review.read_ledger(path)
    assert errors == []
    assert [r.sha for r in strict] == [d["sha"] for d in got]
    assert C.verdict_of(got[0]) == {"bump": "minor", "kind": ["feature"], "why": "adds a verb"}
    assert C.verdict_of(got[1]) is None
    assert C.verdict_of(got[3]) is None
    assert C.labels_text(got[0]) == "bump=minor kind=feature why=adds a verb"
    assert C.labels_text(got[3]) == "(none)"


def test_a_garbled_line_is_skipped_and_the_rest_are_read(tmp_path):
    good = wl_review.ledger_line(review(1))
    other = json.loads(wl_review.ledger_line(review(2)))
    other["verdict"] = "findings"
    path = tmp_path / C.NAME
    path.write_text(
        good + "{torn\n" + json.dumps(other) + "\n" + wl_review.ledger_line(review(3)),
        encoding="utf-8",
    )
    got = C.read(path)
    assert [(d["sha"][0], d["line"]) for d in got] == [("1", 1), ("3", 4)]


def test_a_duplicate_sha_keeps_its_first_line(tmp_path):
    first = wl_review.ledger_line(review(1))
    second = wl_review.ledger_line(review(1, subject="again"))
    path = tmp_path / C.NAME
    path.write_text(first + second, encoding="utf-8")
    got = C.read(path)
    assert len(got) == 1
    assert got[0]["line"] == 1


def test_a_missing_ledger_reads_as_empty(tmp_path):
    assert C.read(pathlib.Path(tmp_path) / "nope" / C.NAME) == []
