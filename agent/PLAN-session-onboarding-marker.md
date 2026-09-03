# PLAN: what a session is told at its FIRST TOUCH, and how we would know it changed anything
Status: draft
Owner: 74de73ca
Updated: 2026-09-03

Every `file:line` anchor below was verified against the tree on 2026-09-03, and the
baseline in section 5 was MEASURED on this checkout rather than estimated.

## 0. The ask, and what it actually names

The operator's words: sessions at their start and after a compaction "hit the wall and
repeat the same mistakes like completing the job without updating the remainings by
invoking stop hook's commands with specific arguments. Currently, we print them in
different moments but I suppose not in first touch."

Two failures, which are one failure at two ends of a session:

  A. work is taken on and never becomes an item (`--add` never happens), so the store
     cannot describe the session at all; and
  B. work finishes without `--tick`/`--update` and without a `## Remaining` section,
     so the stop refuses and the session reconstructs its own history afterwards.

The Stop hook teaches both REACTIVELY. A session that has run a while has been refused
often enough to have learned. A session at minute one has not, and the cheapest
teacher available to it is the wall.

## 1. Why nothing existing lands at first touch

`handle_session_start` emits the design-docs listing, the plans listing and the
checklists. `handle_post_compact` emits STATE.md, RULES.md, TRAPS titles, plans and
checklists. **Neither names `--add`, `--tick`, `--update` or `## Remaining`.** The
reminders exist, but not the one thing the operator names, and they arrive where they
compete with a large system prompt.

`handle_session_start` returns early on `source == "compact"`. That is CORRECT (Claude
Code fires SessionStart with source=compact on top of PostCompact, and both handlers
would otherwise talk) and is not the gap.

The working precedent for this whole plan is `.claude/hooks/context/band-notice.py`: a
PostToolUse hook that speaks ONCE per band per epoch, states facts rather than
instructions, and never blocks. Its docstring records why the register matters --
instruction-shaped hook text trips the model's prompt-injection defences and gets
surfaced to the user instead of acted on. A trigger that gets surfaced is a trigger
that did not fire.

## 2. The marker

A per-session sidecar `.claude/hooks/context/state/<sid8>-onboard.json`, holding a
three-state machine scoped to the context epoch: `armed` -> `await-edit` ->
`delivered`.

**Its own file, not a key in the shared band state.** `band-notice.py` load/saves that
file on every tool call; two hooks on one event may run in parallel and a
last-writer-wins clobber would silently lose either the marker or the band ladder.

Armed at BOTH SessionStart and PostCompact, idempotent inside 120 seconds because a
single compaction fires both. It writes `epoch: null` deliberately: at PostCompact the
registered hooks may run in parallel, so `--arm` cannot know whether the epoch counter
has been bumped yet, and reading it there would be a race. The next tool call adopts
whatever epoch it sees, in a single-writer context.

**The asymmetry that matters:** an in-place compaction can fire NEITHER SessionStart
nor PostCompact. It still moves the epoch, via the usage-drop backstop in
`band-notice.py` -- the only thing in the tree that sees that case. So a marker whose
recorded epoch differs from the current one re-arms itself. That mismatch is how the
marker learns about a compaction no hook saw.

## 3. What first touch says

Two variants, never both, at most one emission per epoch, ~170 tokens, in the factual
register.

**Arm (a), the session owns items:** its own open rows, the store path, the sentence
that the Stop hook compares those rows against the last `## Remaining` section, and
the three verbs that change a row -- with the session prefix ALREADY SUBSTITUTED. The
operator's phrase is "commands with specific arguments", and the most common argument
error is the identity prefix, which the identity check refuses. Pre-substituting
removes that error class for zero extra lines.

**Arm (b), the session owns nothing and has just edited its first file:** that it owns
0 items, `--add` and `--tick` with the evidence requirement, and the measured baseline
from section 5.

**Deliberately left out**, each for a reason: `--lease`, `--brief`, `--ask`, `--state`,
`--triage` (none is the named failure, and every extra line lowers the odds the three
that matter are read); the docs, plans and checklists (already delivered elsewhere, and
repeating them is what makes those blocks skimmable); the crons, the judge and the
deferral audit (each is actionable only when it fires, so the wall is the right teacher
for them); and any imperative framing at all.

## 4. When it fires

**"First touch" means the first TOOL CALL of the epoch, not SessionStart output and not
the first Edit.** Both alternatives were tested against the transcript corpus and both
lose:

