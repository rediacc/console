# PLAN: retire rclone, payload and feature

Status: done

**2026-08-15 (later): one file inside the removal's scope was edited by the LEAD, not by
the removal agent.** `cmd/renet/backup_snapshot_cold.go` and its test now carry the
container-based quiesce verification (see PLAN-cold-path.md). A live round trip proved the
previous predicate refused every repository it selected, so `--cold` could never store a
snapshot. Anyone reconciling the two workstreams must change that file ON TOP of the fix
rather than reverting it, and must keep `stopColdBackupRepos`, `discoverRunningRepos`,
`coldBackupRepo` and the datastore cold lock alive wherever they end up living -- the
chunk-store barrier depends on all four, and `TestEveryQuiescePathHoldsTheColdLock` is the
check that reports it if the lock invariant breaks.

**2026-08-15: THE GATE IS LIFTED AND REMOVAL IS IN FLIGHT.** The operator authorised it
directly -- "Feel free to remove rclone completely. We already have git versioning." --
and postponed server-side backup, so section 1's wave-5b-ii precondition no longer
applies. Everything else in this plan still holds, especially the consumer inventory.
TWO THINGS SURVIVE DELIBERATELY and a `grep -rl rclone | xargs` sweep would destroy
both: `rdc storage browse` / `storage import`, which spawn the operator's OWN rclone
from PATH and are the only in-product read path to the ~500 GiB OneDrive archive, and
`ops rustfs configure-workers`, which installs rclone on a worker VM and never touches
the embedded asset. Git versioning restores CODE, not runtime access to that archive.

Operator decision, 2026-08-15, asked as a three-way choice (full-now /
full-after-cutover / payload-only): **"Full removal, after cutover."**

The ask that produced this plan: *"also remove embeding the rclone into the rdc
binaries. So, we can have smaller artifact."* The size win is real and is the
same under every option, because it is one payload. What the operator chose is
the **scope** (the whole feature, not just the bytes) and the **sequencing**
(behind the cutover, not beside it).

Two read-only investigations and two independent planning passes produced this.
Where they disagreed, the disagreement is recorded rather than smoothed over.

---

## 1. The precondition, and why it is not negotiable

**Nothing may start here until wave 5b-ii is done and proven.** That wave is
operator-only (worklist `#a450387d`, closed `door:operator-only`): the four
`BACKUP_S3_*` Worker secrets, the bucket-scoped `cf-r2-backup` rotation slug,
and the production cutover. Its runbook is
[`docs/backup-storage/08-cutover-runbook.md`](../docs/backup-storage/08-cutover-runbook.md).

**2026-08-18: THE `door:operator-only` ABOVE WAS WRONG, AND MOST OF THAT WAVE IS
NOT OPERATOR-ONLY.** The door was recorded from a single failed `deploy-bench.sh`
run whose cause was misread as "no Cloudflare credential". The real cause is a
variable-NAME mismatch: `scripts/dev/lib/cf-auth.sh:32` reads `CF_API_KEY`, while
`private/account/.env` supplies the credential under `CF_GLOBAL_API_KEY`. The
credential was present the whole time -- `GET /user` returns `success=true` -- and
`cf-auth.sh:34` auto-mints a scoped, self-destructing management token from it.
`gh` additionally holds `admin:org`. So minting the bucket-scoped `cf-r2-backup`
token and setting the four `BACKUP_S3_*` org secrets are both in-session work,
tracked as `#a90a8649`.

What remains genuinely operator-only is narrower: `wrangler secret put` against a
LIVE production worker, and the machine migration and cutover. Both mutate
deployed production; neither is blocked on a credential.

The lesson generalises past this plan: a door closed from one failed run is a
hypothesis, not a finding. `#a450387d` sat closed for days behind a cause that one
`grep` of the env-file key names would have falsified.

The reason is one fact, and it outranks every convenience argument:

> **The chunk store has never carried a production repo.** `CHECKLIST.md` w8 is
> unticked. Only `rediacc-backups-probe` has ever been written. Meanwhile the
> OneDrive archive holds roughly 500 GiB of real backups whose only in-product
> read path is the code this plan deletes.

