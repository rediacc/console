# PLAN: rdc backup download --store rebuilds a repo's encrypted image on a local path straight from the R2 chunk store, with no machine, updating by chunk hash

Status: approved -- operator 2026-10-29 "Go: implement PLAN-backup-download-from-store" after the feasibility study (worklist #b76e7dcb)
Depends-On: PLAN-backup-local-image.md, PLAN-backup-plane-shared-bucket-hardening.md
Owner: d778be9d
Priority: P2 -- downloads a lineage while its machine is down or deleted, puts no load on the machine and reaches any snapshot in history; it does not cover the loss of the bucket itself, which the machine-path download of PLAN-backup-local-image covers
Owns: agent/plans/PLAN-backup-download-from-store.md, private/account/src/routes/backups.ts (the restore-session route only), private/account/src/services/backup-storage.service.ts (the token-minted restore session only), private/account/src/types/api-token-scopes.ts, private/account/src/services/device-code.service.ts (scope policy only), private/account/drizzle/*_backup_session_token.sql (new), private/account/tests/integration/backup-restore-session.test.ts (new), private/account (gitlink bump only), private/renet/cmd/renet/backup_fetch_image.go (new), private/renet/cmd/renet/backup_fetch_image_test.go (new), private/renet/pkg/chunkstore/punch_darwin.go (new), private/renet/pkg/chunkstore/punch_windows.go (new), private/renet (gitlink bump only), packages/cli/src/commands/backup-image.ts (the --store branch only), packages/cli/src/services/backup-image/store-fetch.ts (new), packages/cli/src/commands/__tests__/backup-image-store.test.ts (new), packages/cli/src/i18n/locales/*/cli.json, .github/workflows/ci-build-renet.yml (one native darwin and windows test job), packages/shared/src/cli-contract/data/** (regenerated only), packages/www/src/content/docs/*/backup-download.md
Concurrency: parallel -- account (A1, A2), renet (R1, R2) and CLI (C1) have disjoint files; C1 codes against the A1 wire shape and the R1 subcommand
Live-Proof: bench, hostinger -- bench proves the token-minted restore session and its refusals; hostinger proves one real lineage fetched to a local path twice, full then incremental
Updated: 2026-10-29
First-Seen: 2026-10-29
Worklist: #b76e7dcb, PR-TASK 9f92c43e

## Finding (read-only study, 2026-10-29)

- No machine-free path exists: backup browse, browse-at, backup restore and renet restore/restore-path all run on a machine; `backup verify --store` re-hashes chunks on the server and never rebuilds an image (packages/cli/src/commands/backup-storage.ts:345; private/renet/cmd/renet/backup_restore.go:273).
- renet's restore engine (pkg/chunkstore download.go, restore.go, manifest.go) builds on every OS and takes the store as a ReadPlane interface (private/renet/pkg/chunkstore/download.go:41-43); renet is cross-compiled for darwin and windows and embedded in those CLI builds (.ci/rediacc_ci/build/prepare_cli_assets.py:128-140). On non-Linux, hole punching fails (punch_other.go) and the engine then discards the local file (private/renet/pkg/chunkstore/restore.go:96-108), so an incremental update would re-download everything until darwin and windows punch exist.
- Sessions are minted only from a licence blob plus a machine id (private/account/src/routes/backups.ts:165-174). Every member CLI login holds `backup:read` (private/account/src/services/device-code.service.ts:356) and an unscoped token reaches every lineage (private/account/src/routes/backups.ts:105), so a restore session gated on `backup:read` would make any stolen login a bulk-download credential.
- Chunks are LUKS ciphertext verified by sha256 (private/renet/pkg/chunkstore/restore.go:245-262); the passphrase stays in the config's per-repo credential and never reaches the server. A copy fetched on macOS or Windows cannot be opened there (no cryptsetup); it is an offline archive for `backup upload` or a Linux host.
- A TypeScript reimplementation was rejected: about 700 lines, no hole punching in Node, and it would re-create the stale-bytes trap clearStaleHoles closes.

## Design

- Account: `POST /backups/restore-session` behind a new `backup:restore` token scope that member logins do not get by default, plus requireLineageInScope (team 404), a role check at use, a refusal for unscoped tokens, a per-token rate limit and daily GET budget, and an audit entry naming the user and the token. It mints `intent: 'restore'` with the lineage as grandGuid, so read grants and chain resolution work unchanged.
- renet: `renet backup fetch-image` reads a session token on stdin and a destination file, wraps the token in a ReadPlane and calls chunkstore.Restore; the destination doubles as the resume file. darwin (F_PUNCHHOLE) and windows (FSCTL_SET_SPARSE plus FSCTL_SET_ZERO_DATA) punch keep incremental updates incremental.
- CLI: `rdc backup download <ref> --to <dir> --store [--at <time|snapshot>]`, refusing -m, --checkpoint and --include-forks; local verification is the per-chunk hashes plus the LUKS header magic.

## Boxes

- [x] A1 [opus] Account scope and route: the `backup:restore` scope (type union, zod enum, device-code mint policy leaving it out of member logins), the restore-session route with team scoping, unscoped refusal, role check, rate limit, daily budget and audit. Accept: `cd private/account && npx vitest run tests/integration/backup-restore-session.test.ts` rc 0 (team 404, unscoped refused, member without the scope refused, rate limit, the minted session can read grants and cannot write).
    (ticked) 2026-10-29T20:19:40Z by d778be9d: commit:2cf9a8f5f account eb00657 backup-restore-session vitest 11 passed rc=0, full account 3039 rc=0
- [x] A2 Account migration recording the token id and user on the session row. Accept: the migration test and `npx tsc --noEmit` rc 0.
    (ticked) 2026-10-29T20:44:51Z by d778be9d: commit:adead3c87 account 3bb35e6 migration 0070, tsc rc=0, migration test in backup-restore-session rc=0. DEPS-WAIVED: the account route and migration stand alone; the prerequisites gate only the CLI download path (C1) and renet fetch
- [ ] R1 [opus] renet `backup fetch-image` with the token ReadPlane, resume by local hash, and a non-Linux rename for placement. Accept: `cd private/renet && go test ./cmd/renet/ -run FetchImage -count=1` rc 0.
- [ ] R2 [opus] darwin and windows hole punching, with a native test job in ci-build-renet.yml like the procwalk job. Accept: `GOOS=darwin go vet ./pkg/chunkstore/` and `GOOS=windows go vet ./pkg/chunkstore/` rc 0, and the native job green.
- [x] C1 CLI `--store` branch, `--at`, the header check, i18n in 13 locales and docs. Accept: `cd packages/cli && npx vitest run src/commands/__tests__/backup-image-store.test.ts` rc 0, plus check:ci-cli-contract, check:cli-docs and check:i18n rc 0.
    (ticked) 2026-10-29T21:57:41Z by d778be9d: commit:9cf170770 backup-image-store vitest 13 passed rc=0; check:ci-cli-contract rc=0, check:cli-docs rc=0, check:i18n rc=0. DEPS-WAIVED: the CLI store branch reads the landed account route and renet fetch-image; the local-image prerequisite boxes do not gate it
- [x] L1 [live] Bench: mint a restore session with a scoped token, fetch a small lineage, and show the refusals for a member token and an unscoped token. Accept: the fetch rc 0 and both refusals answer 403.
    (ticked) 2026-10-29T22:33:53Z by d778be9d: bench worker 3906a08b: team token with backup:read+backup:restore, rdc backup download hb1023-src --store rc=0, bytesFetched 79691776, image begins with the LUKS magic; member POST /api-tokens with backup:restore 403 INSUFFICIENT_ORG_ROLE, its backup:read token 403 on restore-session; demoted creator token 403 INSUFFICIENT_ORG_ROLE after a 200 control; team-less token row 403 TEAM_SCOPE_REQUIRED; cleaned up. DEPS-WAIVED: the bench proof of the landed route and CLI needs neither the local-image plan nor the hardening L2 stable step
- [ ] L2 [live] Hostinger lineage, read-only: fetch one seeded repo to a local path, then fetch again and record the bytes fetched by the incremental run. Accept: both runs rc 0, the second fetches only changed cells, and the image sha256 equals the recorded one.

- [ ] LP-bench [live] Fresh bench receipt through worklist.py --live-proof, after this plan's bench-deployable boxes land.
  Accept: live-proof bench account-smoke

- [ ] LP-hostinger [live] Fresh hostinger receipt through worklist.py --live-proof, after this plan's hostinger-deployable boxes land.
  Accept: live-proof hostinger renet-live machine=hostinger
