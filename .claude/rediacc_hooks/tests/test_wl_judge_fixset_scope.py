"""The judge's sweep and proof questions are scoped to the lead's own fix (agent/plans/PLAN-stop-hook-retro-20260924.md R.1 to R.3).

On 2026-09-24 six of ten judge blocks demanded a class sweep or a proof for work a live writer still had in flight, or for a change that was not the lead's. Three defects combined: a tick-based fix-set is the whole dirty tree (R.1), a sweep the session really ran two turns earlier was invisible to a FOLLOWUP that reads only the last message (R.2), and a search that cannot match the fixed instance was handed over as the order anyway (R.3).

THE JUDGE IS ADVERSARIAL MACHINERY, so every narrowing here has a paired case proving a genuine demand still fires: the lead's own dirty file is still in the fix-set, a finished writer's edit is still the lead's to account for, a search that never ran still leaves the demand, and a search that matches the fix is still handed over.

Every case drives the real hook (or the real `run_judge`) through `wlfix`, with a stub `claude` that records the prompt it was given.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import mk_sub, plant_lease, subagents_dir
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

PROOF_MARKER = "PROOF OBLIGATION: DID THE BULK TRANSFORM PROVE ITSELF"
SWEEP_MARKER = "SWEEP THE CLASS, NOT THE INSTANCE"
FOLLOWUP_OPENING = "An earlier stop this session was told"
WRITER = "a3000000000000001"

PKG_REAL_GATE = (
    '{"name":"p","version":"0.0.0","scripts":'
    '{"ci":"npm run check:ci-real","check:ci-real":"true"}}\n'
)


def iso(seconds_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - seconds_ago))


def capturing_judge(fix, structured_output: dict) -> None:
    """A stub `claude` that writes the prompt it receives (argv[2]) to `prompt.txt`, then serves `structured_output`."""
    payload = json.dumps({"is_error": False, "structured_output": structured_output})
    script = fix.base / "binonly" / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "open(%r, 'w').write(sys.argv[2])\n"
        "print(%r)\n" % (str(fix.base / "prompt.txt"), payload),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def prompt_of(fix) -> str:
    path = fix.base / "prompt.txt"
    assert path.is_file(), "the judge was never called"
    return path.read_text(encoding="utf-8")


def regression_gate(**fields) -> dict:
    gate = {
        "applicable": False,
        "blind_spot": "",
        "existing_gate": "",
        "recurring": False,
        "gate_needed": False,
        "gate_proven": False,
        "instruction": "none",
    }
    gate.update(fields)
    return gate


def add_edit(fix, aid: str, rel: str) -> None:
    """Insert an Edit of `rel` into the agent's transcript, before its final record, keeping its mtime."""
    tx = subagents_dir(fix) / ("agent-%s.jsonl" % aid)
    st = tx.stat()
    edit = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_edit",
                    "name": "Edit",
                    "input": {
                        "file_path": str(fix.proj / rel),
                        "old_string": "a",
                        "new_string": "b",
                    },
                }
            ]
        },
    }
    lines = tx.read_text(encoding="utf-8").splitlines(keepends=True)
    tx.write_text("".join(lines[:-1]) + json.dumps(edit) + "\n" + lines[-1], encoding="utf-8")
    os.utime(tx, (st.st_atime, st.st_mtime))


