"""wl_planfid: block a session that papers over an APPROVED PLAN with umbrella
worklist items instead of tracking the plan's actual tasks.

WHY THIS EXISTS, from an incident on 2026-08-19 rather than from theory. The
operator approved a plan at ~/.claude/plans/memoized-gliding-kay.md carrying four
waves and roughly fifteen discrete tasks. The session seeded its worklist with
exactly two items:

    www round 4 Wave A
    www round 4 Waves B-D

The operator caught it by hand: "you took it easy and wrote Round 4 which is not
precise! We need individual items for stop hook."

That is not a cosmetic naming complaint. The Stop battery's entire enforcement is
"a turn cannot end while an open item tagged with this session remains", and that
enforcement is only as good as the DECOMPOSITION behind it. One umbrella item is
indistinguishable, to every check in this directory, from one small task: the
hook sees a queue of length two and asks the same questions it would ask of a
session with two afternoons of work left. Worse, an umbrella item can be TICKED,
and the tick-evidence gate accepts one citation for twenty tasks. So the failure
is not "an item was badly worded", it is "the instrument was disarmed and still
reported green" -- the exact class TRAPS.md exists for.

WHY IT BLOCKS, and this is the deliberate opposite of wl_admit next door.
wl_admit never blocks because it triggers on PROSE, on a session voluntarily
writing "I broke something", and punishing that teaches evasion; the honesty is
the asset and must not be taxed. Nothing here is voluntary. The trigger is the
SHAPE of tracked work measured against a document the operator already approved,
and the remedy is bounded, mechanical, and known in advance: write down the tasks
the plan already lists. There is no confession to chill and no judgement call to
punish. A non-blocking version would also be self-defeating in a way the
admission detector is not: its only non-blocking consequence could be to add a
worklist item, and the defect under detection is precisely that this session
writes worklist items which do not mean what they say. Asking an umbrella-writing
session to police itself with one more item it can tick with a sentence is not a
control. So it blocks, with three named exits, exactly like wl_reggate.

WHY IT FAILS OPEN ON A BROKEN JUDGE, which is the opposite of wl_judge's
no-escape-hatch contract, and the difference is the TRIGGER. wl_judge gates every
stop and wl_reggate triggers on ARTIFACTS (a fix commit, a tick), so failing
closed there costs a session that really did land a fix. This one triggers on a
HEURISTIC about item shape. Failing closed would mean that any session with an
approved plan and a coarse-looking queue is walled in permanently the moment the
claude CLI is unavailable, for a suspicion no artifact supports. And unlike the
stop judge, its absence opens no hatch: every other check in the battery, open
items included, still runs. A failure is QUEUED for the session's next clean stop
rather than dropped, because the queue survives the block stops this session is
likely to be having; the trade is that it is told late rather than not at all.

TWO TIERS, same discipline as wl_admit:

    Tier 1 (cost filter)  deterministic, no tokens. Find the approved plan, count
                          its discrete tasks, count this session's tracked items,
                          look for umbrella-shaped open items. Only a plan that
                          EXISTS plus a shortfall or an umbrella spends a call.
    Tier 2 (judgement)    haiku reads the plan and the items and answers whether
                          the items are a faithful decomposition. Every claim it
                          makes is VERIFIED against the artifacts before it can
                          block: a named umbrella id must be a real OPEN item of
                          this session, and a named missing task must match a
                          line the plan parser itself calls a task. An
                          unevidenced "unfaithful" never blocks, and neither
                          does an umbrella claim on its own -- the block needs
                          the checkable half, a plan task nothing tracks.

                          Both of those rules are paid for. The first corpus run
                          against the real model put a FALSE POSITIVE on the
                          board twice out of two, quoting the plan's locked
                          DECISIONS at a worklist that was already correctly
                          decomposed. See apply_planfid_verdict.

WHY THE MODEL IS NOT OPTIONAL. The two prefilter signals are both shape, and
shape is exactly what a coarse item can fake. "r4-B implement the solution-page
bottom" is long, specific-sounding, carries no wave word, and is still one item
covering four plan tasks. The regexes cannot see that; only reading the plan
next to the items can. The prefilter is a COST FILTER and never the last word.

RESIDUALS, named rather than pretended away:
  - PLAN DISCOVERY IS TRANSCRIPT-BOUND. The approval is an attachment record of
    type `plan_mode_exit` carrying planFilePath. If the harness ever stops
    writing it, this check silently stops firing. `--selftest` pins the record
    shape so that regression is at least visible in the suite.
  - REJECTION IS UNPROVEN. Across the 40 most recent transcripts in this project
    every ExitPlanMode had exactly one matching plan_mode_exit (4 and 4), so no
    REJECTED plan appears in the corpus and it is unverified whether a rejection
    also emits the record. Guarded by requiring planExists AND the file to be
    readable AND non-trivial, which is the best available proxy.
  - THE REPO'S OWN `agent/PLAN-<slug>.md` CONVENTION IS NOT COVERED. Those are
    already tracked by wl_checks.plan_records / plan_drift_rows, and more to the
    point they carry no APPROVAL signal: nothing records that the operator said
    yes to one. This check is about a document the operator accepted, so it
    reads only the harness plan the acceptance names. Extending it is a natural
    follow-up, not an omission.
  - RECALL IS FLAKY AND MEASURED, NOT ASSUMED. Repeated corpus runs of the same
    prompt disagreed with themselves on the positive cases. The gate is
    asymmetric to match (see RECALL_FLOOR): a false positive fails it outright,
    a miss is a rate. So this catches the incident most of the time, not every
    time, and that is the honest claim.
  - SUB-AGENT PLANS ARE OUT OF SCOPE. Plan agents write their own plan files;
    those live in sidechain transcripts, not the session's, so they are not seen
    here. That is correct for now: the operator approved the SESSION's plan.
"""

import contextlib
import hashlib
import json
import math
import os
import pathlib
import re
import sys
import tempfile

import wl_judge

# ---- Tier 1: finding the approved plan --------------------------------------

