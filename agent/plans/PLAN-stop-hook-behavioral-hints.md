# PLAN: a rotating behavioral-hint line on the stop report
Status: draft
Owner: d778be9d
Updated: 2026-09-22

## 0. What already exists, and why this is not a duplicate of it

Three mechanisms in this tree are close enough that the boundary has to be drawn before anything is built, or the fourth one becomes a second copy of one of them.

`wl_agents.py` is the closest relative and the structural template: a deterministic, non-judged matcher over a corpus on disk, delivered through the advisory queue (`wl_checks.py:1441 agent_hint_queue`, queued at priority 3, called on the allow path only at `wl_checks.py:4837`), with a liveness gate (`.ci/scripts/quality/check_agent_hint_liveness.py`) rather than tests over its
internals. It answers "which specialist covers the topic in hand", which is a RELEVANCE question about this particular stop. The mechanism proposed here answers no question at all: it surfaces a standing rule that was already true before the session started, chosen at random. Relevance is what separates them, and it is why one needs a matcher and the other must not have one.

`docs/agent-reference/TRAPS.md` is the corpus whose shape is being copied. Its charter, stated in its own opening lines, is "ways a session gets *fooled* -- as opposed to ways it gets *blocked*", and "Mechanics of a specific subsystem do not belong here. ... This file is about judgement." The operator's two worked examples -- record an order with the worklist verbs, dispatch a
Haiku sub-agent for small work -- are neither. They are standing behavioral defaults already written in CLAUDE.md (`CLAUDE.md:53`, `CLAUDE.md:135`). Filing them in TRAPS.md would dilute a corpus whose value comes from every entry having cost a real incident. A second file with a distinct charter is the right answer, and the distinction is: TRAPS.md is what a session did not know;
HINTS.md is what a session knew and did not do.

`outq_add`/`outq_drain` (`wl_checks.py:1347`, `wl_checks.py:1414`) is the delivery machinery, and `agent/plans/PLAN-eliminate-worklist-report-per-stop-env.md` is redesigning its selection to release a fixed 3 sections per stop with randomized same-priority choice through an injectable `rng`. This plan reuses that plan's `rng` seam and its shown-ledger idea, and deliberately does
NOT use the queue itself. Section 3 gives the reason.

## 1. Where the corpus lives

`docs/agent-reference/HINTS.md`, Markdown, one `## ` entry per hint with a structured trailer, parsed by the hook.

Four facts decide this, none of them a preference.

`agent/README.md:36` already rules on the directory: "The standing lookup material -- TRAPS.md, ci-gates.md, suppressions.md -- lives in `docs/agent-reference/`, because it is reference prose that outlives every session, while everything under `agent/` is per-session state or a durable design record." A hint corpus is standing lookup material by definition. `agent/` is excluded by
the repo's own rule.

The machine-read objection against Markdown does not survive contact with the tree. `wl_store.py:428 trap_entries` already parses exactly this shape from inside the stop hook -- `## ` headings, a trailer block read only between the heading and the first blank line, fenced blocks excluded so a markdown example inside a body cannot become a phantom entry -- and `wl_store.py:283
agent_traps_path` already resolves the path from the hook. A second consumer of the same shape in the same directory is a parser the hook has written and debugged once already, including the fenced-block defect its docstring records.

`.ci/config/*.json` is the wrong precedent for this content. Those files are CI configuration and generated baselines (`.ci/config/python-env-registry.json` says "SHRINK-ONLY, AND GENERATED -- do not hand-edit" in its own header). A hint corpus is hand-curated prose that a human reads in a PR diff, and a reminder's single most important property is that it reads well. JSON string
escaping is where multi-clause English goes to become unreviewable.

The prose-style gate already covers the destination and will cover the corpus for free. `python3 .ci/scripts/quality/check_prose_style.py check docs/agent-reference/TRAPS.md` runs today and reports findings, so a hint written in second person is caught by an instrument that already exists rather than by a new one. That matters more here than anywhere else in this plan: the corpus
IS reminder text that future sessions read, so R1/R2 apply to the content and not only to this design document.

### 1.1 The entry schema

