# 03. v2, GitHub-side autonomy

Status: **RECOMMENDED design, forward-looking. Build after PR-B has been observed on real
traffic.** Nothing here has run.

Goal: apply a label or let a PR go red, and it babysits itself across days and roughly 25 CI
rounds while the laptop is closed, across console plus three submodule repos, stopping at
green + reviewed + threads resolved. It never merges and never pushes `main`.

---

## 0. The decision everything hangs on

**The model never holds a write token. Ever.**

All writes (commits, pushes, PR creation, ready-flip, comments, thread resolution, body
refresh) are performed by a deterministic **harness** that runs *after* the model step exits,
consuming a schema-validated handoff file the model leaves in the workspace. App tokens are
minted **after** the model step completes, so they never exist in the model's process
environment.

Why this shape, and why it is not negotiable:

- Pushes with `github.token` do not trigger workflows, so an autopilot must push with an app
  token. But `.github/actions/app-token`'s own text warns that "a write-scoped token in a PR
  job is a branch-protection bypass in PR-controlled hands", and the existing `rediacc-ci-cd`
  app (`app_id 2772000`) holds an **`always` bypass** on console's ruleset. Handing that to a
  model on a **public** repo that reads public comments is the April 2026 "Comment and
  Control" scenario verbatim. Removing the token from the model kills the entire class of
  direct API-mutation attacks.
- The residual (poisoned code inside a legitimate-looking fix commit) is inherent to any
  code-writing agent and is bounded by the harness path rules, the review pipeline, and the
  human merge.
- It resolves authorship cleanly: the harness sets `user.name` and `user.email` to the
  operator's `<id>+<login>@users.noreply.github.com` identity, unsigned. The action's
  `bot_id`/`bot_name` inputs become irrelevant because the action never commits.

**Say this plainly rather than burying it: attributing autopilot commits to the operator is
impersonation by configuration.** `git log` will not distinguish them from human commits.
The operator accepted this. The compensating audit trail is the state-comment round ledger,
which records every autopilot commit SHA per round. **The ledger must never be optional.**
(`block-commit-meta.sh` bans `Co-Authored-By` trailers repo-wide, so a trailer marking is not
available even if wanted.)

**A second GitHub App, `rediacc-autopilot`,** with `contents:write`, `pull_requests:write`,
`issues:write`, `actions:write`, installed on the same five repos, and **with no bypass on
the console ruleset**. Then even a harness bug cannot push console main; the platform refuses.

**Residual to state honestly:** `renet`, `account` and `elite` have no rulesets (free-plan
private repos), so nothing platform-side stops a main push there. The only guard is the
harness's hardcoded branch checks. **A harness compromise can push submodule main.** Trusted
scripts come only from `console@main`, so the attack requires a merge first, which makes the
human merge the boundary. Keep `autopilot-push.sh` tiny and boring, and review it as the
security boundary it is.

---

## 1. The five structural walls

These define the design space. Do not design around them by wishing.

1. **No cross-run session memory.** `session_id` is a real action output
   (`action.yml:182-184`, set from `run-claude-sdk.ts:197-203`), but the transcript lives on
   the runner and is never uploaded or restored. Verified: the only `.jsonl` reference in the
   whole action is the inline-comment buffer. Cross-run `--resume` requires artifact plumbing
   you build yourself.

   **CORRECTED, and this is good news that changes the state design.** An earlier draft said
   "the PR thread is the session". That is **true for tag mode and false for agent mode**,
   and a `workflow_run` trigger is always agent mode (`detector.ts:78`, since every tag-mode
   branch is gated on `isEntityContext`). Agent mode builds the entire prompt from one place,
   `src/modes/agent/index.ts:75-79`:
   ```ts
   const promptContent = context.inputs.prompt ||
     `Repository: ${context.repository.owner}/${context.repository.repo}`;
   ```
   `fetchGitHubData` and `createPrompt` are **tag-mode only** and agent mode calls neither.
   **No PR comments, titles, bodies or review text are inlined at all.**

   Two consequences, both important:
   - The gate-injected `<autopilot_state>` block is not merely authoritative, it is the
     **only** state channel. There is no fallback to the model reading the thread.
   - Untrusted text reaches the model by exactly two routes you control: what you interpolate
     into `prompt:`, and what the model fetches at runtime through the registered MCP servers
     or an allowlisted `Bash(gh ...)` call. Route two is model-initiated and bounded by
     `--allowedTools`. **That is a materially better security posture than blind inlining**,
     and it is a design advantage of the `workflow_run` plus agent-mode shape.

   The HTML-comment stripping still matters for the existing `<!-- claude-reviewed: -->`
   marker in the review pipeline, but it is not the reason autopilot state must be visible
   text. The reason is that nothing is inlined at all.
