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


def plant_demand(fix, name: str, fields: dict, fired_ago_s: float) -> None:
    """A rule's demand marker exactly as `wl_rules.Demand.bank` writes it. The path is keyed on the hook's cwd, which is this process's cwd."""
    key = hashlib.sha1(os.getcwd().encode("utf-8", "replace")).hexdigest()[:12]
    path = fix.base / "tmp" / "claude-worklist" / ".judge" / ("%s-%s.json" % (name, key))
    path.parent.mkdir(parents=True, exist_ok=True)
    at = time.time() - fired_ago_s
    record = dict(fields, fires=1, at=at, first_at=at, owed=None)
    path.write_text(json.dumps(record), encoding="utf-8")


def plant_sweep_demand(fix, fired_ago_s: float, search: str = "") -> None:
    fields = dict(SWEEP_OUTSTANDING)
    if search:
        fields["search"] = search
    plant_demand(fix, "classsweep", fields, fired_ago_s)


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


# GROUNDED on purpose (R.19): the class names the fix-set's own file, so the fire still blocks. An ungrounded class is queued as the `sweep-ungrounded` advisory instead.
GROUNDED_CLASS = "hook timeout values in .claude/settings.json over the budget"


def timeout_fix_world(
    fix, search: str, defect_class: str = GROUNDED_CLASS, proof: dict | None = None
) -> None:
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
                "defect_class": defect_class,
                "locus": ".claude/settings.json",
                "search": search,
                "evidence": "",
                "evidence_kind": "none",
                "swept": False,
                "instruction": "count the other hook timeouts",
            },
            **({"proof_obligation": proof} if proof else {}),
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


# ---- R.18: the discharge reads what the lead actually ran (second retro, point #2) ---------------

