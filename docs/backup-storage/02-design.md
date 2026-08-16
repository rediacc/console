# 02. Design and scored decisions

> **SUPERSEDED IN PLACES — read `07-execution-record.md` first.** The operator
> has since decided the grant fix (option a-prime: the SERVER names the keys),
> the quota approach (fix the chain shape AND make prune chain-aware AND wire
> retention), and that restore is built now. Decision 1's winner (r2-temp-creds)
> is also the branch that had never executed once, and carried two silent bugs.
> Where a scored decision below conflicts with 07, 07 wins.


Status: Locked design, scored 2026-08-09. Items marked RECOMMENDED are defaults the
operator can still override in the early decision round; everything marked Locked was
decided by the operator in the source session and is not to be relitigated.

## Locked by the operator (do not relitigate)

- Big-bang: one campaign, everything lands together; no v1/v2 shipping split.
- No licensing/tier gating anywhere in this feature: all users get the same
  functionality; the ONLY lever is the per-subscription byte quota, definable per
  subscription, default 10 GB for free/community.
- Pricing matters more than performance when they conflict.
- Opus for code implementation, Sonnet for translations (Fable for the hardest
  pieces and planning, per the staffing section).
- Local-first testing: everything that can be proven locally is proven locally
  before any push; cloud probes are a separate, cost-declared leg.

## The core: content-addressed chunk store, no delta chains

Fixed grid over the LUKS image: cell i covers [i*C, (i+1)*C). A snapshot MANIFEST
maps every cell to either ZERO (wholly hole/unwritten per FIEMAP metadata, never
content-scanned) or the SHA-256 of the cell's ciphertext, which is also the object
key: `t/<tenant>/l/<lineage>/c/<sha256>` with lineage = grand_guid so forks dedup.
First upload writes all non-zero cells. Every later run: reflink-snapshot the image
under the repo flock, `delta.Compare(anchor, snapshot)` with strategy `physical`,
read+hash only touched cells, upload only hashes the store lacks (create-only PUT
with If-None-Match), commit the manifest, advance the anchor (reflink swap).

Why this dissolves the classic problems:
- Restore: no chain replay ever. Any snapshot = fetch manifest, parallel-GET its
  cells, write at offsets into a sparse file. RTO is bandwidth-bound and constant in
  history depth. Re-baselining and image compaction are non-problems.
- Point-in-time with only the live repo on disk. **NOT AS SHIPPED, corrected
  2026-08-16.** This described restore as a DIFF against local state downloading
  only cells that differ from the target manifest, "churn-sized, not
  image-sized". `assembleImage` (`pkg/chunkstore/restore.go:30`) fetches every
  non-ZERO cell the materialized manifest names, so a restore IS image-sized.
  What shipped is narrower and still worth having: an interrupted restore adopts
  its staging file, re-hashes each non-ZERO cell against the manifest and reuses
  what matches (`ChunksReused`, `restore.go:292`), discarding the file if the
  holes are no longer holes; and a hash appearing at several offsets is fetched
  once. Customer copy must NOT promise churn-sized restore. Materialize as a
  reflink fork (repo checkout semantics), promote to swap in place. Fresh-machine DR
  is the only full download. The same "which hashes exist" logic serves seed,
  incremental push, resume, point-in-time fork, and bare-metal DR.
- Integrity: object key IS the content hash; manifests are complete inventories.
  Verify levels: (a) ledger-vs-bucket listing diff (nightly scrub), (b) HEAD every
  cell, (c) sampled re-download+rehash, (d) full rehash. Strictly stronger than the
  old `.delta` footer.
- Resumability: atomic unit = one idempotent chunk PUT. A SIGKILL wastes at most the
  in-flight cell. Journal + server exists-batch resumes exactly.
- GC/retention: manifests are GC roots; retention is a policy over manifests (GFS
  knobs per strategy); chunks die at refcount zero. No compaction of image data,
  only kilobyte-scale manifest consolidation, done server-side.

Manifests: delta manifests (parent + changed cells) with periodic server-side
synthetic-full consolidation; grid geometry (cell size) recorded in every manifest;
GC never deletes a manifest a retained delta manifest references. Manifests are
bucket-resident (self-describing store) and structurally plaintext (server must read
chunk references for GC; they leak geometry/churn only), with a D1 index.

Cell size: chosen by measurement (wave 0 churn instrument), recorded per repo, fixed
until an explicit re-seed. Expect 1-4 MiB. Ops costs push weakly larger, churn
amplification pushes strongly smaller; storage is the entire bill. Single-part PUTs
always. No compression anywhere (ciphertext is incompressible; ZERO-cell elision via
FIEMAP is the only "compression").

## Scored decisions (winners)

1. Cloud data-plane grant: LOCALLY-SIGNED R2 temp credentials with an `actions`
   allowlist (PutObject + multipart set, NO delete verbs), prefix-scoped, about 1h
   TTL, re-minted mid-run as a normal event. Rationale: no REST call in the mint
   path (the REST API is capped at 1,200 req/5min account-wide) and the only
   write-without-delete option. Fallback and customer-S3 path: presigned batches.
   Rejected: REST-minted creds (rate cap, delete included), proxy-through-Worker
   (streaming rewrite, no gain; pricing difference is cents either way).
