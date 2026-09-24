"""Three more evidence shapes `--tick` accepts, and a log of every refusal (agent/plans/PLAN-stop-hook-retro-20260924.md R.8).

On 2026-09-24, 22 of 94 tick calls were refused. Four spelled the exit code `rc=0`, about eight quoted an operator `/ask` answer by its time, and about eight cited a real file by its bare basename. Each shape is checked, not trusted: a basename must name exactly one tracked file, and `ASKED:<minute>` must match an AskUserQuestion result in the lead's own transcript. The paired inverse keeps "done, works" refused.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import subagents_dir
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

EVIDENCE_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_checks as K
print(json.dumps(K.completion_evidence(sys.argv[2], sys.argv[3])))
"""


def evidence(fix, text: str) -> bool:
    proc = subprocess.run(
        [sys.executable, "-c", EVIDENCE_SNIPPET, str(wlfix.STOP_DIR), str(fix.proj), text],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    return json.loads(proc.stdout)


def tracked_files(fix) -> None:
    fix.reg_repo()
    for rel in ("pkg/unique_guard.py", "x/dup_name.py", "y/dup_name.py"):
        (fix.proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (fix.proj / rel).write_text("one\ntwo\nthree\n", encoding="utf-8")
    fix.git("add", "-A")
    fix.git("commit", "-qm", "chore: files")


def test_r8_rc_equals_is_an_exit_code(wl):  # noqa: F811
    """CONTROL: before R.8 `rc=0` was not evidence."""
    assert evidence(wl, "87 cases rc=0") is True
    assert evidence(wl, "87 cases, rc 0") is True


def test_r8_a_unique_basename_citation_resolves(wl):  # noqa: F811
    """CONTROL: before R.8 a bare basename never resolved."""
    tracked_files(wl)
    assert evidence(wl, "fixed in unique_guard.py:2") is True


def test_r8_inverse_ambiguous_or_out_of_range_basenames_do_not_resolve(wl):  # noqa: F811
    tracked_files(wl)
    assert evidence(wl, "fixed in dup_name.py:2") is False
    assert evidence(wl, "fixed in unique_guard.py:40") is False


def test_r8_inverse_a_bare_claim_is_still_refused(wl):  # noqa: F811
    tracked_files(wl)
    assert evidence(wl, "done, works") is False


# ---- ASKED:<minute>, through the real --tick verb ----------------------------------------------


def lead_transcript(fix):
    path = subagents_dir(fix).parent.with_suffix(".jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    fix.env["CLAUDE_CONFIG_DIR"] = str(fix.base / "claude")
    return path


def plant_ask(fix, answered_at: str) -> None:
    records = [
        {
            "type": "assistant",
            "timestamp": answered_at,
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tu_ask", "name": "AskUserQuestion", "input": {}}
                ]
            },
        },
        {
            "type": "user",
            "timestamp": answered_at,
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_ask", "content": "Quarantine it"}
                ]
            },
        },
    ]
    with lead_transcript(fix).open("a", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in records))


def added(fix) -> str:
    got = fix.cli("--add", wlfix.ME, "(deadbeef) the quarantine decision")
    found = re.search(r"#([0-9a-f]+)", got.out)
    assert found, got.out[:200]
    return found.group(1)


def test_r8_asked_passes_against_a_real_answer(wl):  # noqa: F811
    """CONTROL: before R.8 an operator answer quoted by its time was refused."""
    minute = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() - 3600))
    answered = time.strftime("%Y-%m-%dT%H:%M:40.000Z", time.gmtime(time.time() - 3600))
    plant_ask(wl, answered)
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "operator ruled: quarantine it, ASKED:%s" % minute)
    assert got.rc == 0, got.err[:400]


def test_r8_inverse_asked_without_an_answer_is_refused_and_logged(wl):  # noqa: F811
    lead_transcript(wl).write_text("", encoding="utf-8")
    minute = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() - 3600))
    item = added(wl)
    got = wl.cli("--tick", wlfix.ME, item, "operator ruled: quarantine it, ASKED:%s" % minute)
    assert got.rc != 0, got.out[:300]
    log = wl.stem(".tick-refusals-deadbeef.jsonl")
    assert log.is_file(), "the refusal was not logged"
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert row["id"] == item, row
    assert row["why"] == "no-evidence", row
