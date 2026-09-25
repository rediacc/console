"""wl_proofcheck: the stop judge asks whether a bulk mechanical transform proved itself.

WHY THIS EXISTS, in the operator's own instruction: block a bulk transform that carries no proof it did not destroy structure the transform's own author did not think to check. `agent/plans/PLAN-consolidation-pressure.md` names the mechanism -- `.ci/scripts/quality/shape_cluster_diff.py`, a shape-cluster diff over every changed line -- and this module is the second half: the demand
that a session actually runs it, or something as strong, before a bulk rewrite is allowed to stand.

THE INCIDENT THIS RULE ANSWERS TO, all from one session and none caught by a green gate: a reflow pass rewrote 884 files and destroyed 838 section banners while an AST-equality proof, 82 selftest controls and 216 pytest cases all passed, because none of them reads prose STRUCTURE. Fixing the Python comment path left the C-style one absorbing the same shapes. A list item's
continuation was flattened to column 0 under a passing fence/heading/table check. Four bulk rewrites, each shipped on the strength of the WRONG proof, or none.

WHY THIS RIDES wl_classsweep'S TRIGGER RATHER THAN INVENTING ITS OWN. Detecting "a bulk mechanical transform landed" from git alone -- file counts, commit shape -- would need its own state file, its own head-tracking, its own docs-only skip filter, all of which `wl_reggate.fix_signals` already computes to decide whether a FIX landed this turn. Riding that same signal means asking a
SECOND question about a fix-set the judge is already being shown, not a second git scan. The trade is honest: this rule can only fire on a stop that already qualifies as a fix stop, so a bulk transform that is never described as a "fix" (a pure reflow/style commit, say) will not trip it from THIS signal alone -- `docs(agent)`-prefixed and `style(`-prefixed commits do reach
`FIX_SUBJECT` in `wl_reggate.py`, which is why every reflow commit in the incident history above would have qualified.

THE SAME ENFORCEMENT SHAPE AS wl_classsweep, on purpose, because it is proven: ONE optional-at-the-top-level schema object, required only when the prompt actually asks for it (`judge_schema_for`); a verdict flip via `wl_rules.apply_order`, never a new blocking path; a carried-forward demand so a session that stops again without the proof is asked again; FAIL SEMANTICS that never
fail closed, because the only thing this object can do is turn a stop into a continue, and degrading loses a demand rather than granting an exit.

NOT DUPLICATED, REUSED. `validate_search`, `names_destructive` and the Demand class already live behind `wl_classsweep`/`wl_rules` and are called here rather than copied, which is the discipline `agent/plans/PLAN-consolidation-pressure.md` argues for: a rule of this shape belongs in one place, consulted by every caller, not re-derived by each one that needs it.
"""

import os
import re
import shlex

import wl_classsweep as CS
import wl_common
import wl_rules

PROOF_MARKER = "PROOF OBLIGATION: DID THE BULK TRANSFORM PROVE ITSELF"

PROOF_KINDS = ("tool", "manual", "none")

PROOF_SCHEMA = {
    "type": "object",
    "properties": {
        "applicable": {"type": "boolean"},
        "transform_kind": {"type": "string", "maxLength": 300},
        "scope": {"type": "string", "maxLength": 200},
        "proof_kind": {"type": "string", "enum": list(PROOF_KINDS)},
        "evidence": {"type": "string", "maxLength": 300},
        "proof_attached": {"type": "boolean"},
        "instruction": {"type": "string", "maxLength": 300},
    },
    "required": [
        "applicable",
        "transform_kind",
        "scope",
        "proof_kind",
        "evidence",
        "proof_attached",
        "instruction",
    ],
    "additionalProperties": False,
}

