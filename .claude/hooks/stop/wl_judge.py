"""wl_judge: the stop-legitimacy judge call and its v10 verdict cache.

Fail CLOSED by contract: every error path returns an error string, and the caller turns that into a block. See "NO ESCAPE HATCH" in worklist.py.
"""

import copy
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import time

import wl_bravedefault as BD
import wl_claimcheck as CC
import wl_classsweep as CS
import wl_defersettle as DS
import wl_effort
import wl_models
import wl_proc
import wl_proofcheck as PF
import worklist_messages as M

# v5: no cap. Kept as a name so the counter file (used only to TELL the judge it is repeating itself) reads clearly.
# ONE SOURCE: the model id is WK_CLAUDE_HAIKU_MODEL in .ci/config/well-known.env, which the per-commit reviewer reads too. No WORKLIST_JUDGE_MODEL knob any more, and the Python reader ignores an exported WK_ value (only the bash projection honours one): a second place to set it is a second place to forget on the next upgrade.


def __getattr__(name):
    # `wl_judge.JUDGE_MODEL` stays readable by wl_checks, wl_planrec and wl_shapedup, resolved when read (wl_models.haiku_model).
    if name == "JUDGE_MODEL":
        return wl_models.haiku_model()
    raise AttributeError(name)


# Measured on 2026-07-29 with --json-schema: haiku warm $0.011-$0.026 per call at 4.9-20.0s; sonnet $0.231 at 12.1s for the same judgement. Haiku it is. MEASURED, not guessed (2026-08-05): at $0.10 the judge died mid-run with
# subtype=error_max_budget_usd at cost $0.1025, and reported it as the
# unactionable "judge exited 1: " because the envelope goes to stdout, which the failure path was not reading (see _explain_failed_exit). The cap is a post-hoc between-turns stop, not a ceiling, so it must sit clear of the real cost rather than at it: a trivial prompt in a project cwd already reached $0.1025, while the same prompt in the judge's isolated workdir cost $0.0205. $0.25
# leaves room for the real prompt (finding + context) without being open-ended.
JUDGE_BUDGET_USD = os.environ.get("WORKLIST_JUDGE_BUDGET_USD", "0.25")
# 240, raised from 120 on 2026-08-06 after a live timeout that BLOCKED a stop. The judge blocking on failure is correct and deliberate -- a judge that fails open is an escape hatch -- which is exactly why the budget must fit the WORST case rather than the typical one. Measured on this machine: a bare `reply OK` answers in 3.9s, while the real schema-constrained judge call took 30s
# (3 turns, stop_reason tool_use) with two Opus sub-agents running, and had exceeded 120s minutes earlier under heavier load. A stop happens precisely when the session is busiest, so the typical-case budget was the wrong one. THE OUTER DEADLINE MUST EXCEED THIS ONE PLUS THE PREAMBLE, and on 2026-09-08 it did not. `.claude/settings.json` gave the Stop hook `"timeout": 300` while
# this was 240, leaving under 60s for everything the hook does BEFORE the judge -- liveness, git, plan checks, report surfacing. Under load that preamble runs long, the harness SIGTERMs the whole hook mid-judge, and the failure surfaces as "judge exited 143" with empty stdout: a KILLED judge reported as an unreachable one. The diagnostic that message offers then points at the
# model, which was healthy -- the real schema-constrained call answered in 2 turns for $0.0165 while 13 pytest workers were running. Outer raised to 900.
JUDGE_TIMEOUT_S = int(os.environ.get("WORKLIST_JUDGE_TIMEOUT_S", "240"))


def disabled(settings) -> bool:
    """True when the judge is off. Env `WORKLIST_JUDGE` set to `on` or `off` overrides (the test seam); any other value is ignored and the resolved `judge` setting decides (`off`, `core` or `full`: the effort level's bundle, or a QUEUE.md override)."""
    env = os.environ.get("WORKLIST_JUDGE")
    if env in ("on", "off"):
        return env == "off"
    return settings.judge == "off"


def riders(settings) -> bool:
    """True when the judge call carries its riders: the regression fix-set with its class sweep and proof obligation, the deferral audit, defer-settle, the admission check and the brave-default question. Only `judge: full` (effort high and ultra) does; `core` (effort smart) asks the judge its own question alone (agent/plans/PLAN-stop-hook-effort.md)."""
    return not disabled(settings) and settings.judge == "full"


# v10 VERDICT CACHE. The judge is the dominant cost of a quiet-but-tracked stop (5-20s and $0.01-0.03, measured), and its question is a function of the WORLD and the MESSAGE. An identical world signature and an identical message within the TTL is the same question about the same facts, so a cached "stop" answers it for free -- the v9 fast-path argument, one level up. Fails toward
# calling the judge: only clean "stop" verdicts with no regression signals are ever cached, and any mismatch or corruption is a miss.
JUDGE_CACHE_MIN = int(os.environ.get("WORKLIST_JUDGE_CACHE_MIN", "30"))

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["stop", "continue"]},
        "reason": {"type": "string", "maxLength": 300},
        "next_action": {"type": "string", "maxLength": 200},
        # What a `continue` rests on (JUDGE_BASIS below): required only on a stop whose effort level makes a report key advise-only, so an ordinary call's schema keeps its three required fields.
        "basis": {"type": "string", "enum": ["work", "no-remaining", "out-of-sync"]},
        # v7: OPTIONAL at the top level (verified: --json-schema accepts a conditionally-required object and returns cleanly with it omitted, so ONE schema, no variants), but its own properties are all required. On a fix-signal stop a missing or malformed object is a judge error and fails closed, same as an invalid verdict. v11: the admission object, same optional-at-top-level
        # shape as regression_gate above and for the same reason. UNLIKE regression_gate, a missing or malformed object here NEVER fails closed: this detector's only consequence is a tracked item, and a session blocked by a phantom regret learns to phrase things evasively, which costs more than the detection is worth. See wl_admit.py.
        "admission": {
            "type": "object",
            "properties": {
                "present": {"type": "boolean"},
                "quote": {"type": "string", "maxLength": 400},
                "agency": {"type": "boolean"},
                "completed": {"type": "boolean"},
                "residue": {"type": "string", "enum": ["none", "damage", "machinery"]},
                "artifact": {"type": "string", "maxLength": 200},
                "recurrence": {"type": "string", "maxLength": 300},
                "guard": {"type": "string", "maxLength": 300},
            },
            "required": [
                "present",
                "quote",
                "agency",
                "completed",
                "residue",
                "artifact",
                "recurrence",
                "guard",
            ],
            "additionalProperties": False,
        },
        # v14: the class sweep. Same optional-at-the-top-level shape as regression_gate and admission, made REQUIRED by judge_schema_for when the prompt actually asks for it. Its failure semantics are the admission's, NOT the regression gate's: a missing or malformed object never fails closed, because the only thing this object can do is turn a stop into a continue, so degrading
        # loses a demand rather than granting an exit. See wl_classsweep.
        "class_sweep": CS.CLASS_SWEEP_SCHEMA,
        # v14, the second of the pair. Same optional-at-the-top-level shape and the same never-fails-closed semantics as class_sweep, asked on a different trigger: a `[?]` in the remaining list that carries a DEFAULT. See wl_bravedefault.
        "brave_default": BD.BRAVE_DEFAULT_SCHEMA,
        # v18: rides the SAME fix-stop trigger as class_sweep, asking a different question about the same fix-set -- did a bulk mechanical transform inside it prove it did not destroy structure it does not know about. Same optional-at-the-top-level shape, same never-fails-closed semantics: the only thing this object can do is turn a stop into a continue. See wl_proofcheck.
        "proof_obligation": PF.PROOF_SCHEMA,
        # v19: whether a completion claim's own evidence DEMONSTRATES it. Same optional-at-the-top-level shape and the same never-fails-closed semantics as class_sweep, and weaker still: this object cannot even turn a stop into a continue, so a missing or malformed one loses an advisory and nothing else. Asked on the claim-check marker, which rides the fix stop's tick. See
        # wl_claimcheck.
        "claim_check": CC.CLAIM_SCHEMA,
        # v21: whether a [?]'s premise is already false, judged over Python-computed facts. Same optional-at-the-top-level shape and the same never-fails-closed semantics as class_sweep: a missing entry leaves the deferral exactly as it was. Batched and acted on by wl_checks; see wl_defersettle.
        "defer_settle": DS.DEFER_SETTLE_SCHEMA,
        "regression_gate": {
            "type": "object",
            "properties": {
                "applicable": {"type": "boolean"},
                "blind_spot": {"type": "string", "maxLength": 300},
                "existing_gate": {"type": "string", "maxLength": 100},
                "recurring": {"type": "boolean"},
                "gate_needed": {"type": "boolean"},
                "gate_proven": {"type": "boolean"},
                "instruction": {"type": "string", "maxLength": 300},
                # v13: WHERE the regression test belongs. Before this, the only answer the machinery could accept was a check-*.ts, so a behavioural fix in the CLI or renet was told to assert that its SOURCE still looks right -- a different claim from the one the
                # defect needs. The six surfaces are the ones ci.yml actually has;
                # `.claude/skills/testing/` routes between them.
                "surface": {
                    "type": "string",
                    "enum": ["gates", "e2e", "ops", "install", "unit", "hooks", "none"],
                },
                # The repo-relative path the case belongs in. Named by the judge rather than matched against a list of globs, so a surface this machinery has never heard of still has a checkable answer.
                "artifact": {"type": "string", "maxLength": 200},
            },
            "required": [
                "applicable",
                "blind_spot",
                "existing_gate",
                "recurring",
                "gate_needed",
                "gate_proven",
                "instruction",
                "surface",
                "artifact",
            ],
            "additionalProperties": False,
        },
        # v12: OPTIONAL at the top level, same contract as regression_gate: one schema, and on a stop that REQUESTED an audit a missing or malformed array is a judge error that fails closed at the caller (apply_defer_audit + R_AUDIT_MALFORMED).
        "defer_audit": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 16},
                    "verdict": {"type": "string", "enum": ["valid", "do_now"]},
                    "reason": {"type": "string", "maxLength": 200},
                    "order": {"type": "string", "maxLength": 200},
                },
                "required": ["id", "verdict", "reason", "order"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "reason", "next_action"],
    "additionalProperties": False,
}


