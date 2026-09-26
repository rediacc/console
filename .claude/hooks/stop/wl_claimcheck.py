"""wl_claimcheck: does a completion claim's own evidence DEMONSTRATE the claim?

THE GAP THIS CLOSES WAS DOCUMENTED AS A DELEGATION THAT DOES NOT EXIST. `wl_checks.completion_evidence` says in its own docstring that "whether the evidence SUPPORTS the claim is the reggate judge's question, since every new tick already flows into it", and `citation_state` repeats the same sentence. The reggate judge was never asked it: REGGATE_PROMPT puts five questions
and every one is about regression coverage, while the `regression_gate` schema has no field an answer could land in. Two independent checks pointed at a question nobody was putting, so a tick could cite a real file at a real line that says nothing about what was claimed, and every mechanism in the stop battery stayed silent. See agent/plans/PLAN-stop-hook-task-verification.md
Part 1 for the seven mechanisms that were read in full and the measurement behind each number below.

WHAT IS MECHANICAL HERE, AND WHY SO LITTLE OF IT IS. Both candidate mechanical tests were measured against the live corpus of 342 real closing-tick notes before any of this was written, and both came back negative:

  * LEXICAL OVERLAP between the claim and its cited window does not discriminate. A real note against its OWN citation scored a median of 3 shared non-stopword tokens, with 12.4% scoring zero; the same notes re-paired with a STRANGER's citation scored a median of 2, with 26.0% scoring zero. At "score below 1 is suspect" that falsely accuses one in eight genuine claims to
    catch one in four planted mismatches, and the two distributions overlap almost completely. The number is therefore reported to the judge WITH its error rate stated in the prompt, and it is never a threshold in code.
  * "THE CITED SHA TOUCHES A FILE THE CLAIM NAMES" disagrees with 21 of the 59 ticks that carry both a sha and a path (36%), and inspection showed most of those 21 are legitimate: a sha for the code change beside a plan file that was updated in a different commit. A blocker at 36% false positives is a nagging machine by arithmetic.

So the mechanical layer computes CORROBORATION and hands it to a judge that is already being paid for, rather than rendering a verdict it cannot support. One signal earns its place unaided: `resolved-untouched`, where the citation resolves and git's own file list for the fix-set does not contain that path. It is path equality against git's answer, not word similarity, and it has no
threshold to tune.

ADVISORY, NEVER BLOCKING, and this module may not quietly become otherwise. Reasons in order of weight:

  1. The measurements above forbid it. A blocking check built on a 12.4% or a 36% false-positive rate is a nagging machine before it ships.
  2. The repeated-nag failure has already been paid for twice in this hook. `PLAN-fix-stop-hook-completion-evidence-refire.md` repaired a check that blocked ten consecutive stops with no reachable exit, and `PLAN-stop-hook-refactor-enforcement.md` names the lesson: that check re-fired forever because the finding could not be settled.
  3. A false accusation here is uniquely corrosive, because the subject is the session's honesty. Wrongly telling a truthful session that it fabricated evidence teaches it to write evidence that satisfies the checker rather than the reader, which is strictly worse than not asking. `wl_planfid` makes the same argument for why `wl_admit` never blocks: the honesty is the asset
     and must not be taxed.
  4. The layering is already decided. I7 refuses a completion that carries NO evidence and keeps refusing; this layer asks whether the evidence holds, which is a judgement, and judgements in this hook demand rather than refuse.

Enforcement is still met in the sense the sibling rules established: the message is unavoidable, it arrives in the session's own context, it names the tick and the citation, it carries a mechanically computed profile that cannot be talked out of, and it ends in a concrete next step.

GRADUATION CRITERION, written here rather than in the plan so a reader finds it where the decision lives. Every verdict appends one row to `agent/ledgers/census-claim-check.jsonl`. After 30 real verdicts, the rows answer the question directly: if `supported: no` verdicts that the session then conceded -- by re-ticking with better evidence -- exceed 80% of all `no` verdicts,
the `resolved-untouched` arm alone graduates to `wl_rules.apply_order`. Nothing graduates on the strength of how the rule feels to read.

FAIL SEMANTICS, inherited from `wl_classsweep`'s and transferring verbatim: a missing or malformed `claim_check` object never fails closed. The only thing this object can do is add an advisory, so degrading loses a demand rather than granting an exit that was otherwise refused.

SCOPE BOUNDARY, stated plainly because the tempting overclaim is one sentence away. This cannot verify a claim made only in conversational prose. The hook sees the final assistant message of a turn, and only at stop time; it cannot see a claim made mid-turn, inside a sub-agent's transcript, or in a message the session later supersedes. The design binds claims that touch a
tracked file, a worklist tick or a plan box, and nothing else -- by construction, not by omission.
"""

