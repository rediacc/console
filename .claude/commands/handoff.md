---
description: Distill the current session into a durable handoff - a hook-enforced agent/programs/<slug>/CHECKLIST.md, an agent/programs/<slug>/ design suite (README + numbered docs + PROMPT.md), a seeded program-state dir (MANIFEST/reports/checkpoints), and a memory pointer - then print the concise pointer prompt for a fresh session. First token of the arguments is the slug; if agent/programs/<slug>/ already exists this runs in update mode (refresh stale sections, re-verify the checklist, regenerate PROMPT.md, report the delta).
argument-hint: "[slug] (kebab-case dir under agent/programs/; omit and one is proposed; existing dir = update mode)"
disable-model-invocation: true
allowed-tools: Bash(ls:*), Bash(git branch:*), Bash(git status:*), Bash(date:*)
---

## Current state

- Existing program suites (empty = none yet): !`ls agent/programs/ 2>/dev/null || echo '(none yet)'`
- Branch: !`git branch --show-current`
- UTC now: !`date -u +%Y-%m-%dT%H:%MZ`

## Mode

The first whitespace-delimited token of `$ARGUMENTS` is the slug. No slug given:
propose one from the session's dominant topic and state it; use AskUserQuestion only
if genuinely ambiguous. If `agent/programs/<slug>/` exists: UPDATE mode (re-verify and refresh
stale sections, regenerate PROMPT.md wholesale, report exactly what changed).
Otherwise CREATE mode.

UPDATE mode also carries the checklist forward: re-verify every deliverable `file:`
token against the tree, and append newly-discovered waves with fresh monotonic `wN`
ids. Never delete an item, never renumber one, never un-tick one. A checklist already
at `Status: done` that gains new waves flips back to `Status: executing`, and the
report says so. `Status: superseded` is terminal: an abandoned program is left alone,
not revived.

## Workflow

1. **Inventory the session.** Collect: operator-locked decisions (verbatim, marked
   `Locked by the operator (do not relitigate)`); verified findings; open decision
   points, EACH with a RECOMMENDED default; the explicitly-out-of-scope ledger;
   spikes (short pre-implementation verifications); which pieces of the scope are
   the Fable-tier challenging ones.

2. **Verify before enshrining.** Every load-bearing code claim is re-checked against
   the live tree before it enters a doc (read-only; fan out Explore agents for
   sweeps). Stamp docs with the verification date and branch from Current state.
   Anything not re-verifiable is labeled a hypothesis. Never write a confident claim
   from memory; never trust a zero from an instrument without a planted control.

3. **Write `agent/programs/<slug>/CHECKLIST.md` before any other file.** It is the first write
   of the invocation, not a wrap-up at the end. `Status: producing`; `Owner:` your
   8-char session prefix (the same one you tag worklist items with); one `dN` line per
   deliverable you are about to write (README, `01-verified-context.md`, every
   `NN-topic.md`, the execution guide, PROMPT.md, and the program-state `MANIFEST.md`
   by its absolute `~` path); one `wN` line per wave in the README's `## Scope`, with
   ids in the README's wave order. The grammar, so a fresh session need not look it up:

   ```
   # Handoff checklist: <slug>
   Status: producing            <- producing|executing|done|superseded, in the first 10 lines
   Owner: 99ccf057              <- 8-char session prefix, required while producing

   ## Deliverables
   - [ ] d1 file:agent/programs/<slug>/README.md
   - [ ] d2 file:agent/programs/<slug>/PROMPT.md
   - [ ] d3 file:~/.claude/projects/-home-muhammed-monorepo-console/programs/<slug>/MANIFEST.md

   ## Waves
   - [ ] w1 Wave A: <one-line title>
   ```

   Deliverables are file-verified: every `file:` path must exist and be non-empty, and
   the tick is bookkeeping while the file is the truth. The Stop hook will not let this
   session stop until every `file:` verifies AND you flip `Status: producing` to
   `Status: executing` -- that is exactly why it is written first.

4. **Write `agent/programs/<slug>/` adaptively** (typical 3-7 files; do not pad):
   - `README.md` with the mandatory sections: title + scope paragraph (names the
     source session, links the memory file and program-state dir); `## Read order`;
     `## Non-negotiable working ethos` (see step 5); `## Staffing` (see step 6);
     `## Scope` with waves and an `**Explicitly OUT**` ledger; `## Operator decision
     points (ask EARLY, in one round)` numbered with RECOMMENDED defaults.
   - `01-verified-context.md` always: verified current state, the holes/numbers, an
     explicit re-verify banner.
   - One `NN-topic.md` per major concern, opening `# NN. Title` plus a status line.
   - Final `NN-execution-guide.md`: Before-anything / Spikes / Waves and ordering /
     Staffing / Gates / Definition of done.
   - Status vocabulary: `Locked` / `RECOMMENDED` / `SPIKE` for planning suites;
     `AS-BUILT` / `frozen` / `forward-looking` when documenting as-built work. Add a
     `spec/` subdir only for large as-built suites.

