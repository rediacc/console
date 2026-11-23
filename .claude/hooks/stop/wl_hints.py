"""wl_hints: a rotating behavioral-hint line for the stop report.

WHAT THIS IS, AND ISN'T. `docs/agent-reference/HINTS.md` holds a hand-curated corpus of one-line reminders, each grounded in a rule or incident this repo already documents elsewhere (its own `Source:` field). This module reads that corpus, picks ONE entry at random per stop (round-robin: every active entry is shown once before any repeats, and a cycle boundary never repeats the
entry that just closed the previous cycle), and renders it. The line rides an output the stop was already going to produce; it is never queued and never the reason a stop produces output in the first place.

NO JUDGE CALL. The sibling advisory modules in this battery (`wl_classsweep`, `wl_shapedup`, `wl_bravedefault`) each carry a marker, a schema and a rubric prompt because each answers an EVALUATIVE question about how this particular session behaved -- a question with no artifact to compute it from. Selecting a hint is arithmetic over a corpus already on disk: exclude the ids already
shown this cycle, pick one of what remains. There is nothing for a model to decide, and the one thing a model COULD decide -- which hint is most relevant right now -- is out of scope by the operator's own specification: the rotation is random, not ranked. Spending a second model call (4.9-20.0s on the measurement `wl_agents.py` cites for the sibling matcher, with one live
stop-blocking timeout already paid for on that path) to choose between a dozen fixed sentences would not be defensible. So: no `*_MARKER`, no schema, no `apply_verdict`. That absence is deliberate, not an omission a future edit should "restore consistency" by filling in.

THIS IS A REMINDER MECHANISM, NOT AN ENFORCEMENT MECHANISM. Nothing here blocks a stop, flips a judge verdict, or adds a violation key, and no code path may ever check whether a displayed hint's advice was followed: the evidence for that does not exist in any artifact this hook reads, and a check built on the subject's own account of its behavior is satisfied by writing the right
sentence. Conflating "hint shown" with "instruction followed" is precisely the class of trap `docs/agent-reference/TRAPS.md` exists to warn about.

FAIL-OPEN, matching every sibling in this battery. `load_corpus` returns errors rather than raising: this module is consulted on the path that ends every turn in every session, so an exception here is a session that cannot stop. A missing, empty or malformed corpus degrades to silence, never a block and never a traceback.
"""

import hashlib
import json
import os
import pathlib
import random
import re
from typing import Any

import wl_core as C
import wl_store as S
import worklist_messages as M

HINTS_REL = "docs/agent-reference/HINTS.md"

# The `## ` heading is the displayed line itself; a hint whose heading does not stand alone as a complete reminder is not a hint yet. `Hint-Id`/`Source`/`Status` are read only from the trailer block between the heading and the first blank line, mirroring `wl_store.trap_entries`'s fenced-block-safe parser exactly -- a markdown example inside a hint's own body must not become a
# phantom entry, for the identical reason that guard exists there.
_HEADING_RE = re.compile(r"^## (.+)$")
TRAILER_KEYS = ("Hint-Id:", "Source:", "Status:", "Proposal:", "Enforced-By:")
TRAILER_FIELDS = ("id", "source", "status", "proposal", "enforced")
# A trailer value stops at a trailing `<!-- style-ok -->` prose-style marker, so a citation that
# must quote a literal word the R1/R2 gate would otherwise flag never leaks the marker itself into the value a consumer resolves or displays.
_MARKER_RE = re.compile(r"\s*<!--\s*style-ok\s*-->\s*$")


def hints_path(root):
    """Where the hint corpus lives. `WORKLIST_HINTS_FILE` is the seam the suite and the CI gate point at fixtures, the same seam `WORKLIST_AGENTS_DIR` is for the specialist-agent corpus."""
    env = os.environ.get("WORKLIST_HINTS_FILE")
    if env:
        return pathlib.Path(env)
    return pathlib.Path(root) / HINTS_REL


