"""Refuse a Write or Edit that leaves a live plan without a valid `Depends-On:` header.

THE ORDER (operator, 2026-09-24): "we should not start implementing a plan before the required plan completes. It should be a mandatory field and should have at least explicit 'no-dep' if there is really no dependency." This is the write-time half of agent/plans/PLAN-plan-dependencies.md section 2a (T3). The CI gate `check_plan_deps.py` is the merge-time backstop, and both read the one grammar in `.claude/hooks/stop/wl_plandeps.py`.

IT JUDGES THE RESULTING DOCUMENT, NOT THE NEW TEXT. A Write is judged on its content. An Edit or MultiEdit is APPLIED to the on-disk text (`old_string` -> `new_string`, honouring `replace_all`, edits in sequence) and the result is judged, which is exact where a union of old and new text is only approximate, and it catches an Edit that deletes the line. The plan graph is loaded from the tree the file lives in with the result in place of the file, so a cycle the edit would close is visible.

SCOPE. `agent/plans/PLAN-*.md` at the top level only. `_done/`, `_removed/`, `.claude/plans/` and every other file pass untouched. A result whose Status is a stub (`moved`), finished (`wl_planfile.FINISHED_STATES`) or `removed` is exempt: nothing can start it.

REFUSED: missing, malformed, dangling, withdrawn, ambiguous, a self-dependency, a cycle through this plan (codes D1-D7, shared with the gate).

THE X FIELDS (agent/plans/PLAN-plan-priority-concurrency.md section 6a, T4). The same result document is judged for `Priority:`, `Concurrency:` and `Owns:` through `wl_planconc.x_findings` (D10-D16, shared with the gate): every X finding, missing or malformed, is refused.

THE OPERATOR FREEZE. An on-disk `Priority:` carrying `(operator)` is the operator's: an Edit or Write that drops the line, drops the marker, or changes the level or the reason (whitespace-normalised) is refused, and so is introducing `(operator)` on a line that had none. The one escape carries no token: ALLOWED when the new line still carries `(operator)` AND the operator's latest turn (`wl_admit.turn_tools`), or an AskUserQuestion answer after it, names both the plan (basename or slug) and the new `P0`-`P3`. The AI can write neither. Bash writes bypass this chain; CI D17 is the backstop.

PRE-BACKFILL RATCHET. The plan lands this guard in the same commit as the backfill of the field into every live plan (T10) and gives it no grandfather clause. In a shared working tree the guard is live the moment this file exists, while about thirty plans still lack the field; refusing every box tick on those plans would stop every parallel writer. So while `PRE_BACKFILL_RATCHET` is True, an edit that leaves a plan's pre-existing findings unchanged or fewer (same codes, no new one) is ALLOWED with a warning naming them, and anything that adds a finding is refused. T10 sets it to False in the commit that backfills the field; the suite reads the constant and flips its expectations with it.

THE LIVE-PROOF LINE (agent/plans/PLAN-tested-on-bench.md V3). A NEW plan (no file on disk yet) whose `Owns:` hit a deployable surface in `.ci/config/proof-tiers.json` must carry a `Live-Proof:` line (LP1). The surfaces are read through `rediacc_ci.proof.surfaces` (`syspath.import_from_ci`), and an Owns glob hits a surface when `wl_planconc.owns_overlap` finds a shared path that the map's excludes do not drop; a bare submodule path (`private/renet`, the map's `pointer_only`) names the gitlink alone, so it overlaps no surface glob, while `private/renet/` normalises to `private/renet/**` and claims the code. On ANY live plan a `Live-Proof:` line that is malformed, emphasised, duplicated or outside the window is refused when the edit introduces that finding (an existing broken line is the CI gate's), and a `none` whose value is new or changed must resolve its cited ruling against the worklist store and the quoted file (LP2, `wl_plandeps.resolve_live_proof_waiver`). Existing plans without the line pass: box V7 migrates them and the gate judges them. A surface map that cannot be imported costs only this check, with a warning.

ITS EVIDENCE. `OWN_SUITE = True` (never bash, so no golden), so the dedicated suite `.claude/rediacc_hooks/guards/test-block_plan_without_depends.py` drives this guard through the dispatcher in both directions against fixture plan trees, and plants `DEFECT` in-process; `.claude/hooks/stop/test-plandeps.py` covers the grammar it imports.

FAILS OPEN, LOUDLY, when the grammar module cannot be imported (the sibling guards' convention). CI D1-D7 is the backstop.
"""

