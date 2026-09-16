"""Refuse an AskUserQuestion whose answer CLAUDE.md already gives.

THE PROBLEM, in the operator's words: "I don't know why you ask this question
on each new session. It seems that my CLAUDE.md doesn't override you on each
new session. See the big-bang statements there. Find a way to go for big-bang
on each session."

They are right that the document is not enough. Anthropic's own guidance says
so: "CLAUDE.md content is delivered as a user message after the system prompt,
not as part of the system prompt itself... there's no guarantee of strict
compliance", and "If the instruction is something that must run at a specific
point... write it as a hook instead. Hooks execute as shell commands at fixed
lifecycle events and apply regardless of what Claude decides to do."
So this is a hook.

WHAT IT REFUSES, and nothing more: a PERMISSION-SEEKING question about
committing, branching, pushing, opening a PR or merging. CLAUDE.md settles
those twice over -- "the default deliverable is an uncommitted working tree"
and "ask for the big-bang, not for permission to patch one thing" -- so asking
costs the operator a round trip to repeat a rule they already wrote down.

THE MATCH IS NARROW ON PURPOSE, and the narrowness is the whole design. A hook
that swallows legitimate questions is worse than the nagging it replaces,
because the operator never learns what was suppressed. Two independent
conditions must BOTH hold:

  1. a permission-seeking shape  (should I / shall I / do you want / may I /
     would you like / is it ok / can I / want me to)
  2. a git-workflow object       (commit / branch / push / PR / merge)

So "Should I commit this?" is refused, while "Which branch strategy fits this
repo?" and "Did the rebase drop a commit?" pass untouched: they are questions
about DESIGN and FACT, not requests for permission this repo already granted.

This is the same over-matching lesson wl_agents.py paid for four separate
times in one session, where ordinary English words like `while`, `see`, `step`
and `stop` were scoring as domain terms. Anchor on intent, not vocabulary.

WHAT A REFUSAL LEAVES BEHIND. Every refusal below appends one line to a
ledger beside the worklist state (see LEDGER). Before that it left NO TRACE
ANYWHERE, and `.claude/hooks/test-hooks.sh` says exactly why that matters:
"a false positive is invisible by construction: the operator never learns
what was not asked". A narrow matcher is only trustworthy if its misses are
countable, so the denominator has to exist on disk.

PORT NOTE ON `join(" ")`. The other four payload collectors in this chain join
with a NEWLINE; this one joins with a SPACE, and the difference is load-bearing
rather than cosmetic. Every regex below is unanchored and grep matches per
RECORD, so a newline join would put the permission phrase and the object in
different records and the two-condition test could never fire on a question
whose header carried one of them. `hookio.texts` is therefore not used here;
`_jq_collect` is called directly and joined the way the original does.

PORT NOTE ON `tr '[:upper:]' '[:lower:]'`. Under `LC_ALL=C` that maps the 26
ASCII letters and nothing else. Python's `str.lower()` also folds every
non-ASCII uppercase codepoint, which would make a question containing, say, a
Turkish dotted capital lowercase differently on the two sides. The translation
table below is ASCII-only, deliberately.

PORT NOTE ON THE LEDGER'S SIDE EFFECT. This is the only guard in the chain that
WRITES something, and the port keeps it: the differential compares (rc, stdout,
stderr) and would pass either way, so dropping the append would be an invisible
behaviour change -- exactly the class the "no trace anywhere" paragraph above is
about. `jq -n -c` emits compact JSON with the keys in the order given, which is
`json.dumps(..., separators=(",", ":"))` over a dict built in that same order.
"""

import datetime
import json

from rediacc_hooks import hookio

CHAIN = "pre-ask"
TWIN = "pre-ask/block-settled-questions.sh"
ORDER = 3

# The clause anchor. Without it a sentence ABOUT the rule is refused as if it
# were the rule being broken -- "Should I explain in the report why we never
# commit unasked?" -- which is the mention-vs-target class reaching the pre-ask
# chain, where check_guard_mention_anchoring.py cannot see it because it globs
# pre-bash only.
DEFECT = (
    "if hookio.grep_q(CLAUSE, between):\n            return hookio.ALLOW",
    "if False:\n            return hookio.ALLOW",
)