EVIDENCED_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_classsweep as CS
import wl_proofcheck as PF
fn = CS.sweep_evidenced if sys.argv[4] == "sweep" else PF.proof_evidenced
print(json.dumps(fn(json.loads(sys.argv[2]), sys.argv[3])))
"""


def evidenced(fix, fields: dict, rule: str = "sweep") -> bool:
    at = time.time() - 600
    outstanding = dict(fields, fires=1, at=at, first_at=at)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            EVIDENCED_SNIPPET,
            str(wlfix.STOP_DIR),
            json.dumps(outstanding),
            str(fix.transcript),
            rule,
        ],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    return json.loads(proc.stdout)


ORACLE_DEMAND = {"defect_class": "x", "search": r"grep -r 'bash_results\|oracle' .ci/x/"}
FIND_DEMAND = {"defect_class": "x", "search": "find .ci/x -name '*d.py' -type f"}


def test_r18_a_near_literal_rerun_discharges_the_sweep(wl):  # noqa: F811
    """CONTROL, 16:10:39Z: the lead ran the same paths with a shared alternative, and the demand stayed owed for three more stops because the whole pattern was not a substring of the command."""
    plant_search_call(wl, r"grep -rln 'bash_results\|ORACLES\b' .ci/x/", 300)
    assert evidenced(wl, ORACLE_DEMAND) is True


def test_r18_a_find_demand_run_verbatim_discharges(wl):  # noqa: F811
    """CONTROL, 16:29:15Z: a `find` demand run verbatim was never discharged, because `search_pattern` read grep and rg only."""
    plant_search_call(wl, "find .ci/x -name '*d.py' -type f", 300)
    assert evidenced(wl, FIND_DEMAND) is True


def test_r18_inverse_a_shared_word_without_a_shared_path_stays_owed(wl):  # noqa: F811
    plant_search_call(wl, "grep -r 'oracle' docs/", 300)
    assert evidenced(wl, ORACLE_DEMAND) is False, "an alternative with no shared path discharged it"
    wl.setup()
    plant_search_call(wl, "grep -rn 'bash' .ci/x/", 300)
    assert evidenced(wl, ORACLE_DEMAND) is False, "a shared path with no 6-character alternative"
    wl.setup()
    plant_search_call(wl, "find .ci/x -name '*.ts'", 300)
    assert evidenced(wl, FIND_DEMAND) is False, "a different find glob discharged it"
    wl.setup()
    plant_search_call(wl, "find .ci/x -name '*d.py' -type f", 300, result=False)
    assert evidenced(wl, FIND_DEMAND) is False, "a find with no result discharged it"


PROOF_DEMAND = {"transform_kind": "reflow of comments", "scope": "packages/x comments"}


def test_r18_a_shape_cluster_diff_on_the_scope_discharges_the_proof(wl):  # noqa: F811
    """CONTROL: before R.18 a proof demand had no discharge at all; it rode 16:10:30, 16:23:57 and 16:29:10."""
    plant_search_call(
        wl, "python3 .ci/scripts/quality/shape_cluster_diff.py --rev HEAD packages/x", 300
    )
    assert evidenced(wl, PROOF_DEMAND, "proof") is True


def test_r18_inverse_a_proof_elsewhere_or_another_tool_stays_owed(wl):  # noqa: F811
    plant_search_call(wl, "python3 .ci/scripts/quality/shape_cluster_diff.py --rev HEAD docs/", 300)
    assert evidenced(wl, PROOF_DEMAND, "proof") is False, "a proof over another path"
    wl.setup()
    plant_search_call(wl, "git diff --stat HEAD packages/x", 300)
    assert evidenced(wl, PROOF_DEMAND, "proof") is False, "a diff stat is not a proof"
    wl.setup()
    plant_search_call(
        wl, "python3 .ci/scripts/quality/shape_cluster_diff.py --rev HEAD packages/x", 300, False
    )
    assert evidenced(wl, PROOF_DEMAND, "proof") is False, "a proof with no result"


def test_r18_the_real_stop_asks_no_proof_followup_the_transcript_answers(wl):  # noqa: F811
    """CONTROL for the wiring at wl_judge.run_judge: before R.18 `PF.load_outstanding()` was used raw, so the follow-up was asked whatever the transcript showed."""
    deferral_world(wl)
    plant_demand(wl, "proofcheck", PROOF_DEMAND, 600)
    plant_search_call(
        wl, "python3 .ci/scripts/quality/shape_cluster_diff.py --rev HEAD packages/x", 300
    )
    wl.say("answer\n\n## Remaining\n- the quarantine decision, deferred with its justification")
    wl.runj()
    assert PROOF_MARKER not in prompt_of(wl), "the proof follow-up was asked again"


def test_r18_adversarial_the_real_stop_still_follows_up_an_unrun_proof(wl):  # noqa: F811
    deferral_world(wl)
    plant_demand(wl, "proofcheck", PROOF_DEMAND, 600)
    wl.runj()
    assert PROOF_MARKER in prompt_of(wl), prompt_of(wl)[-1200:]


LONG_OWED = "grep -rn 'owed_" + "x" * 215 + "_tail' .claude/settings.json"


def test_r18_a_long_still_owed_search_is_shown_in_full(wl):  # noqa: F811
    """CONTROL, 16:13:17Z: the block read "STILL OWED: A bash orac"; the owed search sat at the end of `reason`, under apply_order's 400-character cap and still_owed_sentence's 160."""
    assert len(LONG_OWED) >= 250
    timeout_fix_world(wl, "grep -rn '\"timeout\"' .claude/settings.json")
    plant_sweep_demand(wl, 600, search=LONG_OWED)
    out = wl.runj().out
    assert '"decision": "block"' in out, out[:600]
    text = json.loads(out)["reason"]
    line = next((ln for ln in text.splitlines() if "STILL OWED (run to discharge)" in ln), "")
    assert LONG_OWED in line, text[-1500:]


def test_r18_adversarial_a_dropped_owed_search_is_never_handed_over(wl):  # noqa: F811
    """A demand is banked whatever its search validated to, so the STILL OWED line must not re-emit a search `enforce` dropped: the line that carries it is now outside every cap and every filter on `next_action`."""
    timeout_fix_world(wl, "grep -rn '\"timeout\"' .claude/settings.json")
    plant_sweep_demand(wl, 600, search="git clean -xdf .claude/")
    out = wl.runj().out
    text = json.loads(out)["reason"]
    assert "STILL OWED (run to discharge)" in text, text[-1500:]
    assert "git clean" not in text, text[-1500:]


# ---- R.19: a gitlink's own files, and an ungrounded fire is advisory ----------------------------

FIXSET_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_reggate as R
print(json.dumps(R.fixset_files(sys.argv[2], json.loads(sys.argv[3]))))
"""