Removing the fallback for a path that has never carried production data is the
one move that cannot be repaired forward. Everything else in this plan can.

### Step 0, mandatory, before any code lands

The repo already ruled that the archive is **not migrated**:
`docs/backup-storage/05-docs-and-decommission.md:153-155` says do NOT migrate the
OneDrive objects (incompatible whole-image layout; the first R2 full upload IS
the migration). So the archive is written off as a copy and kept **readable** for
a retention window. Prove that readability before deleting the reader:

```bash
# 0a. The new path works on a real machine. NEW REPOS ONLY (operator's standing limit).
./rdc.sh backup snapshot <new-throwaway-repo>@hostinger
./rdc.sh backup manifests <new-throwaway-repo>
./rdc.sh backup restore <new-throwaway-repo>@hostinger --as probe-restored --at <snapshot-id>
# then byte-compare source vs probe-restored

# 0b. The archive is still readable WITHOUT any renet storage verb.
ssh hostinger '/usr/local/bin/rclone version'      # MUST exist; the extractor is being deleted
./rdc.sh storage browse <storage-name> --path hot  # local rclone, survives the cut
ssh hostinger '/usr/local/bin/rclone copyto ":<backend>:<bucket>/hot/<guid>" \
  /tmp/archive-readback-probe && ls -l /tmp/archive-readback-probe'

# 0c. Confirm deployed backup units pin a VERSIONED slot, not `current`.
ssh hostinger "systemctl cat 'rediacc-backup-*.service' | grep -E 'ExecStart'"
```

`renet-provisioner.ts:56` installs into `${REMOTE_INSTALL_ROOT}/${VERSION}/renet`
and there is no slot GC, so a deployed unit keeps running the old binary with
rclone inside it. **Verify that; do not assume it.** If any unit resolves through
the `current` symlink, the next `./rdc.sh` invocation silently breaks it.

If 0a or 0b fails, this plan does not land. That is a gate, not a warning.

---

## 2. What is actually being removed, and where it lives

**The headline that reframes the task: rclone is not embedded in `rdc` at all.**
It is `//go:embed`-ed into the **renet** Go binary, and `rdc` embeds whole renet
binaries as SEA assets, so it arrives transitively. Every byte argument has to go
through renet.

Measured on disk:

| asset | `.zst` on disk | uncompressed |
|---|---:|---:|
| `amd64/base/rclone-linux-amd64.zst` | 22,811,885 B | 81.4 MiB |
| `arm64/base/rclone-linux-arm64.zst` | 20,327,402 B | 74.7 MiB |

`prepare-cli-assets.sh:84-93` always ships both Linux renet binaries plus the
host one, so the per-artifact cost is **43,139,287 B on linux/windows** and
**63,466,689 B on macOS**.

**The operator's hint was wrong, and it is worth writing down:**
`.github/workflows/cd-v2.yml` contains **zero** occurrences of `rclone` or
`rsync`. It only retags a prebuilt renet image (`:256`). Do not go looking there.

**`rsync` is a different dependency and must survive.** `rdc repo sync` is plain
rsync over SSH with an SFTP fallback. The two are handled by shared lines in
`pkg/embed/embed.go:105,217` and by a shared `RUN` in the Dockerfile at `:513-514`.
Edit those lines surgically. Never delete an asset by grepping for a word.

---

## 3. The boundary: what dies, what lives

### Dies

- **renet**: `backup_sync.go` + `backup_sync_cold{,_other}.go` + `_perrepo` +
  `_pull` and their 5 test files; the storage arms of `backup_pull.go:56-69,573-700`,
  `backup_push.go:~800-900`, `backup_list.go:157-185,305-388`,
  `backup_delete.go:69,104-170`; the `--rclone-*` flags on all four;
  `pkg/functions/commands/backup.go:17-100` (`appendStorageConfig` and friends).
- **embed**: `AssetRclone` (`embed.go:42,70-71,105,217`), the lockfile component
  (`embed-assets.lock.json:107-137` + prose at `:27`), the Dockerfile downloader
  stages (`:269-292,295-317,483-486,513-514,530`),
  `setup_command.go:867-878`, `ops_up.go:209-211`.
