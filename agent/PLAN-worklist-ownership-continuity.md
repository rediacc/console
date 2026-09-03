# PLAN: worklist ownership must survive a compaction
Status: draft
Owner: 74de73ca
Updated: 2026-09-03

Scope: teach the worklist store that a session which compacted into a new id is the
SAME session, so it can tick its own items -- without giving any session a way to
seize a genuinely concurrent peer's. Every transcript fact below was measured on this
machine by the design agent, not recalled from a doc page, and the principal
spot-checked the load-bearing ones.

## 0. The incident, and the exact cost

Items `#119d740a`, `#3c8d2d34`, `#51bbba34`, `#7bd69fa8` are tagged `a276391d`.
Session `74de73ca` tried to tick them and was refused:

    #<id> is owned by a276391d; never tick or edit another session's tracking

That rule is correct and stays. What is wrong is the premise underneath it: **a
compaction gave one continuous conversation a new session id**, so the rule fired
against the session's own work.

Cost, doubled: four settled decisions stayed open and were surfaced every stop as
needing the operator, AND turns were spent reasoning about a peer that does not
exist -- including a session brief and a TRAPS entry premised on a peer holding
files, both later corrected. The operator had to say "I've never switched to another
window."

## 1. The evidence that exists on disk (measured 2026-09-03)

Under `~/.claude/projects/-home-developer-console/`.

**E1 -- `continued-in`. STRONGEST.** The predecessor's transcript ends with one
record naming both ids:

    {"type":"continued-in","sessionId":"a276391d-…","continuedInSessionId":"74de73ca-…"}

The only such record in the directory. Scanning the last 256 KB of all 52
transcripts (192 MB) took 19 ms. TIMING CAVEAT that decides the retry design: it was
written 2 h 21 m AFTER the compaction boundary, so it is not available at
PostCompact time.

**E2 -- the head `compact_boundary`. AVAILABLE FIRST.** `74de73ca`'s transcript is
the only one whose first conversational record is a `compact_boundary` with
`parentUuid: null`, carrying `logicalParentUuid` pointing into `a276391d`. The SAME
event uuid appears in the predecessor's transcript stamped with the predecessor's
id -- one event, dual-written, naming both. Two mmap scans: 7 ms.

**E3 -- shared message uuids. THE CONCURRENCY REFUTATION.** For 12:00-13:00 the two
transcripts hold 467 conversational records each and the uuid sets are IDENTICAL.
Two genuinely concurrent sessions share ZERO. This is the discriminator a heuristic
cannot supply, and it is MANDATORY: an edge is recorded only when E1 or E2 fires AND
E3 finds a shared record uuid.

**E4 -- a PreCompact half-edge.** A PreCompact hook runs before the successor exists,
so it can record only "A is compacting at T". A corroborator and a survivability
hedge, never an edge on its own.

**E5 -- heuristics. REFUSED BY DESIGN, and this is the load-bearing decision.** The
candidate is cwd + branch + time-adjacency. Measured here: four sessions all carry
`cwd=/home/developer/console` and `gitBranch=main`, several overlapping in time.
Concurrent sessions in one worktree on one branch are ROUTINE. So the heuristic's
false-positive rate is highest on exactly the population it would be applied to, and
its failure mode is one session silently resolving another's tracking -- the failure
the ownership rule exists to prevent. There is NO heuristic rung. When E1/E2 produce
nothing the answer is "continuity cannot be established", and the operator's existing
`WORKLIST_SESSION_ID` override remains: a human's declaration, recorded as such.

## 2. The adoption model: LINEAGE, not an ownership rewrite

Rejected: appending `reassign` events to move `o` from A to B. It costs one event per
item per hop, and it makes `o` say something untrue about who WROTE the item while
the `(a276391d)` tag inside the item text still says `a276391d` -- a half-corrected
log, worse than an untouched one.

Chosen: one `lineage` event per compaction; nothing rewritten; the tag stays truthful.
`wl_core.owned_by_me` is already the single chokepoint for 25 call sites, so one
alias-set consult there fixes Stop blocking, the guided slice, dead-session cleanup
and the deferral surfaces at once -- and cannot roll out partially.

`--reassign` repairs a FICTION, proven by ABSENCE. `--adopt` records that two REAL
identities are one session, proven by PRESENCE. Opposite evidence directions; they
must not be merged.

### What each surface does

| surface | today | after |
|---|---|---|
| `--tick/--defer/--update/--lease` | refuses an ancestor's item | accepts it; refusal unchanged for a real peer |
| Stop blocking (`classify_items`) | ancestor's items reported, never blocked | they BLOCK -- which is the whole fix |
| `--list --open <me>` | ancestor's items invisible | included, annotated `(via a276391d)` |
| `others-items` block | lists the ancestor as a peer | genuine peers only; a resolvable one gets a `--adopt` line |
| `cleanup_dead_sessions` | tombstones them after DEAD_HOURS | they are mine, never auto-tombstoned |
| `(<prefix>)` tag in item text | `(a276391d)` | UNCHANGED. `a276391d` really did write it |

Deliberately NOT in scope, each with its reason so the omission is not read as an
oversight: request routing (a request is addressed to a LIVE correspondent; the
predecessor is genuinely gone), per-prefix sidecars (already lost today; orthogonal),
and `.sessions` brief liveness (keyed on who is alive).

## 3. Storage: one `lineage` event in the existing log

    {"ev":"lineage","by":"74de73ca","prev":"a276391d","next":"74de73ca",
     "via":"continued-in","ev_id":"<boundary uuid>","shared":467,
     "prev_tx":"…jsonl","next_tx":"…jsonl","line_sha":"<sha1 of the evidence line>"}

