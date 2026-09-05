"""wl_judge: the stop-legitimacy judge call and its v10 verdict cache.

Fail CLOSED by contract: every error path returns an error string, and the
caller turns that into a block. See "NO ESCAPE HATCH" in worklist.py.
"""

import copy
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import time

import wl_bravedefault as BD
import wl_classsweep as CS
import worklist_messages as M

# v5: no cap. Kept as a name so the counter file (used only to TELL the judge
# it is repeating itself) reads clearly.
JUDGE_MODEL = os.environ.get("WORKLIST_JUDGE_MODEL", "claude-haiku-4-5-20251001")
# Measured on 2026-07-29 with --json-schema: haiku warm $0.011-$0.026 per call
# at 4.9-20.0s; sonnet $0.231 at 12.1s for the same judgement. Haiku it is.
# MEASURED, not guessed (2026-08-05): at $0.10 the judge died mid-run with
# subtype=error_max_budget_usd at cost $0.1025, and reported it as the
# unactionable "judge exited 1: " because the envelope goes to stdout, which the
# failure path was not reading (see _explain_failed_exit). The cap is a post-hoc
# between-turns stop, not a ceiling, so it must sit clear of the real cost rather
# than at it: a trivial prompt in a project cwd already reached $0.1025, while the
# same prompt in the judge's isolated workdir cost $0.0205. $0.25 leaves room for
# the real prompt (finding + context) without being open-ended.
JUDGE_BUDGET_USD = os.environ.get("WORKLIST_JUDGE_BUDGET_USD", "0.25")
# 240, raised from 120 on 2026-08-06 after a live timeout that BLOCKED a stop.
# The judge blocking on failure is correct and deliberate -- a judge that fails
# open is an escape hatch -- which is exactly why the budget must fit the
# WORST case rather than the typical one. Measured on this machine: a bare
# `reply OK` answers in 3.9s, while the real schema-constrained judge call took
# 30s (3 turns, stop_reason tool_use) with two Opus sub-agents running, and had
# exceeded 120s minutes earlier under heavier load. A stop happens precisely
# when the session is busiest, so the typical-case budget was the wrong one.
JUDGE_TIMEOUT_S = int(os.environ.get("WORKLIST_JUDGE_TIMEOUT_S", "240"))
JUDGE_DISABLED = os.environ.get("WORKLIST_JUDGE") == "off"

# v10 VERDICT CACHE. The judge is the dominant cost of a quiet-but-tracked
# stop (5-20s and $0.01-0.03, measured), and its question is a function of
# the WORLD and the MESSAGE. An identical world signature and an identical
# message within the TTL is the same question about the same facts, so a
# cached "stop" answers it for free -- the v9 fast-path argument, one level
# up. Fails toward calling the judge: only clean "stop" verdicts with no
# regression signals are ever cached, and any mismatch or corruption is a
# miss.
JUDGE_CACHE_MIN = int(os.environ.get("WORKLIST_JUDGE_CACHE_MIN", "30"))

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["stop", "continue"]},
        "reason": {"type": "string", "maxLength": 300},
        "next_action": {"type": "string", "maxLength": 200},
        # v7: OPTIONAL at the top level (verified: --json-schema accepts a
        # conditionally-required object and returns cleanly with it omitted,
        # so ONE schema, no variants), but its own properties are all
        # required. On a fix-signal stop a missing or malformed object is a
        # judge error and fails closed, same as an invalid verdict.
        # v11: the admission object, same optional-at-top-level shape as
        # regression_gate above and for the same reason. UNLIKE regression_gate,
        # a missing or malformed object here NEVER fails closed: this detector's
        # only consequence is a tracked item, and a session blocked by a phantom
        # regret learns to phrase things evasively, which costs more than the
        # detection is worth. See wl_admit.py.
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
        # v14: the class sweep. Same optional-at-the-top-level shape as
        # regression_gate and admission, made REQUIRED by judge_schema_for when
        # the prompt actually asks for it. Its failure semantics are the
        # admission's, NOT the regression gate's: a missing or malformed object
        # never fails closed, because the only thing this object can do is turn
        # a stop into a continue, so degrading loses a demand rather than
        # granting an exit. See wl_classsweep.
        "class_sweep": CS.CLASS_SWEEP_SCHEMA,
        # v14, the second of the pair. Same optional-at-the-top-level shape and
        # the same never-fails-closed semantics as class_sweep, asked on a
        # different trigger: a `[?]` in the remaining list that carries a
        # DEFAULT. See wl_bravedefault.
        "brave_default": BD.BRAVE_DEFAULT_SCHEMA,
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
                # v13: WHERE the regression test belongs. Before this, the only
                # answer the machinery could accept was a check-*.ts, so a
                # behavioural fix in the CLI or renet was told to assert that its
                # SOURCE still looks right -- a different claim from the one the
                # defect needs. The six surfaces are the ones ci.yml actually has;
                # `.claude/skills/testing/` routes between them.
                "surface": {
                    "type": "string",
                    "enum": ["gates", "e2e", "ops", "install", "unit", "hooks", "none"],
                },
                # The repo-relative path the case belongs in. Named by the judge
                # rather than matched against a list of globs, so a surface this
                # machinery has never heard of still has a checkable answer.
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
        # v12: OPTIONAL at the top level, same contract as regression_gate:
        # one schema, and on a stop that REQUESTED an audit a missing or
        # malformed array is a judge error that fails closed at the caller
        # (apply_defer_audit + R_AUDIT_MALFORMED).
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