- **CLI**: `rdc storage prune` (`storage.ts:28-246,294-314`), the `storage` arms
  of `repo-backup.ts` and `repo-backup-list.ts`, `backup.ts:20-45` `--storage`.

### Lives, deliberately

- **`rdc storage browse`** (`storage-browser.ts:60,89`) spawns the **operator's
  own** rclone from `PATH`. Zero embedded bytes. **It is the archive read path.**
- **`storage add/remove/list/import`**, including
  `packages/shared/src/renet-contract/utils/rclone.ts` (176 lines of pure text
  parsing, zero bytes). `import` is how the OneDrive remote gets into the registry
  so `browse` can reach it. Killing it saves nothing and costs archive access.
- **`ops rustfs configure-workers`** (`pkg/infra/docker/service.go:572,677,690-705`).
  This installs rclone **on a worker VM over SSH** (`apt-get install -y rclone`).
  It never touches `embed.AssetRclone` and never calls `getRclonePath()`. Its 8
  i18n keys stay. A `grep -rl rclone | xargs` sweep would delete this by accident.
- **`backup_{list,delete,push,pull} --*-type machine`**, plain SSH + CoW delta.
  Flip their defaults from `storage` to `machine`.

### The gap this exposes, which must be closed in the same change

`backup-strategy.ts:36-55` can only create `kind: 'storage'` destinations, and
`backup-schedule-unit-generator.ts:214-218` now **throws** on exactly those. No
CLI command anywhere creates a `hosted-service` destination. So today the only
way to schedule a backup is to hand-edit config JSON. **Add `--hosted-service` to
`backup strategy set`**, or the product ships a scheduler nothing can feed.

---

## 4. Schema: retain-but-refuse, at every layer

**Keep every enum value. Refuse at the call site.** This follows the ruling
already made this session for `kind: 'backup'`
(`07-execution-record.md` §9.4): clean-break applies to code paths, not to data
already on disk.

The strongest case is `BackupDestinationSchema`
(`packages/shared/src/config-schema/schemas.ts:449-466`), and it is stronger than
the run-history case was:

```ts
kind: z.literal('storage').default('storage'),
```

That `.default` means **a legacy destination carrying no `kind` at all parses as
`storage`**. Delete the variant and the union rejects both `{kind:'storage'}` and
the kindless legacy shape; a Zod union failure fails `parseConfig`, which fails
the whole config load. **Hostinger's config carries exactly such a destination.
`rdc` would refuse to start on the operator's production machine.** That is not a
clean break, it is a brick.

The refusal already exists and is already tested
(`backup-schedule-unit-generator.ts:203-220`, `backup-ops.ts:57-68`,
`backup-cutover-preflight.sh:174-181`). **The refusal is the clean break; the
enum is the on-disk compatibility that the break does not extend to.**

Add a fixture to `packages/cli/src/utils/__tests__/config-schema.test.ts`
asserting a kindless `{name, storage, folder}` destination still parses.

Same treatment for the renet contract `sourceType`/`destinationType`: keep
`['machine','storage']`, flip the defaults, change the help text to
`"machine (SSH); storage is retired"`.

---

## 5. THE TRAP: a green build that ships the payload anyway

Three mechanisms conspire, and the tree is in the vulnerable state right now:

1. The embed directive is a **glob**: `//go:embed assets/amd64/base/*`
   (`embed_assets_amd64.go:19`).
2. Staging is **add-only**: `build.sh:215-227` does a `docker cp` per lockfile
   entry and never deletes.
3. `_embed_receipt_is_current()` (`build.sh:273-292`) checks that every asset the
   **receipt** lists exists and matches. **It has no extra-file check.**

So deleting the lockfile component rewrites the receipt without ever unlinking
the orphaned `.zst`, and the glob re-embeds it. Build green, credits gate green,
arch-parity green, **22 MB still shipped**.

The documented mitigation is worse than it looks: the payload-only planner found
that **`build.sh` has no `clean` target at all** — only `reset()` (`:550`), which
*requires `DOCKER_REGISTRY` and pushes to a registry*. It is not a local prune and
must never be recommended as one.