2. **Workflow files are out of reach, but for a narrower reason than "installation tokens
   cannot write workflows".** That blanket claim is **false**. Writing `.github/workflows/**`
   requires the app to hold `workflows: write`. Verified live:
   - `rediacc-ci-cd` (2772000) permissions: `actions:write, contents:write,
     deployments:write, environments:write, metadata:read, packages:write,
     pull_requests:write`. **No `workflows`.** The restriction holds for this app.
   - `claude` (1236702) permissions **include `workflows:write`**. The restriction does not
     hold for that app.

   What actually protects you is your own wrapper: **no `app-token` preset ever requests
   `workflows`**, so no token minted through it can write workflow files regardless of app
   permissions. Keep it that way, and do not add such a preset.

   Operator decision stands: the autopilot escalates workflow fixes to the human with the
   proposed patch attached.
3. **Pushing with `github.token` does not trigger workflows.** The repo relies on this
   deliberately (`claude-review-reusable.yml:118-120`). An autopilot pushing with
   `${{ github.token }}` pushes a fix and CI never runs: the loop silently dies looking
   successful. Pushing with an app token creates a genuine cycle, so a **hard round cap must
   be enforced by the workflow, not by the model**.
4. **`.claude/` protection DOES NOT APPLY on `workflow_run`. This is the single most
   dangerous finding in the whole v2 design, so treat it as a hard invariant.**

   `restore-config.ts` does restore `.claude`, `.mcp.json`, `.claude.json`, `.gitmodules`,
   `.ripgreprc`, `CLAUDE.md`, `CLAUDE.local.md`, `.husky` from the base and quarantine the
   PR's copies to `.claude-pr/` (`:21-30`, `:100-113`, `:129-155`). **But the call is gated**
   at `src/entrypoints/run.ts:255`:
   ```ts
   if (isEntityContext(context) && context.isPR) {
   ```
   and `isEntityContext` (`context.ts:292-296`) tests membership in `ENTITY_EVENT_NAMES`
   (`issues, issue_comment, pull_request, pull_request_review,
   pull_request_review_comment`). **`workflow_run` is an AUTOMATION event, not an entity
   event, so `restoreConfigFromBase` never fires.**

   And `.claude/hooks/**` **do execute**: `parse-sdk-options.ts:329-335` sets
   `settingSources: ["user", "project", "local"]` by default, so `.claude/settings.json` in
   cwd is live, and restore-config's own docstring says the CLI acts on it "before any
   tool-permission gating, executing hooks (including SessionStart), setting env vars
   (NODE_OPTIONS, LD_PRELOAD, PATH)".

   **Therefore: a `workflow_run` job that checks out PR head has handed arbitrary
   PR-authored hook code a shell, with tokens in the environment, and none of the protection
   the design assumes.** The autopilot MUST check out a trusted ref. `claude-review-reusable.yml:57-60`
   already does exactly this (`repository: rediacc/console, ref: main`). **State it as an
   explicit invariant in the workflow, with a comment, rather than leaving it an accident of
   the checkout step.**

   Still true and still relevant: you cannot iterate on the autopilot inside its own PR, and
   `git add -A` must be forbidden in the prompt.
