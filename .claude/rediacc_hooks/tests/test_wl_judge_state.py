"""The judge's view of finished work and its release-age rule (agent/plans/PLAN-stop-hook-effort.md box E5).

The judge is driven through `wl_judge.run_judge` with a canned `claude` on PATH that records the prompt it was handed and answers a planted verdict, so every case reads both what the judge was told and what the hook did with its answer.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import stat
import types

import pytest

from rediacc_hooks.tests import wlfix

J = wlfix.import_wl("wl_judge")
REPO = pathlib.Path(__file__).resolve().parents[3]
NOW = datetime.datetime(2026, 10, 14, 12, 0, tzinfo=datetime.UTC)


def stamp(hours_ago: float) -> str:
    return (NOW - datetime.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def rec(rid, state, owner, upd, text="", note=""):
    return {
        "id": rid,
        "state": state,
        "owner": owner,
        "text": text,
        "basetext": text,
        "lastnote": note,
        "upd": upd,
    }


@pytest.fixture
def judge(tmp_path, monkeypatch):
    """A canned judge: `answer(verdict, next_action)` plants the reply; `prompt()` reads what it was asked."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    seen = tmp_path / "prompt.txt"
    reply = tmp_path / "reply.json"
    script = bindir / "claude"
    script.write_text(
        '#!/bin/bash\nprintf "%%s" "$2" > %s\ncat %s\n' % (seen, reply), encoding="utf-8"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % bindir)
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    def answer(verdict, next_action):
        reply.write_text(
            json.dumps(
                {
                    "is_error": False,
                    "structured_output": {
                        "verdict": verdict,
                        "reason": "planted",
                        "next_action": next_action,
                    },
                }
            ),
            encoding="utf-8",
        )

    return types.SimpleNamespace(answer=answer, prompt=lambda: seen.read_text(encoding="utf-8"))


def ask(closed=None):
    return J.run_judge(
        ["[ ] (deadbeef) an unrelated open item"],
        0,
        "Fixed the flaky gate earlier; it said `fix the flaky gate` in the plan.",
        0,
        "none declared",
        with_riders=False,
        closed=closed,
    )


CLOSED = [("abc12345", "(deadbeef) fix the flaky gate", "commit:1234567 the gate exits 0")]


def test_closed_items_reads_state_owner_and_age():
    fold = types.SimpleNamespace(
        items=[
            rec("abc12345", "x", "deadbeef", stamp(1), "fix the gate", "commit:1234567 rc 0"),
            rec("old00000", "x", "deadbeef", stamp(30), "long ago", "done"),
            rec("open0000", " ", "deadbeef", stamp(1), "still open"),
            rec("peer0000", "x", "cafe1234", stamp(1), "a peer's"),
        ]
    )
    got = J.closed_items(fold, lambda o: o == "deadbeef", now=NOW)
    assert got == [("abc12345", "fix the gate", "commit:1234567 rc 0")]


def test_a_ticked_items_stale_add_text_is_not_re_raised(judge):
    """The message still talks about the work; the judge says continue and names the closed item. The prompt carries the item as DONE with its evidence, and the verdict is read as stop."""
    judge.answer("continue", "Fix the flaky gate (#abc12345) before stopping.")
    verdict, err = ask(CLOSED)
    assert err is None, err
    prompt = judge.prompt()
    assert "ALREADY DONE" in prompt
    assert "#abc12345 (deadbeef) fix the flaky gate" in prompt
    assert "closed with: commit:1234567 the gate exits 0" in prompt
    assert verdict["verdict"] == "stop", verdict
    assert "names closed item(s) #abc12345" in verdict["reason"]
    assert verdict["next_action"] == ""


def test_control_without_the_closed_rows_the_order_stands(judge):
    judge.answer("continue", "Fix the flaky gate (#abc12345) before stopping.")
    verdict, err = ask(None)
    assert err is None, err
    assert "ALREADY DONE" not in judge.prompt()
    assert verdict["verdict"] == "continue"


def test_control_an_order_naming_an_open_item_too_stands(judge):
    judge.answer("continue", "Finish #abc12345 and then #def67890.")
    verdict, _err = ask(CLOSED)
    assert verdict["verdict"] == "continue"


def test_a_pin_order_inside_the_release_age_soak_is_stripped(judge):
    judge.answer("continue", "apply the 8.7.0 pin now")
    verdict, err = ask(None)
    assert err is None, err
    assert verdict["verdict"] == "continue"  # the verdict is the judge's; only the order goes
    assert "release-age window" in verdict["next_action"]
    assert "1440 minutes" in verdict["next_action"]
    assert "'apply the 8.7.0 pin now'" in verdict["next_action"]


@pytest.mark.parametrize(
    "order",
    [
        "apply the 8.7.0 pin now",
        "bump vitest to 5.0.4 today",
        "Upgrade typescript-eslint to v8.71.2.",
        "pin zod 4.6.7 in package.json",
        "the 26.4.4 upgrade can land now",
    ],
)
def test_the_release_age_rule_matches_pin_orders(order):
    out = J.sanitize_next_action({"verdict": "continue", "next_action": order})
    assert out["next_action"].startswith("[rejected by the stop gate"), out


@pytest.mark.parametrize(
    "order",
    [
        "update the PR #600 body",
        "rerun the hook suite and read rc",
        "tick E3 with the commit sha",
        "apply the review fix to wl_judge.py",
    ],
)
def test_control_ordinary_orders_pass_the_release_age_rule(order):
    out = J.sanitize_next_action({"verdict": "continue", "next_action": order})
    assert out["next_action"] == order


def test_the_window_is_read_from_the_config():
    assert (
        J.release_age_minutes()
        == json.loads((REPO / J.RELEASE_AGE_REL).read_text(encoding="utf-8"))[
            "minimum_release_age_minutes"
        ]
    )