# The attachment the harness writes when the operator ACCEPTS a plan. Matched as
# a raw byte substring first, because a stop hook may not spend a JSON parse on
# every line of a 35 MB transcript.
EXIT_TOKEN = b'"plan_mode_exit"'
PLAN_PATH_RE = re.compile(r'"planFilePath"\s*:\s*"((?:[^"\\]|\\.)*)"')
PLAN_EXISTS_RE = re.compile(r'"planExists"\s*:\s*(true|false)')
SIDECHAIN_RE = re.compile(r'"isSidechain"\s*:\s*true')
# Bound the first scan of a transcript this session has never scanned. 256 MB is
# far above the largest observed here (35 MB) and still bounds the worst case.
FIRST_SCAN_CAP = int(os.environ.get("WORKLIST_PLANFID_SCAN_CAP", str(256 * 1024 * 1024)))
CHUNK = 1 << 20
# A window around the token wide enough to hold the whole attachment record.
WINDOW = 4096


def scan_plan_exit(path, start=0):
    """(plan_path_or_empty, bytes_scanned).

    Scans FORWARD from `start` for the LAST plan_mode_exit attachment and returns
    the plan file it names. `bytes_scanned` is the caller's next `start`, so a
    long-lived session pays the full scan once and the delta thereafter.

    Never raises. A transcript that shrank (a rotation, a different session)
    resets to zero rather than reading from a meaningless offset.
    """
    if not path or not os.path.exists(path):
        return "", 0
    try:
        size = os.path.getsize(path)
    except OSError:
        return "", 0
    if start > size:
        start = 0
    if start == 0 and size > FIRST_SCAN_CAP:
        start = size - FIRST_SCAN_CAP
    found = ""
    try:
        with open(path, "rb") as f:
            f.seek(start)
            carry = b""
            while True:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                buf = carry + chunk
                idx = 0
                while True:
                    i = buf.find(EXIT_TOKEN, idx)
                    if i < 0:
                        break
                    idx = i + 1
                    window = buf[max(0, i - WINDOW) : i + WINDOW].decode("utf-8", "replace")
                    if SIDECHAIN_RE.search(window):
                        continue  # a sub-agent's plan, not the session's
                    ex = PLAN_EXISTS_RE.search(window)
                    if ex and ex.group(1) != "true":
                        continue
                    m = PLAN_PATH_RE.search(window)
                    if m:
                        with contextlib.suppress(ValueError):
                            found = json.loads('"%s"' % m.group(1))
                # Keep a tail so a token straddling a chunk boundary is not lost.
                carry = buf[-WINDOW:]
    except OSError:
        return found, start
    return found, size


# A plan shorter than this is a stub, not a decomposable plan.
MIN_PLAN_CHARS = 400


