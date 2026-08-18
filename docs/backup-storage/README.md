# Backup Storage: Rediacc-native chunk-store backup on S3/R2

A big-bang replacement of the rclone-to-consumer-cloud scheduled backup path with a
Rediacc-hosted (and elite-local) content-addressed chunk store: first upload full,
every later upload only changed blocks, every snapshot independently restorable,
per-subscription byte quota as the only product lever. Designed in a single
read-only discovery session on 2026-08-09 (session prefix 97604f47, branch main),
with roughly twenty parallel investigation agents whose every load-bearing claim was
verified against the live tree, live binaries, or official provider docs on that
date. Program state lives at
`~/.claude/projects/-home-muhammed-monorepo-console/programs/backup-storage/`; the
memory pointer is in the auto-memory MEMORY.md.

## READ 07 FIRST

`07-execution-record.md` is the RECORD; everything else here is the PLAN, written
2026-08-09 before any code existed. Where they disagree, 07 is right. Acting on
the plan without checking it against the tree has been wrong seven times, twice
in ways that would have deleted working code. 07 also carries the operator's
decisions, which override the scored winners below.

## Read order

0. `07-execution-record.md`: status, operator decisions, the bugs found in the
   built system, and every correction to the documents below.
1. `01-verified-context.md`: what exists today, the verified platform facts, and the
   findings ledger (about 47 defects discovered during discovery, all in-path).
2. `02-design.md`: the architecture, every scored decision with its winner, and the
   quota/lifecycle policy.
3. `03-implementation-map.md`: per-surface seams with file:line, the schema plan, the
   parity matrix source, and the traps handed over by name.
4. `04-testing-and-local-loop.md`: the three-tier battery, the local VM topology, and
   the cloud probes.
5. `05-docs-and-decommission.md`: the docs/claims reconciliation and the line-level
   decommission checklists.
6. `06-execution-guide.md`: spikes, waves, staffing, gates, definition of done.
7. `08-cutover-runbook.md`: wave 5. The credential-free half is done and the
   credentialed legs are one copy-paste block. Read §2.2 before setting any
   env var: the R2 binding decides which grant minter production gets, and only
   one of the two has ever been accepted by live R2.

## Non-negotiable working ethos

Validate, do not believe: every file:line reference in these docs is a hypothesis to
re-verify against the tree before building on it; run the real thing; read stdout and
stderr separately; plant a control before trusting any zero. Everything stays local
and uncommitted: no commit, branch, push, or PR unless the operator asks in-task;
never `git checkout/restore/stash/clean`; repair forward. Testing and concurrency
support are first-class deliverables, not afterthoughts. NO em dashes in any authored
text, in any language.

## Staffing

Opus is the default model for coding sub-agents. Fable for the challenging pieces AND
for planning agents. Sonnet for all translation/naturalization work, without
exception. At most 2 concurrent writers, each with disjoint file ownership stated
verbatim in its prompt; investigation agents fan out freely; every sub-agent report
is spot-checked against the artifacts before anything builds on it.

Fable-tier pieces of this program:
- The renet chunk engine (`pkg/chunkstore`): anchor-trust discipline, manifest
  correctness, and the grid/hashing core. A plausible-but-wrong manifest uploads
  cleanly and fails only at restore.
- The control-plane grant signing (locally-signed R2 temp credentials with an
  `actions` allowlist) and the ledger/pin/lease transactionality that closes the
  GC-versus-dedup race.
- All planning agents.

## Scope

- [ ] Wave 0: probes, instruments, and in-path defect fixes (btrfs test tier wiring,
      churn instrumentation, cron seam revival, restore-credential fix, cloud probes,
      bench bucket; operator legs included).
- [ ] Wave 1: renet chunk engine and account control plane, two parallel writers with
      disjoint submodule ownership.
- [ ] Wave 2: CLI/schema surfaces and portal quota UI, two parallel writers.
- [ ] Wave 3: test battery: account vitest suites plus `scripts/drills/backup.sh` in
      one writer, e2e byte-verify battery in the other.
- [ ] Wave 4: English docs and claims reconciliation (Opus), then the 12-locale
      translation pass (Sonnet), tutorial re-record only if commands changed.
- [ ] Wave 5: integration, parallel-run on real machines (hostinger first), verified
      restores, deploy in the pinned order (account, then renet, then CLI), OneDrive
      decommission with a date, old-path code deletion.

**Explicitly OUT** (do not creep):
- Whole-cluster atomic backup (rbd group snap + export-diff): named follow-up shared
  with cross-site cluster migrate; v1 restores are per-repo crash-consistent, not
  cross-repo coordinated, and the docs must say so.
- `storage browse`: the customer-rclone-remote READ surface stays exactly as it
  is. (Note it shells out to an `rclone` on the operator's PATH; the embedded
  copy went with the retirement, and `storage-browser.ts` says so on ENOENT.)
- ADDITION 2026-08-16: `rdc backup browse` is IN, and is a different noun from
  the line above. Retiring the rclone arm took `storage browse` off the backup
  path and left no way to ask what a backup contains. That listing cannot be
  served from the chunk store at any cost — the manifest maps grid cells to the
  SHA-256 of their CIPHERTEXT and carries no filesystem data — so it comes from
  opening the repository image read-only and walking it. Local, no server, no
  network, no credentials. Two design agents on opposite angles converged on
  this shape, including the server-first one arguing against its own angle
  (a server-side plaintext table of contents is a zero-knowledge regression).
  Synthesis and the staged plan for remote browse:
  `agent/PLAN-chunk-store-browse-DECISION.md`.
- CORRECTION 2026-08-16: `rdc repo push/pull --to/--from <storage>` did NOT stay.
  Both now refuse a storage destination (`packages/cli/src/commands/repo-backup.ts:183`)
  and name the chunk store instead. Only the machine form survives. This line
  originally declared the whole surface out of scope; half of it moved.
- Customer-supplied S3 as a backup target (future, via the presigned grant type).
- Infrequent Access storage class: post-launch flag, pending GA confirmation.
- Purchasable quota upgrades: the Stripe seam is mapped, the feature is not built.
- Continuous data protection / sub-minute replication claims: not this system.

## Operator decision points (ask EARLY, in one round)

1. Elite production storage backend. RECOMMENDED: filesystem-backed chunk routes in
   the elite hono server (no third-party system of record; RustFS stays dev/CI
   only). Alternative: pinned RustFS behind the conformance probe suite, which gets
   built either way.
2. Snapshot cadence default. RECOMMENDED: measure churn first (wave 0 instrument),
   then 1h default with 5-minute per-repo opt-in. Do not hardcode 5 minutes.
3. Retention-on-cancel. RECOMMENDED: retain read-only 60 days after subscription end
   (the number repo licenses already use), then sweep; refunds freeze, never delete.
4. Mixed-CLI-version safety. RECOMMENDED: update every rdc install before any new
   config field is written (sole-operator step); optionally bump schemaVersion to 4
   so an old CLI fails loudly instead of silently stripping nested fields.
5. Edge-channel doubling of storageQuotaBytes. RECOMMENDED: no (doubling free
   storage is a real R2 bill; the doubling mechanism is per-field and opt-in).
6. Tutorial re-record scope. RECOMMENDED: keep the existing cast (its seven commands
   all survive); re-record only if wave 2 changes their argv.
7. Campaign packaging: branch/worktree per repo, and whether waves land as PRs or as
   uncommitted trees until told otherwise. Operator call before wave 1.
8. Product naming of the feature in docs/marketing. Operator call before wave 4.
