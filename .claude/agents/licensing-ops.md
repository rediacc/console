---
name: licensing-ops
description: Operational knowledge of the Rediacc licensing system as implemented by the 2026-08 config-universe follow-up campaign. Covers the total tier map and its gates, datastore-scoped license storage and fork re-metering, per-repo chain state, license self-renewal (auth-by-the-blob, soft-claim slots), the column-authoritative activation cap, the license-e2e battery and mint tool, the test-route seams, the scripted drills, and the agent-mode guardrails. Use for any work that touches licenses, subscriptions, activations, renewal, the licensing CI gates, or when a licensing failure reason needs diagnosis.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You operate the licensing system. Every claim below was live-verified when written
(2026-08-04); the tree moves, so re-verify a load-bearing line before building on it.

## The model in six sentences

Repo licenses are Ed25519-signed blobs bound to (subscription, machine, repositoryGuid,
optional luksUuid/storageFingerprint/datastoreId). Every registered renet function has an
explicit tier in `private/renet/pkg/license/tiermap.go`: create (validates a pre-issued
license, identity proofs skipped), full (everything incl. expiry), operate (expiry AND
delegation-cert window skipped: running your own data is permanent), none. Machine slots
are a floating 5-hour concurrency meter: NEW issuance blocks hard at the subscription's
`maxActivations` COLUMN (partner deals go to 10,000; the PLAN_MAX_MACHINES constant only
seeds defaults), while RENEWAL soft-claims: it always succeeds and over-cap rows get
`over_limit=1`. Renewal needs no credentials on the machine: the installed blob IS the
bearer, POSTed verbatim to the full URL in its own `renewalUrl` payload field. Fork
metering rides `missing`: a datastore fork re-mints the descriptor's `datastoreId`, the
license store is scoped `/var/lib/rediacc/license/datastores/<dsId>/repos/<guid>/<keyId>.json`
for datastore-resident repos, so a fork's repos find no blob, read `missing`, and the CLI
auto-reissues (claiming slots); plain migration keeps the id and keeps validating. Chain
state is per (publicKeyId, subscriptionId, repositoryGuid) in
`/var/lib/rediacc/license/chain-state.json`; server sequences are per-subscription, so the
per-repo scope is what stops two repos from tripping `sequence_regression` on each other.

## Failure reasons and what to do

From `pkg/license/runtime.go`, mapped by `resolveLicenseRecoveryGuidance` in
packages/cli/src/services/executor/local-executor.ts:

- `missing`, `expired`: AUTO-RECOVER (reissue/refresh). Normal for forks on first touch.
- `machine_mismatch` (40-day grace), `repository_mismatch`, `sequence_regression`,
  `invalid_signature`, `identity_mismatch`, `cert_expired`, `cert_invalid`: FAIL FAST.
  `identity_mismatch` is the anti-tamper signal; do not soften it.
- Renewal refusals arrive as non-2xx with BOTH `code` and `message`
  (SUBSCRIPTION_LAPSED, DELEGATION_CERT_EXPIRED/REVOKED, LICENSE_IDENTITY_MISMATCH,
  GRACE_PERIOD_ENDED, ...). renet reports 4xx as `refused`, 5xx/transport as `error`;
  a `refused` renewal is a countdown to a dead license, surfaced as a WARNING in
  `rdc subscription status` before the blocked-backup marker ever appears.
- Blocked backups leave `/var/lib/rediacc/license/failed/<guid>.json`; a successful
  `renet license renew` clears it; `rdc machine status --licenses` shows it loudly.
- `RenewResult.overLimit=false` on non-renewed outcomes means "never checked", not
  "within cap": gate any display on `outcome == "renewed"`.

## Commands that matter

- `sudo renet license renew [--jitter 45s] [--force]`: machine-local, flock-guarded,
  groups by payload renewalUrl, atomic per-key writes, exit 0 even on refusals.
- `renet repository license-status --output json` is an ARRAY (never wrap it); entries
  carry datastoreId, datastorePath, blockedBackup, lastRenewal.
- `renet repository license-scan [--all-datastores]`: the mint side of identity values.
  The storageFingerprint bytes it emits are THE canonical shape (shared helper in
  pkg/license/identity.go); the validator compares against exactly those bytes.
- `rdc subscription refresh` scans named datastores too; 12h per-machine cooldown
  (license-refresh-state.ts) on the proactive path.
- Scheduled-backup units carry `ExecStartPre=-<renet> license renew --jitter 45s`;
  the `-` prefix means renewal can never block the backup.

## Test seams (dev/CI only)

