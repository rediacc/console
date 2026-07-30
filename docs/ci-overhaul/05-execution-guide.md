# 05. Execution guide

---

## Before anything

1. **Read [01-verified-context.md](01-verified-context.md) in full**, including section 8b,
   which corrects earlier sections. Then re-verify the handful of claims your first wave
   actually depends on. Do not re-verify all of them; verify the load-bearing ones.
2. **Seed the worklist.** Path via `.claude/hooks/stop/worklist.py --path`. One `- [ ]` per
   wave, each tagged with your session-id prefix. The hook is per-repo and fail-closed, so
   untagged items count as yours.
3. **Ask the nine decision points** ([04](04-decisions.md) section C) in **one round**, with
   the recommended defaults offered. Anything unanswered takes its default and gets logged.
4. **Confirm the tree yourself; do not trust this line.** It moved twice during the source
   session. At the moment of writing, the worktree is on branch **`0727-1`** (not `main`) and
   carries `M package-lock.json` with exactly **27 deletions**, which is the documented
   cosmetic npm 11 versus npm 10 flip described in `CLAUDE.md`: harmless, do not commit it,
   and restore the canonical form with
   `npx -y npm@10 install --package-lock-only --ignore-scripts` if it bothers a gate.
   Earlier in the session the tree was on `main` with `.ci/breakpoint/scripts/start-shell.sh`
   dirty. A prior draft also warned about uncommitted `.claude/hooks` edits; that warning is
   **stale**, they were committed. Work out where you actually are before branching.
5. **Read the three canonical process files** you will be operating inside:
   `.claude/commands/pr-babysit.md`, `.claude/agents/pr-babysitter.md`,
   `.claude/commands/pr-merge.md`. This guide does not restate their mechanics.

---

## Spikes: BOTH SETTLED 2026-07-30

Results and full evidence in [spike-s1-s2.md](spike-s1-s2.md). Neither needs
re-running; the original questions are kept below so the answers have context.

- **S-1: the model IS honoured.** #539 is a cosmetic label bug, not a
  review-quality one, so every finding received so far came from the model that
  was asked for.
- **S-2: the flag DOES bind under OAuth**, but as a between-turns post-hoc stop
  rather than a ceiling: a `$0.01` cap was measured spending `$0.2340351` before
  halting. A dollar stop exists; a hard cap does not. It also turned out not to
  need a CI dispatch, because the pinned action bundles a CLI build that was
  already present locally under the same OAuth auth class.

**S-1. Does `--model claude-sonnet-5` actually take effect?**
Issue #539's third bullet is unresolved and it is the difference between a cosmetic label bug
and a review-quality bug affecting every finding received so far. Read a real
`claude-execution-output.json` from a completed review run and inspect `modelUsage`. If it
contains **only** haiku, the model override is being ignored and that becomes a priority item
rather than a nicety. Haiku legitimately appears for the action's internal sub-steps, so its
presence alone proves nothing; you are looking for the absence of sonnet.

**S-2. Does `--max-budget-usd` bind under OAuth subscription auth?**
The flag is not part of the action and is documented CLI-print-mode only. One live run with
`--max-budget-usd 0.01` and a prompt guaranteed to exceed it settles it. If it does not
abort, the flag does not bind, and the v2 cost section must say so rather than implying a
dollar stop exists.

Both spikes are cheap. Neither blocks Wave A.

---

## Waves and ordering

### Wave A: PR-A, the nightly

Contents in [02](02-v1-economics.md) sections A1 to A5.

**The sequencing constraint that shapes everything:** the nightly executes **main's** code, so
these fixes only take effect after merge. That is why it is a separate PR and why it goes
first.

**Acceptance, both required before Wave B's cuts ship:**
1. one green rehearsal `workflow_dispatch` on `main`, and
2. the next real scheduled run green:
   `gh run list --workflow ci.yml --event schedule -L 1 --json conclusion` is `success`.

