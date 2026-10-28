## SESSION d778be9d 2026-10-28T11:03:17Z

# STATE d778be9d (branch 1023-1, unpushed, no PR; turbo batch-end)

## Durable rules
- Commit by path, message file in its own call, PR-TASK 9f92c43e, submodules first then the pointer. On gen-docs drift run `npx --no-install tsx scripts/gen/gen-docs.ts --write` before commits that touch .ci, shards or guards. Plan edits: `npm run check:ci-plan-record -- --update`.
- Writer briefs carry `Owns:` and, when the Owns sit inside a plan's Owns, `Plan:` (the plan-concurrency guard judges declared Owns).
- Stable deploys: RELEASE_ASKED=ASKED:2026-10-28T07:56Z. Edge and bench free.
- Sweep ruling ASKED:2026-10-28T10:58Z: an unstarted plan past 90 days is asked (keep or archive), never auto-deleted (#d2e1ef28).

## Big pieces
- Durable wave stopped at bench L0 (stable approved ASKED 07:56Z, ruling ff76eb9e9). Cloudflare egress IPv4 cannot reach hostinger; IPv6 retry fafbb7b60; bench retry running (a84ca1da).
- PLAN-backup-restore-path: R1, R2, R3 ticked (R2 tick bf2227d93); perf fix renet 7c3cf0a (35.46 s -> 1.30 s per 100k files); R4 writer running.
- PLAN-tested-on-bench: V6 gate uncommitted in the working tree (.ci/scripts/quality/check_plan_live_proof.py, its test, package.json, gates.lock.json, lane-durations.json); re-add manifest.ts entry and ci-quality.yml step once #629586d9 findings are fixed.

## Delegated
- a84ca1da19151ea88 / #a150016d: bench IPv6 retry + durable L0; owns workers/proxy/wrangler.bench.toml; accept E1 27-90/27-91 rc 0 on durable.
- a1346a3f85aa193db / #b52a181e: restore-path R4; accept sudo go test ./pkg/restorepath/... ./cmd/renet/ -run 'TestRestorePath|TestPlan|TestBackupRestorePath' no SKIP. Lead then runs the renet_types regenerate.
- aa4950bb069054307 / #3e440368: 9 renet review findings (22fe263d.1-3, 675a01f8.1-2, 18ecc8bb.1-4); owns luks/resize.go, repodiff types + browse_list_test, chunkstore/download.go, backup_snapshot_toc*.go.
- ace03099ae56b9c4d / #d2e1ef28: sweep asks before backlog delete; owns check_plan_folders.py, plan_lifecycle.py, test_gate_plan_folders.py, plan-lifecycle.json.

## Done this context
- Captcha incident: deploy_account shipped a keyless portal dist; guard, gates and a 6-hourly probe (a43d7f085, 760ca2d13, 368916992).
- hermes prune on hostinger finished (5.185 GB freed); about 20 GB of orphan overlay2 directories left, deletion not authorized.

## Next action
1. Settle the low review findings 771df6eb.1-4 and 94cc8bd4.1 (this STATE fixes 771df6eb.1-4), then as each writer reports: spot-check, rerun its accept, commit by path (renet then pointer), tick or review-mark fixed <sha>.
2. R4 done -> R5 writer (CLI flags), then R6, L1 hostinger, R7.
3. a84ca1da reports -> L0 rows, wave edge x3 + stable x3, E10 edge-us, then C1/L7.
4. #629586d9 V6 findings, #25705d33, #a0f61e00, #6595b14c, #6dd4e3ff; then ci:quick, backup push, PR.