def load_corpus(path):
    """([entry, ...], [error, ...]) for one HINTS.md-shaped file. Never raises.

    An entry with no `Hint-Id:` or no `Source:` is an ERROR, not a silent skip -- the same reasoning `wl_agents.load_corpus` gives for a frontmatter-less agent file: a silent skip is how an entry stops being reachable while the file still looks healthy. `Status:` defaults to `active` when absent, since the schema names it optional-with-a-default, not optional-with-no-meaning."""
    entries: list[Any] = []
    errors: list[Any] = []
    p = pathlib.Path(path)
    if not p.is_file():
        # NOT AN ERROR, matching wl_agents.load_corpus's directory-glob precedent: a missing corpus reads as "not configured here" (every fixture that has not pointed WORKLIST_HINTS_FILE at one, and this feature's own repo before it existed), not as "was here and broke". A file that exists but cannot be READ (permissions, a bad encoding) is still a real, loud error below.
        return entries, errors
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return entries, ["%s: cannot read hint corpus (%s)" % (path, exc)]
    fence = ""
    in_trailer = False
    seen_ids = set()
    for line in text.splitlines():
        stripped = line.lstrip(" \t")
        if stripped.startswith(("```", "~~~")):
            char = stripped[0]
            if not fence:
                fence = char
            elif fence == char:
                fence = ""
            continue
        if fence:
            continue
        m = _HEADING_RE.match(line) if not line.startswith("### ") else None
        if m:
            entries.append(
                {
                    "heading": m.group(1).strip(),
                    "id": "",
                    "source": "",
                    "status": "active",
                    "proposal": "",
                    "enforced": "",
                }
            )
            in_trailer = True
            continue
        if in_trailer:
            if not line.strip():
                in_trailer = False
                continue
            for key, field in zip(TRAILER_KEYS, TRAILER_FIELDS, strict=True):
                if line.startswith(key):
                    entries[-1][field] = _MARKER_RE.sub("", line[len(key) :].strip())
                    break
            else:
                in_trailer = False
    for e in entries:
        if not e["heading"]:
            errors.append("a hint entry has an empty heading")
            continue
        if not e["id"]:
            errors.append("%r: no Hint-Id" % e["heading"][:60])
            continue
        if not e["source"]:
            errors.append("%s: no Source" % e["id"])
            continue
        if e["id"] in seen_ids:
            errors.append("%s: duplicate Hint-Id" % e["id"])
            continue
        seen_ids.add(e["id"])
    return entries, errors


def hint_pick(entries, ledger, rng=None):
    """(entry, index, total) for the ONE hint to show this stop, or None when there is nothing active.

    `ledger` is the `{"shown": {id: stamp}, "last": id}` sub-doc the caller persists in the state document. Round-robin with randomized order inside each pass: exclude ids already in `shown`, pick uniformly from what remains.
    When nothing remains the cycle has completed -- clear `shown` and pick again from the FULL active set MINUS `last`, so a cycle boundary never repeats the hint that just closed the previous one. `rng` is the whole determinism seam:
    `None` resolves to the module-level `random`, matching the seam `outq_drain` already uses, so a test drives the identical code path with `random.Random(seed)` rather than reaching for a subprocess's random state."""
    active = [e for e in entries if e.get("status") == "active"]
    if not active:
        return None
    r = rng if rng is not None else random
    shown = ledger.get("shown") or {}
    remaining = [e for e in active if e["id"] not in shown]
    if not remaining:
        shown = {}
        last = ledger.get("last")
        remaining = [e for e in active if e["id"] != last] or active
    pick = r.choice(remaining)
    ledger["shown"] = shown
    shown[pick["id"]] = True
    ledger["last"] = pick["id"]
    index = sorted(e["id"] for e in active).index(pick["id"]) + 1
    return pick, index, len(active)


def rotation(root, entries):
    """The entries the draw may pick from: `entries` minus every one whose `Enforced-By:` names a live, tested enforcer (wl_lessons.in_rotation, PLAN-experience-feedback.md P7). Fail-open like the rest of this module: any failure returns `entries` unchanged, so a broken check keeps a hint in rotation rather than silencing the corpus."""
    try:
        import wl_lessons as L

        return L.in_rotation(root, entries)
    except Exception:
        return entries