def tick_world(fix, writer_live: bool, lead_file: str = "") -> None:
    """A fixture repo whose tracked `packages/x/a.ts` is modified by a writer agent, plus a tick of the lead's that touches code.

    `writer_live` decides whether that writer is still running (mid-turn in a tool call, listed by the event) or has finished (turn ended, not listed). `lead_file` adds a second dirty file nobody but the lead edited.
    """
    fix.say("done for now\n\n## Remaining\n- #wr01 rides the writer")
    fix.brief_now()
    fix.hand_now()
    fix.reg_repo()
    (fix.proj / "package.json").write_text(PKG_REAL_GATE, encoding="utf-8")
    for rel in ("packages/x/a.ts", "packages/x/b.ts"):
        (fix.proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (fix.proj / rel).write_text("one\n", encoding="utf-8")
    fix.git("add", "-A")
    fix.git("commit", "-qm", "chore: seed")
    fix.run()  # initialises the regression-gate marker at this HEAD
    (fix.proj / "packages/x/a.ts").write_text("two\n", encoding="utf-8")
    if lead_file:
        (fix.proj / lead_file).write_text("two\n", encoding="utf-8")
    if writer_live:
        mk_sub(fix, WRITER, "general-purpose", 1, last="tool_use")
    else:
        mk_sub(fix, WRITER, "general-purpose", 30, last="end_turn", running=False)
    add_edit(fix, WRITER, "packages/x/a.ts")
    if writer_live:
        plant_lease(fix, "wr01", WRITER)
    sha = fix.git("rev-parse", "--short", "HEAD").stdout.strip()
    fix.add_item("- [x] (deadbeef) fixed the parser in packages/x/a.ts, %s" % sha)
    capturing_judge(
        fix,
        {
            "verdict": "stop",
            "reason": "ok",
            "next_action": "none",
            "regression_gate": regression_gate(),
        },
    )


def fixset_block(prompt: str) -> str:
    return prompt.split("ACTUAL FILES THIS FIX-SET TOUCHED", 1)[1].split("The class_sweep", 1)[0]


# ---- R.1: a live writer's edits are not the lead's fix-set ------------------------------------


def test_r1_a_live_writers_edit_asks_no_sweep_or_proof(wl):  # noqa: F811
    """CONTROL: before R.1 the whole dirty tree, the writer's in-flight edit included, was the fix-set, and the proof and sweep questions were asked about it."""
    tick_world(wl, writer_live=True)
    wl.runj()
    prompt = prompt_of(wl)
    assert PROOF_MARKER not in prompt, "a proof was asked about a live writer's edit"
    assert SWEEP_MARKER not in prompt, "a sweep was asked about a live writer's edit"


def test_r1_inverse_a_finished_writers_edit_is_still_in_the_fixset(wl):  # noqa: F811
    """A finished writer's edit has landed, so it is the lead's to account for: the questions are still asked."""
    tick_world(wl, writer_live=False)
    wl.runj()
    prompt = prompt_of(wl)
    assert PROOF_MARKER in prompt, prompt[-1500:]
    assert "packages/x/a.ts" in fixset_block(prompt), fixset_block(prompt)


def test_r1_adversarial_the_leads_own_dirty_file_still_draws_the_questions(wl):  # noqa: F811
    """The narrowing subtracts ONLY the live writer's paths: a file the lead changed itself keeps the sweep and proof questions, and is the one listed."""
    tick_world(wl, writer_live=True, lead_file="packages/x/b.ts")
    wl.runj()
    prompt = prompt_of(wl)
    assert PROOF_MARKER in prompt, prompt[-1500:]
    assert SWEEP_MARKER in prompt, prompt[-1500:]
    listed = fixset_block(prompt)
    assert "packages/x/b.ts" in listed, listed
    assert "packages/x/a.ts" not in listed, listed


# ---- R.2: a sweep the transcript already shows discharges the demand ----------------------------

SWEEP_OUTSTANDING = {
    "defect_class": "hook timeout values drifted from the budget",
    "search": "grep -r 'post-tool' .claude/settings.json",
}


def plant_sweep_demand(fix, fired_ago_s: float) -> None:
    """The class-sweep marker exactly as `wl_rules.Demand.bank` writes it. The path is keyed on the hook's cwd, which is this process's cwd."""
    key = hashlib.sha1(os.getcwd().encode("utf-8", "replace")).hexdigest()[:12]
    path = fix.base / "tmp" / "claude-worklist" / ".judge" / ("classsweep-%s.json" % key)
    path.parent.mkdir(parents=True, exist_ok=True)
    at = time.time() - fired_ago_s
    record = dict(SWEEP_OUTSTANDING, fires=1, at=at, first_at=at, owed=None)
    path.write_text(json.dumps(record), encoding="utf-8")


def plant_search_call(fix, command: str, seconds_ago: float, result: bool = True) -> None:
    fix.append_transcript(
        {
            "type": "assistant",
            "timestamp": iso(seconds_ago),
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_sweep",
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ]
            },
        }
    )
    if result:
        fix.append_transcript(
            {
                "type": "user",
                "timestamp": iso(seconds_ago - 1),
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "tu_sweep", "content": "3 matches"}
                    ]
                },
            }
        )