import hashlib
import os
import re
from typing import Any

import wl_core as C
import wl_reggate as RG
import wl_rules
import wl_store as S

# The substring the prompt section carries, used by wl_judge.judge_schema_for to decide whether `claim_check` is REQUIRED. Same contract as SWEEP_MARKER and _REGGATE_MARKER: when the prompt asks for the object, the schema requires it, so the model cannot satisfy the schema by omitting the answer.
CLAIM_MARKER = "DOES THE CITED EVIDENCE DEMONSTRATE THE CLAIM"

# The four verdicts a single piece of evidence can earn. They are shapes of CORROBORATION, not degrees of guilt: `unverifiable-shape` means the mechanical layer could not see, which must read differently from "checked and found wanting" -- the generalised lesson of the completion-evidence refire, where a check that could not see reported as if it had.
RESOLVED = "resolved"
UNTOUCHED = "resolved-untouched"
COMMIT = "commit"
VACUOUS = "unverifiable-shape"
VERDICTS = (RESOLVED, UNTOUCHED, COMMIT, VACUOUS)

SUPPORT_KINDS = ("yes", "partial", "no", "unverifiable")

CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "supported": {"type": "string", "enum": list(SUPPORT_KINDS)},
        "why": {"type": "string", "maxLength": 300},
        "instruction": {"type": "string", "maxLength": 300},
    },
    "required": ["supported", "why", "instruction"],
    "additionalProperties": False,
}

# Bounds, stated as constants because the budget argument depends on them: at most three citations at the +/-4 lines `cited_excerpts` already defaults to, and at most three sha candidates, which caps this module at seven git calls on a stop that already runs git for other reasons.
CITE_LIMIT = 3
SHA_LIMIT = 3
CLAIM_MAX = 600
EXCERPT_MAX = 700
FILES_SHOWN = 12

_WORD = re.compile(r"[a-z0-9_]{3,}")

# Tokens that match for free and therefore say nothing about support. Deliberately short: a long stoplist tuned against this corpus would be a threshold in disguise, and section 2.1 already established that no tuning of this score makes it discriminate. Tokenised by `_WORD` rather than listed, so the stoplist and the text it filters are split by ONE function -- a hand-written
# list drifts from the tokenizer the day either changes, and an entry under three characters would sit there looking like coverage while the tokenizer never emits it.
_STOP = frozenset(
    _WORD.findall(
        """a an and are as at be but by for from has have in into is it its of on or that the then
        this to was were will with not no all any one two three fix fixed fixes add added adds
        update updated now here there which when where who what why how done ran run runs"""
    )
)


def _wl_checks():
    """`wl_checks`, imported at CALL time because the two modules are mutually dependent.

    `wl_checks` imports this module to reach its call site, so a module-level `import wl_checks` here would bind a half-initialised module object during whichever import happens to run first. The citation primitives live there and must not be copied: `CITE_RE`, `citation_state` and `cited_excerpts` are the exact regexes a second implementation would get wrong. Section 2 of
    the plan records the cost of not reusing them -- a hand-rolled path regex mis-parsed every `.claude/...` dotfile path and reported 298 dead citations where the real number is 175.
    """
    import wl_checks  # noqa: PLC0415 -- deferred on purpose; see the docstring

    return wl_checks