def render(entry, index, total):
    """The one-line rendering: heading, cycle position, id and source -- so a wrong hint is refutable in one second by opening what it cites, the same argument `wl_agents.py`'s matched-terms rendering makes."""
    return M.N_BEHAVIOR_HINT % (index, total, entry["heading"], entry["id"], entry["source"])


# -- The session-contribution channel -----------------------------------------
#
# WHY THIS NEVER TOUCHES HINTS.md, in one sentence: the display path reads exactly ONE file, and that file holds only reviewed text, so a proposal cannot promote itself by accident, by a bad parse, or by a future edit that flips a status field -- promotion is a write to a file this verb never opens. This is the same reasoning `wl_agents.py`'s header gives for refusing a cache ("a
# cache is precisely what would let a DELETED agent keep being recommended"), applied to the direction where a session, not a stale read, is the thing that must not decide unilaterally.

PROPOSALS_REL = ("agent", "ledgers", "hint-proposals.jsonl")


def proposals_path(root):
    return os.path.join(root, *PROPOSALS_REL)


def _proposals_lock(path):
    """The flock sidecar, in TMPDIR rather than beside the ledger -- see `wl_claimcheck._census_lock` for the identical reasoning: a fourth untracked `.lock` file is a defect this module would introduce, and the lock only ever arbitrates Stop hooks on one machine writing one checkout."""
    base = os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-worklist", ".judge")
    os.makedirs(base, exist_ok=True)
    key = hashlib.sha1(path.encode("utf-8", "replace")).hexdigest()[:12]
    return os.path.join(base, "hint-proposals-%s.lock" % key)


def proposal_id(row):
    """A proposal's id: its own `id` field, else the sha8 of (by, at, text), so rows written before ids existed get the same id every time they are read (PLAN-experience-feedback.md P2)."""
    rid = str(row.get("id") or "").strip()
    if rid:
        return rid
    key = "%s\n%s\n%s" % (row.get("by") or "", row.get("at") or "", (row.get("text") or "").strip())
    return hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()[:8]


def propose(root, by, text, source=""):
    """Append one proposal row and nothing else. Never touches HINTS.md.

    Round-tripped through `worklist.py --hint-propose <session> <text...> [SOURCE: <pointer>]`. `text` is the hint sentence itself; `source` is optional free text naming where the lesson came from, for the human reviewing the backlog rather than for the parser -- a proposal is not yet a graded entry and gets no `Hint-Id`/`Status` fields until it is promoted by hand. The row carries its `id`, which a promoted HINTS entry cites as `Proposal: <id>`."""
    row = {"by": by, "at": C.stamp_now(), "text": text.strip(), "source": source.strip()}
    row["id"] = proposal_id(row)
    path = proposals_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    S._append_lines(path, _proposals_lock(path), [row])
    return row


# A proposal can also become a gate, a test, a guard or a tool fix rather than prose (PLAN-experience-feedback.md P2). `worklist.py --hint-resolve` records that in its own ledger, so the proposals ledger keeps one row shape and the retro brief that lists a session's proposals reads only proposals.
RESOLUTIONS_REL = ("agent", "ledgers", "hint-resolutions.jsonl")


def resolutions_path(root):
    return os.path.join(root, *RESOLUTIONS_REL)


def _jsonl(path):
    """Every JSON object row of `path`, oldest first; a torn line is skipped, a missing file is []."""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def proposals(root):
    """Every proposal row, each with its `id` filled in."""
    return [
        dict(row, id=proposal_id(row)) for row in _jsonl(proposals_path(root)) if row.get("text")
    ]


def resolve_proposal(root, by, pid, pointer):
    """Append one resolution row naming `pointer` as what now carries proposal `pid`. The caller has already checked both."""
    row = {"by": by, "at": C.stamp_now(), "id": pid, "pointer": pointer.strip()}
    path = resolutions_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    S._append_lines(path, _proposals_lock(path), [row])
    return row