# v16 TRIAGE. Same shape as JUDGE_SCHEMA (flat object, string enum) and the same transport, but DELIBERATELY the opposite failure semantics: the stop judge fails closed because it gates an exit, while triage is a decision aid on a CLI path, so an error degrades to the self-assessment printout and exit 0. See run_triage.
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["inline", "plan-subagent", "operator-only"],
        },
        "reason": {"type": "string", "maxLength": 300},
        "plan_slug": {"type": "string", "maxLength": 60},
    },
    "required": ["verdict", "reason", "plan_slug"],
    "additionalProperties": False,
}

TRIAGE_VERDICTS = ("inline", "plan-subagent", "operator-only")


def _budget_headroom(env_out):
    """True when this call ended well inside its budget, so a retry is not a re-wander.

    A budget-exhausted call that produced nothing will exhaust it again; asking twice just doubles the bill for the same silence. Below 80% of the cap, whatever went wrong was not the cap.
    """
    cost = (env_out or {}).get("total_cost_usd")
    if not isinstance(cost, (int, float)):
        return False
    try:
        return cost < float(JUDGE_BUDGET_USD) * 0.8
    except (TypeError, ValueError):
        return False


# The CLI's own name for "the model could not produce an object matching the schema, and I gave up re-asking". It is a SAMPLE failing, not a transport or a configuration failing, which is why it is retried below rather than reported.
SCHEMA_EXHAUSTION = "error_max_structured_output_retries"
# The THIRD spelling of the same sample failure, measured 2026-10-03: "judge exited 1; subtype=success; stop_reason=stop_sequence; turns=2; cost=$0.0707 of budget $0.25". The model ended its turn in text and the CLI, finding no structured object, exited 1 while still calling the run a success. Three re-runs of the real call (same schema, model, budget, no tools) each
# returned a valid verdict at $0.01-0.03, so it is a sample, not a broken gate, and it is retried like the other two.
TURN_ENDED_WITHOUT_OBJECT = ("stop_sequence", "end_turn")


def _sample_failed(env_out):
    """True when a non-zero exit's envelope is a sample that produced no conforming object, the one failure a retry can cure."""
    if env_out.get("subtype") == SCHEMA_EXHAUSTION:
        return True
    return (
        env_out.get("subtype") == "success"
        and not env_out.get("structured_output")
        and env_out.get("stop_reason") in TURN_ENDED_WITHOUT_OBJECT
    )


def wire_schema(schema):
    """The schema as the CLI receives it: every `maxLength` becomes a prose limit in `description`, so the model SEES the limit but the CLI no longer REJECTS an overshoot.

    THE BUG THIS FIXES, measured 2026-10-24 (stop of session d778be9d): "judge exited 1; subtype=error_max_structured_output_retries; stop_reason=tool_use; turns=6; cost=$0.0132", twice in a row, so the single retry did not help. Reproducing the real call with --output-format stream-json showed the child's StructuredOutput tool results: "Output does not match required schema: /reason: must NOT have more than 300 characters (got 310)", then 321, then 345, and so on. A hard `maxLength` makes the CLI bounce a verdict over the limit by a few characters, up to five times, and a model writing a dense multi-fact verdict overshoots 300 again on most re-asks (3 of 6 live runs of one realistic prompt needed a re-ask, one needed two). Tools were never the cause (`--tools ""` is in every argv) and the model was healthy.

    The limit is a size budget for the session-facing text, not a validity condition, so it is enforced HERE, after the answer arrives (`clamp_to_schema`), never by rejecting the answer. A judge that fails still blocks; this only stops a verdict that exists from being thrown away for being 10 characters long.
    """
    if isinstance(schema, list):
        return [wire_schema(v) for v in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: wire_schema(v) for k, v in schema.items() if k != "maxLength"}
    limit = schema.get("maxLength")
    if isinstance(limit, int) and not isinstance(limit, bool):
        note = "Keep under %d characters." % limit
        out["description"] = (
            ("%s %s" % (out["description"], note)) if out.get("description") else note
        )
    return out