5. **Trigger limits.** `label_trigger` is issues-only and never sees a PR label.
   `pull_request: types: [labeled]` plus a `prompt:` input does work, but `track_progress:
   true` **throws** on both `pull_request.labeled` and `workflow_run`.

---

## 2. Trigger and arming

**`workflow_run` is primary; the label is a state flag**, not a trigger. Rationale:
`pull_request.labeled` carries no `author_association` equivalent (the payload tells you the
label, not who applied it; only `sender` does), so on a public repo it would need an explicit
allowlist; and `track_progress` throws on it. `workflow_run` has no user-controllable entry
point and matches the shape the review pipeline already proves.

| Trigger | Purpose | Model may run |
|---|---|---|
| `workflow_run` on "Console CI" completed | primary; failure starts a fix round, success advances finish-line state | yes |
| `workflow_run` on "Claude Review" completed | review posted, so a review-response round | yes |
| `schedule` every 2h | sweeper for missed events and "label applied while CI was already red" | no, dispatch only |
| `workflow_dispatch` | manual arm, resume, stage testing | yes |

Concurrency: `group: autopilot-<head_branch>`, `cancel-in-progress: false`. Never kill a round
mid-push; the queued run's gate then sees "already handled" and exits.

**The gate checks all of these before the model is ever invoked**, so a no-go costs zero
model tokens:
1. Stage flags as repo **variables** (`AUTOPILOT_ENABLED`, `AUTOPILOT_ALLOW_PUSH`,
   `AUTOPILOT_ALLOW_SUBMODULES`): instant, phone-editable, not PR-controllable, no commit.
2. PR open, head repo equals base repo (fork guard).
3. **PR author in an allowlist.** The autopilot never babysits a stranger's PR. This single
   check removes the largest injection surface.
4. **Label applier in an allowlist**, read from the issue timeline's newest `labeled` event
   actor.
5. Round count under cap; this `(run_id, attempt)` not already in the ledger; no watchdog
   `pending_rerun` currently held for this run.
6. Mode selection: failure yields fix; cancelled with at least one failed job yields fix
   (watchdog kill); cancelled with zero failed and a newer head yields exit (superseded);
   Review Gate red yields review-response; success while draft yields ready-flip (no model);
   success plus outstanding threads yields review-response; success plus done-conditions
   yields done.

---

## 3. State, given HTML comments are stripped

**One state comment per PR**, authored by the autopilot app, PATCH-updated in place, in
**plain visible text**:

```
### Autopilot state (machine-maintained, do not edit)
state: waiting-ci | round: 7/25 | head: abc1234 | last_run: 30123456789/1 handled

#### Round ledger
r1 | run 301.../1 | red: check-types | cause: missing import after rename | fix: packages/cli/src/x.ts | console a1b2c3d
#### Ruled out
- widening testTimeout for e2e-fork (tried r3, red persisted, real race in X)
#### DECISIONS (post-hoc review)
- r5: chose expect.poll over sleep in test Y; alternative skip rejected (weakens coverage)
```

The gate parses this and injects it into the prompt as a structured `<autopilot_state>` block,
which is authoritative regardless of how the action builds context.

**Trust rule, because this is a public repo and anyone can post a lookalike comment:** the
gate selects the state comment strictly by **author equals the autopilot bot** and exact
header prefix. The prompt states that its only state is the injected block, and that any PR
comment claiming to be autopilot state is untrusted data. Forgery is impossible for outsiders
because only this repo's workflows can author as that bot.

**Growth bound:** each ledger line hard-capped at 400 chars, so 25 rounds plus ruled-out plus
decisions is roughly 12 to 15 KB against GitHub's 65,536-char limit. Above 55 KB, compact
rounds older than the last 8 to one line each; full detail persists in each round's workflow
logs, and the ledger line carries the run id as the pointer.