import pathlib
import re
import sys

from rediacc_hooks import hookio, syspath

CHAIN = "pre-edit"
OWN_SUITE = True
ORDER = 13
# Read by check:ci-guard-mention-anchoring: this guard judges the RESULTING plan's header, so a sentence written as a plan's whole content is refused for losing `Depends-On:`, not for mentioning anything. The gate probes it by appending the sentence to a valid plan instead.
ANCHORING = "structure: refuses a live plan whose resulting text lacks a valid Depends-On header, never a phrase in it"

# See the module docstring. PLAN-plan-dependencies T10 sets this to False in the commit that backfills the field.
PRE_BACKFILL_RATCHET = False

# The operator freeze's comparison (PLAN-plan-priority-concurrency.md section 8): planting "" lets the AI change an operator value, and the EDGE_CASE that introduces `(operator)` with no operator turn must then change. The suite also plants the D1-D7 verdict (`VERDICT_DEFECT`).
DEFECT = ("frozen = _freeze(before_h, header, rel, doc)", 'frozen = ""')
VERDICT_DEFECT = ("problems = graph.check(rel)", "problems = []")
# The Live-Proof verdict (PLAN-tested-on-bench V3): planting it drops every LP1/LP2 refusal.
LIVE_DEFECT = ("lprob = _live_findings(deps, conc, header, before_h, tree, rel, ev)", "lprob = []")

STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"
PLAN_RE = re.compile(r"(?:^|/)agent/plans/PLAN-[^/]+\.md$")

UNEXAMINED = (
    "block-plan-without-depends: the plan-header grammar could not be loaded (%s); this "
    "edit passed UNEXAMINED. check:ci-plan-deps is the backstop."
)

HEADER = """BLOCKED: %s would be a live plan without a valid header (`Depends-On:` plus the Priority/Concurrency/Owns lines, and `Live-Proof:` when Owns hit a deployable surface).

A plan does not start before the plans it needs are finished, so every live plan
says what it needs, or says why it needs nothing:

"""

FOOTER = """
The two accepted shapes, one line inside the first 10 lines (right after `Status:`):

    Depends-On: PLAN-a.md, PLAN-b.md
    Depends-On: no-dep -- <reason, one line, 12+ chars>

Bare basenames, never paths; `PLAN-y.md#<task>` names one box of another plan.
A proposal from what the plan cites:

    .ci/scripts/quality/check_plan_deps.py --draft %s
"""

_ABS = "/nonexistent-plan-deps-probe/agent/plans"

EDGE_CASES = [
    # The refusals, on a new plan in this tree.
    (
        "a new live plan without the field",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\n",
            },
        },
    ),
    (
        "a malformed value (a path token)",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: agent/plans/PLAN-x.md\n",
            },
        },
    ),
    (
        "a dangling token",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: PLAN-zz-nowhere.md\n",
            },
        },
    ),
    (
        "a self-dependency",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: PLAN-zz-probe.md\n",
            },
        },
    ),
    (
        "no-dep with a placeholder reason",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- n/a\n",
            },
        },
    ),
    # The allows: the same plan, fixed; and everything out of scope or exempt.
    (
        "no-dep with a reason",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- a probe plan with no upstream work\n",
            },
        },
    ),
    (
        "a stub",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-zz-probe.md\n",
            },
        },
    ),
    (
        "a finished record",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: compacted\n",
            },
        },
    ),
    (
        "a _done/ path",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/_done/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\n",
            },
        },
    ),
    (
        "a harness plan",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".claude/plans/zz-probe.md",
                "content": "# P\n\nStatus: draft\n",
            },
        },
    ),
    (
        "a non-plan doc",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/zz-probe.md", "content": "Status: draft\n"},
        },
    ),
    (
        "an Edit to a plan that does not exist (the tool itself fails)",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "%s/PLAN-zz-probe.md" % _ABS,
                "old_string": "a",
                "new_string": "b",
            },
        },
    ),
    ("no file path at all", {"tool_name": "Write", "tool_input": {"content": "Status: draft\n"}}),
    # The X fields and the operator freeze.
    (
        "a malformed Priority",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- a probe plan with no upstream work\nPriority: P7\n",
            },
        },
    ),
    (
        "the AI introducing an operator Priority with no operator turn",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- a probe plan with no upstream work\nPriority: P1 (operator)\n",
            },
        },
    ),
    (
        "an AI Priority",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- a probe plan with no upstream work\nPriority: P1 -- proposed by AI\nConcurrency: parallel\nOwns: docs/zz-probe.md\n",
            },
        },
    ),
]