def clamp_to_schema(value, schema):
    """`value` with every string cut to its schema `maxLength` (dicts and lists are changed in place and returned). The cut falls on the last word boundary that fits, and a limit with no boundary in its second half is a hard slice."""
    if not isinstance(schema, dict):
        return value
    if isinstance(value, str):
        limit = schema.get("maxLength")
        if isinstance(limit, int) and not isinstance(limit, bool) and len(value) > limit:
            cut = value[:limit]
            space = cut.rfind(" ")
            return (cut[:space] if space >= limit // 2 else cut).rstrip()
        return value
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        for k in list(value):
            if k in props:
                value[k] = clamp_to_schema(value[k], props[k])
        return value
    if isinstance(value, list):
        item = schema.get("items")
        for i, v in enumerate(value):
            value[i] = clamp_to_schema(v, item)
        return value
    return value


def retry_schema_exhaustion(label, proc, call):
    """(proc, None) to carry on, or (None, why) to give up, for a NON-ZERO exit.

    THE BUG THIS FIXES, measured 2026-09-04. A stop was blocked with
    "judge exited 1; subtype=error_max_structured_output_retries; turns=6;
    cost=$0.0112 of budget $0.25", and the message that follows such a failure
    tells the session the gate is broken and offers WORKLIST_JUDGE=off.

    Neither claim was true. The model was reachable (a probe answered), and the REAL call -- same schema, same model, same budget -- returned a valid verdict three times out of three at $0.05-0.06 each, which is five times what the failing run spent. So the run did not hit its cap and the schema is not unsatisfiable: one sample simply failed to emit a conforming object.

    That is the SAME condition the exit-0 path a few lines down already retries, and calls "a sample, not a broken gate". The two differ only in how the CLI reports them: wandering to the end of the turn exits 0 with structured_output null, while exhausting the CLI's own schema retries exits 1 with this subtype. Keying the retry on the exit code rather than on what actually
    happened meant the identical failure was a flake in one spelling and a "BUG in the gate" in the other -- and the harsher spelling is the one that points a session at the disable switch.

    Bounded exactly as the other retry is: only this subtype, only with budget headroom (a call that spent its cap will spend it again), only once, and never after a transport failure -- a launch error or a timeout raises before reaching here and is not routed through this path at all.
    """
    first = _explain_failed_exit(label, proc)
    env_out = None
    try:
        env_out = json.loads(proc.stdout or "")
    except ValueError:
        env_out = None
    if not isinstance(env_out, dict) or not _sample_failed(env_out):
        return None, first
    if not _budget_headroom(env_out):
        return None, first + "; not retried: the call had already spent its budget"
    try:
        retried = call()
    except (subprocess.TimeoutExpired, OSError):
        return None, first + "; the single retry could not be launched"
    if retried.returncode != 0:
        return None, first + "; and the single retry also failed: " + _explain_failed_exit(
            label, retried
        )
    return retried, None


def _explain_no_output(label, env_out, out):
    """Exit 0, is_error false, and no usable structured_output: say WHY.

    This is the shape a budget-capped schema-constrained call takes when it wanders: the transport worked, so none of the failure branches above fire, and the bare repr of `None` tells the reading session nothing. The envelope still carries the cost, the stop_reason and the turn count.
    """
    bits = ["%s produced no usable structured_output: %s" % (label, repr(out)[:200])]
    if isinstance(env_out, dict):
        bits.extend(_envelope_bits(env_out))
    return "; ".join(bits)


def _envelope_bits(env_out):
    """The actionable fields of a `claude -p` result envelope, as report bits.

    EXTRACTED 2026-08-26 because these lived only on the non-zero-exit path, and the failure that actually happened exits ZERO. A budget-capped, schema-constrained call that wanders can return exit 0, is_error false, and `structured_output: null` -- and the gate reported exactly that, "produced no usable structured_output: None", while the same envelope was holding the cost, the
    stop_reason and the turn count that name the cause. The next session then reads a line whose following sentence offers to DISABLE the gate, with no evidence either way. Measured the same day: a trivial schema-constrained haiku call costs $0.0566 of the $0.25 default, so a long prompt exhausting it is the expected failure, not an exotic one.
    """
    bits = []
    if env_out.get("subtype"):
        bits.append("subtype=%s" % env_out["subtype"])
    if env_out.get("api_error_status"):
        bits.append("api=%s" % env_out["api_error_status"])
    if env_out.get("stop_reason"):
        bits.append("stop_reason=%s" % env_out["stop_reason"])
    turns = env_out.get("num_turns")
    if isinstance(turns, int):
        bits.append("turns=%d" % turns)
    cost = env_out.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        bits.append("cost=$%.4f of budget $%s" % (cost, JUDGE_BUDGET_USD))
        try:
            if cost >= float(JUDGE_BUDGET_USD) * 0.9:
                bits.append(
                    "BUDGET EXHAUSTED (or within 10%% of it) -- raise "
                    "WORKLIST_JUDGE_BUDGET_USD (currently %s) or shorten the "
                    "prompt" % JUDGE_BUDGET_USD
                )
        except (TypeError, ValueError):
            pass
    return bits


def _explain_failed_exit(label, proc):
    """Why a `claude -p` child exited non-zero, in a line an operator can act on.

    THE BUG THIS FIXES (2026-08-05): these paths reported `proc.stderr` only, and the CLI writes its error ENVELOPE TO STDOUT, leaving stderr empty. The gate therefore surfaced the unactionable "judge exited 1: " with nothing after the colon, while stdout was holding is_error, the stop_reason, and the exact cost against the budget. The `is_error` branch further down never ran,
    because it
    sits behind returncode == 0. A judge that cannot say why it failed is an
    escape hatch wearing a gate's clothes -- the same swallowed-failure class the repo scans for, inside the thing that audits it.
    """
    # A SIGNAL IS NOT A FAILURE TO ANSWER, and conflating the two cost a full turn on 2026-09-08. The child was SIGTERMed because the outer Stop-hook deadline was shorter than this judge's own; the gate reported "exited 143" with empty stdout, the operator-facing text read as an unreachable model, and the remedy it offered was to DISABLE the gate. The model was healthy -- the real
    # schema-constrained call answered in 2 turns for $0.0165 minutes later. So a killed child says so, and points at the deadline rather than the model.
    sig = (
        -proc.returncode
        if proc.returncode < 0
        else (proc.returncode - 128 if 128 < proc.returncode < 160 else 0)
    )
    if sig:
        return [
            "%s was KILLED by signal %d (exit %d), which is not the same as failing "
            "to answer: nothing here says the model is unreachable. Something "
            "terminated the child -- usually an OUTER deadline shorter than this "
            "gate's own %ds, so check the Stop hook's `timeout` in "
            ".claude/settings.json before suspecting the model, and reproduce the "
            "REAL call (--json-schema INLINE, not a path, plus --max-budget-usd) "
            "rather than a bare connectivity probe."
            % (label, sig, proc.returncode, JUDGE_TIMEOUT_S)
        ]
    bits = ["%s exited %d" % (label, proc.returncode)]
    env_out = None
    try:
        env_out = json.loads(proc.stdout or "")
    except ValueError:
        env_out = None
    if isinstance(env_out, dict):
        bits.extend(_envelope_bits(env_out))
    stderr_tail = (proc.stderr or "").strip()
    if stderr_tail:
        bits.append("stderr=%s" % stderr_tail[-200:])
    elif not isinstance(env_out, dict):
        bits.append("stdout=%s" % (proc.stdout or "")[-200:].strip())
    return "; ".join(bits)


def run_triage(finding, context):
    """(verdict_dict, error_string). Exactly one is non-None.

    Modeled on run_judge down to the recursion guard and the workdir, because the transport is the same and a second copy that drifts is a second bug. The CALLER decides what an error means; here every failure is simply reported, never swallowed, so a degraded triage can name what broke.
    """
    exe = resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found (looked at PATH and ~/.local/bin/claude)"
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "triage workdir unusable: %s" % exc
    prompt = M.TRIAGE_PROMPT % {"finding": finding[-4000:], "context": context}
    env = dict(os.environ)
    # THE RECURSION GUARD, same as run_judge: `claude -p` fires the Stop hook.
    env["STOPHOOK_CHILD"] = "1"

    def _call():
        return wl_proc.run(
            [
                exe,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(wire_schema(TRIAGE_SCHEMA)),
                "--model",
                wl_models.haiku_model(),
                # NO TOOLS. A judge reads a prompt and returns a verdict; it has never needed Bash, Read or Grep, and it was being handed all three in a cwd (/tmp/claude-worklist/.judge) that contains nothing -- while the sweep prompt told it "every path it names must actually exist in this repo". Tonight 8 of 21 sweep verdicts were DROPPED for naming paths that do not exist; a
                # model that cannot look must be told the paths instead of inventing them.
                #
                # WHAT THIS IS NOT: a fix for the no-output failure. That theory was that the model spent turn 1 on a tool call and ended on turn 2. Probed 2026-09-04 against the real CLI -- `--tools ""` with `--json-schema` returns a valid
                # verdict and STILL reports turns=2. So turn 2 is the normal shape here and
                # proves nothing about tools. The retry below remains the thing that handles a missing verdict.
                "--tools",
                "",
                "--max-budget-usd",
                JUDGE_BUDGET_USD,
            ],
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            cwd=str(workdir),
        )

    proc = _call()
    if proc.timed_out:
        return None, "triage timed out after %ds" % JUDGE_TIMEOUT_S
    if proc.returncode == wl_proc.SPAWN_FAILED_RC and not proc.stdout:
        return None, "triage could not be launched: %s" % proc.stderr.strip()
    if proc.returncode != 0:
        proc, _why = retry_schema_exhaustion("triage", proc, _call)
        if proc is None:
            return None, _why
    try:
        env_out = json.loads(proc.stdout)
    except ValueError:
        return None, "triage returned unparseable stdout: %s" % (proc.stdout or "")[-300:]
    if env_out.get("is_error"):
        return None, "triage reported is_error (subtype=%s, api=%s)" % (
            env_out.get("subtype"),
            env_out.get("api_error_status"),
        )
    out = clamp_to_schema(env_out.get("structured_output"), TRIAGE_SCHEMA)
    if not isinstance(out, dict) or out.get("verdict") not in TRIAGE_VERDICTS:
        return None, _explain_no_output("triage", env_out, out)
    return out, None


PLANFID_SCHEMA = {
    "type": "object",
    "properties": {
        "plan_fidelity": {
            "type": "object",
            "properties": {
                "faithful": {"type": "boolean"},
                "umbrella_ids": {"type": "array", "items": {"type": "string", "maxLength": 16}},
                "missing": {"type": "array", "items": {"type": "string", "maxLength": 300}},
                "instruction": {"type": "string", "maxLength": 300},
            },
            "required": ["faithful", "umbrella_ids", "missing", "instruction"],
            "additionalProperties": False,
        }
    },
    "required": ["plan_fidelity"],
    "additionalProperties": False,
}


def _run_structured(label, prompt, schema, extract):
    """(payload, error_string). Exactly one is non-None. ONE transport.

    run_judge, run_triage and run_admission are three near-identical copies of this, and wl_judge's own comment on the second one ("the transport is the same and a second copy that drifts is a second bug") is the argument against adding a fourth. Only the NEW caller is routed through here: folding the three live paths in would be a behaviour change to the stop gate itself, which is
    not this change's business. That is a named residual, not an oversight -- the next module that needs a model call should use this and the three copies should follow when something else forces them open.

    Failure semantics are the CALLER's business, exactly as for run_triage: every error is reported, never swallowed.
    """
    exe = resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found (looked at PATH and ~/.local/bin/claude)"
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "%s workdir unusable: %s" % (label, exc)
    env = dict(os.environ)
    # THE RECURSION GUARD, same as run_judge: `claude -p` fires the Stop hook.
    env["STOPHOOK_CHILD"] = "1"

    def _call():
        return wl_proc.run(
            [
                exe,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(wire_schema(schema)),
                "--model",
                wl_models.haiku_model(),
                # NO TOOLS. A judge reads a prompt and returns a verdict; it has never needed Bash, Read or Grep, and it was being handed all three in a cwd (/tmp/claude-worklist/.judge) that contains nothing -- while the sweep prompt told it "every path it names must actually exist in this repo". Tonight 8 of 21 sweep verdicts were DROPPED for naming paths that do not exist; a
                # model that cannot look must be told the paths instead of inventing them.
                #
                # WHAT THIS IS NOT: a fix for the no-output failure. That theory was that the model spent turn 1 on a tool call and ended on turn 2. Probed 2026-09-04 against the real CLI -- `--tools ""` with `--json-schema` returns a valid
                # verdict and STILL reports turns=2. So turn 2 is the normal shape here and
                # proves nothing about tools. The retry below remains the thing that handles a missing verdict.
                "--tools",
                "",
                "--max-budget-usd",
                JUDGE_BUDGET_USD,
            ],
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            cwd=str(workdir),
        )

    proc = _call()
    if proc.timed_out:
        return None, "%s timed out after %ds" % (label, JUDGE_TIMEOUT_S)
    if proc.returncode == wl_proc.SPAWN_FAILED_RC and not proc.stdout:
        return None, "%s could not be launched: %s" % (label, proc.stderr.strip())
    if proc.returncode != 0:
        proc, _why = retry_schema_exhaustion(label, proc, _call)
        if proc is None:
            return None, _why
    try:
        env_out = json.loads(proc.stdout)
    except ValueError:
        return None, "%s returned unparseable stdout: %s" % (label, (proc.stdout or "")[-300:])
    if env_out.get("is_error"):
        return None, "%s reported is_error (subtype=%s, api=%s)" % (
            label,
            env_out.get("subtype"),
            env_out.get("api_error_status"),
        )
    out = clamp_to_schema(env_out.get("structured_output"), schema)
    payload = extract(out) if isinstance(out, dict) else None
    if payload is None:
        return None, _explain_no_output(label, env_out, out)
    return payload, None


def run_planfid(plan_text, items_rendered, message):
    """(plan_fidelity_dict, error_string). Exactly one is non-None.

    DEGRADES, never blocks on its own unavailability. See wl_planfid's header: this check triggers on a heuristic about item shape rather than on an artifact, so an unreachable model must not wall in every session that has an approved plan. The caller reports the error on the systemMessage line.
    """
    prompt = M.PLANFID_PROMPT % {
        "plan": (plan_text or "")[:14000],
        "items": items_rendered or "  (none)",
        "message": (message or "(the session produced no text)")[-3000:],
    }
    return _run_structured(
        "plan-fidelity",
        prompt,
        PLANFID_SCHEMA,
        lambda out: (
            out.get("plan_fidelity") if isinstance(out.get("plan_fidelity"), dict) else None
        ),
    )


ADMISSION_SCHEMA = {
    "type": "object",
    "properties": {"admission": JUDGE_SCHEMA["properties"]["admission"]},
    "required": ["admission"],
    "additionalProperties": False,
}


def run_admission(message):
    """(admission_dict, error_string). Exactly one is non-None.

    The standalone path, for a stop where the prefilter fired but the main judge was never invoked (nothing else remained to judge). Modeled on run_triage down to the recursion guard and the workdir, because the transport is the same and a second copy that drifts is a second bug.

    It DEGRADES, never blocks, like run_triage and unlike run_judge. An admission detector that could block on its own unavailability would punish a session
    for the honesty that triggered it.
    """
    exe = resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found (looked at PATH and ~/.local/bin/claude)"
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "admission workdir unusable: %s" % exc
    prompt = M.ADMISSION_PROMPT + "\n\nMESSAGE:\n" + message[-8000:]
    env = dict(os.environ)
    env["STOPHOOK_CHILD"] = "1"

    def _call():
        return wl_proc.run(
            [
                exe,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(wire_schema(ADMISSION_SCHEMA)),
                "--model",
                wl_models.haiku_model(),
                # NO TOOLS. A judge reads a prompt and returns a verdict; it has never needed Bash, Read or Grep, and it was being handed all three in a cwd (/tmp/claude-worklist/.judge) that contains nothing -- while the sweep prompt told it "every path it names must actually exist in this repo". Tonight 8 of 21 sweep verdicts were DROPPED for naming paths that do not exist; a
                # model that cannot look must be told the paths instead of inventing them.
                #
                # WHAT THIS IS NOT: a fix for the no-output failure. That theory was that the model spent turn 1 on a tool call and ended on turn 2. Probed 2026-09-04 against the real CLI -- `--tools ""` with `--json-schema` returns a valid
                # verdict and STILL reports turns=2. So turn 2 is the normal shape here and
                # proves nothing about tools. The retry below remains the thing that handles a missing verdict.
                "--tools",
                "",
                "--max-budget-usd",
                JUDGE_BUDGET_USD,
            ],
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            cwd=str(workdir),
        )

    proc = _call()
    if proc.timed_out:
        return None, "admission timed out after %ds" % JUDGE_TIMEOUT_S
    if proc.returncode == wl_proc.SPAWN_FAILED_RC and not proc.stdout:
        return None, "admission could not be launched: %s" % proc.stderr.strip()
    if proc.returncode != 0:
        proc, _why = retry_schema_exhaustion("admission", proc, _call)
        if proc is None:
            return None, _why
    try:
        env_out = json.loads(proc.stdout)
    except ValueError:
        return None, "admission returned unparseable stdout: %s" % (proc.stdout or "")[-300:]
    if env_out.get("is_error"):
        return None, "admission reported is_error (subtype=%s)" % env_out.get("subtype")
    out = clamp_to_schema(env_out.get("structured_output"), ADMISSION_SCHEMA)
    if not isinstance(out, dict) or not isinstance(out.get("admission"), dict):
        return None, _explain_no_output("admission", env_out, out)
    return out["admission"], None


def apply_defer_audit(rows, batch):
    """(kind, valids, orders) from the judge's defer_audit answer.

    kind is 'ok' or 'malformed'; valids is [(id, upd_stamp, reason)] to bank, orders is [(id, order_text)] to enforce. STRICT by contract: every audited item must come back with a usable verdict, and anything else -- no array, a non-dict entry, an invalid verdict, a batch id missing -- is 'malformed', which the caller turns into a fail-closed block. An id the judge invented is
    ignored rather than acted on: reopening an item nobody audited would let a hallucination edit the store.
    """
    if not isinstance(rows, list):
        return "malformed", [], []
    by_id = {}
    for e in rows:
        if not isinstance(e, dict) or e.get("verdict") not in ("valid", "do_now"):
            return "malformed", [], []
        by_id[str(e.get("id", ""))] = e
    valids, orders = [], []
    for rec in batch:
        e = by_id.get(rec["id"])
        if e is None:
            return "malformed", [], []
        if e["verdict"] == "valid":
            valids.append((rec["id"], rec.get("upd", ""), str(e.get("reason", ""))))
        else:
            orders.append((rec["id"], str(e.get("order", "")) or str(e.get("reason", ""))))
    return "ok", valids, orders


# ---- the cited-gate pre-check (PLAN-trap-enforcement.md W4-cited-gate) ----------------------------------------------------
#
# NOT A MODEL CALL, and it runs whether or not the judge does. A stop message that says `check:<x> passed` for an id no registry defines is reporting a gate that cannot have run: `npm run <missing>` exits 1, so the "pass" was read off something else (TRAPS.md, manifest-id-is-not-an-npm-script, met here a second time at a different layer). The judge already sees the session's
# citations; this is the narrow deterministic slice of that review (plan section 5), a backstop to the pre-bash guard block_missing_npm_script rather than the mechanism.
#
# REGISTERED MEANS the ci-runner manifest (`scripts/ci-runner/gates.lock.json`, the projection of manifest.ts GATES that check:ci-gates-lock keeps faithful) OR a root package.json script: an aggregate like `check:i18n` is a real npm script with no manifest entry, and calling its pass a phantom would be the false positive that teaches sessions to skim this check. With neither file readable it says nothing.
CLAIMED_GATE = re.compile(
    r"(?<![\w:/-])((?:check|gate-test):[A-Za-z0-9][A-Za-z0-9:._-]*[A-Za-z0-9])`?"
    r"[^\n]{0,40}?\b(pass(?:ed|es)?|green|rc\s*=?\s*0|exit(?:ed|s)?\s*(?:code\s*)?0)\b",
    re.IGNORECASE,
)

V_PHANTOM_GATE = """CLAIMED A GATE THAT DOES NOT EXIST: %s

This message reports a pass for a gate id that neither the ci-runner manifest
(scripts/ci-runner/gates.lock.json) nor package.json defines. `npm run <missing>`
exits 1, so that "pass" was read off something else. Find the real id, run it,
and restate the result with its exit code:
    grep -n "id: '<the-id>'" -A3 scripts/ci-runner/manifest.ts"""


def registered_gate_ids(root):
    """Every manifest id plus every root package.json script name, or None when neither can be read (no verdict)."""
    ids = set()
    readable = False
    try:
        with open(
            os.path.join(str(root), "scripts", "ci-runner", "gates.lock.json"), encoding="utf-8"
        ) as fh:
            lock = json.load(fh)
        ids |= {g["id"] for g in lock if isinstance(g, dict) and isinstance(g.get("id"), str)}
        readable = True
    except (OSError, ValueError, TypeError):
        pass
    try:
        with open(os.path.join(str(root), "package.json"), encoding="utf-8") as fh:
            ids |= set((json.load(fh) or {}).get("scripts") or {})
        readable = True
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return ids if readable else None


def phantom_gate_claims(message, root):
    """Ids `message` claims passed that no registry defines, in first-seen order. [] when nothing is claimed or nothing can be read."""
    claimed = []
    for m in CLAIMED_GATE.finditer(message or ""):
        gid = m.group(1).rstrip(".:")
        if gid not in claimed:
            claimed.append(gid)
    if not claimed:
        return []
    known = registered_gate_ids(root)
    if known is None:
        return []
    return [g for g in claimed if g not in known]


def resolve_claude():
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def msg_hash(message):
    return hashlib.sha1((message or "").encode("utf-8", "replace")).hexdigest()[:16]


def cached_stop_verdict(state_doc, sig, message):
    """A previously banked 'stop' verdict for this exact world+message, or None. Any doubt is a miss."""
    c = state_doc.get("judge_cache")
    if not isinstance(c, dict):
        return None
    try:
        fresh = time.time() - float(c.get("at", 0)) <= JUDGE_CACHE_MIN * 60
    except (TypeError, ValueError):
        return None
    if not fresh or c.get("sig") != sig or c.get("msg") != msg_hash(message):
        return None
    if c.get("verdict") != "stop":
        return None
    return {"verdict": "stop", "reason": str(c.get("reason", "cached")), "next_action": ""}


def bank_stop_verdict(state_doc, sig, message, reason):
    state_doc["judge_cache"] = {
        "sig": sig,
        "msg": msg_hash(message),
        "verdict": "stop",
        "reason": reason[:200],
        "at": time.time(),
    }


# The fix-signal is a SEPARATE prompt section (M.REGGATE_PROMPT, appended as `extra`), but v7 shipped ONE schema in which `regression_gate` is optional at the top level. So on a fix-signal stop the model could satisfy the schema while omitting the object entirely, and `wl_reggate` then reports "regression_gate missing or incomplete: None" and blocks by the no-escape-hatch rule.
# That is the gate refusing to be bypassed, which is correct, but the session is blocked by a JUDGE error rather than by anything it did. Observed live 2026-08-28.
#
# The fix is upstream of the failure: when the prompt ASKS for the object, the schema REQUIRES it. Nothing here weakens the fail-closed path; a malformed object still blocks.
_REGGATE_MARKER = "A FIX LANDED THIS TURN"


# -------------------------------------------------------------------------- THE JUDGE LOG, and the only honest source of the judge's own streak.
#
# The prompt used to say "Consecutive times this gate has already said continue: N" and was handed `worklist.blocks-<me8>` -- the count of ALL stop blocks, from every check in the battery. On 2026-09-04 that number read 69
# while the judge itself had spoken a handful of times. The sentence asks the
# judge to distrust its own advice after 3, so a counter that runs 20x fast turns a useful brake into permanent self-doubt about a history that did not happen.
#
# A verdict log fixes the number and is worth having on its own: it is the only record of what the judge actually said, which until now existed nowhere. --------------------------------------------------------------------------

JUDGE_LOG_CAP = 400


def judge_log_path(worklist, me8):
    """Per-session, beside the store, same convention as the block counter."""
    return worklist.with_suffix(".judge-%s.jsonl" % me8)


def log_verdict(path, verdict, reason, error=None):
    """Append one line. Best-effort: a log that cannot be written must never take a stop with it, so every failure here is swallowed deliberately."""
    try:
        rec = {
            "ts": int(time.time()),
            "verdict": verdict,
            "reason": (reason or "")[:400],
        }
        if error:
            rec["error"] = str(error)[:200]
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        # Bounded: the file is per session, but a long autonomous night is long.
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > JUDGE_LOG_CAP * 2:
            path.write_text("\n".join(lines[-JUDGE_LOG_CAP:]) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError):
        pass


def continue_streak(path):
    """Consecutive trailing `continue` verdicts. Anything else -- a stop, an unavailable judge -- ends the run, because the sentence in the prompt is about advice that kept not landing, and a stop means it landed."""
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    n = 0
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            break
        if rec.get("verdict") != "continue":
            break
        n += 1
    return n


def is_fix_stop(extra):
    """Is this stop already asking the regression-gate question?"""
    return _REGGATE_MARKER in (extra or "")


def judge_schema_for(extra):
    """JUDGE_SCHEMA, with each optional object required iff the prompt asks for it.

    ONE rule, applied per marker: regression_gate for _REGGATE_MARKER, class_sweep for CS.SWEEP_MARKER, brave_default for BD.BRAVE_MARKER, proof_obligation for PF.PROOF_MARKER, claim_check for CC.CLAIM_MARKER. The markers are INDEPENDENT and must not collapse into one boolean: the sweep and proof sections are also appended on a carried-forward demand, the brave section triggers on
    the remaining list, and the claim section is appended by wl_checks only when the fix-set has a TICK behind it, so any of them can arrive on a stop where the others did not. Requiring regression_gate on such a stop would fail the judge closed for a question nobody asked.
    """
    text = extra or ""
    wanted = []
    if _REGGATE_MARKER in text:
        wanted.append("regression_gate")
    if CS.SWEEP_MARKER in text:
        wanted.append("class_sweep")
    if BD.BRAVE_MARKER in text:
        wanted.append("brave_default")
    if PF.PROOF_MARKER in text:
        wanted.append("proof_obligation")
    if CC.CLAIM_MARKER in text:
        wanted.append("claim_check")
    if DS.DEFER_SETTLE_MARKER in text:
        wanted.append("defer_settle")
    missing = [k for k in wanted if k not in JUDGE_SCHEMA["required"]]
    if not missing:
        return JUDGE_SCHEMA
    schema = copy.deepcopy(JUDGE_SCHEMA)
    schema["required"] = [*schema["required"], *missing]
    return schema


def run_judge(
    remaining_lines,
    leases,
    message,
    streak,
    loop_desc,
    citations=None,
    extra="",
    traps=None,
    fixset_files=None,
    fixset_provenance=None,
    transcript=None,
    fixset_instance=None,
    local_batch=None,
    with_riders=True,
    closed=None,
    effort_level=None,
):
    """(verdict_dict, error_string). Exactly one is non-None.

    `effort_level` is the stop's resolved effort level (wl_effort). When it makes a report key (REPORT_BASES) advise-only or off, the prompt carries JUDGE_BASIS, the schema requires `basis`, and a `continue` resting only on such a key is read as stop with the order handed back as an advisory (`settle_by_effort`).

    `with_riders` False (`judge: core`, wl_judge.riders) asks no class sweep, proof obligation or brave-default question, fresh or outstanding: the judge answers whether stopping is honest and nothing else. `closed` is the session's recently closed items as (id, text, evidence) rows (`closed_items`): the prompt names them with their tick evidence, and a `continue` whose only order names one of them is read as stop (`settle_closed_reraise`), so finished work is not ordered again.

    `local_batch` is `{"finished": k, "batch": n}` while a turbo batch fills on a no-PR branch (agent/plans/PLAN-turbo-local-first.md D6), else None: the prompt then carries M.JUDGE_LOCAL_BATCH and the sanitiser also strips an order to open a PR (LOCAL_BATCH_ORDERS).

    `transcript` is the lead's transcript path: an outstanding sweep or proof demand it already answers is discharged before the prompt is built (wl_classsweep.discharge_if_evidenced, wl_proofcheck.discharge_if_evidenced).

    The verdict may carry two lists beside the schema's fields: `still_owed`, the STILL OWED lines wl_checks renders on their own lines (wl_rules.render_owed), and `advisories`, the `sweep-ungrounded` texts of fresh fires git's file list does not ground (R20260924.18, R20260924.19). `fixset_instance` is `(root, commit ids)` for a commit-based fix-set, which grounds a fresh sweep's search in the fix's own diff (wl_classsweep.search_hits_instance).
    """
    exe = resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found (looked at PATH and ~/.local/bin/claude)"
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "judge workdir unusable: %s" % exc
    # THE CLASS SWEEP rides this call rather than making its own: the question "were the siblings swept?" is about the same fix-set the regression gate is already being asked about, and a second model call would double the cost of every fix stop to ask half a question. `extra` is extended BEFORE the schema is built so the two stay in lockstep -- a section the prompt asks for is a
    # field the schema requires.
    #
    # LOADED UNCONDITIONALLY (agent/plans/PLAN-sweep-obligation-carry-forward.md), where it used to be forced to `None` on a fix stop. The forced `None` was itself the bug: apply_verdict never saw the outstanding demand at all on exactly the stops where a fresh fix-set's answer would otherwise overwrite or clear it. `sweep_asked`/`proof_asked` tell CS.apply_verdict/PF.apply_verdict
    # WHICH question this stop actually asked, so a fresh fire displaces the old demand into its `owed` slot instead of destroying it, and a fresh silent/degraded answer -- which is about a DIFFERENT fix-set -- leaves the old demand alone rather than discharging it.
    fix_stop_now = is_fix_stop(extra)
    # NOTHING OF THE LEAD'S IS LEFT (agent/plans/PLAN-stop-hook-retro-20260924.md R.1): a tick-based fix-set whose every dirty file a live writer is still editing is that writer's work in flight, so no fresh sweep or proof is asked about it. The regression-gate question still is, and an outstanding demand is still followed up. A commit-based fix-set never takes this arm.
    # R20260925.2: a tick answered by its own writers' files (`item-writers`) with none of them still dirty has nothing uncommitted left to sweep or prove either; the commit that carried them is its own unit.
    sweep_proof_fresh = (
        with_riders
        and fix_stop_now
        and not (
            fixset_provenance in ("status-minus-live-writers", "item-writers") and not fixset_files
        )
    )
    sweep_outstanding = (
        CS.discharge_if_evidenced(CS.load_outstanding(), transcript) if with_riders else None
    )
    sweep_extra = (
        CS.prompt_section(sweep_proof_fresh, sweep_outstanding, transcript) if with_riders else ""
    )
    sweep_asked = "fresh" if sweep_proof_fresh else "followup"
    # THE PROOF OBLIGATION rides the same call for the same reason the class sweep does: the question is about the same fix-set the regression gate already shows the judge, and a second model call would double the cost of every fix stop.
    # DISCHARGED FROM THE TRANSCRIPT like the sweep above (R20260924.18): a shape-cluster diff the lead already ran on the demand's scope answers the follow-up. It was used raw until then, and proof STILL OWED rode 16:10:30, 16:23:57 and 16:29:10 on 2026-09-24.
    proof_outstanding = (
        PF.discharge_if_evidenced(PF.load_outstanding(), transcript) if with_riders else None
    )
    proof_extra = PF.prompt_section(sweep_proof_fresh, proof_outstanding) if with_riders else ""
    proof_asked = "fresh" if sweep_proof_fresh else "followup"
    # THE BRAVE-DEFAULT rule rides the same call on its own trigger: a parked decision whose DEFAULT does nothing. Its trigger is the remaining list, not `extra`, so the two rules are independent and either may be asked alone.
    #
    # NOT ON A FIX STOP. A regression-gate stop is already asking the judge to rule on a fix's test coverage AND its sibling sweep; adding "and by the way, is that parked question's DEFAULT brave enough" makes one call carry three unrelated judgements, and the parked question is the one least connected to what the session just did. It is not dropped, only deferred: the trigger is
    # the remaining list, which does not go away, so the same item is asked about on the next stop that is not a fix stop.
    brave_extra = "" if fix_stop_now or not with_riders else BD.prompt_section(remaining_lines)
    # GROUND THE SWEEP/PROOF QUESTIONS IN A REAL FILE LIST, computed by git rather than trusted from the model's own prose -- see wl_reggate.fixset_files. Injected only when the caller computed one AND a sweep/proof question is actually being asked, so an ordinary judge call carries no new tokens. `fixset_files is None` (the caller could not compute it, or this is a call site that
    # has not adopted the parameter yet) means NO claim, never "the tree is clean" -- conflating the two would accuse a fired finding of being ungrounded on missing data rather than on git's own evidence.
    ground_extra = ""
    if fixset_files is not None and (sweep_extra or proof_extra):
        shown = fixset_files[:40]
        ground_extra = M.FIXSET_GROUND_TRUTH % {
            "count": len(fixset_files),
            "how": M.FIXSET_PROVENANCE.get(fixset_provenance, M.FIXSET_PROVENANCE[None]),
            "files": "\n".join("  " + f for f in shown)
            or "  (none -- git shows a clean tree and nothing between the fix marker and HEAD)",
            "more": "\n  (+%d more)" % (len(fixset_files) - 40) if len(fixset_files) > 40 else "",
        }
    extra = (extra or "") + ground_extra + sweep_extra + proof_extra + brave_extra
    prompt = M.JUDGE_PROMPT % {
        "streak": streak,
        "remaining": "\n".join("  " + r for r in remaining_lines[:20]) or "  (none tracked)",
        "leases": leases,
        "loop": loop_desc,
        "message": (message or "(the session produced no text)")[-6000:],
        "citations": citations or "  (none cited)",
        "traps": "\n".join("  - " + h for h in (traps or [])) or "  (none recorded)",
    } + (extra or "")
    if closed:
        # After `extra`, never inside it, for the reason given for the local batch below.
        prompt += M.JUDGE_CLOSED_ITEMS % "\n".join(
            "  #%s %s\n      closed with: %s"
            % (cid, text[:120], (evidence or "(no evidence recorded)")[:200])
            for cid, text, evidence in closed[:CLOSED_SHOWN]
        )
    quiet_bases = report_bases_quiet(effort_level)
    schema = judge_schema_for(extra)
    if quiet_bases:
        # After `extra`, never inside it, like the two sections around it: judge_schema_for reads `extra`, and `basis` is required here rather than through a marker.
        prompt += JUDGE_BASIS
        schema = copy.deepcopy(schema)
        schema["required"] = [*schema["required"], "basis"]
    if local_batch:
        # After `extra`, never inside it: is_fix_stop and judge_schema_for read `extra`, and this paragraph asks for no schema field.
        prompt += M.JUDGE_LOCAL_BATCH % {
            "finished": int(local_batch.get("finished") or 0),
            "batch": int(local_batch.get("batch") or 1),
        }
    env = dict(os.environ)
    # THE RECURSION GUARD. `claude -p` fires this very hook; --settings does not suppress it. Without this line the hook forks itself forever.
    env["STOPHOOK_CHILD"] = "1"
    argv = [
        exe,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(wire_schema(schema)),
        "--model",
        wl_models.haiku_model(),
        # NO TOOLS. A judge reads a prompt and returns a verdict; it has never needed Bash, Read or Grep, and it was being handed all three in a cwd (/tmp/claude-worklist/.judge) that contains nothing -- while the sweep prompt told it "every path it names must actually exist in this repo". Tonight 8 of 21 sweep verdicts were DROPPED for naming paths that do not exist; a model that
        # cannot look must be told the paths instead of inventing them.
        #
        # WHAT THIS IS NOT: a fix for the no-output failure. That theory was that the model spent turn 1 on a tool call and ended on turn 2. Probed 2026-09-04 against the real CLI -- `--tools ""` with `--json-schema` returns a valid
        # verdict and STILL reports turns=2. So turn 2 is the normal shape here and
        # proves nothing about tools. The retry below remains the thing that handles a missing verdict.
        "--tools",
        "",
        "--max-budget-usd",
        JUDGE_BUDGET_USD,
    ]

    def _call():
        # THROUGH THE SHARED RUNNER, and for this call site that is not a tidy-up.
        # `claude -p` forks; `subprocess.run(capture_output=True, timeout=N)` kills
        # only the direct child on timeout and then blocks in communicate() on pipe ends a grandchild still holds. This runs inside the STOP HOOK, so that block is not a slow gate -- it is a worktree in which no session can stop. `wl_proc.run` gives the child its own session and signals the group.
        return wl_proc.run(
            argv,
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            cwd=str(workdir),
        )

    proc = _call()
    if proc.timed_out:
        return None, "judge timed out after %ds" % JUDGE_TIMEOUT_S
    if proc.returncode == wl_proc.SPAWN_FAILED_RC and not proc.stdout:
        return None, "judge could not be launched: %s" % proc.stderr.strip()
    if proc.returncode != 0:
        proc, _why = retry_schema_exhaustion("judge", proc, _call)
        if proc is None:
            return None, _why
    try:
        env_out = json.loads(proc.stdout)
    except ValueError:
        return None, "judge returned unparseable stdout: %s" % (proc.stdout or "")[-300:]
    if env_out.get("is_error"):
        return None, "judge reported is_error (subtype=%s, api=%s)" % (
            env_out.get("subtype"),
            env_out.get("api_error_status"),
        )
    out = clamp_to_schema(env_out.get("structured_output"), schema)
    if not isinstance(out, dict) or out.get("verdict") not in ("stop", "continue"):
        # ONE RETRY, and only on THIS path. The call succeeded at every level the code can check -- exit 0, is_error false, subtype success -- and simply ended its turn without emitting the schema. That is a sample, not a broken gate, and treating it as a broken gate is worse than the flake: the message
        # this would otherwise print ends by offering to set WORKLIST_JUDGE=off.
        #
        # Measured 2026-09-04, which is why this exists: a stop returned
        # `stop_reason=end_turn; turns=2; cost=$0.1317 of budget $0.25` and no output.
        # The identical call, same schema and same budget, answered correctly on the very next attempt -- so the session was blocked, and pointed at a disable
        # switch, by one sample.
        #
        # NOT a contradiction of the "sanitise rather than re-ask" rule below: that one is about a verdict that ARRIVED carrying a forbidden instruction, where a second sample buys nothing a rewrite cannot do deterministically. Here nothing arrived at all, so there is nothing to rewrite.
        #
        # Bounded three ways: exactly once, never after a transport failure, and never when the budget was the likely cause.
        if _budget_headroom(env_out):
            first = _explain_no_output("judge", env_out, out)
            try:
                proc = _call()
            except (subprocess.TimeoutExpired, OSError):
                return None, first + "; the single retry could not be launched"
            if proc.returncode == 0:
                try:
                    env_out = json.loads(proc.stdout)
                except ValueError:
                    env_out = {}
                out = (
                    clamp_to_schema(env_out.get("structured_output"), schema)
                    if isinstance(env_out, dict)
                    else None
                )
            if not isinstance(out, dict) or out.get("verdict") not in ("stop", "continue"):
                return (
                    None,
                    "%s; RETRIED ONCE and it produced no verdict either, so this is not one bad sample -- %s"
                    % (
                        first,
                        _explain_no_output("retry", env_out, out),
                    ),
                )
        else:
            return None, _explain_no_output("judge", env_out, out)
    # BEFORE sanitize_next_action, deliberately: the search command and the braver default are the MODEL's text, so they go through the operator-only filter like any other next_action rather than around it.
    fired = False
    if sweep_extra:
        kind, note = CS.apply_verdict(
            out,
            sweep_outstanding,
            fixset_files=fixset_files,
            asked=sweep_asked,
            instance=fixset_instance,
        )
        fired = kind == "fire"
        if kind == "ungrounded":
            # R20260924.19: queued by wl_checks as the `sweep-ungrounded` advisory, never a block.
            out.setdefault("advisories", []).append(note)
        if kind == "degraded":
            # Never a block (see wl_classsweep FAIL SEMANTICS), but never silent either: a paid question that produced no answer must be visible in the one field the session always reads.
            out["reason"] = ("%s [class-sweep not judged: %s]" % (out.get("reason", ""), note))[
                :400
            ]
    if proof_extra:
        # BOTH RULES MAY FIRE ON ONE STOP, deliberately, on the same reasoning apply_order documents: a verdict already `continue` is APPENDED to, never overwritten, so a class-sweep order and a proof order both reach the session rather than one silently losing to the other.
        kind, note = PF.apply_verdict(
            out, proof_outstanding, fixset_files=fixset_files, asked=proof_asked
        )
        fired = fired or kind == "fire"
        if kind == "ungrounded":
            out.setdefault("advisories", []).append(note)
        if kind == "degraded":
            out["reason"] = (
                "%s [proof-obligation not judged: %s]" % (out.get("reason", ""), note)
            )[:400]
    if brave_extra and not fired:
        # ONE ORDER PER STOP. A live defect still in the tree outranks a parked decision, and two orders in one block is how a block stops being read. Skipping is safe here and would not be for the sweep: this rule's trigger is the `[?]` itself, which is still there next stop.
        kind, note = BD.apply_verdict(out)
        fired = fired or kind == "fire"
        if kind == "degraded":
            out["reason"] = ("%s [brave-default not judged: %s]" % (out.get("reason", ""), note))[
                :400
            ]
    if not fired:
        out = settle_wait_only_continue(out)
        out = settle_closed_reraise(out, [c[0] for c in closed or ()])
        out = settle_by_effort(out, effort_level, local_batch=bool(local_batch))
    return sanitize_next_action(out, local_batch=bool(local_batch)), None


# ---- WHAT THE JUDGE IS TOLD IS ALREADY DONE (agent/plans/PLAN-stop-hook-effort.md E5) -------------
# The judge used to see the remaining items only, as their add text with the latest note. An item ticked a minute ago was absent rather than DONE, so a judge reading the session's message (which still talks about that work) ordered it again. It now sees the session's recently closed items with the evidence each was closed on, and a `continue` whose only order names one of them is read
# as stop, the same deterministic rewrite settle_wait_only_continue makes for a wait-only order.
CLOSED_HOURS = 24
CLOSED_SHOWN = 12
_ITEM_REF = re.compile(r"#([0-9a-f]{6,12})\b")


def closed_items(fold, owned, now=None, hours=CLOSED_HOURS):
    """(id, text, evidence) for the items `owned(owner)` accepts that are closed (`[x]`) and were last touched within `hours`, newest first. `text` is the item's base text, `evidence` the note it was closed with."""
    now = now or datetime.datetime.now(datetime.UTC)
    rows = []
    for rec in getattr(fold, "items", None) or ():
        if rec.get("state") != "x" or not owned(rec.get("owner")):
            continue
        try:
            at = datetime.datetime.fromisoformat(str(rec.get("upd") or ""))
        except ValueError:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=datetime.UTC)
        if (now - at).total_seconds() > hours * 3600:
            continue
        rows.append((str(rec.get("upd") or ""), rec))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [
        (
            str(r["id"]),
            str(r.get("basetext") or r.get("text") or ""),
            str(r.get("lastnote") or ""),
        )
        for _at, r in rows
    ]


