"""wl_shapedup: "is this the Nth copy of a shape you already have?"

THE QUESTION NOBODY ASKS. The stop judge asks two things -- did you sweep the class
(wl_classsweep), and is there a gate (wl_reggate). Neither asks whether the thing you just
wrote already exists three times, so every finding correctly answers "add a script + a
manifest entry + a workflow step + controls" and nothing is ever pointed at the
accumulated surface.

This repo reached that conclusion by hand THREE times and wrote it down each time:
`scripts/lib/shrink-only-baseline.ts:25-31` ("a class, not an instance... seven chances to
drift"), `.claude/hooks/pre-bash/block-adhoc-sanctioned.sh:4-8` (a new class is "a row
rather than a 22nd copy of this file"), and `scripts/check-shared-constant-duplication.ts`
(one constant existing twice while "nothing failed"). Three times a person noticed.

ITS OWN MODEL CALL, and the reason is a measurement rather than a preference. The approved
plan rode this rule on the existing judge call, paid for by trimming SWEEP_PROMPT's five
worked examples to three -- estimated at ~2,300 characters freed. Measured after the trim
landed (`eb34b3a47`): **62**. The five examples were ~700 characters in total. A fix stop
already carries 17,735 characters of rubric (JUDGE 5,762 + REGGATE 2,646 + SWEEP 5,683 +
BRAVE 3,644), and adding a fourth object unoffset degrades two rubrics that are calibrated
against operator-supplied worked examples. So this rule pays its own way: one extra
`claude -p` only on the stops where the COUNTER has already fired, which is rare by
construction.

THE COUNTER IS MECHANICAL AND COMES FIRST. `scripts/check-shape-duplication.ts` hashes
sliding 5-line windows over the gate families, seeded so the 219-span standing backlog is
silent, and fires only when a shape that was NOT already present reaches its third copy. A
model asked "is there duplication?" answers yes far too often; a counter answers only when
a real Nth instance lands. The model is never asked to FIND anything -- `instances` comes
from the counter and is not read back off the model, so it cannot be fabricated.
"""

import json
import os
import subprocess

import wl_judge
import wl_rules

SHAPE_MARKER = "IS THIS THE NTH COPY"

CONSOLIDATABLE = ("yes", "no", "already")

SHAPE_SCHEMA = {
    "type": "object",
    "properties": {
        "applicable": {"type": "boolean"},
        "shape": {"type": "string", "maxLength": 300},
        "harness": {"type": "string", "maxLength": 200},
        "consolidatable": {"type": "string", "enum": list(CONSOLIDATABLE)},
        "divergence": {"type": "string", "maxLength": 400},
        "instruction": {"type": "string", "maxLength": 300},
    },
    "required": ["applicable", "shape", "harness", "consolidatable", "divergence", "instruction"],
    "additionalProperties": False,
}

SHAPE_PROMPT = """
IS THIS THE NTH COPY of something this repo already has?

A mechanical counter has ALREADY found the duplication. It hashes 5-line windows over the
gate families and reports only shapes that were not present when it was seeded, so the
instances below are measured, not suspected. You are not being asked to find anything.

  SHAPE INSTANCES (file:line, from the counter):
%(instances)s

Answer ONE question: should these become one thing, and if not, what is the DIVERGENCE?

Three answers, and the middle one is a real answer rather than a hedge:

  yes       they are the same scaffolding and a shared piece should own it. Name the
            module that should, in `harness` -- an existing one if there is one.
  already   a shared module for this ALREADY exists and these copies simply do not use
            it. Name it in `harness`. This is checked against the disk: a module that
            does not exist, or that the instances do not import, is treated as `yes`.
  no        they look alike and are not one thing. `divergence` is REQUIRED and must be
            CONCRETE. Worked example from this repo: `run_gate()` is duplicated 23 times
            with THREE incompatible return contracts -- one echoes the exit code, one
            echoes PASS/FAIL, one propagates -- so extracting it verbatim would be wrong.
            "They are different" is not a divergence; "two accumulate and one exits" is.

WHAT IS NOT DUPLICATION, and the counter already excludes each, so if you see one the
counter has a bug and `no` with that as the divergence is the right answer:
  - an import preamble. Three files importing the same helper is ADOPTION; an import
    statement IS the consolidation.
  - a comment block. The prose explaining why a guard exists is why it is trustworthy.
  - a findings report. Measured across ten gates, ten distinct shapes: the sentence
    saying what failed IS the gate's value.

applicable=false only when the instances are not comparable at all -- generated files, a
vendored dependency, or a fixture whose whole point is to be a copy.

Fill `shape_dup`: applicable, shape (the pattern in one line, not a location), harness,
consolidatable, divergence, instruction (the concrete next step).
"""


def prompt_section(instances):
    """The prompt text, or "" when the counter found nothing."""
    if not instances:
        return ""
    body = "\n".join("    %s" % i for i in instances[:12])
    return SHAPE_PROMPT % {"instances": body}


def _clean(obj, key, limit):
    v = obj.get(key)
    return v.strip()[:limit] if isinstance(v, str) else ""


def harness_is_real(harness, root=None):
    """Does the named module exist on disk? A claim of prior consolidation is exactly the
    claim most worth checking, and one `os.path.exists` checks it."""
    if not harness:
        return False
    root = root or os.getcwd()
    cand = harness.split(":")[0].strip()
    return bool(cand) and os.path.exists(os.path.join(root, cand))


