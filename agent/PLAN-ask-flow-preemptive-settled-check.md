# PLAN: Ask-flow preemptive settled-check
Status: draft (v2 -- Part 1 redesigned around a model call, 2026-08-30)
Owner: 9d92d9b6
Updated: 2026-08-30

Scope: the AskUserQuestion path only. Not the Stop-hook judge, not PR #579, not
the k3s bump.

## The measurement

Two AskUserQuestion calls were refused live on 2026-08-28 and 2026-08-30 by
.claude/hooks/pre-ask/block-settled-questions.sh. Both rows are in
/tmp/claude-worklist/home_developer_console.md.ask-refusals.jsonl. Both are
FALSE POSITIVES:

  1. "...unfixable by editing any file in this diff. How should I get past the
     local push gate?"            perm="should i"  obj="push"
     A how-question about a gate. The governing `how` sits BEFORE the
     permission phrase, and the clause anchor (lines 101-114) only inspects the
     span BETWEEN permission and object.

  2. "...orthogonal to PR #579's actual CI work. Should I implement it now?"
                                  perm="should i"  obj=" pr "
     The object is a PR NUMBER in a different sentence. Refused by the
     fallthrough at lines 110-113, whose own comment concedes it is a guess:
     "The object sits BEFORE the permission phrase. Left refusing,
     deliberately."

The operator's stated worry was wasted effort on a settled question. The
measurement says something worse: the guard ate two legitimate questions, and
the only reason that is known is that a human was watching. In the unattended
run the worry is about, both would have vanished into a JSONL nobody reads.

Three asks CLAUDE.md MANDATES are also refused as naturally phrased:

  CLAUDE.md:7   worktree ask     "...for this branch yet. Should I create one?"
  CLAUDE.md:27  second-PR ask    "Should we open a second PR for X?"
  CLAUDE.md:81  packaging ask    "Should we ride the current PR, or ...?"

## Why v1's repairs were the wrong fix

v1 of this plan proposed two anchoring repairs (a wh-word lookbehind, and a
boundary test for object-before-permission). The operator's direction: "regex is
dead. let's use haiku for deciding for such cases."

That is the same conclusion .claude/hooks/pre-bash/lib/command-scan.sh reached
about flag shapes -- "a single regex chasing flag shapes is a losing game...
there will always be another shape" -- and wl_admit.py:57-64 reached about
admission prose: "A regex-only detector swallows exactly the class most worth
catching, so the regex is a COST FILTER and never the last word on a negative."

But the decisive argument is narrower than "regexes are brittle. It is that the
distinction this hook must draw IS NOT ENCODABLE IN PHRASE SHAPE AT ALL, because
CLAUDE.md both settles some git-workflow questions and MANDATES others, in the
same vocabulary:

  SETTLES (refuse the ask)                 MANDATES the ask (must pass)
  ----------------------------------       ---------------------------------
  :16 Session default 1 -- uncommitted     :7  worktree ask -- "if a new task
      tree; no commit, branch, push or         starts and no worktree exists
      PR unless the operator asks              yet for its branch, ASK the
                                               operator first (AskUserQuestion)"
  :75 "Ask for the big-bang, not for       :27 second-PR ask -- "A genuinely
      permission to patch one thing"           independent second PR is the
                                               operator's call; ask"
                                           :81 packaging ask -- "The ask decides
                                               PACKAGING (one comprehensive
                                               change versus riding the current
                                               PR)"

Both columns contain `commit`, `branch`, `PR`. Repairs A and B would have moved
the boundary; they could not have drawn this one. A reader of both columns can.

## What the hook is today

Pure regex. jq pulls .tool_input.question / .questions[].question /
.questions[].header, lowercases and joins, then two `grep -oE` hits plus a
clause anchor. Milliseconds, no model call. It reads ONLY question and header --
option labels and their consequence descriptions are never examined.