PERMISSION = (
    r"(should|shall|may|can) (i|we)|do you want|would you like|want me to|"
    r"is it (ok|okay|fine)|are you happy for|should it be"
)
OBJECT = r"commit|branch|push|pull request|open a pr|[^a-z]pr[^a-z]|merge"

# ---- ANCHOR: the permission must GOVERN the object, not merely precede it ----
# Both regexes hit anywhere in the question, so a sentence ABOUT the rule was
# refused as if it were the rule being broken:
#
#   "Should I explain in the report why we never commit unasked?"
#    ^^^^^^^^ PERMISSION                        ^^^^^^ OBJECT   -> exit 2
#
# That is the mention-vs-target class -- the same one that hit four pre-bash
# guards on 2026-08-28 -- reaching the pre-ask chain, which
# check_guard_mention_anchoring.py does not probe (it globs pre-bash only).
#
# ANCHOR, DO NOT NARROW: the object list stays exactly as it was. What is added
# is that no CLAUSE BOUNDARY may sit between the permission and the object. A
# subordinating conjunction or a comma means the object belongs to a different
# clause, which is precisely what "a sentence about it" looks like. The direct
# forms this guard exists for have nothing between them: "should i commit",
# "shall i open a pr", "do you want me to create a branch".
CLAUSE = (
    r"(^|[^a-z])(why|whether|that|because|how|when|if|before|after|unless|since|instead)"
    r"([^a-z]|$)|,"
)

# `tr '[:upper:]' '[:lower:]'` under LC_ALL=C: the 26 ASCII letters, nothing
# else. See the port note in the module docstring.
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")

NO_JQ = (
    "block-settled-questions: jq not found; this question passed UNEXAMINED "
    "(the hook did not run its match)."
)

MESSAGE = """BLOCKED: CLAUDE.md already answers this, so asking spends a round trip repeating
a rule the operator has written down twice.

  Session default 1: "The default deliverable is an uncommitted working tree.
  Do not git commit, create a branch, push, or open a PR unless the operator
  asks for it in that task."

  Findings rule: "Ask for the big-bang, not for permission to patch one thing...
  put the whole cluster into a single plan and ask to run it."

Proceed with the documented default: leave the work uncommitted, and if a
decision genuinely needs the operator, park it as a worklist [?] carrying its
own DEFAULT rather than blocking the turn on a question.

If you are NOT asking for permission -- a design question that happens to
mention branching, or a factual question about a merge -- rephrase it as the
question it actually is, and this hook will pass it.
"""

EDGE_CASES = [
    # The two-condition shape this guard exists for.
    ("the direct permission question", "Should I commit this?"),
    ("shall I open a pr", "Shall I open a PR for this?"),
    ("do you want me to branch", "Do you want me to create a branch?"),
    ("may I push", "May I push these to origin?"),
    ("is it ok to merge", "Is it ok to merge this now?"),
    # Design and fact, which must pass untouched.
    ("a design question", "Which branch strategy fits this repo?"),
    ("a factual question", "Did the rebase drop a commit?"),
    # A permission shape with no git object at all.
    ("permission about something else", "Should I run the whole suite first?"),
    # The 2026-08-28 anchor, in the sentence that found it.
    (
        "a sentence about the rule",
        "Should I explain in the report why we never commit unasked?",
    ),
    ("a comma is a clause boundary too", "Should I, before the merge, run the suite?"),
    # The object sits BEFORE the permission phrase. Left refusing, deliberately.
    ("the object before the permission", "The commit is staged, should i proceed?"),
    # A payload shaped as the single-question form rather than the array.
    ("the singular question field", {"tool_input": {"question": "Should I push?"}}),
    ("no question at all", {"tool_input": {}}),
]


def _first_match(pattern, text):
    """`grep -oE "$P" | head -n1` in a `$( )`: the first match, or ""."""
    hits = hookio.grep_o(pattern, text)
    return hits[0] if hits else ""