def settle_closed_reraise(out, closed_ids):
    """`out` with a `continue` whose next action names only closed items (`#<id>`) read as `stop`, the rewrite named in its reason; anything else unchanged."""
    if out.get("verdict") != "continue" or not closed_ids:
        return out
    refs = set(_ITEM_REF.findall(out.get("next_action") or ""))
    closed = {str(c) for c in closed_ids}
    if not refs or not refs <= closed:
        return out
    out = dict(out)
    out["verdict"] = "stop"
    out["reason"] = (
        "%s [read as stop: the judge said continue, but its only order names closed item(s) %s]"
        % (out.get("reason", ""), ", ".join("#" + r for r in sorted(refs)))
    )[:400]
    out["next_action"] = ""
    return out


# ---- THE JUDGE OBEYS THE EFFORT TABLE (operator ruling 2026-10-14T09:27Z, agent/plans/PLAN-stop-hook-effort-tuning.md). At effort smart .claude/config/effort.json makes `no-remaining` and `out-of-sync` advise-only, and the judge still blocked on exactly those demands ("the message omits open items by id", "no loop schedule"): a second door to a block the table
# had closed. The judge now names what its `continue` rests on, and a continue resting only on a report key that does not block at this level is read as stop, its order queued under that key's own threshold (wl_checks hands `effort_advised` to outq_add, which drops it where the key is off). A continue resting on `work`, a rule's order, or a level where the key blocks stands.
REPORT_BASES = ("no-remaining", "out-of-sync")
JUDGE_BASIS = (
    "\nBASIS. Fill `basis` with what a `continue` rests on: `out-of-sync` when the only gap is "
    "that the message omits open tracked items by id, so the report disagrees with the tracked list; "
    "`no-remaining` when the only gap is the report's form (no '## Remaining' section, no schedule, "
    "a missing label or designation); `work` when any gap is work the session can still start or "
    "finish, including a report gap that comes with such work. With `stop`, fill `work`.\n"
)