**`build.sh` must grow a prune step**, inserted after the lockfile-validity check
and before the receipt short-circuit, plus an extra-file arm on
`_embed_receipt_is_current` so a warm tree with an orphan reports stale rather
than being reused. Both planners derived this independently; treat it as required.

**CI is safe by construction, and the reason should be stated rather than
patched.** `ci-build-renet.yml:83-87` keys the embed cache on
`hashFiles(embed-assets.lock.json)` with **no `restore-keys`**. Deleting the
component changes the hash, so the restore is a hard miss and staging starts from
an empty directory. **Do not add a manual cache bust** — it would hide the fact
that the key already does the right job, and mask a regression if someone later
adds `restore-keys`. The prune is still required, for developer trees.

**A second, independent gap in the same machinery, found 2026-08-15 while bumping
the rsync pin.** `./build.sh embed_assets --force` does NOT rebuild the Docker
image: it builds one only `if ! docker image inspect rediacc/renet:latest`, so
`--force` forces re-extraction from a STALE image and a Dockerfile edit is
invisible to it. Proven: after bumping `ARG RSYNC_VERSION` to 3.5.0 and running
`embed_assets --force` to exit 0, the staged binary still answered
`rsync version 3.4.4`. The rebuild is a separate verb, `./build.sh docker_image`.

This matters directly here, because removing rclone edits the **Dockerfile**
(deleting the downloader stages). Sequence it as `docker_image` first, then
`embed_assets --force`, or the removal will report success with the payload
untouched -- the same false green as the glob-plus-add-only-staging trap above,
arriving by a different route.

### The only honest proof

`//go:embed` stores member paths as plaintext in the binary.

```bash
rm -rf private/renet/pkg/embed/assets/*/*/
cd private/renet && ./build.sh embed_assets --force && ./build.sh

strings -a private/bin/renet-linux-amd64 | grep -c rclone-linux   # today: 3   must be: 0
strings -a private/bin/renet-linux-arm64 | grep -c rclone-linux   # must be: 0
ls private/renet/pkg/embed/assets/*/base/                         # no rclone-*.zst
```

**Size alone proves nothing** — a stale-tree build is the same size as today's.
Wire the `strings` count into `backup-cutover-preflight.sh` so the proof becomes
a standing gate rather than a one-off.

Baselines to compare against: `renet-linux-amd64` = 258,621,624 B,
`renet-linux-arm64` = 230,752,440 B.

---

## 6. Gates that will go red, and the ones that must not be trusted

**Will go red and need real edits:**

| Gate | Where |
|---|---|
| embed-credits self-test | `.ci/scripts/test/gates/test-embed-credits.sh:33,40,49` |
| embed-asset-freshness self-test | `.ci/scripts/test/gates/test-embed-asset-freshness.sh:38,48,62` |
| freshness source table | `scripts/lib/embed-asset-sources.ts:27` |
| Go asset table tests | `pkg/embed/embed_test.go:38,87-90,168,284,384-386` |
| renet artifact upload | `ci-build-renet.yml:150`, under `if-no-files-found: error` at `:153` |
| native image build | `private/renet/Dockerfile.native:28-29,94-95,118-119,136` (unconditional `COPY`) |

**Rewrite the two gate fixtures onto a surviving asset (`zot`), do not delete the
cases** — they still guard criu/rsync/k3s/CSI.

**`knip.jsonc:174-178`: rewrite the BLOCKER, do not delete the entry.** `rclone`
remains an unlisted binary because `storage-browser.ts:60` still spawns it. Only
its justification text ("the CLI backup stack") becomes wrong.

**Gates that prove REMOVAL** (accept only these as evidence): the `strings` count
== 0; the asset directory listing; `check-embed-credits.ts` printing a component
count of 7 instead of 8; the new extra-file receipt arm.

**Gates that merely TOLERATE it** (do not accept as evidence): `go build`, the Go
asset tests, `test-embed-arch-parity.sh`, and any size measurement. All of them
pass identically on a tree where the payload was silently re-embedded.

