"""wl_classsweep: the "sweep the class, not the instance" rule of the stop judge.

WHY THIS EXISTS, in the operator's words: "I've been fixing my instance each time instead of the system that lets every session make the same mistake."

CLAUDE.md already carries the rule -- "Sweep the class, not the instance. Before calling a bug fixed, grep for its siblings. One bad call site usually has several." -- and it is routinely not followed, because nothing ever asks. Five defects from ONE night, each fixed at a single site while the siblings were found later by luck or by a human noticing:

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

The shape is identical every time: a fix lands, the message describes ONE site, and no evidence is offered that anything looked for the others.

WHY IT IS NOT wl_reggate, which asks a neighbouring question on the same stop. The regression gate asks "will this defect COME BACK?" and is satisfied by a test. This asks "is this defect ALREADY THERE, somewhere else, right now?" and is satisfied only by a search. A fix can be perfectly gated against recurrence
at the one site it was found and still leave three live siblings in the tree;
example 2 above is exactly that. So it is a separate object with a separate verdict, riding the SAME judge call and the same artifact-detected fix signal, which is what keeps it free: no second model call, no second detector.

TRIGGER BOUNDARY, and why it is drawn here. The rule is asked ONLY on a stop that already carries wl_reggate's fix signal (`A FIX LANDED THIS TURN`). That signal is artifact-derived -- a `^(fix|revert)[(!:]` commit subject between the marker head and HEAD, or a `- [x]` this session ticked -- is de-duplicated per fix-set so a settled fix-set is never re-asked, and already excludes
docs-only fix-sets. Every other trigger considered was prose-based ("the message says it fixed something"), which fires on status reports, on plans, and on the same fix described twice. A rule that fires always is a rule that gets skimmed, and this one has to survive being read on every fix for months.

The model is then given an explicit escape: a defect with no possible second occurrence (a typo in one string, a value correct only at that call site, the
only file of its kind) answers applicable=false and nothing fires.

ENFORCEMENT is a verdict flip, not a new blocking path: when the rule fires, the judge's "stop" becomes "continue" with a reason naming the class and a next_action carrying the exact search command. wl_checks already turns a "continue" into a block. Nothing else in the stop battery had to change.

FAIL SEMANTICS. Unlike regression_gate, a missing or malformed class_sweep object NEVER fails closed. It cannot become an escape hatch by degrading, because the only thing it can do is turn a stop into a continue -- degrading loses a demand, it never grants an exit that was otherwise refused. And an unactionable block ("sweep the class" with no class and no search named) is noise,
which is the one thing this rule cannot afford.
"""

import datetime
import os
import re
import shlex

import wl_common
import wl_rules

# The substring the prompt section carries, used by wl_judge.judge_schema_for to decide whether `class_sweep` is REQUIRED. Same contract as _REGGATE_MARKER: when the prompt asks for the object, the schema requires it, so the model cannot satisfy the schema by omitting the answer.
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