FROZEN = """BLOCKED: Priority on %s is operator-set; the AI never changes it.

  %s

Ask the operator (AskUserQuestion), or they edit the line. An operator-directed
change is accepted when the new line still carries `(operator)` and the operator's
latest turn (or an AskUserQuestion answer after it) names both the plan and the new
`P0`-`P3`.
"""

X_FOOTER = """
The X header lines (PLAN-plan-priority-concurrency.md section 1), inside the first 12 lines:

    Priority: P0|P1|P2|P3 [-- <reason>]            (`(operator)` is the operator's alone)
    Concurrency: parallel [-- <reason>]  |  exclusive -- <reason, 12+ chars>
    Owns: <glob>[ (<note>)], <glob>, ...  |  none -- <reason, 12+ chars>

    .ci/scripts/quality/check_plan_deps.py --set-x %s "Owns: ..." --write
"""

LP_FOOTER = """
The Live-Proof line (PLAN-tested-on-bench.md Design item 2), inside the first 12 lines:

    Live-Proof: bench|hostinger[, <target>...] -- <reason, 12+ chars>
    Live-Proof: none -- <reason citing a closed #<item id> or "<operator quote>" in <path>>

Every deployable surface the Owns hit needs a target admissible for it (proof-tiers.json
`surfaces.<name>.live`); edge and stable are never live-proof targets.
"""

SURFACES_MOD = "rediacc_ci.proof.surfaces"
UNMAPPED = (
    "block-plan-without-depends: the surface map could not be loaded (%s); the Live-Proof "
    "requirement of %s passed UNEXAMINED. check:ci-plan-live-proof is the backstop."
)

PLAN_LEVEL_RE = re.compile(r"\bP([0-3])\b")


def _grammar():
    """(wl_plandeps, wl_planconc), with the stop directory on sys.path for the import and for `finished_states`' lazy wl_planfile import. The caller removes the entry again."""
    import wl_planconc
    import wl_plandeps

    return wl_plandeps, wl_planconc


def _operator_texts(transcript_path):
    """The operator's latest turn and every AskUserQuestion answer after it, from the transcript tail. [] when there is no transcript: then there is no escape, which is the freeze's safe side."""
    if not transcript_path:
        return []
    try:
        import json

        import wl_admit
    except ImportError:
        return []
    _tools, last = wl_admit.turn_tools(transcript_path)
    texts = [last] if last else []
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - wl_admit.TAIL_BYTES))
            chunk = fh.read()
    except OSError:
        return texts
    asks: set[object] = set()
    answers: list[str] = []
    for raw in chunk.split(b"\n"):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        # wl_admit's one definition of "the operator spoke", not a second copy of it.
        if wl_admit._is_operator_turn(rec):
            answers = []
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "AskUserQuestion":
                asks.add(block.get("id"))
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in asks:
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(str(b.get("text") or "") for b in body if isinstance(b, dict))
                answers.append(str(body or ""))
    return texts + answers


def _operator_directed(rel, new_pr, doc):
    """True when an operator turn names this plan and the new level."""
    base = rel.rsplit("/", 1)[-1]
    slug = base[len("PLAN-") : -len(".md")]
    for text in _operator_texts(doc.get("transcript_path")):
        named = base in text or re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(slug), text)
        if named and str(new_pr.level) in PLAN_LEVEL_RE.findall(text):
            return True
    return False