def cited_proposal_ids(entries):
    """The proposal ids HINTS entries cite in a `Proposal:` line (comma-separated)."""
    out = set()
    for e in entries:
        for raw in str(e.get("proposal") or "").split(","):
            if raw.strip():
                out.add(raw.strip())
    return out


def pending_proposals(root):
    """[{...proposal row with its id...}] that no HINTS entry and no live resolution has taken.

    A proposal stops being pending when a HINTS entry carries `Proposal: <id>`, or when a `--hint-resolve` row names it with a pointer that still resolves (wl_lessons.pointer_problem). Text is never matched: a reworded promotion with no cite stays pending, and so does one whose resolving guard, gate or test has since been deleted."""
    rows = proposals(root)
    if not rows:
        return []
    entries, _errors = load_corpus(hints_path(root))
    taken = cited_proposal_ids(entries)
    resolutions = _jsonl(resolutions_path(root))
    if resolutions:
        import wl_lessons as L

        live: dict = {}
        for res in resolutions:
            pid, pointer = str(res.get("id") or ""), str(res.get("pointer") or "")
            if not pid or pid in taken:
                continue
            if pointer not in live:
                live[pointer] = L.pointer_problem(root, pointer) is None
            if live[pointer]:
                taken.add(pid)
    return [r for r in rows if r["id"] not in taken]


# Source keys are spelled many ways in the ledger (101 distinct keys over 217 rows when this table was written), and a lesson that returns under a second spelling must count as one recurrence (PLAN-weekly-lessons.md D6). Each key maps to the family it belongs to; a key absent here is its own family, so a new source is never dropped, only left ungrouped until it is added.
SOURCE_FAMILIES = {
    "judge": "judge",
    "stop-judge": "judge",
    "stop-gate-judge": "judge",
    "judge-unavailable": "judge",
    "judge-timeout": "judge",
    "stop-judge-hibernate": "judge",
    "review-findings": "review-findings",
    "review-findings-block": "review-findings",
    "review-block": "review-findings",
    "review-open": "review-findings",
    "vm-check": "vm-check",
    "vmcheck": "vm-check",
    "commit-review": "commit-review",
    "commit-review-note": "commit-review",
    "plan-tick": "plan-tick",
    "plan-tick-clause1": "plan-tick",
    "roster-concurrency": "roster",
    "roster-unleased": "roster",
    "roster-dead": "roster",
    "lease-dead": "dead-lease",
    "dead-lease": "dead-lease",
}
UNSOURCED_FAMILY = "unsourced"


def source_family(source):
    """The family one proposal `source` key belongs to: trimmed and lower-cased, looked up in SOURCE_FAMILIES, an empty key is `unsourced`, an unlisted key is its own family."""
    key = str(source or "").strip().lower()
    if not key:
        return UNSOURCED_FAMILY
    return SOURCE_FAMILIES.get(key, key)


def cluster_counts(rows):
    """{family: [proposal id, ...]} over proposal rows (each with its `id`), in row order, so a cluster lists every proposal it absorbs and a reviewer can split it."""
    out: dict = {}
    for r in rows:
        out.setdefault(source_family(r.get("source")), []).append(r.get("id") or proposal_id(r))
    return out


def clusters(rows, minimum=3):
    """The families holding at least `minimum` proposals (D1's cluster threshold), largest first, ties by name."""
    counts = cluster_counts(rows)
    keep = [(f, ids) for f, ids in counts.items() if len(ids) >= minimum]
    return sorted(keep, key=lambda kv: (-len(kv[1]), kv[0]))


def lessons_dir(me8, epoch):
    """The lesson-curator's output directory for one context epoch, repo-relative: agent/<me8>/lessons/e<epoch>/ (sibling of the effort tuner's agent/<me8>/effort-tune/e<epoch>/)."""
    return "agent/%s/lessons/e%s/" % (me8, epoch)


def context_epoch(session_id):
    """(epoch, problem): the context epoch from the band state, or (0, a sentence saying why it could not be read)."""
    try:
        import wl_retro

        return int(wl_retro.ctx().load_state(session_id).get("epoch") or 0), ""
    except Exception as exc:
        return 0, " The context epoch could not be read (%s: %s), so epoch 0 is assumed." % (
            type(exc).__name__,
            exc,
        )