# v16 TRIAGE. Same shape as JUDGE_SCHEMA (flat object, string enum) and the
# same transport, but DELIBERATELY the opposite failure semantics: the stop
# judge fails closed because it gates an exit, while triage is a decision aid
# on a CLI path, so an error degrades to the self-assessment printout and
# exit 0. See run_triage.
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

    A budget-exhausted call that produced nothing will exhaust it again; asking twice
    just doubles the bill for the same silence. Below 80% of the cap, whatever went
    wrong was not the cap.
    """
    cost = (env_out or {}).get("total_cost_usd")
    if not isinstance(cost, (int, float)):
        return False
    try:
        return cost < float(JUDGE_BUDGET_USD) * 0.8
    except (TypeError, ValueError):
        return False


# The CLI's own name for "the model could not produce an object matching the
# schema, and I gave up re-asking". It is a SAMPLE failing, not a transport or a
# configuration failing, which is why it is retried below rather than reported.
SCHEMA_EXHAUSTION = "error_max_structured_output_retries"


def retry_schema_exhaustion(label, proc, call):
    """(proc, None) to carry on, or (None, why) to give up, for a NON-ZERO exit.

    THE BUG THIS FIXES, measured 2026-09-04. A stop was blocked with
    "judge exited 1; subtype=error_max_structured_output_retries; turns=6;
    cost=$0.0112 of budget $0.25", and the message that follows such a failure
    tells the session the gate is broken and offers WORKLIST_JUDGE=off.

    Neither claim was true. The model was reachable (a probe answered), and the
    REAL call -- same schema, same model, same budget -- returned a valid verdict
    three times out of three at $0.05-0.06 each, which is five times what the
    failing run spent. So the run did not hit its cap and the schema is not
    unsatisfiable: one sample simply failed to emit a conforming object.

    That is the SAME condition the exit-0 path a few lines down already retries,
    and calls "a sample, not a broken gate". The two differ only in how the CLI
    reports them: wandering to the end of the turn exits 0 with
    structured_output null, while exhausting the CLI's own schema retries exits
    1 with this subtype. Keying the retry on the exit code rather than on what
    actually happened meant the identical failure was a flake in one spelling
    and a "BUG in the gate" in the other -- and the harsher spelling is the one
    that points a session at the disable switch.

    Bounded exactly as the other retry is: only this subtype, only with budget
    headroom (a call that spent its cap will spend it again), only once, and
    never after a transport failure -- a launch error or a timeout raises before
    reaching here and is not routed through this path at all.
    """
    first = _explain_failed_exit(label, proc)
    env_out = None
    try:
        env_out = json.loads(proc.stdout or "")
    except ValueError:
        env_out = None
    if not isinstance(env_out, dict) or env_out.get("subtype") != SCHEMA_EXHAUSTION:
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

    This is the shape a budget-capped schema-constrained call takes when it
    wanders: the transport worked, so none of the failure branches above fire,
    and the bare repr of `None` tells the reading session nothing. The envelope
    still carries the cost, the stop_reason and the turn count.
    """
    bits = ["%s produced no usable structured_output: %s" % (label, repr(out)[:200])]
    if isinstance(env_out, dict):
        bits.extend(_envelope_bits(env_out))
    return "; ".join(bits)


