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

import glob
import hashlib
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
    # `already` USED TO RETURN SILENT HERE, and that was backwards. Operator
    # ruling 2026-09-02, after the calibration fixture and this line had
    # contradicted each other for a full run: "Make it FIRE".
    #
    # The rubric asks whether these copies should become one thing, and reads
    # `already` as "yes, and the thing already exists". Answering that with
    # silence made the MOST actionable case the quietest one -- a helper is on
    # disk, N copies ignore it, and adopting it is a mechanical edit with no
    # design left to do. V_ACTION already carried the right order for it
    # ("Extract the shared piece into <harness>"), which is the adopt
    # instruction; nothing needed writing, only unmuting. The evidence that
    # settled it: with_temp_dir exists at .ci/scripts/test/lib/test-helpers.sh,
    # and 70 gate scripts hand-roll `mktemp -d` against 26 that use it.
    #
    # `already` naming a module that is NOT on disk still fires too -- that is a
    # claim, not a fact, and it fires with the harness it named so the session
    # can see the mistake. Both branches fire now; they differ only in whether
    # the named harness is real, which the instruction carries either way.
    return "fire", {
        "shape": shape,
        "harness": harness,
        # Kept on the payload rather than collapsed into the verdict, so BOTH
        # branches stay separately testable now that both fire. It also picks
        # the order: adopting a harness that exists is a mechanical edit,
        # writing one that does not is a design decision.
        "harness_real": harness_is_real(harness, root),
        # The VERDICT itself, because harness_real alone is the wrong proxy for
        # it. `consolidatable: yes` naming an existing library file as the
        # extraction target is the COMMON case, and it was getting the adopt
        # order -- "X already exists, adopt it" -- when the shared piece still
        # has to be written into X. Found by audit; the comment above used to
        # state that bug as the design.
        "verdict": verdict,
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
# When the harness is already ON DISK there is nothing to design: the order is to
# adopt it, and saying "extract" would invite writing a second one beside it.
V_ACTION_ADOPT = (
    "%s ALREADY EXISTS and these copies do not use it. Adopt it, or say which "
    "DIVERGENCE makes these not one thing. Triage it: "
    ".claude/hooks/stop/worklist.py --triage <you> '<the finding>'"
)


def enforce(out, payload, count):
    reason = V_REASON % (count, payload["shape"])
    if payload.get("verdict") == "already" and payload.get("harness_real") and payload["harness"]:
        action = V_ACTION_ADOPT % payload["harness"]
    else:
        into = " into %s" % payload["harness"] if payload["harness"] else ""
        action = V_ACTION % into
    wl_rules.apply_order(out, reason, action)
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


# THE WRAPPER THIS MODULE HANDS TO `--json-schema`, as a NAMED constant rather
# than a dict literal inside the argv. wl_judge's four schemas are all module
# constants (TRIAGE_SCHEMA, PLANFID_SCHEMA, ADMISSION_SCHEMA, and the one
# judge_schema_for builds), and this fifth one was the only inline literal --
# which is exactly why it was the one that drifted: it alone omitted
# `additionalProperties: False`, so the wrapper accepted top-level keys the other
# four refuse. SHAPE_SCHEMA itself was correctly constrained all along; the
# defect was only in the envelope built at the call site.
#
# Being a constant is half the fix. The other half is that test-judge-schema.py
# now checks all five TOGETHER, which is the thing no per-site test could do.
ASK_SCHEMA = {
    "type": "object",
    "properties": {"shape_dup": SHAPE_SCHEMA},
    "required": ["shape_dup"],
    "additionalProperties": False,
}


def ask(instances):
    """Its OWN `claude -p`. (verdict_dict, error). Never raises."""
    exe = wl_judge.resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found"
    env = dict(os.environ)
    # THE RECURSION GUARD, same as run_judge and run_triage: `claude -p` fires the Stop
    # hook, and without this the rule would ask itself about itself.
    env["STOPHOOK_CHILD"] = "1"

    def _call():
        return subprocess.run(
            [
                exe,
                "-p",
                prompt_section(instances),
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(ASK_SCHEMA),
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

    try:
        proc = _call()
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "shape_dup model call failed: %s" % exc
    if proc.returncode != 0:
        # THE FIFTH SCHEMA-CONSTRAINED CALL SITE, and it was missed when the other
        # four were fixed. `error_max_structured_output_retries` is one SAMPLE
        # failing to emit a conforming object, not a broken gate -- measured
        # 2026-09-04, where the real call answered 3/3 at 4-5x the failing run's
        # cost. This branch treats every non-zero exit as final, and the comment
        # below explains why that is expensive HERE in particular: one erroring
        # case blanks the whole rubric. Retried on exactly that subtype, with
        # budget headroom, once. Everything else still falls through and reports.
        proc, _why = wl_judge.retry_schema_exhaustion("shape_dup model call", proc, _call)
        if proc is None:
            return None, _why
    if proc.returncode != 0:
        # The TAIL OF THE CHILD'S OUTPUT, because the exit code alone says nothing.
        # The counter path in this same file already does it (see the run_counter
        # error below); this branch did not, so a live calibration reported
        # "shape_dup model call exited 1" and SHAPE_PROMPT sat uncalibrated with
        # no way to learn why. A rubric with exactly one fixture cannot afford an
        # opaque failure: one erroring case blanks the whole rubric.
        return None, "shape_dup model call exited %d: %s" % (
            proc.returncode,
            (proc.stderr or proc.stdout or "<no output>").strip()[-300:],
        )
    try:
        env_out = json.loads(proc.stdout)
    except ValueError as exc:
        return None, "shape_dup reply was not JSON: %s" % exc
    # THE ENVELOPE IS UNWRAPPED HERE, in one place. `claude -p --output-format json` returns
    # a wrapper whose `structured_output` holds the schema'd object; `apply_verdict` MUTATES
    # the dict it is handed, so a caller that judged the inner object and then read the
    # reason back off the outer one gets an empty string and a rule that fires silently.
    # That was the first version of this, caught before it shipped.
    if not isinstance(env_out, dict):
        return None, "shape_dup reply was not an object"
    if env_out.get("is_error"):
        return None, "shape_dup reported is_error (subtype=%s)" % env_out.get("subtype")
    inner = env_out.get("structured_output")
    if not isinstance(inner, dict):
        return None, "shape_dup returned no structured_output"
    return inner, ""


def apply_verdict(out, instances, shape_hash, root=None, path=None):
    """(kind, note). Mutates `out` when the rule fires; owns the marker lifecycle.

    kind is 'fire', 'silent', 'degraded' or 'capped'. 'capped' means this same shape has
    already been blocked on SHAPE_MAX_FIRES times inside the TTL: the finding stands but
    the session is let past, because a rule that cannot be satisfied must not be a wall.

    THE CAP IS READ WITH `peek`, NOT `load`, and `bank` is given the PRIOR record. The
    first version of this used `load(path) is None and fires(path) >= MAX` and banked with
    `prior=None`, which is wrong twice: `bank` computes `fires = prior.fires + 1`, so
    without a prior the count is pinned at 1 forever, and `load` returns None only once the
    cap is ALREADY reached, so the guard could not fire while a live demand existed. The
    rule blocked on the same shape indefinitely. Caught by the control below, not by
    reading the code.
    """
    demand = demand_for(shape_hash)
    kind, payload = read_verdict(out, root)
    if kind != "fire":
        demand.clear(path)
        return kind, payload if isinstance(payload, str) else ""
    # The demand file is NAMED by the shape hash, so a prior record is always about this
    # same shape -- unlike wl_bravedefault, which keeps one file and compares a key inside.
    prior = demand.peek(path)
    if prior and prior["fires"] >= SHAPE_MAX_FIRES:
        return "capped", "shape-dup: capped after %d blocks on the same shape" % SHAPE_MAX_FIRES
    note = enforce(out, payload, len(instances))
    demand.bank({"shape": payload["shape"][:200]}, prior, path)
    return "fire", note


# -- The driver: counter first, model only if the counter fired ---------------
#
# THE COUNTER IS THE TRIGGER AND IT IS MECHANICAL. A model asked "is there duplication?"
# answers yes far too often; `scripts/check-shape-duplication.ts` answers only when a shape
# that was NOT in the seed reaches its third copy. So the paid call happens on the rare
# stop where a real Nth instance landed, and never otherwise.

COUNTER = "scripts/check-shape-duplication.ts"
COUNTER_TIMEOUT_S = 60

# The corpus signature, so an unchanged tree costs a stat sweep rather than 1.1s of tsx.
# Measured 2026-09-01: the counter is ~1.10s wall over 320 files / 39,447 windows, and the
# Stop hook fires on every poll. mtime+size rather than content: any edit moves it, so this
# can make the rule LATE by nothing and can never silently switch it off.
CORPUS_GLOBS = (
    "scripts/check-*.ts",
    ".ci/scripts/quality/check-*.sh",
    ".ci/scripts/test/gates/test-*.sh",
    ".claude/hooks/pre-bash/block-*.sh",
)


def corpus_sig(root):
    h = hashlib.sha1()
    for pat in CORPUS_GLOBS:
        for p in sorted(glob.glob(os.path.join(root, pat))):
            try:
                st = os.stat(p)
            except OSError:
                continue
            h.update(("%s:%d:%d;" % (os.path.basename(p), st.st_mtime_ns, st.st_size)).encode())
    return h.hexdigest()[:16]


def counter_findings(root):
    """(findings, error). Each finding is {shape, files, span}. Never raises."""
    script = os.path.join(root, COUNTER)
    if not os.path.exists(script):
        return [], "counter not present at %s" % COUNTER
    try:
        proc = subprocess.run(
            ["npx", "tsx", COUNTER, "--json"],
            capture_output=True,
            text=True,
            timeout=COUNTER_TIMEOUT_S,
            cwd=root,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], "counter failed: %s" % exc
    # The counter EXITS NON-ZERO on its own floors (a broken glob, a missing seed). That is
    # its report to CI, not an answer to this question, so it is surfaced as an error and
    # never read as "no duplication".
    line = ""
    for ln in (proc.stdout or "").splitlines():
        if ln.startswith("{"):
            line = ln
    if not line:
        return [], "counter produced no JSON (exit %d): %s" % (
            proc.returncode,
            (proc.stderr or proc.stdout or "")[-160:],
        )
    try:
        data = json.loads(line)
    except ValueError as exc:
        return [], "counter JSON unparseable: %s" % exc
    out = data.get("findings")
    return (out if isinstance(out, list) else []), ""


def run(root, state):
    """The whole rule. (fired, reason, next_action, note).

    `state` is a mutable dict persisted by the caller; only `shapedup_sig` is used.
    """
    sig = corpus_sig(root)
    if sig == state.get("shapedup_sig"):
        return False, "", "", ""
    state["shapedup_sig"] = sig

    findings, err = counter_findings(root)
    if err:
        # NEVER FAILS CLOSED, same as wl_classsweep: the only thing this rule can do is
        # turn an allowed stop into a block, so a counter that could not answer loses a
        # demand rather than granting an exit.
        return False, "", "", "shape counter unavailable: %s" % err
    if not findings:
        return False, "", "", ""

    # ONE SHAPE PER STOP: the largest, by copies x span. Its own latch keys on the hash, so
    # the next one is asked on a later stop rather than all of them at once.
    top = findings[0]
    instances = [str(f) for f in top.get("files", [])]
    shape_hash = str(top.get("shape", ""))
    if len(instances) < 2:
        return False, "", "", ""

    out, err2 = ask(instances)
    if out is None:
        return False, "", "", "shape_dup not judged: %s" % err2
    # `out` is the inner object, and apply_verdict mutates IT. Read the order back off the
    # same dict that was written.
    kind, note = apply_verdict(out, instances, shape_hash)
    if kind != "fire":
        return False, "", "", note if kind == "degraded" else ""
    return True, out.get("reason", ""), out.get("next_action", ""), note
