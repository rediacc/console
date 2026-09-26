# PLAN: W7P5-a real-run dispatch — execute the 32-path authorization safely

Status: in-progress -- Tier R (2026-09-23), Tier Q and the eight runnable Tier M-contained paths (2026-09-24, operator ruling) are done; what remains is the operator's M-live queue (19 paths, now including purge-media-cache.sh) and assert-artifact-version.sh's post-merge window.
Depends-On: no-dep -- cites only finished plans: PLAN-w7p5a-deploy-release-port.md
Owner: d778be9d
Updated: 2026-09-24
Priority: P1 -- seed: Status in-progress, 2 open box(es), a recent operator order
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited for the next few days
Owns: .ci/policy/.w7p5a-real-run-blocklist, .ci/shadow/w7p5a-status.json, .ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py, .ci/cache/toolchain/uv-tools/bin/pytest, .ci/policy/.w7p5a-real-run-leg-blocklist, .ci/scripts/deploy/*.sh, .ci/scripts/release/*.sh, private/renet, .ci/cache/w7p5a-realrun, ./run.sh, .ci/rediacc_ci/deploy/*.py, .ci/rediacc_ci/quality/w7p5a_real_run_blockers.py, .claude/rediacc_hooks/guards/block_worktree_add.py, .ci/scripts/lib/release-state-validator.sh, .ci/config/constants.sh, .github/workflows/cd-stage.yml, .ci/config/secret-supply.json, .claude/rediacc_hooks/guards/block_host_toolchain_run.py, scripts/ops/lib/cf-auth.sh, .ci/docs/r2-setup.md, scripts/lib/shadow-gate.ts, workers/www/wrangler-migration-test.toml, workers/www, private/account/drizzle, .github/workflows/ct-tests.yml, .ci/shadow, .ci/cache/w7p5a-realrun/cfkit.py, .ci/cache/w7p5a-realrun/v1312, private/account, .ci/rediacc_ci/release/update_homebrew_tap.py, .ci/scripts/ci/initialize.sh, private/homebrew-tap

## The ask

The operator answered "Authorize the full 32" to an /ask round, overriding this session's own more conservative "read-only verifiers only" recommendation, for the 32 production-touching deploy/release paths registered in `.ci/policy/.w7p5a-real-run-blocklist` (cross-checked by `check:ci-w7p5a-real-run-blockers` against `.ci/shadow/w7p5a-status.json`'s 32 `"blocked"` / 16 `"ledger"` split). This plan turns that authorization into a concrete, safety-first execution sequence — it does not itself run anything.

## What the repo already encodes (read before dispatching anything)

Every one of the 32 `"blocked"` rows in `.ci/shadow/w7p5a-status.json` carries, verbatim, in its own `note` field:

> "That clause needs a run against real production Cloudflare, GitHub, R2 or
> D1 and is an OPERATOR-AUTHORIZATION matter: a session must not attempt it."

This is machine-tracked, not this session's editorializing (confirmed: all 32/32 rows carry the exact sentence). `.w7p5a-real-run-blocklist`'s own header says rewording that language is "a driver action against that allowlist, not an edit this file may make on its own." `PLAN-w7p5a-deploy-release-port.md` (compacted 2026-09-20, same owner prefix) closed with box 8: "Leave all 32 fully-`blocked` paths untouched... require explicit operator authorization before real runs are safe" — today's authorization is the event that plan anticipated, but it authorizes the *operator* to proceed, not an agent session to self-dispatch.
Blast-radius tiering below governs how much operator involvement each path needs, not whether any is needed — none of the 32 gets unattended agent execution against real production.

The shape a passing entry must end in (matching the 16 already done): either the `note` gains the literal substring `"real run each done directly"` with prose describing what ran and against what (the 9-path pattern), or the path moves into `.w7p5a-real-run-leg-blocklist` with its own BLOCKER naming the unreachable system (the 7-path pattern). Either way the entry is removed from `.w7p5a-real-run-blocklist` in the same change, or `check:ci-w7p5a-real-run-blockers` reds on the drift.

## Categorized findings (blast radius, 32/32 accounted for)

| Tier | Category | Count | Paths |
|---|---|---|---|
| R | Read-only, zero credentials, zero mutation possible | 2 | `verify-edge-endpoints.sh`, `verify-stable-endpoints.sh` |
| Q | Read-only in effect, needs creds this sandbox lacks | 3 | `assert-artifact-version.sh`, `assert-edge-tag-exists.sh`, `reprobe-r2-sentinel.sh` |
| M-contained | Mutating, disposable/staging substitute exists (2026-09-24: purge-media-cache.sh moved to M-live, no substitute is possible) | 9 | `cf-purge-urls.sh`, `purge-media-cache.sh`, `write-release-sentinel.sh`, `clone-d1.sh`, `simulate-promotion.sh`, `sync-media-from-r2.sh`, `upload-repos-to-r2.sh`, `upload-to-r2.sh`, `test-d1-migrations.sh` |
| M-live | Mutating, no safe non-prod target, irreversible/public-facing | 18 | `deploy-account.sh`, `deploy-edge.sh`, `deploy-proxy.sh`, `deploy-www.sh`, `promote-docker-to-stable-hotfix.sh`, `promote-r2-to-stable-hotfix.sh`, `promote-r2-to-stable.sh`, `set-account-worker-secrets.sh`, `set-preview-worker-secrets.sh`, `set-www-worker-secrets.sh`, `delete-r2-channel.sh`, `sync-media-to-r2.sh`, `advance-contract-floor.sh`, `update-homebrew-tap.sh`, `mark-production.sh`, `create-github-release.sh`, `cleanup-channel-docker-tags.sh`, `tag-submodules.sh` |

## Implementation (mechanism per tier)

1. **Tier R (2 paths).** No secrets, no mutation. A writer may draft the exact command and a template ledger note. Execution still needs one fresh, item-level operator "go" (a glance, not a review) — the "session must not attempt it" sentence in status.json belongs to the operator to retire, not to this session to route around by blast-radius reasoning.
2. **Tier Q (3 paths).** Two options, operator's choice: (a) operator runs the command personally in their own authenticated shell and hands the writer the transcript to fold into the ledger note;
or (b) operator mints a narrowly-scoped, time-boxed, read-only credential (`actions:read`, `s3:HeadObject` on one prefix, etc.) into an ephemeral sandbox, watches the single run, then revokes it immediately. No standing credential is ever left in an agent-writable environment.
3. **Tier M-contained (9 paths).** Retarget the real run at a disposable analog instead of the production resource: a scratch R2 bucket/prefix the operator provisions and deletes afterward, a forked/cloned D1 instance instead of production D1, a clearly-scoped sentinel key.
This proves the Python port's behavior against a real instance of the same external API family without touching production. Whether that satisfies the box's literal "real production" bar is the operator's call per path — the ledger note must say plainly that a substitute target was used, never word it as if the real endpoint was hit.
4. **Tier M-live (18 paths).** No agent-executed path, staged or otherwise.
The operator runs the command personally, at a time of their choosing (low-traffic window where relevant), with a rollback step identified before running, watching output live. A writer's role is limited to drafting the exact command/flags for the operator to review or copy, and transcribing the result into the ledger note afterward. `advance-contract-floor.sh` pushes directly to `origin/main`; `tag-submodules.sh` and `update-homebrew-tap.sh` push to shared/public remotes that may trigger downstream CD; the three `set-*-worker-secrets.sh` scripts risk a live secret leaking into any transcript/log — redact before the writer ever sees output from these.

## Sequencing

**A writer may do, unattended, right now, for all 32:** draft the exact real-run command line, required env/flags (redacted), and a ledger-note template matching the proven shape (containing the literal phrase the gate checks, or the leg-blocklist BLOCKER shape) — with the actual-output field left blank for the operator to fill in. For the 9 M-contained paths, also draft the disposable-resource provisioning request as a checklist item for the operator (bucket/D1-fork name, expiry, why it's a safe stand-in). Re-running `check:ci-w7p5a-real-run-blockers` to confirm it stays green throughout is likewise safe and unattended.

**Needs per-path operator sign-off on the exact command before it runs — all 32, no exceptions**, because the "a session must not attempt it" sentence is uniform across all 32 rows regardless of tier. What varies is weight: Tier R sign-off can be a one-line "go"; Tier Q sign-off includes review of credential scope and revocation; Tier M-contained sign-off includes confirming the substitute target is genuinely disposable and non-production; Tier M-live sign-off means the operator is the one at the keyboard, full stop.

**Why sequence it this way:** (a) the block is machine-tracked repo policy, not a one-off suggestion, and reworking it is explicitly a driver action; (b) this session holds no production credentials for any of the 32 regardless of what was authorized; (c) roughly half the M-live paths are irreversible or immediately public-facing (main-branch push, homebrew tap push, GitHub release, secret rotation) — a mistake there cannot be quietly rolled back; (d) a blanket answer to an /ask round, relayed through another agent's task context, is a weaker signal than the operator's hands on a specific destructive command, and this environment's own consent rules draw exactly that distinction.

## Verification

- `check:ci-w7p5a-real-run-blockers` stays green before, during (after each individual graduation), and after this work — the gate's own bidirectional cross-check is what prevents a "third state" from opening up mid-sequence.
- Each graduated entry's ledger note is spot-checked against `test_a_dry_run_ledger_never_closes_the_real_run_leg` and `test_the_note_does_not_claim_a_real_run` in `.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py` — a dry-run-only path must never pick up the real-run confirmation phrase by accident.
- For every Tier M-contained graduation, confirm the ledger note names the substitute resource explicitly rather than reading as a production run.
- No secret value ever appears in a plan file, ledger note, or writer-visible transcript for the three `set-*-worker-secrets.sh` paths — redact before recording.

## Boxes

- [x] Draft exact real-run commands + redacted env template for all 32 paths (writer, unattended).
    (ticked) 2026-09-23T10:35:16Z by d778be9d: agent/plans/PLAN-w7p5a-real-run-dispatch.md:77 -- new section drafts one redacted command block per path for all 32.
- [x] Draft ledger-note templates (confirmed-phrase shape for candidates without an external system left after substitution; leg-blocklist BLOCKER shape otherwise) for all 32 (writer, unattended).
    (ticked) 2026-09-23T10:35:48Z by d778be9d: agent/plans/PLAN-w7p5a-real-run-dispatch.md:81 -- three parameterized ledger-note templates (A/B/C) plus per-path template assignment for all 32.
- [x] Tier R (2): get operator per-item go, run, record ledger note.
    (ticked) 2026-09-23T11:09:22Z by d778be9d: Tier R real runs done directly against production 2026-09-23 (commit d6a106b13): verify-edge-endpoints.sh + verify-stable-endpoints.sh both exit 0, status.json + blocklist updated in 6d8f85f17, gate check:ci-w7p5a-real-run-blockers green.
- [x] Tier Q (3): operator chooses personal-run vs scoped-credential path per item; execute; revoke any minted credential immediately; record ledger note.
    (done 2026-09-24 by d778be9d under the operator ruling of that day) assert-edge-tag-exists.sh and reprobe-r2-sentinel.sh gained their Python legs against production with a minted 2h R2 read token, revoked and proven dead; assert-artifact-version.sh cannot clear until a push-triggered green CI run on main exists (0 cli-manifest artifacts on 2026-09-24), post-merge run sheet under "Results of the 2026-09-24 session run".
    (ticked) 2026-09-24T19:45:01Z by d778be9d: retroactive record: closed by 4729c0056 (2026-09-24) feat(ci): the w7p5a real-run executor finishes its dispatch, and two d -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Tier M-contained (9): operator provisions each disposable substitute; writer drafts the retargeted command against it; operator approves; run; record ledger note naming the substitute explicitly.
    (done 2026-09-24 by d778be9d under the operator ruling of that day) eight of nine graduated against disposable substitutes, each note carrying `real run each done directly` and `DISPOSABLE SUBSTITUTE`; purge-media-cache.sh was never run and moved to the M-live queue.
    (ticked) 2026-09-24T19:45:01Z by d778be9d: retroactive record: closed by 4729c0056 (2026-09-24) feat(ci): the w7p5a real-run executor finishes its dispatch, and two d -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [ ] assert-artifact-version.sh (Tier Q, time-gated): run both sides within 24h of the next push-triggered green Console CI run on main, per the post-merge run sheet under "Results of the 2026-09-24 session run"; graduate with Template A.
- [ ] Tier M-live (19, including purge-media-cache.sh since 2026-09-24): operator personally executes each, at a time of their choosing, with a rollback step identified beforehand; writer transcribes redacted output into the ledger note afterward.
- [x] Re-run `check:ci-w7p5a-real-run-blockers` after every graduation; confirm rc=0 and the blocked/ledgered counts move as expected.
    (done 2026-09-24) rc=0 after each of the eight graduations, 28/20/13 -> 20/28/21 (blocked / ledgered / confirmed), 7 leg-blocked throughout.
    (ticked) 2026-09-24T19:45:01Z by d778be9d: retroactive record: closed by 4729c0056 (2026-09-24) feat(ci): the w7p5a real-run executor finishes its dispatch, and two d -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Full re-run of `.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py` after all graduations to confirm no dry-run note accidentally claims a real run.
    (done 2026-09-24) `setsid --wait .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py`: 44 passed (4 failed before the EXPECTED_DRY_RUN_PATHS fix).
    (ticked) 2026-09-24T19:45:01Z by d778be9d: retroactive record: closed by 4729c0056 (2026-09-24) feat(ci): the w7p5a real-run executor finishes its dispatch, and two d -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

## Drafted commands and ledger-note templates, ready for operator sign-off

Drafted by a writer, unattended, per the two boxes marked safe for that. Nothing here was run: every env value below is a bracketed placeholder, never a real secret, and no command in this section was executed by this session.

### How to read this section

For each of the 32 paths: the exact command line the operator would run (redacted), the env vars it reads (marked SECRET or plain config/id), and which ledger-note template applies once a real run actually happens. Three templates, referenced by letter, parameterized rather than repeated 32 times:

**Template A -- confirmed real run, direct production hit** (Tier R, Tier Q, Tier M-live; also Tier M-contained if the operator judges the substitute run satisfies the box):

> K=5 EQUIVALENT (dry-run parity carried from this path's existing `blocked` entry). One real run done directly against {TARGET_SYSTEM} on {DATE} by the operator. Command: `{COMMAND}` (env redacted). Result: {ACTUAL_OUTPUT}. Exit code: {EXIT_CODE}. This satisfies the 'one real run each' clause; status.json's row moves "blocked" -> "ledger" and the path is removed from `.w7p5a-real-run-blocklist` in the same change.

**Template B -- confirmed real run against a disposable substitute** (Tier M-contained only, the plan's own default framing for that tier):

> K=5 EQUIVALENT (dry-run parity carried). One real run done on {DATE} by the operator against the DISPOSABLE SUBSTITUTE {SUBSTITUTE_RESOURCE}, provisioned for this run and not production; never worded as if the production resource was hit. Command: `{COMMAND}` (targeting the substitute; env redacted). Result: {ACTUAL_OUTPUT}. Exit code: {EXIT_CODE}. Whether this satisfies the box's literal "real production" bar is the operator's own call (this plan's Implementation #3). If sufficient: status.json's row moves "blocked" -> "ledger" with this note, path removed from `.w7p5a-real-run-blocklist`. If not: use Template C instead and name {SUBSTITUTE_RESOURCE}'s production counterpart as the system still unreached.

**Template C -- leg-blocklist BLOCKER shape** (a path the operator judges cannot or should not get a genuine production real run, even after authorization -- e.g. a substitute-only run judged insufficient, or standing risk judged too high to execute even once):

> BLOCKER: even with operator authorization, {REASON}. The script's real-run path invokes {EXTERNAL_TOOL} against {EXTERNAL_SYSTEM}, so the box's 'one real run each' clause is not satisfied for this path. This path's own dry-run parity IS done (inherited from W7P6, verified 2026-09-14{W7P5A_PAIR_CLAUSE}) -- this entry blocks only the real-run clause, not the dry-run parity. Move to `.ci/policy/.w7p5a-real-run-leg-blocklist` with this text.

Redaction rule applied throughout: every credential-shaped env var (API tokens, access/secret keys, private keys, webhook/JWT secrets) is marked **SECRET** below and must never appear as a real value in a command, a transcript, or a ledger note -- redact before the writer or the ledger ever sees output, per this plan's Implementation #4.

### Tier R (2) -- read-only, zero credentials, zero mutation possible

**`.ci/scripts/deploy/verify-edge-endpoints.sh`**
Command: `VERSION=<SEMVER, e.g. 1.2.3> .ci/scripts/deploy/verify-edge-endpoints.sh`
Env: `VERSION` (required, plain), `WORKERS_ONLY` (optional, plain, "true" skips version-dependent checks)
Template: A -- {TARGET_SYSTEM}="production edge.rediacc.com + releases.rediacc.com R2 backstop", read-only GETs, no substitute needed or possible.

**`.ci/scripts/deploy/verify-stable-endpoints.sh`**
Command: `.ci/scripts/deploy/verify-stable-endpoints.sh` (no args, no required env)
Template: A -- {TARGET_SYSTEM}="production www.rediacc.com stable endpoints", read-only GETs.

### Tier Q (3) -- read-only in effect, needs creds this sandbox lacks

**`.ci/scripts/release/assert-artifact-version.sh`**
Command: `VERSION=<SEMVER> CI_RUN_ID=<CI RUN ID> GITHUB_REPOSITORY=rediacc/console GH_TOKEN=<SECRET> .ci/scripts/release/assert-artifact-version.sh`
Env: `VERSION`, `CI_RUN_ID`, `GITHUB_REPOSITORY` (plain); `GH_TOKEN` (**SECRET**)
Template: A -- {TARGET_SYSTEM}="the real GitHub Actions run's cli-manifest artifact"; read-only `gh run download`.

**`.ci/scripts/release/assert-edge-tag-exists.sh`**
Command: `GH_TOKEN=<SECRET> CLOUDFLARE_R2_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_ENDPOINT=<R2 ENDPOINT URL> .ci/scripts/release/assert-edge-tag-exists.sh --version <SEMVER>`
Env: `GH_TOKEN`/`GITHUB_TOKEN` (**SECRET**), `CLOUDFLARE_R2_ACCESS_KEY_ID` (**SECRET**), `CLOUDFLARE_R2_SECRET_ACCESS_KEY` (**SECRET**), `CLOUDFLARE_R2_ENDPOINT` (plain URL); optional `GITHUB_REPOSITORY`, `RELEASES_BUCKET` (plain)
Template: A -- {TARGET_SYSTEM}="the real git tag, GitHub Release, and R2 `.released` sentinel"; read-only.

**`.ci/scripts/release/reprobe-r2-sentinel.sh`**
Command: `VERSION=<vSEMVER> CLOUDFLARE_R2_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_ENDPOINT=<R2 ENDPOINT URL> .ci/scripts/release/reprobe-r2-sentinel.sh`
Env: `VERSION` (plain), `CLOUDFLARE_R2_ACCESS_KEY_ID` / `CLOUDFLARE_R2_SECRET_ACCESS_KEY` (**SECRET**), `CLOUDFLARE_R2_ENDPOINT` (plain URL)
Template: A -- {TARGET_SYSTEM}="the real production R2 release sentinel"; read-only.

### Tier M-contained (9) -- mutating, disposable/staging substitute exists

**`.ci/scripts/deploy/cf-purge-urls.sh`**
Command: `printf '%s\n' <SUBSTITUTE URL 1> <SUBSTITUTE URL 2> | CLOUDFLARE_API_TOKEN=<SECRET> .ci/scripts/deploy/cf-purge-urls.sh --zone <SCOPED ZONE ID>`
Env: `CLOUDFLARE_API_TOKEN` (**SECRET**, preferred) or `CF_GLOBAL_API_KEY` (**SECRET**) + `CF_EMAIL` (plain)
Template: B -- {SUBSTITUTE_RESOURCE}="a scratch/staging hostname's cache entries, not releases.rediacc.com"; w7p5a dry-run pair `w7p5a-cf-purge-urls` already re-driven 2026-09-20.

**`.ci/scripts/deploy/purge-media-cache.sh`**
Command: `CLOUDFLARE_API_TOKEN=<SECRET> .ci/scripts/deploy/purge-media-cache.sh` (no args; zone id is hardcoded in-script to the real `rediacc.com` zone)
Env: `CLOUDFLARE_API_TOKEN` (**SECRET**) or `CF_GLOBAL_API_KEY` (**SECRET**) + `CF_EMAIL` (plain)
Template: B, with a caveat the operator must weigh: the zone id is hardcoded to the real zone, so a true substitute needs a scoped token limited to a non-production hostname's cache purge scope, not a different target argument -- {SUBSTITUTE_RESOURCE}="a narrowly-scoped token that cannot purge media.rediacc.com itself"; w7p5a pair `w7p5a-purge-media-cache` already re-driven 2026-09-20.

**`.ci/scripts/deploy/write-release-sentinel.sh`**
Command: `CLOUDFLARE_R2_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_ENDPOINT=<R2 ENDPOINT URL> RELEASES_BUCKET=<SCRATCH BUCKET NAME> .ci/scripts/deploy/write-release-sentinel.sh --version <SEMVER> --channel edge --commit-sha <SHA>`
Env: `CLOUDFLARE_R2_ACCESS_KEY_ID` / `CLOUDFLARE_R2_SECRET_ACCESS_KEY` (**SECRET**), `CLOUDFLARE_R2_ENDPOINT` (plain URL), `RELEASES_BUCKET` (plain, optional, default `rediacc-releases`)
Template: B -- {SUBSTITUTE_RESOURCE}="a scratch R2 bucket set via `RELEASES_BUCKET`, not `rediacc-releases`".

**`.ci/scripts/deploy/clone-d1.sh`**
Command: `CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ACCOUNT_ID=<ACCOUNT ID> .ci/scripts/deploy/clone-d1.sh --source <SOURCE DB NAME> --target <DISPOSABLE TARGET DB NAME> [--wrangler-config wrangler.preview.toml] [--sanitize]`
Env: `CLOUDFLARE_API_TOKEN` (**SECRET**), `CLOUDFLARE_ACCOUNT_ID` (plain)
Template: B -- {SUBSTITUTE_RESOURCE}="the `--target` database itself, since the script's own interface is source-vs-disposable-target"; e.g. `--target account-db-pr-42`, deleted by the operator after the run.

**`.ci/scripts/deploy/simulate-promotion.sh`**
Command: `CHANNEL=<SOURCE CHANNEL, e.g. pr-123> AWS_ACCESS_KEY_ID=<SECRET> AWS_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_ENDPOINT=<R2 ENDPOINT URL> CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ZONE_ID=<ZONE ID> .ci/scripts/deploy/simulate-promotion.sh`
Env: `CHANNEL`, `CLOUDFLARE_ZONE_ID` (plain); `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `CLOUDFLARE_R2_ENDPOINT` / `CLOUDFLARE_API_TOKEN` (**SECRET**)
Template: B -- {SUBSTITUTE_RESOURCE}="the script's own `<channel>-promoted` throwaway R2 channel; this script IS the disposable substitute by design, never production `stable/`".

**`.ci/scripts/deploy/sync-media-from-r2.sh`**
Command: `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_MEDIA_ENDPOINT=<R2 ENDPOINT URL> .ci/scripts/deploy/sync-media-from-r2.sh --audio-only` (real run = same invocation without `--dry-run`; scope narrowed with `--tutorials-only`/`--solutions-only`/`--audio-only`)
Env: `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID` / `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY` (**SECRET**), `CLOUDFLARE_R2_MEDIA_ENDPOINT` (plain URL)
Template: B -- read-direction only (download, no mutation of the bucket), so {SUBSTITUTE_RESOURCE}="a disposable local destination directory; the read against real R2 media metadata is itself the smallest-blast-radius option this tier has" -- operator's call on whether a read against real R2 still needs Template A instead, since nothing at the source is mutated.

**`.ci/scripts/deploy/upload-repos-to-r2.sh`**
Command: `CHANNEL=<SCRATCH CHANNEL, e.g. pr-0> CLOUDFLARE_R2_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_ENDPOINT=<SCRATCH R2 ENDPOINT URL> CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ZONE_ID=<ZONE ID> .ci/scripts/deploy/upload-repos-to-r2.sh`
Env: `CHANNEL`, `CLOUDFLARE_ZONE_ID` (plain); `CLOUDFLARE_R2_ACCESS_KEY_ID` / `CLOUDFLARE_R2_SECRET_ACCESS_KEY` / `CLOUDFLARE_R2_ENDPOINT` / `CLOUDFLARE_API_TOKEN` (**SECRET**)
Template: B -- {SUBSTITUTE_RESOURCE}="a scratch R2 bucket/endpoint, per the script's own header instruction to point `CLOUDFLARE_R2_ENDPOINT` at one first".

**`.ci/scripts/deploy/upload-to-r2.sh`**
Command: `CLOUDFLARE_R2_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_ENDPOINT=<SCRATCH R2 ENDPOINT URL> .ci/scripts/deploy/upload-to-r2.sh --version <SEMVER> --channel <SCRATCH CHANNEL>` (real run = same invocation without `--dry-run`)
Env: `CLOUDFLARE_R2_ACCESS_KEY_ID` / `CLOUDFLARE_R2_SECRET_ACCESS_KEY` (**SECRET**), `CLOUDFLARE_R2_ENDPOINT` (plain URL); optional `SKIP_RELEASE` (plain)
Template: B -- {SUBSTITUTE_RESOURCE}="a scratch R2 bucket at a substitute `CLOUDFLARE_R2_ENDPOINT`".

**`.ci/scripts/deploy/test-d1-migrations.sh`**
Command: `CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ACCOUNT_ID=<ACCOUNT ID> .ci/scripts/deploy/test-d1-migrations.sh` (no other args; reads `regions.json` for db names)
Env: `CLOUDFLARE_API_TOKEN` (**SECRET**), `CLOUDFLARE_ACCOUNT_ID` (plain); optional `GITHUB_RUN_ID` / `GITHUB_RUN_ATTEMPT` / `GITHUB_WORKSPACE` (plain)
Template: B -- {SUBSTITUTE_RESOURCE}="the script's own ephemeral per-run D1 clones, deleted by its own EXIT trap; this script IS the disposable substitute by design".

### Tier M-live (18) -- mutating, no safe non-prod target, irreversible/public-facing

**`.ci/scripts/deploy/deploy-account.sh`**
Command: `CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ACCOUNT_ID=<ACCOUNT ID> .ci/scripts/deploy/deploy-account.sh --region <eu|us|asia> [--target edge]`
Env: `CLOUDFLARE_API_TOKEN` (**SECRET**), `CLOUDFLARE_ACCOUNT_ID` (plain)
Template: A -- {TARGET_SYSTEM}="the real regional account Worker (production unless `--target edge`)".

**`.ci/scripts/deploy/deploy-edge.sh`**
Command: `CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ACCOUNT_ID=<ACCOUNT ID> .ci/scripts/deploy/deploy-edge.sh` (no args)
Template: A -- {TARGET_SYSTEM}="the real edge.rediacc.com marketing Worker".

**`.ci/scripts/deploy/deploy-proxy.sh`**
Command: `CLOUDFLARE_API_TOKEN=<SCOPED SECRET, never the global key> .ci/scripts/deploy/deploy-proxy.sh --region eu`
Template: A -- {TARGET_SYSTEM}="the real executor proxy Worker + Container". Already MANUAL ONLY by the script's own header (not wired into any pipeline); the operator is already the only path here regardless of this plan.

**`.ci/scripts/deploy/deploy-www.sh`**
Command: `CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ACCOUNT_ID=<ACCOUNT ID> .ci/scripts/deploy/deploy-www.sh` (production) or `--name <pr-N>` (preview -- still a real Worker deploy, just not the production hostname)
Template: A -- {TARGET_SYSTEM}="the real www.rediacc.com marketing Worker (production form)"; the `--name pr-N` preview form still deploys a real Worker and mints a real per-PR D1 database, so it is not a Tier M-contained substitute in the plan's own sense.

**`.ci/scripts/deploy/promote-docker-to-stable-hotfix.sh`**
Command: `.ci/scripts/deploy/promote-docker-to-stable-hotfix.sh` (no args; requires a docker daemon already logged in to ghcr.io -- credential is the docker login, not a script env var)
Template: A -- {TARGET_SYSTEM}="the real `ghcr.io/rediacc/{renet,rdc,server}:stable` tags"; w7p5a-adjacent dry-run pair `w7p6-promote-docker-to-stable-hotfix` (W7P6 port-level) plus `w7p5a-promote-docker-to-stable-hotfix` re-driven 2026-09-20.

**`.ci/scripts/deploy/promote-r2-to-stable-hotfix.sh`**
Command: `CLOUDFLARE_R2_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_ENDPOINT=<R2 ENDPOINT URL> [CLOUDFLARE_ZONE_ID=<ZONE ID> CLOUDFLARE_API_TOKEN=<SECRET>] .ci/scripts/deploy/promote-r2-to-stable-hotfix.sh`
Template: A -- {TARGET_SYSTEM}="the real production R2 `stable/` channel (every format)".

**`.ci/scripts/deploy/promote-r2-to-stable.sh`**
Command: `AWS_ACCESS_KEY_ID=<SECRET> AWS_SECRET_ACCESS_KEY=<SECRET> AWS_DEFAULT_REGION=auto CLOUDFLARE_R2_ENDPOINT=<R2 ENDPOINT URL> EDGE_VERSION=<SEMVER, log only> .ci/scripts/deploy/promote-r2-to-stable.sh`
Template: A -- {TARGET_SYSTEM}="the real production R2 `stable/` channel, soak-gated two-phase upload"; w7p5a pair `w7p5a-promote-r2-to-stable` already re-driven 2026-09-20.

**`.ci/scripts/deploy/set-account-worker-secrets.sh`**
Command: `WORKER_NAME=<WORKER NAME> TARGET=<stable|edge> SUFFIX=<EU|US|ASIA> CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ACCOUNT_ID=<ACCOUNT ID> ACCOUNT_ED25519_PRIVATE_KEY=<SECRET> ACCOUNT_ED25519_PUBLIC_KEY=<PLAIN> ACCOUNT_X25519_PRIVATE_KEY=<SECRET> ACCOUNT_X25519_PUBLIC_KEY=<PLAIN> ACCOUNT_SERVER_API_KEY=<SECRET> ACCOUNT_JWT_SECRET=<SECRET> ROOT_EMAIL=<PLAIN> CLOUDFLARE_TURNSTILE_SECRET_KEY=<SECRET> STRIPE_SECRET_KEY=<SECRET> STRIPE_WEBHOOK_SECRET_<SUFFIX>=<SECRET> AWS_SES_ACCESS_KEY_ID_<SUFFIX>=<SECRET> AWS_SES_SECRET_ACCESS_KEY_<SUFFIX>=<SECRET> AWS_SES_REGION=<PLAIN> AWS_SES_FROM=<PLAIN> AWS_SES_CONFIGURATION_SET=<PLAIN> ACCOUNT_BACKUP_S3_ENDPOINT=<PLAIN> ACCOUNT_BACKUP_S3_ACCESS_KEY_ID=<SECRET> ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY=<SECRET> BACKUP_BUCKET_STABLE=<PLAIN> BACKUP_BUCKET_EDGE=<PLAIN> R2_JURISDICTION=<PLAIN> OBS_OTLP_CREDENTIALS_<SUFFIX>=<SECRET> .ci/scripts/deploy/set-account-worker-secrets.sh`
Template: A -- {TARGET_SYSTEM}="the real regional account Worker's secret store (one `wrangler secret bulk` call)". Per this plan's Implementation #4, redact every SECRET-marked value before the writer or ledger ever sees any output line from this script.

**`.ci/scripts/deploy/set-preview-worker-secrets.sh`**
Command: `PR_NUMBER=<PR NUMBER> CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ACCOUNT_ID=<ACCOUNT ID> ACCOUNT_ED25519_PRIVATE_KEY=<SECRET> ACCOUNT_ED25519_PUBLIC_KEY=<PLAIN> ACCOUNT_X25519_PRIVATE_KEY=<SECRET> ACCOUNT_X25519_PUBLIC_KEY=<PLAIN> ACCOUNT_SERVER_API_KEY=<SECRET> ACCOUNT_JWT_SECRET=<SECRET> STRIPE_SECRET_KEY=<SECRET> STRIPE_WEBHOOK_SECRET=<SECRET> ROOT_EMAIL=<PLAIN> CLOUDFLARE_TURNSTILE_SECRET_KEY=<SECRET> AWS_SES_ACCESS_KEY_ID=<SECRET> AWS_SES_SECRET_ACCESS_KEY=<SECRET> AWS_SES_REGION=<PLAIN> AWS_SES_FROM=<PLAIN> AWS_SES_CONFIGURATION_SET=<PLAIN> .ci/scripts/deploy/set-preview-worker-secrets.sh`
Template: A -- {TARGET_SYSTEM}="a real per-PR preview Worker's secret store (not production, but a real live Worker, hence M-live not M-contained per this plan's own tier table)". Redact every SECRET-marked value before recording.

**`.ci/scripts/deploy/set-www-worker-secrets.sh`**
Command: `WORKER_NAME=<WORKER NAME> CLOUDFLARE_API_TOKEN=<SECRET> CLOUDFLARE_ACCOUNT_ID=<ACCOUNT ID> ACCOUNT_ED25519_PRIVATE_KEY=<SECRET> ACCOUNT_ED25519_PUBLIC_KEY=<PLAIN> ACCOUNT_X25519_PRIVATE_KEY=<SECRET> ACCOUNT_X25519_PUBLIC_KEY=<PLAIN> ACCOUNT_SERVER_API_KEY=<SECRET> ACCOUNT_JWT_SECRET=<SECRET> STRIPE_SECRET_KEY=<SECRET> STRIPE_WEBHOOK_SECRET=<SECRET> ROOT_EMAIL=<PLAIN> CLOUDFLARE_TURNSTILE_SECRET_KEY=<SECRET> AWS_SES_ACCESS_KEY_ID=<SECRET> AWS_SES_SECRET_ACCESS_KEY=<SECRET> AWS_SES_REGION=<PLAIN> AWS_SES_FROM=<PLAIN> AWS_SES_CONFIGURATION_SET=<PLAIN> SELLER_NAME=<PLAIN> SELLER_VAT_NUMBER=<PLAIN> SELLER_REGISTRATION_NUMBER=<PLAIN> SELLER_ADDRESS_LINE1=<PLAIN> SELLER_ADDRESS_LINE2=<PLAIN> SELLER_CITY=<PLAIN> SELLER_POSTAL_CODE=<PLAIN> SELLER_COUNTRY=<PLAIN> SELLER_EMAIL=<PLAIN> .ci/scripts/deploy/set-www-worker-secrets.sh`
Template: A -- {TARGET_SYSTEM}="the real www Worker's secret store (stable or edge, by `WORKER_NAME`)". Redact every SECRET-marked value before recording.

**`.ci/scripts/deploy/delete-r2-channel.sh`**
Command: `CHANNEL=<CHANNEL, e.g. pr-123> RELEASES_BUCKET=<PLAIN> CLOUDFLARE_R2_ENDPOINT=<R2 ENDPOINT URL> AWS_ACCESS_KEY_ID=<SECRET> AWS_SECRET_ACCESS_KEY=<SECRET> .ci/scripts/deploy/delete-r2-channel.sh`
Template: A -- {TARGET_SYSTEM}="the real R2 release bucket's channel prefix (deletion, best-effort)"; per the plan's own tier table this is M-live (irreversible deletion), not M-contained -- there is no substitute deletion target that proves the same code path without deleting something real.

**`.ci/scripts/deploy/sync-media-to-r2.sh`**
Command: `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_MEDIA_ENDPOINT=<R2 ENDPOINT URL> .ci/scripts/deploy/sync-media-to-r2.sh --audio-only` (real run = same invocation without `--dry-run`; add `--delete` only deliberately)
Template: A -- {TARGET_SYSTEM}="the real shared `rediacc-www-media` bucket"; no disposable substitute exists because the bucket is the one public CDN origin.

**`.ci/scripts/release/advance-contract-floor.sh`**
Command: `CLOUDFLARE_R2_ACCESS_KEY_ID=<SECRET> CLOUDFLARE_R2_SECRET_ACCESS_KEY=<SECRET> CLOUDFLARE_R2_ENDPOINT=<R2 ENDPOINT URL> GIT_BOT_NAME=<PLAIN> GIT_BOT_EMAIL=<PLAIN> .ci/scripts/release/advance-contract-floor.sh`
Template: A -- {TARGET_SYSTEM}="real production R2 sentinels, plus a real `git push` to `origin/main` on an actual advance". Highest-caution M-live entry along with the two below: a mistake here lands directly on `main`.

**`.ci/scripts/release/update-homebrew-tap.sh`**
Command: `GITHUB_PAT=<SECRET> .ci/scripts/release/update-homebrew-tap.sh --version <SEMVER> --push` (or `--stage-only`; `--local-checksums <DIR>` avoids an R2 download step but does not avoid the push)
Template: A -- {TARGET_SYSTEM}="the real `homebrew-tap` repo (a `git push` to a public remote) plus the submodule pointer".

**`.ci/scripts/release/mark-production.sh`**
Command: `GH_TOKEN=<SECRET> .ci/scripts/release/mark-production.sh <SEMVER>` (or `VERSION=<SEMVER>`)
Template: A -- {TARGET_SYSTEM}="the real `production` git tag plus the `--latest` flag on the real GitHub Release".

**`.ci/scripts/release/create-github-release.sh`**
Command: `VERSION=<SEMVER> GITHUB_SHA=<COMMIT SHA> GITHUB_REPOSITORY=rediacc/console GH_TOKEN=<SECRET> .ci/scripts/release/create-github-release.sh` (expects `dist/cli` and `dist/packages` already populated)
Template: A -- {TARGET_SYSTEM}="a real, publicly visible GitHub Release with real uploaded assets".

**`.ci/scripts/release/cleanup-channel-docker-tags.sh`**
Command: `CHANNEL=<edge|stable> GITHUB_STEP_SUMMARY=<PATH> GH_TOKEN=<SECRET, delete:packages scope> .ci/scripts/release/cleanup-channel-docker-tags.sh`
Template: A -- {TARGET_SYSTEM}="the real GHCR channel Docker tag (deletion)"; non-critical by the script's own design (exits 0 either way), but still a real deletion against a real registry.

**`.ci/scripts/release/tag-submodules.sh`**
Command: `VERSION=<SEMVER> [GITHUB_PAT=<SECRET>] .ci/scripts/release/tag-submodules.sh`
Template: A -- {TARGET_SYSTEM}="the real `private/renet` submodule remote (a real tag push)".

## Results of the 2026-09-24 session run

Operator ruling 2026-09-24: session d778be9d runs Tier M-contained and Tier Q; Tier M-live stays operator-run.
Every run happened inside the devbox through `bws_env exec --profile publish-solutions` (plus `publish-media` for sync-media-from-r2). The global key never left the driver process, and the scripts under test saw only a minted token.
Drivers live under `.ci/cache/w7p5a-realrun/` (gitignored), with the raw stdout/stderr/rc per side in `out/`. The devbox cannot see the session scratchpad, which is why they are there.

| # | Path | Outcome | Disposable substitute | Token (2h, revoked on EXIT) |
|---|---|---|---|---|
| 1 | `cf-purge-urls.sh` | graduated, pair `w7p5a-cf-purge-urls` | 31 never-served `releases.rediacc.com/__w7p5a-scratch/1/*` URLs | `w7p5a-1-cachepurge-1` (Cache Purge, one zone), plus `w7p5a-1-zoneread-1` for the negative control |
| 2 | `purge-media-cache.sh` | NOT RUN, moved to the M-live queue | none possible (zone and host are literals) | none |
| 3 | `write-release-sentinel.sh` | graduated, pair `w7p5a-write-release-sentinel` | buckets `w7p5a-scratch-{a,b}-1` | `w7p5a-38-scratchwrite-1` (Item Write, two scratch buckets) |
| 4 | `clone-d1.sh` | graduated, pair `w7p6-clone-d1` | D1 `w7p5a-scratch-{src,dst-a,dst-b}-1`, name-guarded | `w7p5a-49-d1write-1` (D1 Write) |
| 5 | `simulate-promotion.sh` | graduated, pair `w7p6-simulate-promotion` | EU-jurisdiction `rediacc-releases`, created as a separate bucket (`jurisdiction: eu`, fresh creation_date) and deleted after | `w7p5a-75-eureleases-1` (Item Write on `_eu_rediacc-releases` only; refused on the production bucket) |
| 6 | `sync-media-from-r2.sh` | graduated, pair `w7p6-sync-media-from-r2` | scratch roots as destination; production bucket only read | `w7p5a-6-mediaread-1` (Item Read, `rediacc-www-media`) |
| 7 | `upload-repos-to-r2.sh` | graduated, pair `w7p5a-upload-repos-to-r2` | the same EU bucket, plus fixture `dist/` roots | `w7p5a-75-eureleases-1` |
| 8 | `upload-to-r2.sh` | graduated, pair `w7p6-upload-to-r2` | buckets `w7p5a-scratch-{a,b}-1`, seeded so pruning ran | `w7p5a-38-scratchwrite-1` |
| 9 | `test-d1-migrations.sh` | graduated, pair `w7p6-test-d1-migrations` | scratch roots whose `regions.json` names only `*-w7p5as1` source D1s | `w7p5a-49-d1write-1` |
| 10 | `assert-artifact-version.sh` | cannot clear today; refusal case run, both sides identical, exit 1 | none (read-only) | none (operator `gh auth token`) |
| 11 | `assert-edge-tag-exists.sh` | Python leg added to the note; counts unchanged | none (read-only production) | `w7p5a-q-r2read-1` (Item Read, `rediacc-releases`) |
| 12 | `reprobe-r2-sentinel.sh` | Python leg added; pair/ledger now `w7p6-reprobe-r2-sentinel` | none (read-only production) | `w7p5a-q-r2read-1` |

Gate, before: `28 'blocked', 20 ledgered ... 13 have their real-run leg confirmed and 7 are leg-blocked`. After the eighth graduation: `20 'blocked', 28 ledgered ... 21 have their real-run leg confirmed and 7 are leg-blocked`, rc=0 after every step.

Revocation proof (`out/revocation-proof.txt`): all seven minted tokens show `DELETE success=True ; verify success=False errors=[1000]`.
Teardown sweep, run last: `GET /user/tokens` lists no `w7p5a*` token, no `w7p5a*` bucket exists in the default or the EU jurisdiction, the EU `rediacc-releases` is gone (the production default-jurisdiction one is untouched), and no D1 database name contains `w7p5a`.

The devbox was recreated with `./run.sh devbox up` mid-run (between items 5/7 and 1) to gain the read-only bind of `~/.config/rediacc/bws-access-token`. Inside it the file is readable and not writable, and `bws secret list` returned 92 secrets.

### Findings from the real runs

1. **`EXPECTED_DRY_RUN_PATHS` was stale** (`test_w7p5a_dry_run_ledgers.py`): the 2026-09-23 graduations of verify-edge-endpoints, verify-stable-endpoints and assert-edge-tag-exists left three pins behind, so the module failed (4 failed, 61 passed). Fixed first, with a comment that a graduation removes its pin in the same change. The 2026-09-24 graduations removed cf-purge-urls, write-release-sentinel and upload-repos-to-r2 the same way; 44 passed after.
2. **simulate-promotion's empty-channel floor is unreachable against real R2, and the run dies silently.** `CHANNEL=w7p5a-empty` exits 1 on both sides after printing only `Copying apt/w7p5a-empty/ -> ...`. The installed `aws s3 ls` exits 1 on a missing prefix with no output, and `pipefail` ends the run at `.ci/scripts/deploy/simulate-promotion.sh:186` before `:194`'s `refusing to promote an empty channel`. The port pins the same structure (`.ci/rediacc_ci/deploy/simulate_promotion.py:52-60`, `THE_EMPTY_CHANNEL_FLOOR_SITS_BEHIND_PIPEFAIL`). The real run settles the "depending on the aws build" question: the floor never prints. FIXED 2026-09-24 in both twins (worklist #e5ce5408). The listing is now captured first: exit 1 with no output falls through to the floor, and any other failure re-emits aws's stderr and prints `aws s3 ls ... failed (exit N); nothing was promoted`. Two new differential cases fail on the pre-fix code, and a real re-run against R2 with a read-only token now prints the refusal on both sides.
3. **cf-purge-urls had no non-production zone to use.** The account holds `rediacc.com` and `rediacc.io`, and neither is a staging zone, so the run used never-served URL paths on the production zone. The token was scoped to that one zone and the purge was URL-only.

### assert-artifact-version.sh, post-merge run sheet

- Precondition: a push-triggered green Console CI run on main less than 24h old (`cd-stage.yml` uploads `cli-manifest` with 1-day retention). On 2026-09-24 `gh api repos/rediacc/console/actions/artifacts?name=cli-manifest` reports 0.
- Run ID: `gh run list --branch main --event push --workflow "Console CI" -L1`; take `VERSION` from that run's manifest.
- Commands, in the devbox: `GH_TOKEN=$(gh auth token) VERSION=<v> CI_RUN_ID=<id> GITHUB_REPOSITORY=rediacc/console .ci/scripts/release/assert-artifact-version.sh`, then `rm -rf /tmp/cd-artifact-check`, then `PYTHONPATH=.ci python3 -m rediacc_ci.release.assert_artifact_version` with the same env.
- Expected: both print `::notice::Artifact version v<X> matches promotion target v<X>` and exit 0, identical streams.
- Refusal already observed 2026-09-24 (`VERSION=1.3.12 CI_RUN_ID=34074211598`): both sides exit 1 with the identical three `::error::cli-manifest artifact not found ...` lines.
- Graduate with Template A: `status: "ledger"`, pair `w7p5a-assert-artifact-version`, drop `blocker`/`policy_file`/`dry_run_*`. Delete its blocklist line and BLOCKER comment, and remove it from `EXPECTED_DRY_RUN_PATHS`. Then run `npm run check:ci-w7p5a-real-run-blockers`, which should read 19 / 29 / 22.
- Rollback: none, it is read-only. No credential is minted.

## Run sheets (2026-09-24)

Written by a Plan agent for session d778be9d on 2026-09-24 and appended with headings demoted one level and two wording fixes for the prose gate. The operator ruling of 2026-09-24 overrides it where they conflict: item 2 is never run by the session, items 5 and 7 run only against a separately created EU-jurisdiction bucket, and nothing is committed by the session.

### Read this first

1. **Two of the three Tier Q items are already cleared, but only the bash side ran.** Commit `5190ab83d` (2026-09-23) moved `assert-edge-tag-exists.sh` and `reprobe-r2-sentinel.sh` from blocked to ledger (`.ci/shadow/w7p5a-status.json:275`, `:330`). Both notes quote only the `.sh` command, so the Python port never ran against production. For these two, what's left is the Python leg. The gate counts won't change.
2. **One ledger test is probably already failing, found by reading the code.** `EXPECTED_DRY_RUN_PATHS` (`.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py:37-51`) still lists `verify-edge-endpoints.sh`, `verify-stable-endpoints.sh` and `assert-edge-tag-exists.sh`. Their rows lost the `dry_run_ledger` field when they graduated. So `test_no_ledgered_path_quietly_loses_its_field` (`:208`) should fail, and the parametrized test at `:219` should error with `StopIteration` from `_row_for`. pytest was not run when this was written (it is not on the host PATH; `.ci/cache/toolchain/uv-tools/bin/pytest` is). Confirm it in the devbox and fix it before any new graduation. Every graduation below makes the same edit.
3. **The substitute-run wording collides with the gate's phrase.** The gate only counts a real run as confirmed if the note contains the exact phrase `real run each done directly` (`.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py:34`, `:183-192`). Template B (`agent/plans/PLAN-w7p5a-real-run-dispatch.md:85`) does not contain that phrase. Each substitute note must therefore say something like `real run each done directly against the DISPOSABLE SUBSTITUTE <x>, not production`. The alternative is a `.w7p5a-real-run-leg-blocklist` entry (Template C). **The operator should confirm which one.**
4. **CI already has real-run evidence for some items, and the logs expire.**
   - The cut-over Python ports ran for real in PR CI run `35571489498`:
     - Migration Test, job `106268930742`: `rediacc_ci.deploy.test_d1_migrations`, "All 6 regional migration tests passed", all clones deleted.
     - i18n, job `106268955600`: `rediacc_ci.deploy.sync_media_from_r2 --audio-only`.
   - The bash runs on main (run `34074211598`, 2026-09-07) already return HTTP 410; their logs are gone. The 2026-09-21 logs will expire soon too, so save them now.
   - The cutover commit `c5cb6e8a6` is not on `origin/main`.
5. **Tools: run everything in the devbox.** `aws`, `wrangler` and `sqlite3` are missing on the host (checked with `which`). The earlier Tier Q run also used the devbox. `git worktree add` is blocked by `.claude/rediacc_hooks/guards/block_worktree_add.py`, so scratch roots are built by copying files, not with worktrees.

### Summary table

| # | Item | Tier | Disposable substitute | Safe for the session to run? |
|---|---|---|---|---|
| 1 | `deploy/cf-purge-urls.sh` | M-c | One-off URLs under `releases.rediacc.com/__w7p5a-scratch/<N>/` that were never served | **Yes.** It purges by URL only (`files:[…]`, `:89`) and can't purge everything; evicting URLs nobody serves changes nothing. The token itself isn't isolated (Cache Purge covers the whole zone), so the isolation comes from the arguments. |
| 2 | `deploy/purge-media-cache.sh` | M-c | **None possible** | **No.** Zone and hostname are hard-coded (`:25-26`; the port at `.ci/rediacc_ci/deploy/purge_media_cache.py:46-47` says so on purpose). The success path purges the whole live `media.rediacc.com` cache. A token can't be limited to a hostname. Hand to the operator (move to M-live). |
| 3 | `deploy/write-release-sentinel.sh` | M-c | Scratch buckets `w7p5a-scratch-a-<N>` and `-b-<N>`, selected by `RELEASES_BUCKET` | **Yes.** The bucket comes from `RELEASES_BUCKET` (`.ci/scripts/lib/release-state-validator.sh:73`), and the minted token only reaches the scratch buckets. |
| 4 | `deploy/clone-d1.sh` | M-c | Scratch D1s `w7p5a-scratch-src-<N>` and `-dst-{a,b}-<N>` | **Yes, with a guard.** The source and target are arguments. D1 tokens can't be limited to one database, so the driver must refuse any name not starting `w7p5a-scratch-`. |
| 5 | `deploy/simulate-promotion.sh` | M-c | A bucket with the same name `rediacc-releases`, created in the **EU jurisdiction**, reached at `<acct>.eu.r2…`, with a token scoped only to that bucket | **Only if that bucket can be created.** `BUCKET="rediacc-releases"` is hard-coded (`:51`). If Cloudflare refuses the same name across jurisdictions, **No**: it would write to the production bucket. |
| 6 | `deploy/sync-media-from-r2.sh` | M-c | A scratch local destination (scratch repo root). The production bucket is only read. | **Yes.** It only reads R2 (`aws s3 sync` from the bucket, `:104`) with a minted read-only token. |
| 7 | `deploy/upload-repos-to-r2.sh` | M-c | Same EU-jurisdiction `rediacc-releases` bucket as item 5 | **Only if that bucket can be created** (bucket hard-coded at `:116`, `:148`). Otherwise **No**. The header's "point the endpoint at a scratch bucket" (`:34`) does not change the bucket name. |
| 8 | `deploy/upload-to-r2.sh` | M-c | Scratch buckets a and b, selected by `RELEASES_BUCKET` | **Yes.** `.ci/config/constants.sh:201` honours `RELEASES_BUCKET`; the port does the same (`.ci/rediacc_ci/deploy/upload_to_r2.py:184-189`). |
| 9 | `deploy/test-d1-migrations.sh` | M-c | A scratch repo root whose `regions.json` lists only scratch source D1s | **Yes, retargeted only.** As-is it exports all 6 production regional databases (`:52-60`, `:114`). The retargeted form only reads scratch databases. |
| 10 | `release/assert-artifact-version.sh` | Q | None; read-only against GitHub | **Yes, it's read-only, but it can't clear today.** There are 0 `cli-manifest` artifacts (API query, 2026-09-24). The success path needs a push run on main less than 24h old (`.github/workflows/cd-stage.yml:302-307`). |
| 11 | `release/assert-edge-tag-exists.sh` | Q | None; read-only | **Yes.** Already cleared with bash only; only the Python leg remains. |
| 12 | `release/reprobe-r2-sentinel.sh` | Q | None; read-only | **Yes.** Already cleared with bash only; only the Python leg remains. |

**The session must not run item 2.** Items 5 and 7 are also off-limits unless the EU-bucket check in step S4 below succeeds.

### Shared setup (every run sheet refers to this)

**S1. Where to run.**
- Wrap every command as `./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile publish-solutions [--profile publish-media] -- bash "$S/driver-<item>.sh"`.
- `publish-solutions` is the smallest profile that holds `CF_GLOBAL_API_KEY` and `CF_EMAIL` (`.ci/config/secret-supply.json` → `consumers`).
- Item 6 must also name `--profile publish-media`, or the pre-bash guard blocks it (`.claude/rediacc_hooks/guards/block_host_toolchain_run.py:97-100`, `:413-435`).
- Check first that the bootstrap works: `... bws_env exec --profile publish-solutions -- true`.
- `$S` is a scratch directory visible inside the devbox. Check with `./run.sh devbox exec -- ls "$S"`.

**S2. Minting and revoking tokens (the pattern from `scripts/ops/lib/cf-auth.sh:78-169` and `:215-228`, made narrower).** Each driver does this:
```
- Look up permission-group IDs by name: `GET /user/tokens/permission_groups`. The D1 Write ID is already known: `09b2857d1c31407795e75e3fed8617a1` (`scripts/ops/lib/cf-auth.sh:104`, `:146`).
```
- Mint: `POST https://api.cloudflare.com/client/v4/user/tokens` with the `X-Auth-Email`/`X-Auth-Key` headers. The body has a name `w7p5a-<item>-<N>`, `expires_on` set to now + 2h (a backstop if revocation fails), and a single policy.
- Set `trap revoke EXIT`, where `revoke` runs `curl -X DELETE …/user/tokens/$TOKEN_ID` with the global-key headers.
- After revoking, confirm the token is dead: `curl …/user/tokens/verify -H "Authorization: Bearer $TOKEN"` must return `success:false`.
- For R2 S3 credentials: access key ID = the token's `id`; secret = `sha256(token value)`.
```
- Bucket resource keys are `com.cloudflare.edge.r2.bucket.fa51e4a18d553c30e1633288e9733d04_default_<bucket>` (or `_eu_<bucket>` for the EU jurisdiction).
```
- Never echo the token value.

**S3. Keep the environment clean.** Launch the script under test with `env -u CF_GLOBAL_API_KEY -u CF_EMAIL -u CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID -u CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY`, then add back only the minted values. Otherwise `.ci/scripts/deploy/cf-purge-urls.sh:75-76` silently falls back to the global key. Also:
- Give each side its own `AWS_CONFIG_FILE=$S/aws-<side>.cfg`; `.ci/scripts/deploy/simulate-promotion.sh:62-64` runs `aws configure set`.
- Between sides, `rm -f /tmp/config` and `rm -rf /tmp/cd-artifact-check`. Both are fixed paths the bash script and the port share.

**S4. Plain IDs and endpoints.**
```
- Account: `fa51e4a18d553c30e1633288e9733d04` (`.ci/docs/r2-setup.md:35`).
- rediacc.com zone: `9e802649c143c9cefd811d8fd671d31c` (`.ci/scripts/deploy/purge-media-cache.sh:25`).
```
- Default endpoint: `https://<acct>.r2.cloudflarestorage.com`. EU endpoint: `https://<acct>.eu.r2.cloudflarestorage.com`.
- Scratch bucket create/delete: `POST` / `DELETE /accounts/<acct>/r2/buckets[/<name>]`, adding the header `cf-r2-jurisdiction: eu` for EU. A bucket must be emptied before deletion: `aws s3 rm s3://<b> --recursive --endpoint-url <ep>`.

**S5. How to compare the two sides.**
- For each side, capture the exit code, stdout and stderr into files.
- Normalise timestamps, temp paths, and the a/b bucket or run-ID suffix.
- `diff` the normalised files.
- Snapshot the remote state: `aws s3api list-objects-v2` (key and size), plus `head-object` for CacheControl and ContentType.

**S6. Ledger edit that clears an item** (L for short; the same for every item):
- **(a)** In the `.ci/shadow/w7p5a-status.json` row: set `status: "ledger"`; set `pair` / `ledger` to the existing `w7p6-<slug>` pair (or the `w7p5a-<slug>` pair if one exists); remove the `blocker`, `policy_file` and `dry_run_*` fields; write a Template B note that contains the literal phrase and names the substitute.
- **(b)** Delete the path's line from `.ci/policy/.w7p5a-real-run-blocklist`, and its `# BLOCKER` comment if it was the last path in that group.
- **(c)** If the path is in `EXPECTED_DRY_RUN_PATHS` (`.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py:37-51`), remove it.
- **(d)** Run `npm run check:ci-w7p5a-real-run-blockers`.
- **(e)** Run `./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py`.
- **(f)** Run `npx tsx scripts/lib/shadow-gate.ts --pair w7p6-<slug> --assert --k 5`. It must print `equivalence holds over 5 distinct trees`.

### Run sheets

#### 1. `cf-purge-urls.sh` (safe)
- **What it touches for real:** one `POST /zones/<zone>/purge_cache` with `{files:[…]}` per 30 URLs (`:86-102`). It **always exits 0**, even on API failure (`:21-28`, `:96-99`), so the exit code proves nothing. Stdout is the evidence.
- **Substitute:** 31 URLs `https://releases.rediacc.com/__w7p5a-scratch/<N>/f{01..31}.txt`, which were never served. 31 exercises the 30-URL batching. Nothing to create or destroy. Before running, list zones with `GET /zones?account.id=`; if a non-production zone exists, use it instead.
- **Commands:**
```
  - bash: `printf '%s\n' $URLS | CLOUDFLARE_API_TOKEN=$T .ci/scripts/deploy/cf-purge-urls.sh --zone 9e802649c143c9cefd811d8fd671d31c`
  - Python: the same pipe into `python3 -m rediacc_ci.deploy.cf_purge_urls --zone 9e802649c143c9cefd811d8fd671d31c`
```
- **Observation:** both sides print `purging 31 URL(s) from CF zone …` and `purged 31 URL(s) successfully`, with empty stderr.
  - Negative control: a second pair of runs with a Zone-Read-only token must print an identical `::warning::CF purge failed …` line and the same `.errors` JSON. This shows the success line isn't vacuous.
  - **Clears with:** L, pair `w7p5a-cf-purge-urls` (`.ci/shadow/w7p5a-status.json:69`, `blocklist:55`, EXPECTED `:38`).
- **Rollback:** none needed. A mistaken purge only causes a cache miss, which heals on the next request.
- **Credential:** yes. Minimal permission: Zone "Cache Purge" on the one zone, 2h expiry. Revoke with `DELETE /user/tokens/<id>`.

#### 2. `purge-media-cache.sh` (the session must NOT run this)
- **What it touches for real:** a purge of the whole `media.rediacc.com` host (`:43-47`). Objects there carry a one-year max-age, so the origin takes a refill burst.
- **Why no substitute works:** there are no arguments; the zone and hostname are literals. A token that can't purge only exercises the failure path.
- **Operator run sheet (for the M-live queue):**
  - Commands: `CLOUDFLARE_API_TOKEN=$T .ci/scripts/deploy/purge-media-cache.sh`, then `python3 -m rediacc_ci.deploy.purge_media_cache`.
  - Token: Zone "Cache Purge" on 9e80…, revoked the same way as item 1.
  - Observation: both print `Purge complete.` and exit 0.
  - Rollback: none; a purge can't be undone, but the cache refills on its own.
  - Clears with: L, pair `w7p5a-purge-media-cache` (`.ci/shadow/w7p5a-status.json:151`, `blocklist:77`, EXPECTED `:42`).
- **Optional read-only run the session could do instead:** a Zone-Read token. Both sides should exit 1 with `✗ Purge failed: [{"code":10000…}]`. That's Template C evidence only; it doesn't clear the item.

#### 3. `write-release-sentinel.sh` (safe)
- **What it touches for real:** `list-objects-v2` to count binaries, `aws s3 cp` of `cli/v<V>/.released`, then a read-back (`:110-155`).
- **Substitute:**
  - Create buckets `w7p5a-scratch-a-<N>` and `-b-<N>` (S4).
  - Seed each with `cli/v0.0.1-w7p5a/rdc-linux-x64`, a 1-byte file. Without it, the script refuses at `:120-124`.
  - Destroy: empty and delete both buckets.
- **Commands** (the minted token's S3 keys go in `CLOUDFLARE_R2_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY`, plus the default endpoint):
  - bash: `RELEASES_BUCKET=w7p5a-scratch-a-<N> … .ci/scripts/deploy/write-release-sentinel.sh --version 0.0.1-w7p5a --channel edge --commit-sha $(git rev-parse HEAD)`
  - Python: the same with bucket `-b-`, via `python3 -m rediacc_ci.deploy.write_release_sentinel …`
  - Refusal case: run both again with `--version 0.0.2-w7p5a`, which has no binaries. Both must exit 1 with `refusing to seal`.
- **Observation:** both exit 0 with identical `writing sentinel:` / `sealed` / `is sealed` lines. The two `.released` payloads match apart from `released_at`. `head-object` shows `CacheControl=no-cache` and `ContentType=application/json` on both.
  - **Clears with:** L, pair `w7p5a-write-release-sentinel` (`.ci/shadow/w7p5a-status.json:248`, `blocklist:99`, EXPECTED `:45`).
- **Rollback:** delete the buckets. Production is never touched.
- **Credential:** yes. "Workers R2 Storage Bucket Item Write" on the two scratch bucket resources only, 2h. Revoke as in S2.

#### 4. `clone-d1.sh` (safe, with the name guard)
- **What it touches for real:** `wrangler d1 export` on the source; `d1 execute` on the target, which drops every table and imports; then an FK check (`:94`, `:135-144`, `:151`).
- **Substitute:**
  - Create with the minted token: `npx wrangler d1 create w7p5a-scratch-src-<N>`, plus `…-dst-a-<N>` and `…-dst-b-<N>`.
  - Seed the source: `wrangler d1 execute w7p5a-scratch-src-<N> --remote --command "CREATE TABLE p(id INTEGER PRIMARY KEY); CREATE TABLE c(id INTEGER PRIMARY KEY, pid INTEGER REFERENCES p(id)); INSERT INTO p VALUES(1); INSERT INTO c VALUES(1,1);"`
  - Destroy: `wrangler d1 delete <name> --skip-confirmation` for all three, then confirm `wrangler d1 list --json` shows no `w7p5a-scratch`.
- **Guard:** the driver exits unless both `--source` and `--target` match `^w7p5a-scratch-`.
- **Commands:**
  - bash: `CLOUDFLARE_API_TOKEN=$T CLOUDFLARE_ACCOUNT_ID=<acct> .ci/scripts/deploy/clone-d1.sh --source w7p5a-scratch-src-<N> --target w7p5a-scratch-dst-a-<N>`
  - Python: `python3 -m rediacc_ci.deploy.clone_d1` with the same arguments and `dst-b`.
  - `--sanitize` is not exercised; `sanitize-d1.sql` expects the account schema.
- **Observation:** both exit 0 with the same `Exported N lines`, `Import complete` and `FK integrity check passed (0 violations)`. `SELECT count(*) FROM c` is equal on dst-a and dst-b. No `r2.cloudflarestorage.com` URL appears in either output (redaction at `:102`).
  - **Clears with:** L, pair `w7p6-clone-d1` (`.ci/shadow/w7p5a-status.json:79`, `blocklist:58`).
- **Rollback:** delete the three scratch databases.
- **Credential:** yes. Account "D1 Write" (`09b2857d…`). It can't be narrowed to one database, which is why the guard exists. 2h expiry, revoked as in S2.

#### 5. `simulate-promotion.sh` (only if step S4's EU bucket can be created)
- **What it touches for real:** `aws s3 ls` of `<dir>/<CH>/`; server-side `copy-object` into `<dir>/<CH>-promoted/`; a sed fix of `rpm/…/rediacc.repo` and `archlinux/…/rediacc.conf`; a call to `cf-purge-urls.sh` (`:50-51`, `:179-227`). It also writes `$GITHUB_ENV` (`:55`), `~/.aws/config` and `/tmp/config`.
- **Substitute:**
  - Create the EU-jurisdiction `rediacc-releases` bucket (S4 with the jurisdiction header). **If creation returns a name conflict, stop: this item is not isolatable.**
  - Seed: item 7's Python run leaves `apt|rpm|apk|archlinux/w7p5a-<N>/` there. Run item 7 first.
  - Destroy: empty the bucket through the EU endpoint, then delete it with the jurisdiction header.
- **Commands** (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` get the minted keys, because the script reads `AWS_*` at `:41`; `CLOUDFLARE_R2_ENDPOINT` is the EU endpoint; `CLOUDFLARE_ZONE_ID` is 9e80…; **no CF token**, so the purge step warns and exits 0 at `.ci/scripts/deploy/cf-purge-urls.sh:77-80`, and item 1 covers purging):
  - bash: `CHANNEL=w7p5a-<N> GITHUB_ENV=$S/ghenv-bash .ci/scripts/deploy/simulate-promotion.sh`
  - Between sides: `aws s3 rm --recursive` each of the four `*/w7p5a-<N>-promoted/` prefixes, EU endpoint only.
  - Python: `python3 -m rediacc_ci.deploy.simulate_promotion` with `GITHUB_ENV=$S/ghenv-py`.
  - Refusal case: `CHANNEL=w7p5a-empty` on both sides must print `refusing to promote an empty channel` and exit 1.
- **Driver guard:** assert the endpoint contains `.eu.` before any `rm`.
- **Observation:**
  - Both exit 0.
  - Four `Copying …` lines and the `Fixed channel in …` lines match.
  - The `-promoted` key set equals the source key set, with CacheControl `no-cache`.
  - The fixed configs contain `/w7p5a-<N>-promoted/`.
  - Both `GITHUB_ENV` files contain `PROMOTED=w7p5a-<N>-promoted`.
  - The purge-skip warning is identical.
  - **Clears with:** L, pair `w7p6-simulate-promotion` (`.ci/shadow/w7p5a-status.json:182`, `blocklist:85`).
- **Rollback:** delete the EU bucket. If a command ever pointed at the default endpoint by mistake, the EU-scoped token gets a 403, so production is protected by the credential, not by care.
- **Credential:** yes. "Bucket Item Write" on `…_eu_rediacc-releases` only, 2h, revoked as in S2.

#### 6. `sync-media-from-r2.sh` (safe)
- **What it touches for real:** `aws s3 sync s3://rediacc-www-media/tutorials/audio/` into `<REPO_ROOT>/packages/www/public/assets/tutorials/audio/` (`:48`, `:99-117`). It only reads the bucket.
- **Substitute:** two scratch roots, `$S/root-bash` and `$S/root-py`, each with a copy of `.ci/`. Both sides compute the root from their own file location (`:47`; `.ci/rediacc_ci/deploy/sync_media_from_r2.py:195`). Destroy: `rm -rf` both.
- **Commands:**
  - bash: `CLOUDFLARE_R2_MEDIA_*=<minted read-only> $S/root-bash/.ci/scripts/deploy/sync-media-from-r2.sh --audio-only`
  - Python: `PYTHONPATH=$S/root-py/.ci python3 -m rediacc_ci.deploy.sync_media_from_r2 --audio-only`
  - The outer command must include `--profile publish-media` (see S1).
