# PLAN: W7P5-a real-run dispatch — execute the 32-path authorization safely

Status: ready -- the design (categorization, tiers, sequencing) is complete and unchanged since landing; every remaining box is door:operator-only (per-path sign-off, several requiring the operator physically at the keyboard), so no further session-side work advances it without an operator action.
Owner: d778be9d
Updated: 2026-09-23

## The ask

The operator answered "Authorize the full 32" to an /ask round, overriding this session's own more conservative "read-only verifiers only" recommendation, for the 32 production-touching deploy/release paths registered in `.ci/policy/.w7p5a-real-run-blocklist` (cross-checked by `check:ci-w7p5a-real-run-blockers` against `.ci/shadow/w7p5a-status.json`'s 32 `"blocked"` / 16 `"ledger"` split).
This plan turns that authorization into a concrete, safety-first execution sequence — it does not itself run anything.

## What the repo already encodes (read before dispatching anything)

Every one of the 32 `"blocked"` rows in `.ci/shadow/w7p5a-status.json` carries, verbatim, in its own `note` field:

> "That clause needs a run against real production Cloudflare, GitHub, R2 or
> D1 and is an OPERATOR-AUTHORIZATION matter: a session must not attempt it."

This is machine-tracked, not this session's editorializing (confirmed: all 32/32 rows carry the exact sentence).
`.w7p5a-real-run-blocklist`'s own header says rewording that language is "a driver action against that allowlist, not an edit this file may make on its own." `PLAN-w7p5a-deploy-release-port.md` (compacted 2026-09-20, same owner prefix) closed with box 8: "Leave all 32 fully-`blocked` paths untouched... require explicit operator authorization before real runs are safe" — today's authorization is the event that plan anticipated, but it authorizes the *operator* to proceed, not an agent session to self-dispatch.
Blast-radius tiering below governs how much operator involvement each path needs, not whether any is needed — none of the 32 gets unattended agent execution against real production.

The shape a passing entry must end in (matching the 16 already done): either the `note` gains the literal substring `"real run each done directly"` with prose describing what ran and against what (the 9-path pattern), or the path moves into `.w7p5a-real-run-leg-blocklist` with its own BLOCKER naming the unreachable system (the 7-path pattern).
Either way the entry is removed from `.w7p5a-real-run-blocklist` in the same change, or `check:ci-w7p5a-real-run-blockers` reds on the drift.

## Categorized findings (blast radius, 32/32 accounted for)

| Tier | Category | Count | Paths |
|---|---|---|---|
| R | Read-only, zero credentials, zero mutation possible | 2 | `verify-edge-endpoints.sh`, `verify-stable-endpoints.sh` |
| Q | Read-only in effect, needs creds this sandbox lacks | 3 | `assert-artifact-version.sh`, `assert-edge-tag-exists.sh`, `reprobe-r2-sentinel.sh` |
| M-contained | Mutating, disposable/staging substitute exists | 9 | `cf-purge-urls.sh`, `purge-media-cache.sh`, `write-release-sentinel.sh`, `clone-d1.sh`, `simulate-promotion.sh`, `sync-media-from-r2.sh`, `upload-repos-to-r2.sh`, `upload-to-r2.sh`, `test-d1-migrations.sh` |
| M-live | Mutating, no safe non-prod target, irreversible/public-facing | 18 | `deploy-account.sh`, `deploy-edge.sh`, `deploy-proxy.sh`, `deploy-www.sh`, `promote-docker-to-stable-hotfix.sh`, `promote-r2-to-stable-hotfix.sh`, `promote-r2-to-stable.sh`, `set-account-worker-secrets.sh`, `set-preview-worker-secrets.sh`, `set-www-worker-secrets.sh`, `delete-r2-channel.sh`, `sync-media-to-r2.sh`, `advance-contract-floor.sh`, `update-homebrew-tap.sh`, `mark-production.sh`, `create-github-release.sh`, `cleanup-channel-docker-tags.sh`, `tag-submodules.sh` |

## Implementation (mechanism per tier)

1. **Tier R (2 paths).** No secrets, no mutation. A writer may draft the exact command and a template ledger note. Execution still needs one fresh, item-level operator "go" (a glance, not a review) — the "session must not attempt it" sentence in status.json belongs to the operator to retire, not to this session to route around by blast-radius reasoning.
2. **Tier Q (3 paths).** Two options, operator's choice: (a) operator runs the command personally in their own authenticated shell and hands the writer the transcript to fold into the ledger note;
or (b) operator mints a narrowly-scoped, time-boxed, read-only credential (`actions:read`, `s3:HeadObject` on one prefix, etc.) into an ephemeral sandbox, watches the single run, then revokes it immediately.
No standing credential is ever left in an agent-writable environment.
3. **Tier M-contained (9 paths).** Retarget the real run at a disposable analog instead of the production resource: a scratch R2 bucket/prefix the operator provisions and deletes afterward, a forked/cloned D1 instance instead of production D1, a clearly-scoped sentinel key.
This proves the Python port's behavior against a real instance of the same external API family without touching production.
Whether that satisfies the box's literal "real production" bar is the operator's call per path — the ledger note must say plainly that a substitute target was used, never word it as if the real endpoint was hit.
4. **Tier M-live (18 paths).** No agent-executed path, staged or otherwise.
The operator runs the command personally, at a time of their choosing (low-traffic window where relevant), with a rollback step identified before running, watching output live.
A writer's role is limited to drafting the exact command/flags for the operator to review or copy, and transcribing the result into the ledger note afterward.
`advance-contract-floor.sh` pushes directly to `origin/main`; `tag-submodules.sh` and `update-homebrew-tap.sh` push to shared/public remotes that may trigger downstream CD; the three `set-*-worker-secrets.sh` scripts risk a live secret leaking into any transcript/log — redact before the writer ever sees output from these.

## Sequencing

**A writer may do, unattended, right now, for all 32:** draft the exact real-run command line, required env/flags (redacted), and a ledger-note template matching the proven shape (containing the literal phrase the gate checks, or the leg-blocklist BLOCKER shape) — with the actual-output field left blank for the operator to fill in.
For the 9 M-contained paths, also draft the disposable-resource provisioning request as a checklist item for the operator (bucket/D1-fork name, expiry, why it's a safe stand-in). Re-running `check:ci-w7p5a-real-run-blockers` to confirm it stays green throughout is likewise safe and unattended.

**Needs per-path operator sign-off on the exact command before it runs — all 32, no exceptions**, because the "a session must not attempt it" sentence is uniform across all 32 rows regardless of tier.
What varies is weight: Tier R sign-off can be a one-line "go"; Tier Q sign-off includes review of credential scope and revocation; Tier M-contained sign-off includes confirming the substitute target is genuinely disposable and non-production; Tier M-live sign-off means the operator is the one at the keyboard, full stop.

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
- [ ] Tier Q (3): operator chooses personal-run vs scoped-credential path per item; execute; revoke any minted credential immediately; record ledger note.
- [ ] Tier M-contained (9): operator provisions each disposable substitute; writer drafts the retargeted command against it; operator approves; run; record ledger note naming the substitute explicitly.
- [ ] Tier M-live (18): operator personally executes each, at a time of their choosing, with a rollback step identified beforehand; writer transcribes redacted output into the ledger note afterward.
- [ ] Re-run `check:ci-w7p5a-real-run-blockers` after every graduation; confirm rc=0 and the blocked/ledgered counts move as expected.
- [ ] Full re-run of `.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py` after all graduations to confirm no dry-run note accidentally claims a real run.

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
