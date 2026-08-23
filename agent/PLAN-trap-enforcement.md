# PLAN: Trap enforcement, from prose to instruments
Status: draft
Owner: 99ccf057
Updated: 2026-08-09

Replace "a session reads TRAPS.md" with instruments that fire whether or not anyone
read anything. The corpus stops being the protection and becomes the ledger of which
instrument protects what, with a gate that reds when a trap has neither an instrument
nor a stated reason it cannot have one.

**2026-08-23: two TRAPS.md entries and one trapguard rule (`rule_history_rewrite_controls`) landed OUTSIDE this plan -- individual instruments again, NOT this plan starting; it is still `draft` and still unowned.**

Supersedes `agent/PLAN-unify-trap-corpus.md` (§9 says exactly which parts
are kept and which are replaced). Nothing in this plan is implemented.

**2026-08-18: STILL UNIMPLEMENTED, VERIFIED RATHER THAN ASSUMED, AND UNOWNED.**
Checked directly: no trap script exists under `.ci/scripts/quality/`, no `check:`
id in `package.json` mentions traps, and `docs/agent-reference/TRAPS.md` carries
no ledger table (zero table rows). Individual traps HAVE become instruments in
the meantime -- TRAPS.md:537 says "This one is now an instrument, not just a
lesson" -- which is easy to mistake for this plan having landed. It has not: the
thing specified here is the SYSTEMATIC gate that reds when a trap has neither an
instrument nor a stated reason it cannot have one, and that gate does not exist.

Owner `99ccf057` is a session that ended around 2026-08-09; nothing is in flight.
`Status: executing` overstates it, but the work is still wanted, so it is left
open rather than closed as superseded. A session picking this up owns it from
scratch and should re-verify every file:line below before trusting one -- the
sibling plans in this directory have had their line numbers decay twice.

The stale `docs/agent/main/` path above is corrected in place: that tree stopped
existing at the 2026-08-14 move.

---

## 1. Context: prose does not protect, and the repo has the receipts

The operator's statement of the problem: *"reading the trap file could be skipped with
an agent... we need a long-term solution."* A markdown trap protects only a session
that reads it, remembers it, and applies it at the moment of risk. All three links
have been observed to break, repeatedly, in this repository.

**The recurrence evidence, verified:**

- `agent/REPORT-licensing-bigbang-2026-08-04.md:234`, under the heading
  "WHY KNOWING ABOUT IT DOES NOT PREVENT IT": *"The pull is not toward carelessness;
  it is toward the cheapest observable PROXY for the thing you actually need."* The
  same report at `:230-232` records an instrument built for this class, by an author
  who had spent the night on this class, failing the class, and being caught by a
  different pre-existing instrument.
- `~/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-0804-1.md:1424`:
  *"authored by me, hours after writing the TRAPS.md entry about it. Writing the rule
  down does not confer immunity from it."*
- Same file `:113-114`: *"Nine instances of ONE pattern, across harness, product,
  gates, and the meta-gate, and not one was caught by its author re-reading it. Each
  was caught by a DIFFERENT instrument."*
- `reports/pr-babysit-0807.md:290-292` and `:317-322`: four npm scripts that do not
  exist were read as passing gates in one night, after the class had already been
  written down three times.

The class recurred on 2026-08-04, on 2026-08-07, and again on 2026-08-09. Rewriting
the entry more sharply has been tried and is what produced the 2026-08-04 instance.

**The second failure mode, which prose cannot reach at all.** A subagent is spawned
with a task prompt, not with the corpus. Hooks fire on a subagent's tool calls
(the PostToolUse payload carries `agent_id` and `agent_type`, documented at
`.claude/hooks/stop/wl_wait.py:141-142`), so an instrument applies uniformly to the
main loop and to every agent it spawns, including agents spawned by agents. A
document applies only to whoever was handed it. That asymmetry, not the recurrence
count, is the strongest argument for the shift.

---

## 2. Design principle

**"Each was caught by a DIFFERENT instrument."** Everything below is derived from
that one sentence. Four consequences, in order of how much design they decide.

**2.1 The instrument must not be the faculty that failed.** The failure is a model
holding a fact in working memory and not applying it. An instrument that asks a model
to re-read its notes is the same faculty a second time, and the 2026-08-04 evidence
is that the second attempt has no better odds than the first: the author of the entry
committed the violation hours later. This rules out, as *primary* mechanisms:
session-start briefings, sharper wording, longer checklists, and a Stop-hook judge
prompt that asks a model whether it respected the traps. Those are all the same
faculty. They remain useful as backstops and are kept as such, never as the load-
bearing layer.

**2.2 Match the instrument to the failure SHAPE, not to the trap's topic.** Four
shapes cover the 23 traps in the corpus:

| Shape | What goes wrong | Instrument that catches it | Why this one |
|---|---|---|---|
| **Forbidden action** | A command is issued that should never be issued here (`git worktree add`, `git commit --amend`, blanket `git add -A`) | PreToolUse block on the command string | The action has not happened yet; intent is fully visible in the argument vector |
| **Guaranteed-failing action** | A command is issued that cannot possibly do what the session thinks (`npm run <script that does not exist>`) | PreToolUse block, after resolving the referent | Blocking costs nothing: the command was going to fail anyway |
| **Misread outcome** | The command ran, the output is not what the session will conclude from it (a cancelled run read as passed, a phantom deletion in `git diff`) | PostToolUse injection keyed on `tool_response` | Intent was innocent. Only the *result* distinguishes the trap from the normal case |
| **Unproven claim** | A gate, probe, or suite reports clean without having run | CI gate with a planted defect (control-first) | The artifact is static and inspectable outside the session |