def report_bases_quiet(level, table=None):
    """The REPORT_BASES keys that do not block at `level` (wl_effort.verdict); () with no level."""
    if not level:
        return ()
    return tuple(k for k in REPORT_BASES if wl_effort.verdict(k, level, table) != wl_effort.BLOCK)


def settle_by_effort(out, level, table=None, local_batch=False):
    """`out` with a `continue` whose `basis` is a report key that does not block at `level` read as `stop`, the judge's reason and order moved to `effort_advised` as one (key, text) pair; anything else unchanged.

    The order is sanitized on the way in (`sanitize_next_action`), because the field is blanked here and the sanitizer that closes `judge_verdict` never sees it again."""
    if out.get("verdict") != "continue":
        return out
    basis = out.get("basis")
    if basis not in report_bases_quiet(level, table):
        return out
    order = sanitize_next_action({"next_action": out.get("next_action")}, local_batch)[
        "next_action"
    ]
    advised = "Stop-gate judge, advised at effort %s (%s does not block at this level): %s%s" % (
        level,
        basis,
        str(out.get("reason") or "")[:300],
        " Next: %s" % str(order)[:200] if order else "",
    )
    out = dict(out)
    out["verdict"] = "stop"
    out["reason"] = (
        "%s [read as stop at effort %s: the continue rests only on %s, which advises here]"
        % (out.get("reason", ""), level, basis)
    )[:400]
    out["next_action"] = ""
    out["effort_advised"] = [(basis, advised)]
    return out


