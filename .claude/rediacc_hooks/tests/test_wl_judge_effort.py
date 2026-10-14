"""The stop-gate judge obeys the effort table (operator ruling 2026-10-14T09:27Z, agent/plans/PLAN-stop-hook-effort-tuning.md).

At effort smart `no-remaining` and `out-of-sync` advise and do not block, and the judge still blocked on exactly those demands. A `continue` now names its `basis`; one resting only on a report key that does not block at the level is read as stop and its order rides the advisory queue under that key. At high the same answer blocks.

Three layers: `settle_by_effort` alone, `run_judge` through a canned `claude` that records its argv (the prompt and the schema it was handed), and the real Stop hook.
"""

from __future__ import annotations

import json
import stat
import types

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import mk_sub, plant_lease

J = wlfix.import_wl("wl_judge")


@pytest.fixture
def wl(tmp_path):
    """One hook sandbox per test (wlfix.Fixture)."""
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


REPORT_ONLY = {
    "verdict": "continue",
    "reason": "The wait is real, but the message omits open items by id.",
    "next_action": "List every open item by id.",
    "basis": "out-of-sync",
}


# ---- settle_by_effort ---------------------------------------------------------------------------


def test_smart_reads_a_report_only_continue_as_stop_and_hands_back_the_order():
    got = J.settle_by_effort(dict(REPORT_ONLY), "smart")
    assert got["verdict"] == "stop", got
    assert got["next_action"] == ""
    assert "read as stop at effort smart" in got["reason"]
    [(key, text)] = got["effort_advised"]
    assert key == "out-of-sync"
    assert "omits open items by id" in text
    assert "List every open item by id." in text


@pytest.mark.parametrize("level", ["high", "ultra"])
def test_high_and_ultra_keep_the_block(level):
    got = J.settle_by_effort(dict(REPORT_ONLY), level)
    assert got["verdict"] == "continue", got
    assert "effort_advised" not in got


@pytest.mark.parametrize(
    ("label", "change"),
    [
        ("work basis", {"basis": "work"}),
        ("no basis", {"basis": None}),
        ("a stop", {"verdict": "stop"}),
    ],
)
def test_controls_that_stand_at_smart(label, change):
    answer = {**REPORT_ONLY, **change}
    got = J.settle_by_effort(answer, "smart")
    assert got["verdict"] == answer["verdict"], label
    assert "effort_advised" not in got, label


def test_the_table_decides_not_a_list_in_the_judge():
    """A planted table where out-of-sync blocks at smart keeps the continue: the threshold is read, not assumed."""
    table = {
        "checks": {
            "out-of-sync": {"block": "smart", "advise": "low"},
            "no-remaining": {"block": "high", "advise": "smart"},
        }
    }
    assert J.settle_by_effort(dict(REPORT_ONLY), "smart", table)["verdict"] == "continue"
    assert J.report_bases_quiet("smart", table) == ("no-remaining",)
    # A key the table does not list blocks (wl_effort's fail-closed rule), so it is never quiet.
    assert J.report_bases_quiet("smart", {"checks": {}}) == ()
    assert J.report_bases_quiet(None) == ()


# ---- run_judge through a canned claude ------------------------------------------------------------


@pytest.fixture
def judge(tmp_path, monkeypatch):
    """A canned `claude` that records its whole argv and answers `answer(...)`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    seen = tmp_path / "argv.json"
    reply = tmp_path / "reply.json"
    script = bindir / "claude"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        "open(%r, 'w').write(json.dumps(sys.argv[1:]))\n"
        "print(open(%r).read())\n" % (str(seen), str(reply)),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % bindir)
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    def answer(out):
        reply.write_text(json.dumps({"is_error": False, "structured_output": out}), "utf-8")

    def argv():
        got = json.loads(seen.read_text(encoding="utf-8"))
        return got[got.index("-p") + 1], json.loads(got[got.index("--json-schema") + 1])

    return types.SimpleNamespace(answer=answer, argv=argv)


def ask(level):
    return J.run_judge(
        ["[ ] (deadbeef) an open item"],
        0,
        "Waiting on the writer.",
        0,
        "none declared",
        with_riders=False,
        effort_level=level,
    )


def test_run_judge_at_smart_asks_the_basis_and_settles(judge):
    judge.answer(dict(REPORT_ONLY))
    verdict, err = ask("smart")
    assert err is None, err
    prompt, schema = judge.argv()
    assert "BASIS." in prompt
    assert "basis" in schema["required"]
    assert verdict["verdict"] == "stop", verdict
    assert verdict["effort_advised"][0][0] == "out-of-sync"


def test_run_judge_at_high_asks_no_basis_and_blocks(judge):
    judge.answer(dict(REPORT_ONLY))
    verdict, err = ask("high")
    assert err is None, err
    prompt, schema = judge.argv()
    assert "BASIS." not in prompt
    assert "basis" not in schema["required"]
    assert verdict["verdict"] == "continue", verdict


# ---- the real Stop hook ---------------------------------------------------------------------------


def one_writer_world(fix, level):
    """One live leased writer, nothing else open: the stop reaches the judge, which answers REPORT_ONLY."""
    fix.settings(effort=level)
    fix.brief_now()
    fix.hand_now()
    mk_sub(fix, "a1111111111111111", "general-purpose", 0)
    plant_lease(fix, "jw01", "a1111111111111111")
    script = fix.base / "binonly" / "claude"
    script.write_text(
        "#!/usr/bin/env python3\nprint(%r)\n"
        % json.dumps({"is_error": False, "structured_output": REPORT_ONLY}),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    fix.say("waiting on the writer\n\n## Remaining\n- the writer's item")


def queued(fix):
    path = fix.wl.with_suffix(".state-%s.json" % wlfix.ME)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {
        str(e.get("key")): str(e.get("text")) for e in (doc.get("outq") or {}).get("items") or []
    }


def test_the_stop_hook_at_smart_advises_instead_of_blocking(wl):
    one_writer_world(wl, "smart")
    got = wl.runj()
    assert "judge says continue" not in got.out, got.out[:800]
    shown = got.out + "".join(queued(wl).values())
    assert "advised at effort smart (out-of-sync" in shown, got.out[:800]


def test_the_stop_hook_at_high_blocks_on_the_same_answer(wl):
    one_writer_world(wl, "high")
    got = wl.runj()
    assert got.decision == "block", got.out[:800]
    assert "judge says continue" in got.out, got.out[:800]