5. **Ethos block (baked, copy into every README):** Validate, do not believe: every
   file:line reference is a hypothesis, re-verify against the tree, run the real
   thing, read stdout and stderr separately, plant a control before trusting any
   zero. Everything stays local and uncommitted: no commit/branch/push/PR unless the
   operator asks in-task; never `git checkout/restore/stash/clean`; repair forward.
   Testing and concurrency support are first-class deliverables. NO em dashes in any
   authored text, in any language.

6. **Staffing section (baked, its own section in README AND PROMPT.md):** Opus is
   the default for coding sub-agents. **Fable for the challenging pieces AND for
   planning agents.** Sonnet for all translation/naturalization work. At most 2
   concurrent writers with disjoint file ownership stated verbatim in every prompt;
   investigation agents fan out freely; every sub-agent report is spot-checked
   against the artifacts before anything builds on it. The handoff NAMES which
   pieces are Fable-tier.

7. **Seed durable program state** at
   `~/.claude/projects/-home-muhammed-monorepo-console/programs/<slug>/`:
   `MANIFEST.md` skeleton (model policy line; wave/status table; active-agents table
   with their `reports/` paths; discovered-bugs list; checkpoints notes) plus empty
   `reports/` and `checkpoints/` dirs. The execution guide instructs the
   implementing session: every writing/planning sub-agent prompt names its working
   report `reports/<phase>-<agent>.md` (and its brief `reports/<phase>-<agent>-brief.md`
   when one is used); the team-lead reads reports and artifacts, never bare
   summaries; MANIFEST.md updates at every phase boundary; periodic uncommitted-tree
   patches land in `checkpoints/` (a host reboot once destroyed a /tmp scratchpad;
   durable state exists because of that).

8. **Wire in the worklist Stop hook** (fail-closed): the execution guide and
   PROMPT.md instruct the implementing session to seed the shared worklist at start
   (path via `.claude/hooks/stop/worklist.py --path`): one item per wave, tagged with
   the session prefix and carrying the checklist token, seeded as
   `worklist.py --add <me> 'cl:<slug>/<wN> <wave title>'`. The token is what links the
   store item to the checklist: the hook blocks ANY stopping session while a wave is
   neither ticked in `CHECKLIST.md` nor covered by such an item, because an uncovered
   wave is unclaimed work. Tick the `wN` box only after the store item is ticked with
   probed evidence, and once every wave is ticked set `Status: done`. Decision points
   are asked in one early round and parked as `- [?]` if deferred; background
   delegation held as `- [>] (prefix) until:<ISO>Z ...` leases renewed on wake;
   `- [x]` only after probing the artifact; queued future waves stay NOTE lines
   promoted when they start.

9. **Write `agent/programs/<slug>/PROMPT.md` and print it verbatim in chat.** Contents, kept
   concise: mission sentence pointing at `agent/programs/<slug>/README.md` and its read order;
   two-sentence validation ethos; ask-the-decision-points-early instruction; the
   staffing section from step 6; the program-state paths from step 7; the
   `agent/programs/<slug>/CHECKLIST.md` path plus the worklist seeding instruction from step 8,
   spelled out with the literal token format `cl:<slug>/<wN>` so the consuming session
   can seed without reading anything else; the local-and-uncommitted line; the testing
   emphasis; the definition of done.

10. **Append ONE pointer line** to the auto-memory `MEMORY.md` (title, docs path,
    one-line hook). Update mode: refresh the existing line instead of adding another.

11. **Report**: file list with sizes; em-dash scan over every new/changed file
    (must be zero, all languages); the seeded program-state paths; the checklist
    verification state, meaning every `file:` token verified against the tree and
    `Status:` flipped from producing to executing; the printed prompt. In update
    mode, also the section-level delta and the checklist delta (new `wN` ids
    appended, `file:` tokens re-verified, any `done -> executing` flip).

## Constraints

This invocation writes ONLY under `agent/programs/<slug>/` (including `agent/programs/<slug>/CHECKLIST.md`,
which is written first and is the one file this command must never skip), the
`programs/<slug>/` state dir, and the single MEMORY.md pointer line. It never touches
code and never commits. If it delegates verification sweeps, they are held as leased
`- [>]` worklist items.
