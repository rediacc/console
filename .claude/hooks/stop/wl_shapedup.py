"""wl_shapedup: "is this the Nth copy of a shape you already have?"

THE QUESTION NOBODY ASKS. The stop judge asks two things -- did you sweep the class (wl_classsweep), and is there a gate (wl_reggate). Neither asks whether the thing you just wrote already exists three times, so every finding correctly answers "add a script + a manifest entry + a workflow step + controls" and nothing is ever pointed at the accumulated surface.

This repo reached that conclusion by hand THREE times and wrote it down each time: `scripts/lib/shrink-only-baseline.ts:25-31` ("a class, not an instance... seven chances to drift"), `.claude/hooks/pre-bash/block-adhoc-sanctioned.sh:4-8` (a new class is "a row rather than a 22nd copy of this file"), and `scripts/gates/check-shared-constant-duplication.ts` (one constant existing
twice while "nothing failed"). Three times a person noticed.

ITS OWN MODEL CALL, and the reason is a measurement rather than a preference. The approved plan rode this rule on the existing judge call, paid for by trimming SWEEP_PROMPT's five worked examples to three -- estimated at ~2,300 characters freed. Measured after the trim landed (`eb34b3a47`): **62**. The five examples were ~700 characters in total. A fix stop already carries 17,735
characters of rubric (JUDGE 5,762 + REGGATE 2,646 + SWEEP 5,683 + BRAVE 3,644), and adding a fourth object unoffset degrades two rubrics that are calibrated against operator-supplied worked examples. So this rule pays its own way: one extra `claude -p` only on the stops where the COUNTER has already fired, which is rare by construction.

THE COUNTER IS MECHANICAL AND COMES FIRST. `scripts/gates/check-shape-duplication.ts` hashes sliding 5-line windows over the gate families, seeded so the 219-span standing backlog is silent, and fires only when a shape that was NOT already present reaches its third copy. A model asked "is there duplication?" answers yes far too often; a counter answers only when a real Nth instance
lands. The model is never asked to FIND anything -- `instances` comes
from the counter and is not read back off the model, so it cannot be fabricated.

THE WIDE TIER at the foot of this file is the same question over the counter's `advisory` profile, and it is ADVISORY ONLY: it queues one allow-report section and never blocks. It reports duplication in the Stop hook's own `wl_*.py` files, some of which is deliberate parallel rule structure; its section comment says why that is expected and how a `no` verdict settles.
"""

import fnmatch
import glob
import hashlib
import json
import os

import wl_core as C
import wl_judge
import wl_proc
import wl_reggate
import wl_rules
import wl_store as S

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
            CONCRETE: a behavioural difference visible in the instances listed above,
            such as differing return values, error handling or side effects, cited by
            `file:line` from the counter's list. "They are different" is not a
            divergence; "two accumulate and one exits" is the kind of thing that is.

WHAT IS NOT DUPLICATION, and the counter already excludes each, so if you see one the
counter has a bug and `no` with that as the divergence is the right answer:
  - an import preamble. Three files importing the same helper is ADOPTION; an import
    statement IS the consolidation.
  - a comment block. The prose explaining why a guard exists is why it is trustworthy.
  - a findings report. The sentence saying what failed IS the gate's value.

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
    """Does the named module exist on disk? A claim of prior consolidation is exactly the claim most worth checking, and one `os.path.exists` checks it."""
    if not harness:
        return False
    root = root or os.getcwd()
    cand = harness.split(":")[0].strip()
    return bool(cand) and os.path.exists(os.path.join(root, cand))