```
## <the hint itself, one imperative sentence, <= 160 chars>
Hint-Id: <stable-kebab-case>
Source: <pointer>[, <pointer>...]
Status: active | retired

<optional body paragraph: the incident or rule that paid for this hint, for the
human reader only. The hook never displays a body.>
```

The `## ` heading IS the displayed text, exactly as `wl_store.py:401 trap_headings` treats a trap title. This is deliberate and it is a constraint on authorship: a hint whose heading does not stand alone as a complete reminder is not a hint yet.

`Source:` uses the pointer grammar `wl_planrec.py:344 resolve` already implements -- `file:<path>[:<line>]` through the `fileline` kind, `gate:<npm id>`, `trap:<Trap-Id>`, `plan:<slug>`. Reusing that resolver rather than writing a fourth one means a hint that cites `CLAUDE.md:135` is proven to point at a real line by the same code the plan-record gate uses, and a hint whose
grounding gets deleted or renumbered goes red instead of quietly becoming folklore.

`Status:` exists so a retired hint can stay in the file with its history intact rather than being deleted. Only `active` entries are eligible for display. There is deliberately no `proposed` value; section 4 explains why.

A `Hint-Id` is never renumbered and never reused after retirement, matching `Trap-Id`'s rule at `docs/agent-reference/TRAPS.md:12`.

## 2. The delivery path: a bottom line, not a queue entry

The hint is appended to `parts` in `run_stop`'s allow block, AFTER the `outq_drain` call at `wl_checks.py:4844` and after the `N_OUTQ_MORE` tail, as the last element before the final `S.save_state`. It is one line. It never becomes a queue entry.

WHY NOT THE QUEUE, since the queue is where every other advisory goes. The queue exists to make a section DURABLE: `wl_checks.py:1309-1315`'s header records that its whole reason for being is that one-shot producers spend a budget before an emit path that exits the process, so "an entry that lands in the state doc the moment its producer spends that budget survives a block, a judge
block, a crash and a restart." A rotating reminder has the exact opposite property. It is idempotent, it loses nothing by being skipped, and it can be shown again tomorrow at zero cost. Putting it in the queue would buy durability nothing needs and pay for it twice: once by occupying one of the three per-stop slots that a real report section could have used, and once by inheriting
the shown-ledger, whose semantics are "suppress permanently" -- which is precisely wrong for a line that must rotate forever.

WHY IT NEVER CREATES OUTPUT. `wl_checks.py:4852` exits with zero bytes when `parts` is empty, and the comment on it records that this silence was won on purpose: "v18: nothing actionable, nothing queued, no judge line to show. This used to be impossible (the guide was unconditional) and is now the common shape of a clean stop." A tip that turned every silent stop into a line of
output would undo that deliberately, and would be the single most irritating possible shape for this feature. So the rule is absolute and belongs in the module header: the hint RIDES an output that was going to happen anyway, and the emptiness check at `:4851` runs before it, not after.

The accepted cost, stated rather than discovered later: a session whose every stop is clean and silent is never hinted. That is the same trade `agent_hint_queue`'s call site already takes and names at `wl_checks.py:4836` -- "the trade is that a session which never reaches a clean stop is never hinted, which is acceptable for exactly the same reason" -- inverted, and acceptable for
the mirror reason. A session with nothing to be told is a session that needs no reminders.

ALLOW PATH ONLY. A blocked stop already carries a demand, and adding a behavioral aside underneath a block is how the block gets skimmed.

### 2.1 Rendering

```
TIP (hint 4 of 12, rotating): Before calling a bug fixed, grep for its siblings; one bad call site usually has several.  [sweep-the-class -- CLAUDE.md:44]
```

The trailing id and source are not decoration. A hint that reads as wrong must be refutable in one second by opening the thing it cites, which is the same argument `wl_agents.py`'s `fold()` docstring makes for printing matched terms rather than stems: "a wrong hint is self-refuting in one second". The `N of M` counter is what makes the rotation legible as a rotation rather than as
a random nag, and it is what makes the vacuity test in section 6 able to observe progress.

The message constant goes in `worklist_messages.py` beside `N_AGENT_HINT` (`worklist_messages.py:1355`), named `N_BEHAVIOR_HINT`.