def _tokens(text, drop=()):
    """Non-stopword word tokens, with the cited path's own tokens dropped.

    A citation's path appears in both the claim and the excerpt header for free, so counting it would score every citation as corroborating itself.
    """
    drop_set = set()
    for d in drop:
        drop_set.update(_WORD.findall((d or "").lower()))
    return {t for t in _WORD.findall((text or "").lower()) if t not in _STOP and t not in drop_set}


def overlap(claim, excerpt, drop=()):
    """Shared non-stopword tokens between a claim and its cited window.

    REPORTED, NEVER THRESHOLDED. Section 2.1 measured this exact score over 177 real note/citation pairs against 177 adversarially re-paired ones and found the distributions almost coincident. It survives here as one weak input among several, carried into the prompt beside its own error rate so the judge is not invited to treat it as proof.
    """
    return len(_tokens(claim, drop) & _tokens(excerpt, drop))


def profile(root, evidence_text, fixset_files=None):
    """The mechanical corroboration profile for ONE tick's evidence. No model call.

    `fixset_files` is git's own answer for this fix-set (`wl_reggate.fixset_files`), already computed at the call site. An EMPTY or absent list is not "the tree is clean": it means the `resolved-untouched` comparison has nothing to compare against, so the profile records `fixset_known` and the prompt says which of the two it is. Conflating them would accuse a citation of being
    untouched on missing data rather than on git's evidence, which is the shape `wl_rules.scope_grounded` already refuses.

    A citation that does NOT resolve is skipped rather than reported. I7 owns the question "is there a citation at all" and keeps owning it; this layer only ever runs on ticks that already passed it, and re-litigating a dead citation here would duplicate a check that already blocks.
    """
    text = (evidence_text or "").strip()
    prof: dict[str, Any] = {
        "claim": text[:CLAIM_MAX],
        "citations": [],
        "commits": [],
        "fixset_known": bool(fixset_files),
        "fixset_n": len(fixset_files or []),
        "shape": VACUOUS,
    }
    if not text:
        # NO CLAIM IS NOT A CLEAN CLAIM. The shape stays `unverifiable-shape` and `prompt_section` declines to ask about nothing; inventing a fifth "silent" verdict here is what would let an empty profile read as a passing one.
        return prof
    checks = _wl_checks()
    touched = {f.strip() for f in (fixset_files or []) if f and f.strip()}
    seen = set()
    for m in checks.CITE_RE.finditer(text):
        if len(prof["citations"]) >= CITE_LIMIT:
            break
        cite = m.group(0)
        if cite in seen:
            continue
        seen.add(cite)
        ok, detail = checks.citation_state(root, cite)
        if not ok:
            continue
        rel = detail.rsplit(":", 1)[0]
        excerpt = checks.cited_excerpts(root, cite, limit=1)
        # BOTH SPELLINGS ARE CHECKED against git's list: `citation_state` takes one hop through a plan-move stub, so a citation written before the move names the OLD path while the fix-set names whichever one the session actually edited. Comparing only the resolved spelling would report a file the session did touch as untouched.
        if touched and rel not in touched and m.group(1) not in touched:
            verdict = UNTOUCHED
        elif excerpt.strip():
            verdict = RESOLVED
        else:
            # Resolves, and there is nothing to quote. Rare since the stub hop was shared (0 of 186 resolving citations in the corpus, down from 9), and reported as unseeable rather than as supported.
            verdict = VACUOUS
        prof["citations"].append(
            {
                "cite": detail,
                "verdict": verdict,
                "excerpt": excerpt[:EXCERPT_MAX],
                "overlap": overlap(text, excerpt, (rel, m.group(1))),
            }
        )
    # LONGEST CANDIDATES FIRST, then the cap -- the same ordering `completion_evidence` had to learn. Every rendered tick opens with the mandatory 8-hex session tag twice and cited worklist ids are 8 hex as well, so taking the first three in text order spends the whole git budget on tokens that are never object ids.
    cands, seen_sha = [], set()
    for i, m in enumerate(checks.SHA_RE.finditer(text)):
        tok = m.group(0)
        if tok not in seen_sha:
            seen_sha.add(tok)
            cands.append((-len(tok), i, tok))
    for _neg, _i, tok in sorted(cands)[:SHA_LIMIT]:
        files = RG._diff_tree_files(root, tok)
        if files:
            prof["commits"].append({"sha": tok[:12], "files": files[:FILES_SHOWN]})
    verdicts = [c["verdict"] for c in prof["citations"]]
    # THE MISMATCH OUTRANKS THE CORROBORATION, and that ordering is the point of the module. A tick citing one file it touched and one it did not is exactly the adversarial shape (a real citation that cannot demonstrate the claim), so the headline reports the mismatch rather than averaging it away behind the citation that did resolve cleanly.
    if UNTOUCHED in verdicts:
        prof["shape"] = UNTOUCHED
    elif RESOLVED in verdicts:
        prof["shape"] = RESOLVED
    elif prof["commits"]:
        prof["shape"] = COMMIT
    else:
        prof["shape"] = VACUOUS
    return prof