def pending_note(session_id, rows):
    """The advisory line for the pending proposal `rows`, naming this session's curator run, its output directory, and the source families already at D1's cluster threshold (each one box of the weekly lessons plan). The epoch comes from the context band state; any failure reading it names epoch 0 rather than dropping the line."""
    me8 = S.agent_session_slug(session_id)
    epoch, epoch_problem = context_epoch(session_id)
    ready = clusters(rows)
    note = M.N_HINT_PROPOSALS_PENDING % {
        "n": len(rows),
        "me8": me8,
        "epoch": epoch,
        "dir": lessons_dir(me8, epoch),
    }
    if ready:
        note += M.N_HINT_CLUSTERS_READY % {
            "k": len(ready),
            "families": ", ".join("%s (%d)" % (fam, len(ids)) for fam, ids in ready),
        }
    return note + epoch_problem


# -- The weekly lessons plan (agent/plans/PLAN-weekly-lessons.md D1-D4) -----------
#
# One plan a week turns pending proposals into fixes. `weekly_plan_text` builds its skeleton from the ledger (one box per cluster of 3 or more proposals, a cluster table naming every pending id), and the lesson-curator completes each box. `newest_lessons_plan` and `weekly_state` are what the `lessons-weekly` Stop check reads.

LESSONS_PLAN_PREFIX = "PLAN-lessons-"
LESSONS_PLAN_RE = re.compile(r"^PLAN-lessons-(\d{8})\.md$")
# D4: a plan older than this many days no longer covers the week.
LESSONS_CADENCE_DAYS = 7
CLUSTER_HEADING = "## Cluster table"
_TABLE_ROW_RE = re.compile(r"^\|\s*(L\d+|SINGLES)\s*\|([^|]*)\|([^|]*)\|", re.IGNORECASE)
_BOX_ID_RE = re.compile(r"^L\d+$")


def lessons_plan_name(date):
    """`PLAN-lessons-<YYYYMMDD>.md` for a `YYYYMMDD` or `YYYY-MM-DD` date."""
    return "%s%s.md" % (LESSONS_PLAN_PREFIX, str(date).replace("-", ""))


def lessons_plans(root):
    """[(date `YYYYMMDD`, repo-relative path)] of every `agent/plans/PLAN-lessons-<date>.md`, newest first. Folders under agent/plans/ (`_done`, `_removed`) count too: a finished weekly plan still marks the week as covered."""
    base = pathlib.Path(root) / "agent" / "plans"
    out = []
    try:
        paths = [p for p in base.rglob("PLAN-lessons-*.md") if p.is_file()]
    except OSError:
        return []
    for path in paths:
        m = LESSONS_PLAN_RE.match(path.name)
        if m:
            out.append((m.group(1), path.relative_to(root).as_posix()))
    return sorted(out, reverse=True)


def newest_lessons_plan(root):
    """(date, repo-relative path) of the newest weekly lessons plan, or None."""
    plans = lessons_plans(root)
    return plans[0] if plans else None


def _days_between(date8, today):
    """Whole days from `YYYYMMDD` `date8` to the `datetime.date` `today`."""
    import datetime

    return (today - datetime.date(int(date8[:4]), int(date8[4:6]), int(date8[6:]))).days


def _open_box_count(root, rel):
    """Open boxes of the plan at `rel`; raises OSError when the file cannot be read."""
    import wl_planrec

    text = (pathlib.Path(root) / rel).read_text(encoding="utf-8")
    return len(wl_planrec.open_boxes(text))


def weekly_state(root, today, pending=None):
    """(kind, detail) for the `lessons-weekly` check, `today` a `datetime.date`.

    kinds: `none` nothing is owed; `dispatch` pending proposals exist and no plan covers the last 7 days (the newest is older or absent), so the curator is due; `work` the newest plan is more than 7 days old and still has open boxes, so its oldest open box is due. `detail` is the newest plan's repo-relative path ("" for none). An unreadable plan file raises: a read that failed is not an empty plan.
    """
    pend = pending_proposals(root) if pending is None else pending
    newest = newest_lessons_plan(root)
    if newest is None:
        return ("dispatch", "") if pend else ("none", "")
    date8, rel = newest
    if _days_between(date8, today) <= LESSONS_CADENCE_DAYS:
        return ("none", rel)
    if _open_box_count(root, rel) > 0:
        return ("work", rel)
    return ("dispatch", rel) if pend else ("none", rel)