def read_verdict(out, root=None):
    """(kind, payload). kind is 'silent', 'fire' or 'degraded'.

    FAIL SEMANTICS are wl_classsweep's, not the regression gate's: a missing or malformed object NEVER fails closed. Degrading loses a demand; it can never grant an exit that was otherwise refused.
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
        # A refusal that names no divergence is not a refusal. Degraded rather than fired: an unactionable block is the one thing these rules cannot afford.
        if len(divergence) < 20:
            return "degraded", "consolidatable=no with no concrete divergence named"
        return "silent", "not one thing: %s" % divergence[:160]
    # `already` USED TO RETURN SILENT HERE, and that was backwards. Operator ruling 2026-09-02, after the calibration fixture and this line had contradicted each other for a full run: "Make it FIRE".
    #
    # The rubric asks whether these copies should become one thing, and reads `already` as "yes, and the thing already exists". Answering that with silence made the MOST actionable case the quietest one -- a helper is on disk, N copies ignore it, and adopting it is a mechanical edit with no design left to do. V_ACTION already carried the right order for it ("Extract the shared
    # piece into <harness>"), which is the adopt instruction; nothing needed writing, only unmuting. The evidence that settled it: with_temp_dir exists at .ci/scripts/test/lib/test-helpers.sh, and 70 gate scripts hand-roll `mktemp -d` against 26 that use it.
    #
    # `already` naming a module that is NOT on disk still fires too -- that is a claim, not a fact, and it fires with the harness it named so the session can see the mistake. Both branches fire now; they differ only in whether the named harness is real, which the instruction carries either way.
    return "fire", {
        "shape": shape,
        "harness": harness,
        # Kept on the payload rather than collapsed into the verdict, so BOTH branches stay separately testable now that both fire. It also picks the order: adopting a harness that exists is a mechanical edit, writing one that does not is a design decision.
        "harness_real": harness_is_real(harness, root),
        # The VERDICT itself, because harness_real alone is the wrong proxy for it. `consolidatable: yes` naming an existing library file as the extraction target is the COMMON case, and it was getting the adopt order -- "X already exists, adopt it" -- when the shared piece still has to be written into X. Found by audit; the comment above used to state that bug as the design.
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
# When the harness is already ON DISK there is nothing to design: the order is to adopt it, and saying "extract" would invite writing a second one beside it.
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
# Keyed by the shape hash as well as the checkout, so a session authoring three gates in one family gets ONE consolidation question rather than three. Without it the observed 2026-09-01 pattern -- four separate commits, one gate each, same day -- produces four identical asks.

SHAPE_TTL_MIN = int(os.environ.get("WORKLIST_SHAPE_TTL_MIN", "120"))
SHAPE_MAX_FIRES = int(os.environ.get("WORKLIST_SHAPE_MAX_FIRES", "2"))


def demand_for(shape_hash):
    return wl_rules.Demand(
        "shapedup-%s" % (shape_hash or "none")[:12], SHAPE_TTL_MIN, SHAPE_MAX_FIRES
    )


# THE WRAPPER THIS MODULE HANDS TO `--json-schema`, as a NAMED constant rather than a dict literal inside the argv. wl_judge's four schemas are all module constants (TRIAGE_SCHEMA, PLANFID_SCHEMA, ADMISSION_SCHEMA, and the one judge_schema_for builds), and this fifth one was the only inline literal -- which is exactly why it was the one that drifted: it alone omitted
# `additionalProperties: False`, so the wrapper accepted top-level keys the other four refuse. SHAPE_SCHEMA itself was correctly constrained all along; the defect was only in the envelope built at the call site.
#
# Being a constant is half the fix. The other half is that test-judge-schema.py now checks all five TOGETHER, which is the thing no per-site test could do.
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
    # THE RECURSION GUARD, same as run_judge and run_triage: `claude -p` fires the Stop hook, and without this the rule would ask itself about itself.
    env["STOPHOOK_CHILD"] = "1"

    def _call():
        return wl_proc.run(
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
            timeout=wl_judge.JUDGE_TIMEOUT_S,
            env=env,
        )

    proc = _call()
    if proc.timed_out:
        return None, "shape_dup model call timed out after %ds" % wl_judge.JUDGE_TIMEOUT_S
    if proc.returncode == wl_proc.SPAWN_FAILED_RC and not proc.stdout:
        return None, "shape_dup model call failed: %s" % proc.stderr.strip()
    if proc.returncode != 0:
        # THE FIFTH SCHEMA-CONSTRAINED CALL SITE, and it was missed when the other four were fixed. `error_max_structured_output_retries` is one SAMPLE failing to emit a conforming object, not a broken gate -- measured 2026-09-04, where the real call answered 3/3 at 4-5x the failing run's cost. This branch treats every non-zero exit as final, and the comment below explains why that
        # is expensive HERE in particular: one erroring
        # case blanks the whole rubric. Retried on exactly that subtype, with
        # budget headroom, once. Everything else still falls through and reports.
        proc, _why = wl_judge.retry_schema_exhaustion("shape_dup model call", proc, _call)
        if proc is None:
            return None, _why
    if proc.returncode != 0:
        # The TAIL OF THE CHILD'S OUTPUT, because the exit code alone says nothing. The counter path in this same file already does it (see the run_counter error below); this branch did not, so a live calibration reported "shape_dup model call exited 1" and SHAPE_PROMPT sat uncalibrated with no way to learn why. A rubric with exactly one fixture cannot afford an opaque failure: one
        # erroring case blanks the whole rubric.
        return None, "shape_dup model call exited %d: %s" % (
            proc.returncode,
            (proc.stderr or proc.stdout or "<no output>").strip()[-300:],
        )
    try:
        env_out = json.loads(proc.stdout)
    except ValueError as exc:
        return None, "shape_dup reply was not JSON: %s" % exc
    # THE ENVELOPE IS UNWRAPPED HERE, in one place. `claude -p --output-format json` returns a wrapper whose `structured_output` holds the schema'd object; `apply_verdict` MUTATES the dict it is handed, so a caller that judged the inner object and then read the reason back off the outer one gets an empty string and a rule that fires silently. That was the first version of this,
    # caught before it shipped.
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

    kind is 'fire', 'silent', 'degraded' or 'capped'. 'capped' means this same shape has already been blocked on SHAPE_MAX_FIRES times inside the TTL: the finding stands but the session is let past, because a rule that cannot be satisfied must not be a wall.

    THE CAP IS READ WITH `peek`, NOT `load`, and `bank` is given the PRIOR record. The
    first version of this used `load(path) is None and fires(path) >= MAX` and banked with
    `prior=None`, which is wrong twice: `bank` computes `fires = prior.fires + 1`, so
    without a prior the count is pinned at 1 forever, and `load` returns None only once the cap is ALREADY reached, so the guard could not fire while a live demand existed. The rule blocked on the same shape indefinitely. Caught by the control below, not by reading the code.
    """
    demand = demand_for(shape_hash)
    kind, payload = read_verdict(out, root)
    if kind != "fire":
        demand.clear(path)
        return kind, payload if isinstance(payload, str) else ""
    # The demand file is NAMED by the shape hash, so a prior record is always about this same shape -- unlike wl_bravedefault, which keeps one file and compares a key inside.
    prior = demand.peek(path)
    if prior and prior["fires"] >= SHAPE_MAX_FIRES:
        return "capped", "shape-dup: capped after %d blocks on the same shape" % SHAPE_MAX_FIRES
    note = enforce(out, payload, len(instances))
    demand.bank({"shape": payload["shape"][:200]}, prior, path)
    return "fire", note


