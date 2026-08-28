# PLAN: CI-watch enforcement, from "the session remembered" to a ledger join
Status: draft
Owner: unowned (drafted by 9d92d9b6, 2026-08-28)
Updated: 2026-08-28

A session cannot stop while a head IT pushed has no terminal verdict on record
and nothing running to produce one. The enforcement is a join between two local
ledgers, costs no network, and cannot fire on a peer's push by construction.

## 0. Verification status of this plan's own claims

Every root-cause claim below was re-checked against the source by the session
that filed it, because an approved plan's assertion about unread code is a
hypothesis. Confirmed directly:

- `WORKLIST_PUBLISH_REF` is UNSET in this checkout (`echo` of the var is empty),
  so `wl_ci.py:737-739` returns `"unset"` as the FIRST statement of `ci_trouble`.
- `wl_ci.py:740-743` returns `"multi-session"` next; the sessions file carries 19
  entries, so `sole_live_session` has been false throughout.
- `/tmp/claude-worklist/` holds ZERO `cistate`/`cimark`/`ciqueue` sidecars after a
  full night of stops. `ci_trouble`'s first reachable disk write is at
  `wl_ci.py:763`, so it never executed past line 743. This is the empirical
  proof, not an inference from reading.
- `ci_watch_armed` has exactly ONE call site, `wl_ci.py:769`, inside the branch
  reached only after `ci_classify` found a failing job.
- `.claude/agents/pr-babysitter.md:125` does hand out
  `until [ status = completed ]; do sleep 20; done` and call it sanctioned.

## 1. The incident this is paid for

