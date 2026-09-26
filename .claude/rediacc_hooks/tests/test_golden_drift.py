"""The golden-drift control (PLAN-retire-bash-oracles A2): a golden may not change from what HEAD already committed without saying why.

WHY THIS AND NOT A DIFF REVIEW. Nothing else in this suite reads git history; every other control here compares two LIVE answers. This one instead compares TIME -- the golden a commit already carries against the copy on disk right now -- so a change that landed silently (a hand-edit, a `regolden.py` run with a copy-pasted reason, a script that touched the file directly) is caught by WHAT moved rather than by trusting whoever moved it. Every deliberate change already carries `intentional: <reason>` (`regolden.py`, via `goldenio.diff_and_mark` or its own per-record comparison), which is what makes "already carries one" the question worth asking rather than trusting the diff by eye.

KEPT DELIBERATELY SMALL. PLAN-retire-bash-oracles routes this control's design through the lead's review rather than trusting a sonnet writer's judgement on it outright, so `_undeclared_drift` is the WHOLE decision, in one function, testable with no git repository at all: a key answers the same or it does not, and if it does not, its CURRENT record must carry `intentional`. Everything else here is plumbing -- reading two snapshots and handing them to it.

A NEW GOLDEN IS NOT A DRIFT. A key with no answer in the OLD snapshot is new, not changed, exactly as `goldenio.diff_and_mark` already treats it when writing one (see that function's own docstring: "the freeze is the starting point, not the spec"). The two have to agree, or a first freeze would need markers it should never carry.
"""

from __future__ import annotations

import json
import subprocess

from rediacc_hooks.tests import goldenio, guardcorpus

ROOT = guardcorpus.repo_root()
GOLDEN_FILES = sorted(goldenio.GOLDEN_DIR.glob("*.jsonl"))


def _canonical(silent, records):
    """One comparable value per case key, `intentional` stripped.

    That field records WHY a change happened, not WHAT the answer is, so two records differing only in their reason string are not a drift -- and a record's OWN presence in `records` rather than `silent` is itself part of what is compared, since a case moving from silent to a real answer (or back) is exactly the kind of change this control exists to catch.
    """
    view: dict[str, tuple] = dict.fromkeys(silent, ("__silent__",))
    for key, row in records.items():
        view[key] = tuple(sorted((k, v) for k, v in row.items() if k != "intentional"))
    return view


def _undeclared_drift(old_silent, old_records, new_silent, new_records):
    """Every case key whose answer changed between two snapshots without the NEW side carrying `intentional`."""
    old_view = _canonical(old_silent, old_records)
    new_view = _canonical(new_silent, new_records)
    bad = []
    for key, value in new_view.items():
        old_value = old_view.get(key)
        if old_value is None or old_value == value:
            continue
        if "intentional" not in new_records.get(key, {}):
            bad.append(key)
    return sorted(bad)


def test_the_drift_control_can_fail():
    """A control that has never been shown to fire is not evidence, the same anti-vacuity rule `test_the_differential_can_fail` applies to the bash comparison itself."""
    old_silent, old_records = {"a"}, {"b": {"rc": "0", "out": "x", "err": ""}}
    # An undeclared change: "b"'s answer moves and nothing says why.
    undeclared = {"b": {"rc": "0", "out": "y", "err": ""}}
    assert _undeclared_drift(old_silent, old_records, set(), undeclared) == ["b"]
    # The SAME change, declared: the control goes quiet.
    declared = {"b": {"rc": "0", "out": "y", "err": "", "intentional": "Rule T fix"}}
    assert _undeclared_drift(old_silent, old_records, set(), declared) == []
    # A brand new key, absent from the old snapshot, is not a drift.
    fresh = dict(old_records, c={"rc": "0", "out": "z", "err": ""})
    assert _undeclared_drift(old_silent, old_records, set(), fresh) == []
    # A silent case moving to a real answer IS a drift: the answer changed, even though no OLD record existed to diff against textually.
    assert _undeclared_drift({"a"}, {}, set(), {"a": {"rc": "2", "out": "", "err": "blocked"}}) == [
        "a"
    ]
    # An answer that moved AND stopped being silent, both undeclared, is still exactly one offending key -- not double-counted, not missed.
    assert _undeclared_drift(
        {"a"},
        {"b": {"rc": "0", "out": "x", "err": ""}},
        set(),
        {"a": {"rc": "2", "out": "", "err": "no"}, "b": {"rc": "0", "out": "x", "err": ""}},
    ) == ["a"]


def _head_snapshot(path):
    """`(silent, records)` from HEAD's own committed copy of `path`, or `None` when HEAD has no such file yet (a first freeze, not a drift)."""
    rel = path.relative_to(ROOT).as_posix()
    proc = subprocess.run(
        ["git", "show", "HEAD:%s" % rel], cwd=str(ROOT), capture_output=True, check=False
    )
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", "surrogateescape")
    _header, silent, records = goldenio.parse_golden_lines(text.splitlines())
    return silent, records


def test_every_golden_is_reachable():
    """ANTI-VACUITY: this file must actually see the goldens A1 froze, or every case below is a no-op."""
    assert GOLDEN_FILES, "no golden files found under %s" % goldenio.GOLDEN_DIR


def test_golden_drift_is_always_intentional():
    """Every golden that HEAD already carries: nothing may have moved since without a reason."""
    offenders = {}
    for path in GOLDEN_FILES:
        head = _head_snapshot(path)
        if head is None:
            continue
        old_silent, old_records = head
        _header, new_silent, new_records = goldenio.read_golden(path)
        bad = _undeclared_drift(old_silent, old_records, new_silent, new_records)
        if bad:
            offenders[path.name] = bad
    assert not offenders, (
        "these golden records changed since HEAD with no `intentional` reason recorded on "
        "them -- regolden.py always tags a real change, so an untagged one was written some "
        "other way: %s" % json.dumps(offenders, sort_keys=True)
    )
