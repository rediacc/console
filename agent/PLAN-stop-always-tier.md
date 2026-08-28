# PLAN: the always-tier, and three checks that could never reach a reader
Status: landed
Owner: unowned (drafted by 9d92d9b6, 2026-08-28)
Updated: 2026-08-28

Operator: *"you do not listen other channel's messages! Stop hook should detect
it any bombard you with messages until you listen. Not just you also the other
contexts. Our stop hook app is broken for some points. We have implemented too
many things there but there are 'always to do' list that we must check no matter
what!"*

## 0. One-line diagnosis

The `always` tier has a written admission rule at `wl_checks.py:2957-2963` and
three checks VIOLATE it while sitting in the rotating tier. `no-waiter-asked` is
the worst: it calls `wl_wait.bump_ask_nolisten(...)` at `wl_checks.py:3957`,
unconditionally, at COMPUTE time. Its escalation ladder therefore advances on
every stop whether or not the session ever sees a rung. The tier comment claims
rotation is safe because "everything else is recomputed from artifacts each stop,
so showing one at a time loses nothing"; for this check that sentence is false,
and `R_FOCUS_MORE`'s promise that "rotation forgets nothing" is a lie in exactly
the case the operator hit.

## 0.1 Claims verified before filing (an unread plan's claims are hypotheses)

- `wl_wait.bump_ask_nolisten(worklist, me8)` sits at `wl_checks.py:3957` INSIDE
  the vadd block — confirmed by reading it.
- `/tmp/claude-worklist/` holds `.waiternudge-e580532b` and NO
  `.waiternudge-9d92d9b6`. Since `no-waiter` requires
  `nudges_ignored(...) >= WAITER_GRACE_NUDGES` (3), it was STRUCTURALLY unable to
  fire for the failing session all night.
- `outq_drain` has exactly ONE call site, `wl_checks.py:5070`, on the allow path.
  Empirical proof: this session carried 4 unread sub-agent reports through 57
  blocking stops and was never told.

## 1. Verified mechanics

**The always tier is genuinely unconditional.** `wl_checks.py:4491`:
`shown = [t for _k, a, t in violations if a]`, then the rotating pick is
APPENDED. Always entries never enter `served` (`:4479`), so they consume no
rotation slot. `always_now` (`:4320`) defeats the cadence pause at `:4331`.
**So a tier flip alone is sufficient for surfacing** — but not for escalation
shape, lapse detection, or scarcity.

**Rotation is LRU with a battery-order tiebreak** (`:4482-4486`): every
never-served key ties at `-1`, broken by position in the file. **23 rotating keys
sort ahead of "you are not listening"** — `open-items`, `defer-expired`, `brief`,
`agent-state`, `docs-drift` and 18 more. On the observed night listening sat
roughly fifth in a live queue while its ladder burned a rung per stop.

## 2. The admission rule, made explicit

The file already describes the missing ground at `:2965-2970` — *"The rule is not
'important' ... it is WHO PAYS for the silence. These are the ones where another
session is already blocked"* — and attaches it to `carry_through_pause`, a
WEAKER mechanism that survives a cadence pause but NOT rotation. The set is
`{"requests", "no-waiter-asked", "no-waiter"}`. **The file identified the exact
three checks where another party pays and left all three rotatable. That is the
seam.**

Proposed rule for the tier comment:

> A check is an INVARIANT (`always=True`) iff at least one of:
> - **I1 compute-time budget** — the producer spends a latch, bumps a counter or
>   pays for an API call while computing. Hiding the text spends the budget on a
>   line nobody read.
> - **I2 someone else pays** — the remedy is owed to a party that cannot observe
>   this session's silence.
> - **I3 hook integrity** — the hook cannot see, so its silence is not evidence.
>
> **Corollary that keeps the tier small:** if a check qualifies only under I1,
> prefer moving its latch to DISPLAY time over promoting it.

## 3. Tier changes

**PROMOTE (3):** `no-waiter-asked` (`:3941`, I1+I2 — the headline change),
`no-waiter` (`:3889`, I2), `requests` (`:3239`, I2 — its own comment says "the
payload rides inside the obstacle", and a delivery mechanism that can be rotated
23-deep is not one).