# -- The driver: counter first, model only if the counter fired ---------------
#
# THE COUNTER IS THE TRIGGER AND IT IS MECHANICAL. A model asked "is there duplication?" answers yes far too often; `scripts/gates/check-shape-duplication.ts` answers only when a shape that was NOT in the seed reaches its third copy. So the paid call happens on the rare stop where a real Nth instance landed, and never otherwise.

COUNTER = "scripts/gates/check-shape-duplication.ts"
COUNTER_TIMEOUT_S = 60

# The corpus signature, so an unchanged tree costs a stat sweep rather than 1.1s of tsx. Measured 2026-09-01: the counter is ~1.10s wall over 320 files / 39,447 windows, and the Stop hook fires on every poll. mtime+size rather than content: any edit moves it, so this can make the rule LATE by nothing and can never silently switch it off.
CORPUS_GLOBS = (
    "scripts/gates/check-*.ts",
    ".ci/scripts/quality/check-*.sh",
    ".ci/scripts/test/gates/test-*.sh",
)


def corpus_sig(root, globs=CORPUS_GLOBS):
    h = hashlib.sha1()
    for pat in globs:
        for p in sorted(glob.glob(os.path.join(root, pat))):
            try:
                st = os.stat(p)
            except OSError:
                continue
            h.update(("%s:%d:%d;" % (os.path.basename(p), st.st_mtime_ns, st.st_size)).encode())
    return h.hexdigest()[:16]