def _freeze(before, after, rel, doc):
    """Why the result breaks the operator freeze, or "". `before` is the on-disk header (None for a new file)."""
    was = before.priority if before is not None else None
    now = after.priority

    def norm(t):
        return " ".join((t or "").split())

    if was is not None and was.operator:
        same = (
            now is not None
            and now.operator
            and (now.level, norm(now.reason)) == (was.level, norm(was.reason))
        )
        if same:
            return ""
        if now is not None and now.operator and _operator_directed(rel, now, doc):
            return ""
        if now is None:
            return "the edit drops the operator-set `Priority: %s`" % was
        if not now.operator:
            return "the edit demotes the operator-set `Priority: %s` to the AI value `%s`" % (
                was,
                now,
            )
        return "the edit changes the operator-set `Priority: %s` to `%s`" % (was, now)
    if now is not None and now.operator and not _operator_directed(rel, now, doc):
        return (
            "the edit introduces `Priority: %s`, and only an operator turn can mark a value `(operator)`"
            % now
        )
    return ""


def _owned_surfaces(conc, owns):
    """{surface: [Owns glob, ...]} for the deployable surfaces a plan's Owns hit, from the one map (`rediacc_ci.proof.surfaces`). Raises ImportError (or the map's own error) when the map cannot be read; the caller warns and skips."""
    surfaces = syspath.import_from_ci(SURFACES_MOD)
    hits = {}
    for name, surface in surfaces.MAP.surfaces.items():
        for mine, _theirs, witness in conc.owns_overlap(owns.globs, surface.globs):
            if not surfaces.excluded(witness):
                hits.setdefault(name, []).append(mine)
    return hits


def _live_findings(deps, conc, header, before_h, tree, rel, ev):
    """[(code, message)] for the result's `Live-Proof:` line. See the module docstring: required only on a NEW plan whose Owns hit a surface; grammar findings only when the edit introduces them; a new or changed `none` must resolve its ruling."""
    is_new = before_h is None
    required = False
    owns = header.owns
    proof = header.live_proof
    was = before_h.get(deps.LIVE_PROOF) if before_h is not None else None
    now = header.get(deps.LIVE_PROOF)
    changed = now is not None and (was is None or was.value != now.value)
    hits = {}
    surface_live = {}
    declared = proof is not None and not proof.none
    if owns is not None and owns.globs and ((is_new and now is None) or (declared and changed)):
        try:
            hits = _owned_surfaces(conc, owns)
            surface_live = {
                name: surface.live
                for name, surface in syspath.import_from_ci(SURFACES_MOD).MAP.surfaces.items()
            }
        # The map raises its own MapError (a ValueError) at import; any failure is blindness, said aloud.
        except Exception as exc:
            ev.warn(UNMAPPED % (exc, rel))
            hits = {}
        required = is_new and now is None and bool(hits)
    out = deps.live_proof_findings(header, required)
    if required:
        out = [
            (code, "%s (surfaces: %s)" % (msg, ", ".join(sorted(hits))))
            if msg.startswith("no `")
            else (code, msg)
            for code, msg in out
        ]
    if not is_new:
        had = set(deps.live_proof_findings(before_h, False))
        out = [f for f in out if f not in had]
    if declared and changed and hits:
        # LP2 (PLAN-tested-on-bench item 2): every touched surface needs a declared target its
        # `live` list admits, and every declared target must be admissible for a touched surface.
        for name in sorted(hits):
            if not set(proof.targets) & set(surface_live.get(name, ())):
                out.append(
                    (
                        deps.LP_WAIVER,
                        "%s: surface `%s` needs one of %s, declared %s"
                        % (
                            deps.LIVE_PROOF,
                            name,
                            ", ".join(surface_live.get(name, ())) or "(none)",
                            ", ".join(proof.targets),
                        ),
                    )
                )
        usable = set().union(*(surface_live.get(n, ()) for n in hits))
        for tok in proof.targets:
            if tok not in usable:
                out.append(
                    (
                        deps.LP_WAIVER,
                        "%s: target `%s` is admissible for none of the touched surfaces (%s)"
                        % (deps.LIVE_PROOF, tok, ", ".join(sorted(hits))),
                    )
                )
    if proof is not None and proof.none and changed:
        import wl_planfile

        ok, why = deps.resolve_live_proof_waiver(
            tree, rel, proof, wl_planfile.store_item_states(tree)
        )
        if not ok:
            out.append((deps.LP_WAIVER, "%s: %s" % (deps.LIVE_PROOF, why)))
    return out