# -- The prompt -------------------------------------------------------------
#
# ONE QUESTION, deliberately. The judge on a fix stop is already answering the regression gate's five, the class sweep's four and sometimes the proof obligation's; a sixth rubric with sub-parts would be the one that gets skimmed. Everything the mechanical layer knows is rendered ABOVE the question so the judge reads evidence rather than being asked to go and find it -- it
# has no tools (see wl_judge's argv) and cannot open a file.

CLAIM_PROMPT = """

DOES THE CITED EVIDENCE DEMONSTRATE THE CLAIM? ALSO fill the `claim_check`
object, about the completion claim quoted below.

A worklist tick is a COMPLETION CLAIM: it says a piece of work is finished, and
it carries evidence. An existing check already refuses a tick that carries no
evidence at all. This is the next question and it has never been asked: the
evidence resolves, but does it SHOW what the claim says?

THE CLAIM, verbatim from the tick's closing note:
%(claim)s

WHAT THE MECHANICAL LAYER FOUND, computed by git and by reading the cited lines
just now, never narrated:
%(profile)s

HOW MUCH EACH SIGNAL IS WORTH. These numbers were measured over 342 real ticks
in this repository, and they are stated so that no signal is over-weighted:

  - WORD OVERLAP between a claim and its cited window DOES NOT DISCRIMINATE.
    12.4%% of genuine claims score 0, against 26.0%% of deliberately mismatched
    ones. A low overlap is weak evidence, not a finding; do not answer `no`
    on the strength of the overlap number alone.
  - `resolved-untouched` means the citation resolves and git's file list for
    this fix-set does not contain that path. It is the strongest mechanical
    signal available, and it is still not proof: work may legitimately predate
    this session, live in a submodule, or have landed in an earlier commit, in
    which case citing a file this fix-set did not touch is correct and honest.
  - `unverifiable-shape` means the mechanical layer found nothing it could
    check -- a run id, an exit code or a URL, none of which are readable from
    inside this hook. That is different from checked and found wanting, and it
    must be answered `unverifiable`, never `no`.

THE ONE QUESTION: reading the quoted excerpt beside the quoted claim, does the
excerpt demonstrate the claim?

  yes           the cited line or file list shows the claimed work.
  partial       part of the claim is demonstrated and part is not; say which
                part in `why`.
  no            the citation resolves and does NOT show the claimed work --
                a different subject, an unrelated line, or a file the claim's
                own words say was changed and git says was not.
  unverifiable  nothing checkable was supplied, or the excerpt is empty.

`why` quotes the words that decide it, from the claim and from the excerpt.
`instruction` is the concrete next step for the session, and for anything but
`yes` that is normally to re-tick with evidence that shows the work: the commit
sha, the test output, or the file:line that really carries the change.

This object is ADVISORY. It never blocks a stop, so an honest `no` costs the
session one message and nothing else; hedging to `yes` to avoid a block buys
nothing and destroys the record this question exists to build.
"""