SHAPE_INDEX_REL = ".ci/cache/shape-index"


def index_present(root):
    """Is the commit-path cache on disk?

    THE SIGNATURE ALONE IS NOT ENOUGH ANY MORE, and the gap is one-sided in the direction that matters. `corpus_sig` answers "has the corpus changed since the last run", which is the right question for the duplication VERDICT and the wrong one for the cache the verdict now also writes: a fresh checkout, a cleared `.ci/cache`, or the first run after the probe landed all leave an
    unchanged corpus and no index at all, and the early return below would then keep the commit path advisory-less for as long as nobody edited a gate. The cache is gitignored, so that state is the ordinary one rather than an edge case.
    """
    return _cache_complete(
        os.environ.get("SHAPE_PROBE_CACHE") or os.path.join(root, SHAPE_INDEX_REL)
    )


def _cache_complete(cache):
    """Both halves of one cache directory on disk: the index and the probe bundle built beside it."""
    return os.path.exists(os.path.join(cache, "index.json")) and os.path.exists(
        os.path.join(cache, "probe.mjs")
    )


def index_inputs_moved(root):
    """True when the on-disk index cannot be trusted: missing, unreadable, or one of its own recorded `inputs` no longer hashes to what the index says.

    THE FALLBACK CHOSEN OVER THE PREFERRED DESIGN (agent/plans/PLAN-stop-hook-refactor-enforcement.md, Commit 1): moving this check into the probe bundle itself (`probeMain` in `scripts/gates/check-shape-duplication.ts`) is the one-implementation-two-callers design and stays the long-term target, but it is a TypeScript change riding the same file Commit 2's profile split rewrites, and this rule needed the gap closed now. `corpus_sig` only stat-sweeps the three `CORPUS_GLOBS` pathspecs, so it is blind to a change in a file the bundle depends on WITHOUT being IN the scanned corpus -- `scripts/lib/blocker-validator.ts`, `scripts/lib/console.ts` and `scripts/lib/controls.ts` are three such `inputs` today, none of them matching `scripts/gates/check-*.ts`.
    Reading the SAME whole-file sha256 the commit-path guard's `_algorithm_moved` already computes (`.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py:137-153`) needs no port: both read `index.json`'s own `inputs` map and hash the same bytes the same way, so there is nothing here to drift out of step with it.

    Fails toward re-running rather than toward trusting a doubtful cache: a missing index, an unreadable one, a missing input file, or an unreadable one are all read as "moved", never as "unchanged".
    """
    return _cache_inputs_moved(
        root, os.environ.get("SHAPE_PROBE_CACHE") or os.path.join(root, SHAPE_INDEX_REL)
    )


def _cache_inputs_moved(root, cache):
    """`index_inputs_moved`'s body for an explicit cache directory, so the wide tier asks the SAME question of its own cache rather than a second spelling of it."""
    try:
        with open(os.path.join(cache, "index.json"), encoding="utf-8") as fh:
            index = json.load(fh)
    except (OSError, ValueError):
        return True
    inputs = index.get("inputs") if isinstance(index, dict) else None
    if not isinstance(inputs, dict):
        return True
    for rel, want in inputs.items():
        try:
            with open(os.path.join(root, rel), "rb") as fh:
                got = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            return True
        if got != want:
            return True
    return False