- **Observation:** both exit 0 with identical `Restoring s3://rediacc-www-media/tutorials/audio/ -> …` and `Restore complete.` lines. `find … -type f -printf '%P %s\n' | sort | sha256sum` is equal for the two trees. Also attach the CI evidence: run `35571489498`, job `106268955600`.
  - **Clears with:** L, pair `w7p6-sync-media-from-r2` (`.ci/shadow/w7p5a-status.json:189`, `blocklist:88`).
- **Rollback:** delete the scratch roots. Nothing remote changes.
- **Credential:** yes. "Bucket Item Read" on `…_default_rediacc-www-media` only, 2h. This is narrower than the read/write `publish-media` keys. Revoke as in S2.

#### 7. `upload-repos-to-r2.sh` (only if step S4's EU bucket can be created)
- **What it touches for real:** `aws s3 sync dist/repos/<dir>` into `s3://rediacc-releases/<dir>/<CH>/`; sed-rewrites and uploads `cli/<CH>/install.{sh,ps1}`; calls `cf-purge-urls.sh` (`:105-163`).
- **Substitute:**
  - The EU bucket from item 5.
  - Scratch root `$S/root` containing `.ci/`, plus fixtures `dist/repos/{apt,rpm,apk,archlinux}/…`. Include `rpm/rediacc.repo` and `archlinux/rediacc.conf`, both containing `/w7p5a-<N>/`, so item 5's sed fix has something to fix. Add `dist/pages/install.sh` containing `REDIACC_CHANNEL:-stable` and `install.ps1` containing `} else { "stable" }`.
  - The script `cd`s to the scratch root (`:105`).