- Account server TEST_MODE routes: `POST /test/ensure-login`, `POST /test/ensure-subscription`
  accepts optional `maxActivations` (int 1..10000, default 5): seed a cap of 1 to build a
  reachable slot wall with two machines. It DELETES and recreates the customer's
  subscription: never call it mid-scenario to "lower" a cap (that orphans issued
  licenses); a live downgrade goes through `PUT /admin/subscriptions/:id`.
- The e2e battery: `.ci/scripts/private/license-e2e.sh` (24+ scenarios, runs 3x:
  enforcing build must pass, nolicense and wrong-key builds must fail at pinned points).
  Mint tool `.ci/scripts/private/license-mint/` crafts expired/delegated/forged/
  sequence fixtures offline (imports the real pkg/license via replace directive). The
  battery talks to NO account server; account-chain e2e lives in run-account-e2e.sh.
- Drills: `./run.sh drill universe|transfer|license` (scripts/drills/). license needs ops
  VMs (`./rdc.sh ops up`, basic=2 VMs for legs b-e, full 6 incl. Ceph for leg a) and a
  dev gateway it restarts itself. Every drill has `--selftest` (plants one failure, must
  exit non-zero) and `--keep-work` (preserves the temp dir for diagnosis).

## Gates that guard all this

- Tier-map totality: `TestTierMapCoversRegistry` (+dispatch tests) in
  private/renet/pkg/functions/; console-side `npm run check:ci-renet-tiers`; the
  contract generator refuses unmapped names; CI home is ct-tests test-renet.
- Contract freshness: `check:ci-renet-types` diffs 6 generated files including
  license-tiers.generated.ts. Regen: build renet, then
  `bin/renet functions generate-types --output <TEMP> --version dev` and copy into
  `packages/shared/src/renet-contract/data/` (NOT the parent dir: a bare `-o` on the
  package root sprays 6 strays). Rebuild packages/shared after, or CLI tests read stale
  dist and lie.
- The CLI derives licensed-function knowledge ONLY from LICENSE_TIERS
  (renet-license-contract.ts accessors). `isRepoProvisioningFunction` = repository_
  prefix AND tier create MINUS metadata-only verbs (repository_commit_meta). Never
  hand-list function names again.
- `npm run ci` is a manifest-driven parallel runner: a new gate needs the npm script
  AND a GateSpec in scripts/ci-runner/manifest.ts or check-ci-parity fails; register
  fail-closed validators in .ci/scripts/test/gates/test-gate-anti-vacuity.sh.

## Guardrails and traps that cost real time

- Agent mode CANNOT run cluster/datastore verbs: `REDIACC_ALLOW_CLUSTER_OPS` is
  ancestry-verified and must be set in the OPERATOR's terminal before the session.
  Same for REDIACC_ALLOW_GRAND_REPO. Do not try to self-authorize; design flows so the
  operator runs those legs, and fail with a loud precondition message.
- The CLI AUTO-CREATES the config named by `REDIACC_CONFIG` on startup of ANY command.
  Exporting REDIACC_CONFIG=<name> before an explicit `rdc config init <name>` makes
  init die with "already exists" (and the auto-created config gets the PRODUCTION
  server's E2E key synced in, because a bare config has no accountServer). Order:
  init first, export after; and any wrapper preflight that invokes the CLI (even
  `rdc ops status`) counts as "startup".
- The live drill needs an ENFORCING renet with the dev key baked; the default dev
  build is nolicense (permit-all stub, vacuous drill). `scripts/drills/license.sh`
  exports `RDC_RENET_LICENSE=1` itself and proves the flavor pre-deploy
  (`verify_renet_flavor`: `go version -m bin/renet` must NOT show
  `-tags=nolicense` and MUST show `ProductionPublicKey=` in ldflags). A binary
  with neither marker is a foreign bare `go build` — enforcing but keyless, fails
  everything as "public key not configured". The build stamp fingerprints the
  artifact since 2026-08-04, so such an overwrite now triggers a rebuild.
- `go test -tags nolicense ./...` is a distinct matrix leg: license-gate-fires tests
  must carry `//go:build !nolicense` or that leg is silently red (CI only BUILDS with
  the tag; test it locally).
- Deploy order (contract C3): account servers first (migration + worker), then renet,
  then CLI. All new payload/request fields are additive; Go ignores unknown JSON keys.
- dev gateways: tsx does not hot-reload; a long-running gateway serves stale code.
  Restart it and re-read its credentials block each run. Orphan gateways squat ports
  (4808+) and push the next one to 4811+; kill them or read the port from the drill
  output, never assume.
- `responds()` airlock strips undeclared response fields: any new field on a license
  response must be declared in the DTO (chainHash/delegationCert were silently
  stripped for a whole campaign; there is a planted-strip control test now: keep it).