def read_plan(plan_path):
    """The plan's text, or "" when there is nothing worth judging."""
    if not plan_path:
        return ""
    try:
        text = pathlib.Path(plan_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text if len(text) >= MIN_PLAN_CHARS else ""


# ---- Tier 1: counting what the plan asks for --------------------------------

FENCE_RE = re.compile(r"^\s*```")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# Headings under which bullets are TASKS rather than context. Everything else in
# a plan (Context, Decisions, Verified facts, Out of scope) is prose in list
# clothing, and counting it inflates the task count, which makes the shortfall
# signal fire on sessions that decomposed perfectly well.
ACTION_WORD_RE = re.compile(
    r"\b(wave|phase|step|stage|task|plan|implement|work|change|deliverab"
    r"|round|milestone|part|build|todo|to-do|action)\w*\b",
    re.IGNORECASE,
)


def is_action_heading(title):
    """True when a heading NAMES work, tested on its first three words only.

    MEASURED against the real plan, and the anchoring is the whole point. A
    plain "does an action word appear anywhere" test matched
    "Verified facts the plan depends on" on the word `plan`, which pulled ten
    background FACTS into the task list. That inflates the count (harmless, it
    only makes the shortfall signal shyer) and, far worse, makes every one of
    those facts quotable as an untracked "task" -- reopening exactly the false
    positive the missing-entry verification was tightened to close.

    A section is about work when its NAME leads with a work word, not when a
    work word turns up in the middle of a sentence-shaped heading. `scope` was
    dropped from the vocabulary for the same reason: it leads "Out of scope".
    """
    words = re.sub(r"[^A-Za-z0-9\s-]", " ", title or "").split()[:3]
    return bool(ACTION_WORD_RE.search(" ".join(words)))


# Indent 0-3 only: a nested bullet is detail about its parent, not a peer task.
BULLET_RE = re.compile(r"^(?P<ind> {0,3})(?:[-*+]|\d+[.)])\s+(?P<body>\S.*)$")
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+(?P<body>\S.*)$")


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# How much of a claimed missing task must be built out of one real task line.
# 0.7 measured against the corpus: a paraphrase or a truncated quote of a real
# task clears it, while the plan's DECISIONS bullets score 0.23-0.33 against
# their nearest task and are rejected.
TASK_MATCH = float(os.environ.get("WORKLIST_PLANFID_TASK_MATCH", "0.7"))
MIN_MATCH_TOKENS = 3


def matches_a_task(claim, task_tokens):
    """Is this claimed missing task actually one of the plan's task lines?

    NOT a substring test, and the loosening is measured rather than a hunch. The
    strict version demanded the claim appear VERBATIM inside a task, and the
    corpus run then MISSED the real incident in one round of two: haiku quotes
    accurately but not always literally, and a re-wrapped or lightly shortened
    quote of a genuine task was thrown away as a hallucination. Recall matters
    here because the missing list is the only thing that can block.

    Containment of the CLAIM in a task, not the other way round and not Jaccard:
    a short quote of a long bullet must verify (that is the honest, common case),
    while a claim mostly made of words no task uses must not. Anti-hallucination
    survives intact -- the claim still has to be built out of a real task line,
    so an invented task and a quoted DECISION both fail.
    """
    toks = set(_norm(claim).split())
    if len(toks) < MIN_MATCH_TOKENS:
        return False
    return any(t and len(toks & t) / len(toks) >= TASK_MATCH for t in task_tokens)


def plan_tasks(text):
    """The plan's discrete tasks, as a de-duplicated list of strings.

    A checkbox line is a task WHEREVER it appears: the author wrote a box, which
    is as explicit as a plan gets. A plain bullet counts only under an
    action-shaped heading, for the reason on ACTION_HEADING_RE.
    """
    tasks, seen, fenced, action = [], set(), False, False
    for raw in (text or "").splitlines():
        if FENCE_RE.match(raw):
            fenced = not fenced
            continue
        if fenced:
            continue
        h = HEADING_RE.match(raw)
        if h:
            action = is_action_heading(h.group(2))
            continue
        cb = CHECKBOX_RE.match(raw)
        body = None
        if cb:
            body = cb.group("body")
        else:
            b = BULLET_RE.match(raw)
            if b and action:
                body = b.group("body")
        if not body:
            continue
        body = re.sub(r"[*_`]+", "", body).strip()
        key = _norm(body)[:120]
        if len(key) < 8 or key in seen:
            continue
        seen.add(key)
        tasks.append(body[:300])
    return tasks


# ---- Tier 1: the shape of this session's items ------------------------------

LABEL_WORDS = r"(?:waves?|phases?|rounds?|steps?|stages?|parts?|milestones?|batch(?:es)?)"
# "Waves B-D", "phases 1 through 3", "steps 2 and 3": one item, several units.
UMBRELLA_RANGE_RE = re.compile(
    r"\b%s\s+[A-Za-z0-9]+\s*(?:-|--|to|through|,|&|and|\+|/)\s*[A-Za-z0-9]+\b" % LABEL_WORDS,
    re.IGNORECASE,
)
UMBRELLA_WORD_RE = re.compile(r"\b%s\b" % LABEL_WORDS, re.IGNORECASE)
# Same shape the tick-evidence gate accepts. An item carrying a file:line is
# pointed at something concrete, which is the opposite of an umbrella.
CITATION_RE = re.compile(r"[\w./-]+\.[A-Za-z]{1,5}:\d+")
UMBRELLA_MAX_WORDS = int(os.environ.get("WORKLIST_PLANFID_UMBRELLA_WORDS", "8"))


def is_umbrella(text):
    """A container label masquerading as a task.

    Two shapes, both taken from the incident. A RANGE names several units in one
    item and is an umbrella at any length ("www round 4 Waves B-D"). A BARE label
    is an umbrella only when the item is short and cites nothing, so that
    "r4-A-V verify Wave A in-browser: header gutters equal at 1440, ..." -- a
    real task that happens to name its wave -- is not accused.
    """
    t = (text or "").strip()
    if not t:
        return False
    if UMBRELLA_RANGE_RE.search(t):
        return True
    if not UMBRELLA_WORD_RE.search(t):
        return False
    return len(t.split()) <= UMBRELLA_MAX_WORDS and not CITATION_RE.search(t)


MIN_TASKS = int(os.environ.get("WORKLIST_PLANFID_MIN_TASKS", "6"))
SHORTFALL_RATIO = float(os.environ.get("WORKLIST_PLANFID_RATIO", "0.6"))


def prefilter(tasks, mine):
    """[(signal, detail)] for every Tier-1 signal that fires.

    `mine` is [(id, state, text)] for every item this session owns, in ANY state.
    Tracked items are counted across all states on purpose: fidelity is about
    what was WRITTEN DOWN, not about what is still open. Counting open items only
    would re-fire on a session that decomposed correctly and then ticked its way
    down to two, which is the false positive that would teach people to route
    around this.
    """
    hits = []
    if not tasks:
        return hits
    if len(tasks) >= MIN_TASKS:
        floor = math.ceil(len(tasks) * SHORTFALL_RATIO)
        if len(mine) < floor:
            hits.append(
                (
                    "shortfall",
                    "%d tracked item(s) against %d plan task(s); floor is %d"
                    % (len(mine), len(tasks), floor),
                )
            )
    umb = [i for i, st, t in mine if st == " " and is_umbrella(t)]
    if umb:
        hits.append(("umbrella", "open item(s) shaped like a container label: %s" % ", ".join(umb)))
    return hits


# ---- Tier 2 bookkeeping ------------------------------------------------------


def plan_sig(plan_path, plan_text):
    """Identity of the QUESTION: this plan, at this content.

    Deliberately NOT a function of the item set. Keying on the items would make
    every added item a new question and re-pay the model call all the way through
    a correct decomposition; keying on the plan means a settled verdict stands
    until the plan itself changes, and a re-approved plan is asked again.
    """
    h = hashlib.sha1()
    h.update((plan_path or "").encode("utf-8", "replace"))
    h.update(b"\x00")
    h.update((plan_text or "").encode("utf-8", "replace"))
    return h.hexdigest()[:12]


def state_path(worklist, session_id):
    return pathlib.Path(str(worklist) + ".planfid-%s.json" % (session_id or "unknown")[:8])


def load_state(path):
    """(state, forgot). Corrupt state is DISCARDED WHOLE, never salvaged field by
    field, for the reason wl_reggate.load_reggate gives: a half-parsed file
    silently resurrects an unanswered question as settled."""
    default = {"scanned": 0, "plan": "", "settled": {}}
    if not path.exists():
        return default, False
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        ok = (
            isinstance(d, dict)
            and isinstance(d.get("scanned"), int)
            and isinstance(d.get("plan"), str)
            and isinstance(d.get("settled"), dict)
            and all(isinstance(v, dict) for v in d["settled"].values())
        )
    except (OSError, ValueError):
        ok, d = False, None
    if not ok:
        return default, True
    return d, False


def save_state(path, state):
    # Whole-file rewrite, correct here for the same reason as the reggate marker:
    # the file is per-session, so there is no second writer to race.
    with contextlib.suppress(OSError):
        path.write_text(json.dumps(state, indent=1), encoding="utf-8")


def is_settled(state, sig, n_items):
    """Has this plan's question already been answered, for this many items?

    `faithful` and `deferred` settle for good: the plan was judged sound, or the
    operator owns the call, and only editing the plan reopens either.

    `unevidenced` settles CONDITIONALLY, and the condition is the hole it closes.
    Banking it unconditionally was the first design and it is a real blind spot:
    the first stop after an approval can legitimately find a session that has not
    written its items yet, the model has nothing concrete to point at, and a
    permanent bank would then silence the check for that plan forever -- so the
    two umbrella items written five minutes later would never be seen. Recording
    the item count instead means the question reopens the moment the worklist
    grows, which is exactly when a new answer is available. It still cannot loop:
    a session that adds nothing is never re-asked.
    """
    rec = (state.get("settled") or {}).get(sig)
    if not isinstance(rec, dict):
        return False
    if rec.get("verdict") != "unevidenced":
        return True
    try:
        return n_items <= int(rec.get("items", 0))
    except (TypeError, ValueError):
        return False


REQUIRED = ("faithful", "umbrella_ids", "missing", "instruction")
SETTLE_VERDICTS = ("faithful", "deferred", "unevidenced")


def apply_planfid_verdict(pf, plan_text, mine, sig, lines, me8, item_re):
    """('malformed'|'settle'|'block', payload, detail).

    Deterministic mapping from the judge's plan_fidelity object to an action,
    with EVERY model claim verified against artifacts first:

      faithful true                     -> settle 'faithful'
      a `- [?]` carrying planfid:<sig>  -> settle 'deferred'
      umbrella_ids that are not real
        OPEN items of this session      -> dropped as hallucinated
      missing entries not built out of
        a real TASK LINE of the plan    -> dropped as hallucinated
      no missing entry survives         -> settle 'unevidenced', whatever the
                                           umbrella claims say. See below: the
                                           block needs the checkable half.
      otherwise                         -> block, naming the three exits.

    `item_re` is injected (wl_core.ITEM) so this module stays importable without
    dragging the store in, which is what keeps --selftest hermetic.
    """
    if not isinstance(pf, dict) or any(k not in pf for k in REQUIRED):
        missing = [k for k in REQUIRED if not isinstance(pf, dict) or k not in pf]
        return "malformed", "plan_fidelity missing %s" % (missing or "everything"), ""
    if pf.get("faithful") is True:
        return "settle", "faithful", str(pf.get("instruction", ""))[:160]
    token = "planfid:%s" % sig[:8]
    for ln in lines:
        m = item_re.match(ln)
        if m and m.group("state") == "?" and token in ln:
            return "settle", "deferred", token

    open_ids = {i for i, st, _t in mine if st == " "}
    by_id = {i: t for i, _st, t in mine}
    raw_umb = pf.get("umbrella_ids")
    umb = [str(x) for x in raw_umb if str(x) in open_ids] if isinstance(raw_umb, list) else []
    # A missing entry must match a line THE TASK PARSER CALLS A TASK, not merely
    # appear somewhere in the plan.
    #
    # MEASURED, and it is why this is not the looser check it started as. The
    # first version verified `n in _norm(plan_text)`, and the corpus run put a
    # FALSE POSITIVE on the board twice out of two: given the operator's own
    # corrected decomposition, haiku answered "unfaithful" and quoted DECISION
    # bullets ("Stat callouts KEEP their number and claim in place") as untracked
    # tasks. They are verbatim in the plan, so the loose check passed them, and
    # the session that had just done exactly the right thing would have been
    # walled in. Matching against plan_tasks() closes it deterministically: the
    # same parser that decides whether to spend a call decides what counts as
    # evidence, so context and locked decisions cannot be cited as work.
    task_tokens = [set(_norm(t).split()) for t in plan_tasks(plan_text)]
    raw_missing = pf.get("missing")
    miss = []
    if isinstance(raw_missing, list):
        miss = [str(x) for x in raw_missing if matches_a_task(str(x), task_tokens)]
    if not miss:
        # AN UMBRELLA CLAIM ALONE DOES NOT BLOCK, and this is deliberate. "This
        # item is a container label" is a judgement; "this plan task is tracked
        # by nothing" is checkable, and it is also the actionable half -- the
        # remedy is to add the missing items. Requiring the checkable half means
        # a session whose every plan task IS tracked somewhere is never blocked
        # over the wording of an item, which is the false positive that would
        # teach people to route around this. Umbrella ids still ride the message,
        # because naming the item that swallowed the work is what makes the
        # instruction concrete.
        return (
            "settle",
            "unevidenced",
            "judge said unfaithful but named no plan TASK that nothing tracks "
            "(%d umbrella id(s) survived verification)" % len(umb),
        )
    detail = "%d umbrella item(s), %d untracked plan task(s)" % (len(umb), len(miss))
    payload = {
        "umbrella": [(i, by_id.get(i, "")[:160]) for i in umb[:8]],
        "missing": [m[:200] for m in miss[:12]],
        "instruction": str(pf.get("instruction", ""))[:300],
        "token": token,
        "me8": me8,
    }
    return "block", payload, detail


def render_items(mine, cap=40):
    """The item list exactly as the judge will see it: id, state, text."""
    rows = []
    for iid, state, text in mine[:cap]:
        rows.append("  [%s] #%s %s" % (state, iid, (text or "").strip()[:220]))
    if len(mine) > cap:
        rows.append("  (... %d more)" % (len(mine) - cap))
    return "\n".join(rows) or "  (this session tracks no items at all)"


# ---- Controls ----------------------------------------------------------------

# The real incident, quoted from ~/.claude/plans/memoized-gliding-kay.md and from
# the worklist as it stood before the operator caught it. Trimmed to the sections
# that decide the verdict; the wording is verbatim.
REAL_PLAN = """# www round 4: the page frame, the voice, and a docs surface people can browse

## Context

Round 3 shipped (docs columns, header cluster, video language picker, inline citations)
and is on PR #569. This round is the operator's next pass.

## Decisions, locked by the operator (do not relitigate)

- **D1** One continuous black zone at the page bottom: final CTA and footer together.
- **D2** "Get the technical brief" and "Short on time?" share one row, two columns.
- **D3** Stat callouts KEEP their number and claim in place. Only the SOURCES move.
- **D4** Voice becomes imperative / impersonal, website only, docs excluded.

## Waves

### Wave A: the page frame (D1, D6, D7, and item c)

- `.nav-container` gains a 1280px max-width and 80px gutters. Keep the round-3 explicit
  grid placement; only the container changes.
- `Footer.tsx` background goes black, full bleed, its inner container matching the
  header's 1280px.
- Both menus rebuilt on `popover="auto"`, deleting the hover-timeout, click-outside and
  keydown machinery from `PersonaMegaMenu.tsx`.
- One `::backdrop` rule dims the page behind the constellation popup AND both menus.

### Wave B: the solution-page bottom (D2, D3)

- Move the two download sections adjacent to each other and pair them in one two-column
  row.
- The row must degrade to ONE column when the gated button is absent.
- New `SPSources` component: native `<details>`, rendering `references.items[]` as a
  numbered list.
- Callouts lose only their `source` line.

### Wave C: the voice (D4)

- English-only rewrite of second person to imperative across `pages.solutionPages`.
- Then `npm run i18n:generate-hashes` and re-naturalize only the delta on haiku.

### Wave D: the docs browse surface (D5)

1. Browse route replacing the `/[lang]/docs` redirect, listing all docs as cards.
2. `tags` added to the content-collection schema as an English-vocabulary enum array.
3. Filter panel with two axes (category, tags) plus the existing search.
4. SVG thumbnails, simple and consistent, generated rather than hand-drawn.
5. Retitle 79 docs to `X: Y`. Do this LAST: it invalidates the translation hashes.
"""

# What the session actually tracked. Two items for the whole plan.
INCIDENT_ITEMS = [
    ("aaaa1111", " ", "www round 4 Wave A"),
    ("bbbb2222", " ", "www round 4 Waves B-D"),
]

# What it tracked after the operator's correction, trimmed to the same shape the
# live store holds. This is the NEGATIVE control: same plan, faithful items.
DECOMPOSED_ITEMS = [
    ("97e5b05d", " ", "r4-A3 menus: rebuild PersonaMegaMenu.tsx (312 lines, 11 hooks)"),
    ("c84a8a4b", " ", "r4-A4 menus: new Learn menu, flat list = 6 doc categories"),
    ("11110001", " ", "r4-A1 nav-container 1280px max-width + 80px gutters"),
    ("11110002", " ", "r4-A2 Footer.tsx black + full bleed, one band with sp-bottom-cta"),
    ("11110003", " ", "r4-A5 one ::backdrop rule dims constellation popup and both menus"),
    ("02eb5327", " ", "r4-B2 pair Get-the-technical-brief with Short-on-time in one row"),
    # ADDED after the first corpus run, and the model was RIGHT to complain. This
    # fixture is a trim of the live worklist and the trim dropped the item for
    # "The row must degrade to ONE column when the gated button is absent", which
    # is its own plan task. The check called the gap and the fixture, not the
    # check, was wrong. A negative control that is not actually faithful measures
    # nothing.
    ("11110004", " ", "r4-B2b the row degrades to ONE column when the gated button is absent"),
    ("101b59c3", " ", "r4-B1 reorder the download sections in SolutionPage.astro:96"),
    ("d6b6214c", " ", "r4-B3 new SPSources component: native <details>, zero JS"),
    ("09822472", " ", "r4-B4 stat callouts keep number+claim, lose the source line"),
    ("c540762c", " ", "r4-C1 voice: rewrite English second person to imperative"),
    ("4659c319", " ", "r4-C2 voice cascade: i18n:generate-hashes then naturalize-status"),
    ("e3d2008d", " ", "r4-D1 docs: browse route replacing the /[lang]/docs 301"),
    ("19b59014", " ", "r4-D2 docs: add tags to the content-collection schema"),
    ("e5002325", " ", "r4-D3 docs: filter panel, two axes plus existing search"),
    ("c1cc3bdc", " ", "r4-D4 docs: SVG thumbnails, one generated template"),
    ("0fff9f36", " ", "r4-D5 docs: retitle 79 docs to the X: Y form, LAST"),
    ("2b2d39bd", " ", "r4-A-V verify Wave A in-browser at 1440: gutters, band, backdrop"),
    ("6ece336e", " ", "r4-B-V verify Wave B: no source line, disclosure closed on load"),
]

# The model half. Cannot be stubbed: a stub that answers "unfaithful" proves
# nothing about whether the classifier can tell the incident from its own fix.
# Run with --corpus, never on the per-stop path.
CORPUS = [
    ("REAL incident: two umbrella items for four waves", True, REAL_PLAN, INCIDENT_ITEMS),
    ("REAL correction: the same plan, decomposed", False, REAL_PLAN, DECOMPOSED_ITEMS),
    (
        "SYNTHETIC prose-umbrella (no wave word, still one item for four tasks)",
        True,
        REAL_PLAN,
        [
            ("cccc3333", " ", "implement the page frame work end to end"),
            ("dddd4444", " ", "then do the solution-page bottom, the voice and the docs surface"),
        ],
    ),
]


# Measured, not guessed. Two corpus runs on 2026-08-19 disagreed with themselves
# on the same prompt: the incident case came back 2/2 in one run and 1/2 in the
# next. The instability is confined to RECALL, which is the tolerable direction
# here -- a missed umbrella costs one undetected papering-over, while a false
# positive walls in a session that did the right thing and teaches everyone to
# route around the check. So the gate is asymmetric: any FP fails outright,
# recall is a rate with a floor. Raise the floor with a measurement, never on a
# hunch.
RECALL_FLOOR = float(os.environ.get("WORKLIST_PLANFID_RECALL_FLOOR", "0.6"))


def _corpus_selftest(repeat=2):
    """Run the REAL model over CORPUS `repeat` times and report per-case stability.

    WHY REPEAT DEFAULTS ABOVE ONE, same lesson wl_admit records: one run cannot
    tell a prompt improvement from noise, and a tuning session that believes it
    can will chase variance and ship a regression convinced it fixed something.
    """
    stats = {c[0]: {"right": 0, "wrong": 0, "err": 0, "expect": c[1]} for c in CORPUS}
    for _r in range(max(1, repeat)):
        for label, expect, plan, items in CORPUS:
            pf, err = wl_judge.run_planfid(plan, render_items(items), "(no message)")
            if err:
                stats[label]["err"] += 1
                continue
            kind, _payload, _detail = apply_planfid_verdict(
                pf, plan, items, "0" * 12, [], "test1234", re.compile(r"^(?P<state>x)$")
            )
            got = kind == "block"
            stats[label]["right" if got == expect else "wrong"] += 1
    fp = fn = errors = 0
    for label, st in stats.items():
        n = st["right"] + st["wrong"]
        errors += st["err"]
        if st["wrong"]:
            if st["expect"]:
                fn += st["wrong"]
            else:
                fp += st["wrong"]
        print(
            "  %-58s %d/%d  %s"
            % (label[:58], st["right"], n, "ok" if not st["wrong"] else "MISSED")
        )
    pos = [st for st in stats.values() if st["expect"]]
    recall = sum(st["right"] for st in pos) / max(1, sum(st["right"] + st["wrong"] for st in pos))
    print(
        "\n  rounds=%d  FP=%d  FN=%d  errors=%d  recall=%.2f"
        % (max(1, repeat), fp, fn, errors, recall)
    )
    ok = fp == 0 and errors == 0 and recall >= RECALL_FLOOR
    if not ok:
        print(
            "  FAIL: %s"
            % (
                "false positive(s)"
                if fp
                else "judge errors"
                if errors
                else "recall below floor %.2f" % RECALL_FLOOR
            )
        )
    return 0 if ok else 1


def _fake_transcript(path, records):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r) + "\n" for r in records)