- **Commands** (same environment as item 5, using the `CLOUDFLARE_R2_*` names):
  - bash: `CHANNEL=w7p5a-<N> $S/root/.ci/scripts/deploy/upload-repos-to-r2.sh`
  - Snapshot, then wipe with `aws s3 rm s3://rediacc-releases --recursive --endpoint-url <EU>` (behind the `.eu.` guard).
  - Python: `PYTHONPATH=$S/root/.ci python3 -m rediacc_ci.deploy.upload_repos_to_r2`
  - Extra cases on both sides: an empty `dist/repos/apk` must print `VACUOUS … refusing` and exit 1. `CHANNEL=edge SKIP_RELEASE=1` must print `RELEASE SKIPPED … NOTHING WAS WRITTEN` and exit 0.
- **Observation:** both exit 0 with `Repos uploaded to R2 channel: w7p5a-<N>`. The key/size/CacheControl listings are identical. `cli/w7p5a-<N>/install.sh` contains `REDIACC_CHANNEL:-w7p5a-<N>`. The purge-skip warning is identical.
  - **Clears with:** L, pair `w7p5a-upload-repos-to-r2` (`.ci/shadow/w7p5a-status.json:210`, `blocklist:95`, EXPECTED `:44`).
- **Rollback, credential and revoke:** the same as item 5. Keep the Python run's objects as item 5's seed.