# The rubric. Written as WORKED EXAMPLES from this repo rather than as definitions, because "is there a class?" is a judgement about a specific defect and the five cases below are the calibration set the operator supplied.
SWEEP_PROMPT = """

SWEEP THE CLASS, NOT THE INSTANCE. ALSO fill the `class_sweep` object, about
the same fix-set.

WHAT THIS IS FOR: CONSOLIDATION, THE DRY PRINCIPLE. The question is whether the
LOGIC THIS FIX CHANGED exists as another copy or as a sibling implementation of
the same decision somewhere else in the tree. If it does, the right outcome is
usually ONE shared home that every caller consults, not the same patch applied
N times. It is not a keyword hunt over the words of the session's own message,
and it is never a report on how the session behaved.

This project's standing rule is "Before calling a bug fixed, grep for its
siblings. One bad call site usually has several." It is written down and
routinely not followed. Three real defects, each fixed at ONE site while the
siblings were found later by luck. They are three because each names a
DIFFERENT mechanism; two more from the same night were dropped as restating
one of these:

  - TWO PATHS THROUGH ONE GUARD. A guard matched a MENTION of a filename
    where it needed the filename as a command TARGET; the identical line in
    a second guard was found minutes later.
  - A DIRECTORY WRITTEN FROM ONE TEMPLATE. A CI script died on a PATH
    assumption; patching it moved the failure to the next script, and four
    scripts in that directory had it.
  - A TABLE WITH MORE ROWS. One row of a six-row routing table was wrong;
    three rows were.

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

Answer these about the fix-set above. The fix being swept is the one shown in
the ACTUAL FILES list above (if one was injected) or, when that list is empty,
a change the message explicitly quotes. If neither points at a real fix,
applicable=false: there is nothing to sweep.

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

ANCHOR THE SEARCH TO THE CHANGED CODE. Build the pattern from something that
appears in the files of the fix-set: a function or constant name, a regex, a
call shape, an idiom that was edited. Words such as "claim", "swept" or
"transform" taken from the message's own prose describe the WORK, not the code,
and match thousands of unrelated comments. A search that cannot be traced to a
line the fix touched is not a sweep: answer applicable=false instead.

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


_SEARCH_TOOLS = ("grep", "egrep", "fgrep", "rg")
# Options of those tools that take a SEPARATE value, so the value is not mistaken for the pattern.
_VALUED_OPTS = frozenset(
    {"-A", "-B", "-C", "-m", "--max-count", "-g", "--glob", "-t", "--type", "-T", "--type-not"}
    | {"--include", "--exclude", "--exclude-dir", "-f", "--file", "-d", "-D", "--context"}
)
_CMD_SEPARATORS = frozenset({"|", "||", "&&", ";"})


def search_pattern(search):
    """The pattern argument of the first `grep`, `rg` or `git grep` in a search command, or "".

    Shared by the transcript discharge (R.2) and the instance grounding (R.3) of agent/plans/PLAN-stop-hook-retro-20260924.md, so both read one command the same way. "" whenever the command does not parse or names no such tool: the callers then change nothing.
    """
    try:
        tokens = shlex.split(search or "")
    except ValueError:
        return ""
    i = 0
    while i < len(tokens):
        base = os.path.basename(tokens[i])
        if base in _SEARCH_TOOLS:
            j = i + 1
        elif base == "git" and i + 1 < len(tokens) and tokens[i + 1] == "grep":
            j = i + 2
        else:
            i += 1
            continue
        while j < len(tokens):
            tok = tokens[j]
            if tok in _CMD_SEPARATORS:
                break
            if tok in ("-e", "--regexp") and j + 1 < len(tokens):
                return tokens[j + 1]
            if tok.startswith("--regexp="):
                return tok.split("=", 1)[1]
            if tok == "--":
                return tokens[j + 1] if j + 1 < len(tokens) else ""
            if tok.startswith("-"):
                j += 2 if tok in _VALUED_OPTS else 1
                continue
            return tok
        i = j + 1
    return ""


def search_hits_instance(search, root, ids):
    """Whether the search's pattern matches any +/- line of the fix-set's own commits: True, False, or None when it cannot tell (agent/plans/PLAN-stop-hook-retro-20260924.md R.3).

    A search that cannot find the fixed instance cannot find its siblings either. On 2026-09-24 the judge twice handed over `grep -r 'post-tool' ...` for a fix that changed a timeout number, and a session told to run a search that matches nothing is told nothing. Only a COMMIT-based fix-set has its own diff; the caller passes `ids` only for provenance `diff-tree`.
    """
    pattern = search_pattern(search)
    if not pattern or not ids:
        return None
    import wl_core as C  # noqa: PLC0415

    changed: list[str] = []
    for sha in ids:
        diff = C._git(root, "show", "--format=", "--no-color", "--no-ext-diff", "-U0", sha) or ""
        changed.extend(
            ln[1:]
            for ln in diff.splitlines()
            if ln[:1] in ("+", "-") and not ln.startswith(("+++", "---"))
        )
    if not changed:
        return None
    try:
        tokens = shlex.split(search)
    except ValueError:
        return None
    shorts = "".join(t[1:] for t in tokens if t.startswith("-") and not t.startswith("--"))
    ignore_case = "i" in shorts or "--ignore-case" in tokens
    literal = "F" in shorts or "--fixed-strings" in tokens
    regex = None
    if not literal:
        # grep's basic-regex alternation and grouping, spelled the way Python's `re` reads them.
        spelled = pattern.replace("\\|", "|").replace("\\(", "(").replace("\\)", ")")
        try:
            regex = re.compile(spelled, re.IGNORECASE if ignore_case else 0)
        except re.error:
            regex = None
    needle = pattern.lower() if ignore_case else pattern
    for line in changed:
        if regex is not None and regex.search(line):
            return True
        if needle in (line.lower() if ignore_case else line):
            return True
    return False


# How much of the lead transcript's tail the discharge reads. A demand lives SWEEP_TTL_MIN, so its evidence is near the end; a whole 200 MB transcript is never parsed on a stop.
EVIDENCE_TAIL_BYTES = 32 * 1024 * 1024


def _tail_lines(path, max_bytes):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read()
    except (OSError, TypeError):
        return []
    lines = data.split(b"\n")
    return lines[1:] if size > max_bytes else lines


def _epoch(stamp):
    """Epoch seconds of a transcript timestamp (`2026-09-24T15:00:00.123Z`), or None."""
    try:
        return datetime.datetime.fromisoformat(str(stamp)).timestamp()
    except (TypeError, ValueError):
        return None


def sweep_evidenced(outstanding, transcript):
    """True when the lead transcript, AFTER the demand first fired, holds a Bash tool call whose command contains the demand's own search pattern AND whose tool_result came back (agent/plans/PLAN-stop-hook-retro-20260924.md R.2).

    WHY. A FOLLOWUP judges only the last message, so a sweep the session really ran two turns earlier had to be re-run to be seen (2026-09-24 14:57). The transcript is the harness's record, not the session's narration, so it is evidence the lead cannot fabricate by describing it.

    Fails toward "not evidenced": no pattern, a pattern under 3 characters, no timestamp on the call, a call before the demand, or a call with no result each keep the demand.
    """
    if not isinstance(outstanding, dict) or not transcript:
        return False
    pattern = search_pattern(outstanding.get("search") or "")
    if len(pattern) < 3:
        return False
    try:
        since = float(outstanding.get("first_at") or outstanding.get("at") or 0)
    except (TypeError, ValueError):
        return False
    if since <= 0:
        return False
    calls = set()
    for rec in wl_common.records(_tail_lines(transcript, EVIDENCE_TAIL_BYTES), need=b'"tool_'):
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        if rec.get("type") == "assistant":
            when = _epoch(rec.get("timestamp"))
            if when is None or when < since:
                continue
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "Bash"
                    and pattern in str((block.get("input") or {}).get("command") or "")
                ):
                    calls.add(str(block.get("id") or ""))
        elif rec.get("type") == "user" and calls:
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and str(block.get("tool_use_id") or "") in calls
                ):
                    return True
    return False


def discharge_if_evidenced(outstanding, transcript, path=None):
    """The outstanding demand after discharging every head the transcript already answers, or None. A discharged head is PROMOTED, so a demand parked in `owed` is asked next rather than lost."""
    for _ in range(2):  # a head plus its one `owed` slot
        if not outstanding or not sweep_evidenced(outstanding, transcript):
            return outstanding
        SWEEP_DEMAND.promote(path)
        outstanding = load_outstanding(path)
    return outstanding


def prompt_section(fix_signal, outstanding=None, transcript=None):
    """The prompt text to append, or "" when this stop asks nothing.

    The fix signal wins over an outstanding demand: a NEW fix-set is asked about fresh, on SWEEP_PROMPT, which never mentions the outstanding class -- that demand is not dropped, it is carried forward in the marker's `owed` slot (wl_rules.Demand.displace) and asked in full on a later stop that is not a fix stop.

    `transcript`: an outstanding demand the lead transcript already answers (`sweep_evidenced`) asks nothing.
    """
    if fix_signal:
        return SWEEP_PROMPT
    if outstanding and transcript and sweep_evidenced(outstanding, transcript):
        return ""
    if outstanding:
        return FOLLOWUP_PROMPT % {
            "defect_class": (outstanding.get("defect_class") or "(not recorded)")[:300],
            "search": (outstanding.get("search") or "(not recorded)")[:300],
        }
    return ""


# -- The verdict ------------------------------------------------------------


_clean = wl_common.clean


def read_verdict(out):
    """(kind, payload). kind is 'silent', 'fire' or 'degraded'.

    'degraded' means the object was missing or unusable, which is reported and never blocked on -- see the module docstring's FAIL SEMANTICS.
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
    # THE CLAIM IS CHECKED AGAINST ITS OWN EVIDENCE, not taken as given. The operator's ask was for evidence, not assertion, so `swept: true` with evidence_kind `none` is a bare assertion and counts as NOT swept. This is the one place the rule overrides the model's own summary, and it is the point of the rule.
    if cs["swept"] and kind != "none":
        return "silent", "class swept (%s): %s" % (kind, _clean(cs, "evidence", 160) or "(quoted)")
    defect_class = _clean(cs, "defect_class", 300)
    if not defect_class:
        # An order with no class named is unactionable, and an unactionable block is the noise that gets this rule routed around.
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
# WHY. `enforce` writes "Run: <search>" and the session is told to run exactly that, so the command IS the enforcement. Over four consecutive stops in one session the commands handed over were:
#
#   grep -rn 'export.*worker' packages/workers/ --include='*.ts' | wc -l
# `packages/workers/` DOES NOT EXIST in this repo (the workers live at `workers/`). The command printed `1` -- grep's error line, counted by wc -- and a bare `1` reads exactly like a finding.
#
#   find workers -type f \( -name '*.ts' -o -name '*.tsx' \) | xargs -I {} sh -c 'grep -q {} tsconfig.json || echo {
# cut off at the 300-character schema cap, mid-token, with an unbalanced quote. It cannot parse, so it cannot run.
#
# The module docstring already says an unactionable block is "the one thing this rule cannot afford". A WRONG-BUT-PLAUSIBLE order is worse than an absent one: it spends the session's turn and can manufacture a false finding out of an error message. So the command is validated, and a command that fails is DROPPED -- never the demand. The block still happens, at full strength; only
# the bogus "Run: ..." is replaced by the generic order plus the reason, which is also how the operator gets to see that the model is emitting commands that do not run.
#
# WHAT THIS CANNOT CATCH, said plainly so the green is not over-read: a command that runs and answers the wrong question. `tsc --noEmit | grep 'error TS'` at this repo's root is perfectly runnable and reports 10,095 errors that are all the base config rather than any defect. Static validation reaches syntax and existence; it never reaches meaning.