- SessionStart context arrives behind a large system prompt and two other blocks. This
  repo has already concluded a wall of text there is skimmed.
- An Edit-family matcher fails on measurement: session `74de73ca`'s first Edit was at
  +600 minutes; its first stop refusal was at +17.8 minutes. Its third tool call, at
  +1.1 minutes, was a Bash heredoc writing a repo file. An Edit matcher would have
  delivered the notice ten hours after the wall it exists to precede.
- First tool calls landed at +0.3, +3.0, +0.1 and +0.3 minutes across the four working
  sessions -- before every observed refusal.

Arm (a) fires at the first tool call when the session owns items. Arm (b) defers to the
first Edit-family call, because at tool call #1 a fresh session genuinely has nothing
to be told.

## 5. How we would know it worked

`onboard.py --audit`, read-only, never registered as a hook, over three on-disk
sources: the transcript (session start, first tool call, first Edit, stop refusals),
the event log (`min(at where by == <sid8>)` is the first store write), and the marker.

**Baseline, measured on this checkout 2026-09-03:**

| sid | edits | first edit | first store write | first refusal | refused before writing |
|---|---|---|---|---|---|
| 74de73ca | 13 | +600.4 min | +156.5 min | +17.8 min | YES |
| a276391d | 71 | +8.1 min | +1184.8 min | +19h44m | YES |
| f88f9be7 | 82 | +19.5 min | +65.5 min | +72 min | no |
| 88e2bb0c | 2 | +0.5 min | never | +0.7 min | YES (never wrote) |

**Three of four were refused at a stop before they had ever written to the store, and
`a276391d` edited files for 19h37m without recording a single item.** That is the
operator's complaint, measured.

Metrics: refusal-before-first-write (the headline), lag from start to first write, lag
from delivery to first write (says it was ACTED ON rather than merely delivered),
delivery latency, and the SILENCE RATE -- which should be HIGH, because a low one means
the notice is firing on sessions with nothing to do.

**Caveat that keeps the audit honest:** `worklist.py --compact` rewrites the event log
stamping `by: "compact"`, destroying historical attribution. The audit must skip any
session whose start precedes the log's first entry, or it silently under-counts and
reads as an improvement.

## 6. The anti-nag rule

Silent when: already delivered this epoch; the caller is a subagent; the session owns
nothing AND has not yet edited a file; the session has already written to the store
since arming; anything fails (silence plus one line in the error log -- a PostToolUse
hook must never break a tool call); or the off switch is set.

The third is load-bearing. In the corpus, **38 of 41 sessions never edited a file** and
used 6-39 tool calls each. Every one would have been nagged by an unconditional
first-tool-call notice, and a notice that fires on 38 of 41 sessions with nothing to
say is a notice nobody reads on the other three.

## 7. Out of scope, with the trigger that would bring it back

A mutating-Bash arm. Session `74de73ca` took work on at tool call #3 with a heredoc and
did not touch an Edit tool for ten hours, so arm (b) would have reached it long after
its first refusal. Detecting a mutating shell command is a real, fragile parsing job.
The trigger is stated in advance and is measurable: if delivery lands after the first
refusal in more than one third of the audited cohort, arm (b) is too late and a third
arm keyed on Bash write patterns follows, reusing the pre-bash lib rather than
inventing a parser.

## Tasks

- [ ] Write `.claude/hooks/context/onboard.py`, modelled on `band-notice.py` (every exception swallowed to the error log, `sys.exit(0)` on every path, `additionalContext` output)
- [ ] Register it: PostToolUse (universal, no matcher), plus `--arm` on PostCompact and SessionStart
- [ ] Write `worklist-cases/24-first-touch.sh` and register it in `CASE_FILES`
- [ ] Case: arm (a) fires with the item id and the pre-substituted verb; a second tool call in the same epoch is SILENT
- [ ] Case: arm (b) waits for the first Edit; twenty Bash calls with no items emit nothing (the case that would have nagged 38 of 41 real sessions)
- [ ] Case: the epoch-bump path -- a compaction that fires no hook re-arms via epoch mismatch, and the same sequence WITHOUT the bump stays silent
- [ ] Case: a subagent is silent; a corrupt marker and an unrunnable worklist both exit 0 with empty stdout and one error-log line
- [ ] Case: `--audit` reports refusal-before-write correctly in both directions
- [ ] Add the observational line to the Stop refusal naming when the notice was delivered (changes no verdict)
- [ ] Record the post-change baseline with `--audit --json` BEFORE any `worklist.py --compact`