# A `continue` whose ONLY order is to wait contradicts itself: waiting on background work is what a legitimate stop does, and the harness wakes the session when that work exits. Seen 2026-10-05: verdict "continue", reason "Stop gate confirms pure background wait is legitimate; wake timer armed", next_action "Await worker output or timer expiry", which blocked a stop the judge's own reason allowed. Applied only when no rule placed an order this stop (a rule's order is real work and must survive), and only on the model's own next_action.
_WAIT_ONLY = re.compile(
    r"^\s*(?:await|wait(?:\s+for)?|keep\s+waiting|stand\s+by|idle|do\s+nothing|nothing)\b(?![^.;]*\b(?:then|and\s+then|after\s+that)\b)",
    re.IGNORECASE,
)


def settle_wait_only_continue(out):
    """`out` with a wait-only `continue` read as `stop`, the rewrite named in its reason; anything else unchanged."""
    if out.get("verdict") != "continue" or not _WAIT_ONLY.search(out.get("next_action") or ""):
        return out
    out = dict(out)
    out["verdict"] = "stop"
    out["reason"] = (
        "%s [read as stop: the judge said continue, but its only action was to wait (%s)]"
        % (out.get("reason", ""), (out.get("next_action") or "")[:80])
    )[:400]
    out["next_action"] = ""
    return out