def read_verdict(out, root=None):
    """(kind, payload). kind is 'silent', 'fire' or 'degraded'.

    FAIL SEMANTICS are wl_classsweep's, not the regression gate's: a missing or malformed
    object NEVER fails closed. Degrading loses a demand; it can never grant an exit that
    was otherwise refused.
    """
    sd = out.get("shape_dup") if isinstance(out, dict) else None
    if not isinstance(sd, dict):
        return "degraded", "no shape_dup object: %s" % repr(sd)[:120]
    if not isinstance(sd.get("applicable"), bool):
        return "degraded", "shape_dup applicable is not a boolean"
    verdict = sd.get("consolidatable")
    if verdict not in CONSOLIDATABLE:
        return "degraded", "shape_dup consolidatable %r is not one of %s" % (
            verdict,
            CONSOLIDATABLE,
        )
    if not sd["applicable"]:
        return "silent", "not comparable: these copies are not one thing to merge"

    shape = _clean(sd, "shape", 300)
    if not shape:
        return "degraded", "shape_dup fired with no shape named"
    harness = _clean(sd, "harness", 200)
    divergence = _clean(sd, "divergence", 400)

    # THE EVIDENCE IS CHECKED AGAINST ITSELF, the way wl_classsweep.py:263 makes
    # `swept=true` with evidence_kind `none` fire anyway.
    if verdict == "no":
        # A refusal that names no divergence is not a refusal. Degraded rather than
        # fired: an unactionable block is the one thing these rules cannot afford.
        if len(divergence) < 20:
            return "degraded", "consolidatable=no with no concrete divergence named"
        return "silent", "not one thing: %s" % divergence[:160]
    if verdict == "already" and harness_is_real(harness, root):
        return "silent", "a shared module already exists: %s" % harness
    # `already` naming a module that is not on disk is a claim, not a fact, so it falls
    # through and fires -- with the harness it named, so the session can see the mistake.
    return "fire", {
        "shape": shape,
        "harness": harness,
        "instruction": _clean(sd, "instruction", 300),
    }


V_REASON = (
    "IS THIS THE NTH COPY. A counter found this shape at %d places, and it was not here "
    "when the seed was taken: %s"
)
V_ACTION = (
    "Extract the shared piece%s, or say which DIVERGENCE makes these not one thing. "
    "Triage it: .claude/hooks/stop/worklist.py --triage <you> '<the finding>'"
)


def enforce(out, payload, count):
    reason = V_REASON % (count, payload["shape"])
    into = " into %s" % payload["harness"] if payload["harness"] else ""
    wl_rules.apply_order(out, reason, V_ACTION % into)
    return "shape-dup: %s" % payload["shape"][:160]


# -- The latch: once per SHAPE per session ----------------------------------
#
# Keyed by the shape hash as well as the checkout, so a session authoring three gates in
# one family gets ONE consolidation question rather than three. Without it the observed
# 2026-09-01 pattern -- four separate commits, one gate each, same day -- produces four
# identical asks.

SHAPE_TTL_MIN = int(os.environ.get("WORKLIST_SHAPE_TTL_MIN", "120"))
SHAPE_MAX_FIRES = int(os.environ.get("WORKLIST_SHAPE_MAX_FIRES", "2"))


def demand_for(shape_hash):
    return wl_rules.Demand(
        "shapedup-%s" % (shape_hash or "none")[:12], SHAPE_TTL_MIN, SHAPE_MAX_FIRES
    )


def ask(instances):
    """Its OWN `claude -p`. (verdict_dict, error). Never raises."""
    exe = wl_judge.resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found"
    env = dict(os.environ)
    # THE RECURSION GUARD, same as run_judge and run_triage: `claude -p` fires the Stop
    # hook, and without this the rule would ask itself about itself.
    env["STOPHOOK_CHILD"] = "1"
    try:
        proc = subprocess.run(
            [
                exe,
                "-p",
                prompt_section(instances),
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(
                    {
                        "type": "object",
                        "properties": {"shape_dup": SHAPE_SCHEMA},
                        "required": ["shape_dup"],
                    }
                ),
                "--model",
                wl_judge.JUDGE_MODEL,
                "--max-budget-usd",
                wl_judge.JUDGE_BUDGET_USD,
            ],
            capture_output=True,
            text=True,
            timeout=wl_judge.JUDGE_TIMEOUT_S,
            env=env,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "shape_dup model call failed: %s" % exc
    if proc.returncode != 0:
        return None, "shape_dup model call exited %d" % proc.returncode
    try:
        return json.loads(proc.stdout), ""
    except ValueError as exc:
        return None, "shape_dup reply was not JSON: %s" % exc


def apply_verdict(out, instances, shape_hash, root=None, path=None):
    """(kind, note). Mutates `out` when the rule fires; owns the marker lifecycle."""
    demand = demand_for(shape_hash)
    if demand.load(path) is None and demand.fires(path) >= SHAPE_MAX_FIRES:
        return "silent", "already asked about this shape"
    kind, payload = read_verdict(out, root)
    if kind == "fire":
        note = enforce(out, payload, len(instances))
        demand.bank({"shape": payload["shape"]}, None, path)
        return "fire", note
    demand.clear(path)
    return kind, payload if isinstance(payload, str) else ""