PROOF_PROMPT = """

%s. ALSO fill the `proof_obligation` object, about the same fix-set.

A BULK MECHANICAL TRANSFORM is one script, rule or rewrite applied UNIFORMLY
across many files in one pass: a reflow, a rename swept tree-wide, a
regex-driven rewrite, a formatter run over a directory. It is NOT a
hand-written fix confined to one or a few files, even a large one, because a
human read every line they touched.

THE QUESTION IS WHETHER THE FIX-SET INCLUDES ONE, not whether the whole
fix-set is one. A commit that is 95%% a hand-written fix and 5%% "also ran the
formatter over the touched directory" still has a bulk transform inside it.

(1) APPLICABLE. Does any part of this fix-set apply one mechanical change
across many files? If every file in the fix-set was individually read and
edited by a person, applicable=false: a bulk transform needs SCALE THROUGH
REPETITION, not merely touching several files. A trap note earlier in this
prompt describing a PAST bulk transform is never itself evidence that one is
happening now: judge only the ACTUAL FILES list (if one was injected above)
and the message below, and answer applicable=false when that list is short,
clean, or unrelated to what a trap describes even though the message
discusses a related topic.

(2) IF APPLICABLE, WHAT PROOF DOES THE MESSAGE SHOW. Three kinds, and only
two count:
  tool     a structural comparison was RUN and its output reported with real
           counts -- a shape-cluster diff, an AST-equality proof, a
           byte-identity check, a fence/heading/table structural scan. The
           message must show the tool ran and what it said, not merely that
           one exists.
  manual   an explicit claim that specific files were sampled and read across
           both revisions, naming which files or how many.
  none     the message asserts the transform is safe with no verifiable
           check attached: "reflowed N files", "ran the formatter", a diff
           stat, or nothing at all.

A LINE-COUNT OR FILE-COUNT ALONE IS `none`, regardless of how large or small
it is. Reporting how many files a transform touched proves the transform RAN;
it proves nothing about whether it destroyed structure its own author did not
think to check. Judge the count and scope only from the ACTUAL FILES list (if
one was injected above) and the message below -- never invent a count or a
directory of one's own to illustrate the point.

Set `proof_attached=true` ONLY when `proof_kind` is not `none`. An assertion
that the transform is safe, with no verifiable check quoted in `evidence`,
is exactly the failure this object exists to catch.

(3) SCOPE AND INSTRUCTION. `scope` names what the transform touched, in a few
words (a path prefix, a language, a rule name). `instruction` is the concrete
next step: a STRUCTURAL comparison, before and after, of the files the transform
touched (parsed structure, not line counts), with its real output reported, not
"verify the changes are correct". For prose and comments,
`.ci/scripts/quality/shape_cluster_diff.py --rev <base-sha> <path...>` is one
such tool; for code, an AST comparison is another. Name what fits THIS change.

Fill `proof_obligation` accordingly: applicable, transform_kind (the
mechanism, one line), scope, proof_kind, evidence (the quote, or empty
string), proof_attached, instruction.
""" % (PROOF_MARKER)

FOLLOWUP_PROMPT = """

%s. An earlier stop this session found a bulk transform with no proof
attached:

  TRANSFORM: %%(transform_kind)s
  SCOPE:     %%(scope)s

Fill the `proof_obligation` object again, judging ONLY whether the message
now carries proof: a tool run and reported, or an explicit statement of what
was manually sampled. Keep applicable=true and repeat the same transform_kind
and scope. If the message does not mention the proof at all, proof_attached=
false with proof_kind `none`.
""" % (PROOF_MARKER)


def prompt_section(fix_signal, outstanding=None):
    """The prompt text to append, or "" when this stop asks nothing.

    Mirrors `wl_classsweep.prompt_section` exactly: the fix signal wins over an outstanding demand, since a NEW fix-set is asked about fresh, on PROOF_PROMPT, which never mentions the outstanding transform -- that demand is carried forward in the marker's `owed` slot rather than dropped, and asked in full on a later stop that is not a fix stop.
    """
    if fix_signal:
        return PROOF_PROMPT
    if outstanding:
        return FOLLOWUP_PROMPT % {
            "transform_kind": (outstanding.get("transform_kind") or "(not recorded)")[:300],
            "scope": (outstanding.get("scope") or "(not recorded)")[:200],
        }
    return ""


# A structural proof tool actually RUN, as a command (R20260924.18). Narrower than the guard's PROOF_PHRASE on purpose: "sampled 3 files" is prose a message can carry, never a command the transcript can show.
PROOF_TOOL_RE = re.compile(r"shape[-_]cluster[-_]diff", re.IGNORECASE)
# The one proof step a STILL OWED line hands over for a carried proof demand.
PROOF_STEP = ".ci/scripts/quality/shape_cluster_diff.py --rev <base-sha> %s"


def scope_paths(scope):
    """The path-shaped words of a demand's prose `scope`: a word carrying `/`, or a file name with an extension. "packages/x comments" -> ["packages/x"]."""
    out = []
    for raw in re.split(r"[\s,;()`'\"]+", scope or ""):
        word = raw.strip().removeprefix("./").rstrip("/.:")
        if not word:
            continue
        if "/" in word or re.fullmatch(r"[\w.-]+\.[A-Za-z0-9]{1,8}", word):
            out.append(word)
    return out


def _runs_proof_on(scope_list, command):
    if not PROOF_TOOL_RE.search(command or ""):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for tok in tokens:
        have = tok.strip().removeprefix("./").rstrip("/")
        if not have or have.startswith("-"):
            continue
        for want in scope_list:
            # The same path, a directory above it, or a path inside it: each runs the proof over the scope's files.
            if have == want or want.startswith(have + "/") or have.startswith(want + "/"):
                return True
    return False


