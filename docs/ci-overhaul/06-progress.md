# Progress: what has actually been built

The other documents in this folder describe the plan. This one records what
landed, with evidence, and it is the file to update when the code moves. It was
created on 2026-07-29 because the design docs had drifted **44 commits** behind
`.ci/`, `.github/` and `.claude/` on branch `0728-2`, which is exactly the
failure the Stop hook's design-doc check now blocks.

Everything below is on **PR #543** (branch `0728-2`) unless stated otherwise.
README's line "Nothing in it has been built" is no longer true; start here.

---

## Wave A: landed and MERGED (PR #541, 2026-07-28T02:51Z)

**A2 is proven on real scheduled traffic**, with a boundary that lands exactly on
the merge:

    2026-07-24 cancelled   2026-07-25 cancelled
    2026-07-26 cancelled   2026-07-27 cancelled
    <- #541 merges ->
    2026-07-28 FAILURE     2026-07-29 FAILURE

Twelve consecutive nights of failures laundered into `cancelled`, then honest
failures the first night Wave A's code was on main. A2b fired too: issue **#544
"Nightly CI is red"** is open.

**A5 clause 1 (a GREEN scheduled run) is still unmet.** The 2026-07-29 nightly
failed only `Quality / Code` (plus `CI Complete` as a consequence), on
`docker/login-action v4.5.1 -> v4.5.2`. That needs no work: main's
`scripts/check-actions.ts` has **zero** references to `isReleaseDeferred`, while
this branch adds 107 lines including it, so main is running the gate without its
release-age window. #543 is the fix.

## Wave B: built, two acceptance criteria still open

Against `05-execution-guide.md`:

| Criterion | State |
|---|---|
| (a) a reduced run demonstrated | **NO** - needs a throwaway PR |
| (b) `pointer_bump_only` observed TRUE | **NO** - needs a pointer-only push |
| (c) reconciler fails on a planted mismatch | **YES**, locally: 62 assertions, controls fire |
| (d) every new gate seen to fire | **YES** |

**D9 is fixed and the proof is in its own reason string.** It was
`merge commit <x> in the walk` on 13 of 13 runs, meaning the walk aborted
immediately on the synthetic `refs/pull/N/merge` head. It now reads
`no baseline within 5 commits`: the walk runs and terminates on its own cap.

**The baseline resolver is FOUR of five conditions on real traffic.** Round 23's
`scope-baseline.json` rejected the green commit `bb9dd6794` with
`unreconciled-outcome`, not `not-green`. Reading `scope-engine.cjs:151-164`, that
is the *last* of five checks (`plan.reconciled !== true`, line 161). So that
commit was green, carried an attested skip plan, and the plan was full-mode. Only
the `reconciled` flag is missing, and the shadow reconciler never sets it. One
flag is the entire remaining distance, and D-1 forbids closing it until the
reconciler is trusted.

**The reconcile shadow's "WOULD HAVE PASSED" is vacuous and must not be banked.**
It runs on `ubuntu-slim` in ~8-11s against the hard 15-minute cap, node present,
and reports 17 planned keys against 93-94 jobs. But all 17 entries are
`{"run": true, "reason": "full"}`, so it reconciles trivially. It proves the
reconciler does not crash, not that it can detect anything. **#543 can never
produce a non-vacuous reconcile**, because it touches `.ci/` and is therefore
fail-closed to `mode: full`.

**D5 has a live receipt.** `web-27a7cd16729b` and `rdc-334c6306793e` are now
distinct where `RDC_TAG` was literally assigned `"$WEB_TAG"`. Changing
`--extra` (the renet tag) changes the web tag, which closes the most likely
stale-reuse hole. The weekly bucket is at `generate-tag.sh:269`.

**#538 is fixed and proven by execution**, not by reading: `printf -v` replaces
three `eval` sites in `common.sh`, and the CI-path proof arrived when
`Stage Artifacts` went green (it runs the `build-pages.sh --output` caller).

**`generate-tag.sh`'s renet input list: the plan was wrong.** It wanted
`.ci/scripts/infra/build-renet.sh` added because nine jobs run it. It must not
be: that script builds a dev binary for jobs that never receive this tag
(`ct-tests.yml` declares exactly two inputs, `full_suite` and
`pointer_bump_only`, and never references `renet_tag`). Adding it would cost a
45-minute rebuild on every harmless edit. The exclusion and its reason are now
recorded at `generate-tag.sh:105-112`.

## Wave C: unblocked, not started

**The `rediacc-autopilot` App EXISTS and is validated.** app_id `4409539`,
installation `149445627`. It holds **no bypass** on console ruleset `12344707`
(the actors are `RepositoryRole:5` and `Integration:2772000`), and its
permissions are `actions:write, contents:write, issues:write, metadata:read,
pull_requests:write` - notably **no `administration` and no `workflows`**, so it
cannot rewrite the CI that judges it. Credentials are staged as
`AUTOPILOT_APP_ID` and `AUTOPILOT_PRIVATE_KEY`.

That invariant is now pinned by `.ci/scripts/quality/check-autopilot-no-bypass.sh`
with six controls. The gate is built around a measured trap: console is public,
so an unauthenticated GET of the ruleset answers **200 and silently omits
`bypass_actors`**, which would make a naive gate pass for ever. Presence of the
field is asserted before its contents.

Not wired into `npm run ci`: reading `bypass_actors` needs `Administration: read`,
which no current app token grants and which would collide with
`check-no-app-admin-perm.sh`. Unverified: the App's `repository_selection` list
is unreadable from a session, so "it can mint a token for console" is untested.

## The Stop hook (`.claude/hooks/stop/worklist.py` v5)

Not in the original plan; added 2026-07-29 because the old gate watched the wrong
queue. It blocked only on `- [ ]`, and this session held **zero** open items all
night while the harness Task list carried six pending.

Now: harness task-list awareness, a required `## Remaining` section naming every
open task id, `DEFAULT:` on every deferral, a session brief, one-cron enforcement
read from `session_crons`, a 250-600 character single-paragraph handover, a
`PostCompact` hook that hands it back, a `SessionStart` hook that forces these
design docs into context, this drift check, and a haiku judge on quiet stops.
`MAX_BLOCKS` is deleted: there is no escape hatch.

Two measured facts that constrain any future change:

- **`claude -p` fires the project's Stop hook**, and `--settings '{"hooks":{}}'`
  does NOT suppress it. The `STOPHOOK_CHILD` env guard is the only thing that
  works, and it is the first statement of `main()`.
- **The Stop event already carries** `last_assistant_message`, `session_crons`
  and `background_tasks`. Do not reconstruct any of them from the transcript;
  doing so is what made the gate fire on its own author.

## Corrections to the other documents

- README: "Nothing in it has been built" is stale. Wave A merged, Wave B built.
- `01-verified-context.md`: the nightly was red **12 of 12**, not four nights.
- The plan's `generate-tag.sh` renet-input instruction is wrong; see above.
- Wave C's App blocker is closed. The App exists and is validated.
