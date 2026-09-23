# PLAN: what a session is told at its FIRST TOUCH, and how we would know it changed anything
Status: done
First-Seen: 2026-09-17
Owner: d778be9d (adopted from 74de73ca 2026-09-22)
Updated: 2026-09-23

Every `file:line` anchor below was verified against the tree on 2026-09-03, and the baseline in section 5 was MEASURED on this checkout rather than estimated.

## 0. The ask, and what it actually names

The operator's words: sessions at their start and after a compaction "hit the wall and repeat the same mistakes like completing the job without updating the remainings by invoking stop hook's commands with specific arguments. Currently, we print them in different moments but I suppose not in first touch."

Two failures, which are one failure at two ends of a session:

A. work is taken on and never becomes an item (`--add` never happens), so the store
     cannot describe the session at all; and
B. work finishes without `--tick`/`--update` and without a `## Remaining` section,
     so the stop refuses and the session reconstructs its own history afterwards.

The Stop hook teaches both REACTIVELY. A session that has run a while has been refused often enough to have learned. A session at minute one has not, and the cheapest teacher available to it is the wall.

## 1. Why nothing existing lands at first touch

`handle_session_start` emits the design-docs listing, the plans listing and the checklists. `handle_post_compact` emits STATE.md, RULES.md, TRAPS titles, plans and checklists. **Neither names `--add`, `--tick`, `--update` or `## Remaining`.** The reminders exist, but not the one thing the operator names, and they arrive where they compete with a large system prompt.

`handle_session_start` returns early on `source == "compact"`. That is CORRECT (Claude Code fires SessionStart with source=compact on top of PostCompact, and both handlers would otherwise talk) and is not the gap.

The working precedent for this whole plan is `.claude/hooks/context/band-notice.py`: a PostToolUse hook that speaks ONCE per band per epoch, states facts rather than instructions, and never blocks. Its docstring records why the register matters -- instruction-shaped hook text trips the model's prompt-injection defences and gets surfaced to the user instead of acted on. A trigger
that gets surfaced is a trigger that did not fire.

## 2. The marker

A per-session sidecar `.claude/hooks/context/state/<sid8>-onboard.json`, holding a three-state machine scoped to the context epoch: `armed` -> `await-edit` -> `delivered`.

**Its own file, not a key in the shared band state.** `band-notice.py` load/saves that file on every tool call; two hooks on one event may run in parallel and a last-writer-wins clobber would silently lose either the marker or the band ladder.

Armed at BOTH SessionStart and PostCompact, idempotent inside 120 seconds because a single compaction fires both. It writes `epoch: null` deliberately: at PostCompact the registered hooks may run in parallel, so `--arm` cannot know whether the epoch counter has been bumped yet, and reading it there would be a race. The next tool call adopts whatever epoch it sees, in a
single-writer context.

**The asymmetry that matters:** an in-place compaction can fire NEITHER SessionStart nor PostCompact. It still moves the epoch, via the usage-drop backstop in `band-notice.py` -- the only thing in the tree that sees that case. So a marker whose recorded epoch differs from the current one re-arms itself. That mismatch is how the marker learns about a compaction no hook saw.

## 3. What first touch says

Two variants, never both, at most one emission per epoch, ~170 tokens, in the factual register.

**Arm (a), the session owns items:** its own open rows, the store path, the sentence that the Stop hook compares those rows against the last `## Remaining` section, and the three verbs that change a row -- with the session prefix ALREADY SUBSTITUTED. The operator's phrase is "commands with specific arguments", and the most common argument error is the identity prefix, which the
identity check refuses. Pre-substituting removes that error class for zero extra lines.

**Arm (b), the session owns nothing and has just edited its first file:** that it owns 0 items, `--add` and `--tick` with the evidence requirement, and the measured baseline from section 5.

**Deliberately left out**, each for a reason: `--lease`, `--brief`, `--ask`, `--state`, `--triage` (none is the named failure, and every extra line lowers the odds the three that matter are read); the docs, plans and checklists (already delivered elsewhere, and repeating them is what makes those blocks skimmable); the crons, the judge and the deferral audit (each is actionable only
when it fires, so the wall is the right teacher for them); and any imperative framing at all.