def _render(prof):
    """The mechanical profile as prompt text. Never the judge's job to compute."""
    rows = []
    for c in prof["citations"]:
        rows.append("  %s  [%s]" % (c["cite"], c["verdict"]))
        if c["verdict"] == UNTOUCHED:
            rows.append(
                "    git's file list for this fix-set (%d file(s)) does NOT contain that path."
                % prof["fixset_n"]
            )
        rows.append("    word overlap with the claim: %d shared token(s)" % c["overlap"])
        # `cited_excerpts` opens each block with its own `rel:line` header, which the row above already carries WITH the verdict attached. Printing both puts the same path twice inside one entry, and a prompt that repeats itself is a prompt whose structure stops being read.
        body = c["excerpt"].split("\n", 1)[1] if "\n" in c["excerpt"] else ""
        rows.append(body or "    (the cited line could not be quoted)")
    rows.extend(
        "  commit %s touched: %s" % (c["sha"], ", ".join(c["files"]) or "(no files)")
        for c in prof["commits"]
    )
    if not rows:
        rows.append(
            "  (nothing checkable: no citation resolved and no commit sha in the "
            "evidence named a real object)"
        )
    if not prof["fixset_known"]:
        # SAID OUT LOUD rather than left as an absent line. A missing fix-set list is the one input whose absence silently weakens `resolved-untouched` to nothing, and a prompt that omits it reads as though the comparison was made and passed.
        rows.append(
            "  NOTE: git returned no file list for this fix-set, so the "
            "`resolved-untouched` comparison could not be made at all."
        )
    return "\n".join(rows)


# -- The investigation, when the claim is about a plan box --------------------
#
# ADDITIVE, AND ADVISORY LIKE EVERYTHING ELSE HERE. `worklist.py --plan-investigate` records, before a box is implemented, what the tree already held about it; `--plan-tick` then refuses the box without that row and re-derives two clauses over it. Those are MECHANICAL refusals and they are not this module's business. What IS this module's business is that the judge was being
# asked "does the evidence demonstrate the claim" while a written statement of what the session found BEFORE it started sat unread in a committed ledger. Handing it over costs prompt tokens on a call already being made and no new call, and it changes nothing about the verdict's advisory character or the graduation criterion in the module docstring.

#: An 8-hex box signature, the token the ledger, the record and the investigation row all speak. Matched as a WHOLE token so a longer sha cannot be read as one.
_SIG_RE = re.compile(r"(?<![0-9a-zA-Z])([0-9a-f]{8})(?![0-9a-zA-Z])")


def investigation_for_claim(root, text):
    """The investigation row this claim is about, or None.

    MATCHED ON THE PLAN PATH OR THE BOX SIGNATURE, both of which are exact tokens, and NEVER on word similarity. This module's own measurements are the reason: the one similarity score available here does not discriminate, and a fuzzy match would attach a stranger's investigation to a claim and then quote it to the judge as though it were the session's own.

    NEWEST FIRST, so a box investigated twice is represented by the row that actually licensed the tick -- the same rule `wl_planrec.investigation_for` applies for the same reason.
    """
    claim = str(text or "")
    if not claim:
        return None
    try:
        import wl_planrec as R  # noqa: PLC0415 -- deferred; wl_planrec is not on the stop hook's hot path
    except ImportError:
        return None
    sigs = set(_SIG_RE.findall(claim))
    rows = R.read_investigations(root)
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        plan = str(row.get("plan") or "")
        if (plan and plan in claim) or (row.get("sig") in sigs):
            return row
    return None


