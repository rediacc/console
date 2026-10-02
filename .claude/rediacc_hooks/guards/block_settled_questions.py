"""Refuse an AskUserQuestion whose answer CLAUDE.md already gives.

THE PROBLEM, in the operator's words: "I don't know why you ask this question on each new session. It seems that my CLAUDE.md doesn't override you on each new session. See the big-bang statements there. Find a way to go for big-bang on each session."

They are right that the document is not enough. Anthropic's own guidance says so: "CLAUDE.md content is delivered as a user message after the system prompt, not as part of the system prompt itself... there's no guarantee of strict compliance", and "If the instruction is something that must run at a specific point... write it as a hook instead. Hooks execute as shell commands at
fixed lifecycle events and apply regardless of what Claude decides to do." So this is a hook.

WHAT IT REFUSES, and nothing more: a PERMISSION-SEEKING question about committing, branching, pushing, opening a PR or merging, OR a routing question about where a task's work should happen (new worktree vs. the current checkout). CLAUDE.md settles all of those the same way -- "verified work is committed right away, in small reviewable commits on the single current branch" (session default 1, 2026-09-25), "ask for the big-bang, not for permission to
patch one thing", and (2026-09-16, live) "[a worktree/branch routing question] shouldn't have asked ... it has big-bang answering usually" -- so asking costs the operator a round trip to repeat a rule they already wrote down.

THE MATCH IS NARROW ON PURPOSE, and the narrowness is the whole design. A hook that swallows legitimate questions is worse than the nagging it replaces, because the operator never learns what was suppressed. Two independent conditions must BOTH hold:

  1. a permission-seeking shape  (should I / shall I / do you want / may I /
     would you like / is it ok / can I / want me to)
  2. a git-workflow object       (commit / branch / push / PR / merge)
     in the SAME SENTENCE, not used as a noun ("the main push")

So "Should I commit this?" is refused, while "Which branch strategy fits this repo?" and "Did the rebase drop a commit?" pass untouched: they are questions about DESIGN and FACT, not requests for permission this repo already granted.

This is the same over-matching lesson wl_agents.py paid for four separate times in one session, where ordinary English words like `while`, `see`, `step` and `stop` were scoring as domain terms. Anchor on intent, not vocabulary.

WHAT A REFUSAL LEAVES BEHIND. Every refusal below appends one line to a ledger beside the worklist state (see LEDGER). Before that it left NO TRACE ANYWHERE, and `.claude/hooks/test-hooks.sh` says exactly why that matters: "a false positive is invisible by construction: the operator never learns what was not asked". A narrow matcher is only trustworthy if its misses are countable,
so the denominator has to exist on disk.

PORT NOTE ON `join(" ")`. The other four payload collectors in this chain join
with a NEWLINE; this one joins with a SPACE, and the difference is load-bearing
rather than cosmetic. Every regex below is unanchored and grep matches per RECORD, so a newline join would put the permission phrase and the object in different records and the two-condition test could never fire on a question
whose header carried one of them. `hookio.texts` is therefore not used here;
`_jq_collect` is called directly and joined the way the original does.

PORT NOTE ON `tr '[:upper:]' '[:lower:]'`. Under `LC_ALL=C` that maps the 26
ASCII letters and nothing else. Python's `str.lower()` also folds every non-ASCII uppercase codepoint, which would make a question containing, say, a Turkish dotted capital lowercase differently on the two sides. The translation table below is ASCII-only, deliberately.

PORT NOTE ON THE LEDGER'S SIDE EFFECT. This is the only guard in the chain that WRITES something, and the port keeps it: the differential compares (rc, stdout, stderr) and would pass either way, so dropping the append would be an invisible behaviour change -- exactly the class the "no trace anywhere" paragraph above is about. `jq -n -c` emits compact JSON with the keys in the order
given, which is
`json.dumps(..., separators=(",", ":"))` over a dict built in that same order.
"""

import datetime
import json
import re

from rediacc_hooks import hookio

CHAIN = "pre-ask"
ORDER = 3

# The clause anchor. Without it a sentence ABOUT the rule is refused as if it were the rule being broken -- "Should I explain in the report why we never commit unasked?" -- which is the mention-vs-target class reaching the pre-ask chain, where check_guard_mention_anchoring.py cannot see it because it globs pre-bash only.
DEFECT = (
    "if re.search(CLAUSE, between):\n            return None",
    "if False:\n            return None",
)