#### 8. `upload-to-r2.sh` (safe)
- **What it touches for real:** for edge/stable, the write-once guard and then `cli/v<V>/`; `cli/<CH>/`; `latest.json`; the `versions.json` tracker; npm; and `cleanup_old_versions`, which deletes old versions (`:260-300`, `:380-462`).
- **Substitute:**
  - Scratch buckets a and b, each seeded with `cli/versions.json` holding 20 fake versions plus a `cli/v0.0.0-old/x` object, so the pruning and deletion path runs inside scratch (limit `R2_MAX_RELEASE_VERSIONS=20`, `.ci/config/constants.sh:213`).
  - Fixtures: `$S/cli/{rdc-linux-x64,manifest.json}` and `$S/npm/rediacc-cli-0.0.1-w7p5a.tgz`.
- **Commands:**
  - bash: `RELEASES_BUCKET=w7p5a-scratch-a-<N> NPM_DIR=$S/npm CLOUDFLARE_R2_*=… .ci/scripts/deploy/upload-to-r2.sh --version 0.0.1-w7p5a --channel edge --cli-dir $S/cli`
  - Python: the same with bucket `-b-`, via `python3 -m rediacc_ci.deploy.upload_to_r2 …`
  - Set `NPM_DIR` explicitly, or the repo's own `dist/npm` gets picked up (`:426`).