The fourth shape is already mechanized four times over
(`.ci/scripts/quality/check_lint_rule_liveness.py`,
`.ci/scripts/quality/check_gate_reachability_coverage.py`,
`.ci/scripts/quality/check-dead-case-arms.sh:106-132`,
`scripts/check-suppression-liveness.ts`). The third shape is entirely unexploited:
**no hook in this repository reads `tool_response`** (single repo-wide occurrence is
a docstring at `wl_wait.py:141`). That is the largest unclaimed surface and it maps
onto the two most expensive misread-outcome traps.

**2.3 Precision, not coverage, is the budget.** An instrument that fires too often
trains the reader to skim it, which reproduces the corpus's failure at higher
frequency and inside the tool loop, where it is more annoying and therefore learned
faster. This is why the misread-outcome tier is keyed on the response rather than the
command: firing on "the session ran `gh api .../jobs`" would fire on every CI round,
while firing on "the response says `cancelled` and the session filtered for
`failure`" fires only in the trap's own footprint. Each injecting rule additionally
fires at most **once per session per trap**.

**2.4 A blocking instrument that is wrong is worse than the trap it prevents.** A
false block stops correct work with no override, in a session the operator is not
watching. So blocking is not a severity dial, it is a category with an entry
requirement: **a rule may BLOCK only if the blocked command is certain to fail
anyway, or is forbidden by standing policy with an escape named in the block
message.** Everything else injects after the fact and lets the session decide. Both
early blocking candidates in §6 clear that bar explicitly, and the registry gate
(§3, assertion F3b) refuses a `block`-tier rule that declares neither justification.

---

## 3. Ruling on the trap registry: adopt it, with one change and one hard constraint

**Verdict: the registry is right, not over-engineered.** It is the only part of this
design that scales, because it converts "is this trap covered?" from a question
someone has to remember to ask into a gate that asks it every run. The repo already
has two registries of exactly this shape and both are self-policing:
`scripts/ci-runner/manifest.ts` (`GateSpec` at `:26-58`, whose docstring at `:17-20`
states the house rule "MAINTENANCE IS BY RULE, NOT BY HAND") and
`scripts/lib/suppression-liveness.ts` (`Probe` at `:45-78`, where every entry carries
its own oracle and the oracle may return `null` to SKIP rather than condemn).

Two modifications to the proposal as stated.

### 3.1 Change: the corpus IS the registry. Do not create a second file.

The brief proposes "a machine-readable file where each trap carries an id...". A
separate file is the wrong shape here for a specific reason: the defect being fixed
in §9 is *two trap files that drift*. Adding a third artifact that must stay in sync
with the corpus recreates the disease under a new name, and the sync gate would then
be policing a problem the design chose to have.

Instead, each `## ` entry in the single canonical `docs/agent-reference/TRAPS.md` gains a
three-line structured trailer directly under its heading, before the body:

```markdown
## A check that cannot fail is not evidence
Trap-Id: check-cannot-fail
Enforced-By: gate:check:ci-gate-reachability-coverage, gate:check:ci-dead-case-arms, gate:check:ci-suppression-liveness
Residue: JUDGMENT-ONLY for ad-hoc probes typed in the moment; no instrument can know what a one-off probe was meant to prove (nine instances, all ad-hoc, pr-babysit-0804-1.md:113).

<body as today>
```

- `Trap-Id`: stable kebab-case, unique, never reused after retirement.
- `Enforced-By`: comma-separated pointers, or the single token `JUDGMENT-ONLY`.
- `Residue`: optional when `Enforced-By` names instruments (it records the part they
  do not reach); **mandatory** when the disposition is `JUDGMENT-ONLY`.

Pointer grammar, each of which must resolve:

| Prefix | Resolves against | Example |
|---|---|---|
| `gate:<id>` | the `GATES` array in `scripts/ci-runner/manifest.ts` | `gate:check:ci-dead-case-arms` |
| `hook:<rule-id>` | the rule table in the trapguard dispatcher (§4) | `hook:npm-script-exists` |
| `suite:<harness>#<case>` | a case header in `test-worklist-v5.sh` or `test-hooks.sh` | `suite:test-hooks#blanket-git-add-fires` |
| `JUDGMENT-ONLY` | terminal; requires `Residue:` | |

This keeps one writable face, keeps the file human-readable and openable from the
PostCompact briefing, and makes the registry a property of the document rather than a
shadow of it.

**The parser must track fenced code blocks, and today's does not.** `trap_headings`
(`wl_store.py:278-283`) is a bare `line.startswith("## ")` loop with no fence state.
Both corpora happen to contain no fenced `## ` line right now, verified by script, so
this is latent rather than active. The registry activates it: once F2 requires every
`## ` entry to carry a `Trap-Id`, a `## ` inside a fenced example in a trap body
becomes a phantom entry with no id, and the gate reds on a document that is correct.
Trap bodies routinely carry shell and markdown examples, and this plan's own §3.1
example block would trip it. So the shared parser (one implementation, used by both
`wl_store` and the gate, never two) toggles on ``` and ~~~ fences and ignores headings
inside them. Test case: a fixture whose body contains a fenced `## Not A Trap` must
yield the real entries only, and the same line unfenced must yield an F2 red.

### 3.2 Hard constraint: the gate must demand a LIVE instrument, never merely a named one

This is the part that decides whether the registry helps or harms. A gate that
demands every trap name an `enforced_by` creates pressure to name one, and the
cheapest thing to name is a grep that pattern-matches the trap's title. That gate
would industrialize the exact defect the corpus's most expensive entry warns about:
it would manufacture checks that cannot fail, at a rate of one per trap, and report
100% coverage while doing it.

So the gate `check:ci-trap-registry` asserts liveness, not presence:

- **F1 POPULATION FLOOR.** At least `TRAP_FLOOR` entries (23 after the §9 merge). An
  emptied or truncated corpus reds instead of passing vacuously. Precedent:
  `MIN_MANIFEST_GATES = 40` at `check_gate_reachability_coverage.py:47`.