Session 9d92d9b6 pushed branch `0827-1` (PR #579) four times on 2026-08-27/28 and
never once armed a watch on its own initiative. Every CI read happened because
the operator asked or a Stop hook prompted something unrelated.

- run 33125687081: `tsx: not found` (exit 127) in `Quality / Code`; the watchdog
  cancelled 7 sibling jobs. Undiscovered until the operator asked.
- run 33133377611: failed TWICE — the carried trailer gate AND `Quality /
  Security` (hook suite, PASS=1557 FAIL=2, machine-specific test paths). The
  second failure sat undiscovered for a long time.
- run 33135196245: `Quality / Submodule Branches`, because a pointer bump
  demanded a reply to an automated review on rediacc/renet#109. Found only when
  the operator asked "what are we waiting for more than 3 hours?".

Operator: *"Why you don't watch the PR CI process? Actually, stop judge should
have caught that!"*

ONE head carries SEVERAL runs (3c151275 has 33135268915 success AND 33135196245
cancelled), so a receipt keyed on a run id would be wrong. The head SHA is the
key, which is what `.ci/scripts/ci/ci-trace.py` already keys on.

## 2. Root cause

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| a | only fires in-flight; completed-failed not covered | INVERTED, true as a gap | `wl_ci.py:765-768`: no failing job means `"ok"`. In-flight-with-nothing-red is inexpressible |
| b | advisory, not blocking | FALSE | `wl_checks.py:3529` `vadd("ci-red", True, ...)`; always-tier defeats the cadence pause |
| c | needs something present to activate | TRUE, twice | `wl_ci.py:737-739` needs `WORKLIST_PUBLISH_REF`; `:740-743` needs sole liveness |
| d | keys on something that stopped matching | FALSE | `wl_ci.py:562`: a bare `ci-trace` invocation needs no needle |
| e | an earlier check returns first | TRUE | both returns above are the 1st and 2nd statements of `ci_trouble` |

**The decisive structural fact:** `ci_watch_armed` can suppress a block. It has
never been able to cause one. "The machinery already exists" is misleading.

**Neither gate may simply be deleted.** `worklist-cases/09-ci-status.sh` case 131
pins both as deliberate: a second live session may own the red, and an unset
publish ref is a zero-cost opt-out. Both rulings are correct FOR `ci_trouble`,
which cannot prove whose red it sees. This plan does not touch it. It adds an
orthogonal check whose subject is provably owned, which is why it is safe under
multi-session.

## 3. Design: two ledgers and a join

**Push ledger** `<worklist>.cipush-<sid8>`, capped at 20, written ONLY by a new
`post-bash/record-push.sh`: `{at, sha, branch, session}`.

**Read receipts** `<worklist>.ciread`, append-only JSONL capped at 200, written
ONLY by `ci-trace.py` on every terminal path: `{at, sha, exit, reason, jobs,
runs, session, tool}`.

Both paths come from `wl_core.worklist_for(...)`, which `ci-trace.py` already
reaches via its existing `import wl_ci`, so the two agree by construction rather
than by two copies of a path expression.

**The gate is the join.** No network, no git, no subprocess.

`wl_ci.unwatched_push(root, worklist, session_id, live_bg, ack_text)` returns
`none | watched | read | unwatched | red-unacked | downgraded | writer-suspect`:

1. No push-ledger entry for THIS session → `none`, silent, zero cost.
2. A RUNNING `ci-trace` background task matching the head → `watched`. Reuse
   `ci_watch_armed` verbatim; this is the one place it finally does the job it
   was named for.
3. Newest receipt for that sha at-or-after the push:
   absent → `unwatched`; `exit 0`, or `exit 3` (head moved), or
   `exit 2 reason=no-pr` → `read`; `exit 2` otherwise → `unwatched` (a
   non-verdict is not a read); `exit 1` → requires an acknowledgement naming one
   of `receipt["jobs"]`, reusing the `ci_trouble:782-783` matcher so a stop
   message or a `- [?] ... DEFAULT:` deferral both clear it.
4. Ceiling: marker keyed on `sha1(sha + state + jobs)[:12]`, 3 blocks then a
   permanent downgraded note. A new sha or a different job set re-arms it. This
   mirrors `ci_trouble`'s ceiling for the reason its header records: a check that
   demands what a session cannot produce deadlocked this repo for a night.

Call site: `wl_checks.py` just after the `adhoc_watch` block and ABOVE the
`ci_trouble` call. A broken check must SAY SO rather than pass silently.

## 4. "Unread", defended

**Unread = no receipt, written by the sanctioned reader, keyed to the exact head
this session pushed, carrying a terminal verdict; and where that verdict is
non-success, no acknowledgement keyed to (sha, failing-job-set).**

- **It cannot be satisfied by claiming.** The only writer is `ci-trace.py`. A
  session must run the tool; it cannot type its way out. That is the enforcement
  half achieved structurally rather than by another regex.
- **A session may legitimately stop after reading a failure.** Naming the job, or
  filing a `- [?]` item, clears it — `ci_trouble`'s own exit, already load-bearing
  in case 129, and a `- [?]` is reported to the operator every stop so it cannot
  hide.
- **Superseding is free.** Only the NEWEST entry is judged, and `exit 3` (head
  moved) is a terminal answer, so a watch overtaken by a push is not held against
  the session.

## 5. Detecting "there is a pushed head"

**RECOMMENDED: a PostToolUse hook on `git push`.** It fires only in the session
that ran the command and its payload carries `session_id`, so ownership is
established by the event rather than inferred from shared state — the whole
answer to the shared-worktree constraint. The precedent is exact:
`post-bash/cancel-old-ci.sh` already fires on this event and already parses
`src:dst` refspecs.

Failure modes, stated rather than discovered later: a push outside the session's
Bash tool is invisible (desired); it fires on a FAILED push, so record only when
`origin/<dest>` equals local HEAD afterwards; submodule pushes must be excluded
the way `block-unverified-push.sh` already excludes them; prose containing the
words must not over-record, so use `lib/command-scan.sh`'s command-position
matcher; and a silently disabled chain would make it vacuous — see §6.

**Rejected:**
- **Process id** (the operator's suggestion). The defect is the ABSENCE of a
  watcher; you cannot detect an absent thing by its pid. A pid is not durable
  across turns and says nothing about WHICH head is watched, which is the fact
  that matters.
- **`HEAD` vs `@{u}` at Stop time.** Shared worktree: a peer moves HEAD between
  turns. This session publishes with `HEAD:<branch>`, so `@{u}` is often unset.
  And it cannot distinguish my push from a peer's to the same branch.
- **`gh pr list --head`.** A network call on every stop: cost, rate limit, and a
  flaky gate. It also answers "is there a PR", not "did I push".
- **`.ci/cache/prepush-receipt.json`.** Written BEFORE the push, keyed on tree not
  on a push event, and a single file in a shared worktree. It proves gates ran,
  never that a push happened.

## 6. Anti-vacuity: proving the writer is alive

`check-hook-integrity.sh` audits `pre-bash/`, `pre-edit/` and `pre-ask/` only —
`post-bash/` is structurally invisible to it, and the inventory baseline holds
zero `post-bash/` entries. Extend it to a fourth chain and add the new hook to
the shrink-only baseline. No new gate id: that gate is already wired.

Plus a free runtime corroborator, ADVISORY only: compare `origin/<branch>` (a
local ref read) against the newest ledger entry and emit a NOTE on mismatch. A
note and not a block, because a peer pushing the same branch produces the same
observation, and accusing on a peer's push is the failure mode this plan is most
obliged to avoid.

## 7. Sanctioned-tool enforcement, by extension not duplication

Structural first: only `ci-trace.py` writes receipts, so a banned form produces
nothing that discharges the gate. Stronger than any regex, and adds no new list.

One new row in `lib/sanctioned.py` for the variable-assigned loop shape that
slipped both the pre-bash guard and the recipe gate, with `example` + `counter`
that `check_sanctioned_registry.py` re-runs so it cannot rot. **Stated residual:**
a loop whose `gh` call is assigned in an earlier command is not expressible as a
single-command regex; the Stop side catches it via `adhoc_watch`, the pre-bash
side cannot, and that is written down rather than papered over.

Widen `hands_out_loop` in `check-ci-watch-recipe.sh` to an alternative that does
not require the literal `.status` or the quoted `"completed"` — the reason it
could not see `pr-babysitter.md:125`.

## 8. Documentation, so the taught loop matches the enforcement

**`.claude/agents/pr-babysitter.md` is the load-bearing edit** — it is what
`/pr-babysit` inline mode executes verbatim:
- `:125` replace the banned loop with `ci-trace.py --wait --until-final`.
- `:196` "the ONE sanctioned mechanism" must name the script.
- Wake-up section: state that the Stop hook now ENFORCES this.

**`.claude/commands/pr-babysit.md`:** inline mode gains "push, then arm the watch
in the SAME turn; the Stop hook blocks otherwise". Delegate mode §3 gains the
reconciliation — the lead does not push, so its ledger is empty and this never
fires on the lead; it fires on whoever ran the push, and the no-shadowing rule is
unchanged. Both modes: the finish line gains "no undischarged push-ledger entry".

**`.claude/skills/ci-watch/SKILL.md`:** the watch is now a recorded obligation;
exit 2 is not a verdict and discharges nothing.

## 9. Control-first tests

Every new check plants its own defect. Fixtures built by CONSTRUCTION, never by
pattern-substituting real source.

**Stop gate, cases 132-142 in `worklist-cases/09-ci-status.sh`** (no network; the
ledgers are files): entry with no receipt FIRES; a running `ci-trace` is SILENT;
a watch on another ref FIRES; a COMPLETED ci-trace task FIRES (a dead watch is
not a watch); `exit 0` SILENT; `exit 2 timeout` FIRES; `exit 1` with an unrelated
message FIRES naming the job; the same with the job named is SILENT; four stops
block exactly three then downgrade to a note that still reports.

**Case 141 is the most important control here:** a ledger entry under a PEER's
session id must leave this session SILENT.

**Case 142, the no-cost control:** no ledger at all plus a `gh` shim that prints
`GH-WAS-CALLED` — assert silence AND that the shim was never called.

**Push recorder, in `test-hooks.sh`:** fires on a successful push; silent on a
rejected one, on a submodule push, and on prose; fires with `-c` flags between
`git` and `push`; and writes only to its own session's ledger.

**Receipt writer:** green shim → `exit 0` receipt; red shim → `jobs` names every
failing job; **mutation control** — delete the write, re-run, the assertion must
go red, because a receipt assertion that passes against a writer-less script
proves nothing.

## 10. Wiring

**No new `check:ci-*` id**, so `check:ci-parity`'s three-point rule is satisfied
by construction. Everything lands in already-wired gates: the v5 suite, the
claude-hooks gate, `check:ci-watch-recipe`, the ci-trace branch test, and
`check:ci-hook-integrity`. One manifest touch: add `.claude/hooks/post-bash/**`
to the `paths` of the recipe and hook-integrity entries so editing the new hook
selects the gates that judge it.

## 11. Flakiness: what is and is not enforceable

The blocking path touches no network, spawns no subprocess and reads no shared
mutable state. Two honest residuals: a SIGKILLed watch writes no receipt, so the
gate asks for a re-arm (a false positive toward more diligence, bounded by the
ceiling); and a push outside the session's Bash tool is out of scope by design.

**What CANNOT be enforced without flakiness:** "the head has a run in flight" is
not knowable at Stop time without a network read, and a network read every stop
is a flaky gate that will be routed around. This plan does NOT enforce that. It
enforces the local proxy — *you pushed, and there is neither a running sanctioned
reader nor a recorded verdict* — which covers all three of tonight's incidents.

## 12. Shared-worktree safety

1. PostToolUse fires only in the session that ran the command.
2. The ledger is per-session, like every other sidecar.
3. The receipt is SHARED and sha-keyed, so a peer's receipt can DISCHARGE my
   entry but never create one. Shared state only ever makes this gate quieter —
   the safe direction, and why the receipt needs no session key.
4. Case 141 pins properties 1 and 2 with a planted peer entry.

## 13. Sequencing

1. `ci-trace.py` writes receipts, with the mutation control. Inert alone.
2. `post-bash/record-push.sh` + controls + the hook-integrity chain extension.
   Still inert.
3. **Probe** §14 before wiring the gate; do not build on an unverified payload.
4. `unwatched_push` + call site + messages + cases 132-142. First blocking commit.
5. Registry row + widened detector + all three doc edits in ONE commit — the doc
   fixes must land with the widened detector or the tree reds on its own docs.

## 14. What could NOT be determined and needs a probe

1. Is `CLAUDE_CODE_SESSION_ID` guaranteed? Read it best-effort for attribution
   only; the JOIN must stay on sha so an absent var degrades to a shared receipt
   rather than a broken gate.
2. What `session_id` does a TEAMMATE's PostToolUse carry? It decides whether
   `/pr-babysit bg`'s babysitter writes its own ledger or the lead's.
3. Does `tool_response` distinguish a failed push? The design already assumes not
   and falls back to the local ref comparison, but capture the stderr once.
4. **Is `WORKLIST_PUBLISH_REF` deliberately unset here?** Case 131 treats unset as
   a legitimate opt-out, so this plan does not set it — but it means
   `ci_trouble`, `ci_queue_state` and `pr_body_freshness` have ALL been dead in
   this checkout. That is a separate ruling for the operator, and possibly a
   bigger one than this plan.
5. Does the harness drop background tasks across compaction? If so this gate
   fires after every compaction — correct behaviour, but worth knowing first.