def proof_evidenced(outstanding, transcript):
    """True when the lead transcript, AFTER the demand first fired, holds a Bash call that runs a shape-cluster diff on a path named in the demand's `scope`, and whose result came back (R20260924.18). The proof twin of `wl_classsweep.sweep_evidenced`, reading the same harness record.

    Fails toward "not evidenced": a scope naming no path, a call before the demand, another tool, another path, or a call with no result each keep the demand.
    """
    if not isinstance(outstanding, dict) or not transcript:
        return False
    wanted = scope_paths(outstanding.get("scope") or "")
    since = CS.demand_since(outstanding)
    if not wanted or since <= 0:
        return False
    return CS.ran_after(transcript, since, lambda cmd: _runs_proof_on(wanted, cmd))


def discharge_if_evidenced(outstanding, transcript, path=None):
    """The outstanding proof demand after discharging every head the transcript already answers, or None. Mirrors `wl_classsweep.discharge_if_evidenced`: a discharged head is PROMOTED, so a demand parked in `owed` is asked next rather than lost."""
    for _ in range(2):  # a head plus its one `owed` slot
        if not outstanding or not proof_evidenced(outstanding, transcript):
            return outstanding
        PROOF_DEMAND.promote(path)
        outstanding = load_outstanding(path)
    return outstanding


_clean = wl_common.clean


def read_verdict(out):
    """(kind, payload). kind is 'silent', 'fire' or 'degraded'. See wl_classsweep.read_verdict, which this mirrors field for field."""
    po = out.get("proof_obligation") if isinstance(out, dict) else None
    if not isinstance(po, dict):
        return "degraded", "no proof_obligation object: %s" % repr(po)[:120]
    if not isinstance(po.get("applicable"), bool) or not isinstance(po.get("proof_attached"), bool):
        return "degraded", "proof_obligation applicable/proof_attached not booleans"
    kind = po.get("proof_kind")
    if kind not in PROOF_KINDS:
        return "degraded", "proof_obligation proof_kind %r is not one of %s" % (kind, PROOF_KINDS)
    if not po["applicable"]:
        return "silent", "no bulk transform in this fix-set"
    if po["proof_attached"] and kind != "none":
        return "silent", "proof attached (%s): %s" % (
            kind,
            _clean(po, "evidence", 160) or "(quoted)",
        )
    transform_kind = _clean(po, "transform_kind", 300)
    if not transform_kind:
        return "degraded", "proof_obligation fired with no transform_kind named"
    return "fire", {
        "transform_kind": transform_kind,
        "scope": _clean(po, "scope", 200),
        "instruction": _clean(po, "instruction", 300),
        "asserted": bool(po["proof_attached"]),
    }


V_REASON = (
    "PROOF OBLIGATION: a bulk mechanical transform (%s) landed with no verifiable proof "
    "attached that it did not destroy structure it does not know about.%s"
)
V_ASSERTED = " (proof is asserted, but no tool output and no sampled-file statement is quoted)"
V_ACTION = "Run: %s"
V_ACTION_DROPPED = "Run a shape-cluster diff or equivalent structural proof over the changed files (the proposed command %(why)s)."
V_ACTION_NOSEARCH = "%s"