# The judge advises; it does not get to order the three acts with their own guarded paths (merging and moving main go through /pr-merge at a plan's finish line, operator ruling 2026-10-02; releasing goes through CD). On 2026-08-09 it read a session sitting on four green stacked PRs and returned next_action "merge PRs 563, 565 and 566". The session declined, which is the right outcome but the wrong MECHANISM: it survived on the model's judgment at the moment of reading, and the whole point of this program is
# that judgment at the moment of reading is the faculty that fails. A later session, or a more tired one, reads an authoritative-sounding instruction from its own stop gate and complies.
#
# WHY SANITISE RATHER THAN RE-ASK. The deferral's default said reject and re-ask once. Re-asking buys a second sample from the same model that just produced the offending text, at another call's latency and cost, and it needs a loop bound to stay safe. Rewriting the field is deterministic, cannot loop, and is strictly safer than any second sample. The VERDICT is deliberately left
# untouched: stop or continue is the judge's actual job, the offence is only ever in the instruction, and altering the verdict here would collide with the no-escape-hatch invariant.
FORBIDDEN_ORDERS = (
    (re.compile(r"\bmerg(?:e|ing)\b", re.IGNORECASE), "merging"),
    (re.compile(r"\bpush(?:ing)?\b[^.]{0,40}\bmain\b", re.IGNORECASE), "pushing main"),
    (re.compile(r"\bmain\b[^.]{0,40}\bpush(?:ing)?\b", re.IGNORECASE), "pushing main"),
    (re.compile(r"\b(?:cut|publish|ship)\w*\b[^.]{0,30}\brelease\b", re.IGNORECASE), "releasing"),
    (re.compile(r"\brelease\b[^.]{0,20}\b(?:now|it|the\s+\w+)\b", re.IGNORECASE), "releasing"),
    (re.compile(r"\bgh\s+pr\s+merge\b", re.IGNORECASE), "merging"),
)