def _selftest():
    """Controls. Run: wl_planfid.py --selftest

    The DETERMINISTIC half: plan discovery from a transcript, task counting, both
    prefilter signals in BOTH directions on the REAL before/after item sets, and
    the verification that stands between a model claim and a block. The other
    half -- whether haiku can separate the incident from its own correction --
    cannot be stubbed and lives behind --corpus, because a stub that answers
    "unfaithful" proves nothing.
    """
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        if not cond:
            ok = False
        print(
            "  %s  %s%s" % ("PASS" if cond else "FAIL", label, "" if cond else "  <- %s" % detail)
        )

    # ---- plan task extraction, on the real plan ----
    tasks = plan_tasks(REAL_PLAN)
    check("the real plan yields tasks", len(tasks) >= 10, "%d" % len(tasks))
    check(
        "the D1-D4 decision bullets are NOT counted as tasks",
        not any("One continuous black zone" in t for t in tasks),
        "; ".join(t[:40] for t in tasks[:4]),
    )
    check(
        "Wave D's numbered items ARE counted",
        any("rowse route" in t for t in tasks),
        "; ".join(t[:30] for t in tasks),
    )
    check(
        "a fenced code block contributes nothing",
        plan_tasks("## Steps\n\n```\n- rm -rf /\n- drop database\n```\n") == [],
    )
    check(
        "a checkbox is a task under ANY heading",
        len(plan_tasks("## Context\n\n- [ ] a task written as a checkbox item here\n")) == 1,
    )
    check(
        "a heading LEADING with a work word is an action heading",
        all(
            is_action_heading(h)
            for h in ("Waves", "Wave A: the page frame", "Implementation steps")
        ),
    )
    check(
        "a sentence-shaped heading that merely CONTAINS one is not",
        not any(
            is_action_heading(h)
            for h in (
                "Verified facts the plan depends on",
                "Out of scope",
                "Context",
                "Decisions, locked by the operator",
                "Verification",
            )
        ),
    )
    check(
        "background FACTS are not quotable as tasks",
        not any(
            "footer is site-wide" in t.lower()
            for t in plan_tasks(
                REAL_PLAN
                + "\n## Verified facts the plan depends on\n\n- The footer is site-wide and lands on docs pages.\n"
            )
        ),
    )
    check(
        "a nested sub-bullet is detail, not a peer task",
        len(plan_tasks("## Steps\n\n- the parent task line\n      - a nested detail line\n")) == 1,
    )

    # ---- the claim matcher, directly. It is the ONLY thing standing between a
    # model sentence and a block, so it gets its own controls rather than being
    # exercised only through apply_planfid_verdict.
    tt = [set(_norm(t).split()) for t in plan_tasks(REAL_PLAN)]
    check("an exact task line matches", matches_a_task("Callouts lose only their source line.", tt))
    check(
        "a truncated quote of a task matches",
        matches_a_task("New SPSources component: native details", tt),
    )
    check(
        "a locked DECISION bullet does not match any task",
        not matches_a_task(
            "Stat callouts KEEP their number and claim in place. Only the SOURCES move.", tt
        ),
    )
    check("an invented task does not match", not matches_a_task("rewrite the kernel in rust", tt))
    check("a two-word claim is too thin to match", not matches_a_task("the row", tt))

    # ---- umbrella shape, both directions, on the real strings ----
    check("the incident's Wave A item is an umbrella", is_umbrella("www round 4 Wave A"))
    check("the incident's Waves B-D item is an umbrella", is_umbrella("www round 4 Waves B-D"))
    check(
        "a real task that merely NAMES its wave is not accused",
        not is_umbrella(
            "r4-A-V verify Wave A in-browser: header gutters equal at 1440, CTA and footer "
            "one black band with no seam, docs and legal pages still deliberate"
        ),
    )
    check(
        "a cited short item is not accused",
        not is_umbrella("wave A: SolutionPage.astro:96 two-column row"),
    )
    check("an ordinary item is not accused", not is_umbrella("rebuild PersonaMegaMenu.tsx"))

    # ---- THE TWO-DIRECTION CONTROL, on the real before/after item sets ----
    fired = prefilter(tasks, INCIDENT_ITEMS)
    check("PREFILTER FIRES on the real incident", bool(fired), repr(fired))
    check(
        "it fires on BOTH signals (shortfall and umbrella)",
        {k for k, _d in fired} == {"shortfall", "umbrella"},
        repr(fired),
    )
    quiet = prefilter(tasks, DECOMPOSED_ITEMS)
    check("PREFILTER IS SILENT on the operator's own correction", not quiet, repr(quiet))
    check("no plan means no signal at all", prefilter([], INCIDENT_ITEMS) == [])
    check(
        "a plan below the task floor is never policed by shortfall",
        "shortfall" not in {k for k, _d in prefilter(tasks[:4], [("a1", " ", "one item")])},
    )
    # THE INSTRUMENT BLIND. The umbrella signal must read STATE, not only text:
    # the same two strings, already ticked, are history rather than live cover.
    ticked = [(i, "x", t) for i, _s, t in INCIDENT_ITEMS]
    check(
        "an already-TICKED umbrella does not fire the umbrella signal",
        "umbrella" not in {k for k, _d in prefilter(tasks, ticked)},
    )

    # ---- plan discovery from a transcript ----
    with tempfile.TemporaryDirectory() as td:
        tp = os.path.join(td, "t.jsonl")
        plan = os.path.join(td, "p.md")
        pathlib.Path(plan).write_text(REAL_PLAN, encoding="utf-8")
        _fake_transcript(
            tp,
            [
                {"type": "attachment", "attachment": {"type": "plan_mode", "planFilePath": plan}},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}},
            ],
        )
        got, _n = scan_plan_exit(tp)
        check("plan_mode alone (entered, not approved) yields no plan", got == "", got)
        _fake_transcript(
            tp,
            [
                {"type": "attachment", "attachment": {"type": "plan_mode", "planFilePath": plan}},
                {
                    "type": "attachment",
                    "isSidechain": False,
                    "attachment": {
                        "type": "plan_mode_exit",
                        "planFilePath": plan,
                        "planExists": True,
                    },
                },
            ],
        )
        got, scanned = scan_plan_exit(tp)
        check("an APPROVED plan is discovered from the transcript", got == plan, got)
        check(
            "the scan reports the whole file as consumed", scanned == os.path.getsize(tp), scanned
        )
        check("the discovered plan reads back", len(read_plan(got)) > MIN_PLAN_CHARS)
        # Incremental: re-scanning from the recorded offset finds nothing new,
        # which is what makes the per-stop cost the DELTA and not the file.
        got2, _ = scan_plan_exit(tp, start=scanned)
        check("re-scanning from the banked offset costs nothing and finds nothing", got2 == "")
        # planExists false is not an approval we can act on.
        _fake_transcript(
            tp,
            [
                {
                    "type": "attachment",
                    "attachment": {
                        "type": "plan_mode_exit",
                        "planFilePath": plan,
                        "planExists": False,
                    },
                }
            ],
        )
        got, _ = scan_plan_exit(tp)
        check("planExists=false is not treated as an approval", got == "", got)
        # A sub-agent's plan is not the session's.
        _fake_transcript(
            tp,
            [
                {
                    "type": "attachment",
                    "isSidechain": True,
                    "attachment": {
                        "type": "plan_mode_exit",
                        "planFilePath": plan,
                        "planExists": True,
                    },
                }
            ],
        )
        got, _ = scan_plan_exit(tp)
        check("a sidechain (sub-agent) plan approval is ignored", got == "", got)
        check(
            "a missing transcript is silent, not an error",
            scan_plan_exit(os.path.join(td, "no")) == ("", 0),
        )
        check(
            "a stub plan file is not judged",
            read_plan(os.path.join(td, "p.md")) != "" and read_plan(tp) == "",
        )

        # ---- state round-trip and corrupt discard ----
        wl = pathlib.Path(td) / "w.jsonl"
        sp = state_path(wl, "abcdefgh")
        sp.write_text("{not json", encoding="utf-8")
        st, forgot = load_state(sp)
        check("corrupt state is discarded whole, not salvaged", st["settled"] == {} and forgot)
        st["settled"]["deadbeefcafe"] = {"verdict": "faithful", "at": "now"}
        st["scanned"] = 1234
        save_state(sp, st)
        st2, forgot2 = load_state(sp)
        check(
            "a settled verdict and the scan offset round-trip",
            st2["settled"].get("deadbeefcafe", {}).get("verdict") == "faithful"
            and st2["scanned"] == 1234
            and not forgot2,
        )

        # SETTLED LIFETIME. faithful and deferred are permanent; unevidenced
        # expires the moment the worklist grows, which is the hole a permanent
        # bank would leave open (see is_settled).
        perm = {"settled": {"s1": {"verdict": "faithful"}}}
        check("a faithful verdict stays settled at any item count", is_settled(perm, "s1", 99))
        cond = {"settled": {"s2": {"verdict": "unevidenced", "items": 2}}}
        check(
            "an unevidenced verdict holds while the worklist is unchanged",
            is_settled(cond, "s2", 2),
        )
        check("an unevidenced verdict REOPENS once an item is added", not is_settled(cond, "s2", 3))
        check("an unknown plan is never settled", not is_settled(perm, "nope", 0))
        check(
            "a malformed settled record is not settled",
            not is_settled({"settled": {"s3": "x"}}, "s3", 0),
        )

    # ---- the verification between a model claim and a block ----
    item_re = re.compile(r"^\s*-\s*\[(?P<state>[ x?>])\]\s*(?:\((?P<owner>[^)]*)\)\s*)?")
    sig = plan_sig("/p.md", REAL_PLAN)
    good = {
        "faithful": False,
        "umbrella_ids": ["aaaa1111", "bbbb2222"],
        "missing": ["New `SPSources` component: native `<details>`"],
        "instruction": "split the two items into one item per plan task",
    }
    kind, payload, detail = apply_planfid_verdict(
        good, REAL_PLAN, INCIDENT_ITEMS, sig, [], "e6500e92", item_re
    )
    check("a verified unfaithful verdict BLOCKS", kind == "block", "%s %s" % (kind, detail))
    check(
        "the block names the real umbrella items", kind == "block" and len(payload["umbrella"]) == 2
    )
    check("the block quotes the untracked plan task", kind == "block" and payload["missing"])
    check(
        "the block carries a deferral token",
        kind == "block" and payload["token"].startswith("planfid:"),
    )

    k, _p, d = apply_planfid_verdict(
        {**good, "faithful": True}, REAL_PLAN, INCIDENT_ITEMS, sig, [], "e6500e92", item_re
    )
    check("faithful=true settles and never blocks", (k, _p) == ("settle", "faithful"), d)

    # Anti-hallucination, both axes. Each alone must be able to stop a block.
    k, _p, d = apply_planfid_verdict(
        {**good, "umbrella_ids": ["9999zzzz"], "missing": []},
        REAL_PLAN,
        INCIDENT_ITEMS,
        sig,
        [],
        "e6500e92",
        item_re,
    )
    check(
        "an invented item id cannot manufacture a block", k == "settle" and _p == "unevidenced", d
    )
    k, _p, d = apply_planfid_verdict(
        {**good, "umbrella_ids": [], "missing": ["rewrite the kernel scheduler in rust"]},
        REAL_PLAN,
        INCIDENT_ITEMS,
        sig,
        [],
        "e6500e92",
        item_re,
    )
    check(
        "a plan task absent from the plan cannot manufacture a block",
        k == "settle" and _p == "unevidenced",
        d,
    )
    # THE MEASURED FALSE POSITIVE, pinned. On the corpus run of 2026-08-19 haiku
    # answered "unfaithful" about the operator's own corrected decomposition and
    # quoted a locked DECISION bullet as an untracked task. It is verbatim in the
    # plan, so the first version of this verification passed it and blocked a
    # session that had done exactly the right thing.
    k, _p, d = apply_planfid_verdict(
        {
            **good,
            "umbrella_ids": [],
            "missing": ["Stat callouts KEEP their number and claim in place"],
        },
        REAL_PLAN,
        INCIDENT_ITEMS,
        sig,
        [],
        "e6500e92",
        item_re,
    )
    check("a DECISION bullet quoted as a task is not evidence", k == "settle", "%s %s" % (k, d))
    check(
        "an umbrella claim ALONE never blocks (the checkable half is required)",
        apply_planfid_verdict(
            {**good, "missing": []}, REAL_PLAN, INCIDENT_ITEMS, sig, [], "e6500e92", item_re
        )[0]
        == "settle",
    )
    k, _p, _d = apply_planfid_verdict(
        {**good, "umbrella_ids": [], "missing": ["Callouts lose only their `source` line."]},
        REAL_PLAN,
        INCIDENT_ITEMS,
        sig,
        [],
        "e6500e92",
        item_re,
    )
    check("a VERBATIM plan task alone is enough evidence to block", k == "block", k)
    # A TICKED umbrella id is not open cover, so it is not evidence either.
    k, _p, _d = apply_planfid_verdict(
        {**good, "missing": []},
        REAL_PLAN,
        [(i, "x", t) for i, _s, t in INCIDENT_ITEMS],
        sig,
        [],
        "e6500e92",
        item_re,
    )
    check("a ticked item cannot be cited as live umbrella cover", k == "settle", k)

    # The deferral exit, and it must be OWNED and carry the right token.
    defer_line = (
        "- [?] (e6500e92) planfid:%s is this plan superseded? DEFAULT: decompose it" % sig[:8]
    )
    k, _p, d = apply_planfid_verdict(
        good, REAL_PLAN, INCIDENT_ITEMS, sig, [defer_line], "e6500e92", item_re
    )
    check("a `- [?]` carrying the planfid token settles it", (k, _p) == ("settle", "deferred"), d)
    k, _p, _d = apply_planfid_verdict(
        good,
        REAL_PLAN,
        INCIDENT_ITEMS,
        sig,
        [defer_line.replace("[?]", "[ ]")],
        "e6500e92",
        item_re,
    )
    check("an OPEN item carrying the token does not settle it", k == "block", k)

    # Malformed is reported and never blocks.
    k, p, _d = apply_planfid_verdict(
        {k2: v for k2, v in good.items() if k2 != "missing"},
        REAL_PLAN,
        INCIDENT_ITEMS,
        sig,
        [],
        "e6500e92",
        item_re,
    )
    check("a malformed verdict is reported, not silently dropped", k == "malformed", p)
    check("malformed names the missing field", "missing" in p, p)
    k, p, _d = apply_planfid_verdict(None, REAL_PLAN, INCIDENT_ITEMS, sig, [], "e6500e92", item_re)
    check("a null verdict is malformed, not a block", k == "malformed", p)

    # The signature is a function of the PLAN, never of the items.
    check(
        "the same plan yields the same signature whatever the items are",
        plan_sig("/p.md", REAL_PLAN) == plan_sig("/p.md", REAL_PLAN),
    )
    check(
        "an edited plan reopens the question",
        plan_sig("/p.md", REAL_PLAN) != plan_sig("/p.md", REAL_PLAN + "\n- one more task line\n"),
    )

    check(
        "the rendered item list carries ids and states", "#aaaa1111" in render_items(INCIDENT_ITEMS)
    )
    check(
        "an empty item list still renders something readable", "tracks no items" in render_items([])
    )

    print("  %s" % ("all planfid controls passed" if ok else "*** FAILURES ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--corpus" in sys.argv:
        # Real model calls. A gate, run when this module or PLANFID_PROMPT
        # changes, never on the per-stop path.
        sys.exit(_corpus_selftest())
    sys.exit(_selftest() if "--selftest" in sys.argv else 0)