CLAIM_INVESTIGATION = """

WHAT THE SESSION FOUND BEFORE IT STARTED, read out of
agent/ledgers/plan-investigation.jsonl rather than inferred. This row was
written BEFORE the work and its pointers were re-resolved by this process, so
it is evidence about the ORDER of events and not only about the result:

  plan:     %(plan)s
  box:      %(sig)s
  verdict:  %(verdict)s
  note:     %(note)s

  `present` means the work was ALREADY THERE and only the record was stale,
  which is a complete and honourable close -- do not read it as a session
  claiming credit for work it did not do. `absent` means the work was not in
  the tree at that point, so the claim should name what was then built.
  `partial` means the note says which half existed.
"""


def prompt_section(prof, investigation=None):
    """The prompt text to append, or "" when this stop asks nothing.

    Empty for a fix-set with no tick behind it: a commit-only fix-set carries no completion claim, and asking the judge to rule on a claim nobody made is how a rule starts firing on everything and stops being read.

    `investigation` is OPTIONAL and its absence is the ordinary case: most ticks are worklist ticks and carry no plan box. A missing row adds nothing to the prompt and is never reported as a gap here -- whether a plan box may be closed without one is `--plan-tick`'s mechanical refusal, not a judgement.
    """
    if not prof or not prof.get("claim"):
        return ""
    out = CLAIM_PROMPT % {
        "claim": "\n".join("    " + ln for ln in prof["claim"].splitlines()) or "    (empty)",
        "profile": _render(prof),
    }
    if isinstance(investigation, dict) and investigation.get("verdict"):
        out += CLAIM_INVESTIGATION % {
            "plan": investigation.get("plan") or "(unnamed)",
            "sig": investigation.get("sig") or "(none)",
            "verdict": investigation.get("verdict"),
            "note": (investigation.get("note") or "(none)")[:400],
        }
    return out


# -- The verdict ------------------------------------------------------------


def _clean(obj, key, limit):
    v = obj.get(key)
    return v.strip()[:limit] if isinstance(v, str) else ""


DEGRADED = "degraded"


def read_verdict(out):
    """(kind, payload). kind is the judge's own `supported` value, or 'degraded'.

    THE KIND IS THE ANSWER ITSELF, where the sibling rules return 'fire'/'silent'. Nothing here fires, because nothing here can block, so a two-state kind would carry no information -- and the graduation criterion in the module docstring counts `no` verdicts specifically, which a kind that collapsed `no` into "advisory" would make unanswerable from the census rows.

    'degraded' means the object was missing or unusable, which is reported and never blocked on. See the module docstring's FAIL SEMANTICS.
    """
    cc = out.get("claim_check") if isinstance(out, dict) else None
    if not isinstance(cc, dict):
        return DEGRADED, "no claim_check object: %s" % repr(cc)[:120]
    supported = cc.get("supported")
    if supported not in SUPPORT_KINDS:
        return DEGRADED, "claim_check supported %r is not one of %s" % (supported, SUPPORT_KINDS)
    payload = {
        "supported": supported,
        "why": _clean(cc, "why", 300),
        "instruction": _clean(cc, "instruction", 300),
    }
    return supported, payload


N_OK = (
    "Claim check (advisory): the judge read the tick's own citation beside its claim and "
    "found the evidence supports it. Mechanical profile: %(shape)s. %(why)s"
)
N_ADVISORY = (
    "A completion claim was checked against its own evidence and the judge answered "
    "supported=%(supported)s. Mechanical profile: %(shape)s. CLAIM CHECK: WHY: %(why)s "
    "NEXT: %(instruction)s"
)
N_DEGRADED = (
    "Claim check: a completion claim was put to the judge and no usable claim_check came "
    "back (%s). Nothing is blocked on it; the question goes unanswered for this fix-set."
)