SEARCH_MAX = 300  # the schema's maxLength; a value at the cap arrived truncated

# A SWEEP ENUMERATES. It never writes, moves or deletes, so a proposed command that does is not a bad search -- it is an order to damage the tree, issued by a model and handed to a session under the word "Run:". The verb sets and the prose matcher live in wl_rules because wl_bravedefault needs them too at a DIFFERENT threshold; keeping a second copy here is the very duplication
# this module exists to catch.
_DESTRUCTIVE = wl_rules.WRITE_VERBS
_DESTRUCTIVE_GIT = wl_rules.WRITE_GIT

# A token shaped like a repo path: at least one `/`, and only characters a path or a glob would carry.
_PATHY = re.compile(r"^[A-Za-z0-9_.@+-]*(?:/[A-Za-z0-9_.@+*?\[\]-]*)+/?$")


def _repo_root():
    # .claude/hooks/stop/ -> repo root
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
    )


def names_destructive(text):
    """The write verb this PROSE names, or "". See wl_rules.names_write.

    THE SECOND DOOR, and it stayed open after the first was shut. `search` is a command and is validated as one; `instruction` is model-authored PROSE that reaches the session verbatim through V_ACTION_NOSEARCH whenever `search` is empty. Prose is not a command line, so it is not tokenised -- but a session told "next step: git clean -xdf" may well run it, and the read-only
    guarantee a sweep carries has to hold on every path out of this module, not only the one wearing the word "Run:".
    """
    return wl_rules.names_write(text)


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
        # ONLY judge a token whose FIRST segment is a real top-level entry. That is what makes it a repo path rather than a quoted regex that happens to contain a slash, and it is exactly the shape that failed: `packages/` exists, `packages/workers/` does not.
        head = rel.split("/", 1)[0]
        if not head or not os.path.exists(os.path.join(root, head)):
            continue
        if not os.path.exists(os.path.join(root, rel)):
            return False, "it names %s, which does not exist in this repo" % rel

    return True, ""