**`check-command-tree.sh` fails OPEN when stale** (`:14-20`) and nine validators
trust its output, so regenerate the command tree, the CLI contract, and
`.claude/skills/rdc/reference.md` in the same commit as the command deletions.

---

## 7. Generated artifacts: never hand-edit

```bash
# renet contract
cd private/renet && go build -o bin/renet ./cmd/renet
./bin/renet functions generate-types --output ../../packages/shared/src/renet-contract/data \
  --version "$(git describe --tags --always)"

# CLI contract + command tree  (cli-contract/data/i18n/*.json are OUTPUTS:
# edit packages/cli/src/i18n/locales/*/cli.json instead)
npm run generate:cli-contract -w @rediacc/cli
npx tsx packages/cli/scripts/export-command-tree.ts

# credits: ONE command writes BOTH inventories
npx tsx scripts/generate-embed-credits.ts
```

`credits_data.go:49-55` and `packages/cli/src/data/third-party-credits.json:49-55`
are a pair. Regenerating one side only turns `check-embed-credits.ts` red, or
worse, leaves an attribution that no longer matches the binary.

---

## 8. Locales: ~28 keys, ~364 strings, 13 languages

CLI (`packages/cli/src/i18n/locales/<lang>/cli.json`): ~11 deletions
(`commands.storage.prune.*` ×8 and friends), ~9 rewordings, ~3 additions for
`--hosted-service`. renet Go (`pkg/i18n/locales/<lang>.go`): ~17 deletions
(`backup_sync.*` ×12, `setup.installing_rclone`, `setup.rclone_installed`, three
transfer strings). **Keep all 8 RustFS keys.**

Both catalogues are key-usage-gated, and `05:131` states the rule: **do NOT
allowlist orphans, delete keys.** English first, then all 12 others with the same
key set, then rebaseline with the tools (`npm run fix:i18n`,
`renet i18n generate-hashes`) — never by hand. Both baselines may only shrink.

Locale work is the one part to hand to writer sub-agents (Sonnet, per the model
policy), one language family each, English landed first as the reference. The
embed payload work (§5) and the schema ruling (§4) stay inline and single-threaded.

---

## 9. Risks, worst first

1. **The 500 GiB becomes unreadable.** Mitigated only by §1 step 0 being a
   blocking gate, and by `09-onedrive-archive-readback.md` landing in the same
   commit. If `/usr/local/bin/rclone` is missing on any machine, install it there
   **before** merging: the extractor is being deleted.
2. **The chunk store has never carried production data.** This is why the
   operator sequenced the whole plan behind the cutover.
3. **Narrowing `BackupDestinationSchema` bricks `rdc` on hostinger.** §4.
4. **The trap ships 22 MB anyway, green.** §5.
5. **The scheduler is left unfeedable.** §3's closing gap.
6. **`ops rustfs configure-workers` collaterally deleted** by a word-grep. §3.
7. **Submodule branch mismatch**: `private/renet` is on `backup-storage` while
   `.gitmodules:4` declares `main`. `check-submodule-branches.sh` will catch it.

Change size: **~140 files**, of which ~29 are locale catalogues and ~40 are www
docs across 13 locales.

---

## 10. Already done, do not redo

- **The restore-lie bug is fixed** (this session, uncommitted).
  `rcloneObjectExists` (`private/renet/cmd/renet/backup_pull.go`) discarded its
  error, so a machine without rclone reported **"backup `<name>` not found"** for
  data sitting intact in the bucket. Both planners independently identified this
  as blocking. It now returns `(bool, error)`, treats only an `*exec.ExitError` as
  a possible absence, and `resolveStorageObjectPath` aborts the candidate walk
  with `cannot probe storage for <name>: ...` instead of arriving at a confident
  "not found". Two regression tests in `backup_pull_probe_test.go` drive the real
  missing-binary path with an emptied `PATH`, and were **mutation-proved**: both
  fail against the old one-liner.
- **`05-docs-and-decommission.md:89` is corrected.** It justified keeping the
  payload with "repo sync, storage browse, migrate", and all three were wrong.