- **F2 IDENTITY.** Every `## ` entry has a `Trap-Id`; ids are unique; ids match
  `^[a-z0-9][a-z0-9-]{2,48}$`.
- **F3 DISPOSITION.** Every entry has either at least one resolving pointer or
  `JUDGMENT-ONLY`. **F3b:** a pointer of the form `hook:<id>` whose rule declares
  `tier == "block"` requires that rule to also declare `certain_failure = True` or a
  non-empty `policy` string naming the standing rule and the escape (§2.4).
- **F4 POINTERS RESOLVE.** Every `gate:` id exists in `GATES`; every `hook:` id exists
  in the dispatcher's rule table; every `suite:` case header exists in the named
  harness. A dangling pointer is a red, not a warning.
- **F5 POINTERS ARE LIVE.** This is the assertion the registry exists for.
  - `gate:` ids must additionally be reachable from `npm run ci`, reusing the existing
    probe (`.claude/hooks/stop/wl_reggate.py`'s `gate_reachable`, whose own blindness
    is already gated by `check_gate_reachability_coverage.py`). A gate nobody runs is
    not an instrument.
  - `hook:` rule ids must have **at least one FIRING case and at least one SILENT
    case** in the hook suite. One-sided coverage is how a rule that always fires, or
    never fires, passes as covered.
  - `suite:` cases must appear in the harness's own pass tally, which
    `.ci/scripts/test/gates/test-claude-hooks.sh:31-38` already parses.
- **F6 SELF-CONTROL, runs first.** Against a `mktemp` fixture, plant three defects and
  require a red on each: an entry with no disposition (F3), an entry pointing at
  `gate:check:does-not-exist` (F4), and a `hook:` rule with a firing case but no
  silent case (F5). If any plant passes, the gate exits non-zero **without judging the
  real tree**. This is `check-dead-case-arms.sh:106-132` applied to the registry, and
  it is non-negotiable given what the gate is for.

`JUDGMENT-ONLY` must stay cheap to declare, deliberately. A disposition that is
expensive or embarrassing to choose gets lied about, and a lie in this field is worse
than an honest gap because it hides the residue that §5 is trying to size. The gate
never counts `JUDGMENT-ONLY` against anything; the number of them is the metric the
operator should watch, not a number to drive to zero.

### 3.3 The registry pays for itself immediately: it fixes the judge prompt's cost curve