def _envelope_bits(env_out):
    """The actionable fields of a `claude -p` result envelope, as report bits.

    EXTRACTED 2026-08-26 because these lived only on the non-zero-exit path,
    and the failure that actually happened exits ZERO. A budget-capped,
    schema-constrained call that wanders can return exit 0, is_error false, and
    `structured_output: null` -- and the gate reported exactly that, "produced
    no usable structured_output: None", while the same envelope was holding the
    cost, the stop_reason and the turn count that name the cause. The next
    session then reads a line whose following sentence offers to DISABLE the
    gate, with no evidence either way. Measured the same day: a trivial
    schema-constrained haiku call costs $0.0566 of the $0.25 default, so a long
    prompt exhausting it is the expected failure, not an exotic one.
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

    THE BUG THIS FIXES (2026-08-05): these paths reported `proc.stderr` only, and
    the CLI writes its error ENVELOPE TO STDOUT, leaving stderr empty. The gate
    therefore surfaced the unactionable "judge exited 1: " with nothing after the
    colon, while stdout was holding is_error, the stop_reason, and the exact cost
    against the budget. The `is_error` branch further down never ran, because it
    sits behind returncode == 0. A judge that cannot say why it failed is an
    escape hatch wearing a gate's clothes -- the same swallowed-failure class the
    repo scans for, inside the thing that audits it.
    """
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

    Modeled on run_judge down to the recursion guard and the workdir, because
    the transport is the same and a second copy that drifts is a second bug.
    The CALLER decides what an error means; here every failure is simply
    reported, never swallowed, so a degraded triage can name what broke.
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
        return subprocess.run(
            [
                exe,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(TRIAGE_SCHEMA),
                "--model",
                JUDGE_MODEL,
                # NO TOOLS. A judge reads a prompt and returns a verdict; it has never needed
                # Bash, Read or Grep, and it was being handed all three in a cwd
                # (/tmp/claude-worklist/.judge) that contains nothing -- while the sweep prompt
                # told it "every path it names must actually exist in this repo". Tonight 8 of
                # 21 sweep verdicts were DROPPED for naming paths that do not exist; a model
                # that cannot look must be told the paths instead of inventing them.
                #
                # WHAT THIS IS NOT: a fix for the no-output failure. That theory was that the
                # model spent turn 1 on a tool call and ended on turn 2. Probed 2026-09-04
                # against the real CLI -- `--tools ""` with `--json-schema` returns a valid
                # verdict and STILL reports turns=2. So turn 2 is the normal shape here and
                # proves nothing about tools. The retry below remains the thing that handles a
                # missing verdict.
                "--tools",
                "",
                "--max-budget-usd",
                JUDGE_BUDGET_USD,
            ],
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            check=False,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
        )

    try:
        proc = _call()
    except subprocess.TimeoutExpired:
        return None, "triage timed out after %ds" % JUDGE_TIMEOUT_S
    except OSError as exc:
        return None, "triage could not be launched: %s" % exc
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
    out = env_out.get("structured_output")
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

    run_judge, run_triage and run_admission are three near-identical copies of
    this, and wl_judge's own comment on the second one ("the transport is the
    same and a second copy that drifts is a second bug") is the argument against
    adding a fourth. Only the NEW caller is routed through here: folding the
    three live paths in would be a behaviour change to the stop gate itself,
    which is not this change's business. That is a named residual, not an
    oversight -- the next module that needs a model call should use this and the
    three copies should follow when something else forces them open.

    Failure semantics are the CALLER's business, exactly as for run_triage: every
    error is reported, never swallowed.
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
        return subprocess.run(
            [
                exe,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(schema),
                "--model",
                JUDGE_MODEL,
                # NO TOOLS. A judge reads a prompt and returns a verdict; it has never needed
                # Bash, Read or Grep, and it was being handed all three in a cwd
                # (/tmp/claude-worklist/.judge) that contains nothing -- while the sweep prompt
                # told it "every path it names must actually exist in this repo". Tonight 8 of
                # 21 sweep verdicts were DROPPED for naming paths that do not exist; a model
                # that cannot look must be told the paths instead of inventing them.
                #
                # WHAT THIS IS NOT: a fix for the no-output failure. That theory was that the
                # model spent turn 1 on a tool call and ended on turn 2. Probed 2026-09-04
                # against the real CLI -- `--tools ""` with `--json-schema` returns a valid
                # verdict and STILL reports turns=2. So turn 2 is the normal shape here and
                # proves nothing about tools. The retry below remains the thing that handles a
                # missing verdict.
                "--tools",
                "",
                "--max-budget-usd",
                JUDGE_BUDGET_USD,
            ],
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            check=False,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
        )

    try:
        proc = _call()
    except subprocess.TimeoutExpired:
        return None, "%s timed out after %ds" % (label, JUDGE_TIMEOUT_S)
    except OSError as exc:
        return None, "%s could not be launched: %s" % (label, exc)
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
    out = env_out.get("structured_output")
    payload = extract(out) if isinstance(out, dict) else None
    if payload is None:
        return None, _explain_no_output(label, env_out, out)
    return payload, None