def apply_verdict(out, prof):
    """(kind, note), the kind being the judge's `supported` value or 'degraded'. READ-ONLY on `out` -- this is the advisory decision pinned as code.

    Every sibling rule in this battery mutates the verdict through `wl_rules.apply_order`, which turns a stop into a continue and therefore into a block. This one must not, and a comment saying so is not enough: `out` is read for the judge's answer and never written, the module imports no blocking path, and a control greps this function's own source for the absence. The
    reasons are in the module docstring, and the graduation criterion recorded there is the only route by which any of this may start blocking.
    """
    kind, payload = read_verdict(out)
    shape = (prof or {}).get("shape") or VACUOUS
    if kind == DEGRADED:
        return kind, N_DEGRADED % payload
    if kind == "yes":
        return kind, N_OK % {"shape": shape, "why": payload["why"]}
    return kind, N_ADVISORY % {
        "supported": payload["supported"],
        "why": payload["why"] or "(none given)",
        "instruction": payload["instruction"] or "(none given)",
        "shape": shape,
    }


# -- The latch --------------------------------------------------------------
#
# WHY A LATCH WHEN THE FIXSET LEDGER ALREADY DE-DUPLICATES. A settled fix-set is absorbed by wl_checks and never asked again, which bounds the question to once -- but only on the path where the regression gate SETTLES. When it blocks instead, the same fix-set returns on the next stop and the claim question would ride along with it every time. The latch bounds that path
# independently, so the one thing this rule cannot become is the third repeated-nag incident.

# PLAIN CONSTANTS, where every sibling latch reads an env override. Two reasons, and the second is the binding one. A knob on an advisory that already cannot block buys nothing an edit does not; and every `WORKLIST_*` name in this tree must be declared in the registry `check:ci-worklist-env-registry` enforces, so a name added here without that declaration reds a gate to make an
# untunable rule tunable. The values match the plan's: 120 minutes, two asks.
CLAIM_TTL_MIN = 120
CLAIM_MAX_FIRES = 2


def demand_for(sig):
    return wl_rules.Demand("claimcheck-%s" % (sig or "none")[:12], CLAIM_TTL_MIN, CLAIM_MAX_FIRES)


def exhausted(sig, path=None):
    """True when this fix-set has already been asked CLAIM_MAX_FIRES times inside the TTL."""
    dem = demand_for(sig)
    return dem.fires(path) >= dem.max_fires


# -- The census -------------------------------------------------------------

CENSUS_REL = ("agent", "ledgers", "census-claim-check.jsonl")


def census_path(root):
    return os.path.join(root, *CENSUS_REL)


def _census_lock(path):
    """The flock sidecar, in TMPDIR rather than beside the ledger.

    Every other sidecar in this repo sits next to its file and needed its own `.gitignore` line to stay out of `git status` -- `agent/reggate/*.lock` records itself as the third instance of that shape. A fourth untracked `.lock` appearing in the operator's tree is a defect this module would be introducing, and the clean-tree gates would report it as one. The lock arbitrates
    only between Stop hooks on ONE machine writing ONE checkout, which is precisely what a per-machine tmp path serves.
    """
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-worklist", ".judge")
    os.makedirs(base, exist_ok=True)
    key = hashlib.sha1(path.encode("utf-8", "replace")).hexdigest()[:12]
    return os.path.join(base, "census-claim-check-%s.lock" % key)


def census(root, row):
    """Append one verdict row, so the graduation criterion is answerable from rows.

    THE SAME SHAPE AS `agent/ledgers/census-plan-record.jsonl`, deliberately, rather than a new ledger format: append-only JSONL under `agent/ledgers/`, written through the store's own locked append so two sessions stopping at once cannot tear a line. The reason the rows exist at all is that "advisory forever" is otherwise the silent outcome -- the module docstring's criterion
    names a number, and a number nobody recorded is a criterion nobody can meet.

    Failure is suppressed by the caller, never raised: a census that cannot write must not break a stop.
    """
    path = census_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # STAMPED HERE, not at the call site. The graduation criterion is a question about a WINDOW of verdicts, so a row whose author forgot the time is a row that cannot be counted; the same argument `wl_reggate.append_ledger` makes by defaulting its own.
    rec = dict(row)
    rec.setdefault("at", C.stamp_now())
    rec.setdefault("br", C.git_branch(root) or "")
    S._append_lines(path, _census_lock(path), [rec])
    return rec