`wl_store.trap_headings` (`.claude/hooks/stop/wl_store.py:265-284`, not `:231` as the
brief states; `:231` is `agent_traps_path`) caps at 40 headings and `break`s in **file
order**, while both corpora append newest-last (`.agent/TRAPS.md:11`, "Newest at the
bottom"). Past 40 entries the newest traps go silently invisible to the judge. The
merge alone reaches 23, so this stops being theoretical at once.

`PLAN-unify-trap-corpus.md` §4.2 answers this by raising the cap to 120 and appending
a synthetic overflow marker. **This plan supersedes that.** With `Enforced-By` present,
the cap problem dissolves rather than moving: a trap that a gate or hook already
enforces does not need to be in a per-stop model prompt at all, because a machine is
already watching it. So:

> The judge prompt and the PostCompact briefing carry only the entries whose
> disposition is `JUDGMENT-ONLY`, plus entries with a non-empty `Residue:`, rendered
> as the residue sentence rather than the title.

Mechanized traps leave the prompt permanently. Growth in the mechanized population
becomes free, growth in the residue population is exactly the thing that should cost
attention, and the "silently drops the newest" bug cannot recur because there is no
positional cap left to hit. Keep a generous belt-and-braces cap (`TRAP_PROMPT_CAP =
60`) purely so a pathological corpus cannot blow the prompt, and make overflow loud,
per the unify plan's instinct.

---

## 4. The system: one dispatcher, four tiers, one ledger

### 4.1 Stop adding one file per hook

Today each hook is registered individually in `.claude/settings.json`: 18 separate
PreToolUse entries for Bash (`:9-77`), 4 for edits (`:86-98`), 2 PostToolUse for Bash
(`:109-113`). **There is no dispatcher**; the JSON array order is the only thing that
encodes ordering, and adding a hook means two synchronized edits. Each Bash tool call
therefore spawns 18 `bash` processes, and each hook that sources
`pre-bash/lib/command-scan.sh` forks roughly ten more (`command-scan.sh:108-113`
chains awk, tr, sed, awk, tr, sed). Order 200 processes per Bash tool call, with **no
`timeout` on any PreToolUse hook** (the only timeout in the file is `:142`, Stop=300s)
and a worst case around 70 seconds of unbounded network wait on a single `gh pr merge`
line (`block-admin-merge.sh:64,82,92` and `block-premature-ready.sh:49`).

Adding five more entries in that style is a 28% increase in per-call fork cost for no
functional gain. Introduce **`.claude/hooks/trapguard/`**, registered exactly twice:

```
PreToolUse  matcher "Bash": python3 .../trapguard/dispatch.py --pre-bash
PostToolUse matcher "Bash": python3 .../trapguard/dispatch.py --post-bash
```

One process for all new rules, which buys three things the current shape cannot have:
a single enforced time budget, a single exception boundary, and a rule-id namespace
for `Enforced-By` pointers to resolve against.

**The dispatcher's own risk, named:** it is a single point of failure where 18
independent hooks degrade one at a time. That is answered by F5, which requires every
rule id to carry a firing case and a silent case, and by §7's dispatcher-integrity
case. This is strictly better than the status quo, where `pre-edit/block-inline-python.sh`
and both `post-bash/` hooks have **zero behavioral test cases** (wiring-checked only,
via `test-hooks.sh:44-113`) and `pre-bash/test-block-git-amend.py` is an orphan
referenced by nothing in the repo. Existing instruments are already unproven; the
dispatcher is the first shape that makes that state impossible to reach quietly.

Do **not** migrate the existing 18 in this program. They work, migration is churn with
its own regression surface, and F4 can point at them by `suite:` case today.

### 4.2 The rule interface

Mirroring `Probe` (`scripts/lib/suppression-liveness.ts:45-78`), where each entry
carries its own oracle and its own fix:

```python
@dataclass(frozen=True)
class Rule:
    id: str                    # the Enforced-By hook:<id> target
    trap: str                  # the Trap-Id it enforces; F4 checks both directions
    tier: str                  # "block" | "inject"
    certain_failure: bool = False   # block-tier justification (a)
    policy: str = ""                # block-tier justification (b), names rule + escape
    def applies(self, ev) -> bool: ...   # cheap: string ops on the command only
    def verdict(self, ev) -> str | None: # the message, or None
```

`applies` may not fork a process or touch the filesystem. `verdict` may, within the
budget. The split exists so the common case (no rule applies) costs only string
comparisons.

### 4.3 Dispatcher contract

1. **Bounded read.** `sys.stdin.buffer.read()` up to `MAX_PAYLOAD = 4 MiB`; drain and
   discard the remainder so the writer never sees EPIPE. Over the bound, command-only
   rules still run and response-reading rules are skipped with a recorded reason. This
   matters because `tool_response` carries the full tool output: a `gh run view --log`
   can be megabytes on a hook that runs on every Bash call.
2. **Never persist response values.** The response may contain tokens, keys, and
   customer data. Rules may read it; nothing writes it anywhere. The probe in §7
   records key names, lengths, and booleans only.
3. **Time budget.** `DEADLINE_MS = 250`, checked on a monotonic clock between rules.
   Over budget, remaining rules are skipped and the overrun is logged. No rule may
   make a network call; that is a review rule, and F5's silent-case requirement makes
   a network-dependent rule hard to test, which is the intended friction.
4. **Fail open per rule, and loudly.** Every `applies`/`verdict` call is wrapped; an
   exception is appended to `~/.claude/trapguard/errors.jsonl` and the next rule runs.
   The Stop hook surfaces a non-empty error log as a `vadd(..., always=True, ...)`
   violation, because `always=True` is the documented tier for hook-integrity failures
   (`wl_checks.py:2184-2190`). A silently failing guard is the trap this whole plan is
   about; failing open is correct, failing open *quietly* is not.
5. **Block resolution.** First `tier == "block"` verdict wins: message to stderr,
   `exit 2`. That matches every existing hook's contract
   (`block-worktree-add.sh:36-37`).
6. **Inject resolution.** All `tier == "inject"` verdicts are concatenated into one
   `hookSpecificOutput.additionalContext` and printed as JSON with `exit 0`. Live
   precedent for the exact envelope: `wl_wait.py:386-396`.
7. **One shot per session per trap.** Inject verdicts are suppressed if
   `(session_id, trap_id)` is already recorded in
   `~/.claude/trapguard/shown-<session>.json`. Per §2.3, repetition is how an
   instrument teaches skimming.

### 4.4 What the four tiers are, end to end

- **Tier 1, forbidden action** (PreToolUse block): the existing 18 hooks, plus
  `blanket-git-add`.
- **Tier 2, guaranteed-failing action** (PreToolUse block): `npm-script-exists`, and
  future referent-resolution rules of the same shape.
- **Tier 3, misread outcome** (PostToolUse inject, reads `tool_response`):
  `cancelled-run-not-passed`, `phantom-deletion-diff`.
- **Tier 4, unproven claim** (CI gate, control-first): the four existing liveness
  gates, plus `check:ci-trap-registry` itself.

---

## 5. The judgment-only residue

This is the part no instrument closes, and it is the expensive part.

**What is actually in it.** The honest split on the corpus's most costly entry: a
*registered gate that cannot fire* is Tier 4 and already has four working precedents.
An *ad-hoc probe an agent types in the moment* is not mechanizable, because no hook
can know what the probe was meant to prove. All nine 2026-08-04 instances were
ad-hoc: a `git archive` that extracted nothing, a restricted PATH that hid bash, a log
collector pointed at a directory the tool deletes on exit, and a `keyctl` probe that
exercised a different operation from the one that fails
(`pr-babysit-0804-1.md:1420-1424`). Joining that residue: `A wrong comment is more
dangerous than a wrong commit message` (no parser knows what a comment overclaims) and
`A ruling from an artifact is a hypothesis` (no parser knows which claim was
load-bearing).

**Recommendation: inject at the moment of risk, and accept a named residue below
that.** Ranked against the alternatives:

- *Session-start or PostCompact briefing* is what exists today, and it is precisely
  what failed: the 2026-08-04 author had the fact and did not apply it. Keep it (it is
  free, it already runs), demote it to a backstop.
- *A Stop-hook judge that checks traps against the session's actions* is the same
  faculty per §2.1, and it is post-hoc: it can only report a cost already paid. Keep
  one narrow, deterministic slice of it: the judge already receives the session's
  cited sources (`wl_judge.py:316-324`), so a **non-model** pre-check can assert that
  a session claiming a gate passed cited a gate id that exists in `GATES`. That is
  cheap, mechanical, and catches the `npm run <missing>` family a second time at a
  different layer. It is a backstop, not the mechanism.
- *Moment-of-risk injection* is the recommendation, because it is the only option that
  puts the fact in front of the decision instead of before it, and because it reaches
  subagents for free (§1).

**The failure mode of the recommendation, named plainly: precision decay.** The
injector's value is entirely in its hit rate. If it fires on shapes that turn out to
be usually fine, sessions learn to discount injected text, and at that point the
instrument is worse than nothing because it also consumes context. Three defenses,
all mechanical:

1. **Response-keyed, never intent-keyed.** Fire on evidence in the output, not on the
   shape of the request (§2.3). This is what makes Tier 3 different from every hook in
   the repo today.
2. **One shot per session per trap** (§4.3.7).
3. **A measured hit rate, or the rule is retired.** Each Tier 3 rule appends one line
   per fire to `~/.claude/trapguard/fires.jsonl` (rule id, timestamp, session, and
   nothing else). A rule that has fired more than `RETIRE_FIRES = 40` times without the
   operator having confirmed a true positive is a candidate for retirement, reported by
   the Stop hook rather than auto-removed. Without a fire log, precision decay is
   invisible, which is the same blindness this plan exists to remove.

**What is left after all that, stated so it can be argued with:** for ad-hoc
verification, wrong comments, and rulings taken on faith, there is no instrument, and
this plan does not pretend otherwise. The registry's contribution is that the residue
becomes *enumerable*: `grep -c 'JUDGMENT-ONLY' docs/agent-reference/TRAPS.md` is the honest size
of the unprotected surface, and it is the only number in this design worth reviewing
periodically.

---

## 6. Sequencing

Ordered by cost already paid. Each wave is independently landable and leaves the tree
green.

### W0 (prerequisite): execute the corpus unification

Run `PLAN-unify-trap-corpus.md` §4 through §7 as written, with the §9 amendments
below. Output: one canonical `docs/agent-reference/TRAPS.md` at 23 entries, the hook repointed,
the anti-resplit gate green. Nothing here can be ordered before ids exist and the
corpus has one home.

### W1: registry trailers, the coverage gate, and the prompt filter

1. Add `Trap-Id` / `Enforced-By` / `Residue` trailers to all 23 entries. Populating
   them **is** the reclassification. Do not port the "roughly 14 mechanizable" estimate
   from the earlier investigation: that investigation asserted three claims as verified
   and two were false (it claimed the hook test suites are in no workflow and no
   `package.json`, which is refuted by `manifest.ts:388` plus
   `.ci/scripts/test/gates/test-claude-hooks.sh:24` and
   `.github/workflows/ci-quality.yml:1089`; and it claimed
   `check-autopilot-no-bypass.sh` is wired nowhere, also false). Every disposition gets
   written by resolving a pointer, not by recalling a classification.
2. Land `.ci/scripts/quality/check-trap-registry.sh` with F1 to F4 and F6. **F5 is
   deferred to W2**, honestly and in a comment, because there are no `hook:` pointers
   to prove live yet.
3. Land the prompt filter of §3.3 (`JUDGMENT-ONLY` and `Residue` entries only) in
   `wl_store.trap_headings` and the single renderer the unify plan introduces.
4. **File the coverage gap this exposes as work, not as a note.** `block-inline-python.sh`
   and both `post-bash/` hooks have no behavioral cases, so any trap pointing at them
   points at an unproven instrument, and F5 will red on them in W2. Write those cases
   in W1, before F5 lands, so W2 does not begin with a self-inflicted red.

### W2: the dispatcher, two blocking rules, and the first `tool_response` probe

**Candidate A: `npm-script-exists`** (Tier 2, block).

- *Correction to the brief, verified this session.* The 0807 report describes missing
  npm scripts as exiting "non-zero-or-silent". Measured: `npm run check:ci-docs-links`
  exits **1** and writes `npm error Missing script: "check:ci-docs-links"` plus
  did-you-mean suggestions to **stderr**, with **stdout completely empty**. npm is not
  silent. The trap is a session reading stdout only, which is the same root cause as
  `.agent/TRAPS.md:101` ("Read stdout and stderr SEPARATELY"). That changes the
  instrument for the better: the referent is resolvable *before* the call, so this
  becomes a deterministic Tier 2 block instead of a response heuristic.
- *Surface:* PreToolUse, `trapguard` rule id `npm-script-exists`.
- *Detection rule:* for each `npm run <name>` / `npm run-script <name>` anchored at a
  command position (reuse the anchoring idiom of
  `command-scan.sh:120` `hook_gh_pr_at_command_pos`), resolve the governing
  `package.json`: `--prefix <dir>` or `-w <workspace>` in the same segment, else a
  `cd <dir>` earlier in the same segment, else the repo root. Block when `<name>` is
  absent from that file's `.scripts`. **Fail open** on: a name containing `$`, backtick
  or `{` (dynamic); an unresolvable directory; an unparseable `package.json`.
- *Why blocking is safe:* `certain_failure = True`. The command exits 1 regardless, so
  a false block costs nothing a true block does not already cost.
- *Message:* the missing name, the resolved `package.json`, and the nearest real script
  names, so the fix is one edit away.
- *Mutations that must turn it red:* `npm run check:ci-docs-links` exits 2;
  `cd packages/cli && npm run test` (a real script in that package) exits 0;
  `npm run "$GATE"` exits 0 (fail open); `npm run check:ci-python-lint` exits 0.

**Candidate B: `blanket-git-add`** (Tier 1, block).

- *Verified gap:* grep across `.claude/hooks/pre-bash/` for `git add`, `add -A`,
  `add --all`, `add .` returns exactly one hit, and it is a fixture inside the orphan
  `test-block-git-amend.py:25`. There is no guard. Trap `.agent/TRAPS.md:146` documents
  the incident (sweep `cefa43ca7` imported another session's
  `check-solution-video-engine.ts`, which failed `273 of 273` on branch 0730-2, run
  30554973713, job 90913300683).
- *Surface:* PreToolUse, rule id `blanket-git-add`.
- *Detection rule:* at a command position, `git [-flags] add` whose pathspec set is
  blanket: `-A`/`--all` with **no** `--` pathspec following, or a lone `.`, or `:/`.
  `git add -A -- packages/cli/src` is explicitly allowed, and that is the escape the
  message names.
- *Why blocking is safe:* `policy = "CLAUDE.md session default 1 plus memory
  feedback_shared_checkout_hygiene: never blanket-add in a shared tree. Escape: name
  the pathspec, git add -A -- <path>."` The escape is in the block text, so a session
  that legitimately wants everything can express that in one edit.
- *Mutations:* `git add -A` exits 2; `git add .` exits 2; `git add -A -- packages/cli`
  exits 0; `git add packages/cli/src/foo.ts` exits 0; `git worktree add x` exits 0 (no
  cross-talk with the existing worktree guard).

**Candidate C: the `tool_response` probe** (see §7.1). It lands in W2 and retires in
W3; nothing in Tier 3 may be written until it has reported.

Also in W2: F5 goes live, `check:ci-trap-registry` gains its manifest entry and
workflow step, and the two new rule ids become resolvable `Enforced-By` targets.

### W3: the two misread-outcome rules

**Candidate D: `cancelled-run-not-passed`** (Tier 3, inject). Trap:
`docs/agent-reference/TRAPS.md:147`, measured cost three consecutive CI rounds that measured
nothing while being counted as "did not recur".

- *Surface:* PostToolUse, matcher Bash, rule id `cancelled-run-not-passed`.
- *Detection rule:* `applies` when the command names `gh run` or an
  `actions/runs`/`jobs` API path. `verdict` fires when the response shows a run-level
  `cancelled` conclusion, **or** when the command filtered on `conclusion=="failure"`
  and returned empty output while any run in scope is `cancelled`. Both branches key on
  the response, never on the command alone.
- *Injected text:* the trap's residue sentence plus the exact remedy already in the
  entry (read the job's own conclusion, not the run's).
- *Mutations:* a synthetic payload whose `tool_response` carries a cancelled run must
  produce `additionalContext` naming the trap id; a payload where every job is
  `success` must produce no output at all; a payload with an empty `tool_response` must
  produce no output (proving the rule does not fire on absence).

**Candidate E: `phantom-deletion-diff`** (Tier 3, inject). Trap: the one entry present
in both corpora, `.agent/TRAPS.md:192` and `docs/agent-reference/TRAPS.md:184`. Observed
2026-08-09 on branch 0809-2: an intact 462-line `wl_checklist.py` reported
`1 file changed, 462 deletions(-)`, and the entry itself records that "the reflex read
is that a sub-agent deleted it". The near-miss is a destructive repair of a file that
was never damaged, which is why it earns an instrument despite one observed instance.
- *Surface:* PostToolUse, rule id `phantom-deletion-diff`.
- *Detection rule:* `applies` when the command is `git diff` with a ref argument and
  without `--cached`/`--staged`. `verdict` fires when the response reports deletions
  with no insertions **and** at least one path named in the output still exists on
  disk. The on-disk test is the whole discriminator and costs one `stat`.
- *Injected text:* the entry's own remedy, `git show <branch>:<path> | diff - <path>`.
- *Mutations:* synthetic `1 file changed, 462 deletions(-)` naming an existing file
  fires; the same output naming a path that does not exist stays silent; a normal
  mixed insert/delete diff stays silent.

Also in W3: the probe entry is removed from `settings.json`, and the registry gate
grows an assertion that it is gone, so a diagnostic cannot become permanent overhead
on every tool call.

### W4: residue instrumentation

The fire log and retirement reporting of §5.3, plus the deterministic
cited-gate-id-exists pre-check of §5. No new blocking rules. Reassess the
`JUDGMENT-ONLY` count; that number, not the rule count, is the program's exit
criterion.

---

## 7. Control-first test plan

House style throughout: plant the defect, assert the FIRE, re-run clean, assert
SILENCE. A case that only asserts silence proves nothing.

### 7.1 The first `tool_response` reader's control (blocking prerequisite for Tier 3)

No hook in this repo has ever read `tool_response`. The only evidence it arrives is a
docstring (`wl_wait.py:139-143`) recording a payload someone captured. That is a
ruling from an artifact, which is itself a trap in the corpus, so it gets probed
before anything depends on it.

**The probe.** `trapguard/dispatch.py --probe-payload`, registered for one wave as a
matcher-less PostToolUse entry. Per invocation it appends one line to
`~/.claude/trapguard/probe.jsonl`:

```json
{"ts": "...", "tool_name": "Bash", "payload_keys": ["tool_name","tool_input","tool_response","..."],
 "response_type": "dict", "response_len": 1841, "response_keys": ["stdout","stderr","interrupted"],
 "nonce_found": true, "agent_id": "present", "agent_type": "Explore"}
```

**Key names, lengths, and booleans only. No values, ever** (§4.3.2).

**Acceptance assertions**, all three required before a single Tier 3 rule is written:

- **P1, the field arrives.** At least one Bash line has `tool_response` in
  `payload_keys` with `response_len > 0`.
- **P2, content arrives, proven without retaining content.** Run
  `echo trapguard-probe-<nonce>` with a fresh random nonce; the probe line for that
  call must have `nonce_found: true`. That proves stdout actually reaches the hook,
  and the nonce is the only string the probe ever matches against. If P2 fails while
  P1 passes, the field exists but is not the output, and every Tier 3 rule in this
  plan is void; say so and stop.
- **P3, hooks fire for subagents.** At least one line carries a non-null `agent_id`
  with an `agent_type` other than the main loop. §1 leans on this; it is currently
  inferred from field names, not observed. If P3 fails, the subagent-coverage argument
  in §1 is withdrawn and the plan's value drops to the main loop only, which is worth
  knowing before W3 rather than after.

**Retirement.** The probe entry is removed in W3 and the registry gate asserts its
absence. A permanent probe on every tool call is exactly the cost §4.1 objects to.

### 7.2 `.claude/hooks/test-hooks.sh`

Extend the existing harness rather than adding a second one; it is already gated
(`.ci/scripts/test/gates/test-claude-hooks.sh:24`, reached from
`.github/workflows/ci-quality.yml:1089` via `check:ci-quality-gates`), it already has
a vacuity guard (`test-claude-hooks.sh:35-38` fails on `CASES == 0`, so a harness that
silently ran nothing still reds), and it already runs a wiring control that deletes a
real registration and invents a ghost one (`test-hooks.sh:106-112`).

- One `check` case per mutation row in §6 (candidates A, B, D, E): each mutation
  asserted red, each companion asserted green.
- **Dispatcher integrity.** A payload that matches no rule must exit 0 and print
  nothing. A rule that raises must not prevent later rules from firing: register a
  deliberately-raising rule behind `TRAPGUARD_FAULT=<rule-id>`, then assert that a
  second rule in the same dispatch still blocks, that the error log gained a line, and
  that the dispatcher exit code is that of the second rule and not an interpreter
  traceback.
- **Budget.** A payload with `MAX_PAYLOAD + 1` bytes of response must exit 0 within the
  deadline, must not raise, and must record the skip reason.
- **Wiring.** `check_wiring` (`test-hooks.sh:70`) globs `*.sh` only, so it is blind to
  the dispatcher's Python. Extend the glob, or the two new registrations can be
  deleted from `settings.json` without the suite noticing. That blindness is also how
  `test-block-git-amend.py` became an orphan nobody detected.

### 7.3 `.ci/scripts/test/gates/test-trap-registry.sh`

One case per F-assertion, each against a `mktemp` fixture (never the real tree; the
hazard of a gate test that writes into the live tree is documented at
`run-all.sh:14-31`), plus a clean-tree case asserting exit 0 and a vacuity case
asserting an empty fixture reds.

**Correction to `PLAN-unify-trap-corpus.md` §7, which would otherwise be copied
forward.** That plan tells its gate test to end with `passed=<n> failed=<m>`. That is
the wrong contract and would make the test read as vacuous. Verified: `run-all.sh:207`
defines `PASS_RE=$'^(\033\\[0;32m)?PASS:'` and `:267-275` fails any gate test that
exits 0 without a single matching line. Gate tests under `.ci/scripts/test/gates/`
therefore emit `log_pass` lines, one per case, ending in `log_pass "all tests passed"`
(the shape of `test-dead-case-arms.sh`). The `PASS=<n> FAIL=<m>` counter is a different
contract belonging to `.claude/hooks/test-hooks.sh`, translated by
`test-claude-hooks.sh:31-38` precisely because the two harnesses do not agree. Use
`log_pass` for `test-trap-registry.sh`; use the counter only if extending
`test-hooks.sh`.

### 7.4 Manifest and parity

`scripts/ci-runner/manifest.ts` gains `check:ci-trap-registry`
(`ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: '...' }`)
and `gate-test:trap-registry` (`qualityGateTest: true`). The `gate-test:` prefix is
mandatory: `check-gate-id-convention.sh` reds on a manifest entry whose `run` resolves
to a `gates/` script under any other id. `check:ci-parity` then verifies the step name
against the workflow YAML, so the workflow step must be added with the exact same
string.

### 7.5 Local run commands

```bash
bash .claude/hooks/test-hooks.sh
bash .ci/scripts/test/gates/test-claude-hooks.sh
bash .ci/scripts/quality/check-trap-registry.sh
bash .ci/scripts/test/gates/test-trap-registry.sh
bash .ci/scripts/quality/check-python-lint.sh
npm run check:ci-shell-format
npm run check:ci-gate-id-convention
npm run check:ci-gate-reachability-coverage
bash .ci/scripts/test/gates/test-ci-parity.sh
```

Read stdout and stderr separately on every one of these. `test-worklist-v5.sh` has
shipped `253 passed, 0 failed` while three assertions wrote `pass: command not found`
to stderr (`.agent/TRAPS.md:111-117`), and this plan's own W2 correction exists because
a command's stderr was not read.

---

## 8. Risk

**Blast radius: every Bash tool call, in every session and every subagent, in this
repo.** That is the largest blast radius of any change in this program, and it is why
tiers 1 and 2 have an entry requirement (§2.4) rather than a severity dial.

Ranked by what can actually go wrong:

1. **A blocking rule that is wrong stops correct work with no override.** Worse than
   the trap it prevents, because the trap costs a round and a false block costs the
   task. Defenses: the §2.4 entry requirement, enforced mechanically by F3b; every
   detection rule fails open on anything it cannot resolve confidently; and the block
   message always names the escape. If the reviewer wants more margin, land candidates
   A and B in `inject` tier for one wave and promote them once the fire log shows zero
   false positives. That is a real option and it costs one wave.
2. **The dispatcher crashes and takes all its rules dark at once.** Defenses:
   per-rule exception boundaries (§4.3.4) so one bad rule cannot silence the others;
   the error log surfaced by the Stop hook at `always=True`, so failing open is visible
   within one stop rather than at the next incident; and F5's two-sided coverage
   requirement, which makes a rule that never fires a gate failure instead of a quiet
   nothing.
3. **Latency on every Bash call.** The baseline is already order 200 forks per call
   with no timeout (§4.1). The dispatcher adds one Python interpreter start, roughly
   30 to 60 ms, in exchange for not adding five more bash-plus-jq chains. The 250 ms
   deadline bounds the worst case, `applies` may not fork, and no rule may make a
   network call. Measure it in W2 and put the number in the wave report; if the
   interpreter start dominates, the fallback is to fold the dispatcher into the
   existing matcher-less PostToolUse Python entry (`settings.json:121`) rather than to
   add a second interpreter.
4. **A large `tool_response` on a hot path.** Bounded read plus discard-drain
   (§4.3.1). The failure mode to avoid is a hook that hangs holding a megabyte
   pipe; the bound is the fix and the oversized-payload case in §7.2 is the proof.
5. **Response data leaking into a log.** Prohibited by §4.3.2 and enforced by review:
   the probe records key names, lengths, and booleans, and the fire log records rule
   ids and timestamps. No file this plan creates may contain a byte of tool output.
6. **Precision decay in Tier 3**, covered in §5.3, measured by the fire log rather
   than assumed away.

**What keeps it cheap to reverse:** every rule is a data-driven entry in one table.
Deleting a rule is one deletion plus one `Enforced-By` pointer edit, and F4 turns a
forgotten pointer red rather than leaving a lie in the corpus.

---

## 9. Relationship to `PLAN-unify-trap-corpus.md`

**That plan should be marked `Status: superseded by PLAN-trap-enforcement.md` and kept
in place.** Its §5 merge plan and §6 gate design are executed unchanged as W0; nothing
below re-litigates them.

**Kept, unchanged, and depended on:**

- Canonical corpus at the tracked `docs/agent-reference/TRAPS.md`; repoint the hook to it
  (its §3.1). All of this plan assumes one file that exists in every checkout.
- `trap_headings` returns a two-tuple `(headings, problem)` so a caller cannot obtain
  headings without also receiving the problem (its §3.2). Loud-by-shape, not by care.
- One renderer, `traps_block(root)`, collapsing the duplicate fallbacks at
  `wl_checks.py:1481` and `wl_judge.py:323` (its §3.3).
- A missing corpus blocks the stop at `always=True`, with the repair command in the
  message (its §3.4).
- The anti-resplit gate `check:ci-trap-corpus`, assertions A to E and its self-control
  (its §6). It stays a separate gate from `check:ci-trap-registry`: one polices
  location, one polices dispositions, and merging them would make a single control
  responsible for two unrelated failure classes.
- The merge arithmetic and the `lost: []` verification (its §5.1, §5.5), the
  move-never-delete rule for the gitignored original (its §4.15), and the charter
  rewrite (its §5.3), which now also has to state the trailer format from §3.1.
- Its rejections of (b) un-ignoring `.agent/TRAPS.md`, (c) a generated or symlinked
  view, and (d) moving only the pointer. All three still hold; (b)'s finding that a
  directory ignore cannot be undone by a file re-include is independently confirmed.

**Superseded:**

- **Its §4.2 cap change** (raise the cap to 120, append a synthetic overflow marker) is
  replaced by §3.3 here: filter the prompt by disposition so mechanized traps leave it
  entirely, and keep a loud belt-and-braces `TRAP_PROMPT_CAP = 60`. The cap was
  treating a symptom that the registry removes.
- **Its §7 summary-line contract for `test-trap-corpus.sh`** is factually wrong and
  would ship a gate test that `run-all.sh` scores as vacuous. Corrected in §7.3 here:
  gate tests emit `log_pass` lines, verified against `run-all.sh:207,267-275`. Apply
  the correction to W0's gate test as well, since W0 executes that plan as written.
- **Its implicit model that the corpus is the protection.** Under this plan the corpus
  is the ledger, and the protection lives in the tiers of §4. The charter rewrite
  should say so, because an append-only file whose entries must each carry a
  disposition is a different artifact from a file of hard-won prose.

**Extended:**

- Its §4.12 `CLAUDE.md` edit must also say that appending a trap now requires a
  `Trap-Id` and a disposition, and that `check:ci-trap-registry` reds without them.
  A contributor who learns the trailer format from a gate failure has already had the
  bad experience the format exists to prevent.

**Its adjacent finding stands and is inherited:** `V_AGENT_BOOTSTRAP`
(`worklist_messages.py:271-279`) points at `.agent/README.md`, which is gitignored, so
on a fresh clone the whole `.agent/` convention bootstraps from a file that does not
exist. Same class (durable instructions in a volatile tree), separate worklist item.

---

## 10. Corrections to the brief, verified this session

1. **`wl_store.py:231` is not the reader.** `:231` is `agent_traps_path`; the corpus
   reader is `trap_headings` at `wl_store.py:265-284`. Everything the brief says about
   the 40-cap and file-order truncation is correct, at those lines.
2. **`npm run <missing>` is not silent.** Measured: exit code 1, empty stdout, and
   `npm error Missing script: "<name>"` with did-you-mean suggestions on stderr. The
   0807 report's "non-zero-or-silent" framing is imprecise, and the imprecision
   mattered: the real root cause is stdout-only reading, and the correct instrument is
   a deterministic pre-call block (§6, candidate A) rather than a response heuristic.
3. **`git add -A` is genuinely unguarded, confirmed.** The only hit anywhere under
   `.claude/hooks/pre-bash/` is a fixture line inside `test-block-git-amend.py:25`, a
   file referenced by nothing in the repo.
4. **`tool_response` is genuinely unread, confirmed.** One repo-wide occurrence, a
   docstring at `wl_wait.py:141`. `duration_ms` and `effort` are documented in the same
   line and are also used by nothing.
5. **New: the corpus parser has no fenced-code-block handling** (`wl_store.py:278-283`).
   Latent today (verified: zero fenced `## ` lines in either corpus), activated by the
   registry. Covered in §3.1. Found by grepping `^## ` over this plan file and getting
   a hit from inside its own example block.
6. **New, and relevant to the plan's premise:** three registered hooks
   (`pre-edit/block-inline-python.sh`, `post-bash/cancel-old-ci.sh`,
   `post-bash/refresh-pr-body.sh`) have **zero behavioral test cases**; they are
   wiring-checked only. The repo's existing instruments are already in the state this
   plan is trying to prevent, which is why F5 demands liveness rather than presence and
   why W1 writes those cases before F5 lands.