## 4. When it fires

**"First touch" means the first TOOL CALL of the epoch, not SessionStart output and not the first Edit.** Both alternatives were tested against the transcript corpus and both lose:

- SessionStart context arrives behind a large system prompt and two other blocks. This
repo has already concluded a wall of text there is skimmed.
- An Edit-family matcher fails on measurement: session `74de73ca`'s first Edit was at
+600 minutes; its first stop refusal was at +17.8 minutes. Its third tool call, at +1.1 minutes, was a Bash heredoc writing a repo file. An Edit matcher would have delivered the notice ten hours after the wall it exists to precede.
- First tool calls landed at +0.3, +3.0, +0.1 and +0.3 minutes across the four working
sessions -- before every observed refusal.

Arm (a) fires at the first tool call when the session owns items. Arm (b) defers to the first Edit-family call, because at tool call #1 a fresh session genuinely has nothing to be told.

## 5. How we would know it worked

`onboard.py --audit`, read-only, never registered as a hook, over three on-disk sources: the transcript (session start, first tool call, first Edit, stop refusals), the event log (`min(at where by == <sid8>)` is the first store write), and the marker.

**Baseline, measured on this checkout 2026-09-03:**

| sid | edits | first edit | first store write | first refusal | refused before writing |
|---|---|---|---|---|---|
| 74de73ca | 13 | +600.4 min | +156.5 min | +17.8 min | YES |
| a276391d | 71 | +8.1 min | +1184.8 min | +19h44m | YES |
| f88f9be7 | 82 | +19.5 min | +65.5 min | +72 min | no |
| 88e2bb0c | 2 | +0.5 min | never | +0.7 min | YES (never wrote) |

**Three of four were refused at a stop before they had ever written to the store, and `a276391d` edited files for 19h37m without recording a single item.** That is the operator's complaint, measured.

Metrics: refusal-before-first-write (the headline), lag from start to first write, lag
from delivery to first write (says it was ACTED ON rather than merely delivered), delivery latency, and the SILENCE RATE -- which should be HIGH, because a low one means the notice is firing on sessions with nothing to do.

**Caveat that keeps the audit honest:** `worklist.py --compact` rewrites the event log stamping `by: "compact"`, destroying historical attribution. The audit must skip any session whose start precedes the log's first entry, or it silently under-counts and reads as an improvement.

## 6. The anti-nag rule

Silent when: already delivered this epoch; the caller is a subagent; the session owns nothing AND has not yet edited a file; the session has already written to the store since arming; anything fails (silence plus one line in the error log -- a PostToolUse hook must never break a tool call); or the off switch is set.

The third is load-bearing. In the corpus, **38 of 41 sessions never edited a file** and used 6-39 tool calls each. Every one would have been nagged by an unconditional first-tool-call notice, and a notice that fires on 38 of 41 sessions with nothing to say is a notice nobody reads on the other three.

## 7. Out of scope, with the trigger that would bring it back

A mutating-Bash arm. Session `74de73ca` took work on at tool call #3 with a heredoc and did not touch an Edit tool for ten hours, so arm (b) would have reached it long after its first refusal. Detecting a mutating shell command is a real, fragile parsing job. The trigger is stated in advance and is measurable: if delivery lands after the first refusal in more than one third of the
audited cohort, arm (b) is too late and a third arm keyed on Bash write patterns follows, reusing the pre-bash lib rather than inventing a parser.

## Numbering note, 2026-09-03

This plan was written naming `24-first-touch.sh`. Case slot 24 was taken in the meantime by `24-lineage.sh` (PLAN-worklist-ownership-continuity), so the file is `25-first-touch.sh`. `CASE_FILES` in `test-worklist-v5.sh` is an explicit ordered list rather than a glob -- ORDER IS THE CONTRACT, per its own comment -- so the number is not cosmetic and a collision would have been a
silent overwrite.

## Tasks