- **Observation:** both exit 0 with the same `Artifacts uploaded: N`. The two buckets have identical listings (key, size, CacheControl, ContentType), identical `versions.json`, and the oldest version deleted in both.
  - **Clears with:** L, pair `w7p6-upload-to-r2` (`.ci/shadow/w7p5a-status.json:220`, `blocklist:96`).
- **Rollback:** delete the buckets.
- **Credential:** "Bucket Item Write" on the two scratch buckets, 2h, revoked as in S2.

#### 9. `test-d1-migrations.sh` (safe only in the retargeted form)
- **What it touches for real:**
  - It reads `regions.json` (`:52-60`) and clones each listed database through `clone-d1.sh` (`:114`).
  - It creates and deletes `migration-test-*` databases (`:63-86`, `:104`).
  - It writes `workers/www/wrangler-migration-test.toml` (`:116-131`).
  - The Python port still calls the bash `clone-d1.sh` (`.ci/rediacc_ci/deploy/test_d1_migrations.py:116`).
- **Substitute:**
  - `$S/root` containing `.ci/`, `workers/www/` (without `node_modules`), `private/account/drizzle/`, and a `regions.json` of `{"regions":[{"id":"w7p5a","d1":{"name":"account-db-w7p5as<N>"},"edgeD1":{"name":"edge-account-db-w7p5as<N>"}}]}`. The prefixes are required by the prefix-stripping at `:90-98`.
  - Create and seed both source databases as in item 4.
  - Use `GITHUB_RUN_ID=w7p5a<N>b` for bash and `w7p5a<N>p` for Python.
  - **Guard:** the driver checks that `jq -r '.regions[]|.d1.name,.edgeD1.name'` returns only `*w7p5as<N>` names.
