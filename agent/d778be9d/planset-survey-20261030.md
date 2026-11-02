# Plan set survey 1023-1, 2026-10-30T01:50Z (read-only)

H = `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-proxy -- ./rdc.sh --config eu-remote` (hostinger, read-only verbs).
Box B = `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench`, then `worklist.py --live-proof` (bench receipt).
One run done during the survey: `PYTHONPATH=.ci python3 -m rediacc_ci.infra.elite_s3_probe --selftest` rc=0; `cd private/account && npx vitest run tests/integration/backup-isolation-suite.test.ts` 15 passed.

| plan | sig | label | class | evidence or command |
|---|---|---|---|---|
| backup-program | 695c3218 | A1a | PR-OR-MERGE | stepQuotaPageShipped needs a deploy-preview run on the open PR; record the run id |
| backup-program | 0a237b2e | A4d | ALREADY-DONE | .github/workflows/ci.yml:1360 calls rediacc_ci.infra.elite_s3_probe (selftest then live); selftest rc=0 shows a stub ignoring If-None-Match goes red; commits 3bd4b6e7f, 041e3f166 |
| backup-program | bf28887d | D12 | LIVE-NOW | code+test landed (private/renet/pkg/orchestration/workflows_authkeys_test.go); Q2 record saw 4 of 16 lines without --guid in the muhammed user's file; read-only grep of authorized_keys on hostinger (`H term connect hostinger` / ssh) and decide human keys vs repo keys |
| backup-program | fbef928b | E1 | ALREADY-DONE | renet --replace <guid> at private/renet/cmd/renet/backup_restore.go:124,143,180; suite 26 K5 ticked 2026-10-28T16:18:45Z (plan :373) and P8 ticked (plan :490), same-machine restore leaves source byte-identical |
| backup-program | 73358a56 | H8 | LIVE-NOW | no ensureRclone/renderEnsureRclone/rclone left in service.go, pkgset.go, ops_rustfs.go; H9/H10 ticks cover suites 15, 19, 25; review note says suite 20 result is owed: run suite 20 on an ops VM via `PYTHONPATH=.ci python3 -m rediacc_ci.env.create_e2e_env ...` then `rediacc_ci.testrun.e2e` (recipe as K3 tick) |
| backup-program | 5d379672 | I3 | LIVE-NOW | in tree: private/elite/docker-compose.standalone.yml:35 publishes RustFS, PUBLIC_SITE_URL compose:61, ACCOUNT_BACKUP_S3_PUBLIC_ENDPOINT, private/elite/BACKUP.md; owed: elite compose up (rediacc_ci.infra.ci_start_elite or ./private/elite/run.sh) and a snapshot from an ops VM outside the docker network |
| backup-program | 575e0098 | J6 | PR-OR-MERGE | ct-tests.yml:2135-2145 runs suite 26 with BACKUP_STORAGE_SUITE=1; accept is a green CI run id on the PR |
| backup-program | 07955f58 | J9 | PR-OR-MERGE | ct-tests.yml:2672 btrfs tier wired (041e3f166); accept is a CI run id |
| backup-program | 6d1a7936 | K2 | LIVE-NOW | case exists packages/e2e-tests/tests/26-backup-storage-cli.test.ts:955, no recorded run; run on ops VM (create_e2e_env --vm-workers 23 23, `rediacc_ci.testrun.e2e` with BACKUP_STORAGE_SUITE=1) |
| backup-program | 388c4a76 | K10 | PR-OR-MERGE | .github/workflows/ct-backup-perf.yml (cron 30 2, dispatch) + suite 31 exist (581206c7b); schedule runs only on main, so first result after the merge (dispatch needs the file on the pushed ref) |
| backup-program | 5330ae20 | K11 | LIVE-NOW | case 26-...test.ts:1203 uses corruptStoredChunk; needs E2E_BACKUP_S3_KEY/SECRET of the dev plane; run suite 26 case on ops VM with the dev RustFS plane |
| backup-program | b5a0a909 | K11a | ALREADY-DONE | fixture packages/e2e-tests/src/utils/backup/chunkCorruption.ts + __tests__/chunkCorruption.test.ts; K11's case imports it (26-...test.ts:25,1212) |
| backup-program | d7be9d49 | N4b | LIVE-NOW | code and 8 CLI tests landed (packages/cli/src/commands/backup-restore-path.ts, __tests__/backup-restore-path.test.ts; PLAN-backup-restore-path R1-R6 ticked); accept's last clause is a bench or edge run of `rdc backup restore --path` rc 0 (plan R L1); bench via Box B |
| backup-program | 8d89e640 | R1 | PR-OR-MERGE | envelope-skew test exists (packages/cli/src/adapters/__tests__/remote-config-adapter.envelope-skew.test.ts); accept needs a live read by the next released CLI |
| backup-program | 5f9f66fa | R4 | OPERATOR | grand-repo mutation (repo expand hermes) needs the operator's REDIACC_ALLOW_GRAND_REPO=hermes; read-only `H machine status hostinger --storage-health` can precede |
| backup-program | 35e210c1 | S1 | ALREADY-DONE | agent/plans/_done/PLAN-backup-credential-isolation.md B1-B7 ticked (B7 revoked backup-s3-20260901T103133Z, token absent from list); private/account/tests/integration/config-blob-key-isolation.test.ts; deploy_bench.py:96-107 no CLOUDFLARE_R2 fallback; check:ci-backup-credential-isolation; C1 probe rc=0 per region (shared-bucket-hardening plan :31) |
| backup-program | f6dcb754 | S5 | LIVE-NOW | code in backup.dto.ts:59-75 and backup-chunk-store.ts:542,734 (finished by PLAN-backup-plane-shared-bucket-hardening A1); owed: drill leg n on RustFS (`PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup --legs n`) and the R2 half on bench (Box B), vitest backup-upload-bounds |
| backup-program | 6875743d | S12 | LOCAL | private/account/tests/integration/backup-isolation-suite.test.ts passes (15, rc=0); owed: mutation proof that reverting each of S2-S8 fails it, and `drills.backup --legs o` (local RustFS) |
| backup-program | 42258f2a | P1 | ALREADY-DONE | P5-P14 ticked on rediacc11/12 with the plane on :4811 (plan :480-503); tick text: stack and VMs were up for those runs |
| backup-program | 9429544f | P2 | LIVE-NOW | no recorded C4 field or `pgrep -a 'renet plugin'` result; `./rdc.sh --dev machine status <vm1> --system` and ssh pgrep on the ops VM |
| backup-program | fa02c94a | P3 | ALREADY-DONE | bp-src and fork bp-src:t1 were used by P5-P10 (tick :484-:497 name bp-src, bp-src:t1) |
| backup-program | 42f309b5 | P4 | ALREADY-DONE | bp-hot strategy bound and scheduled; P11 ticked: rediacc-backup-bp-hot.service ran and `backup status --machine` shows success; G9 contract lives in the gates |
| backup-program | 4cd2aa89 | P13 | LIVE-NOW | rebuild renet with trivial change, `./rdc.sh --dev machine setup <vm1>`, compare container start times and C4 on an ops VM |
| backup-program | bfa6ab14 | P15 | LIVE-NOW | `npm run vm:check -- --changed` plus the J4 backup receipt on the FINAL tree; run last, after the other commits |
| backup-program | dcb51664 | Q0 | LIVE-NOW | push_backup_credentials --target stable exists (secret-supply.json:385) and hostinger already uploads to the eu bucket; owed: secret-name list of the eu stable Worker, rotation dry run showing the cf-r2-backup slug (private/account/scripts/rotation), rollback id |
| backup-program | f45499e6 | Q1 | PR-OR-MERGE | merge through /pr-babysit, then stable EU deploy per the deploy skill |
| backup-program | 4174040a | Q2 | LIVE-NOW | setup rc=0 and status rc=0 recorded 2026-10-29; owed: state-mirror 0644 and every authorized_keys line carrying --guid (same check as D12): `H machine status hostinger` plus read-only term probe |
| backup-program | 8ec9d6d9 | Q3 | ALREADY-DONE | live record plan :514: restart-services rc=0 (482 s), `machine status --containers --health-check` rc=0 all healthy; hermes/demo seeding later re-checked healthy |
| backup-program | 623824c1 | Q4 | ALREADY-DONE | live record plan :518-:519: strategy set rc=0 and `backup strategy show nightly-hot` rc=0 (hosted, policy last=7,daily=7,weekly=4,monthly=6); Q10 tick adds bandwidthLimit 12M |
| backup-program | 1d91e505 | Q5 | ALREADY-DONE | live record plan :519-:520 "Q5 PASSED": snapshot 20261029T074142Z-f7574d96..., usage storedBytes 4,257,218,560, R2 1530 objects by SigV4 ListObjectsV2 on rediacc-backups-eu |
| backup-program | ffca002a | Q8 | ALREADY-DONE | P7 tick (plan :488) is the evidence; tick as a note line citing it |
| backup-program | 8c77d3e7 | Q11 | LIVE-NOW | live records show all 11 repos snapshotted (mail, demo-heartbeat, mautic, marketing, erpnext, observability, gitlab, nextcloud, miscellaneous, demo-stackoverflow, hermes); owed: one read-only `H backup usage` + `H backup manifests <repo>` x11 vs datastore written bytes (the 1568 mautic orphan chunks are a recorded unmetered finding) |
| backup-program | 0d0655ae | Q12 | TIMED | timer rediacc-backup-nightly-hot.timer first fires 2026-10-30T02:00Z; read `H backup status --machine hostinger` and `H backup usage` after it finishes (about 02:30Z or later) |
| backup-program | 61fe2fa7 | Q13 | TIMED | after the 02:00Z run (earliest 2026-10-30 ~02:30Z): `H backup retention preview mail` read-only |
| backup-program | f1d31572 | Q14 | LIVE-NOW | `H backup verify <repo>` spot x11, full on one small repo (demo-heartbeat); read-only, can run now (best after the 02:00Z run is done) |
| backup-program | 9460d3e3 | Q15 | TIMED | `H machine health hostinger` needs backup age inside the interval for every repo; first clean after the 02:00Z run, 2026-10-30 ~02:30Z+ |
| backup-program | e14b9f6a | Q16 | LOCAL | docs/plan record only (CHECKLIST w8, 07-execution-record.md, final tick); accept `check:ci-plan-record` rc=0; do last, after Q12-Q15 |
| agent-tree-lifecycle | a97dd3b2 | S6 | TIMED | sweeper half NOT-BEFORE 2026-10-31 (plan header line 2); drop half waits on 228 docstring citations |
| cloudflare-proxy | e3150839 | B4 | PR-OR-MERGE | suite 29 (packages/e2e-tests/tests/29-proxy-local-executor.test.ts) not on main; first scheduled Console CI run after the merge is the accept |
| cloudflare-proxy | e5ff4d4a | Operator redeploy | LIVE-NOW | `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-proxy -- python3 -m rediacc_ci.deploy.deploy_proxy --target eu` (eu proxy deploy), then `rdc --proxy https://proxy.eu.rediacc.com machine status hostinger`; bench steps 1-3 already green (plan Phase 2 results), step 4 never green |
| cloudflare-proxy | 4ebc4d0b | Teardown | OPERATOR | removes the production proxy; fires when the operator closes the trial or shelves it |
| cloudflare-proxy | 24f82950 | C2 | LIVE-NOW | after the redeploy box is green: set EXECUTOR_MODE/EXECUTOR_URL in workers/account/wrangler.eu.toml and deploy eu (deploy skill, eu deploys need no ask), run one portal console `machine status hostinger` |
| cloudflare-proxy | b00bc9df | LP-bench | LIVE-NOW | Box B; same signature on three plans (cloudflare-proxy, telemetry-export, token-ip-rebind) |
| sync-remote-file-ownership | 7692f2db | LP-hostinger | OPERATOR | box text requires a VERIFIED `npm run vm:check -- --changed` and ASKING the operator first (branch renet restarts router and daemons) |
| telemetry-export | 9b40e7bf | T10 | LIVE-NOW | dashboards on the hostinger observability repo, same path as ticked T12: edit then `H repo up observability -y` and `docker restart observability-grafana`; T9 data prerequisite is ticked |
| telemetry-export | 32531c67 | T11 | LIVE-NOW | Grafana alert provisioning on observability; the disable/re-enable of otlp-bench-traces is `./run.sh rotation` territory the session may drive (memory: no operator steps for observability) |
| telemetry-export | 9cb0a359 | T15 | LIVE-NOW | after the cloudflare-proxy redeploy box: `rdc --proxy https://proxy.eu.rediacc.com machine status hostinger`, then Tempo search through Grafana proxy |
| telemetry-export | b5c07118 | T16 | PR-OR-MERGE | code exists (.ci/rediacc_ci/ops/telemetry_delivery.py, tests, .github/workflows/telemetry-probe.yml; T9 tick rc=0 7 hosts); accept needs the first scheduled run on main (PROXY_CONFIGS still bench only) |
| telemetry-export | b00bc9df | LP-bench | LIVE-NOW | Box B |
| token-ip-rebind | ccc8658a | T9 | OPERATOR | needs an egress IP change (VPN or hotspot) for the live smoke; the eu deploy and removal sweep alone are not enough |
| token-ip-rebind | b00bc9df | LP-bench | LIVE-NOW | Box B |

## Per-class counts (51 boxes)

- ALREADY-DONE: 11 (A4d, E1, K11a, S1, P1, P3, P4, Q3, Q4, Q5, Q8; all in backup-program)
- LIVE-NOW: 22 (backup-program 14; cloudflare-proxy 3; telemetry-export 4; token-ip-rebind 1)
- PR-OR-MERGE: 8 (backup-program 6; cloudflare-proxy 1; telemetry-export 1)
- OPERATOR: 4 (R4, cloudflare-proxy Teardown, sync LP-hostinger, token-ip-rebind T9)
- LOCAL: 2 (S12, Q16)
- TIMED: 4 (Q12, Q13, Q15 at 2026-10-30 after the 02:00Z run; agent-tree-lifecycle S6 NOT-BEFORE 2026-10-31)

Note: signatures in the table are read from the `--plan-investigate` listing.