The rehearsal is schedule-equivalent by construction (`full_suite` is `event != 'push'`, and
the channel step yields `''` for anything that is not push or pull_request), which compresses
this gate from roughly 24 hours to roughly one CI run.

**On the Stage Artifacts fix specifically:** verification found that `cd-stage.yml:156-160`
**already diagnoses this exact bug in a comment**, and that `build-pkg-repo.sh` hard-exits on
an empty channel *and* bakes `CHANNEL` into generated content (`baseurl`, `gpgkey`, `Server`).
So "generate always, gate only the upload" requires supplying a placeholder channel, and the
generated files would carry an unusable baseurl. **The one-line alternative** (channel-gate
the validator's two assertions at `validate-stage-artifacts.sh:106-113`) has lower blast
radius. Pick deliberately and say which you picked and why.

### Wave B: PR-B, the engine and the sweep

Contents in [02](02-v1-economics.md) sections B1 to B8.

**Build order inside the wave**, because later steps depend on earlier ones:
1. The baseline-and-net-delta engine plus its gate tests (`--classify` pure mode first, so it
   is testable without network).
2. The attested skip-plan and the `ci-complete` reconciliation. **Prove it fails on a planted
   mismatch before gating anything on it.**
3. D10's job-list-to-`RESULT_` gate. Cheap, and it protects every later change.
4. The pilot cut: `test-renet` only. Smallest surface, cleanest boundary.
5. The remaining scope wiring.
6. Policy cuts: D5, macOS demotion, preview decouple.
7. The defect sweep and the four issues.
8. Testing pillar, labels, metadata, milestones.

**Live proof is mandatory and cannot be done on the PR itself**, because PR-B's own diff
touches `.ci/` and `.github/` and therefore forces full CI. Use two throwaway draft PRs, then
close them unmerged:
- a one-line `docs/` change: expect reduced scope, the gated jobs rendering as `skipped`, and
  `CI Complete` green;
- a one-line comment change inside `private/account` with the gitlink bumped on a scratch
  branch: expect reduced scope with `run_account_e2e=true` and workers skipped, which proves
  the submodule-content-diff leg.

Additionally, **prove D9 actually fires**: a pointer-bump-only commit must now produce
`pointer_bump_only=true`. It has never once been true. That is the single most convincing
demonstration available.

### Wave C: PR-C, the autopilot

Contents in [03](03-v2-autonomy.md). Lands with **every stage flag off**.

**Do not enable a stage until Wave B has been observed on real traffic**, concretely: at least
one PR where the scope line reported `reduced` and the skipped jobs were the expected ones,
and one where D9's fast path fired on a pointer bump. Two observations, not a fixed number of
days.

Then progress S1 to S6 as in [03](03-v2-autonomy.md) section 8, one at a time, each with its
canary.

---

## The automated flow, end to end

This is what the operator asked for: branches, PRs, merging and testing, driven without
supervision. It is the existing house flow; do not invent a new one.

**Per wave:**

1. **Branch.** `MMDD-N` from current `main`, the **same branch name in every repo** you touch.
   `git fetch origin --prune` in each repo first.
2. **Submodules first, every cycle.** Commit and push each dirty submodule to **GitHub
   origin** (console CI submodule-inits from GitHub, so a push elsewhere is invisible to it),
   open its PR, then re-point the parent, then commit and push the parent. Verify pointers are
   staged at the new commits with `git ls-files -s`.
3. **Console PR is created with `--draft`.** Submodule PRs are plain today; if decision D-6
   goes the other way they become drafts too. The hooks enforce whichever is current, and
   **a hook block is the flow speaking, not an obstacle to route around.**
4. **PR body links the submodule PRs** (the `Submodule Branches` gate reads the body) and
   spells out user-facing surface changes. **Refresh the body on every push**; the gate reads
   `lastEditedAt`, not `updatedAt`, so a push alone does not satisfy it.
5. **Run `/pr-babysit`** and follow `.claude/agents/pr-babysitter.md` as written: it is the
   single source of truth for the loop, the tier system, the round log and the gotchas. Key
   points that bite: `gh run watch` is banned in favour of a terminal-state poll; every turn
   that leaves a run in flight must end with an armed wake-up; after the first snapshot
   commit, `git add -A` is banned.
6. **Flip ready only at green.** `gh pr ready` is hook-gated on `CI Complete` being green on
   the current head. A block means you are not actually green.
7. **Review, then threads.** The review fires on the ready-flip and on green pushes, capped at
   3 passes per PR. Resolve threads and reply substantively; note that a resolved thread and a
   replied comment are **different facts**, checked independently.
8. **Merge with `/pr-merge`.** Submodule PRs squash-merge first, then bump console pointers to
   the **squash commits** (verify `git diff --stat <old-tip> <new-main-sha>` is empty), then
   `gh pr merge --squash --auto` on console. `--admin` is banned by hook.
9. **Watch the release land**, then re-sync `main`, remembering that CD pushes two commits back
   to `main` after every release.

**Autonomy boundary for this program.** The operator asked for an automated flow that can
still ask. So: run autonomously, and reserve questions for decisions that are genuinely
critical, meaning a change that is irreversible outside the PR, a change to product behaviour
where intent is unclear, or a gate you believe is itself wrong. Everything else is decided,
logged under a `DECISIONS` heading in the round log for post-hoc veto, and kept moving.
**Never** push `main`, merge without being asked, force-push, amend a pushed commit, or
suppress a gate to get past it.

---

## Gates

Run before claiming any wave complete:

- `npm run ci` from the repo root.
- `npm run test:quality-gates` (the gate self-tests; new gates must be registered in
  `test-gate-anti-vacuity.sh` with a pinned diagnostic).
- `.ci/scripts/security/check-workflow-gates.sh` (CHECK 1 `always()` prefixes, CHECK 2 the
  reusable input/secret contract both directions, CHECK 3 the `ubuntu-slim` 14-minute cap).
- `.ci/scripts/quality/check-workflows.sh` (`INLINE_MAX_LOGIC=8`, so detector logic lives in
  `.ci/scripts/ci/`).
- `scripts/check-ci-chain-parity.ts`: a gate wired into a workflow must also be in the
  `npm run ci` chain.
- `.claude/hooks/test-hooks.sh` if any hook changed, and it must show a nonzero case count.

**Known-environmental local reds that are not failures:** `validate:tutorial-audio`,
`check:actions`.

---

## Definition of done

**Wave A** is done when the nightly is green from a real scheduled run, a failed nightly
reads as `failure` rather than `cancelled`, and a red nightly raises something a human will
see.

**Wave B** is done when: the two throwaway PRs demonstrated a reduced run; `pointer_bump_only`
has been observed **true** at least once; the skip-plan reconciler has been proven to fail on
a planted mismatch; every new gate has been seen to fire; and the full battery is green.

**Wave C** is done when stage S5 has driven one real PR from red to green to ready to
reviewed without human intervention, with the round ledger showing every commit it made.

**The whole program is done** when a normal PR round costs materially less than the measured
73-minute baseline and you can say, with a run id, exactly how much and on which class of
change. Report measured numbers, not intentions.

---

## Found, not fixed (carry these forward)

These were discovered during the session and are deliberately not in any wave. Report them to
the operator again at the end rather than letting them dissolve.

- The two dead `deploy-preview` inject steps (`ci.yml:807`, `:813`) unless D-9 says delete.
- All 8 VM/E2E jobs install three `private/account` npm trees the suites never reference.
- `generate-tag.sh:92-97`'s renet build-config list omits `.ci/scripts/infra/build-renet.sh`,
  which is what `ct-tests.yml` and `ci-ops-test.yml` actually use.
- The submodule review pipeline is **doubly** broken: no `CLAUDE_CODE_OAUTH_TOKEN` on
  `renet`/`account`, **and** the reusable's bootstrap step assumes a script that exists only
  in console.
- `#533`'s underlying question is still unanswered.
- The intra-quality serial gate chain.
