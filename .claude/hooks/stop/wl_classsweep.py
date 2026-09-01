"""wl_classsweep: the "sweep the class, not the instance" rule of the stop judge.

WHY THIS EXISTS, in the operator's words: "I've been fixing my instance each time
instead of the system that lets every session make the same mistake."

CLAUDE.md already carries the rule -- "Sweep the class, not the instance. Before
calling a bug fixed, grep for its siblings. One bad call site usually has
several." -- and it is routinely not followed, because nothing ever asks. Five
defects from ONE night, each fixed at a single site while the siblings were
found later by luck or by a human noticing:

  1. block-bash-write-to-running-script.sh matched a MENTION where it needed a
     TARGET. Fixed. The identical line in block-roundlog-truncate.sh was found
     separately, minutes later.
  2. private/renet/.ci/scripts/quality/format.sh died at exit 127 on a GOPATH
     assumption. Patching it moved the failure to lint.sh, which had the same
     bug; four scripts in that directory did.
  3. One row of a routing table (check:ci-actionlint) was wrong. So were
     check:ci-shell-lint and check:ci-shell-format -- three of six.
  4. Two agent-browser cases hardcoded one machine's path. The fix touched
     exactly those two; nothing asked about the other 1,557 cases.
  5. A guard false positive was fixed on the python-heredoc path; the redirect
     path had the same hole and was found only when it fired again.

The shape is identical every time: a fix lands, the message describes ONE site,
and no evidence is offered that anything looked for the others.

WHY IT IS NOT wl_reggate, which asks a neighbouring question on the same stop.
The regression gate asks "will this defect COME BACK?" and is satisfied by a
test. This asks "is this defect ALREADY THERE, somewhere else, right now?" and
is satisfied only by a search. A fix can be perfectly gated against recurrence
at the one site it was found and still leave three live siblings in the tree;
example 2 above is exactly that. So it is a separate object with a separate
verdict, riding the SAME judge call and the same artifact-detected fix signal,
which is what keeps it free: no second model call, no second detector.

TRIGGER BOUNDARY, and why it is drawn here. The rule is asked ONLY on a stop
that already carries wl_reggate's fix signal (`A FIX LANDED THIS TURN`). That
signal is artifact-derived -- a `^(fix|revert)[(!:]` commit subject between the
marker head and HEAD, or a `- [x]` this session ticked -- is de-duplicated per
fix-set so a settled fix-set is never re-asked, and already excludes docs-only
fix-sets. Every other trigger considered was prose-based ("the message says it
fixed something"), which fires on status reports, on plans, and on the same fix
described twice. A rule that fires always is a rule that gets skimmed, and this
one has to survive being read on every fix for months.

The model is then given an explicit escape: a defect with no possible second
occurrence (a typo in one string, a value correct only at that call site, the
only file of its kind) answers applicable=false and nothing fires.

ENFORCEMENT is a verdict flip, not a new blocking path: when the rule fires,
the judge's "stop" becomes "continue" with a reason naming the class and a
next_action carrying the exact search command. wl_checks already turns a
"continue" into a block. Nothing else in the stop battery had to change.

FAIL SEMANTICS. Unlike regression_gate, a missing or malformed class_sweep
object NEVER fails closed. It cannot become an escape hatch by degrading,
because the only thing it can do is turn a stop into a continue -- degrading
loses a demand, it never grants an exit that was otherwise refused. And an
unactionable block ("sweep the class" with no class and no search named) is
noise, which is the one thing this rule cannot afford.
"""

import os
import re
import shlex

import wl_rules

# The substring the prompt section carries, used by wl_judge.judge_schema_for to
# decide whether `class_sweep` is REQUIRED. Same contract as _REGGATE_MARKER:
# when the prompt asks for the object, the schema requires it, so the model
# cannot satisfy the schema by omitting the answer.
SWEEP_MARKER = "SWEEP THE CLASS, NOT THE INSTANCE"

EVIDENCE_KINDS = ("gate", "scan", "statement", "none")

CLASS_SWEEP_SCHEMA = {
    "type": "object",
    "properties": {
        "applicable": {"type": "boolean"},
        "defect_class": {"type": "string", "maxLength": 300},
        "locus": {"type": "string", "maxLength": 200},
        "search": {"type": "string", "maxLength": 300},
        "evidence": {"type": "string", "maxLength": 300},
        "evidence_kind": {"type": "string", "enum": list(EVIDENCE_KINDS)},
        "swept": {"type": "boolean"},
        "instruction": {"type": "string", "maxLength": 300},
    },
    "required": [
        "applicable",
        "defect_class",
        "locus",
        "search",
        "evidence",
        "evidence_kind",
        "swept",
        "instruction",
    ],
    "additionalProperties": False,
}