- [x] Write `.claude/hooks/context/onboard.py`, modelled on `band-notice.py` (every exception swallowed to the error log, `sys.exit(0)` on every path, `additionalContext` output)
- [x] Register it: PostToolUse (universal, no matcher), plus `--arm` on PostCompact and SessionStart
      LEDGER LAG, closed 2026-09-09: `.claude/settings.json:112` (PostToolUse, no `matcher`
      key, unlike the `Bash`-matched group above it), `:189` (PostCompact) and `:215`
      (SessionStart) both run `onboard.py --arm`.
- [x] Write `worklist-cases/25-first-touch.sh` and register it in `CASE_FILES`
- [x] Case: arm (a) fires with the item id and the pre-substituted verb; a second tool call in the same epoch is SILENT
      Closed 2026-09-23: `test_25_arm_a_fires_at_the_first_tool_call_carrying_the_id_and_the_prefix`
      in `.claude/rediacc_hooks/tests/test_wl_first_touch.py`. It asserts the notice on a BASH
      call (arm (a), not arm (b)), the item id, all three pre-substituted verbs, the ABSENCE of
      the ambient `deadbeef` prefix, silence on the next call, and `state == delivered`.
      Two plants proved it can fail: replacing `"\n".join(rows[:12])` with `""` and pinning
      `me = "deadbeef"` each turned the case red, and `git diff` confirmed the hook byte-identical
      after both reverts.
- [x] Case: arm (b) waits for the first Edit; twenty Bash calls with no items emit nothing (the case that would have nagged 38 of 41 real sessions)
- [x] Case: the epoch-bump path -- a compaction that fires no hook re-arms via epoch mismatch, and the same sequence WITHOUT the bump stays silent
      Closed 2026-09-23: `test_25_an_epoch_bump_re_arms_and_the_same_sequence_without_one_stays_silent`.
      The control runs FIRST: three identical tool calls with the epoch unmoved must all be silent
      before the bump is allowed to break the silence, because an assertion that a bumped epoch
      speaks again passes equally on a hook that speaks on every call. Planting `if
      m.get("state") == "delivered": sys.exit(0)` (no epoch term) reds the bump leg; deleting the
      early exit entirely reds the control leg.
- [x] Case: a subagent is silent; a corrupt marker and an unrunnable worklist both exit 0 with empty stdout and one error-log line
- [x] Case: `--audit` reports refusal-before-write correctly in both directions
      Closed 2026-09-23, and the audit itself was BUILT for it: section 5's tool did not exist,
      `--audit` only dumped the marker JSON. `onboard.py` now carries `scan_transcript`,
      `store_first_writes`, `audit_rows`, `audit_summary`, `audit_report` and `audit_main`, with
      `--json` and `--session <prefix>`. Four cases cover it, all in `test_wl_first_touch.py`:
      both directions on a built cohort (refused at +5 with no write until +20 against a write at
      +2 refused at +8), the compaction-floor skip, the three empty-cohort refusals, and the
      wording control. Plants: always-YES and always-NO each red exactly one direction, disabling
      the floor skip reds three cases, and turning the empty-cohort exit into 0 reds the
      anti-vacuity case.
