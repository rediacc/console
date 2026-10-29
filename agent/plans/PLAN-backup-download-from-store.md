# PLAN: rdc backup download --store rebuilds a repo's encrypted image on a local path straight from the R2 chunk store, with no machine, updating by chunk hash

Status: proposed -- operator 2026-10-29 answered "Go with changes, plan it" on the feasibility study (worklist #b76e7dcb); implementation waits for a second operator go
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
- renet's restore engine (pkg/chunkstore download.go, restore.go, manifest.go) builds on every OS and takes the store as a ReadPlane interface (download.go:41-43); renet is cross-compiled for darwin and windows and embedded in those CLI builds (.ci/rediacc_ci/build/prepare_cli_assets.py:128-140). On non-Linux, hole punching fails (punch_other.go) and the engine then discards the local file (restore.go:96-108), so an incremental update would re-download everything until darwin and windows punch exist.
- Sessions are minted only from a licence blob plus a machine id (private/account/src/routes/backups.ts:165-174). Every member CLI login holds `backup:read` (device-code.service.ts:356) and an unscoped token reaches every lineage (routes/backups.ts:105), so a restore session gated on `backup:read` would make any stolen login a bulk-download credential.
- Chunks are LUKS ciphertext verified by sha256 (restore.go:245-262); the passphrase stays in the config's per-repo credential and never reaches the server. A copy fetched on macOS or Windows cannot be opened there (no cryptsetup); it is an offline archive for `backup upload` or a Linux host.
- A TypeScript reimplementation was rejected: about 700 lines, no hole punching in Node, and it would re-create the stale-bytes trap clearStaleHoles closes.

## Design

- Account: `POST /backups/restore-session` behind a new `backup:restore` token scope that member logins do not get by default, plus requireLineageInScope (team 404), a role check at use, a refusal for unscoped tokens, a per-token rate limit and daily GET budget, and an audit entry naming the user and the token. It mints `intent: 'restore'` with the lineage as grandGuid, so read grants and chain resolution work unchanged.
- renet: `renet backup fetch-image` reads a session token on stdin and a destination file, wraps the token in a ReadPlane and calls chunkstore.Restore; the destination doubles as the resume file. darwin (F_PUNCHHOLE) and windows (FSCTL_SET_SPARSE plus FSCTL_SET_ZERO_DATA) punch keep incremental updates incremental.
- CLI: `rdc backup download <ref> --to <dir> --store [--at <time|snapshot>]`, refusing -m, --checkpoint and --include-forks; local verification is the per-chunk hashes plus the LUKS header magic.

## Boxes

- [ ] A1 [opus] Account scope and route: the `backup:restore` scope (type union, zod enum, device-code mint policy leaving it out of member logins), the restore-session route with team scoping, unscoped refusal, role check, rate limit, daily budget and audit. Accept: `cd private/account && npx vitest run tests/integration/backup-restore-session.test.ts` rc 0 (team 404, unscoped refused, member without the scope refused, rate limit, the minted session can read grants and cannot write).
- [ ] A2 Account migration recording the token id and user on the session row. Accept: the migration test and `npx tsc --noEmit` rc 0.
- [ ] R1 [opus] renet `backup fetch-image` with the token ReadPlane, resume by local hash, and a non-Linux rename for placement. Accept: `cd private/renet && go test ./cmd/renet/ -run FetchImage -count=1` rc 0.
- [ ] R2 [opus] darwin and windows hole punching, with a native test job in ci-build-renet.yml like the procwalk job. Accept: `GOOS=darwin go vet ./pkg/chunkstore/` and `GOOS=windows go vet ./pkg/chunkstore/` rc 0, and the native job green.
- [ ] C1 CLI `--store` branch, `--at`, the header check, i18n in 13 locales and docs. Accept: `cd packages/cli && npx vitest run src/commands/__tests__/backup-image-store.test.ts` rc 0, plus check:ci-cli-contract, check:cli-docs and check:i18n rc 0.
- [ ] L1 [live] Bench: mint a restore session with a scoped token, fetch a small lineage, and show the refusals for a member token and an unscoped token. Accept: the fetch rc 0 and both refusals answer 403.
- [ ] L2 [live] Hostinger lineage, read-only: fetch one seeded repo to a local path, then fetch again and record the bytes fetched by the incremental run. Accept: both runs rc 0, the second fetches only changed cells, and the image sha256 equals the recorded one.