def _ledger_path():
    """`python3 .../stop/worklist.py --path` plus the `.ask-refusals.jsonl` suffix.

    BEST EFFORT, ALWAYS. `worklist.py --path` is self-contained (it works with
    every sibling module broken -- see suite case 118), but if python3 is missing
    or the write fails, the refusal still happens. A ledger that could veto the
    gate would be a worse bug than no ledger.
    """
    wlpath = hookio.run_out(
        ["python3", "%s/.claude/hooks/stop/worklist.py" % hookio.repo_root(), "--path"]
    )
    return "%s.ask-refusals.jsonl" % wlpath if wlpath else ""


def _record(ev, question, perm_hit, obj_hit):
    """One line per refusal, appended BEFORE the message is printed.

    It carries the timestamp, the session, the question text this hook actually
    matched against (lowercased and joined, i.e. what the regexes saw rather
    than a reconstruction), and the two spans that matched -- so "which
    condition matched" is answerable from the file instead of by re-deriving it.

    It lives beside the worklist state (TMPDIR/claude-worklist/<slug>.md), NOT in
    the repo: it is per-machine session debris, and a ledger that dirtied the
    working tree would be deleted by the first person tidying a diff.
    """
    ledger = _ledger_path()
    if ledger == "":
        return
    session = ev.default(("session_id",), "unknown") or "unknown"
    stamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "ts": stamp,
        "session": session,
        # `--arg question "$(printf '%s' "$QUESTION" | head -c 500)"`: 500
        # BYTES, not characters, which is what `head -c` counts.
        "question": question.encode("utf-8", "surrogateescape")[:500].decode(
            "utf-8", "surrogateescape"
        ),
        "permission": perm_hit,
        "object": obj_hit,
    }
    try:
        with open(ledger, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        # `>>"$LEDGER" 2>/dev/null || true`
        pass


def run(ev):
    # jq IS NOT GUARANTEED HERE, and this comment used to claim it was: "jq is
    # guaranteed here: require-jq.sh runs first in this same chain and fails closed
    # without it." That is false. The AskUserQuestion matcher in
    # .claude/settings.json contains exactly ONE hook -- this one -- so nothing runs
    # ahead of it. Without jq the command substitution below produced an empty
    # QUESTION and the `[ -z ... ]` guard passed the question through SILENTLY: a
    # gate that cannot fire, wearing a comment that promised it could.
    #
    # The handling is now explicit and it FAILS OPEN ON PURPOSE, which is the
    # opposite of the rule for the Stop gates next door. A missing jq is this
    # hook's problem, not the session's, and blocking a legitimate question over a
    # missing binary is the precise failure the "narrow on purpose" note above
    # exists to prevent. So: pass the question, and SAY that it went unexamined
    # rather than pretending it was examined and cleared.
    if not hookio.have("jq"):
        ev.warn(NO_JQ)
        return hookio.ALLOW

    parts = []
    for path in (
        ("tool_input", "question"),
        ("tool_input", "questions", "[]?", "question"),
        ("tool_input", "questions", "[]?", "header"),
    ):
        parts.extend(hookio._jq_collect(ev.doc, path))
    question = hookio._command_substitution(" ".join(parts)).translate(_ASCII_LOWER)
    if question == "":
        return hookio.ALLOW

    perm_hit = _first_match(PERMISSION, question)
    if perm_hit == "":
        return hookio.ALLOW
    obj_hit = _first_match(OBJECT, question)
    if obj_hit == "":
        return hookio.ALLOW

    # `AFTER_PERM="${QUESTION#*"$PERM_HIT"}"` -- the shortest prefix, so the
    # FIRST occurrence of the permission phrase.
    cut = question.find(perm_hit)
    after_perm = question[cut + len(perm_hit) :] if cut >= 0 else question
    if obj_hit in after_perm:
        # `BETWEEN="${AFTER_PERM%%"$OBJ_HIT"*}"` -- up to the first occurrence.
        between = after_perm[: after_perm.find(obj_hit)]
        if hookio.grep_q(CLAUSE, between):
            return hookio.ALLOW
    # else: the object sits BEFORE the permission phrase. Left refusing,
    # deliberately: this anchor exists to stop a false positive, and guessing at
    # an unmeasured word order is how anchoring turns into narrowing.

    _record(ev, question, perm_hit, obj_hit)
    ev.warn_raw(MESSAGE)
    return hookio.DENY