## 3. Selection: the rotation

State lives in the session's state doc under a new `hints` key, shaped like the existing `agent_hints` ledger at `wl_checks.py:1466`:

```
state_doc["hints"] = {"shown": {"<hint-id>": "<stamp>"}, "cycle": 0, "last": "<hint-id>"}
```

The algorithm, in one paragraph. Read the corpus from disk on every stop, take every `Status: active` entry, subtract the ids already in `shown`, and pick one uniformly at random from what remains using an injectable `rng`. When the remaining set is empty the cycle has completed: clear `shown`, increment `cycle`, and pick from the full set MINUS `last`, so a cycle boundary can
never produce a back-to-back repeat of the same hint. Record the pick in `shown` and in `last`, and save.

That is round-robin with randomized order inside each pass, which is what the operator asked for, and it terminates and repeats forever without a second clock.

### 3.1 What is shared with the per-stop-report plan, and what is not

`agent/plans/PLAN-eliminate-worklist-report-per-stop-env.md` section 2 adds an `rng` parameter to `outq_drain`, defaulting to `None` meaning the module-level `random`, and its section 8 drives that seam directly in-process with `random.Random(seed)` rather than trying to reach a subprocess's random state. Both halves are reused verbatim:

- The SEAM. `hint_pick(entries, ledger, rng=None)` takes the same optional `rng` with the same `None` -> module `random` default and the same in-process test style. There is deliberately no seed env var and no "deterministic mode" flag; the parameter is the whole mechanism, exactly as that plan decided.
- The LEDGER SHAPE. `shown` is a dict keyed by a stable id with a stamp value, the same shape `_outq`'s `shown` has at `wl_checks.py:1325`.

One helper is genuinely common and should be extracted rather than written twice: `pick_random(candidates, rng)`, a two-line wrapper that resolves `rng or random` and returns one element, which `outq_drain`'s tier-internal selection and `hint_pick` both call. Nothing larger is shared. `outq_drain` groups by priority tier and takes up to a budget; `hint_pick` has no tiers and takes
exactly one. Forcing those into one function would produce a parameterized abstraction with two callers and no third, which is the shape this repo's own `class_sweep` rubric names as consolidation pressure applied where there is no class.

THE ONE SEMANTIC DIFFERENCE, and it must be stated in the module header or somebody will "fix" it: `outq`'s `shown` ledger suppresses an item PERMANENTLY once surfaced, because re-showing a report section is noise. This ledger's `shown` suppresses only until the cycle completes, then resets. A reminder that stops after one pass is a reminder that expires exactly when the session
has been running long enough to have forgotten it.

SEQUENCING. This plan lands AFTER `PLAN-eliminate-worklist-report-per-stop-env.md`, because `pick_random` is extracted from the tier-selection code that plan writes. If this work has to start first, `hint_pick` carries its own `rng or random` resolution and the extraction becomes a task on the other plan instead; nothing else changes.

### 3.2 Cadence

One hint line per full allow-path stop that already has non-empty `parts`. No one-in-N throttle, no minute-based floor.

The counter-argument is in this tree and deserves an answer: `wl_checks.py:2047`'s `ALWAYS_FULL_MAX` comment warns that "a prompt that fires always is a prompt that gets skimmed", and `wl_classsweep.py`'s header says the same of its trigger boundary. Both are about a rule that DEMANDS something and asks the same question every time. Rotation is the difference: the line is one
sentence, it is different on every stop, and it costs nothing to skip. A time-based floor would add a clock nobody can observe from the output and would make the liveness test in section 6 depend on wall time.

The reversal is decided now so it does not get re-litigated from scratch later. If the operator reports the line as noise, the first lever is to STOP CYCLING: go silent after one full pass per session, rather than to add a timer or a probability. That keeps the rotation legible and makes the quiet deterministic.

## 4. The session-contribution path

A session proposes a hint with a new worklist verb:

```
worklist.py --hint-propose <me> <the hint, as one imperative sentence> [SOURCE: <pointer>]
```

