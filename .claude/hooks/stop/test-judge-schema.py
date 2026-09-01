#!/usr/bin/env python3
"""Controls for wl_judge: which objects the judge MUST return, and the class-sweep rule.

Two rules live here. The first is judge_schema_for's marker contract; the second is
wl_classsweep, the "sweep the class, not the instance" rule, whose controls start at
PART 2 and carry their own argument.

Why this exists. The fix-signal is a separate prompt section (M.REGGATE_PROMPT, appended
as `extra`), while v7 deliberately shipped ONE schema in which `regression_gate` is
optional at the top level. Those two facts together let the model satisfy the schema while
omitting the object, after which wl_reggate reports

    regression_gate missing or incomplete: None

and the stop hook blocks by the no-escape-hatch rule. The block is correct; what is wrong
is that the session is blocked by a JUDGE error rather than by anything it did. Observed
live on 2026-08-28, on a turn whose fix was already gated.

Every control is a PAIR, because asserting that the signal makes the field required proves
nothing on its own: a builder that always required it would pass that half and would break
every ordinary stop. The paired assertion is that WITHOUT the signal it stays optional.

The third pair is the one that matters most and is easiest to get wrong: the builder must
not mutate the module-level JUDGE_SCHEMA. A dict returned by reference would make the
first fix-signal stop poison every later call in the same process.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wl_bravedefault
import wl_classsweep
import wl_core
import wl_judge


class Tally:
    """A counter object rather than module globals: ruff's PLW0603 is right that a
    `global` statement here buys nothing, and the sibling test files already use this
    shape."""

    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got == want:
        return
    Tally.fails += 1
    print(f"  FAIL {label}: got {got!r}, want {want!r}", file=sys.stderr)


SIGNAL = "\n\nA FIX LANDED THIS TURN, so ALSO fill the `regression_gate` object.\n"

plain = wl_judge.judge_schema_for("")
signalled = wl_judge.judge_schema_for(SIGNAL)

# 1. The pair: required only when the prompt actually asks for it.
control(
    "no fix-signal leaves regression_gate optional", "regression_gate" in plain["required"], False
)
control(
    "a fix-signal makes regression_gate required", "regression_gate" in signalled["required"], True
)

# 2. Nothing else about the schema may drift, or a passing judge call starts failing
#    for reasons that have nothing to do with this switch.
control(
    "the base fields stay required", plain["required"][:3], ["verdict", "reason", "next_action"]
)
control(
    "the signalled schema keeps them too",
    signalled["required"][:3],
    ["verdict", "reason", "next_action"],
)

# 3. THE MUTATION PAIR. Ask for the signalled schema first, then the plain one: if the
#    builder handed back the module constant and appended to it, the plain schema would
#    now carry regression_gate and every ordinary stop would fail closed.
wl_judge.judge_schema_for(SIGNAL)
control(
    "the module constant is not mutated",
    "regression_gate" in wl_judge.JUDGE_SCHEMA["required"],
    False,
)
control(
    "a later plain call is unaffected",
    "regression_gate" in wl_judge.judge_schema_for("")["required"],
    False,
)

# 4. The marker is matched as a substring of a larger prompt, which is how it arrives.
control(
    "the signal is found inside surrounding prompt text",
    "regression_gate" in wl_judge.judge_schema_for("preamble\n" + SIGNAL + "\ntrailer")["required"],
    True,
)
control(
    "CONTROL: unrelated prompt text does not trip it",
    "regression_gate"
    in wl_judge.judge_schema_for("a fix landed, lowercase and different")["required"],
    False,
)


# ===========================================================================
# PART 2 -- wl_classsweep: "sweep the class, not the instance".
#
# WHY THESE CONTROLS. The rule's whole job is to fire on a message that claims
# ONE site fixed and offers no evidence anyone looked for the others. A rule
# that cannot fire is worse than no rule, so every case below is a PAIR: the
# planted defect that must fire, and the honest message that must stay silent.
#
# WHAT CANNOT BE CONTROLLED HERE, said plainly. The judgement itself is made by
# haiku, and this suite runs offline with no model call. So these controls pin
# the SEAM, not the model's taste: given a judge answer, does the machinery
# fire, stay silent, and produce an actionable order? Whether haiku returns
# `applicable: true` for a genuine class is calibrated by the opt-in live
# harness `calibrate-class-sweep.py`, which costs money and needs a network,
# and is therefore not wired into `npm run ci`.
# ===========================================================================

FIXSIG = "\n\n%s, so ALSO fill the `regression_gate` object.\n" % wl_judge._REGGATE_MARKER

# The marker is a real file; keep every control out of the developer's own
# outstanding-demand state, which is keyed by TMPDIR and cwd.
_TMP = tempfile.TemporaryDirectory()
os.environ["TMPDIR"] = _TMP.name
MARKER = pathlib.Path(_TMP.name) / "sweep-marker.json"


def fires(path):
    """The banked fire count, or None. Read defensively so a rule that stopped
    firing altogether reports a clean FAIL instead of a traceback -- the first
    mutation run against these controls crashed here rather than failing."""
    try:
        return json.loads(path.read_text())["fires"]
    except (OSError, ValueError, KeyError):
        return None


def answer(**kw):
    """A judge verdict carrying a class_sweep object, defaults to the fired shape."""
    cs = {
        "applicable": True,
        "defect_class": "a guard that greps a script name without anchoring it to argv[0]",
        "locus": ".claude/hooks/pre-bash/",
        "search": "grep -rln 'block-' .claude/hooks/pre-bash/",
        "evidence": "",
        "evidence_kind": "none",
        "swept": False,
        "instruction": "grep the sibling guards and fix every one",
    }
    cs.update(kw)
    return {"verdict": "stop", "reason": "the board is clean", "next_action": "", "class_sweep": cs}


# -- 2a. The schema pair, exactly as for regression_gate ---------------------
sweep_sig = wl_classsweep.SWEEP_PROMPT
control(
    "no sweep section leaves class_sweep optional",
    "class_sweep" in wl_judge.judge_schema_for("")["required"],
    False,
)
control(
    "the sweep section makes class_sweep required",
    "class_sweep" in wl_judge.judge_schema_for(sweep_sig)["required"],
    True,
)
# The two markers are INDEPENDENT: the sweep section is also appended on a
# carried-forward demand, on a stop with no fix signal at all. A builder that
# collapsed them into one boolean would require regression_gate on that stop
# and fail the judge closed for a question nobody asked.
both = wl_judge.judge_schema_for(FIXSIG + sweep_sig)
control(
    "both markers require both objects",
    sorted(both["required"][3:]),
    ["class_sweep", "regression_gate"],
)
control(
    "the sweep section alone does NOT require regression_gate",
    "regression_gate" in wl_judge.judge_schema_for(sweep_sig)["required"],
    False,
)
control(
    "the module constant survives the sweep marker too",
    "class_sweep" in wl_judge.JUDGE_SCHEMA["required"],
    False,
)
control(
    "class_sweep is still declared as a property",
    wl_judge.JUDGE_SCHEMA["properties"]["class_sweep"]["required"][0],
    "applicable",
)

# -- 2b. THE PLANTED DEFECT. A fix claimed at one site, no class evidence. ---
out = answer()
kind, _note = wl_classsweep.apply_verdict(out, path=MARKER)
control("PLANTED: an unswept class fires", kind, "fire")
control("PLANTED: the stop is flipped to continue", out["verdict"], "continue")
control(
    "PLANTED: the reason names the class",
    "anchoring it to argv[0]" in out["reason"],
    True,
)
control(
    "PLANTED: the order carries the actual search command",
    out["next_action"].startswith("Run: grep -rln 'block-'"),
    True,
)
control("PLANTED: the demand is banked for the next stop", MARKER.exists(), True)
control("PLANTED: banked at one fire", fires(MARKER), 1)

# -- 2c. THE SILENT PAIR. Evidence of a sweep, and a genuine one-off. --------
out = answer(swept=True, evidence_kind="scan", evidence="grep found 4 scripts; all four fixed")
kind, _note = wl_classsweep.apply_verdict(out, path=MARKER)
control("CONTROL: a scan with its count is silent", kind, "silent")
control("CONTROL: the verdict is left alone", out["verdict"], "stop")
control("CONTROL: a silent answer discharges the banked demand", MARKER.exists(), False)

out = answer(swept=True, evidence_kind="gate", evidence="the new gate fails for every sibling")
control(
    "CONTROL: a gate covering the class is silent",
    wl_classsweep.apply_verdict(out, path=MARKER)[0],
    "silent",
)
out = answer(swept=True, evidence_kind="statement", evidence="grepped; this is the only instance")
control(
    "CONTROL: an explicit searched-and-unique statement is silent",
    wl_classsweep.apply_verdict(out, path=MARKER)[0],
    "silent",
)

out = answer(applicable=False, defect_class="", search="", instruction="")
kind, _note = wl_classsweep.apply_verdict(out, path=MARKER)
control("CONTROL: a genuine one-off never fires", kind, "silent")
control("CONTROL: the one-off keeps its stop", out["verdict"], "stop")

# -- 2d. THE ASSERTION CASE, which is the point of the whole rule. ----------
# "I swept the class" with nothing quotable behind it is exactly the failure
# the operator described. The code overrides the model's own summary here.
out = answer(swept=True, evidence_kind="none")
kind, _note = wl_classsweep.apply_verdict(out, path=MARKER)
control("a bare `swept` assertion with no evidence still fires", kind, "fire")
control("and the reason says the sweep was only asserted", "asserted" in out["reason"], True)
wl_classsweep.clear_outstanding(MARKER)

# -- 2e. DEGRADED, never blocked. ------------------------------------------
out = {"verdict": "stop", "reason": "clean", "next_action": ""}
kind, note = wl_classsweep.apply_verdict(out, path=MARKER)
control("a missing class_sweep degrades", kind, "degraded")
control("a degraded answer never flips the verdict", out["verdict"], "stop")
control("and it says what was missing", "no class_sweep object" in note, True)

out = answer(defect_class="")
kind, note = wl_classsweep.apply_verdict(out, path=MARKER)
control("firing with no class named is unactionable, so it degrades", kind, "degraded")
control("an unactionable answer never blocks", out["verdict"], "stop")

out = answer(evidence_kind="whatever")
control(
    "an invalid evidence_kind degrades",
    wl_classsweep.apply_verdict(out, path=MARKER)[0],
    "degraded",
)

# A fire with no search still fires -- the class is named, so the order is
# actionable even without the command. This is the boundary between 'degraded'
# and 'fire' and it is easy to get backwards.
out = answer(search="")
kind, _note = wl_classsweep.apply_verdict(out, path=MARKER)
control("a fire with no search command still fires", kind, "fire")
control(
    "and falls back to a generic sweep order",
    out["next_action"].startswith("Grep for siblings"),
    True,
)
wl_classsweep.clear_outstanding(MARKER)

# -- 2e2. THE JUDGE'S OWN COMMAND IS VALIDATED, and both real misfires. -----
# Both strings below were handed to a live session on consecutive stops and
# both were unrunnable; the first printed grep's error line, which the session
# read as a finding. The demand must survive validation failing -- dropping the
# block would turn a bad command into an escape hatch.
BAD_PATH = "grep -rn 'export.*worker' packages/workers/ --include='*.ts' | wc -l"
TRUNCATED = (
    "find workers -type f \\( -name '*.ts' -o -name '*.tsx' \\) | xargs -I {} sh -c 'grep -q {"
)

ok, why = wl_classsweep.validate_search(BAD_PATH)
control("REAL MISFIRE: a command naming a directory that does not exist is rejected", ok, False)
control("and the reason names the path", "packages/workers" in why, True)

ok, why = wl_classsweep.validate_search(TRUNCATED)
control("REAL MISFIRE: a command truncated mid-token is rejected", ok, False)
control("and the reason says it does not parse", "does not parse" in why, True)

control(
    "a command at the schema cap is treated as truncated",
    wl_classsweep.validate_search("grep -rn x .claude/" + "a" * 300)[0],
    False,
)
control(
    "CONTROL: a command over a directory that DOES exist passes",
    wl_classsweep.validate_search("grep -rln 'block-' .claude/hooks/pre-bash/"),
    (True, ""),
)
control(
    "CONTROL: a quoted regex containing a slash is not mistaken for a path",
    wl_classsweep.validate_search("grep -rn 'error/TS' .claude/hooks/")[0],
    True,
)
control(
    "CONTROL: a glob names a set, so it is not existence-checked",
    wl_classsweep.validate_search("ls .claude/hooks/stop/wl_*.py")[0],
    True,
)

# The whole point: a rejected command must NOT weaken the block.
out = answer(search=BAD_PATH)
kind, _note = wl_classsweep.apply_verdict(out, path=MARKER)
control("a rejected command still FIRES", kind, "fire")
control("and still flips the stop to continue", out["verdict"], "continue")
control(
    "the bogus command is not handed over as `Run:`",
    out["next_action"].startswith("Run:"),
    False,
)
control(
    "the session is told why it was dropped",
    "does not exist in this repo" in out["next_action"],
    True,
)
control(
    "and the class is still named in the reason",
    "argv[0]" in out["reason"],
    True,
)
# wl_rules.apply_order caps next_action at 200 characters. The first draft of the
# dropped-command order ran to exactly 200 and was cut mid-word, so the session
# was handed a sentence that stopped at "or say plainly it is t". Pin the fit.
control(
    "the dropped-command order fits inside the 200-char next_action cap",
    len(out["next_action"]) < 200 and out["next_action"].endswith("instance."),
    True,
)
wl_classsweep.clear_outstanding(MARKER)

# -- 2f. The carried-forward demand, and its hard cap. ---------------------
# Without this the demand is one-shot: wl_reggate settles the fix-set on the
# same stop, so the next stop carries no fix signal and would never ask again.
first = answer()
wl_classsweep.apply_verdict(first, path=MARKER)
carried = wl_classsweep.load_outstanding(MARKER)
control("the demand is readable on the next stop", bool(carried), True)
control(
    "the follow-up prompt repeats the class",
    "argv[0]" in wl_classsweep.prompt_section(False, carried),
    True,
)
control(
    "a NEW fix signal outranks the carried demand",
    wl_classsweep.prompt_section(True, carried) == wl_classsweep.SWEEP_PROMPT,
    True,
)
control(
    "nothing to ask means no prompt section at all", wl_classsweep.prompt_section(False, None), ""
)

second = answer()
wl_classsweep.apply_verdict(second, carried, path=MARKER)
control("the second fire is counted", fires(MARKER), 2)
control(
    "THE CAP: a demand at the cap is never carried a third time",
    wl_classsweep.load_outstanding(MARKER),
    None,
)
MARKER.write_text(json.dumps({"defect_class": "x", "search": "y", "fires": 1, "at": 0}))
control("THE TTL: an ancient demand is not carried", wl_classsweep.load_outstanding(MARKER), None)
MARKER.write_text("{not json")
control("a corrupt marker is not carried", wl_classsweep.load_outstanding(MARKER), None)
wl_classsweep.clear_outstanding(MARKER)

# ---------------------------------------------------------------------------
# PART 3 -- end to end through run_judge, with the model call stubbed.
#
# The seam is subprocess: wl_judge shells out to `claude -p`. Replacing that ONE
# attribute exercises everything else for real -- prompt assembly, the schema
# built from the assembled prompt, the verdict flip, and the operator-only
# sanitiser that runs after it.
# ---------------------------------------------------------------------------

CAPTURED = {}


class FakeProc:
    returncode = 0
    stderr = ""

    def __init__(self, stdout):
        self.stdout = stdout


def fake_run(cmd, **_kw):
    CAPTURED["prompt"] = cmd[cmd.index("-p") + 1]
    CAPTURED["schema"] = json.loads(cmd[cmd.index("--json-schema") + 1])
    return FakeProc(json.dumps({"is_error": False, "structured_output": CAPTURED["answer"]}))


wl_judge.subprocess = types.SimpleNamespace(
    run=fake_run,
    TimeoutExpired=subprocess.TimeoutExpired,
    DEVNULL=subprocess.DEVNULL,
)
wl_judge.resolve_claude = lambda: "/bin/sh"


def judged(extra, ans, remaining=None):
    CAPTURED["answer"] = ans
    verdict, err = wl_judge.run_judge(
        remaining or [], 0, "a message", 0, "none declared", extra=extra
    )
    control("run_judge returned no error for %s" % (extra[:20] or "(plain)"), err, None)
    return verdict


# 3a. A fix stop: the section is in the prompt, the field is in the schema, and
#     the planted answer turns the stop into a block.
v = judged(FIXSIG, answer())
control(
    "the fix signal puts the rubric in the prompt",
    wl_classsweep.SWEEP_MARKER in CAPTURED["prompt"],
    True,
)
control(
    "and class_sweep into the schema it is asked against",
    "class_sweep" in CAPTURED["schema"]["required"],
    True,
)
control("END TO END: the planted defect blocks the stop", v["verdict"], "continue")
control("END TO END: with the search in the order", "grep -rln" in v["next_action"], True)

# 3b. THE PAIR. An ordinary stop must be byte-identical to what it was before
#     this rule existed -- no section, no field, no interference.
wl_classsweep.clear_outstanding()
v = judged("", {"verdict": "stop", "reason": "clean board", "next_action": ""})
control(
    "CONTROL: an ordinary stop is not asked at all",
    wl_classsweep.SWEEP_MARKER in CAPTURED["prompt"],
    False,
)
control(
    "CONTROL: and class_sweep is not required of it",
    "class_sweep" in CAPTURED["schema"]["required"],
    False,
)
control("CONTROL: its verdict passes through untouched", v["verdict"], "stop")
control("CONTROL: and its reason is not annotated", v["reason"], "clean board")

# 3c. A fix stop whose message DID show the sweep keeps its stop.
v = judged(FIXSIG, answer(swept=True, evidence_kind="scan", evidence="4 found, 4 fixed"))
control("CONTROL: end to end, a swept class still stops", v["verdict"], "stop")

# 3d. A fix stop where the model omitted the object: reported, never blocked.
v = judged(FIXSIG, {"verdict": "stop", "reason": "clean", "next_action": ""})
control("a missing object does not block the stop", v["verdict"], "stop")
control("but it is visible in the reason", "class-sweep not judged" in v["reason"], True)

# 3e. ORDERING. The search command is the MODEL's text, so it must pass through
#     the operator-only sanitiser like any other next_action. A rule that wrote
#     next_action after sanitize_next_action would hand the session an order
#     this judge is forbidden to give.
wl_classsweep.clear_outstanding()
v = judged(FIXSIG, answer(search="gh pr merge 563 && grep -rn foo ."))
control(
    "the sweep order is still sanitised",
    v["next_action"].startswith("[rejected by the stop gate:"),
    True,
)
control("and the class survives in the reason", "argv[0]" in v["reason"], True)
wl_classsweep.clear_outstanding()


# ===========================================================================
# PART 4 -- wl_bravedefault: "a DEFAULT that does nothing is not a DEFAULT".
#
# Same discipline as PART 2: every case is a pair. The planted defect is a
# deferral that defaults to the status quo; the controls beside it are a
# default that commits to an action, and a hold that is genuinely justified by
# irreversibility. Holding is sometimes right, so a rule that rejected every
# hold would be wrong, not strict.
#
# The judgement is still haiku's; these controls pin the seam.
# ===========================================================================

BMARKER = pathlib.Path(_TMP.name) / "brave-marker.json"

TIMID_LINE = "[?] - [?] (ab12) ship the regenerated teasers?  DEFAULT: hold and report the numbers."
BRAVE_LINE = "[?] - [?] (cd34) which branch?  DEFAULT: land it on the open PR."
OPEN_LINE = "[ ] - [ ] (ab12) wire the gate into ci-quality.yml"


def bd_answer(**kw):
    """A judge verdict carrying a brave_default object, defaults to the fired shape."""
    bd = {
        "applicable": True,
        "quote": "ship the regenerated teasers?",
        "default_text": "hold and report the numbers",
        "changes_state": False,
        "hold_reason": "preference",
        "braver": "publish the regenerated teasers and say what changed",
        "instruction": "rewrite the default as the action you would take alone",
    }
    bd.update(kw)
    return {
        "verdict": "stop",
        "reason": "the board is clean",
        "next_action": "",
        "brave_default": bd,
    }


# -- 4a. The trigger, and what it deliberately ignores. ---------------------
control(
    "a [?] carrying a DEFAULT is asked about",
    wl_bravedefault.has_deferral_with_default([TIMID_LINE]),
    True,
)
control(
    "CONTROL: an ordinary open item is not a deferral",
    wl_bravedefault.has_deferral_with_default([OPEN_LINE]),
    False,
)
control(
    "CONTROL: a [?] with no DEFAULT at all is somebody else's gate",
    wl_bravedefault.has_deferral_with_default(["[?] - [?] (ab12) ship the teasers?"]),
    False,
)
control(
    "CONTROL: nothing remaining asks nothing", wl_bravedefault.has_deferral_with_default([]), False
)
control("no trigger means no prompt section", wl_bravedefault.prompt_section([OPEN_LINE]), "")
# The trigger token is the program's ONE copy, not a second spelling of it. A
# re-typed regex would drift from wl_core's the day either changes -- the exact
# defect the sibling rule in this same file exists to catch.
control(
    "the DEFAULT token is the shared one, not a copy",
    wl_bravedefault.DEFAULT_TOKEN is wl_core.DEFAULT_TOKEN,
    True,
)
control(
    "and it agrees with wl_core on a bare `DEFAULT:` with nothing after it",
    wl_bravedefault.has_deferral_with_default(["[?] - [?] (ab12) ship it? DEFAULT:"]),
    False,
)
control(
    "the trigger puts the rubric in the prompt",
    wl_bravedefault.BRAVE_MARKER in wl_bravedefault.prompt_section([TIMID_LINE]),
    True,
)

# -- 4b. The schema pair. --------------------------------------------------
brave_sig = wl_bravedefault.BRAVE_PROMPT
control(
    "no brave section leaves brave_default optional",
    "brave_default" in wl_judge.judge_schema_for("")["required"],
    False,
)
control(
    "the brave section makes brave_default required",
    "brave_default" in wl_judge.judge_schema_for(brave_sig)["required"],
    True,
)
control(
    "the three markers stay independent",
    sorted(wl_judge.judge_schema_for(FIXSIG + sweep_sig + brave_sig)["required"][3:]),
    ["brave_default", "class_sweep", "regression_gate"],
)
control(
    "the brave section alone requires neither of the others",
    [
        k
        for k in ("class_sweep", "regression_gate")
        if k in wl_judge.judge_schema_for(brave_sig)["required"]
    ],
    [],
)
control(
    "the module constant is still not mutated",
    "brave_default" in wl_judge.JUDGE_SCHEMA["required"],
    False,
)

# -- 4c. THE PLANTED DEFECT: a default that describes the status quo. ------
out = bd_answer()
kind, _note = wl_bravedefault.apply_verdict(out, path=BMARKER)
control("PLANTED: a no-op default fires", kind, "fire")
control("PLANTED: the stop is flipped to continue", out["verdict"], "continue")
control("PLANTED: the reason quotes the deferral", "regenerated teasers" in out["reason"], True)
control("PLANTED: and quotes the timid default", "hold and report" in out["reason"], True)
control(
    "PLANTED: the order carries the braver form",
    out["next_action"].startswith(
        "Rewrite that deferral's DEFAULT as the action you would take alone: publish"
    ),
    True,
)
wl_bravedefault.BRAVE_DEMAND.clear(BMARKER)

# "no reason at all" is the other rejected reason, and it must not be silently
# treated as a justification just because the model left the field bland.
out = bd_answer(hold_reason="none")
control(
    "PLANTED: an unexplained hold fires too",
    wl_bravedefault.apply_verdict(out, path=BMARKER)[0],
    "fire",
)
control("and says the hold had no stated reason", "no stated reason" in out["reason"], True)
wl_bravedefault.BRAVE_DEMAND.clear(BMARKER)

# -- 4d. THE SILENT PAIR: a real action, and a justified hold. -------------
out = bd_answer(changes_state=True, default_text="land it on the open PR", hold_reason="none")
kind, _note = wl_bravedefault.apply_verdict(out, path=BMARKER)
control("CONTROL: a default that acts is silent", kind, "silent")
control("CONTROL: and keeps its stop", out["verdict"], "stop")

for reason in ("irreversible", "outward", "cost-on-others"):
    out = bd_answer(hold_reason=reason, default_text="hold; publishing cannot be undone")
    kind, note = wl_bravedefault.apply_verdict(out, path=BMARKER)
    control("CONTROL: a hold justified as %s is silent" % reason, kind, "silent")
    control("CONTROL: and the justification is recorded for audit", reason in note, True)
    control("CONTROL: %s keeps its stop" % reason, out["verdict"], "stop")

out = bd_answer(applicable=False)
control(
    "CONTROL: nothing to judge is silent",
    wl_bravedefault.apply_verdict(out, path=BMARKER)[0],
    "silent",
)

# -- 4e. DEGRADED, never blocked. -----------------------------------------
out = {"verdict": "stop", "reason": "clean", "next_action": ""}
kind, note = wl_bravedefault.apply_verdict(out, path=BMARKER)
control("a missing brave_default degrades", kind, "degraded")
control("a degraded answer never flips the verdict", out["verdict"], "stop")

out = bd_answer(quote="")
kind, _note = wl_bravedefault.apply_verdict(out, path=BMARKER)
control("firing without naming the deferral is unactionable, so it degrades", kind, "degraded")
control("and never blocks", out["verdict"], "stop")

out = bd_answer(hold_reason="because")
control(
    "an invalid hold_reason degrades",
    wl_bravedefault.apply_verdict(out, path=BMARKER)[0],
    "degraded",
)

out = bd_answer(braver="")
kind, _note = wl_bravedefault.apply_verdict(out, path=BMARKER)
control("a fire with no braver form still fires", kind, "fire")
control(
    "and falls back to a generic rewrite order",
    "the action you would take alone --" in out["next_action"],
    True,
)
wl_bravedefault.BRAVE_DEMAND.clear(BMARKER)

# -- 4f. THE CAP. A rule that cannot be satisfied must not be a wall. ------
for n in (1, 2, 3):
    out = bd_answer()
    kind, _note = wl_bravedefault.apply_verdict(out, path=BMARKER)
    control("fire %d of the cap still fires" % n, kind, "fire")
    control("and is counted", fires(BMARKER), n)
out = bd_answer()
kind, note = wl_bravedefault.apply_verdict(out, path=BMARKER)
control("THE CAP: the fourth block on the same deferral is suppressed", kind, "capped")
control("THE CAP: and the session is let past", out["verdict"], "stop")
control("THE CAP: which is said out loud, not silently", "capped after 3" in note, True)

# A DIFFERENT deferral is a different demand: the cap must not carry over, or
# one exhausted item would buy silence for every later one.
out = bd_answer(quote="delete the dead branch?")
kind, _note = wl_bravedefault.apply_verdict(out, path=BMARKER)
control("CONTROL: a different deferral is not capped", kind, "fire")
control("CONTROL: and its count starts again", fires(BMARKER), 1)
wl_bravedefault.BRAVE_DEMAND.clear(BMARKER)

# -- 4g. apply_order: a judge that already said continue is not overwritten.
# Its own order is not less important than a rule's; clobbering it would trade
# one true instruction for another and hide the trade.
out = bd_answer()
out["verdict"] = "continue"
out["reason"] = "three items are open"
out["next_action"] = "work #a1b2"
wl_bravedefault.apply_verdict(out, path=BMARKER)
control("an existing continue keeps its own order", out["next_action"], "work #a1b2")
control("and its own reason", out["reason"].startswith("three items are open"), True)
control("with the finding appended", "ALSO:" in out["reason"], True)
wl_bravedefault.BRAVE_DEMAND.clear(BMARKER)

# The braver form is the MODEL's text, so it passes through the operator-only
# sanitiser like any other order. The rubric now tells the model that merging,
# pushing main and releasing are never a brave default -- this is the belt for
# that brace, and it is why the rubric's own examples were rewritten.
out = bd_answer(braver="merge it into the open PR")
wl_bravedefault.apply_verdict(out, path=BMARKER)
wl_judge.sanitize_next_action(out)
control(
    "an operator-only braver form is rejected, not ordered",
    out["next_action"].startswith("[rejected by the stop gate:"),
    True,
)
control("and the finding survives in the reason", "regenerated teasers" in out["reason"], True)
wl_bravedefault.BRAVE_DEMAND.clear(BMARKER)

# -- 4h. End to end through run_judge, and the precedence rule. -----------
v = judged("", bd_answer(), remaining=[TIMID_LINE])
control(
    "END TO END: the rubric reaches the prompt",
    wl_bravedefault.BRAVE_MARKER in CAPTURED["prompt"],
    True,
)
control(
    "END TO END: brave_default is required of the answer",
    "brave_default" in CAPTURED["schema"]["required"],
    True,
)
control("END TO END: the timid default blocks the stop", v["verdict"], "continue")
control(
    "END TO END: with the braver form in the order",
    "publish the regenerated teasers" in v["next_action"],
    True,
)
wl_bravedefault.BRAVE_DEMAND.clear()

v = judged(
    "", {"verdict": "stop", "reason": "clean board", "next_action": ""}, remaining=[OPEN_LINE]
)
control(
    "CONTROL: a board with no deferral is not asked",
    wl_bravedefault.BRAVE_MARKER in CAPTURED["prompt"],
    False,
)
control("CONTROL: and its verdict passes through", v["verdict"], "stop")
control("CONTROL: and its reason is not annotated", v["reason"], "clean board")

# ONE ORDER PER STOP: when both rules fire, the live defect in the tree wins
# and the parked decision waits for the next stop -- where its own trigger,
# the `[?]` itself, is still sitting in the list.
both_ans = answer()
both_ans["brave_default"] = bd_answer()["brave_default"]
v = judged(FIXSIG, both_ans, remaining=[TIMID_LINE])
control("PRECEDENCE: both rules fire, the sweep wins", "SWEEP THE CLASS" in v["reason"], True)
control(
    "PRECEDENCE: and the brave order is not stacked on top",
    "DEFAULT THAT DOES NOTHING" in v["reason"],
    False,
)
control(
    "PRECEDENCE: the brave demand is left unbanked for next stop",
    fires(wl_bravedefault.BRAVE_DEMAND.path()),
    None,
)
wl_classsweep.clear_outstanding()


# ===========================================================================
# PART 5 -- the judge_schema_for CONTRACT, after three markers instead of one.
#
# Session e580532b built this builder to fix a real fail-closed bug: the prompt
# asked for regression_gate while JUDGE_SCHEMA left it optional, so a stop could
# be blocked by a JUDGE error rather than by anything the session did. The fix
# is the deepcopy -- the module constant is never mutated, so one fix-signal
# stop cannot poison every later call in the same process.
#
# Adding two more markers is exactly the change that could break it quietly, so
# the contract is pinned here rather than trusted. THE GAP THIS CLOSES: every
# existing non-mutation control asserts membership of ONE key, and all of them
# would pass under a SHALLOW copy, because the builder only ever reassigns
# `required` to a fresh list. Nothing proved the deepcopy was load-bearing.
# ===========================================================================

# Captured from the constant itself, not written out by hand: a literal would
# have to be edited every time a base field is added, and an out-of-date
# literal fails for the wrong reason.
BASE_REQUIRED = list(wl_judge.JUDGE_SCHEMA["required"])
ALL_MARKERS = FIXSIG + sweep_sig + brave_sig

control("the base schema requires exactly three fields", len(BASE_REQUIRED), 3)

# 5a. THE IDENTITY PAIR. The plain path must hand back the constant itself --
#     that early return is what stops every ordinary stop paying for a deepcopy
#     -- while any marker path must hand back a different object.
control(
    "a plain call returns the module constant itself",
    wl_judge.judge_schema_for("") is wl_judge.JUDGE_SCHEMA,
    True,
)
control(
    "a marker call returns a copy, not the constant",
    wl_judge.judge_schema_for(ALL_MARKERS) is not wl_judge.JUDGE_SCHEMA,
    True,
)

# 5b. ALL THREE MARKERS AT ONCE, then EXACT equality of the constant. The
#     per-key membership checks above can each pass while a different key leaks;
#     this cannot.
_all = wl_judge.judge_schema_for(ALL_MARKERS)
control(
    "all three objects are required together",
    sorted(_all["required"][3:]),
    ["brave_default", "class_sweep", "regression_gate"],
)
control(
    "and the constant is EXACTLY unchanged afterwards",
    wl_judge.JUDGE_SCHEMA["required"],
    BASE_REQUIRED,
)
control(
    "so a later plain call is still the bare schema",
    wl_judge.judge_schema_for("")["required"],
    BASE_REQUIRED,
)

# 5c. THE DEEPCOPY ITSELF. A shallow copy would share every nested dict with the
#     constant, so writing into the returned schema's properties would edit
#     JUDGE_SCHEMA in place -- invisible to every control above. Mutate the copy
#     and prove the constant did not move.
_all["properties"]["class_sweep"]["required"].append("planted_by_a_control")
control(
    "the returned schema's nested objects are NOT shared with the constant",
    "planted_by_a_control" in wl_judge.JUDGE_SCHEMA["properties"]["class_sweep"]["required"],
    False,
)
_all["properties"]["regression_gate"]["additionalProperties"] = "planted"
control(
    "which holds for the object e580532b added, too",
    wl_judge.JUDGE_SCHEMA["properties"]["regression_gate"]["additionalProperties"],
    False,
)

# 5d. CONTROL: the planting above must actually reach the copy, or 5c proves
#     nothing -- an assertion that a write did not propagate is vacuous if the
#     write never happened.
control(
    "CONTROL: the planted field really is in the copy",
    "planted_by_a_control" in _all["properties"]["class_sweep"]["required"],
    True,
)

# 5e. Order independence. `wanted` is built marker by marker; a builder that
#     appended to a list it also read from could produce a different schema
#     depending on which marker came first in the prompt.
control(
    "marker order does not change the result",
    sorted(wl_judge.judge_schema_for(brave_sig + sweep_sig + FIXSIG)["required"]),
    sorted(_all["required"]),
)

if Tally.fails:
    print(f"FAIL: {Tally.fails} of {Tally.count} control(s) failed", file=sys.stderr)
    sys.exit(1)
print(f"{Tally.count} control(s) passed")