def weekly_plan_text(rows, date, owner):
    """The skeleton of `PLAN-lessons-<date>.md` for the pending proposal `rows`.

    One `[writer]` box per source family holding 3 or more proposals (`clusters`), the cluster table naming EVERY pending id exactly once (families under 3 sit on one `SINGLES` row, which the curator resolves or folds into a box), and a header that fits the plan parser. The curator replaces each box's placeholder owns and accept lines with the real ones; resolving the ids is the closing act of ticking a box (`resolved_ids_for_box`).
    """
    date8 = str(date).replace("-", "")
    iso = "%s-%s-%s" % (date8[:4], date8[4:6], date8[6:])
    counts = cluster_counts(rows)
    ready = clusters(rows)
    in_box = {f for f, _ids in ready}
    singles = [pid for f, ids in counts.items() if f not in in_box for pid in ids]
    by_id = {r["id"]: r for r in rows}
    lines = [
        "# PLAN: Weekly lessons %s -- pending hint proposals become fixes" % iso,
        "",
        "Status: approved",
        "Depends-On: no-dep -- no box waits on another plan",
        "Priority: P2 -- %d pending hint proposal(s) in %d source family(ies)"
        % (len(rows), len(counts)),
        "Concurrency: parallel -- one box per cluster, each on its own files",
        "Owns: .claude/hooks/stop/**, .claude/rediacc_hooks/**, docs/agent-reference/HINTS.md, docs/agent-reference/TRAPS.md",
        "First-Seen: %s" % iso,
        "Owner: %s" % owner,
        "Updated: %s" % iso,
        "",
        "## Ask",
        "",
        "PLAN-weekly-lessons.md D1: one box per cluster of 3 or more pending proposals, each a code change that makes the lesson unnecessary; a lesson something already enforces closes as resolved with that pointer instead.",
        "",
        CLUSTER_HEADING,
        "",
        "| Box | Family | Proposals |",
        "|---|---|---|",
    ]
    for n, (fam, ids) in enumerate(ready, 1):
        lines.append("| L%d | %s | %s |" % (n, fam, ", ".join(ids)))
    if singles:
        lines.append("| SINGLES | families under 3 | %s |" % ", ".join(singles))
    lines += ["", "## Tasks", ""]
    for n, (fam, ids) in enumerate(ready, 1):
        sample = (by_id[ids[0]].get("text") or "").strip().replace("\n", " ")[:100]
        lines += [
            "- [ ] L%d [writer] The `%s` family (%d pending proposals, first: %s): a guard, gate, check or tool fix that makes the lesson unnecessary"
            % (n, fam, len(ids), sample),
            "    Owns: <the curator names the files>",
            "    Depends on: none.",
            "    Needs: none",
            "    Accept: <the curator names the command, its control that fires and the one that stays silent>",
        ]
    lines.append("")
    return "\n".join(lines)


def parse_cluster_table(text):
    """{box id (`L1`..) or `SINGLES`: [proposal id, ...]} from the cluster table of a weekly lessons plan; rows outside the table section are ignored."""
    out: dict = {}
    in_table = False
    for line in str(text or "").splitlines():
        if line.startswith("## "):
            in_table = line.strip().lower() == CLUSTER_HEADING.lower()
            continue
        if not in_table:
            continue
        m = _TABLE_ROW_RE.match(line.strip())
        if m:
            ids = [p.strip() for p in m.group(3).split(",") if p.strip()]
            out.setdefault(m.group(1).upper(), []).extend(ids)
    return out


def box_label(body):
    """The box id (`L3`) a box body starts with, or ""."""
    words = str(body or "").split(None, 1)
    return words[0] if words and _BOX_ID_RE.match(words[0]) else ""


