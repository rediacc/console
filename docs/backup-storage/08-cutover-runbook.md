# 08. Cutover runbook: chunk store in, rclone/OneDrive out

Wave 5. This is the credential-free half, prepared so the credentialed legs are
a single copy-paste rather than a discovery exercise. It was written by
executing the standing default on the wave-5 deferral, not by guessing what
cutover might involve: every claim below was checked against the tree.

**Nothing here touches production data or the OneDrive archive.** The steps that
do are yours, listed in §2 and nowhere else.

---

## 0. The one ordering rule

**Nothing whose removal destroys the last restore path may go before the new
restore is proven ON A MACHINE.**

Until e2e suite 26's RESTORE tier goes green on a real two-worker fleet, rclone
is the only way to get data back. `scripts/backup-cutover-preflight.sh` enforces
this as a check rather than a sentence: it FAILS if the rclone schedule path has
already been removed from the unit generator.

Restore exists and is verified in the small (`go test -race` over the engine, 88
account test files, the drill's read-grant legs d/j/k). It has NOT been run by a
machine against a real bucket, because no bucket exists. That gap is exactly
what §2 closes.

---

## 0.1 DEPLOY ACCOUNT AND RENET TOGETHER, or every chunk PUT gets a 403

Added 2026-08-15, from a live probe rather than reasoning. The chunk and manifest
PUT URLs are now presigned WITH `IfNoneMatch: '*'`, which closes the create-only
hole the design promised and never had.

A presigned URL signs the headers it carries, so the two halves are welded:

| server signs | client sends | result |
|---|---|---|
| `IfNoneMatch` | the header | 200, duplicate gives 412 |
| `IfNoneMatch` | nothing | **403 SignatureDoesNotMatch** |
| nothing | the header | 200, condition silently ignored |

So an OLDER renet talking to the UPDATED account fails **every** chunk PUT with a
signature error, and the message names signatures rather than versions, which is
the kind of error that costs an hour at 3am. Ship the account worker and the
renet binary in the same window, and prove the machine's renet is the new one
before the first scheduled run.

There is a third client of this wire that is easy to forget: the drill
(`scripts/drills/backup.sh`) PUTs cells and the manifest with bare `curl`. It
went from 86/86 to 14 failures the moment the server started signing the
condition, and needed `-H 'If-None-Match: *'` on both PUTs. Anything else that
speaks this protocol directly needs the same.

## 1. Preflight, and it fails closed

```bash
scripts/backup-cutover-preflight.sh
```

Read-only: no bucket creation, no object writes, no credential minting, no
mutating Cloudflare or R2 call. Run it against production as often as you like.

It refuses rather than skips. With no store credentials it exits 1 saying so,
because a preflight that reports "looks fine" when it could not reach the store
converts an absent bucket into a green light, and the first thing anyone does
with a green light is decommission the working restore path.

Proven in both directions on 2026-08-14: with `rediacc-releases` it reports the
bucket exists and exits 0; with a nonexistent bucket name it reports `404` and
exits 1.

Once you have created a bucket:

```bash
ACCOUNT_BACKUP_S3_ENDPOINT="https://<account>.r2.cloudflarestorage.com" \
ACCOUNT_BACKUP_S3_BUCKET="rediacc-backups-probe" \
ACCOUNT_BACKUP_S3_ACCESS_KEY_ID="..." \
ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY="..." \
  scripts/backup-cutover-preflight.sh
```

---

## 2. The credentialed legs — yours, and why each is yours

These need operator-only powers (external accounts, secrets, production
deploys). I cannot do them and have not attempted them.

### 2.1 Create the probe bucket FIRST

Name it **`rediacc-backups-probe`**, never `rediacc-backups`. Your instruction,
and the preflight enforces it: a bare production name is a hard failure, so no
misconfiguration can cross test and production backups.

### 2.2 Decide the grant minter — this changes what you set

**CORRECTED 2026-08-15. The previous text here was stale and would have made you
delete a binding you should keep.** It claimed `createBackupPlane` returns EARLY
on the R2-binding branch so `ACCOUNT_BACKUP_S3_*` is unreachable whenever a
`BACKUP_BUCKET` binding exists. That is no longer true, and the code says so in
as many words: inside the binding branch
(`private/account/src/services/backup-chunk-store.ts:921-956`), if
`ACCOUNT_BACKUP_S3_ENDPOINT` and `ACCOUNT_BACKUP_S3_ACCESS_KEY_ID` are set it returns
`{ store: R2BackupChunkStore, grantMinter: S3PresignGrantMinter }`.

So a `BACKUP_BUCKET` binding is not merely harmless, it is the BETTER
configuration: the store stays the native R2 binding (no S3 round trip for GC or
reads) while grants are presigned with `ACCOUNT_BACKUP_S3_*`. The JWT minter is kept but
deliberately NOT selected. What still must not be set is
`ACCOUNT_BACKUP_R2_GRANT_PARENT_SECRET`, which is what would select the unproven JWT path, and
the preflight fails if it is.

| Option | What you set | State |
|---|---|---|
| **Presign minter (recommended, the recorded default)** | `ACCOUNT_BACKUP_S3_ENDPOINT`, `ACCOUNT_BACKUP_S3_BUCKET`, `ACCOUNT_BACKUP_S3_ACCESS_KEY_ID`, `ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY`, and **no** `BACKUP_BUCKET` binding | The path RustFS, local dev and customer S3 already use. Provable in tier A. |
| R2 locally-signed JWT | a `BACKUP_BUCKET` binding + `ACCOUNT_BACKUP_R2_GRANT_ENDPOINT`, `ACCOUNT_BACKUP_R2_GRANT_BUCKET`, `ACCOUNT_BACKUP_R2_GRANT_PARENT_ACCESS_KEY_ID`, `ACCOUNT_BACKUP_R2_GRANT_PARENT_SECRET` | **Refused by live R2 in every variant tested**, including Cloudflare's documented one. See `07-execution-record.md` §6.1. |

R2 speaks the S3 API, so the presign option works against an R2 bucket; the
store is `S3BackupChunkStore` instead of `R2BackupChunkStore`, which is a
different class and the same bytes.

The preflight fails if `ACCOUNT_BACKUP_R2_GRANT_PARENT_SECRET` is set, on the grounds that
selecting an unproven minter for production is a decision, not a default.

### 2.3 The copy-paste block

Substitute your account id and the key pair, then run from the repo root:

```bash
# 1. Confirm the bucket exists and the credentials are scoped to it (read-only).
ACCOUNT_BACKUP_S3_ENDPOINT="https://<account>.r2.cloudflarestorage.com" \
ACCOUNT_BACKUP_S3_BUCKET="rediacc-backups-probe" \
ACCOUNT_BACKUP_S3_ACCESS_KEY_ID="<key id>" \
ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY="<secret>" \
  scripts/backup-cutover-preflight.sh

# 2. NOTHING TO DO BY HAND ANY MORE. SUPERSEDED 2026-08-18.
#    CD now pushes these four to every account Worker on every deploy, so a
#    hand-pushed secret is at best redundant and at worst a value that drifts
#    from the one CI holds. The chain, all four links required:
#      - the four values live as GitHub ORG secrets scoped to `console`
#      - .github/workflows/cd-deploy-account.yml declares them under
#        on.workflow_call.secrets AND passes them into "Set Worker secrets"
#      - all three callers pass them: cd-v2.yml deploy-account-edge,
#        cd-v2.yml deploy-account-stable, promote-stable.yml
#      - .ci/scripts/deploy/set-account-worker-secrets.sh puts them in the jq
#        payload piped to `wrangler secret bulk`
#    `check:ci-workflow-gates` enforces the declare-and-pass contract in BOTH
#    directions, so an incomplete rewiring fails CI by name rather than
#    shipping a Worker whose backup endpoints answer 503. Verified by control:
#    deleting one caller's pass-through reddens it with
#    "promote-stable.yml: job 'deploy-account-stable' -> cd-deploy-account.yml:
#     does not pass required secret ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY".
#
#    `wrangler secret bulk` MERGES rather than replacing, so any secret set by
#    hand outside this list survives a deploy.
#
#    The old manual loop is kept below ONLY as the break-glass path for a
#    target CD does not cover (e.g. a one-off bench worker). The worker configs
#    live in workers/account, NOT in the private/account submodule, and each
#    target is its OWN config file (wrangler.bench.toml, wrangler.eu.toml,
#    wrangler.edge-eu.toml, ...), not an [env.*] section — so this is
#    `--config <file>`, never `--env edge`.
#
# cd workers/account
# for k in ACCOUNT_BACKUP_S3_ENDPOINT ACCOUNT_BACKUP_S3_BUCKET ACCOUNT_BACKUP_S3_ACCESS_KEY_ID ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY; do
#   npx wrangler secret put "$k" --config wrangler.edge-eu.toml
# done
#
# NOTE (2026-09-02): ACCOUNT_BACKUP_S3_BUCKET is still the WORKER-side
# variable name, so the break-glass loop above is unchanged. But it is no longer a GitHub secret
# and must not be recreated as one. CD now derives it per region and per channel
# from regions.json (backupR2 / edgeBackupR2) and hands it to
# set-account-worker-secrets.sh, because one global bucket name against six
# per-region BACKUP_BUCKET bindings meant the presign signer signed for a
# different bucket than the Worker read and GC'd. Likewise
# ACCOUNT_BACKUP_S3_ENDPOINT is stored as the DEFAULT host and the
# jurisdiction label is inserted at deploy time from regions.json's
# r2Jurisdiction, since the EU buckets answer only at
# <account>.eu.r2.cloudflarestorage.com. check:ci-backup-bucket-conformance
# holds regions.json and the wrangler bindings together.

# 3. Register the credential for rotation (slug: cf-r2-backup), so this key
#    joins the same lifecycle as cf-r2 and cf-r2-media rather than living
#    forever outside it.
./run.sh rotation list          # confirm the slug is absent before adding it
```

`cf-r2-backup` should be **bucket-scoped to the backup bucket only**, the way
`cf-r2-media` is scoped to `rediacc-www-media` rather than account-wide. An
account-wide key here would make one backup credential equivalent to R2 admin.

### 2.4 The end-to-end proof, once the bucket exists

```bash
# On a machine with a real repo, not on this host:
./rdc.sh backup snapshot <repo>
./rdc.sh backup manifests <repo>
./rdc.sh backup restore <repo>@<place> --as <repo>-restored --at <snapshot-id>
```

Then the one assertion the whole program rests on: the restored image is
byte-identical to the source. e2e suite 26's RESTORE tier automates exactly
this across two machines and is no longer dark — it defaults to the real verb
and probes `renet backup --help` on the deployed binary.

---

## 3. Migration of the real machines

Order matters, and it is the reverse of the intuitive one: **add the new path,
prove it, run both, and only then remove the old.**

1. **Add.** Deploy renet carrying `backup snapshot`/`backup restore` to each
   machine. `./rdc.sh` syncs the freshly built binary on any invocation.
2. **Prove per machine.** `backup snapshot`, then `backup restore` into a
   throwaway name, then compare. A machine that has not round-tripped is not
   migrated, however green its uploads look.
3. **Run both.** Leave the rclone schedule in place for at least one full cycle
   after the first successful chunk restore on that machine. Two backup paths
   cost storage; one unproven path costs the data.
4. **Only then remove.** The scheduling clean break
   (`packages/cli/src/services/backup/backup-schedule-unit-generator.ts:128`
   still emits `backup sync push`) is tracked separately and is deliberately
   gated behind this step.

The OneDrive archive is not deleted by any step here. Retiring it is a separate
decision after the chunk store holds a full retention window.

---

## 4. What this runbook does NOT claim

- It does not claim the chunk path has ever run against a real bucket. No bucket
  exists yet; that is §2.1.
- It does not claim R2 enforces the prefix scope, the delete-free action list,
  or grant expiry. Those are the ransomware property and are unproven — the
  read-only probe could never reach them, because no locally-signed credential
  was accepted at all (`07-execution-record.md` §6.1).
- It does not claim byte-identical cross-machine restore is proven. It is
  proven in the small and automated in suite 26; it needs the fleet and the
  bucket to actually run.