PERMISSION = (
    # The pronoun ends at a word boundary. Without it "what should ITS merge do?" read as "should i ... merge" and a release-policy question was refused (2026-10-02, #09e8d9bc); "may INclude" and "can WEb" were the same hole.
    r"(should|shall|may|can) (i|we)(?![a-z])|do you want|would you like|want me to|"
    r"is it (ok|okay|fine)|are you happy for|should it be|"
    r"where should|new worktree or|worktree or (the )?current|"
    r"should (a |the )?(new )?worktree|"
    # 2026-09-30: the branch/worktree ROUTING ask in its "which ... should" spelling, which the forms above never reached ("which branch should this go on?" passed). `branch` must be followed by a space, so "which branching strategy should ..." stays a design question.
    r"(which|what) (branch|worktree|checkout) (should|shall|do you want|would you like)"
)
# `pr` may end the text: a sentence or question is no longer followed by the joined header that used to supply the trailing character.
OBJECT = r"commit|branch|push|pull request|open a pr|[^a-z]pr([^a-z]|$)|merge|worktree"

# ---- ANCHOR: the permission must GOVERN the object, not merely precede it ---- Both regexes hit anywhere in the question, so a sentence ABOUT the rule was refused as if it were the rule being broken:
#
# "Should I explain in the report why we never commit unasked?" ^^^^^^^^ PERMISSION ^^^^^^ OBJECT -> exit 2
#
# That is the mention-vs-target class -- the same one that hit four pre-bash guards on 2026-08-28 -- reaching the pre-ask chain, which check_guard_mention_anchoring.py does not probe (it globs pre-bash only).
#
# ANCHOR, DO NOT NARROW: the object list stays exactly as it was. What is added is that no CLAUSE BOUNDARY may sit between the permission and the object. A subordinating conjunction or a comma means the object belongs to a different clause, which is precisely what "a sentence about it" looks like. The direct forms this guard exists for have nothing between them: "should i commit",
# "shall i open a pr", "do you want me to create a branch".
CLAUSE = (
    r"(^|[^a-z])(why|whether|that|because|how|when|if|before|after|unless|since|instead)"
    r"([^a-z]|$)|,"
)

# ---- SCOPE: the permission and the object must share a SENTENCE ---- Measured false positive, 2026-09-30 (#a1f111d6). A CI-budget question was refused as a commit/branch permission ask:
#
# "Renet (Full) build-renet took 16.7 min on the main push (...). It's on the release path, ... How should it be budgeted?" OBJECT `push` in sentence one, PERMISSION `should it be` in sentence three -> exit 2
#
# The object sat BEFORE the permission phrase, which the old code refused on purpose, but across the whole joined payload: every question of a multi-question ask and every header in one string. So the object could come from a different sentence, or a different question, than the permission. A sentence end (`.`, `?`, `!` or `;` followed by whitespace, or a newline) now bounds both
# conditions. "The commit is staged, should i proceed?" is ONE sentence and still refuses; "~3.7" is not a sentence end.
# The split keeps the terminator on its sentence (a lookbehind), so `[^a-z]pr[^a-z]` still sees the "?" after "open the pr".
SENTENCE_END = r"(?<=[.?!;])\s+|\n"

# ---- NOUN USE: "the main push" is an event, not an action ---- The same measurement's sibling: "Should we cap the main push job at 18?" has both conditions in one clause, and `push` there names a CI trigger, not something the assistant is asking leave to do. An object occurrence directly after one of these event modifiers is skipped. The list is closed and short on purpose: `the`/`a`
# are NOT in it, so the lowercased `should i open the pr?` still refuses.
NOUN_MODIFIER = r"(^|[^a-z])(main|nightly|ci|edge|stable|every|each|per|on)[ -]$"