V_REASON = (
    "SWEEP THE CLASS, NOT THE INSTANCE (a DRY check). A fix landed and the message "
    "shows only its own instance fixed. Class: %s. No evidence that other copies of "
    "the changed logic were searched for%s."
)
V_ASSERTED = " (the sweep is asserted, but no gate, no scan count and no explicit search is quoted)"

V_ACTION = (
    "Run: %s -- other copies of the CHANGED code? Consolidate into one home or fix each; "
    "say the COUNT, or that none exist."
)
# R.3 of agent/plans/PLAN-stop-hook-retro-20260924.md: the demand stays, only the command is replaced.
V_ACTION_UNGROUNDED = (
    "The judge's search does not match the fix's own changed lines; name a search that finds "
    "the fixed instance, then count its siblings."
)
V_ACTION_NOSEARCH = (
    "Grep for siblings of the CHANGED code (its function, constant or pattern): consolidate "
    "copies into one home or fix each, say the COUNT, or that none exist. %s"
)
# Kept SHORT on purpose: wl_rules.apply_order caps next_action at 200 characters, and the first draft of this string put the reason last, where the cap ate it -- the session was handed a sentence that stopped mid-word. The WHY leads, and the rejected command is deliberately NOT echoed: it is the one thing that must not be run, and quoting it is what blew the budget.
V_ACTION_DROPPED = (
    "Command DROPPED: %(why)s. Grep for copies of the changed code yourself; "
    "consolidate or fix each, say the COUNT or none."
)