That last fact fixes the ordering for free: the question line is the cheap part
to draft and the only part the matcher sees. A pre-check placed after the
question line and before the option set costs nothing and protects everything
expensive.

## Design

Three parts, in dependency order. Part 1 is the highest-value half and stands
alone; parts 2 and 3 depend on it.

### Part 1 -- replace the matcher with a Haiku classifier

#### 1a. The transport is not invented; it already exists

REUSE wl_judge._run_structured (.claude/hooks/stop/wl_judge.py:359), whose own
docstring is the mandate: "the next module that needs a model call should use
this and the three copies should follow when something else forces them open."

Its invocation, wl_judge.py:386-407, verbatim:

    claude -p <prompt> --output-format json --json-schema <json> \
           --model claude-haiku-4-5-20251001 --max-budget-usd 0.25

  capture_output=True, text=True, timeout=JUDGE_TIMEOUT_S, check=False,
  env={..., "STOPHOOK_CHILD": "1"}, cwd=$TMPDIR/claude-worklist/.judge,
  stdin=subprocess.DEVNULL

What comes free with it, and would have to be rebuilt by anything else:

  BINARY      resolve_claude (:556) -- PATH, then ~/.local/bin/claude.
  AUTH        NONE TO MANAGE. `grep -rn ANTHROPIC_API_KEY .claude/` returns
              nothing; the child inherits the operator's logged-in CLI
              credentials. No key to provision, rotate, or leak into a hook.
  MODEL       JUDGE_MODEL (:23), env-overridable via WORKLIST_JUDGE_MODEL.
  COST        _envelope_bits (:208-243) reads total_cost_usd, subtype,
              api_error_status, stop_reason and num_turns from the envelope and
              warns at 90% of budget.
  FAILURE     every path returns (None, error_string): TimeoutExpired (:408),
              OSError (:410), non-zero exit via _explain_failed_exit -- which
              reads the envelope from STDOUT because the CLI writes errors there
              (:247-274) -- is_error with api_error_status (where a 429 lands),
              unparseable stdout, and null/invalid structured_output.
  RECURSION   STOPHOOK_CHILD=1; worklist.py:926 no-ops the Stop hook on it.
  CWD         the isolated .judge workdir is a 5x COST decision, not tidiness:
              wl_judge.py:29-33 measured the same trivial prompt at $0.1025 in a
              project cwd versus $0.0205 in the isolated one.

ONE EDIT OUTSIDE THE ASK PATH, and it is the minimum: _run_structured hardcodes
JUDGE_TIMEOUT_S (240) and JUDGE_BUDGET_USD (0.25). 240 seconds is catastrophic
in a PreToolUse hook that blocks an interactive tool. Add two DEFAULTED keyword
arguments, `timeout_s=None, budget_usd=None`, falling back to today's constants.
Behaviour for the existing caller (run_planfid) is bit-identical, and a control
in the new test file asserts that.

  REJECTED ALTERNATIVE: pre-setting WORKLIST_JUDGE_TIMEOUT_S in os.environ
  before importing wl_judge. It works -- the constants are read at import -- and
  it is spooky action at a distance that the next reader would have to
  reverse-engineer. A defaulted kwarg is honest and testable.

#### 1b. NEW: .claude/hooks/pre-ask/settled_judge.py