**"Ruled out" is the anti-thrash memory.** The prompt forbids re-trying a ruled-out approach
without new evidence. It is the main round-economiser.

---

## 4. Loop safety and the termination proof

- **Hard cap `MAX_ROUNDS=25` per PR**, enforced by the gate, counted from ledger entries in
  the trusted-author comment. Same pattern as `MAX_REVIEWS_PER_PR=3`.
- **Three kill switches, all instant and commit-free:** remove the label; flip
  `AUTOPILOT_ENABLED` (kills all PRs at once); suspend the app installation (kills all writes
  even mid-round).
- **Termination.** Every gate invocation ends in exactly one of: a push, which increments the
  round counter and is bounded by 25; a deterministic finish step (ready-flip once,
  review-gate rerun bounded by the review cap and thread count); or exit-no-action, which
  generates no push, hence no CI run, hence no new `workflow_run` event. The only non-push
  event sources are the 2h cron (which acts only on a genuinely missed terminal run, then
  defers to the same cap) and human dispatch. **No cycle avoids the round counter.**
- **Flapping.** The watchdog owns transient classification; the gate defers while a
  `pending_rerun` is held so the two do not race. Same job red twice with the same signature
  after two distinct fixes yields `stuck` and escalates rather than burning the cap.
- **Runaway model:** per-round turn cap, 30-minute job timeout, and no write token, so the
  worst case is a wasted round.

**The 25-round cap is calibrated, not generous.** The serial-gate-chain reality of this repo
(one red revealed per run, a 27-round precedent) means some real waves **will** end
`escalated` at cap. That is the design working. The morning human re-arms with context
instead of the bot thrashing.

---

## 5. Submodules

- Harness-enforced order: commit and push submodule branches, create plain PRs (console gets
  a draft), verify each pointer advance with `git merge-base --is-ancestor <recorded> <new>`,
  stage pointers, verify with `git ls-files -s`, then commit and push console.
- **Anti-rollback is ancestry, never ownership.** This mechanically encodes the real incident
  where homebrew-tap showed dirty at 1.2.3 while the parent already recorded 1.2.5. A pointer
  behind origin/main means a stale checkout: update, commit nothing. Only a descendant pointer
  is ever committed. Diverged escalates.
- **Pointers-at-latest is logged, not auto-fixed.** Bumping unrelated submodules mid-babysit
  can drag unreviewed changes into the PR, so it is a judgment call for the next round or for
  escalation.
- Per-round token scoping: `repositories:` is exactly the repos named in that round's
  handoff. A console-only round mints a console-only token.
- `elite` has no CI and no review caller. Push, PR and pointer only.

---

## 6. Adversarial review of this design

Actor: anyone on the internet, since console is public. Assets: private submodule source
checked out on the runner, the OAuth token, app private keys, main-branch integrity, the
operator's commit identity.

**Where untrusted text reaches the model, and the mitigation.**
1. **PR comments.** Fix rounds are pointed at the gate-provided failed-job list and logs, not
   comments. Review-response rounds receive a **gate-built payload filtered by comment
   author** before the model sees any text. The tool allowlist contains no comment-listing
   endpoint. Residual: `gh pr view` shows the body plus some comments; body is
   operator-authored because of the author allowlist.
2. **PR body and title.** Armed PRs are operator-authored. Passed to scripts via `env:`, never
   interpolated into `run:`, preserving the existing zero-interpolation hardening.
3. **CI job logs**, the model's primary input. Semi-trusted; the prompt marks log text as data.
   Accepted residual.
4. **Branch and job names**, env-passed only, with the fork guard at the workflow `if:`.
5. **The state comment**, trusted-author-selected.
6. **`handoff.json`**, written by the model and therefore untrusted by definition:
   schema-validated, path-normalised, denylisted (`.github/**` escalates, `.claude/**` reverts
   blocked), messages passed with `-F` so no shell interpolation, no `eval` anywhere.