def run_planfid(plan_text, items_rendered, message):
    """(plan_fidelity_dict, error_string). Exactly one is non-None.

    DEGRADES, never blocks on its own unavailability. See wl_planfid's header:
    this check triggers on a heuristic about item shape rather than on an
    artifact, so an unreachable model must not wall in every session that has an
    approved plan. The caller reports the error on the systemMessage line.
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

    The standalone path, for a stop where the prefilter fired but the main judge
    was never invoked (nothing else remained to judge). Modeled on run_triage
    down to the recursion guard and the workdir, because the transport is the
    same and a second copy that drifts is a second bug.

    It DEGRADES, never blocks, like run_triage and unlike run_judge. An admission
    detector that could block on its own unavailability would punish a session
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
        return subprocess.run(
            [
                exe,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(ADMISSION_SCHEMA),
                "--model",
                JUDGE_MODEL,
                # NO TOOLS. A judge reads a prompt and returns a verdict; it has never needed
                # Bash, Read or Grep, and it was being handed all three in a cwd
                # (/tmp/claude-worklist/.judge) that contains nothing -- while the sweep prompt
                # told it "every path it names must actually exist in this repo". Tonight 8 of
                # 21 sweep verdicts were DROPPED for naming paths that do not exist; a model
                # that cannot look must be told the paths instead of inventing them.
                #
                # WHAT THIS IS NOT: a fix for the no-output failure. That theory was that the
                # model spent turn 1 on a tool call and ended on turn 2. Probed 2026-09-04
                # against the real CLI -- `--tools ""` with `--json-schema` returns a valid
                # verdict and STILL reports turns=2. So turn 2 is the normal shape here and
                # proves nothing about tools. The retry below remains the thing that handles a
                # missing verdict.
                "--tools",
                "",
                "--max-budget-usd",
                JUDGE_BUDGET_USD,
            ],
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            check=False,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
        )

    try:
        proc = _call()
    except subprocess.TimeoutExpired:
        return None, "admission timed out after %ds" % JUDGE_TIMEOUT_S
    except OSError as exc:
        return None, "admission could not be launched: %s" % exc
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
    out = env_out.get("structured_output")
    if not isinstance(out, dict) or not isinstance(out.get("admission"), dict):
        return None, _explain_no_output("admission", env_out, out)
    return out["admission"], None


def apply_defer_audit(rows, batch):
    """(kind, valids, orders) from the judge's defer_audit answer.

    kind is 'ok' or 'malformed'; valids is [(id, upd_stamp, reason)] to bank,
    orders is [(id, order_text)] to enforce. STRICT by contract: every
    audited item must come back with a usable verdict, and anything else --
    no array, a non-dict entry, an invalid verdict, a batch id missing --
    is 'malformed', which the caller turns into a fail-closed block. An id
    the judge invented is ignored rather than acted on: reopening an item
    nobody audited would let a hallucination edit the store.
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