PROMPT_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_classsweep as CS
out = json.loads(sys.argv[2])
print(json.dumps(CS.prompt_section(False, out, sys.argv[3])))
"""


def prompt_section(fix, outstanding: dict) -> str:
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            PROMPT_SNIPPET,
            str(wlfix.STOP_DIR),
            json.dumps(outstanding),
            str(fix.transcript),
        ],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    return json.loads(proc.stdout)


def test_r2_a_search_already_run_in_the_transcript_discharges_the_followup(wl):  # noqa: F811
    """CONTROL: before R.2 the FOLLOWUP was asked again, whatever the transcript showed."""
    outstanding = dict(SWEEP_OUTSTANDING, fires=1, at=time.time() - 600, first_at=time.time() - 600)
    plant_search_call(wl, "grep -rn 'post-tool' .claude/settings.json | wc -l", 300)
    assert prompt_section(wl, outstanding) == ""


def test_r2_inverse_a_search_before_the_demand_or_without_a_result_keeps_it(wl):  # noqa: F811
    outstanding = dict(SWEEP_OUTSTANDING, fires=1, at=time.time() - 600, first_at=time.time() - 600)
    plant_search_call(wl, "grep -rn 'post-tool' .claude/settings.json", 900)
    assert FOLLOWUP_OPENING in prompt_section(wl, outstanding), (
        "a search older than the demand discharged it"
    )
    wl.setup()
    plant_search_call(wl, "grep -rn 'post-tool' .claude/settings.json", 300, result=False)
    assert FOLLOWUP_OPENING in prompt_section(wl, outstanding), (
        "a search with no result discharged it"
    )
    wl.setup()
    plant_search_call(wl, "grep -rn 'something-else' .claude/settings.json", 300)
    assert FOLLOWUP_OPENING in prompt_section(wl, outstanding), "an unrelated search discharged it"


def deferral_world(fix) -> None:
    """A stop on which the judge runs with no fix signal: a deferred item of the lead's and a Remaining section."""
    fix.brief_now()
    fix.hand_now()
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": "ffff3331",
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600)),
                    "by": "deadbeef",
                    "s": "?",
                    "o": "deadbeef",
                    "t": "quarantine the flaky leg? DEFAULT: quarantine it WHY: only the operator "
                    "can accept the coverage loss HOW: operator approves the quarantine",
                }
            )
            + "\n"
        )
    fix.say("answer\n\n## Remaining\n- the quarantine decision, deferred with its justification")
    capturing_judge(fix, {"verdict": "stop", "reason": "ok", "next_action": "none"})


def test_r2_the_real_stop_asks_no_followup_the_transcript_answers(wl):  # noqa: F811
    deferral_world(wl)
    plant_sweep_demand(wl, 600)
    plant_search_call(wl, "grep -rn 'post-tool' .claude/settings.json", 300)
    wl.say("answer\n\n## Remaining\n- the quarantine decision, deferred with its justification")
    wl.runj()
    assert SWEEP_MARKER not in prompt_of(wl), "the sweep follow-up was asked again"


def test_r2_adversarial_the_real_stop_still_follows_up_an_unrun_search(wl):  # noqa: F811
    deferral_world(wl)
    plant_sweep_demand(wl, 600)
    wl.runj()
    assert FOLLOWUP_OPENING in prompt_of(wl), prompt_of(wl)[-1200:]


# ---- R.3: the judge's search must find the fixed instance ----------------------------------------

SETTINGS_BEFORE = '{\n  "hooks": {\n    "timeout": 135\n  }\n}\n'
SETTINGS_AFTER = '{\n  "hooks": {\n    "timeout": 75\n  }\n}\n'


def timeout_fix_world(fix, search: str) -> None:
    fix.say("done for now")
    fix.brief_now()
    fix.reg_repo()
    (fix.proj / "package.json").write_text(PKG_REAL_GATE, encoding="utf-8")
    (fix.proj / ".claude").mkdir(parents=True, exist_ok=True)
    (fix.proj / ".claude" / "settings.json").write_text(SETTINGS_BEFORE, encoding="utf-8")
    fix.git("add", "-A")
    fix.git("commit", "-qm", "chore: seed")
    fix.run()
    (fix.proj / ".claude" / "settings.json").write_text(SETTINGS_AFTER, encoding="utf-8")
    fix.git("add", "-A")
    fix.git("commit", "-qm", "fix(hooks): the post-tool hook timeout fits the budget")
    capturing_judge(
        fix,
        {
            "verdict": "stop",
            "reason": "ok",
            "next_action": "none",
            "regression_gate": regression_gate(),
            "class_sweep": {
                "applicable": True,
                "defect_class": "hook timeout values over the budget",
                "locus": ".claude/settings.json",
                "search": search,
                "evidence": "",
                "evidence_kind": "none",
                "swept": False,
                "instruction": "count the other hook timeouts",
            },
        },
    )


def test_r3_a_search_that_misses_the_fixed_instance_is_replaced(wl):  # noqa: F811
    """CONTROL: before R.3 the block handed over `Run: grep -r 'post-tool' ...`, a search the fix's own diff never matches."""
    timeout_fix_world(wl, "grep -r 'post-tool' .claude/settings.json")
    out = wl.runj().out
    assert '"decision": "block"' in out, out[:600]
    assert "does not match the fix's own changed lines" in out, out[-1200:]
    assert "Run: grep -r 'post-tool'" not in out, out[-1200:]


def test_r3_inverse_a_search_that_finds_the_fixed_instance_is_kept(wl):  # noqa: F811
    timeout_fix_world(wl, "grep -rn '\"timeout\"' .claude/settings.json")
    out = wl.runj().out
    assert '"decision": "block"' in out, out[:600]
    assert "Run: grep -rn" in out, out[-1200:]
    assert "does not match the fix's own changed lines" not in out, out[-1200:]