**Worst case per capability.** Opening a PR achieves nothing, because the gate refuses
non-allowlisted authors and the workflow never checks out attacker code. Commenting on an
armed PR can at most steer the model's **edits** on the operator's branch: it cannot make it
push (no token), cannot redirect the harness (branch and path checks), and cannot exfiltrate
via API (no write surface). **The remaining exfiltration channel is encoding private
submodule content into a staged file on the public console branch.** That is real and
inherent to a code-writing agent with private code in its workspace. Bound it with a
tripwire: flag any single-round console diff adding more than N KB under paths the round's red
did not implicate, and escalate instead of pushing. **Ship that tripwire.**

**Non-regression claim, which is checkable in review because it is structural rather than
behavioural:** no `${{ github.event.* }}` enters any `run:`; tool allowlists stay tighter than
the review pipeline's; trusted scripts stay outside the workspace; and `contents:write` is
added only post-model, to a bypass-less app, scoped per round.

---

## 7. Tier mapping when nobody is watching

`pr-babysitter.md`'s tiers assume a human or lead is reachable. Unattended, there is nobody,
so tier 3 splits:

- **Tier 1 (mechanical):** autonomous, ledger note.
- **Tier 2 (test/CI-only judgment):** autonomous with a DECISIONS ledger entry, preserving
  post-hoc veto.
- **Tier 3a (decidable by declared intent):** the PR body's operator-authored
  `## Autopilot brief` section (intent, deliberate renames, sanctioned reds, frozen surfaces)
  makes some tier-3s decidable. No brief means 3a collapses into 3b.
- **Tier 3b (hard ceiling, always escalate):** product-code behaviour changes, gate edits, any
  suppression, locale translated values, count baselines without a mechanism, anything under
  `.github/**`, diverged pointers, and `stuck`. Escalation sets state `escalated`, applies
  `autopilot-blocked`, and posts one comment mentioning the operator with the failing gate, a
  log pointer, candidate fixes and any proposed patch. **No new issues are opened.**

This is deliberately narrower autonomy than in-session default mode. It accepts more
escalations in exchange for never guessing at product intent while nobody is watching. If
mornings show the ceiling is too conservative, promote classes via the brief rather than by
loosening the default.

---

## 8. Land-then-observe

v2 cannot be tested pre-merge. Stage flags are repo **variables**, so behavioural rollback
never needs a commit.

- **S0 prep** (independently worthwhile, **moved into PR-B**): paginate
  `check-resolved-threads.sh`; give `worklist.py` a CI no-op branch. Plus create and install
  the `rediacc-autopilot` app with no bypass.
- **S1 shadow:** land the workflow and gate with writes disabled; the gate logs its decision
  and exits. Verify event delivery, dedup and mode selection against reality.
- **S2 state only:** enable state-comment writes. Verify ledger mechanics and author filtering.
- **S3 deterministic finish:** ready-flip plus review-gate rerun. **Canary: a
  pointer-bump-only PR** (cheap, fast CI). Verifies that an app-token ready-flip fires
  `ready_for_review` and the review pipeline chains.
- **S4 model dry-run:** fix rounds with push disabled; the harness uploads the would-be diff
  as an artifact. Canary: a scratch branch with a deliberate lint error.
- **S5 push, console only, cap 3:** full loop red to fix to green to ready to review to done.
- **S6 submodules, review-response, sweeper, cap 25.** Canary: a trivial renet change.

Rollback at any stage: flip the variable (seconds) or revoke the installation (also seconds).

---

## 9. Cost

The model runs only on fix rounds and review-response rounds. **Zero model cost** for gate
no-gos, dedup, superseded, watchdog-defer, ready-flip, review-gate rerun, done-detection and
sweeper ticks. On a healthy PR that goes green first try, the autopilot costs zero model
invocations through to done.