Appended through the existing blocking flock, like every other event. No new sidecar.
`shared` and `line_sha` are the audit trail: anyone can re-derive the claim from the
named transcripts, and an edge whose evidence no longer reproduces is visible as such
rather than trusted forever.

**THE PITFALL THAT WILL EAT THIS IF IT IS MISSED.** `wl_store.compact()` rewrites the
log to the minimal set reproducing the current fold and emits only `md`/`add`/`lease`.
It would SILENTLY DELETE every `lineage` event, and every adopted item would revert to
a peer's. The carry-forward is a task below and the control that reds without it is in
section 5.

## 4. Blast radius

Ownership is read or enforced at: `wl_core.owned_by_me` (the predicate), the two
refusal sites in `worklist.py`, `wl_store.classify_items` (Stop blocking),
`wl_store.cleanup_dead_sessions` (both arms), the world/state signatures, and nine
sites in `wl_checks.py`. `wl_checklist.py`, `wl_reggate.py`, `wl_liveness.py`,
`wl_admit.py` and `wl_planfile.py` all inherit the fix and need no edit.

`wl_core.same_session` is NOT changed: its ~40 callers compare PEERS (request
routing, brief roster, dead-session sweep, waiter), and widening it would silently
change all of them.

Test surface that fails if a step is skipped: `worklist-cases/18-identity.sh`'s
`L1_TABLE` DERIVES the me-taking verb list from the dispatch and reds when a verb has
no row, and `test-worklist-v5.sh`'s `CASE_FILES` must list any new case file.

## 5. Proof

New case file `worklist-cases/24-lineage.sh`, registered in `CASE_FILES`. Two
fixture helpers: `plant_chain` (a real boundary, a `continued-in` tail, shared uuids)
and `plant_concurrent` (overlapping timestamps, same cwd, same branch, DISJOINT uuid
sets, no boundary).

The controls that matter:

- **FIRE.** Plant a chain and three items owned by `<prev>`. Before `--adopt` they
  appear in `others-items` and the stop is allowed; after, they are in the open slice,
  `--tick` succeeds, and the stop is BLOCKED. The before-assert is the control --
  without it the case passes on a store that never had the items.
- **THE REFUSAL, and this is the one that matters.** `plant_concurrent`; `--adopt`
  must exit non-zero naming the missing evidence. Then a control on the control: add
  ONLY a boundary and shared uuids to the same fixture and the same command succeeds,
  so the refusal is an evidence gate rather than a blanket no.
- **E3 alone cannot be defeated.** Plant a chain, strip the shared uuids, KEEP the
  `continued-in` line: `--adopt` must refuse. Without this, forging one line is
  enough, and E1 is the easiest line to forge.
- **Store compaction does not eat the edge.** Adopt, run `--compact`, re-run: the
  items are still mine. This case reds against a naive implementation.
- **Nothing changes with no lineage event** -- byte-identical output to today. The
  anti-vacuity guarantee that the fix is additive.

## 6. Residual risks, stated rather than pretended away

- A session can write to `~/.claude/projects/`, so a `continued-in` line is forgeable.
  Out of the threat model for the same reason the operator-answer hole is recorded
  rather than closed: a process that can write there can equally append `reassign`
  events straight into the store. E3 raises the forgery cost from one line to a
  consistent dual-written conversation, which is the honest improvement available.
- A compaction that does NOT change the session id needs nothing and gets nothing --
  three of the four compactions inside `74de73ca` are of that kind, and gate 1
  declines them.
- Making an ancestor's open items BLOCK is a behaviour change. It is the intended one:
  the session becomes blocked on its own work, exactly as it was before the compaction.

## Tasks

- [ ] Write `.claude/hooks/stop/wl_lineage.py`: gate-1 (head `compact_boundary`, `parentUuid: null`), E1 tail scan, E2 mmap joins, E3 shared-uuid refutation (mandatory), bounded reads only
- [ ] Add the alias set and `bind_lineage()`/`lineage_of()` to `wl_core.py`, and one ancestor branch inside `owned_by_me`, keyed on the bound id so a peer's id can never pick up my aliases
- [ ] Leave `wl_core.same_session` untouched, with a comment naming its ~40 peer-comparison callers
- [ ] Add the `lineage` fold arm and resolve the transitive chain at the end of `wl_store.load()`
- [ ] Carry `lineage` events through `wl_store.compact()` -- without this the next `--compact` silently deletes every adoption
- [ ] Add `worklist.py --adopt <me> <prev>`, through the identity check, with NO `--force` and refusal text naming which evidence rung failed
- [ ] Add the `CLI_ADOPT_*` messages beside the `CLI_REASSIGN_*` block
- [ ] Record the edge automatically at PostCompact inside a suppressed exception, and retry on the Stop path only when `others` is non-empty and no edge exists
- [ ] Annotate adopted rows `(via <prev>)` in the guided slice
- [ ] Offer `--adopt` from the `others-items` block when a listed peer has a resolvable edge
- [ ] Add `--adopt` to `L1_TABLE` in `18-identity.sh`
- [ ] Write `worklist-cases/24-lineage.sh` with all the controls in section 5; register it in `CASE_FILES`
- [ ] Run `worklist.py --adopt 74de73ca a276391d` and settle the four items
- [ ] Amend the ownership paragraph in CLAUDE.md and add the TRAPS entry