# ---- A HEADER CARRIES THE OBJECT only when it IS the object ---- The bash original joined headers into the same string so a question whose header named the action ("Commit" over a bare go-ahead question) still refused. That join is also what let one question's object meet another question's permission. A header now counts only when it is essentially just the git action (an
# optional verb and article, then the object), so a topic chip like "Push strategy" or "Renet budget" never supplies an object.
HEADER_OBJECT = (
    r"^[^a-z]*((create|open|new|make|cut) )?((a|the) )?"
    r"(commit|branch|push|pull request|pr|merge|worktree)[^a-z]*$"
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

  Session default 1: "Verified work is committed right away, in small
  reviewable commits on the single current branch." Pushes run on a cadence
  ("at an epic milestone, at least every 2 hours of committed work, and before
  a stop that leaves unpushed commits"), and "a second branch or PR is the
  operator's own `!` command; there is nothing to ask for."

  Findings rule: "Ask for the big-bang, not for permission to patch one thing...
  put the whole cluster into a single plan and ask to run it."

  Worktree/branch routing: default to the checkout the session is already in.
  `git worktree add` stays hook-blocked from the assistant's own Bash tool
  regardless, so a new one only ever comes from the operator's own `!` prefix.

Proceed with the documented default: commit each verified unit on the current
branch, push on the documented cadence, and if a decision genuinely needs the
operator, park it as a worklist [?] carrying its own DEFAULT rather than
blocking the turn on a question.

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
    # 2026-09-16: the worktree/branch routing class, added live -- "shouldn't have asked ... it should also catch the worktree and branching questions". Same two-condition shape, new object and permission forms.
    (
        "worktree routing question",
        "Where should this work happen: a new worktree, or the current checkout?",
    ),
    ("should a new worktree be created", "Should a new worktree be created for this task?"),
    ("new worktree or continue", "New worktree or continue in the current checkout?"),
    ("which branch should this go on", "Which branch should this go on?"),
    ("which worktree should", "Which worktree should I use for this?"),
    ("can I push", "Can I push?"),
    ("should I open the pr", "Should I open the PR?"),
    ("push to main is still an action", "Should I push to main now?"),
    (
        "a header that is the object",
        {"tool_input": {"questions": [{"question": "Should I go ahead?", "header": "Commit"}]}},
    ),
    # 2026-09-30 (#a1f111d6), MEASURED: a CI job-budget ask refused as a commit/branch permission question. Object (`push`) and permission (`should it be`) sat three sentences apart, across two questions.
    (
        "a budget question naming the main push (measured)",
        {
            "tool_input": {
                "questions": [
                    {
                        "question": "Renet (Full) build-renet took 16.7 min on the main push "
                        "(cold build; ~3.7 on PRs). It's on the release path, and a 15-min "
                        "timeout would cancel a release. How should it be budgeted?",
                        "header": "Renet budget",
                        "options": [
                            {"label": "Cap at 20 (Recommended)"},
                            {"label": "Keep 15, fix the cold build"},
                        ],
                    },
                    {
                        "question": "E2E Workers jobs ran past 15 min on the main push. "
                        "Should both be capped at 18, or kept at 15?",
                        "header": "E2E budget",
                        "options": [
                            {"label": "Cap both at 18 (Recommended)"},
                            {"label": "Keep 15"},
                        ],
                    },
                ]
            }
        },
    ),
    ("the main push as a noun", "Should we cap the main push job at 18 minutes?"),
    ("on push as a trigger", "Should we run the lane on push or nightly?"),
    (
        "a topic header is not an object",
        {
            "tool_input": {
                "questions": [{"question": "Should it be capped at 20?", "header": "Push timeout"}]
            }
        },
    ),
    ("which branching strategy should", "Which branching strategy should this repo use?"),
    # 2026-10-02 (#09e8d9bc), MEASURED: "should its" matched "should i", so a release-policy question about a merge was refused. The pronoun ends at a word boundary now.
    (
        "should ITS merge is not should I (measured)",
        "A PR whose every commit is docs-only turns green. What should its merge do?",
    ),
    ("may include is not may I", "The release may include a merge commit, is that a problem?"),
    # CONTROL: mentioning worktrees is not itself permission-seeking.
    ("a design question about worktrees", "How are worktrees organized across the repos?"),
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

    BEST EFFORT, ALWAYS. `worklist.py --path` is self-contained (it works with every sibling module broken -- see suite case 118), but if python3 is missing or the write fails, the refusal still happens. A ledger that could veto the gate would be a worse bug than no ledger.
    """
    wlpath = hookio.run_out(
        ["python3", "%s/.claude/hooks/stop/worklist.py" % hookio.repo_root(), "--path"]
    )
    return "%s.ask-refusals.jsonl" % wlpath if wlpath else ""


def _record(ev, question, perm_hit, obj_hit):
    """One line per refusal, appended BEFORE the message is printed.

    It carries the timestamp, the session, the question text this hook actually matched against (lowercased and joined, i.e. what the regexes saw rather than a reconstruction), and the two spans that matched -- so "which condition matched" is answerable from the file instead of by re-deriving it.

    It lives beside the worklist state (TMPDIR/claude-worklist/<slug>.md), NOT in the repo: it is per-machine session debris, and a ledger that dirtied the working tree would be deleted by the first person tidying a diff.
    """
    ledger = _ledger_path()
    if ledger == "":
        return
    session = ev.default(("session_id",), "unknown") or "unknown"
    stamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "ts": stamp,
        "session": session,
        # `--arg question "$(printf '%s' "$QUESTION" | head -c 500)"`: 500 BYTES, not characters, which is what `head -c` counts.
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


def _text(node):
    """A field as `jq -r` would print it: nothing for null, JSON for a non-string."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    return json.dumps(node, separators=(",", ":"))


def _entries(doc):
    """(question, header) per asked question, ASCII-lowercased.

    Per QUESTION rather than one joined string: the join is what let the first question's object meet the second question's permission (see SCOPE).
    """
    tool_input = doc.get("tool_input") if isinstance(doc, dict) else None
    if not isinstance(tool_input, dict):
        return []
    out = []
    if tool_input.get("question") is not None:
        out.append((_text(tool_input.get("question")), ""))
    questions = tool_input.get("questions")
    if isinstance(questions, list):
        out.extend(
            (_text(item.get("question")), _text(item.get("header")))
            for item in questions
            if isinstance(item, dict)
        )
    return [(q.translate(_ASCII_LOWER), h.translate(_ASCII_LOWER)) for q, h in out]


def _objects(sentence):
    """Every OBJECT occurrence that is an action, as (start, end, text); noun uses skipped."""
    found = []
    for m in re.finditer(OBJECT, sentence):
        # Every OBJECT alternative contains a letter; `[^a-z]pr...` starts on the non-letter before it.
        core = m.start() + (0 if m.group(0)[0].isalpha() else 1)
        if re.search(NOUN_MODIFIER, sentence[:core]):
            continue
        found.append((m.start(), m.end(), m.group(0)))
    return found


def _judge(sentence, header_object):
    """(permission, object) when this sentence asks leave for a settled action, else None."""
    perm = re.search(PERMISSION, sentence)
    if perm is None:
        return None
    objects = _objects(sentence)
    if not objects:
        # The header IS the git action ("Commit" over a bare go-ahead question): it supplies the object, and the clause anchor still applies to what follows the permission.
        if header_object and not re.search(CLAUSE, sentence[perm.end() :]):
            return perm.group(0), header_object
        return None
    obj = objects[0][2]
    after = [o for o in objects if o[0] >= perm.end()]
    if any(o[2] == obj for o in after):
        start = next(o[0] for o in after if o[2] == obj)
        between = sentence[perm.end() : start]
        if re.search(CLAUSE, between):
            return None
    # else: the object sits BEFORE the permission phrase, in the same sentence ("The commit is staged, should i proceed?"). Left refusing, deliberately.
    return perm.group(0), obj


def run(ev):
    # jq IS NOT GUARANTEED HERE, and this comment used to claim it was: "jq is guaranteed here: require-jq.sh runs first in this same chain and fails closed without it." That is false. The AskUserQuestion matcher in .claude/settings.json contains exactly ONE hook -- this one -- so nothing runs ahead of it. Without jq the command substitution below produced an empty QUESTION and the
    # `[ -z ... ]` guard passed the question through SILENTLY: a gate that cannot fire, wearing a comment that promised it could.
    #
    # The handling is now explicit and it FAILS OPEN ON PURPOSE, which is the opposite of the rule for the Stop gates next door. A missing jq is this hook's problem, not the session's, and blocking a legitimate question over a missing binary is the precise failure the "narrow on purpose" note above exists to prevent. So: pass the question, and SAY that it went unexamined rather
    # than pretending it was examined and cleared.
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
    # The joined text is what the ledger records, unchanged; the MATCH runs per question and per sentence below.
    question = hookio._command_substitution(" ".join(parts)).translate(_ASCII_LOWER)
    if question == "":
        return hookio.ALLOW

    for text, header in _entries(ev.doc):
        header_hit = re.search(HEADER_OBJECT, header)
        header_object = header_hit.group(5) if header_hit else ""
        for sentence in [*re.split(SENTENCE_END, text), header]:
            if sentence.strip() == "":
                continue
            verdict = _judge(sentence, header_object)
            if verdict is not None:
                _record(ev, question, verdict[0], verdict[1])
                ev.warn_raw(MESSAGE)
                return hookio.DENY
    return hookio.ALLOW