# The rubric. Written as WORKED EXAMPLES from this repo rather than as
# definitions, because "is there a class?" is a judgement about a specific
# defect and the five cases below are the calibration set the operator supplied.
SWEEP_PROMPT = """

SWEEP THE CLASS, NOT THE INSTANCE. ALSO fill the `class_sweep` object, about
the same fix-set.

This project's standing rule is "Before calling a bug fixed, grep for its
siblings. One bad call site usually has several." It is written down and
routinely not followed. Five real defects from one night, each fixed at ONE
site while the siblings were found later by luck:

  - a guard script matched a MENTION of a filename where it needed the
    filename as a command TARGET; the identical line in a second guard was
    found minutes later. Two files, one class.
  - a CI script died on a PATH assumption; patching it moved the failure to
    the next script, and four scripts in that directory had it.
  - one row of a six-row routing table was wrong; three rows were.
  - two test cases hardcoded one machine's path; nothing asked whether the
    other 1,557 cases in that suite do the same.
  - a guard false positive was fixed on the heredoc path; the redirect path
    had the same hole and fired again later.

The shape is always identical: the fix lands, the message describes ONE site,
and no evidence is offered that anything looked for the others.

And two from the same night where the answer is applicable=FALSE, because
there is nothing to sweep:

  - "The error message said 'reposiotry'. Fixed the spelling in that one
    string." A misspelling has no mechanism behind it. Another one somewhere
    else would be a coincidence, not a consequence, and blocking a session to
    grep for it buys nothing. applicable=false.
  - "Bumped the pinned action from v4 to v5." A version bump is not a defect
    with siblings. applicable=false.

Answer these about the fix-set above.

(1) CLASS. State the defect as a PATTERN, not as a location. "block-x.sh
matched a mention" is a location; "a guard that greps for a script name
without anchoring it to the command position" is a class.

THE TEST IS A MECHANISM, NOT A COINCIDENCE, and this is the whole judgement.
A class exists when something in the tree MAKES the same defect likely
elsewhere: a shared assumption, an idiom copied from file to file, a table
with more rows, a directory of scripts written from one template, two paths
through the same guard. Every example above is one of those.

If the only thing siblings could share is that a human slipped the same way --
a misspelling, a wrong number, an awkward sentence -- there is NO mechanism
and no class, so answer applicable=false, even though an identical slip
somewhere else is perfectly imaginable and even though you could write a grep
for it. This object BLOCKS a session; it must not spend a block on a search
worth two seconds of idle curiosity. Also false for: a value correct only at
that one call site, the only file of its kind, a dependency bump, a revert,
pure formatting, documentation prose.

A CATEGORY OF HUMAN ERROR IS NOT A CLASS EITHER. "other typos", "other
missing tests", "other badly named things" name a kind of mistake, not a
shape: the search returns the whole repo and fixes nothing.

Most real fixes DO have a mechanism behind them -- but a rule that fires on
everything is a rule that gets skimmed, so say false plainly when it is
false.

(2) LOCUS and SEARCH. Where would siblings live, and what ONE command would
enumerate them? Name a real command (a grep or rg with the actual pattern, a
glob over the sibling directory), because the session is going to be told to
run exactly this.

THE COMMAND IS CHECKED BEFORE IT IS HANDED OVER. It must parse, and every
directory or file it names must actually exist in this repo. Two real misfires:
one named `packages/workers/`, which does not exist (they live at `workers/`),
and the session ran it and got grep's error line back looking like a result;
another was cut off mid-token by the length limit and could not parse. Keep it
SHORT and use paths you have actually seen in the message. A command that fails
the check is dropped and the session is told you proposed one that does not
run -- the class still gets swept, but by a search you did not write.

(3) EVIDENCE. Does the session's message show the class was ACTUALLY swept?
Only three things count, and quote the words that carry it in `evidence`:
  gate       a check was added or changed that would now fail for EVERY
             sibling, not only the one that was fixed.
  scan       a search across the repo is reported WITH ITS RESULT: how many
             siblings it found, and that each was fixed.
  statement  an explicit claim that the siblings were searched for and this
             is the only instance.
Intent is not evidence. "I fixed X", "this may apply elsewhere", "a follow-up
could check the others", a TODO, a filed issue, and a plan to look later are
all `none`. A fix touching several files is `none` too, unless the message
says how that set was ENUMERATED -- fixing three files you happened to trip
over is not a sweep.

Set swept=true ONLY when evidence_kind is not `none`. An assertion with no
quotable evidence is exactly the failure this object exists to catch.

(4) THIS IS NOT ONLY ABOUT CODE. Ask the same question of: a guard or hook
fixed for one file (siblings: the other guards); a test fixed for one machine
or one path (siblings: the other cases in that suite); a gate or route wired
for one surface (siblings: the other rows of the same table or manifest); a
CI red fixed by hand rather than gated (siblings: the other reds of that
shape). Do NOT ask it of documentation prose, translations, a version bump,
or a revert.

Fill class_sweep accordingly: applicable, defect_class (the pattern, one
line), locus, search (the command), evidence (the quote, or empty string),
evidence_kind, swept, instruction (the concrete next step for the session).
"""