which appends one JSON line to `agent/ledgers/hint-proposals.jsonl` -- `agent/README.md:23-24` already reserves `ledgers/` for "append-only measurement logs a gate writes and reads", and `wl_store.AGENT_RESERVED_DIRS` already reserves the name. The verb writes nothing else. Promotion into `docs/agent-reference/HINTS.md` is a hand edit to that file, reviewed in the PR diff like any
other tracked content.

The hook then surfaces the backlog through the queue it already has: one advisory section, key `hint-proposals`, priority 3, `refresh_min` matching `wl_agents.REFRESH_MIN` (720), naming the count of proposals whose text does not appear in the corpus and printing the exact promotion command. That advisory is a real queue entry, unlike the tip itself, because a proposal genuinely CAN
be lost and durability is the queue's whole purpose.

### 4.1 Why not `[?]`, which was the obvious candidate

The brief asked for this to be investigated against `agent/README.md` and CLAUDE.md's real deferral semantics rather than assumed. It fails on three counts, each of which is enough on its own.

THE DEFAULT EXECUTES. `CLAUDE.md:82` is explicit: "A `- [?]` must carry `DEFAULT:`, and the default EXECUTES. Autonomy is time-boxed, not indefinite: an unanswered deferral whose window closes becomes an order to do the default and tick it with evidence." A deferral is a mechanism for proceeding WITHOUT the operator after a window. The entire point of gating hint contributions is
that they may NOT go live without the operator, so a deferral either auto-promotes an unreviewed hint (defeating the gate) or auto-discards a real one (defeating the channel). There is no third default.

IT IS NOT A DECISION THE SESSION IS BLOCKED ON. The same paragraph continues: "Reserve `- [?]` for decisions that are genuinely the operator's: anything settleable from the code, the request, or a sensible default belongs to this session, and parking it as 'blocked on the operator' wastes a round trip. Thirty open deferrals is a symptom of over-asking." And `CLAUDE.md:87` restricts
`## Remaining` to "things that CANNOT be done right now". A hint proposal blocks nothing; the session's work proceeds untouched whether or not it is ever read. Routing it through `[?]` would industrialize exactly the over-asking that rule was written against, at a rate of one per session.