def _result_text(doc, path):
    """(text, reason) for the document the tool call would leave, or (None, why) when it cannot be computed (the tool itself would fail, so there is nothing to judge)."""
    tin = doc.get("tool_input") or {}
    if not isinstance(tin, dict):
        return None, "no tool_input"
    if "content" in tin:
        return str(tin.get("content") or ""), ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, "the file does not exist, so the Edit fails on its own"
    edits = tin.get("edits")
    if not isinstance(edits, list):
        edits = [tin]
    for edit in edits:
        if not isinstance(edit, dict):
            return None, "an edit is not an object"
        old = str(edit.get("old_string") or "")
        new = str(edit.get("new_string") or "")
        if not old or old not in text:
            return None, "old_string is absent, so the Edit fails on its own"
        text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text, ""


def run(ev):
    doc = ev.doc
    if not isinstance(doc, dict):
        return hookio.ALLOW
    file_path = ev.first(("tool_input", "file_path"))
    if not file_path:
        return hookio.ALLOW
    # Where the write LANDS (#bc7d998c, the 3f53e99e.1 sweep): `agent/plans/x/../PLAN-a.md` and a directory symlink into `agent/plans` were out of scope as typed and allowed. `hookio.landing` is the one reading every pre-edit guard shares (9c6817f3.8); the plan's tree and name are read from the landing. A path the OS refuses (an embedded NUL, 9c6817f3.5) comes back as typed and is judged by its text, so a plan-shaped one is still held to the rule rather than raising.
    path = pathlib.Path(hookio.landing(file_path, ev.field("cwd") or None)[0])
    if not PLAN_RE.search(path.as_posix()):
        return hookio.ALLOW
    tree = path.parents[2]
    rel = "agent/plans/%s" % path.name

    text, _why = _result_text(doc, path)
    if text is None:
        return hookio.ALLOW

    inserted = syspath.on_sys_path(STOP_DIR)
    try:
        try:
            deps, conc = _grammar()
            finished = deps.finished_states()
        except (ImportError, OSError, SyntaxError) as exc:
            ev.warn(UNEXAMINED % exc)
            return hookio.ALLOW
        header = deps.parse_header(text)
        try:
            before_text = path.read_text(encoding="utf-8") if path.is_file() else None
        except OSError:
            before_text = None
        before_h = deps.parse_header(before_text) if before_text is not None else None
        # The freeze runs on EVERY plan edit, finished plans included: a record's operator value is still the operator's.
        frozen = _freeze(before_h, header, rel, doc)
        if frozen:
            ev.warn_raw(FROZEN % (rel, frozen))
            return hookio.DENY
        if (
            deps.is_stub_header(header)
            or header.status in finished
            or header.status == deps.REMOVED_STATUS
        ):
            return hookio.ALLOW
        graph = deps.Graph.load(tree, override={rel: text})
        problems = graph.check(rel)
        xprob = [(f.code, f.message) for f in conc.x_findings(header, text)]
        lprob = _live_findings(deps, conc, header, before_h, tree, rel, ev)
        xprob += lprob
        if not problems and not xprob:
            return hookio.ALLOW
        if problems and PRE_BACKFILL_RATCHET and path.is_file():
            before = deps.Graph.load(tree).check(rel)
            had = {code for code, _ in before}
            if before and {code for code, _ in problems} <= had and not xprob:
                ev.warn(
                    "block-plan-without-depends: %s still lacks a valid `Depends-On:` (%s); allowed "
                    "only until the backfill (PLAN-plan-dependencies T10). Fix it with "
                    "`.ci/scripts/quality/check_plan_deps.py --draft %s`."
                    % (rel, ", ".join(sorted(had)), rel)
                )
                return hookio.ALLOW
    finally:
        if inserted and str(STOP_DIR) in sys.path:
            sys.path.remove(str(STOP_DIR))

    both = problems + xprob
    lines = [HEADER % rel]
    for code, msg in both[:12]:
        lines.append("  %s  %s\n" % (code, msg))
    if len(both) > 12:
        lines.append("  ... and %d more\n" % (len(both) - 12))
    lines.append(FOOTER % rel)
    if len(xprob) > len(lprob):
        lines.append(X_FOOTER % rel)
    if lprob:
        lines.append(LP_FOOTER)
    ev.warn_raw("".join(lines))
    return hookio.DENY