- **Commands:**
  - bash: `CLOUDFLARE_API_TOKEN=$T CLOUDFLARE_ACCOUNT_ID=<acct> $S/root/.ci/scripts/deploy/test-d1-migrations.sh`
  - Python: `PYTHONPATH=$S/root/.ci python3 -m rediacc_ci.deploy.test_d1_migrations`
- **Observation:** both exit 0 with `All 2 regional migration tests passed (1 edge + 1 stable)` and two `Deleted migration-test-…` lines. `wrangler d1 list` shows no leftover `*w7p5a<N>*` databases.
  - Also cite CI run `35571489498` / job `106268930742` (the Python port against production, 6/6, 2026-09-21). The bash CI job `101599755239` shows success but its log returns 410.
  - **Clears with:** L, pair `w7p6-test-d1-migrations` (`.ci/shadow/w7p5a-status.json:203`, `blocklist:92`).
- **Rollback:** the script's EXIT trap deletes the clones. The driver deletes the two source databases. As a last resort, the reaper step `cleanup_stale_d1 --max-age 60` (`.github/workflows/ct-tests.yml:180-181`) removes leftover `migration-test-*` databases.
- **Credential:** the same D1 Write token as item 4; mint it once for items 4 and 9. Revoke as in S2.

#### 10. `assert-artifact-version.sh` (read-only; clearing depends on timing)
- **What it touches for real:** `gh run download <id> --name cli-manifest` into the fixed directory `/tmp/cd-artifact-check` (`:48-58`).
- **No substitute.** A scratch GitHub repo that uploads a `cli-manifest` artifact through a retargeted `GITHUB_REPOSITORY` would work technically, but it creates GitHub state. Not recommended.
- **Path: personal run** with the operator's `gh auth token` (read-only). There is nothing to mint:
  - GitHub fine-grained tokens can't be created through the API.
  - A GitHub App installation token would need `GITHUB_APP_PRIVATE_KEY`, and no `consumers` profile exposes it. Adding one is a change to `secret-supply.json`, gated by `check:ci-secret-supply`.