**FIX THE LATCH, do not promote (2):** `submodule` (`:3455`) and `solo-grind`
(`:2220`) both stamp state at compute time, so a rotation miss silently starts a
suppression window for a message never shown. Latch on display instead.

**DECLINED, on evidence:** `answers` (the peer already discharged its
obligation — and the file already discriminated correctly, putting `requests` in
`carry_through_pause` but not `answers`), `defer-expired`, `undefaulted`,
`unjustified`, `completion`, `brief`, `stale-local`, `diverged`, `pr-stale`,
`ci-waiting`, `loop-died`, and ~19 others. All recomputed each stop with no
third party.

**NOT A TIER PROBLEM AT ALL:** `unread-reports` (`:3744`) is an `outq` advisory
at priority 2, and `outq_drain` runs only on the ALLOW path. A continuously
blocking session NEVER sees a teammate's report. Its stated excuse — "there is no
honest evidence a stop could demand for 'I read it'" — is untrue:
`wl_report.py --read <me> <id>` is exactly that, and the message already prints
it. Graduate it: advisory under 15m, rotating after, invariant at 45m or on any
`[SILENT]` report.

## 4. "Bombard until you listen" — the ladder is unreachable today

`V_ASK_NOLISTEN_LADDER` has five well-designed rungs, but with ~5 rotating keys
ahead of it the FIRST sighting lands at round >= 5, the terminal rung. Rungs 2-4,
which carry the only new information, cannot be reached in a crowded session —
and rung 5's "It has now asked %d times" is false: it asked once, out loud.

**The tier flip fixes this by construction:** once always, compute time and
display time coincide, so bump-at-compute becomes correct and the ladder walks
1→2→3→4→5. No relocation needed.

## 5. The grace counter is resettable BY THE FAILURE

`wl_wait.nudge()` at `wl_wait.py:451-455` UNLINKS the counter on a fresh
heartbeat. So arming one waiter zeroes it; when that waiter lapses, the count
must climb from zero over another 30+ minutes. **A session that arms one
60-minute waiter every few hours keeps `no-waiter` permanently below threshold.**
That is exactly the failing session's shape, and the absent
`.waiternudge-9d92d9b6` is the proof.

Second gate failure: `no-waiter` requires `live_work_crons` (`:3880`), and the
file itself records at `:3897-3903` that a measured live session had no cron
directory "so the check could NEVER fire for it". That produced `no-waiter-asked`
as a workaround; the underlying gate was never repaired.

**Fixes:** decay the counter instead of unlinking; replace the `live_work_crons`
gate with `wl_wait.outstanding_work(...)`, the same predicate the nudge uses.

## 6. Lapsed vs never-armed are indistinguishable

`wl_wait.wait()` unlinks the heartbeat on BOTH exits (`:243` timeout, `:302`
fired). Combined with the reset above, **arming a waiter buys 30+ minutes of
guaranteed silence after it dies.** That is a perverse incentive, not a gap.

**The tombstone:** replace both unlinks with a write of
`EXPIRED <stamp> <timeout|fired>` to the same path. Freshness is mtime-based with
`HEARTBEAT_STALE_S = 60`, so a tombstone ages out within a minute and NO existing
caller changes behaviour — the cheapest possible carrier. Add `waiter_lapsed()`;
a lapse fires immediately with no grace, since the session already accepted the
contract. New `V_WAITER_LAPSED` wording names which of the two happened.

**Settle a wording inconsistency in the same pass:** `V_NO_WAITER` says
`--timeout 60`, `V_ASK_NOLISTEN_CMD` says `900`, `wl_wait.HELP` says `60`. A
session told both picks 60 and lapses in an hour.

## 7. Keeping the invariant tier scarce

The file's own warning applies: "a prompt that fires always is a prompt that gets
skimmed" (`:3123`). Three defences:

1. **Graduation gate** — a check enters the tier when its remedy is fully in
   reach NOW, not the instant its condition is true.
2. **The collapse** — sort invariants by an explicit severity index rather than
   battery line order, quote at most `ALWAYS_FULL_MAX = 2` in full, render the
   rest as one line each under "also blocking, in brief". **Nothing is dropped:**
   every invariant is NAMED every stop, at most two are QUOTED.