def enforce(out, payload, fixset_files=None, displaced=None, instance=None):
    """Write the sweep order into a judge verdict, in place. Returns the note.

    `instance` is `(root, commit ids)` for a commit-based fix-set, or None. When given, a runnable search whose pattern matches none of the fix's own changed lines is replaced by V_ACTION_UNGROUNDED (`search_hits_instance`); the demand itself is unchanged.

    `search` IS MODEL PROSE TOO, and `validate_search` was never asked to know that: it checks whether a string PARSES as a read-only shell command, not whether its English happens to name a reserved act. "commit the reflow now" carries no `git` token and no verb `_DESTRUCTIVE` recognises, so it validated as `ok` and would have reached the session as `Run: commit the reflow now`,
    the exact second-door shape the comment two lines below was written about for `instruction` and left open here. Found by this module's own sibling, `wl_proofcheck`, planting the identical case against an `instruction` field and noticing `search` had never been asked the same question.

    `fixset_files` checks the TRIGGERING FIX's own claim (`defect_class`), never `locus`/`search`: those legitimately point OUTSIDE the touched files by design (that is the entire point of a sweep), so grounding them against the fix-set would flag every real sweep as ungrounded. Annotates `reason` only, mirroring `wl_proofcheck.enforce` exactly (see
    agent/plans/PLAN-judge-prompt-trap-conflation.md).

    `displaced` is the demand THIS fire is about to bump into the marker's `owed` slot (see wl_rules.Demand.displace), or None when there is nothing to carry. Its class and search were already validated when that demand first fired, so the STILL OWED sentence appended here re-emits only that already-checked text, never anything fresh from the model.
    """
    reason = V_REASON % (payload["defect_class"], V_ASSERTED if payload["asserted"] else "")
    if isinstance(displaced, dict) and displaced.get("defect_class"):
        reason += wl_rules.still_owed_sentence(
            displaced["defect_class"],
            "run %s" % (displaced.get("search") or "(no search recorded)"),
        )
    if not wl_rules.scope_grounded(payload.get("defect_class", ""), fixset_files):
        reason += (
            " UNVERIFIED: git's own file list for this fix-set does not match '%s' -- if that "
            "defect is not real, name the actual commit or files it fixed, or say plainly none "
            "occurred." % (payload.get("defect_class") or "")[:80]
        )
    ok, why = validate_search(payload["search"])
    search_reserved = wl_rules.names_operator_reserved(payload["search"]) if ok else ""
    search_verb = names_destructive(payload["search"]) if ok else ""
    if ok and search_reserved:
        action = V_ACTION_DROPPED % {
            "why": "it names `%s`, which needs the operator's ask" % search_reserved
        }
    elif ok and search_verb:
        action = V_ACTION_DROPPED % {"why": "it names `%s`, and a sweep only reads" % search_verb}
    elif ok and instance and search_hits_instance(payload["search"], *instance) is False:
        action = V_ACTION_UNGROUNDED
    elif ok:
        action = V_ACTION % payload["search"]
    elif payload["search"]:
        action = V_ACTION_DROPPED % {"why": why[:70]}
    else:
        verb = names_destructive(payload["instruction"])
        # THE SAME SECOND DOOR, for the standing order rather than for safety. `instruction` is model prose reaching the session verbatim, so it can carry "commit the fix" as easily as "git clean" -- and this repo's first standing order reserves committing, branching, pushing and opening a PR to an explicit operator ask. wl_bravedefault emitted exactly that on 2026-09-02 and the
        # session quietly disobeyed it; the fix belongs on every path that hands model text to a session, not only the one that was seen.
        reserved = wl_rules.names_operator_reserved(payload["instruction"])
        if verb:
            action = V_ACTION_DROPPED % {
                "why": "its instruction named `%s`, and a sweep only reads" % verb
            }
        elif reserved:
            action = V_ACTION_DROPPED % {
                "why": "its instruction named `%s`, which needs the operator's ask" % reserved
            }
        else:
            action = V_ACTION_NOSEARCH % payload["instruction"]
    wl_rules.apply_order(out, reason, action)
    return "class-sweep: %s" % payload["defect_class"][:160]