def enforce(out, payload, fixset_files=None, displaced=None):
    """Write the proof order into a judge verdict, in place. Returns the note.

    Reuses `wl_classsweep.validate_search`/`names_destructive` rather than re-deriving them, on the same reasoning the plan this rule implements argues for: a safety check consulted twice belongs in one place.

    THE RESERVED CHECK RUNS EVEN WHEN `validate_search` SAYS OK, and it has to: `validate_search` proves a string PARSES as a read-only shell command, not that its English is safe to hand over. "commit the reflow now" carries no `git` token and no verb `_DESTRUCTIVE` recognises, so it validates as `ok` -- caught by this module's own planted control, and fixed here and in
    `wl_classsweep.enforce`, which carried the identical gap on its `search` field.

    `fixset_files` is a SEPARATE, later-added gap of the same shape: a fired finding's own SCOPE claim was never checked against what git says actually changed, only that a follow-up command built from it parses. ANNOTATES `reason` only, never suppresses (see agent/plans/PLAN-judge-prompt-trap-conflation.md and `wl_rules.scope_grounded`'s own docstring for why): this rule never
    fails closed, so a check added here may only make a fired finding more legible about its own uncertainty.

    `displaced` is the demand THIS fire is about to bump into the marker's `owed` slot (wl_rules.Demand.displace), or None. Mirrors `wl_classsweep.enforce`'s identical parameter: the STILL OWED sentence re-emits only text already validated when that demand first fired.
    """
    reason = V_REASON % (payload["transform_kind"], V_ASSERTED if payload["asserted"] else "")
    owed = []
    if isinstance(displaced, dict) and displaced.get("transform_kind"):
        reason += wl_rules.still_owed_sentence(displaced["transform_kind"])
        owed.append(
            wl_rules.owed_line(PROOF_STEP % (displaced.get("scope") or "(scope not recorded)"))
        )
    if not wl_rules.scope_grounded(payload.get("scope", ""), fixset_files):
        reason += (
            " UNVERIFIED: git's own file list for this fix-set does not match '%s' -- if that "
            "scope is not real, name the actual commit or files this transform touched, or say "
            "plainly none occurred." % (payload.get("scope") or "")[:80]
        )
    ok, why = CS.validate_search(payload["instruction"])
    reserved = wl_rules.names_operator_reserved(payload["instruction"]) if ok else ""
    verb = CS.names_destructive(payload["instruction"]) if ok else ""
    if ok and reserved:
        action = V_ACTION_DROPPED % {"why": "named `%s`, which needs the operator's ask" % reserved}
    elif ok and verb:
        action = V_ACTION_DROPPED % {"why": "named `%s`, and a proof step only reads" % verb}
    elif ok:
        action = V_ACTION % payload["instruction"]
    elif payload["instruction"]:
        verb = CS.names_destructive(payload["instruction"])
        reserved = wl_rules.names_operator_reserved(payload["instruction"])
        if verb:
            action = V_ACTION_DROPPED % {"why": "named `%s`, and a proof step only reads" % verb}
        elif reserved:
            action = V_ACTION_DROPPED % {
                "why": "named `%s`, which needs the operator's ask" % reserved
            }
        else:
            action = V_ACTION_DROPPED % {"why": why[:70] or "did not parse"}
    else:
        action = V_ACTION_NOSEARCH % (
            "Run a structural before/after comparison of the files the transform touched and "
            "report its real output (for prose, .ci/scripts/quality/shape_cluster_diff.py "
            "--rev <base-sha> <files>; for code, an AST comparison)."
        )
    wl_rules.apply_order(out, reason, action, owed)
    return "proof-obligation: %s" % payload["transform_kind"][:160]


PROOF_TTL_MIN = int(os.environ.get("WORKLIST_PROOFCHECK_TTL_MIN", "120"))
PROOF_MAX_FIRES = int(os.environ.get("WORKLIST_PROOFCHECK_MAX_FIRES", "2"))

PROOF_DEMAND = wl_rules.Demand("proofcheck", PROOF_TTL_MIN, PROOF_MAX_FIRES)


def load_outstanding(path=None):
    return PROOF_DEMAND.load(path)


def save_outstanding(payload, prior=None, path=None):
    PROOF_DEMAND.bank(
        {"transform_kind": payload["transform_kind"], "scope": payload["scope"]}, prior, path
    )


def clear_outstanding(path=None):
    PROOF_DEMAND.clear(path)


def apply_verdict(out, outstanding=None, path=None, fixset_files=None, asked=None):
    """(kind, note). Mutates `out` when the rule fires; owns the marker lifecycle.

    Mirrors `wl_classsweep.apply_verdict` exactly, including the `asked` contract: `"fresh"` displaces `outstanding` into `owed` on a fire and leaves both untouched on silent/degraded; `"followup"` banks a re-fire over `outstanding` as before and promotes a live `owed` record on silent/degraded; `None` (the default) reproduces the byte-identical legacy behaviour of always banking on fire and always clearing on silent/degraded, for any caller that has not adopted the parameter.

    `fixset_files` defaults to `None`, so every existing call site that does not know about it behaves byte-identically to before this parameter existed (see `wl_rules.scope_grounded`).

    kind is also 'ungrounded' (R20260924.19), as in `wl_classsweep.apply_verdict`: a FRESH fire whose scope is not in `fixset_files` changes nothing and returns the advisory text.
    """
    kind, payload = read_verdict(out)
    if (
        kind == "fire"
        and asked == "fresh"
        and not wl_rules.scope_grounded(payload.get("scope", ""), fixset_files)
    ):
        # UNGROUNDED IS ADVISORY (R20260924.19), exactly as in wl_classsweep.apply_verdict.
        return "ungrounded", CS.ungrounded_note("proof obligation", payload.get("scope", ""))
    if kind == "fire":
        if asked == "fresh":
            note = enforce(out, payload, fixset_files, displaced=outstanding)
            PROOF_DEMAND.displace(
                {"transform_kind": payload["transform_kind"], "scope": payload["scope"]},
                head=outstanding,
                path=path,
            )
            return "fire", note
        note = enforce(out, payload, fixset_files)
        save_outstanding(payload, outstanding, path)
        return "fire", note
    if asked == "fresh":
        return kind, payload if isinstance(payload, str) else ""
    if asked == "followup":
        PROOF_DEMAND.promote(path)
    else:
        clear_outstanding(path)
    return kind, payload if isinstance(payload, str) else ""