def resolved_ids_for_box(plan_text, body):
    """The proposal ids the cluster table lists for the box whose body is `body`: [] for a box with no table row (or a plan without a table)."""
    label = box_label(body)
    return parse_cluster_table(plan_text).get(label, []) if label else []


CLAIM_STEM = "lessons-weekly"


def weekly_block(root, worklist, session_id, today, parked=False):
    """The `lessons-weekly` block text for this stop, or "" when nothing is owed to this session.

    "" when: the stop is `parked` (the landing tree babysits and merges the PR, so the weekly cadence waits for the development tree), `weekly_state` says nothing is owed, or another live session holds the claim (wl_schedred.claim: O_EXCL file `<worklist>.schedred-claim-lessons-weekly`, keyed on the owed state, handed on when the holder's session brief goes stale). The text names the exact next command: dispatch the curator, or work the oldest open box.
    """
    if parked:
        return ""
    kind, rel = weekly_state(root, today)
    if kind == "none":
        return ""
    import wl_schedred

    me8 = S.agent_session_slug(session_id)
    holder = wl_schedred.claim(worklist, CLAIM_STEM, "%s|%s" % (kind, rel or "none"), me8)
    if holder != me8:
        return ""
    date8 = today.strftime("%Y%m%d")
    if kind == "work":
        import wl_planrec

        text = (pathlib.Path(root) / rel).read_text(encoding="utf-8")
        boxes = wl_planrec.open_boxes(text)
        return M.N_LESSONS_WEEKLY_WORK % {
            "plan": rel,
            "days": _days_between(lessons_plans(root)[0][0], today),
            "cadence": LESSONS_CADENCE_DAYS,
            "open": len(boxes),
            "box": box_label(boxes[0][2]) or boxes[0][3],
            "sig": boxes[0][3],
            "me8": me8,
        }
    pending = pending_proposals(root)
    if rel:
        why = M.N_LESSONS_WEEKLY_WHY_OLD % {
            "plan": rel,
            "days": _days_between(lessons_plans(root)[0][0], today),
            "cadence": LESSONS_CADENCE_DAYS,
        }
    else:
        why = M.N_LESSONS_WEEKLY_WHY_NONE
    return M.N_LESSONS_WEEKLY_DISPATCH % {
        "why": why,
        "pending": pending_note(session_id, pending),
        "me8": me8,
        "epoch": context_epoch(session_id)[0],
        "date": date8,
    }


_SHA_RE = re.compile(r"\b(?:commit:)?([0-9a-f]{7,40})\b")


def tick_resolution(root, rel, plan_text, selector, evidence):
    """(ids, pointer, problem) for ticking the box `selector` of the plan at `rel`, whose text before the tick is `plan_text`.

    D3/W6: ticking a box of a `PLAN-lessons-<date>.md` resolves every proposal id its cluster-table row lists. `ids` is [] for any other plan, a box with no table row, or ids already taken. `pointer` is the first `commit:<sha>` the evidence names that resolves in this tree (wl_lessons.pointer_problem), or "" with `problem` saying why none did: the caller then resolves nothing and names the ids, never writes a dead pointer.
    """
    import wl_lessons
    import wl_planrec

    if not LESSONS_PLAN_RE.match(pathlib.PurePosixPath(rel).name):
        return [], "", ""
    box = wl_planrec.select_box(wl_planrec.open_boxes(plan_text), selector)
    listed = resolved_ids_for_box(plan_text, box[2])
    if not listed:
        return [], "", ""
    pending = {r["id"] for r in pending_proposals(root)}
    ids = [pid for pid in listed if pid in pending]
    if not ids:
        return [], "", ""
    problems = []
    for sha in _SHA_RE.findall(str(evidence or "")):
        why = wl_lessons.pointer_problem(root, "commit:%s" % sha)
        if why is None:
            return ids, "commit:%s" % sha, ""
        problems.append(why)
    return (
        ids,
        "",
        problems[0] if problems else "the evidence names no commit sha to point the proposals at",
    )