# Hard limit 2 of wl_defersettle: its standing-rule catalog may never carry an operator-reserved order. Checked here because this is where FORBIDDEN_ORDERS exists, and wl_defersettle is imported before it does.
DS.check_catalog(FORBIDDEN_ORDERS)


# The orders a filling turbo batch forbids (agent/plans/PLAN-turbo-local-first.md D6): the PR opens once, when the batch completes, and the hook's own LOOP NEXT block says when. Applied only while `local_batch` is set, so under `turbo_push: pr` (and turbo off) "open the draft PR" stays a legitimate next action.
LOCAL_BATCH_ORDERS = (
    (re.compile(r"\bgh\s+pr\s+create\b", re.IGNORECASE), "opening a PR"),
    (re.compile(r"\bopen\s+(?:a|the)\s+(?:draft\s+)?PR\b", re.IGNORECASE), "opening a PR"),
)


# ---- ADVICE RULES (agent/plans/PLAN-stop-hook-effort.md E5): orders the judge may not give because a repo rule it cannot see decides them. Checked in order after FORBIDDEN_ORDERS; the first match rewrites next_action with its own message.
#
# THE RELEASE-AGE WINDOW FIRST. On 2026-10-14 the judge ordered "apply the 8.7.0 pin now" for a release still inside the freshness window of .ci/config/release-age.json. The judge has no publish date at stop time, and the freshness gates that do (scripts/lib/release-age.ts, through check-deps, the pin gates and go_deps) decide when a version may land, so every order to apply a version pin, bump or upgrade is treated as possibly inside the soak and stripped.
RELEASE_AGE_REL = ".ci/config/release-age.json"
_VERSION = r"v?\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?"
_PIN_ORDER = re.compile(
    r"\b(?:apply|land|pin|bump|upgrade|update|install|move)\w*\b[^.;]{0,60}?\b%s\b|\b%s\b[^.;]{0,40}?\b(?:pin|bump|upgrade)\b"
    % (_VERSION, _VERSION),
    re.IGNORECASE,
)


def release_age_minutes(root=None):
    """`minimum_release_age_minutes` from .ci/config/release-age.json, or None when it cannot be read (the rule still applies; the message then names the file instead of the number)."""
    base = pathlib.Path(root) if root else pathlib.Path(__file__).resolve().parents[3]
    try:
        got = json.loads((base / RELEASE_AGE_REL).read_text(encoding="utf-8"))
        return int(got["minimum_release_age_minutes"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _release_age_message(action):
    minutes = release_age_minutes()
    window = (
        "%d minutes, then the next UTC midnight" % minutes
        if minutes is not None
        else "the window in %s" % RELEASE_AGE_REL
    )
    return M.V_JUDGE_RELEASE_AGE_REJECTED % (window, action[:120])


ADVICE_RULES = ((_PIN_ORDER, _release_age_message),)


def sanitize_next_action(out, local_batch=False):
    """Strip an operator-only directive from a judge verdict, in place, then an order a repo rule decides (ADVICE_RULES: a version pin inside the release-age soak), and with `local_batch` an order to open a PR before the batch completes (LOCAL_BATCH_ORDERS).

    Matches on the ORDER, not on politeness: "merge 563" and "you should probably merge 563" are the same instruction. Deliberately narrow about `release`, since "release notes" and "the release channel" are ordinary nouns a legitimate next action may name, while "cut the release" is an order.
    """
    action = out.get("next_action")
    if not isinstance(action, str) or not action.strip():
        return out
    for pattern, label in FORBIDDEN_ORDERS:
        if pattern.search(action):
            out["next_action"] = M.V_JUDGE_ORDER_REJECTED % (label, action[:120])
            return out
    for pattern, message in ADVICE_RULES:
        if pattern.search(action):
            out["next_action"] = message(action)
            return out
    if local_batch:
        for pattern, _label in LOCAL_BATCH_ORDERS:
            if pattern.search(action):
                out["next_action"] = M.V_JUDGE_BATCH_ORDER_REJECTED % (action[:120],)
                return out
    return out