def counter_findings(root, profile=None):
    """(findings, error). Each finding is {shape, files, span}. Never raises.

    `profile` names one of the counter's `PROFILES`; None runs the default (`gate`) with an argv byte-identical to the one this function has always built. A named profile also runs WITHOUT `SHAPE_PROBE_CACHE` in its environment: the counter's `cacheDir()` honours that variable for whichever profile is running, so an inherited value would make the wide scan overwrite the commit-path guard's own index with a corpus of different pathspecs (risk 6 of agent/plans/PLAN-stop-hook-refactor-enforcement.md, a one-line mistake with a silent, total failure mode).
    """
    script = os.path.join(root, COUNTER)
    if not os.path.exists(script):
        return [], "counter not present at %s" % COUNTER
    # `--emit-index` RIDES THE RUN THAT WAS HAPPENING ANYWAY, which is the whole reason the commit-path probe can afford a fresh cache. The scan is the expensive part (about 1.1s over the corpus); writing the index it just computed is a bundle and two file writes, and it happens exactly when the corpus has changed, because that is when this rule re-runs at all. A refresh on its
    # own timer would be a second schedule for one fact.
    argv = ["npx", "tsx", COUNTER, "--json", "--emit-index"]
    kwargs = {"timeout": COUNTER_TIMEOUT_S, "cwd": root}
    if profile:
        argv += ["--profile", profile]
        kwargs["env"] = {k: v for k, v in os.environ.items() if k != "SHAPE_PROBE_CACHE"}
    proc = wl_proc.run(argv, **kwargs)
    if proc.timed_out:
        return [], "counter timed out after %ds" % COUNTER_TIMEOUT_S
    if proc.returncode == wl_proc.SPAWN_FAILED_RC and not proc.stdout:
        return [], "counter failed: %s" % proc.stderr.strip()
    # The counter EXITS NON-ZERO on its own floors (a broken glob, a missing seed). That is its report to CI, not an answer to this question, so it is surfaced as an error and never read as "no duplication".
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


def refresh_index(root, state):
    """(findings, err) from a fresh counter run, or (None, "") when nothing needed re-running.

    SPLIT OUT OF `run` (agent/plans/PLAN-stop-hook-refactor-enforcement.md, Commit 1) so the commit-path guard's index can be rearmed on EVERY stop that reaches the allow path, independent of whether the judge said `stop`. Before this split the only thing that re-ran the counter -- and so the only thing that re-emitted `.ci/cache/shape-index/` -- was `run`, called exclusively from inside `if judged_ok:`. A one-character comment edit to the counter's own source moved its `inputs` hash, `warn_staged_shape_duplication`'s `_algorithm_moved` correctly refused to trust the stale index, and the commit-path advisory stayed disarmed for 36+ minutes because the judge kept saying `continue` -- verified live, not assumed.
    `None` (rather than `[]`) is the signal that the counter did not run at all this stop, which the judged half needs to tell apart from "it ran and found nothing".
    """
    sig = corpus_sig(root)
    stale = sig != state.get("shapedup_sig") or not index_present(root) or index_inputs_moved(root)
    if not stale:
        return None, ""
    state["shapedup_sig"] = sig
    return counter_findings(root)


def judge(root, findings, err):
    """The judged half of the old `run`: given findings `refresh_index` already computed, ask the model about the largest shape and apply the verdict. (fired, reason, next_action, note). Never runs the counter itself."""
    if err:
        # NEVER FAILS CLOSED, same as wl_classsweep: the only thing this rule can do is turn an allowed stop into a block, so a counter that could not answer loses a demand rather than granting an exit.
        return False, "", "", "shape counter unavailable: %s" % err
    if not findings:
        return False, "", "", ""

    # ONE SHAPE PER STOP: the largest, by copies x span. Its own latch keys on the hash, so the next one is asked on a later stop rather than all of them at once.
    top = findings[0]
    instances = [str(f) for f in top.get("files", [])]
    shape_hash = str(top.get("shape", ""))
    if len(instances) < 2:
        return False, "", "", ""

    out, err2 = ask(instances)
    if out is None:
        return False, "", "", "shape_dup not judged: %s" % err2
    # `out` is the inner object, and apply_verdict mutates IT. Read the order back off the same dict that was written.
    kind, note = apply_verdict(out, instances, shape_hash)
    if kind != "fire":
        return False, "", "", note if kind == "degraded" else ""
    return True, out.get("reason", ""), out.get("next_action", ""), note