def fixset(fix, ids: list[str]) -> tuple[list[str], str]:
    proc = subprocess.run(
        [sys.executable, "-c", FIXSET_SNIPPET, str(wlfix.STOP_DIR), str(fix.proj), json.dumps(ids)],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    files, provenance = json.loads(proc.stdout)
    return files, provenance


def gitlink_world(fix) -> object:
    """A parent repo carrying `sub` as a gitlink (no .gitmodules needed), then a `sub` commit adding tests/a.test.ts."""
    fix.reg_repo()
    sub = fix.proj / "sub"
    sub.mkdir()
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@t"),
        ("config", "user.name", "t"),
    ):
        subprocess.run(["git", *args], cwd=str(sub), check=True, capture_output=True)
    (sub / "src.ts").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(sub), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=str(sub), check=True, capture_output=True)
    fix.git("add", "sub")
    fix.git("commit", "-qm", "chore: add sub")
    (sub / "tests").mkdir()
    (sub / "tests" / "a.test.ts").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(sub), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "test"], cwd=str(sub), check=True, capture_output=True)
    return sub


def test_r19_a_moved_gitlink_lists_the_submodule_files(wl):  # noqa: F811
    """CONTROL, 16:23:57Z: "no test files appear in this fix-set" while the tests sat in private/account commit aea435154; the fix-set listed only the gitlink path."""
    gitlink_world(wl)
    files, _how = fixset(wl, ["tickid01"])
    assert "sub/tests/a.test.ts" in files, files
    wl.git("add", "sub")
    wl.git("commit", "-qm", "fix: bump sub")
    sha = wl.git("rev-parse", "HEAD").stdout.strip()
    files, how = fixset(wl, [sha])
    assert how == "diff-tree", how
    assert "sub/tests/a.test.ts" in files, files


def test_r19_inverse_an_unmoved_gitlink_adds_nothing(wl):  # noqa: F811
    gitlink_world(wl)
    wl.git("add", "sub")
    wl.git("commit", "-qm", "fix: bump sub")
    (wl.proj / "base.txt").write_text("changed\n", encoding="utf-8")
    files, _how = fixset(wl, ["tickid01"])
    assert files == ["base.txt"], files


UNGROUNDED_TEXT = "queued here instead of blocking"


def queued_keys(fix) -> list[str]:
    path = fix.stem(".state-deadbeef.json")
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [str(e.get("key")) for e in (doc.get("outq") or {}).get("items") or []]


def advised(fix, got) -> bool:
    """The `sweep-ungrounded` advisory reached the session: still queued, or drained into this stop's allow report."""
    return UNGROUNDED_TEXT in got.out or any(
        k.startswith("sweep-ungrounded") for k in queued_keys(fix)
    )


def test_r19_an_ungrounded_sweep_fire_is_an_advisory(wl):  # noqa: F811
    """CONTROL, 15:49:19Z and 16:10:30Z: the block's own text said UNVERIFIED and it blocked anyway."""
    timeout_fix_world(
        wl, "grep -rn '\"timeout\"' .claude/settings.json", "hook timeout values over the budget"
    )
    got = wl.runj()
    assert got.decision != "block", got.out[:800]
    assert advised(wl, got), got.out[-1500:]


def test_r19_an_ungrounded_proof_fire_is_an_advisory(wl):  # noqa: F811
    proof = {
        "applicable": True,
        "transform_kind": "a reflow",
        "scope": "packages/nowhere",
        "proof_kind": "none",
        "evidence": "",
        "proof_attached": False,
        "instruction": "run a structural diff",
    }
    timeout_fix_world(wl, "grep -rn '\"timeout\"' .claude/settings.json", proof=proof)
    got = wl.runj()
    assert got.decision == "block", got.out[:600]
    assert "PROOF OBLIGATION" not in json.loads(got.out)["reason"], got.out[-1200:]
    assert advised(wl, got), queued_keys(wl)


def test_r19_inverse_a_grounded_fire_still_blocks(wl):  # noqa: F811
    timeout_fix_world(wl, "grep -rn '\"timeout\"' .claude/settings.json")
    got = wl.runj()
    assert got.decision == "block", got.out[:600]
    assert SWEEP_MARKER in got.out, got.out[-1200:]
    assert not advised(wl, got), queued_keys(wl)


# ---- R20260925.3: a covering `find` glob discharges the sweep (agent/plans/PLAN-stop-hook-retro-20260925.md section 2) ----

BASELINE_DEMAND = {
    "defect_class": "shrink-only baselines",
    "search": "find .ci/config .ci/rediacc_ci -name '*-baseline.json' -type f",
}
BASELINE_COVER = "find .ci/config .ci/rediacc_ci scripts/data -name '*baseline*.json' -type f"