Billing is subscription via the OAuth token, so the constraint is plan rate limits rather than
dollars. Concurrent PRs multiply it, so arm PRs serially where possible.

**`--max-budget-usd` binds under OAuth. It is a post-hoc stop, NOT a ceiling, and the wording
here has to keep that distinction.** Settled by spike S-2 on 2026-07-30 against the pinned
CLI build itself; full evidence in `spike-s1-s2.md`. Measured: cap `0.01`, exit 1,
`subtype: error_max_budget_usd`, `terminal_reason: budget_exhausted`, and
`total_cost_usd: 0.2340351`. A 23x overshoot, because the check compares ACCUMULATED cost
against the cap **between turns** and nothing bounds a single request. So the real guarantee
is *total <= budget + one more turn*. At PR #543's measured $5.9255 over 61 turns that is
about $0.097 a turn, but a first turn ingesting a large diff can overshoot by dollars. Say a
dollar stop exists; never say a hard cap does.

It binds under OAuth because there is no auth branch on the path: cost is token-times-price
arithmetic, accumulated and compared with nothing between the credential and the comparison.
The flag is not an action input, so it must ride in through `claude_args`, which
`parse-sdk-options.ts` preserves as an unknown flag/value pair and forwards to the SDK's
`extraArgs` (measured emitting `--max-budget-usd 0.01` verbatim into child argv).

**Design consequence, and it must not be discovered in production.** `error_max_budget_usd`
carries `is_error: true`, so the step FAILS. The three steps after it in
`claude-review-reusable.yml` (post report, post inline findings, record reviewed SHA) carry
only a `gate.outputs.go` condition with no status function, so implicit `success()` skips all
three. A budget halt today therefore costs a red job, no report, no findings, and **no marker
SHA**, so the next run re-reviews the same commit and pays again. If the flag is wired in,
decide deliberately whether those steps get `always()`. Derived from the conditions plus
documented `if:` semantics, never observed, since no budget halt has occurred here.

---

## 10. Hook audit for the CI context

All hooks execute inside the action, restored from main.

- **Helpful as-is:** `block-admin-merge`, `block-git-force-push`, `block-git-amend`,
  `block-git-empty-commit`, `block-commit-meta`, `block-protected-files`.
- **Harmless:** `block-nondraft-pr-create`, `block-premature-ready` (both police harness-only
  operations in this design).
- **Aligned by accident:** `block-ci-polling` and `block-long-sleep`. In CI the model never
  waits on CI, because the event loop replaces waiting, so the polling bans reinforce the
  design.
- **Needs a CI-aware branch:** `stop/worklist.py`. `CLAUDE.md` instructs appending `- [ ]`
  items, and the Stop hook refuses to end a turn while any remain, which on a runner can wedge
  the action into burning turns. No-op when `GITHUB_ACTIONS=true`. **This moves into PR-B.**

Also note that `CLAUDE.md`'s Session Defaults ("work stays uncommitted until asked") textually
contradict the autopilot's job. The fix-round prompt must explicitly supersede Session
Defaults for the CI context. Hooks still enforce the hard bans, so the safety floor does not
depend on prose.

---

## 11. If v2 must ship in two increments

- **Increment 1 (the useful 80%):** S0 through S5. Console-only fix loop, state comment, caps
  and kill switches, ready-flip, escalation. Submodule-needing fixes escalate with the repo
  named and a proposed diff. Review threads escalate. This already covers the dominant real
  case (post-land console reds, lint/test/generated-artifact rounds) with the full security
  posture.
- **Increment 2:** the submodule push path, review-response mode, the sweeper, decomposition
  tooling, the exfiltration tripwire, brief-driven tier 3a.
- **Cut entirely if squeezed:** sub-issue decomposition (manual today, orthogonal), and the
  sweeper (`workflow_dispatch` covers the gap manually).