def run(root, state):
    """The whole rule, byte-identical in behaviour to before the split: refresh then judge.

    `state` is a mutable dict persisted by the caller; only `shapedup_sig` is used. Kept for any caller that still wants both halves in one call; `.claude/hooks/stop/wl_checks.py` now calls `refresh_index` and `judge` separately so the former can run unconditionally.
    """
    findings, err = refresh_index(root, state)
    if findings is None and not err:
        return False, "", "", ""
    return judge(root, findings, err)


# -- THE WIDE TIER: an advisory drip over the corpus CI does not refuse on -------
#
# WHAT IT IS (agent/plans/PLAN-stop-hook-refactor-enforcement.md, Commit 3). The counter's `advisory` profile scans four families the `gate` profile never reaches -- `.ci/scripts/quality/check_*.py`, `.ci/rediacc_ci/tests/gates/test_gate_*.py`, `.claude/rediacc_hooks/guards/block_*.py` and `.claude/hooks/stop/wl_*.py` -- and about 90 standing findings sit in them that no session here created. So this tier NEVER BLOCKS: it never calls `wl_rules.apply_order`, it never places a `decision: block`, and its whole output is one allow-report section queued at priority 2 through `outq_add`, one shape per logical moment. A blocking tier over a standing backlog is a nagging machine by construction.
#
# IT REPORTS DUPLICATION IN THE STOP HOOK'S OWN FILES (risk 2 of the plan), and that will read as a defect the first time it happens: a session editing `.claude/hooks/stop/wl_*.py` gets duplication findings about the stop hook, from the stop hook, while editing it. It is not a defect. It is also the family most likely to produce false positives, because those files carry DELIBERATE parallel rule structure -- `wl_classsweep`, `wl_bravedefault` and this module share a shape on purpose (`wl_rules.py`'s header says exactly that). Expect `no` verdicts there, and settle each one the way the message says: an `accepted` entry with a BLOCKER reason in `scripts/data/shape-duplication-seed-advisory.json`, which silences that shape on the very next counter run, forever and visibly. A `no` verdict's text carries the ready-to-paste entry so the settle path costs one edit.
#
# REUSED UNCHANGED: `counter_findings` (with `profile`), `ask`, `read_verdict`, `demand_for` and `SHAPE_PROMPT`, so the calibration hash in `.ci/config/rubric-calibration.json` does not move and no new judged-rule module exists for `check_judged_rule_wiring.py` to count. Four brakes, all pre-existing: `outq_add`'s shown ledger (same text is not said twice inside `REPORT_REFRESH_MIN`), `outq_drain`'s per-stop budget, a per-shape `Demand` latch (SHAPE_TTL_MIN / SHAPE_MAX_FIRES), and the branch-scoped spend cap below. Above the cap the finding still lands, mechanically, with no model call: a rule that goes silent when its budget runs out is a rule that quietly stops.

# THE SAME FOUR PATHSPECS AS `ADVISORY_FAMILIES` in `scripts/gates/check-shape-duplication.ts`, pinned equal in both directions by `.ci/rediacc_ci/tests/test_shapedup_corpus_sig.py`: a narrower signature would serve a stale verdict, exactly as for the narrow tuple above.
CORPUS_GLOBS_WIDE = (
    ".ci/scripts/quality/check_*.py",
    ".ci/rediacc_ci/tests/gates/test_gate_*.py",
    ".claude/rediacc_hooks/guards/block_*.py",
    ".claude/hooks/stop/wl_*.py",
)
WIDE_PROFILE = "advisory"
# The advisory profile's OWN cache, never `SHAPE_PROBE_CACHE`: that variable belongs to the commit-path guard, which compares a commit's staged files against the pathspecs recorded in the index it reads (risk 6).
SHAPE_INDEX_WIDE_REL = ".ci/cache/shape-index-advisory"
# Model calls per BRANCH, not per session: a branch is one PR and one CI queue, which is where the cost lands, and a per-session budget would reset at every compaction (the same argument wl_reggate's REGGATE_CAP makes).
WIDE_CAP = max(0, int(os.environ.get("WORKLIST_SHAPEDUP_WIDE_CAP", "5")))