FOLLOWUP_PROMPT = """

SWEEP THE CLASS, NOT THE INSTANCE. An earlier stop this session was told its
fix addressed one instance of a class, and was ordered to sweep it:

  CLASS:  %(defect_class)s
  SEARCH: %(search)s

Fill the `class_sweep` object again, judging ONLY whether the message now
carries the evidence: a gate that covers every sibling, a scan reported with
its count, or an explicit "searched, this is the only instance". Keep
applicable=true and repeat the same class and search. If the message does not
mention the sweep at all, swept=false with evidence_kind `none`.
"""


def prompt_section(fix_signal, outstanding=None):
    """The prompt text to append, or "" when this stop asks nothing.

    The fix signal wins over an outstanding demand: a NEW fix-set is a new
    class, and asking about the old one instead would drop it.
    """
    if fix_signal:
        return SWEEP_PROMPT
    if outstanding:
        return FOLLOWUP_PROMPT % {
            "defect_class": (outstanding.get("defect_class") or "(not recorded)")[:300],
            "search": (outstanding.get("search") or "(not recorded)")[:300],
        }
    return ""


# -- The verdict ------------------------------------------------------------


def _clean(obj, key, limit):
    v = obj.get(key)
    return v.strip()[:limit] if isinstance(v, str) else ""


def read_verdict(out):
    """(kind, payload). kind is 'silent', 'fire' or 'degraded'.

    'degraded' means the object was missing or unusable, which is reported and
    never blocked on -- see the module docstring's FAIL SEMANTICS.
    """
    cs = out.get("class_sweep") if isinstance(out, dict) else None
    if not isinstance(cs, dict):
        return "degraded", "no class_sweep object: %s" % repr(cs)[:120]
    if not isinstance(cs.get("applicable"), bool) or not isinstance(cs.get("swept"), bool):
        return "degraded", "class_sweep applicable/swept not booleans"
    kind = cs.get("evidence_kind")
    if kind not in EVIDENCE_KINDS:
        return "degraded", "class_sweep evidence_kind %r is not one of %s" % (kind, EVIDENCE_KINDS)
    if not cs["applicable"]:
        return "silent", "no class: this defect cannot occur twice"
    # THE CLAIM IS CHECKED AGAINST ITS OWN EVIDENCE, not taken as given. The
    # operator's ask was for evidence, not assertion, so `swept: true` with
    # evidence_kind `none` is a bare assertion and counts as NOT swept. This is
    # the one place the rule overrides the model's own summary, and it is the
    # point of the rule.
    if cs["swept"] and kind != "none":
        return "silent", "class swept (%s): %s" % (kind, _clean(cs, "evidence", 160) or "(quoted)")
    defect_class = _clean(cs, "defect_class", 300)
    if not defect_class:
        # An order with no class named is unactionable, and an unactionable
        # block is the noise that gets this rule routed around.
        return "degraded", "class_sweep fired with no defect_class named"
    return "fire", {
        "defect_class": defect_class,
        "locus": _clean(cs, "locus", 200),
        "search": _clean(cs, "search", 300),
        "instruction": _clean(cs, "instruction", 300),
        "asserted": bool(cs["swept"]),
    }