# -- The outstanding-demand marker -----------------------------------------
#
# WHY A MARKER AT ALL. The fix signal is de-duplicated per fix-set by wl_reggate and a settled fix-set is never re-asked, so without this the demand is strictly one-shot: a session could stop again with no new commits and never be asked whether it did the sweep. The marker carries the question forward onto the next judged stop. Its bounds -- and why they are hard -- are in
# wl_rules.
#
# WHY A FRESH FIRE DOES NOT DESTROY THE OLD DEMAND ANY MORE (agent/plans/PLAN-sweep-obligation-carry-forward.md). A NEW fix-set's class always wins the PROMPT -- asking about the old class instead would drop the new one, which is worse -- but the marker itself no longer treats "a different question was asked" as "nothing is owed". `wl_judge.run_judge` loads this demand unconditionally now and tells `apply_verdict` which question was asked (`asked="fresh"` or `"followup"`); a fresh fire DISPLACES the current head into the marker's one `owed` slot instead of overwriting it, and a fresh silent/degraded answer leaves both head and owed untouched, since a verdict about a DIFFERENT fix-set says nothing about whether THIS class was swept.

SWEEP_TTL_MIN = int(os.environ.get("WORKLIST_SWEEP_TTL_MIN", "120"))
SWEEP_MAX_FIRES = int(os.environ.get("WORKLIST_SWEEP_MAX_FIRES", "2"))

SWEEP_DEMAND = wl_rules.Demand("classsweep", SWEEP_TTL_MIN, SWEEP_MAX_FIRES)

# Three named wrappers, not four. A `marker_path` wrapper stood here after the refactor onto wl_rules.Demand with nothing left calling it, and case 143's dead-code gate named it on the first full run -- SWEEP_DEMAND.path() is the one spelling. Do not add a pass-through here unless something calls it.


def load_outstanding(path=None):
    return SWEEP_DEMAND.load(path)


def save_outstanding(payload, prior=None, path=None):
    SWEEP_DEMAND.bank(
        {"defect_class": payload["defect_class"], "search": payload["search"]}, prior, path
    )


def clear_outstanding(path=None):
    SWEEP_DEMAND.clear(path)


def apply_verdict(out, outstanding=None, path=None, fixset_files=None, asked=None, instance=None):
    """(kind, note). Mutates `out` when the rule fires; owns the marker lifecycle.

    kind is 'fire', 'silent' or 'degraded'. A verdict discharges only the question it was actually asked (agent/plans/PLAN-sweep-obligation-carry-forward.md): `asked` is `"fresh"` on a stop that asked SWEEP_PROMPT about a NEW fix-set, `"followup"` on a stop that asked FOLLOWUP_PROMPT about `outstanding` itself, and `None` (the default) reproduces the byte-identical legacy behaviour for any caller that has not adopted the parameter -- fire always banks over `outstanding`, silent/degraded always clears it.

    On `asked="fresh"`: a fire DISPLACES `outstanding` into the marker's `owed` slot rather than overwriting it (the new class still wins the prompt and the verdict), and a silent or degraded answer leaves `outstanding` and its `owed` slot completely untouched -- an answer about a DIFFERENT fix-set says nothing about whether THIS class was swept.

    On `asked="followup"`: a fire is a re-fire of the SAME `outstanding` head, banked as before; a silent or degraded answer discharges the head and promotes a live `owed` record to take its place, since the question just answered was actually about `outstanding`.

    `fixset_files` defaults to `None`, so every existing call site that does not know about it behaves byte-identically to before this parameter existed (see `wl_rules.scope_grounded`).

    `instance` (see `enforce`) is honoured on a FRESH ask only: a follow-up's search is about an older fix-set, not about these commits.
    """
    kind, payload = read_verdict(out)
    if kind == "fire":
        if asked == "fresh":
            note = enforce(out, payload, fixset_files, displaced=outstanding, instance=instance)
            SWEEP_DEMAND.displace(
                {"defect_class": payload["defect_class"], "search": payload["search"]},
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
        SWEEP_DEMAND.promote(path)
    else:
        clear_outstanding(path)
    return kind, payload if isinstance(payload, str) else ""