V_REASON_WIDE = (
    "IS THIS THE NTH COPY. A counter found this shape at %d places across "
    "the %s family, outside the corpus CI refuses on: %s"
)
V_ACTION_WIDE = (
    "Extract the shared piece%s, or record the DIVERGENCE with a BLOCKER "
    "reason in scripts/data/shape-duplication-seed-advisory.json under "
    '"accepted". ADVISORY: nothing is blocked on this. '
    "Triage it: .claude/hooks/stop/worklist.py --triage <you> '<the finding>'"
)
# A `no` verdict is the settle path half-written: the model has named the divergence, so the entry that silences the shape is handed over whole rather than described.
V_SETTLE_WIDE = (
    'Judged NOT one thing: %s. To settle it for good, add this under "accepted" in '
    'scripts/data/shape-duplication-seed-advisory.json: "%s": "BLOCKER: <that divergence, '
    'citing file:line>". ADVISORY: nothing is blocked on this.'
)


def touches_wide(files):
    """Does any path match a wide pathspec? The plan's `any(fnmatch(f, g) ...)` test, kept here so `wl_checks.py` needs no import of its own for it."""
    return any(fnmatch.fnmatch(f, g) for f in files or () for g in CORPUS_GLOBS_WIDE)


def wide_sig_moved(root, state):
    """True when the wide corpus changed since the last wide run, or its cache is absent or stale. A stat sweep plus one small JSON read (about 4ms measured); never runs the counter. A FILTER on the fix-landed moment, not a trigger of its own: the widened counter measured a 3.05s median, over the plan's 3s ceiling, so an edit alone does not buy a scan."""
    cache = os.path.join(root, SHAPE_INDEX_WIDE_REL)
    return (
        corpus_sig(root, CORPUS_GLOBS_WIDE) != state.get("shapedup_wide_sig")
        or not _cache_complete(cache)
        or _cache_inputs_moved(root, cache)
    )


def wide_ledger_path(branch, root=None):
    """`agent/reggate/<branch-slug>.shapedup-wide.jsonl`, beside wl_reggate's own per-branch ledger and through its `debt_dir`, so `$WORKLIST_STORE_DIR` redirects both at once.

    NOT a new `agent/shapedup-wide/` directory: `wl_store.agent_session_dirs` reports every non-reserved directory under `agent/` as a peer session, and `check:ci-tree-shape` refuses one, so a new directory would need a reservation in three places. `agent/reggate/` is already reserved and its `*.lock` sidecars are already gitignored; the `.shapedup-wide` infix keeps this file apart from the branch's reggate ledger and its lock.
    """
    return wl_reggate.debt_dir(root) / (wl_reggate._branch_slug(branch) + ".shapedup-wide.jsonl")