Placement is forced by two gates, and .py is forced by one of them:

  * test-hooks.sh:94-100 (hook_files) finds every *.sh under pre-ask/ except
    lib/*, and its `test-` exclusion only strips ROOT-level paths -- so a
    `pre-ask/test-*.sh` would be reported UNWIRED. A .py file is invisible to it.
  * check-hook-integrity.sh:121-133 counts a `test-<stem>.py|.sh` beside a
    `block-*.sh` guard as covering BOTH directions.

The module does four things and nothing else:

  prefilter(text) -> [(name, span)]
      OBJECT-ONLY and RECALL-FIRST. `commit | branch | push | pull request |
      open a pr | [^a-z]pr[^a-z] | merge | worktree | rebase | tag | release`.
      Its ONLY sanctioned effect is not spending a model call (the wl_admit.py
      Tier-R rule). THE PERMISSION REGEX IS DELETED OUTRIGHT: it is the direct
      cause of both live false positives, and shape is precisely what the model
      is here to stop guessing at.

  verdict(question) -> (dict, None) | (None, err)
      Builds the prompt (1c), calls _run_structured with label "settled",
      PREASK_TIMEOUT_S and PREASK_BUDGET_USD, and an extract() that returns the
      payload only when `settled` is a bool and `rule` is in the enum.

  settled(question) -> (bool, rule, reason, err)
      True ONLY on settled==true AND rule != "none". A `settled: true` with
      rule "none" is incoherent and passes: belt and braces on the one path
      that suppresses a question.

  __main__
      Reads argv or stdin, prints `SETTLED <rule> <reason>` / `PASSES` /
      `UNEXAMINED <err>`, exits 2 / 0 / 0. This is the mode /ask calls.

Kill switches, all of which exit 0 without a call:
  PREASK_SETTLED_JUDGE=off  (mirrors WORKLIST_JUDGE=off, wl_judge.py:44)
  GITHUB_ACTIONS=true       (mirrors worklist.py:1601)
  STOPHOOK_CHILD or PREASK_CHILD set

#### 1c. The prompt and the schema

DO NOT SEND THE WHOLE CLAUDE.md. Measured: 49,477 bytes, 741 lines, ~12.4k
tokens -- about $0.012 of padding per call at Haiku 4.5's $1.00/MTok input,
before the CLI's own wrapper. It is also pointless: the child runs in the
isolated .judge workdir and never loads the project CLAUDE.md anyway.

Send a ~40-line excerpt carrying BOTH columns of the table above. Define it ONCE
as SETTLED_RULES in settled_judge.py, and have the refusal message render from
the same constant, so the rule the model judged against and the rule the
operator is shown can never drift.

    PREASK_PROMPT = """\
    You are a gate on ONE question a coding session is about to put to its
    operator. Decide ONE thing: does the operator's own CLAUDE.md ALREADY
    settle this question, so that asking it only spends a round trip repeating
    a rule they have written down?

    THE RULES THAT SETTLE A QUESTION:

      session-default-1: "The default deliverable is an uncommitted working
      tree. Do not git commit, create a branch, push, or open a PR unless the
      operator asks for it in that task. Approving a plan is not approval to
      commit."

      findings-big-bang: "Ask for the big-bang, not for permission to patch one
      thing... when findings cluster, do not ask about them one at a time and do
      not propose the minimal patch: put the whole cluster into a single plan
      and ask to run it."

    THE SAME DOCUMENT MANDATES THESE ASKS. They use the same words and they are
    NOT settled. If the question is one of these, answer settled=false:

      * whether to create a WORKTREE for a new task's branch. CLAUDE.md: "if a
        new task starts and no worktree exists yet for its branch, ASK the
        operator first (AskUserQuestion)... Do not decide either way on your own."
      * whether a SECOND PR is warranted. CLAUDE.md: "A genuinely independent
        second PR is the operator's call; ask, and say why the work cannot ride
        the open one."
      * PACKAGING: one comprehensive change versus riding the current PR.
        CLAUDE.md: "The ask decides PACKAGING... never WHETHER the findings get
        fixed."

    ALSO answer settled=false for:
      * a DESIGN question that happens to mention branching, merging or PRs
        ("Which branching strategy fits this repo?")
      * a FACTUAL question about git state ("Did the rebase drop a commit?")
      * a question ABOUT one of the rules rather than an instance of breaking it
        ("Should I explain in the report why we never commit unasked?")
      * a HOW question about a mechanism ("How do I get past the local push
        gate?")
      * anything where you are not confident. Passing a settled question costs
        one round trip. Blocking a legitimate one costs a question the operator
        never learns was asked, which is strictly worse.

    The question:
    <<<
    %(question)s
    >>>

    Set `rule` to the rule that settles it, or "none". Write `reason` as ONE
    sentence addressed to the session, naming the fact that decided it. Never
    use em dashes.
    """

    PREASK_SCHEMA = {
        "type": "object",
        "properties": {
            "settled": {"type": "boolean"},
            "rule": {"type": "string",
                     "enum": ["session-default-1", "findings-big-bang", "none"]},
            "reason": {"type": "string", "maxLength": 200},
        },
        "required": ["settled", "rule", "reason"],
        "additionalProperties": False,
    }

`rule` is an ENUM, not free text, for the reason the ledger exists: a wrong
model verdict must be auditable by grouping, not by reading prose.

#### 1d. EDIT: .claude/hooks/pre-ask/block-settled-questions.sh

The shell keeps the jq extraction, the fail-open-without-jq branch (lines 62-65),
the ledger and the refusal message. It loses PERMISSION, OBJECT, CLAUSE and the
whole anchoring block, and gains one call:

    python3 "$(dirname "$0")/settled_judge.py" "$QUESTION"
      exit 2 -> refuse (stdout carries `SETTLED <rule> <reason>`)
      exit 0, "PASSES" -> pass
      exit 0, "UNEXAMINED <err>" -> pass, and say so on stderr

The header comment is rewritten around the two-column argument, not the
two-condition one. The refusal message gains the model's one-line `reason` above
the quoted rules, so a refusal stays as explainable as it is today and names
WHICH rule decided it.

#### 1e. FAIL OPEN, every path, no exceptions

The hook's own comment at lines 57-65 governs and extends unchanged: "it FAILS
OPEN ON PURPOSE, which is the opposite of the rule for the Stop gates next
door... blocking a legitimate question over a missing binary is the precise
failure the 'narrow on purpose' note above exists to prevent. So: pass the
question, and SAY that it went unexamined rather than pretending it was examined
and cleared."

Every one of these exits 0 and prints one line on stderr in exactly the shape of
lines 62-65:

    block-settled-questions: <cause>; this question passed UNEXAMINED
    (the hook did not run its check).

  jq missing (existing)              python3 missing
  stop/ modules unimportable         claude CLI not found
  timeout (PREASK_TIMEOUT_S)         child exited non-zero
  is_error / api_error_status (429)  unparseable stdout
  structured_output null or schema-invalid
  PREASK_SETTLED_JUDGE=off / GITHUB_ACTIONS / STOPHOOK_CHILD / PREASK_CHILD

Exit 2 requires an affirmative settled=true with a named rule. SILENCE NEVER
BLOCKS. This is the inverse of the Stop judge's "NO ESCAPE HATCH" rule, and
deliberately so: that judge guards an artifact, this one guards a QUESTION, and
wl_admit.py:39-46 already made the same inversion for the same reason.

#### 1f. Latency and cost

CORRECTING AN ASSUMPTION: this is not a sub-second call. wl_judge.py:36-40
measured it on this machine: "a bare `reply OK` answers in 3.9s, while the real
schema-constrained judge call took 30s... and had exceeded 120s minutes earlier
under heavier load." That is `claude -p` process startup, not the model. A raw
SDK call would be sub-second; this transport is not, and the transport is
non-negotiable (see 1a).

  prefilter miss (most asks)  ~5ms          $0
  prefilter hit, warm         2-6s          $0.02-0.06 (repo-measured range for
                                            a schema-constrained haiku call in
                                            the isolated workdir: $0.0205 for a
                                            trivial one, $0.0566 for a real one)
  hard cap                    12s -> open   PREASK_BUDGET_USD=0.10

  PREASK_TIMEOUT_S = 12   -- NOT the judge's 240. The judge's long budget exists
                             because it FAILS CLOSED and a timeout blocks a stop
                             (wl_judge.py:35-42). This one fails OPEN, so the
                             correct budget is the operator's patience, not the
                             worst case.
  PREASK_BUDGET_USD = 0.10 -- clear of the measured $0.0566, well under the
                             judge's $0.25.
  settings.json            -- add "timeout": 20 to this hook's entry. The file
                             already uses per-hook timeouts (lines 233, 244,
                             275, 302).

SANITY CHECK AGAINST WHAT ALREADY RUNS: the Stop judge fires on EVERY TURN at
$0.011-0.026 (wl_judge.py:24-25). AskUserQuestion calls are far rarer than
turns, and only prefilter hits pay anything at all. This is strictly cheaper
than machinery this repo already runs all day. The latency is also spent at the
one moment it costs least: the operator is about to be interrupted anyway.

#### 1g. The ledger, now Tier R

Keep it, and it matters MORE than it did: a wrong model verdict is harder to
eyeball-audit than a wrong regex match. Adopt wl_admit's two-tier shape
(wl_admit.py:49-53, 194-199): the row is written BEFORE the model call, "because
a hit recorded only after a successful verdict would vanish exactly when the
judge times out, which is when the record matters most."

Row gains: verdict ("settled"|"passed"|"unexamined"), rule, reason, model,
latency_ms, cost_usd, err. Loses: permission (that regex is gone).

TWO CONSEQUENT EDITS:

  * wl_admit.ask_refusals (wl_admit.py:586) counts EVERY row for the session.
    With pass/unexamined rows present it must count only
    `verdict in (absent, "settled")`, or the advisory inflates. Legacy rows have
    no verdict field, hence the absent case.
  * SKIP THE LEDGER WRITE WHEN session_id IS ABSENT. This closes v1's "Known
    residue": check_guard_mention_anchoring.py:319 and test-hooks.sh both drive
    the real hook with no session_id, so every CI run appends "session":"unknown"
    rows and the file the operator is told to read as "the denominator" is mostly
    test debris.

#### 1h. Tests: the offline half and the live half

This repo has already solved "how do you gate a model call" twice, and both
halves are copied rather than invented.

OFFLINE, deterministic, in `npm run ci`:

  NEW .claude/hooks/pre-ask/test-block-settled-questions.py
    The stem must match the guard exactly (check-hook-integrity.sh:121-133) and
    it must be .py, not .sh (test-hooks.sh:94-100 would call a .sh UNWIRED).

    The seam is the same one test-judge-schema.py:323-352 uses: "Replacing that
    ONE attribute exercises everything else for real -- prompt assembly, the
    schema built from the assembled prompt, the verdict flip, and the
    sanitiser that runs after it." Assign wl_judge.subprocess to a
    SimpleNamespace and wl_judge.resolve_claude to a stub, then assert:

      - prefilter fires on each object token, and is silent on "Which colour
        should the badge be?"
      - the prompt carries BOTH rule columns and the question verbatim
      - the schema reaches the child with the rule enum intact
      - settled=true + rule -> exit 2, and the reason reaches stderr
      - settled=false      -> exit 0
      - settled=true, rule="none" -> exit 0 (the incoherence guard)
      - TimeoutExpired    -> exit 0 and "UNEXAMINED" on stderr
      - is_error true     -> exit 0 and "UNEXAMINED"
      - returncode 1 with the envelope on STDOUT -> exit 0, and the reported
        cause names api_error_status (the wl_judge.py:247-274 lesson)
      - unparseable stdout, and structured_output null -> exit 0
      - a ledger row is written on the settled path AND on the timeout path
      - no ledger row when session_id is absent
      - _run_structured's defaults are unchanged when the new kwargs are omitted

  EDIT .claude/hooks/test-hooks.sh (pre-ask block, ~608-634)
    The suite must stay offline, so every case there runs with
    PREASK_SETTLED_JUDGE=off and asserts exit 0 plus the UNEXAMINED stderr line
    (via check_out). The six existing strings stay -- their meaning changes from
    "this must block" to "with the classifier off, NOTHING blocks and the hook
    says so", which is the fail-open contract and the property most worth a
    deterministic control. Block-direction coverage moves to the test-<stem>.py
    file, which check-hook-integrity counts as both directions.

LIVE, opt-in, costs money, never in CI:

  NEW .claude/hooks/pre-ask/calibrate-settled-judge.py --live
    Modeled on calibrate-judge-rules.py, whose header states the split: "Those
    controls pin the SEAM... They cannot answer the other half of the question
    -- does haiku, reading a real session message, actually recognise [it]? That
    needs the model, a network, and about two cents a case, which is exactly
    what a CI gate must not need." Same shape: refuses to run without --live,
    `--only <substring>` to re-run just the misses, scratch TMPDIR.

    repeat=3 by default, and the reason is measured, not stylistic --
    wl_admit.py:740-745: "two runs of the IDENTICAL prompt disagreed on 3 of 12
    cases. A single run therefore cannot tell a prompt improvement from noise."

    THE CORPUS (every case is real, from this repo's ledger, CLAUDE.md or the
    existing suite):

      must REFUSE (settled)
        "Should I commit this change?"                      session-default-1
        "Shall I open a PR for this?"                       session-default-1
        "Do you want me to create a branch first?"          session-default-1
        "Should I fix just this one call site first?"       findings-big-bang

      must PASS -- the two live false positives, verbatim from the ledger
        "...How should I get past the local push gate?"
        "...orthogonal to PR #579's actual CI work. Should I implement it now?"

      must PASS -- the three CLAUDE.md-mandated asks, naturally phrased
        "No worktree exists for this branch yet. Should I create one?"
        "Should we open a second PR for X?"
        "Should we ride the current PR, or cut a second one?"

      must PASS -- mention-vs-target and design/fact (today's suite, 622-634)
        "Should I explain in the report why we never commit unasked?"
        "Can we record that the commit rule is settled?"
        "Should I describe how the branch guard works?"
        "Which branching strategy should this repo use?"
        "Did the rebase drop a commit, or is the count right?"
        "Should I install node from a tarball or a package manager?"

    THE GATE IS ASYMMETRIC, mirroring wl_admit._corpus_selftest:783-790, with
    the polarity that matches THIS hook's fail-open design:

      any must-PASS case judged settled  -> FAIL outright. This is the failure
                                            the hook exists to prevent and it is
                                            invisible in production.
      a must-REFUSE case missed          -> reported as a rate, floored at 0.60.
                                            The cost is one redundant question.

    A fixture that flips is the rubric drifting, and "the fix is the PROMPT, not
    the fixture" (calibrate-judge-rules.py:19-20).

### Part 2 -- /ask self-checks before it drafts options

Conceptually unchanged from v1; the cost sentence is the revision.

EDIT: .claude/commands/ask.md

  Frontmatter allowed-tools gains:
      Bash(.claude/hooks/pre-ask/settled_judge.py:*)

  New step between the current 2 and 3, so the check lands after the question
  line exists and before any option is written -- exactly the split the
  classifier's input already implies:

    ### 3. Pre-check each question line before drafting its options

    For each question you intend to ask, run:
        python3 .claude/hooks/pre-ask/settled_judge.py '<the question line>'

    SETTLED means block-settled-questions.sh will refuse it, so do not draft
    options for it. One of two things is true:
      - it really is settled: drop it, take the documented default, and note
        the default you took in the report.
      - it is a design or fact question wearing permission words: rewrite it as
        the noun-phrase question it actually is and re-run the check.

    UNEXAMINED means the classifier could not run. Ask the question. The gate
    will not block it either.

  COST HAS CHANGED and the file must say so. v1 said "cost is three greps. Run
  it on every question." That is now false: a prefilter hit costs 2-6s and
  ~$0.03. The instruction becomes: the script exits in milliseconds when the
  question has no git-workflow vocabulary at all, so running it on every
  question is still right -- but a question that DOES mention commits, branches
  or PRs will pause for a few seconds, and that pause is the check working.

  Also amend step 2's "Do not ask what ... already settles" to name the specific
  class and point at the check, so the prose and the mechanism agree.

### Part 3 -- close the announcement gap that made the operator type /ask

UNCHANGED from v1. Independent of the classifier.

The operator spent a turn saying "ask", which is precisely the cost
wl_admit.pending_ask (.claude/hooks/stop/wl_admit.py:557) exists to remove. It
did not fire. Likely cause: PENDING_ASK_CLOSING_LINES is 3 (:403), and a report
ending in a `## Remaining` table pushes the announcing line out of the
bare-question window; ASK_ANNOUNCEMENT_RE (:374) is deliberately short and may
not have matched.

Bounded action, NOT a redesign: recover this session's actual closing message
from the transcript, run wl_admit.ask_announcement over it, and record in this
plan which of the two rules missed and by how much. Only then decide whether the
window widens or the regex family gains one alternative. Widening on a guess is
how that gate acquires the same false-positive problem Part 1 is fixing -- and
its header already warns that a broader regex "matches the prose in this very
file".

## Explicitly not doing

- NOT repairing the regex. v1's Repairs A and B are withdrawn. They survive as
  calibration fixtures, which is the only part of them that was ever load-bearing.
- NOT sending CLAUDE.md. 49,477 bytes, ~12.4k tokens, ~$0.012 per call of
  padding, and the child's isolated cwd would not load it anyway.
- NOT a second transport. Nothing here talks to api.anthropic.com directly. One
  transport, one auth story, one place where a failure is explained.
- NOT touching run_judge, run_triage or run_admission. wl_judge's own comment on
  the second copy -- "the transport is the same and a second copy that drifts is
  a second bug" -- is exactly why the new caller uses _run_structured and the
  three live copies are left alone.
- NOT deleting the hook in favour of the /ask step. /ask is
  disable-model-invocation:true, so the model reaches AskUserQuestion by other
  paths (CLAUDE.md:7's worktree ask, handoff.md:17) that never see step 3.
- NOT touching the pre-bash gh/git guards, PR #579, or the k3s bump.

## Verification

  python3 .claude/hooks/pre-ask/test-block-settled-questions.py   # offline, stubbed
  bash .claude/hooks/test-hooks.sh                                # offline, fail-open
  bash .ci/scripts/quality/check-hook-integrity.sh                # inventory + coverage
  bash .ci/scripts/quality/check-python-lint.sh                   # both new .py files
  python3 .ci/scripts/quality/check_guard_mention_anchoring.py
  bash .claude/hooks/stop/worklist-cases/21-cadence.sh             # if part 3 lands

Live, by hand, before the change is called done and after any prompt edit:

  python3 .claude/hooks/pre-ask/calibrate-settled-judge.py --live

Manual smoke: run settled_judge.py over the two ledger rows and the three
CLAUDE.md-mandated asks; each must print PASSES. Over the four must-refuse
forms; each must print SETTLED with a named rule. With PREASK_SETTLED_JUDGE=off,
all nine must print UNEXAMINED and exit 0.

## Open questions

- Should a verdict be CACHED by question hash, as wl_judge caches stop verdicts
  (wl_judge.py:46-54)? Probably not: question text rarely repeats verbatim, and
  a cache is state that can go stale against a CLAUDE.md edit. Revisit only if
  the ledger shows repeated identical questions.
- Should the ledger record the raw envelope cost so per-session spend is
  answerable from the file? Cheap to add; deferred until there is a second
  month of rows to compare against.