- [x] Add the observational line to the Stop refusal naming when the notice was delivered (changes no verdict)
      DONE 2026-09-23. `wl_checks.py` cross-imports `onboard` (best-effort, not a real sibling --
      wrapped in `try/except ImportError`, falls back to `onboard = None`, since the crash-test
      fixture `test_wl_cadence.py::test_222j` copies only `.claude/hooks/stop/*.py` and a hard
      import there took the whole hook down; caught by running that suite before landing). Added
      `worklist_messages.N_ONBOARD_DELIVERED`. Two lines beside `wl_checks.py:4197` read the
      marker via `onboard.load_marker(session_id)` and append the line when `state == "delivered"`.
      Verified: `test_wl_cadence.py` 39/39, `test_wl_first_touch.py` 15/15, `check:ci-python-lint`
      clean on both touched files, `check:ci-python-types` shows zero new findings caused by this
      change (the one remaining `wl_checks.py` finding, `tiers` var-annotated, predates this edit
      and is outside this box's diff).
- [x] Record the post-change baseline with `--audit --json` BEFORE any `worklist.py --compact`
      Closed 2026-09-23, recorded in `## Baseline re-measured 2026-09-23` below. No
      `worklist.py --compact` was run by this session.


## Progress 2026-09-03

`.claude/hooks/context/onboard.py` (239 lines) and `worklist-cases/25-first-touch.sh` (138 lines) are written and driven directly. Verified by hand across every path: unarmed is silent; arm (a) emits once with the session prefix pre-substituted and stays silent on the next call in the same epoch; arm (b) stays silent across five non-edit tool calls, advances the marker to
`await-edit`, then emits on the first Edit and not again; a subagent is silent; the off switch works; a corrupt marker still exits 0 with no stray stdout.

**One real bug found while testing, and it is worth recording because the code carried a comment claiming the opposite was handled.** `worklist.py --list --open <me>` exits **1** for an EMPTY slice, so keying "can I answer?" on the exit code collapsed *owns nothing* into *cannot say* — and arm (b) could therefore never fire at all. It now keys on the output, and the converse is
asserted as its own case: a store that REFUSES to answer (identity mismatch) must produce silence, never the confident "you own 0 items" notice.

Also corrected: this plan named `24-first-touch.sh`, but slot 24 went to `24-lineage.sh` in the meantime. `CASE_FILES` is an explicit ordered list, not a glob, so the collision would have been silent.

Still to do: register the hook (PostToolUse universal, plus `--arm` on PostCompact and SessionStart), add `25-first-touch.sh` to `CASE_FILES`, and the two observability items. Registration is deliberately last: an unregistered hook is inert, so nothing can misfire while the cases are still being proven.

## Baseline re-measured 2026-09-23

`.claude/hooks/context/onboard.py --audit --json < /dev/null`, exit 0, 4.5 seconds over 1.5 GB of transcripts. Shape: **176 transcripts scanned, 116 audited, 60 skipped, 2,773 store events, log floor `2026-09-04T19:50:13Z`**.
Sixty skips are the floor rule doing its job, and `74de73ca` (the first row of the 2026-09-03 table) is one of them: a `--compact` has since erased its attribution, so it is now unmeasurable and is reported as such rather than counted as a session that never wrote.

**The working sessions, which is the slice comparable to section 5.** Lags are minutes from the session's first timestamped record.

| sid | edits | first edit | notice | first store write | first refusal | refused before writing |
|---|---|---|---|---|---|---|
| 8f55d4f0 | 45 | +21.1 | +1589.6 | +1589.6 | +1588.4 | YES |
| f5e68c5a | 1 | +0.6 | none | never | never | no |
| f4da5c2e | 540 | +217.0 | +0.1 | +423.1 | +56.0 | YES |
| d778be9d | 872 | +51.0 | +41.6 | +0.2 | +0.3 | no |
| f031d897 | 1 | +0.9 | none | never | never | no |
| 29d4d08f | 7 | +1.0 | none | never | never | no |
| 3d3db1c8 | 6 | +1.1 | none | never | never | no |

**Refusal-before-write is 2 of the 7 that edited a file (28.6%), against 3 of 4 (75%) before the change.** The whole-cohort figure is 2 of 116 (1.7%) and it is NOT the comparable number: 109 of those 116 never open a file at all, so the rate over everything measures the corpus rather than the notice. Both are printed side by side for exactly that reason.

The other metrics: 113 of 116 silent (97.4%, and high is correct), 3 deliveries with a median latency of +41.6 minutes, one session that wrote AFTER a delivery, and the section 7 trigger NOT met.

**Two defects that only a live run could surface, both now fixed and both with a control.**

The `notice -> first store write` median came out at **-0.1 minutes** on the first run. Folding in sessions whose write PRECEDED the notice made a metric whose entire claim is "the notice was acted on" report a negative lag, which reads as acted on six seconds early. It now counts only sessions that wrote after a delivery, and prints how many contributed.

`f4da5c2e` reported its first refusal at **-2.0 minutes**. A resumed session opens a NEW transcript whose head replays records from the context it continues, stamps and all: that file begins at 12:05:08 and its fourth record is a `Stop hook feedback` stamped 12:03:10. Charged to the session, it made one that was genuinely refused at +56 look refused before it had started.
Anything stamped earlier than the first record is now counted as carry-over and never attributed. It is not rare: **106 carry-over records across the 116 audited sessions.**