# -- The judge's own command is CHECKED before it becomes an order ----------
#
# WHY. `enforce` writes "Run: <search>" and the session is told to run exactly
# that, so the command IS the enforcement. Over four consecutive stops in one
# session the commands handed over were:
#
#   grep -rn 'export.*worker' packages/workers/ --include='*.ts' | wc -l
#       `packages/workers/` DOES NOT EXIST in this repo (the workers live at
#       `workers/`). The command printed `1` -- grep's error line, counted by
#       wc -- and a bare `1` reads exactly like a finding.
#
#   find workers -type f \( -name '*.ts' -o -name '*.tsx' \) | xargs -I {} sh -c 'grep -q {} tsconfig.json || echo {
#       cut off at the 300-character schema cap, mid-token, with an unbalanced
#       quote. It cannot parse, so it cannot run.
#
# The module docstring already says an unactionable block is "the one thing
# this rule cannot afford". A WRONG-BUT-PLAUSIBLE order is worse than an absent
# one: it spends the session's turn and can manufacture a false finding out of
# an error message. So the command is validated, and a command that fails is
# DROPPED -- never the demand. The block still happens, at full strength; only
# the bogus "Run: ..." is replaced by the generic order plus the reason, which
# is also how the operator gets to see that the model is emitting commands that
# do not run.
#
# WHAT THIS CANNOT CATCH, said plainly so the green is not over-read: a command
# that runs and answers the wrong question. `tsc --noEmit | grep 'error TS'` at
# this repo's root is perfectly runnable and reports 10,095 errors that are all
# the base config rather than any defect. Static validation reaches syntax and
# existence; it never reaches meaning.

SEARCH_MAX = 300  # the schema's maxLength; a value at the cap arrived truncated

# A SWEEP ENUMERATES. It never writes, moves or deletes, so a proposed command that
# does is not a bad search -- it is an order to damage the tree, issued by a model,
# handed to a session under the words "Run:". This repo's standing rule that no
# session may `git checkout` / `restore` / `stash` / `clean` exists because the tree
# carries other sessions' uncommitted work; a rule that ORDERS one of those would be
# worse than the mistake it was written to stop.
#
# A denylist rather than an allowlist of read-only verbs: the set below is small,
# well known and unambiguous, while the set of legitimate ways to enumerate siblings
# is not, and rejecting a valid search costs the very actionability this rule needs.
_DESTRUCTIVE = frozenset(
    (
        "rm",
        "rmdir",
        "mv",
        "cp",
        "dd",
        "truncate",
        "shred",
        "install",
        "chmod",
        "chown",
        "chgrp",
        "ln",
        "mkdir",
        "touch",
        "tee",
        "kill",
        "pkill",
        "reboot",
        "shutdown",
    )
)
# git subcommands that discard work. `git grep` / `git ls-files` are exactly what a
# sweep should use, so git itself is not denied -- only these second words are.
_DESTRUCTIVE_GIT = frozenset(
    ("checkout", "restore", "stash", "clean", "reset", "rm", "mv", "push", "commit")
)

# A token shaped like a repo path: at least one `/`, and only characters a path
# or a glob would carry.
_PATHY = re.compile(r"^[A-Za-z0-9_.@+-]*(?:/[A-Za-z0-9_.@+*?\[\]-]*)+/?$")


def _repo_root():
    # .claude/hooks/stop/ -> repo root
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
    )


def validate_search(search, root=None):
    """(ok, reason). `reason` is empty when ok, else why the command was dropped."""
    root = root or _repo_root()
    if not search:
        return False, "no command was given"
    if len(search) >= SEARCH_MAX:
        return False, "it arrived truncated at the %d-character cap" % SEARCH_MAX
    try:
        tokens = shlex.split(search)
    except ValueError as exc:
        return False, "it does not parse (%s)" % exc
    if not tokens:
        return False, "it is empty once parsed"

    for i, tok in enumerate(tokens):
        if tok in (">", ">>"):
            return False, "it redirects output into a file, and a sweep only reads"
        if tok.startswith(">"):
            return False, "it redirects output into a file, and a sweep only reads"
        if tok in _DESTRUCTIVE:
            return False, "it runs `%s`, which writes or deletes; a sweep only reads" % tok
        if tok == "git" and i + 1 < len(tokens) and tokens[i + 1] in _DESTRUCTIVE_GIT:
            return False, "it runs `git %s`, which changes the tree; a sweep only reads" % tokens[
                i + 1
            ]
        if tok == "-delete":
            return False, "it passes -delete to find; a sweep only reads"
        if tok == "-i" and tokens[0] in ("sed", "perl"):
            return False, "it edits in place with `%s -i`; a sweep only reads" % tokens[0]

    for tok in tokens:
        if tok.startswith("-") or not _PATHY.match(tok):
            continue
        if any(c in tok for c in "*?["):
            continue  # a glob names a set, not a file; nothing to exist-check
        rel = tok.rstrip("/")
        # ONLY judge a token whose FIRST segment is a real top-level entry. That
        # is what makes it a repo path rather than a quoted regex that happens
        # to contain a slash, and it is exactly the shape that failed:
        # `packages/` exists, `packages/workers/` does not.
        head = rel.split("/", 1)[0]
        if not head or not os.path.exists(os.path.join(root, head)):
            continue
        if not os.path.exists(os.path.join(root, rel)):
            return False, "it names %s, which does not exist in this repo" % rel

    return True, ""