- **Now (optional):** run both sides with `VERSION=1.3.12 CI_RUN_ID=34074211598 GITHUB_REPOSITORY=rediacc/console`, removing `/tmp/cd-artifact-check` between them. Both should print the same three `::error::cli-manifest artifact not found …` lines and exit 1. This does **not** clear the item; the blocker at `blocklist:104` names the success path.
- **To clear:** within 24h of the next push-triggered green Console CI run on main (for example, right after PR 590 merges through `/pr-merge`):
  - Get the run ID: `gh run list --branch main --event push --workflow "Console CI" -L1`.
  - Take `VERSION` from that run's manifest.
  - Run bash, then `rm -rf /tmp/cd-artifact-check`, then `python3 -m rediacc_ci.release.assert_artifact_version`.
  - Both must print `::notice::Artifact version vX matches promotion target vX` and exit 0.
  - **Clears with:** L as Template A, pair `w7p5a-assert-artifact-version` (`.ci/shadow/w7p5a-status.json:265`, EXPECTED `:47`).
- **Rollback:** none needed. **Credential:** none minted.

#### 11. `assert-edge-tag-exists.sh` (Python leg only)
- **What it touches for real:** `gh api` for the tag, `gh release view`, and `aws s3api head-object` on `cli/v1.3.12/.released` (`:103`, `:117`, `:136`).
- **Substitute:** none; it's read-only.
- **Commands:** personal `GH_TOKEN` plus a minted R2 read-only token.
  - Python: `python3 -m rediacc_ci.release.assert_edge_tag_exists --version 1.3.12`
  - Re-run the bash side in the same session so the diff is like-for-like.
- **Observation:** both report the tag, release and sentinel as OK and exit 0. **Ledger:** add the Python leg to the note at `.ci/shadow/w7p5a-status.json:275-280`; the gate counts stay the same. Also remove this path from EXPECTED (`:48`), which fixes the failing test from item 2 of "Read this first".
- **Rollback:** none.
- **Credential:** "Bucket Item Read" on `…_default_rediacc-releases`, 2h, revoked as in S2.

#### 12. `reprobe-r2-sentinel.sh` (Python leg only)
- **What it touches for real:** `rsv_sentinel_exists` does a `head-object` (`:42-50`).
- **Commands:**
  - Python: `VERSION=v1.3.12 python3 -m rediacc_ci.release.reprobe_r2_sentinel`
  - Negative case on both sides: `VERSION=v0.0.0-w7p5a-absent` must print `::error::…NOT present` and exit 1.
- **Observation:** both print `✓ cli/v1.3.12/.released present in R2` and exit 0.
- **Ledger:** extend the note at `.ci/shadow/w7p5a-status.json:330-335`, and fix `pair: null` / `ledger: null` to point at `w7p6-reprobe-r2-sentinel` (its ledger exists in `.ci/shadow/`).
- **Credential:** the same token as item 11; mint once for both.

### Run order and time

| Step | What | Time |
|---|---|---|
| 0 | Preflight (S1 check, devbox mount, bws check), save the two CI logs, fix the `EXPECTED_DRY_RUN_PATHS` failure and commit | 25 min |
| 1 | Items 12 and 11: Python legs, read-only, one R2 read token | 15 min |
| 2 | Item 6: read-only | 15 min |
| 3 | Item 10: optional refusal-case run | 5 min |
| 4 | Item 3, then item 8: scratch buckets, one write token scoped to buckets a and b | 35 min |
| 5 | EU bucket check. If it succeeds: item 7, then item 5 (7 seeds 5). If not, both go to the operator. | 40 min |
| 6 | Item 1: first contact with the production zone, so after all the R2 work | 10 min |
| 7 | Item 4, then item 9: one D1 token, name guard | 45 min |
| 8 | Teardown sweep. `GET /user/tokens` shows no `w7p5a-*`. No `w7p5a-scratch*` buckets, including a check with the EU jurisdiction header. `wrangler d1 list` shows no `w7p5a*`. | 15 min |
| 9 | L for each cleared item, one commit each, gate run after every commit | 30 min |

**Total: about 3h55m.** Item 10's success run (+10 min) waits for the post-merge window. Item 2 is not run.

### Verification

After each graduation, run `npm run check:ci-w7p5a-real-run-blockers` (`package.json:180`). It must exit 0.

- **Current output (checked 2026-09-24):** `✓ 28 BLOCKER-gated real-run exemption(s) in .w7p5a-real-run-blocklist, agreeing with .ci/shadow/w7p5a-status.json (28 'blocked', 20 ledgered) -- no third state; of the ledgered, 13 have their real-run leg confirmed and 7 are leg-blocked in .w7p5a-real-run-leg-blocklist`
- **Each cleared M-contained item** changes the line to `(28-k 'blocked', 20+k ledgered)` with `13+k` confirmed and still 7 leg-blocked. Items 11 and 12 don't change any count.
- **If all 8 safe M-contained items clear** (items 5 and 7 need the EU bucket): `✓ 20 … (20 'blocked', 28 ledgered) … 21 have their real-run leg confirmed and 7 are leg-blocked`.
- **Without the EU bucket (6 clear):** 22 / 26 / 19.
- **After item 10 clears later:** one step further, for example 19 / 29 / 22.

Also check, for each cleared item:
- `./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py` passes with 0 failures. It must fail before step 0's fix if the reading in "Read this first" item 2 is right.
- `npx tsx scripts/lib/shadow-gate.ts --pair <pair> --assert --k 5` prints `equivalence holds over N distinct trees`.
- The note contains `real run each done directly` **and** the words `DISPOSABLE SUBSTITUTE <resource>` (`agent/plans/PLAN-w7p5a-real-run-dispatch.md:54`).
- The revocation check from S2 returned `success:false` for every minted token.

#### Critical Files for Implementation
- /home/developer/console/.ci/shadow/w7p5a-status.json
- /home/developer/console/.ci/policy/.w7p5a-real-run-blocklist
- /home/developer/console/.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py
- /home/developer/console/.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py
- /home/developer/console/scripts/ops/lib/cf-auth.sh

## M-live run sheets (operator queue, 2026-09-24)

Nineteen paths, all operator-run: the eighteen of the M-live tier plus `purge-media-cache.sh`, moved here on 2026-09-24 because no substitute exists.
The Drafted commands section above still holds each path's full env list. This section adds, per path, the order to run the two sides in, what success prints, what to do when it goes wrong, and how the ledger closes.

**Common to every sheet.**
- Run inside the devbox. Credentials come from `env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile <profile> -- ...`; `publish-solutions` carries `CF_GLOBAL_API_KEY`/`CF_EMAIL`.
- Where a sheet says "minted token", mint it the way `.ci/cache/w7p5a-realrun/cfkit.py` does. Use the narrowest permission group, `expires_on` two hours ahead, and a trap that revokes it on EXIT. Then prove it is dead: `/user/tokens/verify` must return `success:false`.
- Bash first, then the Python port, `PYTHONPATH=.ci python3 -m rediacc_ci.<family>.<stem>` with the same arguments. Capture exit code, stdout and stderr per side, and diff them.
- Several paths are not idempotent. For those the sheet says what the second side meets.
- Closing a path: Template A note containing `real run each done directly`, `status: "ledger"` with the existing pair, and the path removed from `.w7p5a-real-run-blocklist` (with its BLOCKER comment when last in its group). If it is pinned in `EXPECTED_DRY_RUN_PATHS`, remove it there too. Then `npm run check:ci-w7p5a-real-run-blockers` must exit 0.
- Worker rollback, everywhere below: `npx wrangler deployments list --name <worker>` shows the previous version, and `npx wrangler rollback <version-id> --name <worker>` restores it.

### Cloudflare Workers and D1

**`deploy/deploy-account.sh`** (port `rediacc_ci.deploy.deploy_account`)
```
- Command: `CLOUDFLARE_API_TOKEN=<minted: Workers Scripts Write + D1 Write> CLOUDFLARE_ACCOUNT_ID=fa51e4a18d553c30e1633288e9733d04 .ci/scripts/deploy/deploy-account.sh --region eu --target edge`. Start with `--target edge`, and do production regions only after edge is clean.
```
- Expected: `Migrations applied to <db>` then `Account worker deployed: edge eu`, exit 0. The Python side redeploys the same bytes and applies zero migrations.
- Rollback: `wrangler rollback` on the regional worker. A migration that already ran is forward-only; restore D1 with Time Travel (`npx wrangler d1 time-travel restore <db> --timestamp <before-run>`).
- Preview: none; read `wrangler d1 migrations list <db> --remote` first to see what would apply.

**`deploy/deploy-edge.sh`** (port `rediacc_ci.deploy.deploy_edge`)
- Command: `CLOUDFLARE_API_TOKEN=<minted: Workers Scripts Write + Workers Routes Write> CLOUDFLARE_ACCOUNT_ID=<acct> .ci/scripts/deploy/deploy-edge.sh`.
- Expected: `Deploying edge worker (edge.rediacc.com)...`, `Edge worker deployed`, exit 0. Afterwards `VERSION=<v> .ci/scripts/deploy/verify-edge-endpoints.sh` passes.
- Rollback: `wrangler rollback` on the edge worker.

**`deploy/deploy-proxy.sh`** (port `rediacc_ci.deploy.deploy_proxy`)
- Preview: `--dry-run` first, on both sides; it prints `Dry run passed. Nothing was deployed.`
- Command: `CLOUDFLARE_API_TOKEN=<minted, scoped; never the global key> .ci/scripts/deploy/deploy-proxy.sh --region eu`.
- Expected: `Deployed. The executor still needs its own account token:` plus the `EXECUTOR_TOKEN` hint lines, exit 0.
- Rollback: `wrangler rollback` on the proxy worker. The container image rolls back with the worker version that references it.

**`deploy/deploy-www.sh`** (port `rediacc_ci.deploy.deploy_www`)
- Command: the preview form first, `--name pr-<N>` for an open PR. It deletes and recreates D1 `account-db-pr-<N>` (`Created D1 database ...`, `Migrations applied to account-db-pr-<N>`). Production form without `--name` only in a low-traffic window.
- Expected: `Deploying www production worker...` and wrangler's deploy summary, exit 0. The script prints no closing line of its own, so the exit code and the wrangler summary are the evidence.
- Rollback: `wrangler rollback` on the www worker. The preview D1 is disposable by design.

**`deploy/set-account-worker-secrets.sh`** (port `rediacc_ci.deploy.set_account_worker_secrets`)
- Command: the full env from the Drafted section, sourced from BWS. Start with `TARGET=edge`, one `SUFFIX`.
- Expected: exit 0 from `wrangler secret bulk`, whose summary lists the keys. The script prints no success line of its own. The refusals (`... is EMPTY for WORKER_NAME=...`, the OBS_OTLP_CREDENTIALS shape check) must not fire.
- Rollback: re-run with the previous values; BWS holds the source of truth and the Worker holds a copy. A single bad key: `npx wrangler secret put <KEY> --name <worker>`.
- Redaction: capture only the exit code and the key NAMES; never keep the stdin JSON.

**`deploy/set-preview-worker-secrets.sh`** (port `rediacc_ci.deploy.set_preview_worker_secrets`)
- Command: `PR_NUMBER=<N>` plus the env from the Drafted section, against an existing `pr-<N>` preview worker.
- Expected: `Set 15 secrets on pr-<N> in one bulk call`, exit 0, on both sides.
- Rollback: delete the preview worker (`npx wrangler delete --name pr-<N>`), which is disposable, or re-run with the right values.

**`deploy/set-www-worker-secrets.sh`** (port `rediacc_ci.deploy.set_www_worker_secrets`)
- Command: `WORKER_NAME=<edge www worker first>` plus the env from the Drafted section.
- Expected: exit 0 from `wrangler secret bulk`, with no `is EMPTY` refusal.
- Rollback and redaction: as for set-account-worker-secrets.

### R2 and the Cloudflare cache