THE JUSTIFICATION GATE WOULD REJECT IT ANYWAY. `worklist.py:678` shows `--defer` validating `WHY:`/`HOW:` at creation (v12, from the operator's "Too many '[?]'. This is an escape hatch."), and the judge audits whether the WHY is true, reopening the item as `- [ ]` when it is not. A hint proposal has no honest WHY -- nothing is blocked.

`--ask operator` was the second candidate and is closer, but `wl_requests.py:112` records that an escalated ask "appends an `escalate` event plus a `- [?]` item ... carrying the ask's own DEFAULT:", so it lands in the same place by a longer road.

### 4.2 Why proposals never live in the corpus file

Keeping proposals in a separate ledger rather than as a `Status: proposed` entry in HINTS.md buys one specific property: the display path reads ONE file, and that file contains only approved text. A session cannot promote its own proposal by accident, by a bad parse, or by a future edit that flips a status field, because promotion is a write to a file the proposal verb cannot
touch. This is the same reasoning `wl_agents.py`'s header gives for refusing a cache -- "a cache is precisely what would let a DELETED agent keep being recommended" -- applied to the other direction.

What this does NOT buy, and the plan says so rather than implying otherwise: nothing mechanically prevents a session from editing `docs/agent-reference/HINTS.md` directly. The gate in section 6 asserts that every entry resolves its `Source:` pointer, which makes an ungrounded hint red, but the approval itself is a human reading a diff. Calling that "enforcement" would be the same
overclaim section 5 forbids.

## 5. Non-goals

Stated plainly, in the shape `wl_reggate.py` and `check_plan_citations.py` use, because the most likely way this feature goes wrong is that a later session mistakes it for an instrument.

THIS IS A REMINDER MECHANISM, NOT AN ENFORCEMENT MECHANISM. Nothing here blocks a stop, flips a judge verdict, or adds a violation key. A session that reads a displayed hint and ignores it has not violated anything the stop hook can detect, and the hook must never grow a check of the form "hint X was displayed and the session did not do X".

WHY THAT CHECK IS FORBIDDEN AND NOT MERELY UNBUILT. The evidence that a hint was FOLLOWED does not exist in any artifact the hook reads. "Did this session dispatch a Haiku sub-agent when it should have?" is answerable only from prose the session wrote about itself, and a check whose input is the subject's own account of its behavior is satisfied by writing the right sentence. That
is `check-cannot-fail` (`docs/agent-reference/TRAPS.md:48`) and `self-certifying-false-comfort` (`docs/agent-reference/TRAPS.md:1010`) in one object, and it would report coverage of the entire behavioral surface while proving nothing. Conflating "hint shown" with "instruction followed" is the exact failure TRAPS.md exists to warn about, and building it inside a feature whose stated
purpose is to surface TRAPS-style lessons would be an unusually complete own goal.

NOT A RELEVANCE MATCHER. Selection is random by specification. `wl_agents.py` already owns topic-matched advice, has a measured threshold calibration behind it, and has a liveness gate; a second scorer competing for the same surface would need its own calibration and would produce two systems disagreeing about what the session is doing.

NOT A RULE-MAKING SURFACE. Every hint must cite an existing rule, trap, or recorded incident through `Source:`. HINTS.md resurfaces rules that already exist; it never originates one. Without this, the corpus becomes a second CLAUDE.md that nobody reviewed and no gate checks, and the two will disagree.

NOT A TRAP CORPUS. TRAPS.md keeps its charter and its `check:ci-trap-registry` gate. If an entry describes a way a session gets FOOLED, it belongs there, and a hint may cite it with `trap:<id>`.

NOT A MODEL CALL. See section 6.2.

NOT A BLOCKER ON ITS OWN FAILURE. An unreadable, missing, or malformed corpus degrades to silence plus one queued note, never an exception and never a block, matching `wl_agents.py`'s returned-errors contract and `agent_hint_queue`'s `agent-corpus-err` section at `wl_checks.py:1453`. The call site is wrapped in the same `contextlib.suppress(Exception)` the agent hint already uses
at `wl_checks.py:4836`.

## 6. The module

`.claude/hooks/stop/wl_hints.py`, roughly 150 lines, no model call.

### 6.1 Surface

```
HINTS_REL = "docs/agent-reference/HINTS.md"
hints_path()                      -> pathlib.Path, WORKLIST_HINTS_FILE seam first
load_corpus(path)                 -> ([entry, ...], [error, ...])   never raises
hint_pick(entries, ledger, rng=None) -> (entry, index, total) or None
render(entry, index, total)       -> one line, via M.N_BEHAVIOR_HINT
```

`load_corpus` returns errors rather than raising, for the reason `wl_agents.py`'s header gives: "this module is consulted on the path that ends every turn in every session, so an exception here is a session that cannot stop."

One new environment name, `WORKLIST_HINTS_FILE`, `kind: path`, `defaults: ["NONE"]` -- a byte-for-byte copy of `WORKLIST_AGENTS_DIR`'s registry entry, and for the same reason: the CI gate and the test suite must be able to point the reader at a fixture corpus. There is deliberately NO on/off flag. `WORKLIST_AGENT_HINT` has one, but silence here is better produced by pointing
`WORKLIST_HINTS_FILE` at an empty corpus, which proves the corpus drives the output; a flag would prove only that the flag works. Both `.ci/policy/worklist-env-registry.json` and `.ci/config/env-manifest.json` need the one new name, and `scripts/data/doc-registry.md` regenerates from the manifest.

### 6.2 No JUDGE call, and the justification

The sibling advisory modules the brief names -- `wl_classsweep.py`, `wl_shapedup.py`, `wl_bravedefault.py` -- share a template because they share a job: each produces a VERDICT about how this particular session behaved, which cannot be computed from any artifact and therefore needs a model reading the transcript. Each one accordingly carries a marker constant, a JSON schema, a
rubric prompt, and an `apply_verdict` that never fails closed.

This module produces no verdict. It reads a file, excludes the ids in a ledger, and picks one at random. There is nothing for a model to decide, and the one thing a model COULD decide here -- which hint is most relevant right now -- is explicitly ruled out by section 5 and by the operator's own specification of randomness.

The cost side is already measured in this tree and points the same way. `wl_agents.py`'s header cites `wl_judge.py:20-39` for what a second paid call costs on the stop path: "4.9-20.0s, and one live timeout that BLOCKED a stop". Spending that to choose between twelve fixed sentences would be indefensible.

So: marker, schema, prompt and `apply_verdict` are all absent, and the module header states why in those terms, so the next reader does not "restore consistency" with its siblings by adding them.

### 6.3 The gate: `.ci/scripts/quality/check_hint_corpus.py`

Registered as `check:ci-hint-corpus`, modelled directly on `check_agent_hint_liveness.py`, whose header already states the governing principle: "A healthy matcher on a quiet stop emits nothing, exactly like a broken one. Counting hints cannot separate them."

Assertions:

- H1 POPULATION FLOOR. At least `MIN_HINTS` (8) active entries. An emptied, truncated or relocated corpus reds instead of passing vacuously. Same shape as `trap_registry`'s F1 and `check_plan_boxes.py:211 vacuity_problems` (G-A6).
- H2 IDENTITY. Every entry carries a `Hint-Id` matching `^[a-z0-9][a-z0-9-]{2,48}$`; ids are unique.
- H3 GROUNDING. Every entry carries at least one `Source:` pointer, and every pointer RESOLVES through `wl_planrec.resolve`. A hint whose citation has been deleted or renumbered is folklore and reds here.
- H4 SHAPE. Every `## ` heading is <= 160 chars, is a complete sentence on its own, and carries no second-person or first-person pronoun. The prose-style gate covers the file for the general case; H4 is the heading-specific floor.
- H5 IT ACTUALLY FIRES. Drive `wl_hints.hint_pick` against the REAL corpus with a fresh ledger for `len(active)` consecutive picks and assert: every pick is non-None, every id is distinct, and the set of picked ids EQUALS the set of active ids.
  This is the vacuity control the brief demands, and it is the same two-sided construction `check_agent_hint_liveness.py` uses: a mechanism that never fires and one that fires the same thing every time both fail it.
- H6 THE CYCLE REPEATS. One more pick after exhaustion returns non-None with a reset ledger, and its id is not the previous pick.
- H7 CONTROL-FIRST. Before any verdict on the real corpus, run every assertion above against a mktemp fixture with planted defects -- a corpus below the floor, a duplicate id, a `Source:` pointing at a deleted file, a `hint_pick` stubbed to return a constant -- and require each to red with its matching message.
  If any planted defect passes, exit non-zero WITHOUT judging the real corpus.

Three-point wiring per this repo's convention: the `---- gate ----` block in the script header, `package.json` scripts, and `scripts/ci-runner/manifest.ts`. `scripts/gates/check-ci-parity.ts` enforces that the three agree.

## 7. The starter corpus

Twelve entries. Every one restates a rule or incident already written down in this repo; none is invented for this plan, which is the `Source:` column's whole purpose. Headings are given as they would appear; bodies are omitted here and written when the file is authored.

| Hint-Id | Heading (the displayed line) | Source |
|---|---|---|
| `record-the-order` | An order given in conversation is not tracked until it is in the store; `worklist.py --add <me> <text>` is what survives a restart and a compaction. | `file:CLAUDE.md:53`, `file:CLAUDE.md:55` |
| `haiku-for-derived-work` | Derived, mechanical work with a pre-existing oracle and a loud failure goes to a Haiku sub-agent, not inline. | `file:CLAUDE.md:135`, `file:docs/agent-reference/model-routing.md` |
| `investigate-with-fan-out` | A question that means sweeping several files or packages goes to read-only Explore agents, several at once, asking for `file:line` evidence rather than file dumps. | `file:CLAUDE.md:126` |
| `sweep-the-class` | Before calling a bug fixed, grep for its siblings; one bad call site usually has several. | `file:CLAUDE.md:44`, `file:.claude/hooks/stop/wl_classsweep.py` |
| `control-before-green` | A clean result is not evidence until the check has been made to go red on known-bad input through the same path. | `trap:check-cannot-fail` |
| `probe-the-impossible` | "Cannot be done here" is a claim; run the command that would refute it before making it. | `file:CLAUDE.md:119` |
| `read-the-history` | The commit log is evidence, and it is the evidence nobody reads; `git log` on the file in hand usually answers the question already. | `trap:read-the-history-before-you-guess` |
| `stderr-separately` | Read stdout and stderr separately, and never `2>/dev/null`; a swallowed stream is where the answer was. | `trap:read-stdout-and-stderr-separately` |
| `search-before-creating` | Before creating a new file, gate, doc or provider, search the tree for one that already exists under another name. | `file:CLAUDE.md:161` |
| `check-the-artifact` | A sub-agent's report is accurate about intent and quietly wrong about placement; check the artifact, not the summary of it. | `file:CLAUDE.md:133`, `trap:ruling-from-an-artifact-is-a-hypothesis` |
| `remaining-is-not-a-todo` | `## Remaining` lists what CANNOT be done right now; "blocked on: nothing" is a confession that the turn ended with work in hand. | `file:CLAUDE.md:87` |
| `propose-a-hint` | A lesson this session paid for that is not in this corpus can be proposed with `worklist.py --hint-propose <me> <text...>`. | `file:docs/agent-reference/HINTS.md` |

`propose-a-hint` is the operator's third example rendered literally: the invitation to contribute is itself a rotating hint, which is the only way it reaches a session at the moment the lesson is fresh. It is also the sole advertisement of the section 4 channel, so removing it silently kills that channel -- worth a note in its body.

Two more are grounded and held back only to keep the first cut at twelve: `one-open-pr` (`file:CLAUDE.md:19`, and the night that produced four stacked PRs) and `defer-carries-a-default` (`file:CLAUDE.md:82`). They are the first two candidates when the corpus next grows.

## 8. Risks

- A twelve-entry corpus cycles quickly in a long session. The `N of M` counter makes that visible rather than confusing, and the cycle reset at section 3 is the documented lever if it reads as repetitive.
- `Source:` pointers using `fileline` decay whenever CLAUDE.md is edited above the cited line. H3 turns that into a red rather than into silent folklore, but it also means editing CLAUDE.md can red this gate for an unrelated reason. That is the same cost `check:ci-plan-citations` already carries in this tree and the same remedy applies: repoint the citation.
  Prefer a section-anchor-free `file:CLAUDE.md` pointer where the rule is unlikely to move, and a `:line` only where the exact site is the grounding.
- The hint line lands beneath the `N_OUTQ_MORE` tail, so a reader skimming for "what is left" sees the tip after the count. Verified against the current emit order at `wl_checks.py:4844-4847`; if that reads badly in practice, the fix is ordering inside `parts`, not a new channel.
- `pick_random` is extracted from work that has not landed yet. Section 3.1 names the fallback so this plan cannot be blocked by that one.

## Tasks

- [ ] Write `docs/agent-reference/HINTS.md` with the section 1.1 schema, a header stating the TRAPS.md boundary, and the twelve section 7 entries.
- [ ] Add `.claude/hooks/stop/wl_hints.py`: `HINTS_REL`, `hints_path()` with the `WORKLIST_HINTS_FILE` seam, `load_corpus` returning `(entries, errors)` and never raising, `hint_pick(entries, ledger, rng=None)`, and `render`.
- [ ] State in the module header that there is no judge call, no marker, no schema and no `apply_verdict`, with the section 6.2 reasons, so the absence is not read as an omission.
- [ ] Extract `pick_random(candidates, rng)` and make `outq_drain`'s tier-internal selection call it (depends on `PLAN-eliminate-worklist-report-per-stop-env.md` landing; fallback in section 3.1 if it has not).
- [ ] Add `N_BEHAVIOR_HINT` to `worklist_messages.py` beside `N_AGENT_HINT`.
- [ ] Wire the hint line into `run_stop`'s allow block after the drain at `wl_checks.py:4844`, inside `contextlib.suppress(Exception)`, BEFORE the empty-`parts` exit at `wl_checks.py:4852` so it can never create output on a silent stop.
- [ ] Queue an `hint-corpus-err` advisory at priority 3 when `load_corpus` returns errors, mirroring `agent-corpus-err` at `wl_checks.py:1453`.
- [ ] Add the `--hint-propose <me> <text...> [SOURCE: <pointer>]` verb to `worklist.py`, appending one JSON line to `agent/ledgers/hint-proposals.jsonl` and nothing else.
- [ ] Queue the `hint-proposals` advisory (priority 3, `refresh_min` 720) counting proposals whose text is absent from the corpus, printing the promotion command.
- [ ] Register `WORKLIST_HINTS_FILE` in `.ci/policy/worklist-env-registry.json` (`kind: path`, `defaults: ["NONE"]`) and in `.ci/config/env-manifest.json`'s harness shard.
- [ ] Run `python3 .ci/scripts/quality/check_python_env_registry.py --write-baseline` and `npx tsx scripts/gen/gen-docs.ts --write` for the new name.
- [ ] Write `.ci/scripts/quality/check_hint_corpus.py` with assertions H1-H7 from section 6.3, control-first.
- [ ] Wire `check:ci-hint-corpus` at all three points (`---- gate ----` header block, `package.json`, `scripts/ci-runner/manifest.ts`) and confirm `scripts/gates/check-ci-parity.ts` is green.
- [ ] Add in-process unit tests in `.claude/rediacc_hooks/tests/test_wl_hints.py` driving `hint_pick` with `random.Random(seed)`: full-cycle coverage, no repeat inside a cycle, no back-to-back repeat across a cycle boundary, and at least two distinct first-picks across 50 seeds (the entropy control, mirroring `test_181_control`).
- [ ] Add a subprocess test proving the line appears on a loud allow stop AND is absent from a silent clean stop (the zero-byte case at `wl_checks.py:4852`), and absent from a blocked stop.
- [ ] Add the negative control: point `WORKLIST_HINTS_FILE` at an empty corpus and assert the stop output is byte-identical to the run without the feature, proving the corpus drives the line.
- [ ] Add `"WORKLIST_HINTS_FILE"` to `wlfix.py`'s `RESET_KNOBS` tuple.
- [ ] Add a ledger entry for this plan in `.ci/config/plan-boxes.json` (or run the ledger's own update path) so `check:ci-plan-boxes` G-A0 does not red on an untracked plan carrying open boxes.
- [ ] Run `python3 .ci/scripts/quality/check_prose_style.py reflow --write` then `check` on `docs/agent-reference/HINTS.md` and this plan.
- [ ] Run the full `.claude/rediacc_hooks/tests/` suite as the closing verification step.

## Acceptance criteria

- A loud allow-path stop carries exactly one `TIP (hint N of M, rotating):` line, last.
- A silent clean stop still emits zero bytes; a blocked stop carries no tip.
- `check:ci-hint-corpus` is green, and each of its seven assertions has been seen to RED against a planted defect before the green was believed.
- Over `M` consecutive stops in one session the set of displayed hint ids equals the set of active corpus ids, with no repeat inside the cycle.
- An empty corpus, a missing corpus and a malformed corpus each produce silence plus one queued note, and never a block or a traceback.
- `worklist.py --hint-propose` writes to `agent/ledgers/hint-proposals.jsonl` and to nothing else, and no code path promotes a proposal into `docs/agent-reference/HINTS.md` automatically.

## Notes for the implementer

### Critical Files for Implementation

- `.claude/hooks/stop/wl_checks.py` -- `OUTQ_PER_STOP:1315`, `outq_add:1347`, `outq_drain:1414`, `agent_hint_queue:1441`, allow-block emit `:4837-4852`
- `.claude/hooks/stop/wl_agents.py` -- the non-judged corpus-hint template (`agents_dir:191`, `load_corpus:236`, `best_hint:309`)
- `.claude/hooks/stop/wl_store.py` -- `agent_traps_path:283`, `trap_headings:401`, `trap_entries:428`, the Markdown-with-trailer parser to mirror
- `docs/agent-reference/TRAPS.md` -- the corpus shape and the charter boundary
- `.ci/scripts/quality/check_agent_hint_liveness.py` -- the control-first liveness gate to model `check_hint_corpus.py` on