V_REASON = (
    "SWEEP THE CLASS, NOT THE INSTANCE. A fix landed and the message shows only "
    "its own instance fixed. Class: %s. No evidence that the siblings were "
    "searched for%s."
)
V_ASSERTED = " (the sweep is asserted, but no gate, no scan count and no explicit search is quoted)"

V_ACTION = (
    "Run: %s -- fix every sibling it finds and say the COUNT, or say plainly that it found none."
)
V_ACTION_NOSEARCH = (
    "Grep for siblings of this class across the repo, fix every one you find and say the COUNT, "
    "or say plainly that this is the only instance. %s"
)
# Kept SHORT on purpose: wl_rules.apply_order caps next_action at 200 characters,
# and the first draft of this string put the reason last, where the cap ate it --
# the session was handed a sentence that stopped mid-word. The WHY leads, and the
# rejected command is deliberately NOT echoed: it is the one thing that must not
# be run, and quoting it is what blew the budget.
V_ACTION_DROPPED = (
    "Proposed command DROPPED: %(why)s. Grep for siblings yourself, fix each and say the "
    "COUNT, or say it is the only instance."
)


def enforce(out, payload):
    """Write the sweep order into a judge verdict, in place. Returns the note."""
    reason = V_REASON % (payload["defect_class"], V_ASSERTED if payload["asserted"] else "")
    ok, why = validate_search(payload["search"])
    if ok:
        action = V_ACTION % payload["search"]
    elif payload["search"]:
        action = V_ACTION_DROPPED % {"why": why[:70]}
    else:
        action = V_ACTION_NOSEARCH % payload["instruction"]
    wl_rules.apply_order(out, reason, action)
    return "class-sweep: %s" % payload["defect_class"][:160]


# -- The outstanding-demand marker -----------------------------------------
#
# WHY A MARKER AT ALL. The fix signal is de-duplicated per fix-set by wl_reggate
# and a settled fix-set is never re-asked, so without this the demand is
# strictly one-shot: a session could stop again with no new commits and never be
# asked whether it did the sweep. The marker carries the question forward onto
# the next judged stop. Its bounds -- and why they are hard -- are in wl_rules.

SWEEP_TTL_MIN = int(os.environ.get("WORKLIST_SWEEP_TTL_MIN", "120"))
SWEEP_MAX_FIRES = int(os.environ.get("WORKLIST_SWEEP_MAX_FIRES", "2"))

SWEEP_DEMAND = wl_rules.Demand("classsweep", SWEEP_TTL_MIN, SWEEP_MAX_FIRES)

# Three named wrappers, not four. A `marker_path` wrapper stood here after the
# refactor onto wl_rules.Demand with nothing left calling it, and case 143's
# dead-code gate named it on the first full run -- SWEEP_DEMAND.path() is the
# one spelling. Do not add a pass-through here unless something calls it.


def load_outstanding(path=None):
    return SWEEP_DEMAND.load(path)


def save_outstanding(payload, prior=None, path=None):
    SWEEP_DEMAND.bank(
        {"defect_class": payload["defect_class"], "search": payload["search"]}, prior, path
    )


def clear_outstanding(path=None):
    SWEEP_DEMAND.clear(path)


def apply_verdict(out, outstanding=None, path=None):
    """(kind, note). Mutates `out` when the rule fires; owns the marker lifecycle.

    kind is 'fire', 'silent' or 'degraded'. A silent OR degraded answer
    discharges any outstanding demand: carrying one forward on an answer nobody
    could read would block a session on the judge's malfunction rather than on
    anything it did.
    """
    kind, payload = read_verdict(out)
    if kind == "fire":
        note = enforce(out, payload)
        save_outstanding(payload, outstanding, path)
        return "fire", note
    clear_outstanding(path)
    return kind, payload if isinstance(payload, str) else ""