**`deploy/purge-media-cache.sh`** (port `rediacc_ci.deploy.purge_media_cache`), moved here from M-contained on 2026-09-24
- Why here: the zone and the hostname are literals (`.ci/scripts/deploy/purge-media-cache.sh:25-26`; `.ci/rediacc_ci/deploy/purge_media_cache.py:46-47` keeps them literal on purpose). Success purges the whole live `media.rediacc.com` host, and a token cannot be narrowed to a hostname.
```
- Command: `CLOUDFLARE_API_TOKEN=<minted: Zone Cache Purge on 9e802649c143c9cefd811d8fd671d31c> .ci/scripts/deploy/purge-media-cache.sh`, then `python3 -m rediacc_ci.deploy.purge_media_cache`.
```
- Expected: `Purging Cloudflare cache for media.rediacc.com...`, `Purge complete. Cache repopulates on next request (cf-cache-status: MISS then HIT).`, exit 0 on both.
- Rollback: none. A purge cannot be undone; the cache refills from R2 on demand, and objects carry a one-year max-age, so expect an origin burst. Run it in a low-traffic window.
- Optional safe preview: a Zone-Read-only token makes both sides exit 1 with `Purge failed: [{"code":10000,...}]`. That is Template C evidence only.
- Clears with: pair `w7p5a-purge-media-cache`; also remove it from `EXPECTED_DRY_RUN_PATHS`.

**`deploy/promote-r2-to-stable-hotfix.sh`** (port `rediacc_ci.deploy.promote_r2_to_stable_hotfix`)
- Command: `CLOUDFLARE_R2_*=<minted: Item Write on rediacc-releases> CLOUDFLARE_R2_ENDPOINT=<default endpoint> CLOUDFLARE_ZONE_ID=<zone> CLOUDFLARE_API_TOKEN=<minted Cache Purge> .ci/scripts/deploy/promote-r2-to-stable-hotfix.sh`. Only run it when a hotfix promotion is actually due.
- Expected: `R2 promoted to stable`, exit 0. The second side re-copies the same edge bytes over stable.
- Rollback: re-promote the previous stable version, which is still under `cli/v<prev>/` (immutable), by re-running `promote-r2-to-stable.sh` with the prior `EDGE_VERSION`. Snapshot `stable/` with `aws s3 ls --recursive` before running.

**`deploy/promote-r2-to-stable.sh`** (port `rediacc_ci.deploy.promote_r2_to_stable`)
- Command: `AWS_*=<minted: Item Write on rediacc-releases> AWS_DEFAULT_REGION=auto CLOUDFLARE_R2_ENDPOINT=<default endpoint> EDGE_VERSION=<v> .ci/scripts/deploy/promote-r2-to-stable.sh`. Run it as the real 7-day-soak promotion, not an extra one.
- Expected: `R2 promotion complete: edge v<v> -> stable`, exit 0. The second side is a no-op sync of identical bytes.
- Rollback: as for the hotfix variant.

**`deploy/delete-r2-channel.sh`** (port `rediacc_ci.deploy.delete_r2_channel`)
- Command: `CHANNEL=pr-<closed PR> RELEASES_BUCKET=rediacc-releases CLOUDFLARE_R2_ENDPOINT=<default endpoint> AWS_*=<minted Item Write> .ci/scripts/deploy/delete-r2-channel.sh`. Use a channel whose PR is closed, which is garbage anyway.
- Expected: `Channel 'pr-<N>' (+ promoted) deleted from R2`, exit 0. The second side, on a second closed PR's channel, prints the same line.
- Rollback: none. Deletions are best-effort `|| true` and irreversible; the channel is rebuilt only by re-running that PR's CI.
- NEVER `edge` or `stable`.

**`deploy/sync-media-to-r2.sh`** (port `rediacc_ci.deploy.sync_media_to_r2`)
- Preview: `--dry-run --audio-only` first, on both sides; the planned upload lists must match.
- Command: `CLOUDFLARE_R2_MEDIA_*=<minted: Item Write on rediacc-www-media> .ci/scripts/deploy/sync-media-to-r2.sh --audio-only`, from a tree whose audio came from `sync-media-from-r2.sh`, so the sync uploads nothing new. Never `--delete`.
- Expected: `Sync complete. Verify with:` plus the two verification hints, exit 0.
- Rollback: re-upload any overwritten object from the local copy restored by `sync-media-from-r2.sh`. Media keys are content-hashed, so an overwrite with the same key carries the same bytes.

### Docker and GitHub

**`deploy/promote-docker-to-stable-hotfix.sh`** (port `rediacc_ci.deploy.promote_docker_to_stable_hotfix`)
- Command: `docker login ghcr.io` first, then `.ci/scripts/deploy/promote-docker-to-stable-hotfix.sh`. Only run it when a hotfix promotion is due.
- Expected: `Promoting <image>: edge -> stable` per image, `Docker promoted to stable`, exit 0. The second side re-points `:stable` at the same digest.
- Rollback: note the digests first (`docker buildx imagetools inspect ghcr.io/rediacc/<image>:stable`), then `docker buildx imagetools create -t ghcr.io/rediacc/<image>:stable ghcr.io/rediacc/<image>@<old digest>`.

**`release/create-github-release.sh`** (port `rediacc_ci.release.create_github_release`)
- Command: `VERSION=<v> GITHUB_SHA=<sha> GITHUB_REPOSITORY=rediacc/console GH_TOKEN=<gh auth token> .ci/scripts/release/create-github-release.sh`, with `dist/cli` and `dist/packages` populated from that version's CI artifacts.
- Expected: exit 0 and `gh release create`'s release URL. The script prints no closing line. Not idempotent: the second side meets an existing release and must fail the same way. Alternatively, split the two sides across two consecutive real releases.
- Rollback: `gh release delete v<v> --yes` (the tag stays).

**`release/mark-production.sh`** (port `rediacc_ci.release.mark_production`)
- Command: `GH_TOKEN=<gh auth token> .ci/scripts/release/mark-production.sh <v>`, for the version production actually serves.
- Expected: `mark-production: moved the 'production' tag to <v> (<sha>)`, `mark-production: marked <v> as the latest GitHub Release`, exit 0. The second side re-points to the same sha.
- Rollback: note the old sha first (`gh api repos/rediacc/console/git/refs/tags/production`). Then `gh api --method PATCH repos/rediacc/console/git/refs/tags/production -f sha=<old> -F force=true` and `gh release edit v<old> --latest`.

**`release/cleanup-channel-docker-tags.sh`** (port `rediacc_ci.release.cleanup_channel_docker_tags`)
- Command: `CHANNEL=edge GITHUB_STEP_SUMMARY=$S/summary-<side>.md GH_TOKEN=<gh auth token> .ci/scripts/release/cleanup-channel-docker-tags.sh`.
- Expected: exit 0. The summary file reads `**Channel tag NOT cleaned up:** edge`, because the staging-only guard refuses channel tags by design.
- Rollback: none needed. The guard makes a real channel-tag deletion impossible.

**`release/tag-submodules.sh`** (port `rediacc_ci.release.tag_submodules`)
- Command: `VERSION=<v> GITHUB_PAT=<gh auth token> .ci/scripts/release/tag-submodules.sh`, for a version whose renet commit is the submodule HEAD.
- Expected: exit 0 with the tag pushed. The second side prints `::notice::Submodule private/renet tag v<v> already at HEAD (<sha>); reusing`.
- Rollback: `git -C private/renet push origin :refs/tags/v<v>` and `git -C private/renet tag -d v<v>`.

**`release/update-homebrew-tap.sh`** (port `rediacc_ci.release.update_homebrew_tap`)
- Preview: `--version <v> --dry-run`, then `--stage-only`.
- Command: `GITHUB_PAT=<gh auth token> .ci/scripts/release/update-homebrew-tap.sh --version <v> --push`, for the version just released.
- Expected: `Homebrew tap update complete`, exit 0. The second side prints `Formula already at version <v>`.
- Rollback: `git -C <tap checkout> revert HEAD && git push`, then revert the submodule pointer commit on main the same way.
- It pushes to a public repository and to main, so run it only as part of a real release.

**`release/advance-contract-floor.sh`** (port `rediacc_ci.release.advance_contract_floor`)
- Command: `CLOUDFLARE_R2_*=<minted: Item Read on rediacc-releases> GIT_BOT_NAME=<n> GIT_BOT_EMAIL=<e> .ci/scripts/release/advance-contract-floor.sh`, from a clean checkout of main.
- Expected: either a no-op, `ratchet already at <cur> >= observed <oldest>` with exit 0 and nothing pushed, or a commit `chore(release-state): advance contract floor to <oldest> [skip ci]` pushed to main. The second side meets the advanced floor and prints the no-op line.
- Rollback: `git revert <commit> && git push origin main`.
- It is the one sheet that pushes to main. Run the no-op form first; it is the likely one, and it proves the R2 read without a push.

### M-live progress (2026-09-24, session d778be9d)

The coordinator relayed the operator's 2026-09-24 authorization for the M-live tier. The session ran only the runs whose pre-state check proved they change nothing in production, each with its rollback written down before the run.
Each of the other fifteen changes live state: Worker deploys, secret stores, a public GitHub Release, pushes to main and to the public tap, R2 deletions and promotions, a full media-cache purge. They wait for the operator's own go in this session, because an authorization relayed through another agent is not taken as consent for irreversible production changes.

| Path | Outcome | Pre-state proof / rollback |
|---|---|---|
| `release/advance-contract-floor.sh` | graduated, pair `w7p6-advance-contract-floor` | floor v1.2.21 = oldest R2 sentinel v1.2.21, so no commit and no push; both sides print the identical `ratchet already at v1.2.21` |
| `release/mark-production.sh` | graduated, pair `w7p5a-mark-production` | `production` already at 880b1b3e (v1.3.12), v1.3.12 already Latest; rollback PATCH written before the run |
| `release/cleanup-channel-docker-tags.sh` | graduated, pair `w7p6-cleanup-channel-docker-tags` | staging-only guard, no registry call; identical summaries |
| `deploy/promote-docker-to-stable-hotfix.sh` | graduated, pair `w7p5a-promote-docker-to-stable-hotfix` | `:stable` = `:edge` digests for renet/rdc/server before and after; digests saved in `out/L-docker-rollback-digests.txt` |
| `release/tag-submodules.sh` | not run | `private/renet` HEAD is `v1.3.12-16-g86719a5` while `v1.3.12` exists remotely at another commit, so the script's drift refusal fires (exit 1); it clears only with the next real release |
| `release/update-homebrew-tap.sh` | not run | see finding 5; the formula already reads 1.3.12, so the next real release is the natural run |
| the other thirteen | operator go needed | sheets above |

Gate after the fourth graduation: `16 'blocked', 32 ledgered ... 25 have their real-run leg confirmed and 7 are leg-blocked`, rc=0 after each step. The ledger module then reported 32 passed. Token `w7p5a-live-r2read-1`: DELETE success, verify `success:false` (code 1000).

**Update, later on 2026-09-24.** The lead then relayed the operator's authorization as the operator's own words and directed all fifteen runs.
- `deploy/purge-media-cache.sh` ran and graduated (pair `w7p5a-purge-media-cache`). Its worst case is cache misses, which recover by themselves: both sides exited 0 with identical output, the media host still serves 200, and the token was revoked and verified dead. Gate afterwards: 15 blocked, 33 ledgered, 26 confirmed.
- A v1.3.12 build now sits at `.ci/cache/w7p5a-realrun/v1312`. It was materialized with a private index (the shared tree was never checked out), `private/account` is at the v1.3.12 gitlink 65820fd7, and it was built the way cd-deploy-worker.yml and cd-deploy-account.yml build (log in `out/build_v1312.log`, BUILD-OK). The deploy sheets can therefore redeploy exactly what production runs, not this branch's uncommitted tree. CI builds with `vars.TURNSTILE_SITE_KEY`, which is not defined at repo, environment or org level, so the portal is built with an empty site key there too. The scratch build copies that.
- The R2 promotion driver (`drive_r2live.py`) was stopped by the session itself during its read-only snapshot of every `<dir>/stable/` prefix, before any write. Both of its tokens were revoked and verified dead.
- The session holds the remaining fourteen until the operator gives the go in their own session. Those are the four deploys, the three secret scripts, create-github-release, both R2 promotions, sync-media-to-r2, delete-r2-channel, tag-submodules and update-homebrew-tap. The last two are next-release items in any case. The harness treats an authorization quoted by another agent as not being the operator's consent, and these runs change live production state. The drivers and the v1.3.12 build are ready, so each one is a single command once the operator confirms.

Findings from this tier:

4. **The devbox docker has no buildx plugin.** `docker buildx imagetools inspect ...` inside the devbox prints only `Run 'docker --help' for more information`. promote-docker-to-stable-hotfix.sh therefore ran on the host.
5. **update-homebrew-tap.sh writes the PAT into the global git config** (`.ci/scripts/release/update-homebrew-tap.sh:78`, port `.ci/rediacc_ci/release/update_homebrew_tap.py:567-568`, sibling `.ci/scripts/ci/initialize.sh:104`). That is harmless on an ephemeral CI runner. On a workstation, and inside the devbox, whose `~/.gitconfig` is bind-mounted from the host, it persists `x-access-token:<PAT>` in plain text. The script also runs `git checkout -B main <origin> --force` in `private/homebrew-tap` (`:87`), which discards uncommitted work in a shared tree. Both are outside this writer's file set.
