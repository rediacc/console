# PLAN: chunk-store BROWSE, argued from the account server and the CLI
Status: compacted
First-Seen: 2026-09-17
Full-Text: f7a5351a9 agent/PLAN-chunk-store-browse-server.md
Full-Text-Blob: d35bf9ec010014690d6e890ee6aa1e16f3c5c1fd
Record-Sig: f6e46844

## Why
The operator wanted to ask whether a particular file is inside a backup. This plan was one of two competing angles, assigned "server-and-client-first, renet changes as a last resort". Its verdict: the engine must PRODUCE a file index (no listing is derivable from a manifest, which hashes LUKS ciphertext in a fixed grid and carries no namespace at all), but the engine is the wrong
place to SERVE one. A browse whose whole purpose is "should I restore?" must work when no machine survives, so routing it through an executor makes it useless in the disaster it exists for. It proposed a per-snapshot encrypted table of contents written at snapshot time, stored opaquely by the account server, and decrypted by the CLI.

## Outcome
NOT ADOPTED. The rival engine-first angle shipped instead, and none of this plan's own deliverables exist. Measured 2026-09-06.

- `rdc backup browse` EXISTS, but in the shape this plan argued against.
`registerBackupBrowse` (`packages/cli/src/commands/backup-storage.ts:208`, blob b22de98ed1761c71d20faabefa3894867890b564) resolves a repo ref and calls `executeRepoFunction('backup_browse', ...)`, so it must reach a machine holding the image. Landed by console commit 3f52d5d52, "feat(cli): rdc backup browse, and the reference the retention fix still owed" (2026-08-18).
- Nothing from section 5 is in the tree: no browse or TOC route in
`private/account/src/routes/backups.ts`; no TOC table or column in `private/account/src/db/schema.ts`; the HKDF info string `rediacc-backup-toc-v1` appears nowhere in either repo; `private/renet/pkg/backupindex/` does not exist; there is no `--no-index` flag. Historical browse (`--at`) is therefore still unreachable.
- Section 1.4's correction HELD. `rdc storage browse` was not retired and is still
registered at `packages/cli/src/commands/storage.ts:259` over `packages/cli/src/services/repo/storage-browser.ts`.
- THE HEADER IS TRUE ABOUT ITSELF AND MISLEADING ABOUT ITS SUBJECT. "Status: design only,
no code written" is accurate for this file and reads, eighteen days later, as though browse were unbuilt. `agent/PLAN-chunk-store-browse-engine.md` and `agent/PLAN-chunk-store-browse-DECISION.md` record the same conclusion from the winning side.

## Lessons
- A losing angle needs a status that says LOST. "No code written" and "this design was
not adopted" are both true; only the second stops a reader treating the file as live design work.
- The zero-knowledge argument survived the loss by accident rather than by design: the
shipped browse reads the image locally, so no filenames reach the server. The plaintext TOC this plan refused to design was never built, and neither was the encrypted one.
- Section 1.7 is a real finding that is still open and still unowned: no backup table
carries a team column, so within one subscription any `backup:read` token sees every lineage. Today that leaks sizes and churn; it is the reason the TOC had to be encrypted.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: UNKNOWN
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:30:33Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: private/renet/pkg/chunkstore/manifest.go, private/renet/pkg/chunkstore/pipeline_linux.go, private/renet/pkg/chunkstore/uploader.go, private/renet/pkg/chunkstore/hash.go, private/account/src/db/schema.ts, private/account/src/services/backup-gc.service.ts, private/account/src/services/backup-chunk-store.ts, private/account/src/services/backup-storage.service.ts, packages/cli/src/commands/storage.ts, packages/cli/src/services/repo/storage-browser.ts, docs/backup-storage/05-docs-and-decommission.md, docs/backup-storage/README.md, private/account/src/routes/backups.ts, packages/cli/src/services/account/account-client.ts, packages/cli/src/services/config/config-base.ts, packages/cli/src/adapters/remote-config-adapter.ts, packages/cli/src/services/config/remote-cache.ts, packages/cli/src/adapters/config-file-storage.ts, packages/cli/src/commands/config.ts, private/account/src/middleware/api-token.ts
Gates: check:ci-account-scope-audit, check:ci-account-server, check:ci-cli-contract, check:ci-command-planes, check:ci-command-tree, check:ci-design-tree, check:ci-i18n-cli-key-usage, check:ci-tutorial-cli-validity, check:cli-examples, check:i18n, check:test-cli
Why-Source: author
Read-History: `git show d35bf9ec010014690d6e890ee6aa1e16f3c5c1fd` recovers the text; `git log --find-object=d35bf9ec010014690d6e890ee6aa1e16f3c5c1fd --all` names the commit

## History
- 2026-09-06T17:30:33Z compacted by 8f55d4f0 from `UNKNOWN` (record-sig f6e46844)
