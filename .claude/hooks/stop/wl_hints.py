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


# Plain constant, not a WORKLIST_* env knob -- matching wl_claimcheck's own reasoning: an untunable rule costs nothing an edit does not buy, and every WORKLIST_* name in this tree must be declared in the registry check:ci-worklist-env-registry enforces.
PROPOSAL_REFRESH_MIN = 720

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


def lessons_dir(me8, epoch):
    """The lesson-curator's output directory for one context epoch, repo-relative: agent/<me8>/lessons/e<epoch>/ (sibling of the effort tuner's agent/<me8>/effort-tune/e<epoch>/)."""
    return "agent/%s/lessons/e%s/" % (me8, epoch)


def pending_note(session_id, n):
    """The advisory line for `n` pending proposals, naming this session's curator run and its output directory. The epoch comes from the context band state; any failure reading it names epoch 0 rather than dropping the line."""
    me8 = S.agent_session_slug(session_id)
    epoch = 0
    try:
        import wl_retro

        epoch = int(wl_retro.ctx().load_state(session_id).get("epoch") or 0)
    except Exception:
        epoch = 0
    return M.N_HINT_PROPOSALS_PENDING % {
        "n": n,
        "me8": me8,
        "epoch": epoch,
        "dir": lessons_dir(me8, epoch),
    }
