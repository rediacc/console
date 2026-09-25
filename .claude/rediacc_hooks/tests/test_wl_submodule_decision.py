"""A KEEP or DROP the lead recorded in an open or leased item's note is a submodule decision (agent/plans/PLAN-stop-hook-retro-20260924.md R20260924.23).

On 2026-09-24 the same move, `private/account 9fda8c7c2 -> aea435154`, blocked at 15:58:03Z and again at 16:15:36Z, 17.5 minutes apart. Item #f2dd1732's note already said "account pointer 9fda8c7 -> aea4351 ...: KEEP", but `submodule_decision_recorded` accepted only a TICKED item carrying `sha[:9]`, so a decision in an open `[>]` item with a 7-character sha never matched and the check fell back to the 15-minute latch. The lead staged the gitlink only to silence it.

Every acceptance has a paired refusal: a note with no KEEP or DROP, a different sha, a sha prefix under 7 characters, and another session's item each stay undecided.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

TARGET = "aea435154"

DECIDED_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_checks as K
import wl_core as C
import wl_store as S
fold = S.load(C.worklist_for(sys.argv[2]), sync=False)
print(json.dumps(K.submodule_decision_recorded(
    sys.argv[2], "private/account", sys.argv[3], fold=fold, session_id=sys.argv[4]
)))
"""


def decided(fix, sha: str = TARGET, session_id: str = wlfix.SID) -> bool:
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            DECIDED_SNIPPET,
            str(wlfix.STOP_DIR),
            str(fix.proj),
            sha,
            session_id,
        ],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout)


def item(fix, text: str) -> str:
    got = fix.cli("--add", wlfix.ME, text)
    found = re.search(r"#([0-9a-f]+)", got.out)
    assert found, got.out[:300] + got.err[:300]
    return found.group(1)


def leased_with_note(fix, note: str) -> str:
    rid = item(fix, "(deadbeef) ride the account pointer through the babysitter")
    got = fix.cli("--lease", wlfix.ME, rid, "+60", "worker:lead", note)
    assert got.rc == 0, got.err[:400]
    return rid


def test_r23_a_keep_in_a_leased_items_note_is_a_decision(wl):  # noqa: F811
    """CONTROL: before R.23 only a ticked item carrying sha[:9] counted, so this was False."""
    leased_with_note(wl, "private/account 9fda8c7 -> aea4351: KEEP, the babysitter commits it")
    assert decided(wl) is True


def test_r23_a_drop_in_an_open_items_update_is_a_decision(wl):  # noqa: F811
    rid = item(wl, "(deadbeef) the account pointer")
    got = wl.cli("--update", wlfix.ME, rid, "DROP private/account aea43515, a peer's checkout")
    assert got.rc == 0, got.err[:400]
    assert decided(wl) is True


def test_r23_inverse_a_note_without_keep_or_drop_is_not_a_decision(wl):  # noqa: F811
    leased_with_note(wl, "private/account 9fda8c7 -> aea4351: looking at it")
    assert decided(wl) is False


def test_r23_inverse_a_different_sha_is_not_a_decision(wl):  # noqa: F811
    leased_with_note(wl, "private/account 9fda8c7 -> aea4351: KEEP")
    assert decided(wl, sha="bbbb12345") is False


def test_r23_inverse_a_short_sha_or_another_path_is_not_a_decision(wl):  # noqa: F811
    leased_with_note(wl, "private/account aea43: KEEP")
    assert decided(wl) is False, "a 5-character prefix"
    wl.setup()
    leased_with_note(wl, "private/renet 9fda8c7 -> aea4351: KEEP")
    assert decided(wl) is False, "another submodule's path"


def test_r23_inverse_another_sessions_item_is_not_this_sessions_decision(wl):  # noqa: F811
    leased_with_note(wl, "private/account 9fda8c7 -> aea4351: KEEP")
    assert decided(wl, session_id=wlfix.peer_id("cafef00d")) is False