2. Elite data plane. RECOMMENDED: filesystem-backed chunk PUT/GET routes in the
   elite hono server (Node streams, atomic rename, create-only and no-delete
   enforced in code, fs usage = metering). Alternative kept alive: pinned RustFS
   behind a conformance probe suite (presigned round-trip, conditional PUT,
   multipart, DeleteObjects, expiry), which is built regardless as the acceptance
   test for any customer-supplied S3. MinIO is dead (archived). renet's uploader
   speaks a grant abstraction: r2-temp-creds | presigned-s3 | direct-https.
3. Overwrite/delete protection: If-None-Match create-only PUT + delete-free grants +
   server-only deletes. Bucket locks demote to an optional compliance layer on the
   manifests prefix (they are API-removable, hence never true WORM). Strict-WORM
   customers point the presigned path at AWS S3 Object Lock later.
4. GC-versus-dedup race: exists-answers create 24h ledger PINS; uploads hold
   LEASES; GC deletes only unreferenced + unpinned + unleased + older than a 7-day
   grace. Built into the commit protocol from day one.
5. Buckets: PER-SUBSCRIPTION bucket. R2 allows 1M buckets; temp creds are
   bucket-scoped natively; per-bucket metrics give a free usage cross-check;
   lifecycle/locks/jurisdiction are per-bucket; offboarding = delete bucket. EU
   subscriptions get `jurisdiction=eu` buckets (note the `eu_` name prefix quirk in
   GraphQL analytics). Keyspace stays prefix-based so pooled buckets remain possible.
6. Quota: PHYSICAL unique stored bytes per subscription (what R2 bills us; dedup
   benefit passes to the user). `storageQuotaBytes` plan default + nullable
   override + usage-adjustment column, copying the issuance-quota stack. Enforced at
   grant-mint time (refuse before I/O is spent, retry-after attached); ledger
   authoritative, per-bucket metrics as sanity check, nightly listing reconcile as
   truth. Portal shows stored bytes vs quota AND logical protected data.
7. Machine auth: license-blob exchange for a short-lived storage session token
   (`config_tokens` semantics), exactly the `renew.go` shape with the server-stamped
   URL convention. Machines continue to hold nothing. The CLI mediates interactive
   queries via the tunnel with a new `backup:read` scope; the MACHINE commits its
   own manifests (scheduled runs have no CLI present).
8. Stream identity: server-minted stream ID at first backup per (subscription,
   repo GUID, machine), persisted in the journal; hardware machine ID is advisory
   metadata only (fragile to NIC swaps, duplicated by VM clones).
9. Ordering under constraint: plan the whole run first (Compare is free), then
   schedule furthest-behind-RPO first, ascending delta size second. The lost-work
   motive for smallest-first is structurally gone.
10. Cadence: per-repo policy, default decided by the wave-0 churn measurement.
    RECOMMENDED 1h default, 5-minute opt-in. Per-repo snapshots are held for
    MINUTES (snapshot, compare, upload delta, advance anchor, delete), never a
    datastore-wide snapshot for hours: this also dissolves the trim-starvation
    interaction (`pkg/trim/trim_linux.go:50,177-179`).
11. Lifecycle policy (first one in the product): retain-on-cancel read-only 60 days
    then sweep (nightly cron, named constant); over-quota-after-downgrade = hard-cap
    new writes, soft-carry existing with an over_limit flag that self-clears;
    refunds freeze, never delete; GDPR delete = the config-store deletePrefix
    pattern, one bucket delete per subscription. Nothing is deleted without an
    explicit event.
12. On-prem quota transport: `storageQuotaBytes` rides INSIDE the signed delegation
    cert (populated from the subscription row, like maxRepositorySizeGb), because
    the on-prem admin has no subscription-edit surface by design. Elite metering
    runs in the elite server's own SQLite.
13. Infrequent Access: post-launch flag pending GA confirmation; when adopted, a
    lifecycle rule transitions 30-day survivors (by then provably stable) for about
    a third off storage on the stable majority.
14. Zero-knowledge boundary: we store ciphertext and see ciphertext hashes; repo
    names never reach the server (GUIDs only); the portal resolves names client-side
    after CEK unlock (requires splitting config-session availability from the paid
    webConsole gate, since COMMUNITY is the quota page's main audience). The DR
    story reduces to config-storage enrollment: the repo `credential` field IS the
    LUKS slot-0 passphrase and syncs inside the CEK-encrypted blob; slot-1 keyfiles
    self-heal on `repo up`.

## Cost model (for the docs wave to quote honestly)

Storage dominates. 137 GB seed: about $2/mo Standard, ops pennies. Churn cost =
cadence x hot-block amplification x retention; the churn instrument turns this into
measured numbers per repo. R2 egress is free (restores cost nothing but time).
Community 10 GB rides R2's own free tier shape. First uploads carry only written
extents (FIEMAP), typically far below nominal image size; trim shrinks backups.