3. **The pinned set** — `test-always-tier.py` AST-parses every `vadd` and asserts
   the always-key set equals a pinned literal, plus that every
   `carry_through_pause` member is either always or documented-exempt. **That
   third assertion is the one that would have caught this seam.**

Measured expectation: `focus.served` shows the always tier was effectively empty
across all 57 blocks, and the three promotions are near-mutually-exclusive in
practice. Realistic steady state is 0 or 1 invariant, not five.

## 8. Sequencing (each step independently testable)

1. Tombstone in `wl_wait.py` — isolated, no caller changes.
2. Decay the nudge counter.
3. Repair `no-waiter`'s gates; still `always=False`, to prove the FIRING change
   before the tier change.
4. The three tier flips + rewrite the tier comment + trim `carry_through_pause`.
5. The collapse renderer.
6. Move the `submodule` and `solo-grind` latches to display time.
7. `unread-reports` graduation.
8. Wording pass.
9. The pinned-set control.

**Keep the violation tuple 3-wide.** Six unpack sites depend on it, and widening
it would collide with the peer's live judge work for no benefit.

## 9. Controls (control-first)

**The proving case, which must FAIL before and PASS after:** a crowded session
with an open ask, no waiter, and five unrelated rotating violations must still
hear "NOT LISTENING" on the FIRST stop. Today it fails — `no-waiter-asked` sorts
23rd and the pick goes to `open-items`.

Plus: ladder rungs 1→2→3→4 on four consecutive stops; a confirmed waiter silences
it, an unverifiable one does not; tombstone with zero nudges blocks immediately
while never-armed with zero nudges stays silent; nudge decay leaves 2 not 0;
three simultaneous invariants quote exactly two and name the third; a rotated-away
submodule move re-offers next stop; and `carry_through_pause` gets its first
behavioural case ever (§1.5: it is currently untested).

No new `check:ci-*` id — everything rides `test-worklist-hooks.sh` and
`test-hooks.sh`, both already wired.

## 10. What could NOT be determined

1. **Why the ask-ladder never surfaced across ~6 hours.** The counter exists and
   bumps, and the queue is 23 deep, but which stops actually COMPUTED the check
   is unreconstructable. Two innocent explanations survive (a live poll cron
   silences it at `:3925`; a recipient brief aged past
   `WORKLIST_REQUEST_DEAD_MIN` at `:3932`). **The mitigation is itself a
   deliverable:** when a listening check computes and declines to fire, record
   the declining gate in `state_doc` and print it. A check that cannot explain
   its own silence cannot be debugged afterwards — which is exactly the position
   this analysis is in.
2. Whether `requests` will over-fire once promoted (no age gate; broadcast asks).
   Measure for a day; if it does, the fix is an ack-age gate, not a demotion.
3. `ALWAYS_FULL_MAX = 2` is a knob chosen from live evidence, not derived.
4. Whether `HEARTBEAT_STALE_S = 60` is right for tombstone-vs-live on a loaded
   box; `TICK_S` was not read.

## 11. Collision risk — this decides sequencing

Session `e580532b` is live and editing `wl_judge.py`, `test-judge-schema.py`,
`TRAPS.md` and neighbours of `wl_checks.py`.

- `wl_checks.py` — **HIGH overlap.** Steps 3-7 all touch it; ~5,086 lines.
- `wl_wait.py` — LOW-MEDIUM. Not on their list.
- `worklist_messages.py` — MEDIUM; a concurrent edit produces a confusing
  format-parity failure rather than a clean conflict.
- `wl_judge.py`, `test-judge-schema.py`, `TRAPS.md` — **leave alone entirely.**

**Protocol:** do steps 1, 2 and 9 first (they touch only `wl_wait.py` and a new
test file, so they land while the peer works). Batch steps 3-7 into ONE announced
window on `wl_checks.py`. Announce it by cross-session request **and arm a waiter
in the same turn** — doing otherwise while implementing this plan would be the
joke telling itself.

## Landed

`12de2e910` — all three promotions (`no-waiter`, `no-waiter-asked`, `requests`),
`unread-reports` graduated, the tombstone in `wl_wait.py`, nudge decay,
`ALWAYS_FULL_MAX=2` collapse, `test-always-tier.py` pinning the always-key set.
Tier 21 -> 27. Independent suite run: 854/0.
