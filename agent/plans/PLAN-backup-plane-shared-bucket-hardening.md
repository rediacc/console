# PLAN: the shared backup bucket stops trusting the client for object sizes, and its credential is proven to reach one bucket only

Status: approved -- operator 2026-10-29 ASKED "Implement all, promote (Recommended)" after the tenant-isolation audit (worklist #02467f38)
Depends-On: no-dep -- the account, renet and credential boxes need nothing outside this plan
Owner: d778be9d
Priority: P2 -- no cross-org data exposure was found; these are hardening and cost-abuse fixes on the shared regional bucket
Owns: agent/plans/PLAN-backup-plane-shared-bucket-hardening.md, private/account/src/dto/backup.dto.ts, private/account/src/services/backup-chunk-store.ts, private/account/src/services/backup-storage.service.ts, private/account/tests/integration/backup-upload-bounds.test.ts (new), private/account/tests/integration/backup-presign-grant.test.ts, private/account (gitlink bump only), private/renet/pkg/chunkstore/session.go, private/renet/pkg/chunkstore/grants.go, private/renet/pkg/chunkstore/grant_bounds_test.go (new), private/renet (gitlink bump only), .ci/rediacc_ci/ops/backup_bucket_scope_probe.py (new), .ci/rediacc_ci/tests/test_ops_backup_bucket_scope_probe.py (new)
Concurrency: parallel -- A1 (account) and R1 (renet) have disjoint Owns; R1 sends the sizes A1 starts requiring, so the deployed renet must send them before A1 reaches stable; the CLI is untouched
Live-Proof: bench, hostinger -- bench proves a grant without sizes is refused and a sized upload still works; hostinger's next scheduled snapshot proves production uploads keep working
Updated: 2026-10-29
First-Seen: 2026-10-29
Worklist: #02467f38, PR-TASK 9f92c43e

## Finding (read-only audit, 2026-10-29)

Tenant isolation holds: every key is server-built as `t/<subscriptionId>/l/<lineageGuid>/{c,m,i}/...` (private/account/src/services/backup-chunk-store.ts:45-58), dedup HEADs only the caller's own lineage prefix (private/account/src/services/backup-storage.service.ts:1110-1116), GC, prune, purge and the orphan sweep are scoped by subscription and lineage, `deletePrefix` refuses an unterminated prefix (private/account/src/services/backup-chunk-store.ts:204), presigned URLs are one key, one verb, create-only, 1 h, and restore re-hashes every chunk against the manifest (private/renet/pkg/chunkstore/restore.go:245-262). Chunks are LUKS ciphertext; the browse index is ECIES-encrypted to a passphrase-derived key.

Three residual risks:

1. Medium (inferred, unverified). The Worker signs every tenant's URLs with one `ACCOUNT_BACKUP_S3_*` credential. Its scope (one bucket, or account-wide) is not provable from the code; earlier probes used account-wide keys (private/account/src/services/backup-chunk-store.ts:689). A leak or SSRF reaches every org in the region, and other buckets too if the token is account-wide.
2. Low. Size-unbounded PUTs: a chunk URL signs no Content-Length when the request omits `chunkBytes` (private/account/src/services/backup-chunk-store.ts:866), and manifest and index URLs never sign one. A paying tenant can store up to the single-PUT ceiling per URL, up to 1000 URLs per grant call, billed to the operator until the 7-day GC grace.
3. Low, in-org only. A leaked licence blob plus machine id mints sessions for that lineage; the data reached is ciphertext.

## Boxes

- [x] A1. Account: `chunkBytes` becomes required in the grant DTO and the unbounded branch of `S3PresignGrantMinter.mint` is deleted; manifest and index grants take `manifestBytes`/`indexBytes`, capped at `BACKUP_MANIFEST_MAX_BYTES`, and sign `content-length`. Siblings: the unselected R2 JWT minter (delete it, it carries ListBucket) and `MemoryGrantMinter` follow the same rule. Accept: `cd private/account && npx vitest run tests/integration/backup-upload-bounds.test.ts tests/integration/backup-presign-grant.test.ts` (a grant without sizes answers 400; tenant A's session cannot get a URL under tenant B's prefix, with a control).
    (ticked) 2026-10-29T21:44:53Z by d778be9d: commit:e14f4f48a account 4da3475 (ancestor of account HEAD 3bb35e6); backup-upload-bounds and backup-presign-grant vitest 29 passed rc=0 at 2026-10-29T21:5xZ
- [x] R1. Renet: the session client sends the manifest and index sizes and always sends chunk sizes. Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'GrantsAreBatched|UnboundedServer|EveryRequestedHash|BoundsFake|NamesThe|ReMints|IndexLength|OversizeIndex|IndexAtTheLimit|BoundedURL' -count=1 -v` rc 0, its PASS lines including all 12 tests of grant_bounds_test.go (no test is named GrantBounds, so a -run GrantBounds matched nothing and passed vacuously).
    (ticked) 2026-10-29T21:45:10Z by d778be9d: commit:e14f4f48a renet 7e6a6f1 (ancestor of renet HEAD 765ac44); the corrected accept regex rc=0 with all 12 grant_bounds_test.go tests PASS; hostinger binary carries manifestBytes
- [x] C1. Credential: mint an R2 API token limited to Object Read and Write on each regional backup bucket, store it through `bws_env` by name, and add `backup_bucket_scope_probe.py`, which proves the token can PUT and GET under a probe prefix of its own bucket and is refused a LIST of another bucket. Accept: the probe exits 0 per region; its pytest exits 0.
    (ticked) 2026-10-29T22:24:06Z by d778be9d: commit:0368ba735 probe rc=0 per region: stable eu/us/asia and edge eu/us/asia every leg PASS (own PUT/GET/DELETE 2xx, foreign LIST 403) at 2026-10-29T22:23Z, bench rc=0; pytest 17 passed; tokens minted earlier by credential-isolation B5
- [x] L1. Bench: deploy A1 and R1, run a snapshot and a restore on a bench machine, and show a size-less grant refused. Accept: the bench snapshot and restore exit 0 and the refusal answers 400.
    (ticked) 2026-10-29T22:24:21Z by d778be9d: bench worker version 3906a08b (account 318b696, branch renet with R1): backup snapshot hb1023-src rc=0 (19 chunks stored), backup restore --as hb1023-rst rc=0, three POST /backups/grants without chunkBytes or manifestBytes answered 400; repos deleted and the lineage purged after
- [ ] L2. Hostinger: after the stable deploy, the next scheduled snapshot of one hostinger repo uploads and commits. Accept: `backup usage` shows the new snapshot.

- [ ] LP-bench [live] Fresh bench receipt through worklist.py --live-proof, after this plan's bench-deployable boxes land.
  Accept: live-proof bench account-smoke

- [ ] LP-hostinger [live] Fresh hostinger receipt through worklist.py --live-proof, after this plan's hostinger-deployable boxes land.
  Accept: live-proof hostinger renet-live machine=hostinger
