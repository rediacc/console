# PLAN: one backup program: S3/R2 chunk store only, safe restores and retention, GUID-only repo identity, clean renet daemons, an offline plane, gated tests, and a live cutover of hostinger to rediacc-backups-eu

Status: approved -- operator 2026-10-15 ("make a new plan file with boxes", "last steps should be real backup from hostinger to eu R2"); in ## Generated, promoted later by the operator
Depends-On: PLAN-shell-sandbox-readonly-view.md, PLAN-account-vm-check.md
Supersedes: agent/plans/PLAN-rclone-decommission.md, agent/plans/PLAN-cold-path.md, agent/plans/PLAN-backup-quota-delta-gc.md, agent/plans/PLAN-add-chunkstore-backup-verb.md, agent/plans/PLAN-backup-restore-target-license.md, agent/plans/PLAN-testing-surface-audit.md, agent/plans/PLAN-chunk-store-browse-toc-and-remote.md
Priority: P1 -- hostinger has had no backup since 2026-08-14, and a restore can overwrite its own source
Concurrency: parallel -- operator /ask 2026-10-23 ("Parallel, per-phase Owns"): writers take disjoint per-phase Owns declared on their spawn (account backup services; renet chunkstore and restore; renet daemons; CLI backup), and phases touching files other live plans hold (account types/env.ts, drizzle/meta, CLI locales, gates.lock, renet pkg/i18n) wait for those plans
Owns: private/renet/**, private/account/**, private/elite/**, packages/cli/src/**, packages/shared/src/**, packages/e2e-tests/**, packages/www/src/content/**, workers/account/**, .ci/rediacc_ci/**, .ci/scripts/quality/**, .ci/config/**, .claude/rediacc_hooks/**, .claude/skills/**, .claude/agents/backup-storage.md, scripts/gates/**, docs/backup-storage/**, docs/design/**, .github/workflows/**
Owner: 5cc33087
First-Seen: 2026-10-15

## Why

Backups stopped on 2026-08-14. The rclone path was removed (docs/backup-storage/CHECKLIST.md w9) before machines were cut over to the chunk store (w8, never done). No timer was left on hostinger, and every regional R2 backup bucket is empty. The engine itself is sound: a fixed 4 MiB grid over LUKS ciphertext, FIEMAP deltas, dedup by sha256, and tested restore. What is broken or missing sits around it: scheduling, retention, repo identity, daemon lifecycle, the offline plane, gating, and the cutover itself. There is one operator and no customer, so every fix is a clean break, with no migration commands, fallbacks or dual paths.

Done before this plan (2026-10-15, not repeated here):
- R2 buckets rediacc, edge-rediacc-configs and rediacc-backups-probe deleted
- BACKUP_S3_* removed from the six regional account workers
- BWS R2_TOKEN_AUTH_API deleted
- hostinger: rclone and 16 old renet slots removed
- eu-remote config: r2-cloudflare storage, the microsoft (OneDrive) storage, both legacy strategies (twiceweekly-hot, weekly-cold) and my-server removed; the config holds no storage and no strategy now

## Operating context (read this first)

**The production config is `eu-remote`.** It is a named rdc config whose content lives in the encrypted remote config storage of the EU account server (https://eu.rediacc.com). The local file `~/.config/rediacc/eu-remote.json` is only a cache. Never use the default `rediacc` or `dev` configs for production work, and never use `~/.config/rediacc.quarantine/` (an untrusted downloaded copy).

- Every production command carries `--config eu-remote`, run through the repo wrapper: `./rdc.sh <command> --config eu-remote`. Bare `./rdc.sh` builds the CLI from this tree and targets production; `./rdc.sh --dev` targets the local dev account server instead.
- Check the link first: `./rdc.sh config remote status --config eu-remote` must say `connected`; `./rdc.sh config remote refresh --config eu-remote` pulls the newest version.
- If the login token has expired: `./rdc.sh subscription login --server https://eu.rediacc.com --config eu-remote` prints an authorize URL the operator opens. If the remote link itself is lost: `./rdc.sh config remote enable --api-url https://eu.rediacc.com --config eu-remote` prints a portal link plus a pairing code; the operator approves it in a browser (2FA).
- Machines: `./rdc.sh machine list --config eu-remote` shows `hostinger` (the only production machine; user `muhammed`, datastore `/mnt/rediacc`, Ubuntu 24.04, about 50 GB free in the datastore). The address comes from that command; it is not written here.
- Repos on hostinger (all grand repos, none forked): demo-stackoverflow 128 GB, miscellaneous 48 GB, hermes 32 GB (100% full), nextcloud 26 GB, erpnext 20 GB, marketing 16 GB, observability 16 GB, gitlab 14 GB, mautic 8 GB, mail 4 GB, demo-heartbeat 2 GB (unmounted, no Rediaccfile). Routes are `https://*.<repo>.hostinger.rediacc.io`.
- Reading state is always allowed: `./rdc.sh machine status hostinger --config eu-remote` (add `--repositories`, `--containers`, `--licenses`, `--storage-health`; add `-o json` and parse stdout only, since build noise goes to stderr).
- Grand repos are guarded: an agent cannot open a shell inside one (`term connect <repo>`) or change it unless the operator starts the session with `REDIACC_ALLOW_GRAND_REPO=<repo>` (or `*`). The normal path is fork first (`./rdc.sh repo fork <repo> --tag <tag> --config eu-remote`) and work on `<repo>:<tag>`.
- A machine-level shell is `./rdc.sh term connect hostinger --config eu-remote -c '<cmd>'` (sudo is available as `sudo -n`). The CLI refuses machine commands that mention `docker` or a repo mount path even when they only read (C7/C8); a read that needs one of those waits for C7/C8 rather than spelling around the guard.
- `machine setup hostinger` uploads this tree's renet and restarts rediacc-router; the operator approved running it. It does not restart the hub, plugins or per-repo supervisors (Phase C).
- Cloudflare, R2 and secrets: see "Credentials and live validation" below.
- Buckets: stable `rediacc-backups-{eu,us,asia}`, edge `edge-rediacc-backups-{eu,us,asia}` (both EU ones in the EU jurisdiction), bound as `BACKUP_BUCKET` to the workers `rediacc-account-{eu,us,asia}` and `edge-rediacc-account-{eu,us,asia}`. hostinger's repo licences come from the stable EU server, so its backups land in `rediacc-backups-eu`. On 2026-10-15 every backup bucket was empty.
- Dev and test machines are the local KVM VMs from `./rdc.sh ops up` (192.168.111.*), used with `./rdc.sh --dev`; they are dev-only and never added to `eu-remote`.
- hostinger state on 2026-10-15: renet updated by `machine setup`, but 21 renet processes (hub, 10 plugins, 10 per-repo supervisors) still run the replaced binary until Phase C restarts them; no backup timer exists.

## Credentials and live validation (tools and concepts; no secret is written here)

Every live claim in this plan (bucket contents, worker bindings, token scopes, portal health) can be checked from this host. The rule that keeps it safe: a secret goes from Bitwarden into an environment variable inside one script and is never echoed, logged, written to a file or passed on a command line that shows up in `ps`.

- **Bitwarden Secrets Manager (bws), not the Bitwarden password manager (bw).** The CLI is `~/.local/bin/bws`; the machine-account token is the file `~/.config/rediacc/bws-access-token` (mode 0600). Export it as `BWS_ACCESS_TOKEN` for the one command that needs it.
- **Names first, values only in memory.** `bws secret list -o json` prints every secret's `value` alongside its `key`, `note` and `id`, so it never runs bare: pipe it straight into a projection that keeps only names and notes (`bws secret list -o json | jq -r '.[] | [.key, .note] | @tsv'`, or the projection `scripts/ops/bws-map-refresh.py` already does), and read a `value` only inside the script that uses it. `.ci/config/bws-secret-map.json` and `.ci/config/secret-supply.json` say which repo code reads which name.
- **Repo wrapper.** `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile <profile> -- <command>` runs a command with a named profile's secrets exported (profiles are in secret-supply.json: deploy-workers, deploy-bench, rotation and others). There is no all-secrets mode by design; M1 adds a tracked profile for account worker secrets.
- **Names used for live checks:** `CF_EMAIL` and `CF_GLOBAL_API_KEY` (Cloudflare API, sent as the `X-Auth-Email` and `X-Auth-Key` headers), `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` (the deploy token), `ACCOUNT_BACKUP_S3_ENDPOINT`, `ACCOUNT_BACKUP_S3_ACCESS_KEY_ID` and `ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY` (the backup plane's S3 credential; S1 splits it per environment).
- **Cloudflare REST calls that answer this plan's questions** (base `https://api.cloudflare.com/client/v4/accounts/<account id>`):
  - `GET /r2/buckets` lists buckets. EU-jurisdiction buckets appear only with the header `cf-r2-jurisdiction: eu`, which every object or bucket call on them also needs.
  - `GET /r2/buckets/<bucket>/objects?per_page=1000` (paginate with `cursor`) counts objects and bytes; `DELETE .../objects/<key>` and `DELETE /r2/buckets/<bucket>` remove them.
  - `GET /r2/buckets/<bucket>/domains/managed`, `/domains/custom` and `/cors` show whether a bucket is publicly reachable (all off on 2026-10-15).
  - `GET /workers/scripts` lists workers; `GET /workers/scripts/<worker>/settings` lists bindings, which show secret names and R2 bucket bindings but never secret values; `/deployments` and `/versions/<id>` give rollback points.
  - `DELETE /workers/scripts/<worker>/secrets/<name>` removes a worker secret and keeps the ASSETS binding (measured 2026-10-15); `wrangler secret put` mints a version that can detach static assets.
  - An R2 S3 access key id is the id of a Cloudflare API token, so `GET /tokens/<access key id>` returns that token's name, status and policies, which is how a credential's real scope is read without touching its secret.
- **Health probe after any worker change:** `https://<host>/account/login` and its first `/account/assets/*.js` return 200, and `https://<host>/account/api/v1/health` returns 200. The hosts are eu.rediacc.com, us.rediacc.com, asia.rediacc.com, edge-eu, edge-us and edge-asia under rediacc.com, and bench.rediacc.com. A CDN cache HIT proves nothing about a new version; read the version's bindings instead.
- **Ask before** rotating or revoking a token or deleting a non-empty bucket. Worker deploys and secret changes go ahead without asking (no active users), each with its rollback version id recorded.

## Known defects (each maps to the box that fixes it)

| Defect | Evidence | Box |
|---|---|---|
| A restore reuses the source GUID and renames over an unmounted source image | private/renet/cmd/renet/backup_restore.go:259-305, packages/cli/src/commands/backup.ts:166-170 | E1, K5 |
| Retention keep set and newest-kept floor are per lineage, so forks or a second machine prune another stream | backup-gc.service.ts retentionKeepSet | E2, K3 |
| Commit accepts a missing or foreign parent; restore fails later | backup-storage.service.ts commitManifest | E3 |
| `restore --at` picks another fork's or machine's snapshot | the unscoped lineage pick in packages/cli/src/commands/backup.ts before b8fa5ef7e (E4); E4 scoped it to the stream at packages/cli/src/commands/backup.ts:337-352 | E4 |
| A first seed runs on the 30 s I/O budget | private/renet/cmd/renet/functions_commands.go:902 | E5 |
| No default retention; strategy.retention is never sent | packages/shared/src/config-schema/schemas.ts:482-499 | F2, F4, A8 |
| Schedules pass repo names to the GUID-only `--repo`, and refuse `exclude` | packages/cli/src/services/backup/backup-schedule-unit-generator.ts:136-161 | G1, G9 |
| `backup status` says idle with no timer; nothing warns on stale backups | live hostinger, 2026-10-15 | G6, G7 |
| `IsDockerRunning` reads the dead plugin's PID file | private/renet/pkg/orchestration/orchestrator.go:98-104 | B1 |
| `daemon cleanup-ips` treats every live service IP as unused | private/renet/pkg/daemon/loopback.go:388 | B2 |
| Hub, plugins and supervisors keep running a replaced binary; old renet slots pile up and are globbed as fallbacks | live hostinger; private/renet/pkg/config/constants.go:281 | C1-C6 |
| State-mirror records stay 0600 after an upgrade, so every repo shell fails | live hostinger, 2026-10-15 | C10 |
| renet's real error is reduced to "SSH exited with code 1, Generic error" | live `term connect hermes` | C11 |
| A newer CLI passes flags an older remote renet refuses on read-only paths | live `term connect` (`unknown flag: --datastore`) | C12 |
| Machine commands that only mention docker or a mount path are refused | live `term connect hostinger` | C7, C8 |
| Unresolved repos widen to the whole datastore; names fall back to raw keys | private/renet/pkg/functions/commands/backup.go:603 | D1-D4 |
| Offline plane: region fixed, presign host internal, partial env silent | private/account/src/services/backup-chunk-store.ts:171-187 | I1-I6 |
| The released CLI cannot read a config the dev CLI enrolled | live, rdc 1.3.12 against eu-remote | R1 |
| The remote config version climbs without a deliberate write | live, version 5 to 15 on 2026-10-15 | R2 |
| The server counts 0 valid licences of 35 while hostinger reports 11 valid | live `subscription status` vs `machine status --licenses` | R3 |
| hermes is 100% full | live `machine status --storage-health` | R4 |
| Config blob keys carry no store id, so one org can delete another org's configs | private/account/src/services/config.service.ts:2681-2698 | S1 (fixed by another session) |
| An account-wide R2 key can reach bench; one backup key serves stable, edge and bench | .ci/rediacc_ci/ops/deploy_bench.py:76-90 | S1 (fixed by another session) |
| A licence never expires as a backup credential, and the machineId check trusts the client | private/account/src/services/repo-license-verify.service.ts:79 | S2 |
| A backup session reaches every lineage of the subscription, not only its own repo | private/account/src/services/backup-storage.service.ts:187-195 | S3 |
| Team-scoped tokens can read and prune other teams' backups | private/account/src/routes/backups.ts:126-208 | S4 |
| Presigned PUTs carry no size or checksum; billing trusts client numbers | private/account/src/services/backup-chunk-store.ts:826 | S5 |
| One tenant can stall maintenance for all | private/account/src/services/backup-gc.service.ts:129-150 | S6 |
| Executor tokens can be minted as any team member and can write | private/account/src/routes/configs.ts:837-892 | S7 |
| Chunk-store Go tests are never run before a push; suite 26 never runs in CI | .ci/rediacc_ci/proxies/go_unit.py:26 | J1-J6 |

## Design notes

- Identity: renet takes GUIDs only. The CLI resolves name[:tag] to repositoryGuid from its config. An unresolved value is an error, never a pass-through or a widening.
- Destinations: one kind, S3-compatible. The hosted account server is the default; a self-hosted account server points at any S3 endpoint. The storage kind, the storages registry and every rclone path are deleted, and a config carrying them fails to load with a message naming the removed field.
- Retention: count-based buckets (already safe when backups stop), plus a hard per-stream floor (newest 3 and the stream's anchor), a server default when no policy exists, per-plan defaults and limits, and the strategy declaring its policy.
- Restore: never reuses a live GUID on the same datastore. It writes a journal and anchor, and can seed from a local CoW copy, fetching only the cells that differ.
- Daemons: renet plugin is deleted. Hub and per-repo supervisors get a rolling, health-checked restart after every upload, and stale binaries are surfaced in machine status.
- Proof order: unit tests, then account vitest, then the RustFS drill, then local VMs with the account gateway, then suite 26 in CI, and only then stable EU and hostinger.

## Tasks

### Phase A: records, folds and doc truth

- [x] A1: Mark docs/backup-storage/CHECKLIST.md superseded by this plan; carry w8 and the w3/w4/w5 leftovers (preview smoke, e2e corruption-injection control, suite 26 never run, stale locales) into boxes here. Owns: docs/backup-storage/CHECKLIST.md. Accept: header line names this plan; check:ci-plan-citations rc=0.
    (ticked) 2026-10-23T07:36:27Z by d778be9d: commit:ee2ac7589 CHECKLIST.md line 2 names this plan; leftovers carried as A1a, A1b, K11a and Q0 (w8 cutover is Phase Q, suite 26 is J6); check:ci-plan-citations rc=0
- [ ] A1a: Preview smoke for the portal quota page: run `stepQuotaPageShipped` (.ci/scripts/test/smoke-test-preview.ts, asserting the served bundle carries the `backup-storage` route) against a real preview deployment; carried from CHECKLIST w3. Accept: a green deploy-preview run id recorded here.
- [x] A1b: Locale freshness for the chunk-restore and quota docs (backup-restore.md, limits.md): the 12 non-English locales re-translated by delta and the hashes regenerated; carried from CHECKLIST w5. Accept: validate-translation-freshness rc=0 and check:i18n rc=0.
    (ticked) 2026-10-24T10:25:21Z by d778be9d: commit:71bf8902e no locale edit needed: validate-translation-freshness --strict-all rc=0 (all 12 locales incl. backup-restore.md, limits.md) and check:i18n rc=0 on 2026-10-24; CHECKLIST w5 note corrected
- [x] A2: After PR #600 merges, fold PLAN-chunk-store-browse-toc-and-remote.md: copy its 11 boxes verbatim into Phase O, leave a Status: moved + Moved-To: stub, run check_plan_boxes.py --update in the same commit. Accept: check:ci-plan-boxes rc=0, G-A1 finds every signature.
    (ticked) 2026-10-23T07:55:36Z by d778be9d: plan:agent/plans/_done/PLAN-chunk-store-browse-toc-and-remote.md closed instead of folded, operator /ask 2026-10-23 ("Close into _done, tick A2"): its 11 boxes were all ticked (last in d96400c32) and validated on renet, account and console main
- [ ] A3: Fold PLAN-renet-fetch-hardening.md site 6 (ensureRclone retry) as obsolete once H8 deletes ensureRclone; tick it there with the commit sha. Accept: plan-boxes ledger shows the box done.
- [x] A4: Give fresh boxes (cited, not edited) to the leftovers of compacted records: rclone-decommission (re-embed gate, storage prune), cold-path T3, backup-quota-delta-gc leg l and retention push, add-chunkstore-backup-verb I/O budget, backup-restore-target-license e2e, testing-surface-audit F1-F10 re-verified. Accept: each leftover maps to a box id below.
    (ticked) 2026-10-24T10:35:35Z by d778be9d: mapped 2026-10-24: re-embed H15, storage prune H1, cold-path T3 K6, delta-gc leg l J8, retention push F4, I/O budget E5, restore-target-license K12/A7, audit F1 J8, audit F5 btrfs-tier half J9, audit items F2/F3/F5/F8/F10-artifacts landed; unbuilt audit items F4, F6, F7 and F10-probe carried as new boxes A4a-A4d (not the retention-push box F4), mapping table A4e; check:ci-plan-boxes and check:ci-plan-citations rc=0
- [x] A4a: Testing-surface-audit F4 (re-verified 2026-10-24: `packages/e2e-tests/tests/ops-lifecycle/18-ops-lifecycle.test.ts` is still in the base config's testIgnore, packages/e2e-tests/playwright.config.ts:30, and no playwright*.config.ts selects it): extend scripts/gates/check-e2e-skip-hygiene.ts with a second direction, every `*.test.ts` under tests/ selected by a config or named in a parsed deliberate-omission list. Accept: the gate reports ops-lifecycle on the current tree before the fix, a planted `tests/nowhere/99-x.test.ts` fixture exits non-zero, then green.
    (ticked) 2026-10-24T10:57:16Z by d778be9d: commit:4754890bc gate reports an unselected test (planted tests/ceph/99-x.test.ts rc=1, ops-lifecycle without its omission entry rc=1), tree rc=0
- [x] A4b: Testing-surface-audit F6 (re-verified 2026-10-24: .ci/rediacc_ci/quality/mutate_check.py exists, scripts/ci-runner/manifest.ts GateSpec carries no `mutation` field and only check:ci-mutate-check and check:ci-guard-mutations use the instrument): a `mutation` entry on the backup gates (check-no-client-key-composition, check-backup-protocol-conformance, check-backup-manifest-shape-parity, check-retention-knob-parity), run by a gate that requires RED then GREEN. Accept: a mutant the gate cannot see makes the new gate fail.
    (ticked) 2026-10-24T11:25:46Z by d778be9d: commit:8d692e44e check:ci-gate-mutations rc=0: 4 backup gates red on their planted defect and green on the tree, 0 unseen; selftest 21 controls rc=0; wired via gate-bind (parity, reachability rc=0)
- [x] A4c: Testing-surface-audit F7 (re-verified 2026-10-24: package.json:283 `check:ci-account-no-admin-role` and :287 `check:ci-account-no-node-env-routes` are still inline `! grep ... 2>/dev/null` one-liners that pass on a missing path): replace them with scripts that fail on a missing target and parse the enum array. Accept: tests with the single-line plant, the wrapped plant and a clean tree.
    (ticked) 2026-10-24T11:33:23Z by d778be9d: commit:5fe6ca54a both gates rc=0 with selftests; wrapped, bracket and missing-input plants rc=1
- [ ] A4d: Testing-surface-audit F10 third item (re-verified 2026-10-24: private/elite/scripts/s3-conformance-probe.sh exists and no workflow, script or gate calls it; the drill-backup.log artifact and the `renet` drills scope, .ci/scripts/ci/scope-map.cjs:244, already landed): call the probe from the job that starts elite. Accept: a non-conformant stub makes it red. Needs a CI run, so it is not a local-only box.
- [x] A4e: Map table, the rest of A4's leftovers to existing boxes (re-verified 2026-10-24): rclone-decommission re-embed gate = H15, storage prune = H1; cold-path T3 = K6; backup-quota-delta-gc leg l = J8, retention push = box F4; add-chunkstore-backup-verb I/O budget = E5; backup-restore-target-license e2e = K12 and its stale comment (private/renet/cmd/renet/backup_restore.go:359-360) = A7; testing-surface-audit F1 = J8, F5 btrfs-tier half = J9 (ct-tests.yml has no btrfs-progs), F2 and F3 DONE (packages/cli/src/commands/__tests__/backup-storage.test.ts `backup retention`, backup-restore-at.test.ts), F5 provisioning and e2e-unit half DONE (check:test-provisioning, check:test-e2e-unit in package.json), F8 DONE (.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py), audit F4, F6, F7 and F10 = A4a to A4d. Accept: every leftover above names a box id.
    (ticked) 2026-10-24T11:06:54Z by d778be9d: verified 2026-10-24, no change needed: every leftover in the A4e table names an existing box id; cited tests and gates exist and rc=0 (backup-storage.test.ts, backup-restore-at.test.ts 20 tests, check:test-provisioning, check:test-e2e-unit, check:ci-plan-record)
- [x] A5: Add Supersedes: lines for the folded plans; re-render QUEUE.md and agent/INDEX.md. Accept: check:ci-plan-record rc=0.
    (ticked) 2026-10-24T12:17:10Z by d778be9d: commit:ba8c6b102 Supersedes: names rclone-decommission, cold-path, backup-quota-delta-gc, add-chunkstore-backup-verb, backup-restore-target-license, testing-surface-audit, chunk-store-browse-toc-and-remote; check:ci-plan-record rc=0
- [x] A6: Archive docs/backup-storage README, PROMPT and 01-06 into an archive folder, and update every citer (private/account/src/services/backup-chunk-store.ts:806,981, private/account/src/services/backup-storage.service.ts:3, .ci/rediacc_ci/ops/backup_cutover_preflight.py:98, .claude/agents/backup-storage.md, the prose-style and account-env baselines, agent/INDEX.md); keep 07, 08 and 09. Accept: no dangling citation in the grep of the old paths.
    (ticked) 2026-10-24T12:13:31Z by d778be9d: commit:4cf136ba5 superseded docs under docs/backup-storage/archive/, every citer repointed, no old-path hit outside reviews and ledgers; check:ci-plan-record rc=0
- [x] A7: Fix the stale comments: private/account/src/services/backup-chunk-store.ts:955-958 (says JWT, the code presigns), private/account/src/entry/cloudflare.ts:90-97 (an unreachable error path), private/renet/cmd/renet/backup_snapshot.go:32-35 (says restore doesn't exist), private/renet/cmd/renet/backup_restore.go:359-360, and 07-execution-record.md §4 and §9.7. Accept: each line states what the code does.
    (ticked) 2026-10-24T12:51:30Z by d778be9d: commit:59cd1a554 (account d76e9f5): presign doc; the BACKUP_BUCKET warning now reachable on a null grant minter with 3 tests; record sections 4 and 9.7 match the code; renet comments already fixed by 02aadac and fb48c98
- [ ] A8: Correct the pricing catalog's scheduledBackups text (private/account/src/pricing/catalog.default.ts:163-169) once F2 ships the default retention, so the promise matches behaviour. Accept: the text names the default policy.
- [ ] A9: Update .claude/agents/backup-storage.md and .claude/skills/rdc/backup.md to the final verbs and flags of this program (regenerated reference.md, not hand edits). Accept: skill regeneration rc=0.
- [x] A10: Verify the other session's cleanup landed: PLAN-rdc-readonly-mode in _done/, worklist #fcd7316f closed, no R2_TOKEN_AUTH_API / BACKUP_S3_ / rediacc-backups-probe / edge-rediacc-configs reference left in tracked code outside agent/, and the two new gates exist. Accept: git grep empty; gates listed in gates.lock.json.
    (ticked) 2026-10-24T12:29:03Z by d778be9d: commit:4c048114b verified 2026-10-24: rdc-readonly-mode in _done (stub moved), #fcd7316f closed, check:ci-retired-terms and check:ci-account-env-retired rc=0 and both in gates.lock.json; the gate regexes over the submodules found two stale account references, fixed in account 645a233/3f3f4b3; private/elite/docker-compose.yml:43-44 keep the rename history deliberately (submodule scope tracked as #2f9533de)

### Phase B: delete renet plugin and fix what secretly depends on it

- [ ] B1: Rewrite Orchestrator.IsDockerRunning and GetStatus (private/renet/pkg/orchestration/orchestrator.go:98-104,132-138) to probe dockerd itself (unit active and the socket answering), no PID file. Owns: pkg/orchestration/orchestrator.go, its test. Accept: tests for down-while-running, delete-guard and merge-quiesce pass.
- [ ] B2: Fix CleanupAllUnusedIPs (private/renet/pkg/daemon/loopback.go:388) to take used IPs from container labels over the repo's docker socket (rediacc.service_ip) or .rediacc.json, never ipam-state.json. Accept: a test with live service IPs removes none of them; it fails on today's code.
- [ ] B3: Fix ListIPAllocations/getContainerIPs (private/renet/pkg/daemon/ips.go:40,86), which opens the plugin socket as if it were the Docker API. Accept: unit test against a fake docker socket.
- [ ] B4: Delete pkg/network, pkg/ipam, runPlugin and the plugin command tree (private/renet/cmd/renet/main.go:98-140,519,592-700,856-927), the go-plugins-helpers dependency, and pkg/daemon start/control/stop/status/pid (and their windows variants). Accept: go build ./... for linux, darwin and windows; go vet rc=0.
- [ ] B5: Remove StartDaemon/StopDaemon calls from workflows.go (106,360-385,853,933-943,975-987), lifecycle_commands.go, daemon_commands.go, uninstall_command.go, and the --plugins-only flag and plugin_running field. Accept: grep for StartDaemon( empty.
- [ ] B6: Point renet status and uninstall network discovery at systemd units and sockets (GetConfiguredNetworks/GetRunningNetworks); fix the uninstall socket glob. Accept: test with two configured networks.
- [ ] B7: Delete the plugin_start/stop/status bridge functions (private/renet/pkg/functions/commands/daemon.go:92-120,390-460) and their tiers (private/renet/pkg/license/tiermap.go:194-196); regenerate packages/shared functions.generated.ts and license-tiers.generated.ts. Accept: tiermap completeness tests and contract regeneration rc=0.
- [ ] B8: Remove about 28 plugin i18n keys across 13 locales plus hashes.json, and fix the help text that says "Start IPAM/network plugins" (repository_create/mount/unmount/delete/autostart, repository.go). Accept: .ci/scripts/quality/i18n.sh rc=0.
- [ ] B9: Remove dead residue: Wrapper.networkName, the DOCKER_PLUGIN_DIR .envrc export, daemon-setup/daemon.json.template, and README / BASH_TO_GO_REWRITE_PLAN.md plugin text. Accept: grep rediacc-net empty outside history.
- [ ] B10: Update or delete the Go and Python tests that pin the plugin (driver_test, ipam driver_test, daemon status/output/pid tests, test_daemon_lifecycle.py, test_full_stack.py). Accept: renet run-tests.sh rc=0.
- [ ] B11: One-release live cleanup inside renet setup: for each /var/run/renet-N.pid whose cmdline is `renet plugin`, SIGTERM it; remove /run/docker/plugins/rediacc-*.sock, docker-N/{network,ipam} and plugins.log; refuse loudly if any network uses the drivers. Accept: an ops VM run shows the plugins gone and containers still running.

### Phase C: daemons follow the binary

- [ ] C1: Add `renet daemons upgrade --json`: find renet processes whose /proc/<pid>/exe is (deleted) or differs from current; restart hub units one at a time with a /health poll; report per-repo supervisors without restarting them unless --include-docker. Accept: unit test over a fake /proc; ops VM run restarts the hub with no container restart.
- [ ] C2: The provisioner runs `daemons upgrade` after every binary update (packages/cli/src/services/renet/renet-provisioner.ts:316-319,538-548), alongside the router restart, and prints what it restarted and what is still stale. Accept: CLI test; a live setup on an ops VM leaves no (deleted) hub.
- [ ] C3: `rdc machine restart-services <m> [--include-docker]`, a rolling restart with per-repo health checks; with --include-docker it restarts rediacc-docker-N one repo at a time. Accept: e2e on an ops VM; containers come back healthy.
- [ ] C4: machine status and health report stale_binary per process (pid, unit, exe target); health exits 1 when any is stale. Accept: CLI test plus a live read against an ops VM.
- [ ] C5: Slot pruning: the provisioner's flock'd install keeps current plus the 2 previous slots and removes the rest; stop globbing old slots into RenetSearchPaths (private/renet/pkg/config/constants.go:281). Accept: test with 5 slots leaves 3; renet resolves only current.
- [ ] C6: Every spawner resolves `current`, not os.Executable(): audit private/renet/cmd/renet/sandbox_overlay_linux.go:96, private/renet/pkg/functions/executor_ssh.go:496, private/renet/pkg/infra/worker/service.go:227, private/renet/pkg/infra/bridgesvc/service.go:113. Accept: grep for os.Executable() in spawn paths is empty or justified.
- [x] C7: Fix the term connect keyword guard: a machine-level command that only names a unit or path containing "docker" (systemctl list-units rediacc-docker-*, find -path /var/lib/docker) is not a docker client call. Detect real docker invocations only. Accept: tests for both false positives and a real `docker ps` still refused.
    (ticked) 2026-10-24T14:16:20Z by d778be9d: commit:60bea783e commit:a8f8c9af2 docker matched only as a whole word or command basename; systemctl/find/ls false positives admitted, docker ps refused; vitest repo-context-guard 136 passed rc=0
- [x] C8: Fix the repo-mount-path guard false positive the same way (a read of /mnt/rediacc/mounts/<guid> metadata is allowed); keep refusing commands that need DOCKER_HOST. Accept: tests.
    (ticked) 2026-10-24T14:16:20Z by d778be9d: commit:60bea783e mount metadata reads admitted, a docker call on the mount and DOCKER_HOST still refused; vitest rc=0
- [ ] C9: Fix the hub X-Rediacc-Repo marker so it records the GUID (systemd_install_hub.service.tmpl:4, private/renet/cmd/renet/main.go:1184-1187) and systemd_installed is detected. Accept: list test with a named hub repo.
- [ ] C10: Verify the state-mirror fix handed to another session on 2026-10-15 landed: `renet setup` rewrites every existing `<datastore>/.interim/state/*/.rediacc.json` to 0644 (regular files only, no symlink following), and writeForkMirror writes a readable record. Add the missing half if either is absent. Accept: tests for both; on an ops VM, a pre-fix 0600 record becomes 0644 after `machine setup` and `term connect <repo>` works.
- [ ] C11: Carry renet's own error into the CLI result: when a remote renet exits non-zero, its stderr message becomes the JSON `errors[].message` instead of "SSH exited with code 1, Generic error". Accept: CLI test with a fake remote; live `term connect` against a planted failure shows renet's text.
- [ ] C12: Version skew on read-only paths: a forced-command or read-only call that would pass a flag the remote renet does not know answers "renet on <machine> is older than this CLI; run machine setup" before running anything. Accept: test with an old renet binary on an ops VM.

### Phase D: GUID-only repo identity

- [ ] D1: renet registry: RequireRepository and ResolveRepositoryGUID (private/renet/pkg/functions/commands/registry.go:35-43,194-204) error on any value that is not GUID-shaped and not mapped; never a pass-through or "". Accept: tests for unmapped name, mapped name and GUID.
- [ ] D2: private/renet/pkg/functions/commands/backup.go:603,639-642,683: an unresolved repo is an error, never a widening to the whole datastore or a raw-name fallback. Accept: test that fails on today's code.
- [ ] D3: private/renet/pkg/functions/provider/vault_provider.go:289-295: no credential lookup by raw key. Update private/renet/pkg/functions/provider/provider_test.go:58-110 to map the GUID. Accept: go test rc=0.
- [ ] D4: backup snapshot/verify/restore/browse take --repo <guid> only; delete --include-repo/--exclude-repo name matching (private/renet/cmd/renet/backup_license.go:98-166) in favour of --repo and --exclude-repo by GUID; an --exclude-repo GUID absent from the datastore is a no-op. Accept: backup_license_test.go rewritten; refusal tests.
- [ ] D5: One GUID regex shared from one package, replacing the six copies (private/renet/cmd/renet/backup_list.go:100, private/renet/cmd/renet/repository_license_scan.go:39, private/renet/cmd/renet/repository_license_status.go:51, private/renet/pkg/list/repositories.go:32, private/renet/pkg/prune/identifiers.go:17, private/renet/pkg/functions/commands/registry.go:17). Accept: grep shows one definition.
- [ ] D6: sandbox-gateway requires --guid; delete the legacy home/<name> and mounts/*/<name> scans (private/renet/cmd/renet/sandbox_gateway.go:376-414). Sequenced after PLAN-shell-sandbox-readonly-view closes. Accept: TestFindRepoMountPathLegacyKeys replaced by a refusal test.
- [ ] D7: Key .interim/sandbox by GUID (private/renet/cmd/renet/sandbox_gateway.go:138, private/renet/pkg/orchestration/workflows.go:793, private/renet/pkg/prune/datastore.go:633-705) and make renet-side authorized_keys removal match the GUID (private/renet/pkg/orchestration/workflows.go:1188-1207). Accept: workflows_authkeys_test updated.
- [ ] D8: CLI: buildSingleRepoEntry throws instead of using the name as the GUID (packages/cli/src/services/renet/renet-execution.ts:410); packages/cli/src/services/repo/repo-key-deployment.ts:52 requires the GUID; packages/cli/src/commands/repo-batch-utils.ts:357 drops the name fallback. Accept: renet-execution.test.ts and repo-key-deployment.test.ts updated.
- [ ] D9: CLI sends task.repository as the GUID and the friendly name only as repo_name, for every vault-built verb; delete aliasBareNamesToGrands' name aliasing where it becomes dead. Accept: contract tests; one live repo up on an ops VM.
- [ ] D10: Fix kube dispatch (private/renet/cmd/renet/reporuntime_dispatch.go:67-69) so Name and GUID are distinct, and REDIACC_REPO_NAME is the friendly name. Accept: kube unit test.
- [ ] D11: renet help text and examples say GUID where the value is a GUID (private/renet/cmd/renet/helpers.go:46, private/renet/cmd/renet/repository_mount.go:30-41, private/renet/cmd/renet/repository_fork.go:41-53, private/renet/cmd/renet/backup_browse.go:56). Accept: i18n gate rc=0.
- [ ] D12: Re-deploy keys with --guid for every repo during setup, so no authorized_keys line without --guid survives the upgrade. Accept: live grep on hostinger in Q-phase shows every line carries --guid.

### Phase E: data safety

- [ ] E1: `backup restore --as X` mints a new GUID (and a credential map entry) instead of reusing the source's; renet refuses to write over any existing repositories/<guid> unless the caller passes --replace with the same GUID on purpose. Owns: packages/cli/src/commands/backup.ts, cmd/renet/backup_restore.go. Accept: e2e "restore on the source machine leaves the source byte-identical".
- [x] E2: Per-stream retention floor on the server: keep the newest 3 manifests of every stream (subscription, repository, machine) plus each stream's current anchor, regardless of policy. Owns: backup-gc.service.ts retentionKeepSet. Accept: vitest with two streams and a fork in one lineage; each keeps its newest.
    (ticked) 2026-10-23T23:43:53Z by d778be9d: commit:4f4a78487 private/account/src/services/backup-gc.service.ts:66; account HEAD export: vitest backup-retention, backup-gc, backup-storage, dto-conformance 133 passed rc=0 on 2026-10-24
- [x] E3: commitManifest refuses a parentSnapshotId that has no row, or belongs to another lineage; renet answers that refusal by promoting the run to a full manifest. Accept: vitest refusal plus a Go test for the promote path.
    (ticked) 2026-10-23T23:43:24Z by d778be9d: commit:4f4a78487 private/account/src/services/backup-storage.service.ts:1075; account HEAD export: vitest backup-retention, backup-gc, backup-storage, dto-conformance 133 passed rc=0 on 2026-10-24
- [x] E4: `restore --at <time>` filters by stream (this repo GUID and, by default, this machine), with --any-stream to widen on purpose. Owns: packages/cli/src/commands/backup.ts:311-318. Accept: test with two streams.
    (ticked) 2026-10-24T04:10:40Z by d778be9d: commit:b8fa5ef7e packages/cli/src/commands/__tests__/backup-restore-at.test.ts:1; E4: restore --at defaults to this repo stream on its machine, --any-stream widens; two-stream tests pass, vitest 28 passed rc=0
- [x] E5: Add backup_snapshot and backup_restore to slowFunctionNames (private/renet/cmd/renet/functions_commands.go:902) so a first seed is not cut at 30 s. Accept: test asserts the budget.
    (ticked) 2026-10-25T05:51:05Z by d778be9d: renet ff13648: backup_snapshot and backup_restore in slowFunctionNames, TestTestModeTimeout_BackupVerbsGetTheIOBudget; go test ./cmd/renet -run TestTestModeTimeout|TestSlowFunction rc=0 (scratch clone at HEAD)
- [x] E6: Restore uses a licence of the same lineage only; the fallback to any licence with a warning is removed. Accept: test with two lineages.
    (ticked) 2026-10-24T04:10:42Z by d778be9d: commit:32ebe33f2 private/renet/cmd/renet/backup_restore_test.go:1; E6 in renet 43aba35: lineage-only restore licence, the fallback removed; TestResolveRestoreLicense_TwoLineages passes and failed on HEAD

### Phase F: retention that a customer can rely on

- [ ] F1: Policy scope moves to (subscription, lineage, stream) with a lineage-level default row; schema migration and DTOs. Owns: private/account/drizzle, src/db/schema.ts, dto/backup.dto.ts. Accept: migration applies on a copy of the eu D1 shape; vitest.
- [x] F2: Server default when no policy exists: last 7, daily 7, weekly 4, monthly 6; an explicit `--keep-all` row keeps everything. Accept: vitest "no row prunes to the default"; dry-run shows the deletion set before the first real sweep.
    (ticked) 2026-10-23T23:43:55Z by d778be9d: commit:4f4a78487 private/account/src/services/backup-gc.service.ts:133; account HEAD export: vitest backup-retention, backup-gc, backup-storage, dto-conformance 133 passed rc=0 on 2026-10-24
- [ ] F3: Per-plan defaults and limits in PLAN_LIMITS (packages/shared/src/subscription/constants.ts:35-54): community last 3 + daily 7; professional daily 7, weekly 4, monthly 6; business daily 14, weekly 8, monthly 12, yearly 1; enterprise daily 30, weekly 12, monthly 24, yearly 7. Accept: vitest per plan; a limit above the plan refuses with a named error.
- [ ] F4: `backup strategy set --retention "last=7,daily=7,weekly=4,monthly=6"` writes strategy.retention (packages/shared/src/config-schema/schemas.ts:482-499, currently dead); `backup schedule` and every `backup run` push it to each included repo's lineage; a per-repo `retention set` overrides it. Accept: CLI tests; live check in Q.
- [ ] F5: `backup retention` shows the effective policy and its source (repo override, strategy, plan default, server default). Accept: CLI test.
- [ ] F6: Dry-run endpoint and `rdc backup retention preview <repo>` listing what the next sweep deletes and the bytes it frees. Accept: vitest plus CLI test.
- [ ] F7: Warn at `strategy set` when the knobs don't fit the cron (keepHourly on a daily cron; keepDaily on a weekly cron). Accept: CLI tests.
- [ ] F8: Orphaned lineages: `repo delete` marks the lineage orphaned on the server; orphans keep their last N for 90 days, then expire; `--purge-backups` deletes now. Accept: vitest for the expiry and the purge.
- [x] F9: Chunk GC grace counts from when a chunk became unreferenced, not from its upload time (private/account/src/services/backup-gc.service.ts:46,177-299). Accept: vitest that fails on today's code.
    (ticked) 2026-10-23T23:43:27Z by d778be9d: commit:4f4a78487 private/account/src/services/backup-gc.service.ts:187; account HEAD export: vitest backup-retention, backup-gc, backup-storage, dto-conformance 133 passed rc=0 on 2026-10-24
- [ ] F10: Manual delete: `rdc backup snapshots delete <repo> <id>` through pruneManifest (private/account/src/services/backup-gc.service.ts:359), so the quota error's "prune old snapshots" names a real command. Accept: CLI + vitest.
- [ ] F11: Over-quota response: show what the policy would free and what a stricter preset would free; never prune beyond the declared policy. Accept: vitest on the over-limit flag path.
- [ ] F12: Tests for hourly/weekly/monthly/yearly buckets across an ISO-week year boundary and UTC midnight, the policy sweep racing a live lease, and "backups stopped for 6 months deletes nothing". Accept: vitest rc=0, each fails when its rule is broken.

### Phase G: scheduling that runs what was asked

- [ ] G1: The unit generator resolves strategy.include/exclude names through the config to repositoryGuid, keeps only repos placed on the target datastore, and emits --repo <guid> / --exclude-repo <guid>; delete the exclude refusal (packages/cli/src/services/backup/backup-schedule-unit-generator.ts:136-161). It takes config and machine context. Accept: contract test (G9) passes; today's string test is deleted.
- [x] G2: `backup strategy set` validates include/exclude names against the config and refuses unknown names. Accept: CLI test.
    (ticked) 2026-10-24T14:16:21Z by d778be9d: commit:a0d131ce3 strategy set refuses unknown include/exclude names before writing; vitest backup-strategy-validate 8 passed rc=0
- [ ] G3: One snapshot per strategy run, whatever the number of destinations; the destination list collapses to one hosted or self-hosted S3 endpoint per strategy. Accept: generator test with two destinations emits one command.
- [ ] G4: Schedules re-render on repo create, delete, fork and rename (the reconciler redeploys when the unit hash changes). Accept: CLI test; live on an ops VM a new fork appears in the unit.
- [ ] G5: Named datastores get schedules too (packages/cli/src/services/backup/backup-schedule.ts:195 only does machine.datastore). Accept: test with a named datastore.
- [ ] G6: `backup status` says "not scheduled" when the timer is absent, shows last run, result and next run per strategy, and exits non-zero on a missed run. Accept: CLI test with no timer; live on hostinger before Q.
- [ ] G7: machine status and health warn when any repo's last backup is older than 2x its schedule interval (backup_coverage age_days). Accept: test; health exits 1.
- [x] G8: Binding a strategy that cannot be scheduled is refused at bind time, not at schedule time. Accept: CLI test.
    (ticked) 2026-10-24T14:16:22Z by d778be9d: commit:a0d131ce3 bind refuses an unschedulable strategy through strategyUnschedulableReason, shared with the unit generator; vitest rc=0
- [ ] G9: Contract test: every generated ExecStart argv is parsed by the real `renet backup snapshot` flag set (cobra, no execution), so a flag mismatch fails CI. Accept: it fails on today's --repo <name> output.
- [ ] G10: Per-repo cadence (02-design decision 10): an optional per-repo schedule override inside a strategy. Accept: generator test.
- [ ] G11: Order a run by RPO deficit, furthest-behind repo first (decision 9, private/renet/cmd/renet/backup_snapshot.go:124-126). Accept: Go test on the ordering.

### Phase H: rclone out of everything

- [ ] H1: Delete `rdc storage` (browse, import, prune, add, remove, list), services/repo/storage-browser.ts, commands/storage-endpoints.ts and their metadata (packages/cli/src/config/command-metadata.ts:319,794; packages/cli/src/config/command-planes.ts:55,105-106). Accept: CLI builds; command-tree regenerated.
- [ ] H2: Shared schema: delete StorageConfigSchema and resources.storages, the destination kind 'storage' and DESTINATION_KIND (packages/shared/src/config-schema/schemas.ts:188-194,431-454; packages/shared/src/config/defaults.ts:483-497), and the sensitivity entry (packages/shared/src/config-schema/sensitivity.ts:184). A config carrying them fails to load naming the removed field. Accept: config-schema tests; a fixture with storages is refused with that message.
- [ ] H3: Delete packages/shared rclone parser and storage-browser (renet-contract/utils/rclone.ts and its exports, storage-browser/*), RCLONE_PATTERN in utils/progress.ts, and the rclone test. Accept: shared builds; knip clean.
- [ ] H4: CLI residue, part 1: backup-strategy.ts --storage, kind 'storage' and the NOT SCHEDULABLE marker; packages/cli/src/commands/backup-ops.ts:58-63; packages/cli/src/commands/repo-backup.ts:170-182 storageRetired; packages/cli/src/commands/backup.ts:147-148; packages/cli/src/commands/repo-backup-list.ts:81 --from storage. Accept: CLI tests rc=0.
- [ ] H5: CLI residue, part 2: packages/cli/src/services/renet/renet-execution.ts:368-397 and packages/cli/src/services/executor/vault-inputs.ts:20-27 STORAGE_SYSTEMS; the unit generator's --rclone-param redaction and RCLONE comments; backup-env-file.ts, credits.ts and delta.ts comments. Accept: grep -i rclone in packages/cli/src is empty.
- [ ] H6: Rename the --bwlimit label away from "Rclone bandwidth limit" across 13 locales and the contract mirror. Accept: i18n gates rc=0.
- [ ] H7: renet: delete sourceTypeStorage/destTypeStorage and their refusals (private/renet/cmd/renet/backup_pull.go:28-55, private/renet/pkg/functions/commands/backup.go:17-30,81-267), and backup list/delete --source/--target storage. Accept: go build; refusal tests replaced by "unknown flag" tests.
- [ ] H8: renet RustFS workers without rclone: replace ensureRclone/renderEnsureRclone/ConfigureWorker(s) (private/renet/pkg/infra/docker/service.go:386-752), pkgset.Rclone (private/renet/pkg/infra/pkgset/pkgset.go:348-353), ops rustfs configure-worker(s) (private/renet/cmd/renet/ops_rustfs.go:147-172) and the image-bake hook (private/renet/cmd/renet/image_build_command.go:113, private/renet/pkg/infra/image/one_shot_builder.go:84) with an S3 client path or delete them; update .ci/rediacc_ci/infra/vm_bake_key.py:93-95. Accept: RustFS e2e suites 15/19/20 green.
- [ ] H9: renet dead code: GeneralSettings RCLONE_* and the Storage struct (private/renet/pkg/config/config.go:255-284), ValidateStorage/GetRcloneConfigString/GetRcloneEnvVars (private/renet/pkg/config/config.go:459-548), PathTypeRclone (private/renet/pkg/toolexec/ssh.go:89-150), rclone progress filtering (private/renet/pkg/functions/executor_local.go:810-839), the VAULT_PARSING.md section. Accept: deadcode gate rc=0.
- [ ] H10: e2e helpers: StorageTestHelper, OpsRustFSManager, OpsManager and packages/e2e-tests/src/base/bridge-global-setup.ts:253-378 use an S3 client instead of the rclone CLI. Accept: suites 15, 19, 20 and 25 pass locally (e2e-local agent recipe).
- [ ] H11: i18n: delete every rclone key in packages/cli locales, the contract mirror and renet locales (ops.rustfs_configure_rclone_*, infra.docker_*rclone*, cmd.configure_rclone_*, baseline RCLONE_* strings); fix credits.description. Accept: i18n gates rc=0 across the three trees.
- [ ] H12: Docs and www: backup-restore.md, pruning.md, quick-start.md, rdc-cheat-sheet.md, architecture.md and packages/www/src/content/docs/en/server-reference.md:198-200 in all 13 locales; the NIS2 blog posts' "any rclone-compatible target"; regenerate search indexes and the skill reference; the changelog stays history. Accept: check-retired-commands-in-docs rc=0; www build rc=0.
- [ ] H13: private/account: migrate the persisted pricing flag key rcloneBackup (private/account/src/pricing/catalog.default.ts:155, drizzle 0034) to a chunk-store key with a migration; fix exam and study content (private/account/src/data/exam-question-bank.json:1619, drizzle 0037, private/account/web/src/data/study-content/mt6-backup.ts:23). Accept: account vitest rc=0; migration applies.
- [ ] H14: CI residue: Dockerfile and workflow comments, the embed blocklist comment, the ci_diagnose rclone classifier, the knip ignore entry, tutorial-backup-restore.sh, and the third-party-licenses and dockerfile-versions comments. Accept: grep -ri rclone in tracked code returns only agent/ history and the H15 gate.
- [ ] H15: The re-embed gate: a check that fails when an rdc or renet binary or the embed lockfile contains rclone (strings count), wired into ci:quick and the build lane. Accept: control test: a planted asset fails it.
- [ ] H16: renet legacy prune subsets: StalePullStaging (.pull-*), StaleBackupSnapshots (.backup-*), GenerateBackupSnapshotName, CleanStaleBackupSnapshots in maintain. Accept: prune tests updated.
- [ ] H17: renet CLAUDE.md, private/renet/docs/datastore/README.md:184-186, and the rclone text in docs/design 06, spec 03 and spec 04 corrected. Accept: grep.

### Phase I: the self-hosted backup plane

- [x] I1: ACCOUNT_BACKUP_S3_REGION env (default us-east-1, "auto" for R2) passed to S3BackupChunkStore and blob-storage.service. Owns: types/env.ts, private/account/src/services/backup-chunk-store.ts:171-187, private/account/src/services/blob-storage.service.ts:49. Accept: vitest that the signer uses the configured region.
    (ticked) 2026-10-24T15:59:59Z by d778be9d: commit:166ba413e (account 8e7d44e, elite 4d69f70) I1 ACCOUNT_BACKUP_S3_REGION reaches the S3 store and blob client, signer uses the configured region; vitest rc=0 (35 passed), 16 of 19 failed before the fix
- [x] I2: ACCOUNT_BACKUP_S3_PUBLIC_ENDPOINT used for presigned grant URLs (S3PresignGrantMinter, private/account/src/services/backup-chunk-store.ts:1001,1018); the server keeps the internal endpoint for its own calls. Accept: vitest that a grant URL carries the public host.
    (ticked) 2026-10-24T16:00:00Z by d778be9d: commit:166ba413e (account 8e7d44e, elite 4d69f70) I2 presigned grants signed on ACCOUNT_BACKUP_S3_PUBLIC_ENDPOINT while the store keeps the internal endpoint; vitest rc=0 (35 passed), 16 of 19 failed before the fix
- [ ] I3: Elite stack exposure: an nginx /s3/ location or a published port for RustFS, PUBLIC_SITE_URL and the public endpoint set in private/elite docker-compose.yml, and an operator-facing elite backup doc. Accept: elite compose up; a machine outside the docker network completes a snapshot.
- [x] I4: Startup validation on the node and on-premise entries: a partial ACCOUNT_BACKUP_S3_* set refuses to start naming the missing keys, and misspelled keys are reported (zod strict for that prefix). Accept: vitest for each partial set.
    (ticked) 2026-10-24T16:00:01Z by d778be9d: commit:166ba413e (account 8e7d44e, elite 4d69f70) I4 assertBackupS3Env refuses a partial or misspelled ACCOUNT_BACKUP_S3_ set at node and on-premise start; vitest rc=0 (35 passed), 16 of 19 failed before the fix
- [x] I5: CI_MODE parity: on-premise.ts skips maintenance under CI_MODE like node.ts; BACKUP_MAINTENANCE_INTERVAL_MS exposed in elite compose. Accept: vitest.
    (ticked) 2026-10-24T16:00:01Z by d778be9d: commit:166ba413e (account 8e7d44e, elite 4d69f70) I5 on-premise skips maintenance under CI_MODE through the shared helper, elite compose exposes BACKUP_MAINTENANCE_INTERVAL_MS; vitest rc=0 (35 passed), 16 of 19 failed before the fix
- [ ] I6: The startup log names the public endpoint and region. Accept: a test pins the log line.
- [ ] I7: A drill variant that boots entry/on-premise.ts (not dev-gateway) against RustFS and runs private/elite/scripts/s3-conformance-probe.sh; it becomes part of the backup receipt (J4). Accept: drill rc=0 locally.

### Phase J: gates, CI binding and push enforcement

- [ ] J1: Split pkg/chunkstore root-only tests behind a build tag so check:ci-proxy-go-unit stops excluding the package (.ci/rediacc_ci/proxies/go_unit.py:26,63); the same for pkg/delta and pkg/datastore where possible. Accept: the proxy runs chunkstore unit tests; the count is logged.
- [ ] J2: Gate check:renet-chunkstore-unit (paths private/renet) running go test ./pkg/chunkstore/... non-root, in gates.lock.json, package.json and the CI lane. Accept: ci-parity and gate-reachability rc=0; a planted failing test reds ci:quick.
- [ ] J3: Gate check:account-backup (paths private/account) running the backup-* vitest files. Accept: same as J2.
- [ ] J4: A backup receipt: backup_check_trigger.py plus block_backup_unverified_push.py, cloned from the vm-check pair (ORDER near 61), triggered by backup paths in console, renet (gitlink diff) and account. The receipt comes from the RustFS drill (legs a-l) and I7, keyed on tree, input digest and both gitlinks; REASON_ENV with ASKED: is the only escape; it extends PLAN-account-vm-check's runner where it fits. Accept: guard tests (no receipt refused, receipt admits, stale gitlink refused).
- [ ] J5: Unbound-test complaint: extend check_test_file_orphans.py and check:ci-e2e-coverage so every Go test package, vitest file, e2e suite and drill leg is reached by some CI job or carries a BLOCKER-reasoned allowlist entry; suite 26 and backup_restore lose their allowlist entries. Accept: the gate fails on today's tree for suite 26, then passes after J6.
- [ ] J6: Suite 26 runs in CI on the VM fleet with the account gateway (BACKUP_STORAGE_SUITE=1 set by the workflow), at least nightly and on backup-path changes. Accept: a green CI run id recorded here.
- [ ] J7: Drill legs b-d drive real renet instead of host-built cells. Accept: drill rc=0 with renet in the loop.
- [ ] J8: Drill leg l: GC and retention through /backup/maintenance against RustFS, asserting that bytes go down and the floor holds. Accept: KNOWN_LEGS includes l; drill rc=0.
- [ ] J9: The renet full test suite (btrfs tier) runs on every renet change in CI, not only on full_suite (.github/workflows/ct-tests.yml:2335,2416). Accept: CI run id.
- [ ] J10: Extend githooks.py pre_push (:290) so a terminal push of backup paths also needs the receipt, or record the operator's ruling not to. Accept: hook test, or the ruling cited.

### Phase K: tests for what is untested today

- [ ] K1: Kill and resume a real `renet backup snapshot` mid-upload; the journal drains and the manifest commits once (btrfs tier plus RustFS). Accept: Go integration test.
- [ ] K2: Kill and resume a real restore. Accept: e2e in suite 26.
- [ ] K3: Two machines and a fork commit into one lineage, then a retention sweep runs; every stream keeps its floor and every chain resolves. Accept: vitest plus a suite 26 case.
- [ ] K4: Fork restore: fork, write, back up the fork, restore the fork's snapshot on a second VM, byte-compare. Accept: suite 26 case.
- [ ] K5: A same-machine restore leaves the source byte-identical (E1). Accept: suite 26 case.
- [ ] K6: Cold round trip T3: a container writes a counter, a `--cold` backup runs, the restore shows no gap and no torn write. Accept: suite 26 case.
- [ ] K7: A scheduled timer fires: `backup schedule`, then `systemctl start` the unit, and a manifest commits. Accept: suite 26 case.
- [x] K8: verifyReconcile: plant a deleted chunk and a ledger drift and assert driftBytes; wire a nightly caller into runMaintenance. Accept: vitest; cron wiring test.
    (ticked) 2026-10-24T15:56:11Z by d778be9d: commit:677aad399 (account 62e2e29) verifyReconcile drift tests (deleted chunk -100, overcount -200, clean 0) and the nightly verify-reconcile phase; vitest 49 passed rc=0, cron-wiring mutation fails without the call
- [ ] K9: Key rotation: a passphrase change keeps dedup (same master key); a reencrypt forces a full seed and still restores. Accept: btrfs/LUKS tier test.
- [ ] K10: Large-repo performance: a nightly VM job seeds 50 GB and runs an incremental against a time and byte budget, recording durationMs. Accept: the first nightly result recorded.
- [ ] K11: Corruption injection at e2e level: flip a byte in a stored chunk; restore refuses and verify reports it. Accept: suite 26 case.
- [ ] K11a: A reusable corruption-injection fixture (flip one byte of a stored chunk) for K11 and later suites; CHECKLIST w4 found no such helper. Accept: K11's suite 26 case uses it.
- [ ] K12: A restore scenario in license-e2e. Accept: license-e2e rc=0.
- [ ] K13: Cross-region --at: an EU subscription resolves a time even when the CLI's default server is another region. Accept: CLI test, plus a fix if it fails.
- [ ] K14: Parallel hashing on the backup side (private/renet/pkg/chunkstore/hash.go:35 is single-threaded), with a benchmark. Accept: the benchmark shows the speed-up; tests pass.

### Phase L: seeded, incremental restore

- [ ] L1: Restore writes a journal and anchor for the restored snapshot, so the next backup on that machine re-hashes nothing. Accept: btrfs-tier test: a backup after a restore uploads 0 new bytes.
- [ ] L2: A hole-punch helper in renet (fallocate PUNCH_HOLE); the restore holes check punches cells the target says are zero instead of discarding the seed (private/renet/pkg/chunkstore/restore.go:73-81,233-257). Accept: unit test.
- [ ] L3: Seed candidates in order: the same GUID's anchor, the fork's or grand's anchor, then the live image (reflink copy into the staging path). The LUKS UUID and key digest are compared first, and a seed with a different key is skipped. Accept: a test per candidate type.
- [ ] L4: Fetch only cells whose hash differs from the target manifest, reusing the resume path (private/renet/pkg/chunkstore/restore.go:174-177,267-280). Accept: a restore after a 1% change fetches about 1% of cells (metric asserted).
- [ ] L5: Cross-machine seeding: a machine holding a pushed copy or a fork seeds from it. Accept: suite 26 case on two VMs.
- [ ] L6: Restore metrics (cells fetched, reused, punched, bytes) in the JSON output and the `backup restore` summary. Accept: CLI test.

### Phase M: secrets and a traceable local publish

- [ ] M1: Port .ci/cache/w7p5a-realrun/bws_names_exec.py and the lead_run.py item-5 wiring into tracked code: a BWS profile (or an explicit name list in secret-supply.json) plus a local entry for rediacc_ci.deploy.set_account_worker_secrets that takes --region and --target and derives SUFFIX, buckets, jurisdiction and SES region from regions.json. Coordinate Owns with PLAN-w7p5a-real-run-dispatch. Accept: a dry run prints the 29 names (never values) for eu stable and edge.
- [ ] M2: The local path runs the turnstile_drift preflight first and refuses on drift. Accept: test with a planted mismatch.
- [ ] M3: A worker-secret prune verb: list the live worker's secret names, compare them with the names the deploy pushes, and delete the extras through the Cloudflare API (which keeps the ASSETS binding, measured 2026-10-15). Extend check-worker-secret-names.ts to report live extras when a token is present. Accept: a dry run on eu lists nothing extra after the 2026-10-15 cleanup.
- [ ] M4: Pin wrangler in workers/account to the constants.sh version (4.150.0; 4.131.2 is installed) and make the deploy refuse a mismatch. Accept: pins gate rc=0.
- [ ] M5: Update .claude/skills/deploy/SKILL.md: bws on the host, the local secrets path, and the API-delete fact. Accept: skill text matches the tooling.

### Phase N: design backlog decided and built

- [ ] N1: Verify level (b) HEADs every chunk of a lineage on a schedule; level (c) re-downloads a sample and hashes it. Both run in runMaintenance with budgets. Accept: vitest, and the RustFS drill covers both.
- [ ] N2: Decision 5 (bucket per subscription): decide and record; pooled regional buckets stay unless a customer requirement appears. Accept: a decision line in 07-execution-record.md.
- [ ] N3: Decision 13 (Infrequent Access tier for old full manifests): decide and record, and build it if chosen. Accept: decision recorded.
- [ ] N4: Single file or directory restore from a snapshot without a full image restore, on top of Phase O's table of contents. Accept: a box in Phase O covers it after A2.

### Phase O: browse TOC and remote browse (folded from PLAN-chunk-store-browse-toc-and-remote.md by A2)

- [ ] O1: Holds the place until A2 copies the 11 boxes verbatim here after PR #600 merges; the A2 commit ticks it.

### Phase R: config, licence and machine findings from 2026-10-15

- [ ] R1: The released CLI (rdc 1.3.12) refuses `eu-remote`, reporting that the config was encrypted with a different key than the reader's slot holds, while the dev CLI reads it. Find whether this is format skew between versions or a real slot-key mismatch, and fix the side that is wrong; an older CLI must refuse with a message that names the version gap. Accept: a test with a config enrolled by the new code and read by the old reader path, plus a live read by the next released CLI.
- [ ] R2: The remote config version went from 5 to 15 on 2026-10-15 with no deliberate write by the session that held it. Trace which commands push (machine setup, key deployment, infra push, refresh, strategy and storage edits) and make every push intentional and visible in the command output. Accept: `config remote versions --config eu-remote` explained entry by entry; a test that a read-only command never pushes.
- [ ] R3: `subscription status --config eu-remote` counts 35 tracked licences, 0 valid, 16 refresh recommended and 19 hard expired, while `machine status hostinger --licenses` reports all 11 valid. Reconcile the server's licence ledger with the machines (deleted repos and forks are the likely extra rows) and make the two views agree. Accept: both commands agree after the fix; a test covers a deleted repo's licence row.
- [ ] R4: hermes is 100% full (31.4G of 31.4G). Before the first seed in Q11, inside a fork or with REDIACC_ALLOW_GRAND_REPO=hermes granted by the operator, find what fills it and either free space or grow the image online (`./rdc.sh repo expand hermes --config eu-remote`, zero downtime, grow-only; the datastore has about 50 GB free). Accept: hermes below 90% used and its services healthy.
- [ ] R5: Removing a resource that others reference is refused or cascades on purpose: `storage remove` left both strategies pointing at a removed storage on 2026-10-15. H1 deletes `rdc storage`; sweep the remaining remove verbs (machine, strategy, datastore) for the same gap. Accept: a test per verb.

### Phase S: tenant isolation and security holes (audit of 2026-10-15)

Two holes went to another session on 2026-10-15 for an immediate fix: cross-tenant config deletion (config blob keys carry no store id) and the backup credentials (an account-wide R2 key reachable by bench, and one backup key shared by stable, edge and bench). S1 only verifies that work landed. Verified as sound on 2026-10-15: no backup or config bucket has r2.dev access, a custom domain or CORS; the backup subscription is always taken from the server; /exists and restore chains stay inside the tenant prefix; grants are single-key, single-verb and create-only.

- [ ] S1: Verify the hand-off landed: config blob keys carry the store id (private/account/src/services/config.service.ts:2681-2698) with a two-stores-one-configId test; separate stable, edge and bench backup tokens scoped to their own buckets; no fallback to CLOUDFLARE_R2_* in .ci/rediacc_ci/ops/deploy_bench.py:74-86; the shared token revoked; the credential gate exists. Accept: the commits and the Cloudflare token list (names and scopes only).
- [x] S2: Licences expire as backup credentials: the backup session refuses a blob past hardExpiresAt (private/account/src/services/repo-license-verify.service.ts:79 parses it and nothing checks it), with a short restore-only grace if chosen; the session requires a live activation for the machineId instead of trusting the echoed machineId (private/account/src/services/subscription.service.ts:1190-1204); chainHash is required when the ledger has an entry. Accept: vitest for an expired blob, an echoed machineId with no activation, and a stripped chainHash; each fails on today's code.
    (ticked) 2026-10-24T04:10:33Z by d778be9d: commit:d22373e7b private/account/tests/integration/backup-session-isolation.test.ts:1; S2 in account 1cae9da: expired blob, echoed machineId without activation and stripped chainHash refused; the new tests failed 9 of 10 on HEAD and pass now; full account suite 2442 passed rc=0; activation is required on machineId drift (the echoed-id case), a decision recorded for the operator
- [x] S3: Bind the backup session to the licence's grandGuid: store it on the session and require lineageGuid to match on /streams, /grants, /read-grants, /exists and /commit (private/account/src/services/backup-storage.service.ts:187-195,550-563). Accept: vitest: a licence for repo A cannot read or write repo B's lineage in the same subscription.
    (ticked) 2026-10-24T04:10:35Z by d778be9d: commit:d22373e7b private/account/tests/integration/backup-session-isolation.test.ts:1; S3 in account 1cae9da: the session stores grandGuid and requireSessionLineage guards streams, grants, read-grants, exists and commit; repo A's licence cannot read or write repo B's lineage; full account suite 2442 passed rc=0
- [x] S4: Team scope on backup token routes: map each lineage to its team through the licence issuance and filter /backups/usage, /manifests and /retention by apiTokenTeamId (private/account/src/routes/backups.ts:126-208); make backup:manage an owner/admin scope. Accept: vitest: a team-scoped token cannot see or change another team's lineage.
    (ticked) 2026-10-24T16:39:01Z by d778be9d: commit:a2e4ffc4b (account c5363e9) a team-scoped token cannot see or change another team's lineage; backup:manage privileged; vitest 109 passed, 7 of 8 failed before the fix
- [ ] S5: Size-bound uploads: presigned PUTs sign ContentLength (a per-chunk maximum) and x-amz-checksum-sha256 (private/account/src/services/backup-chunk-store.ts:826); cap hashes per grant call and require them to fit declaredBytes (private/account/src/dto/backup.dto.ts:59-61); bill from stored sizes, not client numbers. Accept: a drill PUT larger than declared is refused by RustFS and R2; vitest for the caps.
- [x] S6: Maintenance isolation: runMaintenance wraps each subscription in its own error boundary with a CPU, time and subrequest budget and resumes from a cursor (private/account/src/services/backup-gc.service.ts:129-150); commit HEADs and caps manifest size. Accept: vitest: one failing or oversized tenant does not stop the sweep for the rest.
    (ticked) 2026-10-24T04:10:37Z by d778be9d: commit:d22373e7b private/account/tests/integration/backup-maintenance-isolation.test.ts:1; S6 in account 1cae9da: per-subscription error boundary, budgets and resume cursor (a failing or oversized tenant does not stop the rest), plus the commit-side manifest HEAD and size cap; full account suite 2442 passed rc=0
- [x] S7: Executor tokens: /configs/executor-token (private/account/src/routes/configs.ts:837-892) mints only for a user who granted the session, the token is read-only, and minting proxy:exec is admin-only. Accept: vitest: a member cannot mint a token as the team admin, and an executor token cannot PUT.
    (ticked) 2026-10-24T19:24:24Z by d778be9d: commit:d8c6e802b (account 8e97b94, 7ec6730, 8a86225; CLI f7af8d367) a member cannot mint as the admin, an executor token cannot PUT, and minting needs the session's recorded grantor; vitest 61 + 107 passed rc=0
- [x] S8: Strict identifiers: lineageGuid, repositoryGuid, snapshotId and streamId are UUIDs or `^[A-Za-z0-9-]{1,64}$` in every DTO (private/account/src/dto/backup.dto.ts:6). Accept: vitest refusing `/`, `..` and other separators.
    (ticked) 2026-10-23T23:43:57Z by d778be9d: commit:4f4a78487 private/account/src/dto/backup.dto.ts:16; account HEAD export: vitest backup-retention, backup-gc, backup-storage, dto-conformance 133 passed rc=0 on 2026-10-24
- [ ] S9: Rate limits at the edge for /backups/session and /licenses/renew, and sampled refusal logging so garbage blobs cannot flood D1 (private/account/src/routes/backups.ts:70, private/account/src/middleware/rate-limit.ts:43-51). Accept: test or Cloudflare rule recorded.
- [x] S10: Self-hosted hardening: trust X-Forwarded-For and X-Real-IP only from a configured proxy list (private/account/src/utils/request.ts:13-18); elite refuses to start with the default admin and RustFS credentials, or generates them on first start (private/elite/.env.template:11). Accept: tests for both.
    (ticked) 2026-10-24T16:39:02Z by d778be9d: commit:a2e4ffc4b (elite 19ac922; account half c185e93/10f0fc6) forwarded headers trusted only from TRUSTED_PROXIES; elite generates RustFS/admin credentials on first start and refuses defaults in cloud mode; test-credentials.sh rc=0, ip-binding tests 65 passed
- [x] S11: Small fixes: requireTwoFactor on DELETE /configs/:id (private/account/src/routes/configs.ts:1436), /rotate-cek/status limited to admins (:812), CI_MODE pinned false in the Workers entry (private/account/src/entry/cloudflare.ts:36). Accept: vitest per route.
    (ticked) 2026-10-24T16:02:44Z by d778be9d: commit:589d12fb0 (account 8e97b94) requireTwoFactor on DELETE /configs/:id, requireRotationAdmin on rotate-cek/status, CI_MODE pinned false in entry/cloudflare.ts; vitest 50 passed rc=0, refusals failed before the fix
- [ ] S12: An isolation test suite that keeps these closed: two subscriptions, two orgs, two teams and two stores sharing ids, run in account vitest and in the RustFS drill (J4 receipt). Accept: the suite fails if any of S2-S8 is reverted.

### Phase P: local integration proof (dev VMs, account gateway, RustFS)

- [ ] P1: Bring up the stack with `./run.sh account dev` (gateway, portal, RustFS) and `./rdc.sh ops up --basic`; `./rdc.sh --dev config current` shows the dev server. Accept: gateway health 200, two VMs ready.
- [ ] P2: Provision both VMs with the new renet: `./rdc.sh --dev machine setup <vm1>` and `<vm2>`; `./rdc.sh --dev machine status <vm1> --system` shows no stale_binary and no renet plugin process. Accept: the C4 field is empty and `pgrep -a 'renet plugin'` prints nothing.
- [ ] P3: `./rdc.sh --dev repo create bp-src -m <vm1>`, write about 2 GB into it, then `./rdc.sh --dev repo fork bp-src --tag t1`. Accept: both repos up.
- [ ] P4: `./rdc.sh --dev backup strategy set bp-hot --destination hosted --cron "*/30 * * * *" --mode hot --include bp-src --retention "last=7,daily=7"`, then `./rdc.sh --dev backup strategy bind bp-hot --machine <vm1>` and `./rdc.sh --dev backup schedule --machine <vm1>`. Accept: the unit's ExecStart carries --repo <guid>; the G9 contract passes.
- [ ] P5: First seed and an unchanged second run: `./rdc.sh --dev backup run bp-hot --machine <vm1>` twice, then `./rdc.sh --dev backup manifests bp-src`. Accept: the second run uploads about 0 new bytes (metric).
- [ ] P6: Change 1% of bp-src and back up again. Accept: the incremental is within 2x of the change.
- [ ] P7: Cross-machine restore: `./rdc.sh --dev backup restore bp-src --as bp-restored -m <vm2> --at <snapshot-id>`, then byte-compare the file trees. Accept: identical, with a new GUID.
- [ ] P8: Restore on the source machine: `./rdc.sh --dev backup restore bp-src --as bp-same -m <vm1>`. Accept: the source image hash is the same before and after (E1).
- [ ] P9: Seeded restore: restore bp-src on vm2 again over the previous restore's anchor. Accept: cells fetched about equal to the change (L4 metric).
- [ ] P10: Retention: `./rdc.sh --dev backup retention preview bp-src`, then a maintenance run through the dev seam. Accept: the per-stream floor holds for bp-src and bp-src:t1 in `backup manifests`.
- [ ] P11: The timer fires on its own (*/30) or through `systemctl start` on vm1; `./rdc.sh --dev backup status --machine <vm1>` shows the run. Accept: status output.
- [ ] P12: Cold mode: a strategy with --mode cold on a repo with a writer container. Accept: the restore shows no torn write (K6 by hand).
- [ ] P13: Daemon upgrade: rebuild renet with a trivial change and run `./rdc.sh --dev machine setup <vm1>`. Accept: `daemons upgrade` restarted the hub, no container start time changed, C4 shows nothing stale.
- [ ] P14: Offline plane: run the account server from entry/on-premise.ts with ACCOUNT_BACKUP_S3_PUBLIC_ENDPOINT set to an address the VMs reach, and repeat P5 against it. Accept: the snapshot commits.
- [ ] P15: Record both receipts for the final tree: `npm run vm:check -- --changed` and the backup receipt (J4). Accept: both VERIFIED with the tree hash.

### Phase Q: live cutover, stable EU, hostinger to rediacc-backups-eu

- [ ] Q0: Before the cutover, set the four ACCOUNT_BACKUP_S3_* secrets on the eu stable Worker (names only, through the M1 path) and add the bucket-scoped cf-r2-backup rotation slug to the rotation profile in .ci/config/secret-supply.json; carried from CHECKLIST w8. Accept: the Worker settings list all four names; the rotation dry run lists the slug; the rollback version id is recorded.
- [ ] Q1: Merge the program's PR through the loop (CD deploys edge). Deploy stable EU locally per .claude/skills/deploy/SKILL.md: `./run.sh devbox exec -- env PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- bash -c 'npm run build:packages && PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_account --region eu --target stable'` (with the portal build step the skill names), then the M1 secrets path for eu stable. Record the rollback version id and the D1 bookmark. Accept: https://eu.rediacc.com/account/api/v1/health answers 200 and the portal assets load.
- [ ] Q2: `./rdc.sh machine setup hostinger --config eu-remote`, then `./rdc.sh machine status hostinger --config eu-remote`. Accept: no stale_binary, no renet plugin process, state-mirror records at 0644, and every authorized_keys line carries --guid (D12).
- [ ] Q3: In a quiet window, `./rdc.sh machine restart-services hostinger --include-docker --config eu-remote` restarts what the upgrade reported stale, repo by repo with health checks. Accept: `./rdc.sh machine status hostinger --containers --health-check --config eu-remote` exits 0 for all 11 repos.
- [ ] Q4: The legacy OneDrive strategies and storage were removed on 2026-10-15, so `./rdc.sh backup strategy list --config eu-remote` starts empty. Create the new strategy: `./rdc.sh backup strategy set nightly-hot --destination hosted --cron "0 2 * * *" --mode hot --retention "last=7,daily=7,weekly=4,monthly=6" --config eu-remote`. Accept: `./rdc.sh backup strategy show nightly-hot --config eu-remote` shows one hosted destination and the policy.
- [ ] Q5: Fork probe: `./rdc.sh repo fork mail --tag bp-probe --config eu-remote`, `./rdc.sh backup snapshot mail:bp-probe --config eu-remote`, `./rdc.sh backup manifests mail:bp-probe --config eu-remote`. Accept: a manifest id; `./rdc.sh backup usage --config eu-remote` shows storedBytes > 0, and the rediacc-backups-eu object count (Cloudflare API, cf-r2-jurisdiction: eu) is non-zero.
- [ ] Q6: A second, unchanged `backup snapshot mail:bp-probe`. Accept: about 0 new bytes uploaded.
- [ ] Q7: `./rdc.sh backup restore mail:bp-probe --as bp-restore -m hostinger --config eu-remote`; compare file trees of mail:bp-probe and bp-restore (`rdc repo sync download` of both, or a hash walk inside each). Accept: identical trees, bp-restore has a new GUID, and the source fork's image hash is unchanged.
- [ ] Q8: Cross-machine restore of the probe is covered by P7, because dev VMs are not part of eu-remote by design. Accept: a note line with the P7 evidence.
- [ ] Q9: `./rdc.sh repo delete bp-restore --config eu-remote` and `./rdc.sh repo delete mail:bp-probe --purge-backups --config eu-remote` (F8). Accept: the probe lineage is gone, or marked orphaned per F8.
- [ ] Q10: `./rdc.sh backup strategy bind nightly-hot --machine hostinger --config eu-remote`, `./rdc.sh backup schedule --machine hostinger --config eu-remote`, `./rdc.sh backup status --machine hostinger --config eu-remote`. Accept: the timer and next run are listed, and systemctl list-timers on hostinger shows the unit.
- [ ] Q11: First seed now instead of at 02:00: `./rdc.sh backup run nightly-hot --machine hostinger --config eu-remote -b`, watched to completion. About 310 GB at 6 MB/s is about 14 h; raise --bwlimit only with the operator's word. Accept: every repo has a manifest, and backup usage storedBytes is close to the datastore's written bytes.
- [ ] Q12: The next 02:00 timer run completes on its own and uploads only changed cells. Accept: backup status shows the timer run; usage grows by a small delta.
- [ ] Q13: After a few runs, `./rdc.sh backup retention preview mail --config eu-remote`. Accept: nothing beyond the policy is listed, and the floor is kept.
- [ ] Q14: `./rdc.sh backup verify <repo> --config eu-remote` at spot level for all 11 repos, and at full level for one small repo. Accept: every verify passes.
- [ ] Q15: `./rdc.sh machine health hostinger --config eu-remote`. Accept: exit 0, with backup age inside the interval for every repo.
- [ ] Q16: Close the record: mark CHECKLIST w8 done with run ids, add the cutover entry to 07-execution-record.md, and list the manifest ids, bucket object counts and first-seed duration in this plan's final tick. Accept: check:ci-plan-record rc=0.