def resolve_claude():
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def msg_hash(message):
    return hashlib.sha1((message or "").encode("utf-8", "replace")).hexdigest()[:16]


def cached_stop_verdict(state_doc, sig, message):
    """A previously banked 'stop' verdict for this exact world+message, or
    None. Any doubt is a miss."""
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


# The fix-signal is a SEPARATE prompt section (M.REGGATE_PROMPT, appended as `extra`),
# but v7 shipped ONE schema in which `regression_gate` is optional at the top level. So on
# a fix-signal stop the model could satisfy the schema while omitting the object entirely,
# and `wl_reggate` then reports "regression_gate missing or incomplete: None" and blocks by
# the no-escape-hatch rule. That is the gate refusing to be bypassed, which is correct, but
# the session is blocked by a JUDGE error rather than by anything it did. Observed live
# 2026-08-28.
#
# The fix is upstream of the failure: when the prompt ASKS for the object, the schema
# REQUIRES it. Nothing here weakens the fail-closed path; a malformed object still blocks.
_REGGATE_MARKER = "A FIX LANDED THIS TURN"


# --------------------------------------------------------------------------
# THE JUDGE LOG, and the only honest source of the judge's own streak.
#
# The prompt used to say "Consecutive times this gate has already said
# continue: N" and was handed `worklist.blocks-<me8>` -- the count of ALL stop
# blocks, from every check in the battery. On 2026-09-04 that number read 69
# while the judge itself had spoken a handful of times. The sentence asks the
# judge to distrust its own advice after 3, so a counter that runs 20x fast
# turns a useful brake into permanent self-doubt about a history that did not
# happen.
#
# A verdict log fixes the number and is worth having on its own: it is the only
# record of what the judge actually said, which until now existed nowhere.
# --------------------------------------------------------------------------

JUDGE_LOG_CAP = 400


def judge_log_path(worklist, me8):
    """Per-session, beside the store, same convention as the block counter."""
    return worklist.with_suffix(".judge-%s.jsonl" % me8)