def wide_spent(branch, root=None):
    """Model calls this branch has already spent on the wide tier. An unreadable line is not a refund: only well-formed `ask` records count, and a ledger that cannot be read at all counts as spent in full, so a broken ledger can never read as a fresh budget."""
    path = wide_ledger_path(branch, root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return 0
    except OSError:
        return WIDE_CAP
    n = 0
    for raw in text.splitlines():
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("kind") == "ask":
            n += 1
    return n


def wide_charge(branch, shape_hash, root=None):
    """Append one spend record under the store's blocking flock. This tree is shared by concurrent sessions, so the ledger is never written unlocked."""
    path = wide_ledger_path(branch, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"kind": "ask", "shape": shape_hash, "at": C.stamp_now(), "br": branch or ""}
    S._append_lines(path, path.with_suffix(".lock"), [rec])


def _wide_family(instances):
    fams = [
        g
        for g in CORPUS_GLOBS_WIDE
        if any(fnmatch.fnmatch(i.rsplit(":", 1)[0], g) for i in instances)
    ]
    return " + ".join(fams) or "advisory"


def _wide_pick(findings):
    """The largest finding (copies x span) whose per-shape latch is not yet capped, or None. The latch is `demand_for` keyed on `wide-<hash>`, so the wide tier and the narrow one never share a record and two shapes never share one either."""
    ranked = sorted(
        (f for f in findings or [] if isinstance(f, dict)),
        key=lambda f: len(f.get("files") or []) * int(f.get("span") or 0),
        reverse=True,
    )
    for f in ranked:
        instances = [str(x) for x in f.get("files") or []]
        shape_hash = str(f.get("shape", ""))
        if len(instances) < 2 or not shape_hash:
            continue
        demand = demand_for("wide-" + shape_hash)
        prior = demand.peek()
        if prior and prior["fires"] >= SHAPE_MAX_FIRES:
            continue
        return f, instances, shape_hash, demand, prior
    return None


def wide_report(root, findings, err, branch):
    """(text, note) for ONE wide finding. `text` is the allow-report section to queue, "" when there is nothing to say; `note` is a diagnostic. Never raises on a counter error and never calls `wl_rules.apply_order`."""
    if err:
        # NEVER FIRES on a counter that could not answer: the error is surfaced as a note and nothing is claimed about the tree.
        return "", "wide shape counter unavailable: %s" % err
    pick = _wide_pick(findings)
    if pick is None:
        return "", ""
    f, instances, shape_hash, demand, prior = pick
    note, desc, action = "", "", ""
    spent = wide_spent(branch, root)
    if spent < WIDE_CAP:
        # CHARGED BEFORE THE CALL: a call that times out or errors was still paid for.
        wide_charge(branch, shape_hash, root)
        out, err2 = ask(instances)
        if out is None:
            note = "wide shape_dup not judged: %s" % err2
        else:
            kind, payload = read_verdict(out, root)
            if kind == "fire":
                desc = payload["shape"]
                action = V_ACTION_WIDE % (
                    " into %s" % payload["harness"] if payload["harness"] else ""
                )
            elif kind == "silent":
                desc = "shape %s" % shape_hash
                action = V_SETTLE_WIDE % (payload, shape_hash)
            else:
                note = "wide shape_dup degraded: %s" % payload
        judged = "%s by %s, model call %d of %d on this branch" % (
            "judged" if action else "no verdict",
            wl_judge.JUDGE_MODEL,
            spent + 1,
            WIDE_CAP,
        )
    else:
        judged = (
            "not judged: this branch's %d wide-tier model calls are spent, counter output only"
            % WIDE_CAP
        )
    if not action:
        # Mechanical: the counter's own measurement, which is true whether or not a model looked at it.
        desc = desc or "shape %s, ~%d lines" % (shape_hash, int(f.get("span") or 0))
        action = V_ACTION_WIDE % ""
    lines = [V_REASON_WIDE % (len(instances), _wide_family(instances), desc)]
    lines += ["    %s" % i for i in instances[:12]]
    if len(instances) > 12:
        lines.append("    ... and %d more" % (len(instances) - 12))
    lines.append("  accepted key: %s (%s)" % (shape_hash, judged))
    lines.append(action)
    demand.bank({"shape": shape_hash}, prior)
    return "\n".join(lines), note


def wide_run(root, state, branch):
    """Run the advisory counter and report one finding. The CALLER decides the moment (`wl_checks.py`: a fix landing in a wide family, filtered by `wide_sig_moved`, the plan's fallback after the widened counter measured over its 3s ceiling); this records the new signature so an unchanged tree is not re-scanned. `state` is the caller's persisted dict; only `shapedup_wide_sig` is written."""
    state["shapedup_wide_sig"] = corpus_sig(root, CORPUS_GLOBS_WIDE)
    findings, err = counter_findings(root, profile=WIDE_PROFILE)
    return wide_report(root, findings, err, branch)