def test_r25_3_a_covering_find_glob_with_a_shared_path_discharges(wl):  # noqa: F811
    """CONTROL, 19:50:04 marker against the 19:50:12 command: a superset of the glob and the paths, and the demand stayed owed because `near_literal` needs the demand's glob as a substring."""
    plant_search_call(wl, BASELINE_COVER, 300)
    assert evidenced(wl, BASELINE_DEMAND) is True


def test_r25_3_inverse_a_narrower_glob_stays_owed(wl):  # noqa: F811
    plant_search_call(wl, "find .ci/config .ci/rediacc_ci -name 'ci-baseline.json' -type f", 300)
    assert evidenced(wl, BASELINE_DEMAND) is False, "a narrower glob discharged it"


def test_r25_3_inverse_a_covering_glob_with_no_shared_path_stays_owed(wl):  # noqa: F811
    plant_search_call(wl, "find scripts/data -name '*baseline*.json' -type f", 300)
    assert evidenced(wl, BASELINE_DEMAND) is False, "a covering glob over other paths discharged it"


def test_r25_3_inverse_a_case_sensitive_cover_of_an_iname_demand_stays_owed(wl):  # noqa: F811
    demand = dict(BASELINE_DEMAND, search=BASELINE_DEMAND["search"].replace("-name", "-iname"))
    plant_search_call(wl, BASELINE_COVER, 300)
    assert evidenced(wl, demand) is False, "-name does not cover an -iname demand"
    wl.setup()
    plant_search_call(wl, BASELINE_COVER.replace("-name", "-iname"), 300)
    assert evidenced(wl, demand) is True, "an -iname cover of an -iname demand"


# ---- R20260925.4: shape_cluster_diff's JSON key-path mode discharges the locale proof --------------

SHAPE_TOOL = wlfix.STOP_DIR.parents[2] / ".ci" / "scripts" / "quality" / "shape_cluster_diff.py"
LOCALES = "packages/cli/src/i18n/locales"
LOCALE_PROOF_DEMAND = {
    "transform_kind": "Automatic translation key regeneration across 16 locales",
    "scope": "packages/cli/src/i18n/locales/",
}
LOCALE_PROOF_CMD = ".ci/scripts/quality/shape_cluster_diff.py --rev HEAD " + LOCALES


def run_shape_tool_on_locales(fix) -> subprocess.CompletedProcess:
    """The real tool in a throwaway repo: one committed locale file, then a working-tree edit adding a key."""
    repo = fix.base / "locrepo"
    loc = repo / LOCALES / "de" / "cli.json"
    loc.parent.mkdir(parents=True, exist_ok=True)
    loc.write_text(json.dumps({"commands": {"up": "Hoch"}}, indent=2), encoding="utf-8")
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(git + argv, cwd=repo, check=True, capture_output=True)
    loc.write_text(
        json.dumps({"commands": {"up": "Hoch", "down": "Runter"}}, indent=2), encoding="utf-8"
    )
    return subprocess.run(
        [sys.executable, str(SHAPE_TOOL), "--rev", "HEAD", LOCALES],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_r25_4_the_ordered_proof_is_a_key_diff_and_discharges_the_locale_demand(wl):  # noqa: F811
    """CONTROL: the judge ordered `shape_cluster_diff` on the locales, a tool that shaped JSON as prose lines. It now reports key paths, and the ordered command discharges the demand through the unwidened PROOF_TOOL_RE."""
    ran = run_shape_tool_on_locales(wl)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "added commands.down" in ran.stdout, ran.stdout
    plant_search_call(wl, LOCALE_PROOF_CMD, 300)
    assert evidenced(wl, LOCALE_PROOF_DEMAND, "proof") is True


def test_r25_4_inverse_a_hand_rolled_key_diff_or_another_scope_stays_owed(wl):  # noqa: F811
    """PROOF_TOOL_RE stays narrow: the lead's own key diff at 19:44:02 is not the proof tool, and the tool over another tree is not the scope."""
    plant_search_call(
        wl, "python3 -c 'import json; print(\"unexpected 0\")' " + LOCALES + "/de/cli.json", 300
    )
    assert evidenced(wl, LOCALE_PROOF_DEMAND, "proof") is False, "a hand-rolled key diff"
    wl.setup()
    plant_search_call(wl, LOCALE_PROOF_CMD.replace("packages/cli", "packages/www"), 300)
    assert evidenced(wl, LOCALE_PROOF_DEMAND, "proof") is False, "the tool over another tree"