def log_verdict(path, verdict, reason, error=None):
    """Append one line. Best-effort: a log that cannot be written must never
    take a stop with it, so every failure here is swallowed deliberately."""
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
    """Consecutive trailing `continue` verdicts. Anything else -- a stop, an
    unavailable judge -- ends the run, because the sentence in the prompt is
    about advice that kept not landing, and a stop means it landed."""
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

    ONE rule, applied per marker: regression_gate for _REGGATE_MARKER,
    class_sweep for CS.SWEEP_MARKER, brave_default for BD.BRAVE_MARKER. The
    three markers are INDEPENDENT and must not collapse into one boolean: the
    sweep section is also appended on a carried-forward demand, and the brave
    section triggers on the remaining list, so either can arrive on a stop where
    no fix landed at all. Requiring regression_gate on such a stop would fail
    the judge closed for a question nobody asked.
    """
    text = extra or ""
    wanted = []
    if _REGGATE_MARKER in text:
        wanted.append("regression_gate")
    if CS.SWEEP_MARKER in text:
        wanted.append("class_sweep")
    if BD.BRAVE_MARKER in text:
        wanted.append("brave_default")
    missing = [k for k in wanted if k not in JUDGE_SCHEMA["required"]]
    if not missing:
        return JUDGE_SCHEMA
    schema = copy.deepcopy(JUDGE_SCHEMA)
    schema["required"] = [*schema["required"], *missing]
    return schema


def run_judge(
    remaining_lines, leases, message, streak, loop_desc, citations=None, extra="", traps=None
):
    """(verdict_dict, error_string). Exactly one is non-None."""
    exe = resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found (looked at PATH and ~/.local/bin/claude)"
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "judge workdir unusable: %s" % exc
    # THE CLASS SWEEP rides this call rather than making its own: the question
    # "were the siblings swept?" is about the same fix-set the regression gate
    # is already being asked about, and a second model call would double the
    # cost of every fix stop to ask half a question. `extra` is extended BEFORE
    # the schema is built so the two stay in lockstep -- a section the prompt
    # asks for is a field the schema requires.
    sweep_outstanding = None if _REGGATE_MARKER in (extra or "") else CS.load_outstanding()
    sweep_extra = CS.prompt_section(_REGGATE_MARKER in (extra or ""), sweep_outstanding)
    # THE BRAVE-DEFAULT rule rides the same call on its own trigger: a parked
    # decision whose DEFAULT does nothing. Its trigger is the remaining list, not
    # `extra`, so the two rules are independent and either may be asked alone.
    #
    # NOT ON A FIX STOP. A regression-gate stop is already asking the judge to
    # rule on a fix's test coverage AND its sibling sweep; adding "and by the
    # way, is that parked question's DEFAULT brave enough" makes one call carry
    # three unrelated judgements, and the parked question is the one least
    # connected to what the session just did. It is not dropped, only deferred:
    # the trigger is the remaining list, which does not go away, so the same
    # item is asked about on the next stop that is not a fix stop.
    brave_extra = "" if is_fix_stop(extra) else BD.prompt_section(remaining_lines)
    extra = (extra or "") + sweep_extra + brave_extra
    prompt = M.JUDGE_PROMPT % {
        "streak": streak,
        "remaining": "\n".join("  " + r for r in remaining_lines[:20]) or "  (none tracked)",
        "leases": leases,
        "loop": loop_desc,
        "message": (message or "(the session produced no text)")[-6000:],
        "citations": citations or "  (none cited)",
        "traps": "\n".join("  - " + h for h in (traps or [])) or "  (none recorded)",
    } + (extra or "")
    env = dict(os.environ)
    # THE RECURSION GUARD. `claude -p` fires this very hook; --settings does not
    # suppress it. Without this line the hook forks itself forever.
    env["STOPHOOK_CHILD"] = "1"
    argv = [
        exe,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(judge_schema_for(extra)),
        "--model",
        JUDGE_MODEL,
        # NO TOOLS. A judge reads a prompt and returns a verdict; it has never needed
        # Bash, Read or Grep, and it was being handed all three in a cwd
        # (/tmp/claude-worklist/.judge) that contains nothing -- while the sweep prompt
        # told it "every path it names must actually exist in this repo". Tonight 8 of
        # 21 sweep verdicts were DROPPED for naming paths that do not exist; a model
        # that cannot look must be told the paths instead of inventing them.
        #
        # WHAT THIS IS NOT: a fix for the no-output failure. That theory was that the
        # model spent turn 1 on a tool call and ended on turn 2. Probed 2026-09-04
        # against the real CLI -- `--tools ""` with `--json-schema` returns a valid
        # verdict and STILL reports turns=2. So turn 2 is the normal shape here and
        # proves nothing about tools. The retry below remains the thing that handles a
        # missing verdict.
        "--tools",
        "",
        "--max-budget-usd",
        JUDGE_BUDGET_USD,
    ]

    def _call():
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            check=False,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
        )

    try:
        proc = _call()
    except subprocess.TimeoutExpired:
        return None, "judge timed out after %ds" % JUDGE_TIMEOUT_S
    except OSError as exc:
        return None, "judge could not be launched: %s" % exc
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
    out = env_out.get("structured_output")
    if not isinstance(out, dict) or out.get("verdict") not in ("stop", "continue"):
        # ONE RETRY, and only on THIS path. The call succeeded at every level the
        # code can check -- exit 0, is_error false, subtype success -- and simply
        # ended its turn without emitting the schema. That is a sample, not a broken
        # gate, and treating it as a broken gate is worse than the flake: the message
        # this would otherwise print ends by offering to set WORKLIST_JUDGE=off.
        #
        # Measured 2026-09-04, which is why this exists: a stop returned
        # `stop_reason=end_turn; turns=2; cost=$0.1317 of budget $0.25` and no output.
        # The identical call, same schema and same budget, answered correctly on the
        # very next attempt -- so the session was blocked, and pointed at a disable
        # switch, by one sample.
        #
        # NOT a contradiction of the "sanitise rather than re-ask" rule below: that
        # one is about a verdict that ARRIVED carrying a forbidden instruction, where
        # a second sample buys nothing a rewrite cannot do deterministically. Here
        # nothing arrived at all, so there is nothing to rewrite.
        #
        # Bounded three ways: exactly once, never after a transport failure, and never
        # when the budget was the likely cause.
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
                out = env_out.get("structured_output") if isinstance(env_out, dict) else None
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
    # BEFORE sanitize_next_action, deliberately: the search command and the
    # braver default are the MODEL's text, so they go through the operator-only
    # filter like any other next_action rather than around it.
    fired = False
    if sweep_extra:
        kind, note = CS.apply_verdict(out, sweep_outstanding)
        fired = kind == "fire"
        if kind == "degraded":
            # Never a block (see wl_classsweep FAIL SEMANTICS), but never
            # silent either: a paid question that produced no answer must be
            # visible in the one field the session always reads.
            out["reason"] = ("%s [class-sweep not judged: %s]" % (out.get("reason", ""), note))[
                :400
            ]
    if brave_extra and not fired:
        # ONE ORDER PER STOP. A live defect still in the tree outranks a parked
        # decision, and two orders in one block is how a block stops being read.
        # Skipping is safe here and would not be for the sweep: this rule's
        # trigger is the `[?]` itself, which is still there next stop.
        kind, note = BD.apply_verdict(out)
        if kind == "degraded":
            out["reason"] = ("%s [brave-default not judged: %s]" % (out.get("reason", ""), note))[
                :400
            ]
    return sanitize_next_action(out), None


# The judge advises; it does not get to order the three things reserved to the
# operator. On 2026-08-09 it read a session sitting on four green stacked PRs and
# returned next_action "merge PRs 563, 565 and 566". The session declined, which is
# the right outcome but the wrong MECHANISM: it survived on the model's judgment at
# the moment of reading, and the whole point of this program is that judgment at the
# moment of reading is the faculty that fails. A later session, or a more tired one,
# reads an authoritative-sounding instruction from its own stop gate and complies.
#
# WHY SANITISE RATHER THAN RE-ASK. The deferral's default said reject and re-ask
# once. Re-asking buys a second sample from the same model that just produced the
# offending text, at another call's latency and cost, and it needs a loop bound to
# stay safe. Rewriting the field is deterministic, cannot loop, and is strictly
# safer than any second sample. The VERDICT is deliberately left untouched: stop or
# continue is the judge's actual job, the offence is only ever in the instruction,
# and altering the verdict here would collide with the no-escape-hatch invariant.
FORBIDDEN_ORDERS = (
    (re.compile(r"\bmerg(?:e|ing)\b", re.IGNORECASE), "merging"),
    (re.compile(r"\bpush(?:ing)?\b[^.]{0,40}\bmain\b", re.IGNORECASE), "pushing main"),
    (re.compile(r"\bmain\b[^.]{0,40}\bpush(?:ing)?\b", re.IGNORECASE), "pushing main"),
    (re.compile(r"\b(?:cut|publish|ship)\w*\b[^.]{0,30}\brelease\b", re.IGNORECASE), "releasing"),
    (re.compile(r"\brelease\b[^.]{0,20}\b(?:now|it|the\s+\w+)\b", re.IGNORECASE), "releasing"),
    (re.compile(r"\bgh\s+pr\s+merge\b", re.IGNORECASE), "merging"),
)


def sanitize_next_action(out):
    """Strip an operator-only directive from a judge verdict, in place.

    Matches on the ORDER, not on politeness: "merge 563" and "you should probably
    merge 563" are the same instruction. Deliberately narrow about `release`, since
    "release notes" and "the release channel" are ordinary nouns a legitimate next
    action may name, while "cut the release" is an order.
    """
    action = out.get("next_action")
    if not isinstance(action, str) or not action.strip():
        return out
    for pattern, label in FORBIDDEN_ORDERS:
        if pattern.search(action):
            out["next_action"] = M.V_JUDGE_ORDER_REJECTED % (label, action[:120])
            return out
    return out
