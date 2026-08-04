# Final Report: Config-Universe Follow-Up Big-Bang (licensing), 2026-08-04

Status: COMPLETE except two operator actions (below). Everything UNCOMMITTED on the
shared `main` checkout. Plan: `~/.claude/plans/implement-the-follow-up-big-bang-synthetic-walrus.md`.

## What landed

**Wave 1 (testing substrate)** had largely landed before this session via renet #95;
this session closed the leftovers: the CLI derives all licensed-function knowledge from
the generated contract (LICENSE_TIERS accessors + never-stale pin tests), and
`check:ci-renet-tiers` joined npm + manifest + anti-vacuity with three planted-defect
RED proofs.

**Wave 2 (licensing model)**, all seven design holes closed:
- Fork metering: immutable `datastoreId` minted at datastore create, re-minted
  fail-closed at fork; license store scoped
  `/var/lib/rediacc/license/datastores/<dsId>/repos/<guid>/` (clean break; fixes the
  same-GUID parent/fork blob collision); metering rides `missing` + existing
  auto-reissue; migration keeps validating. Kube-repo validation skip narrowed to
  size-only. CSI clone gained a namespace-equality check.
- Self-renewal: `POST /licenses/renew` authenticated by the presented blob (new
  server-side RepoLicense verifier incl. delegated chains + revocation);
  `renet license renew` (flock, jitter, atomic writes, 2xx accepted, 4xx=refused vs
  5xx=error split); `ExecStartPre=-<renet> license renew --jitter 45s` on backup
  units; failure markers `/var/lib/rediacc/license/failed/<guid>.json`; renewalUrl
  (full URL) embedded in every payload.
- Soft-claim slots: renewal always succeeds; over-cap rows flagged `over_limit`
  (migration 0047), self-clearing; surfaced in /licenses/status (overLimitCount),
  portal Machines page, CLI status + login; per-renewal overLimit threaded through
  renew-state (display must gate on outcome=="renewed").
- Cap fix: all live checks read the subscription's `maxActivations` column (partner
  deals up to 10,000 honored); constants seed defaults only. New-issuance
  recount-and-compensate race fix; concurrency tests tightened to exact.
- Per-repo chain state (P1 probe CONFIRMED then fix proven in battery S9c): scope is
  now `<keyId>:<subscriptionId>:<repositoryGuid>`; self-GC on save is the migration;
  write-only LastIssuedAt deleted.
- clusterId telemetry (config cluster name; CA-fingerprint exposure is a known
  limitation), pre-flight slot checks with Enterprise-path messaging, partial-placement
  guidance (nothing rolled back by design).
- Public surfaces in 13 languages: docs (clusters + self-renewal + corrected claims),
  pricing FAQ, ToS 5.5 (operator-approved), all naturalized.

**Wave 3**: `./run.sh drill universe|transfer|license` harness (assertion lib,
selftests, keep-work, loud setup); e2e suite 24 (cluster licensing, declared-skip
discipline); live battery on the 6-VM cluster proven through machine setup + leg f;
CI wiring: new `test-drills` leaf job + suite 24's ACCOUNT tier lit on the multinode
job with an in-job TEST_MODE account server (no org secrets).

## Defects found and fixed along the way (beyond scope, in-session per policy)

1. Airlock stripped chainHash + delegationCert from every license HTTP response
   (field blobs were chain-less; on-prem delegated blobs would fail validation).
2. Batch issuance never touched the issuance ledger (sequence:0 chain-less blobs).
3. Live cap read the plan constant, not the column (partner deals silently capped at 25).
4. Multi-repo sequence_regression (subscription-scoped chain state).
5. Fingerprint format mismatch in three places (scan vs validator vs CLI; unified).
6. CLI wrote licenses to the unscoped path (would have looped reissue forever under
   the scoped store).
7. `repo commit` never had CLI pre-issuance (broken under enforcement all along;
   commit=fork-kind now; commit_meta correctly exempt).
8. nolicense test-tag leg was silently red (now green both variants).
9. i18n gate blindness: cross-locale skipped unmodelled locales (379 German values in
   ar/ja/ru/zh + 59 hidden by a crowd filter), no English detection, renet had no
   locale-value gate at all + a fail-open extractor; 2350+ locale lines fixed
   (incl. 1912 renet garbled lines + 26 romanized-Russian), gates rebuilt around
   @rediacc/locales as single source, shrink-only baselines now at zero.
10. Stop-hook noise: repo-scoped fast-path baseline + frozen latch; fixed with a
    no-op-wake ladder and silent clean stops.
11. Five CLI UX defects from live drills (init key sync, blanket 403 mapping,
    empty-list JSON envelopes across 9 sites, WSL SSH path message, raw WebCrypto
    errors classified via HMAC evidence).
12. Ops-VM SSH divergence root-caused (VMs authorize the renet-staged id_rsa;
    OpenSSH silent fallback masks wrong keys; drills hardened with IdentitiesOnly).

## Final gate state (each verified individually this session)

- `npm run ci` (155 gates): all campaign-owned gates GREEN. In the last full run, the
  only failures were: `check:ci-renet` (2 hardcoded strings in the FOREIGN in-flight
  pkg/infra/docker/service.go, another session's live work, not ours),
  `check:actions` (anonymous GitHub API rate limit, local-only; green with a token:
  "All GitHub Actions are up-to-date (14 up-to-date)"), and one ESLint under-load
  crash that is clean standalone ("Checked 631 files. No fixes applied"). Two
  timing-sensitive CLI tests (update-apply-race, ops-timeout) flaked once under
  full parallel load + 6 VMs and pass 8/8 in isolation.
- License battery `.ci/scripts/private/license-e2e.sh`: exit 0, 24 scenarios incl.
  fork-remeter (S8a-e), per-repo chain (S9a-d, the P1 bug proven closed), fingerprint
  (S10a-b); both controls (nolicense, wrong-key) fail exactly as required.
- Drills: universe 42/42, transfer 33/33, license legs f 5/5 (chainHash survives the
  real HTTP boundary, planted-strip control fires); all selftests exit 1 as designed.
- Test suites: CLI 164 files / 2198 tests; account 81 / 1470+; renet go test green
  both tag variants; e2e 26 unit + suite battery; hook harness 504/0.

## Operator actions outstanding

1. **Live drill legs a-e** (the ancestry-verified overrides forbid agent
   self-authorization, correctly):
   `export REDIACC_ALLOW_CLUSTER_OPS=* REDIACC_ALLOW_GRAND_REPO=*` then
   `./run.sh drill license` (6-VM cluster is UP and left running for this; tear down
   with `./rdc.sh ops down` afterwards).
2. **Push when ready**: the new CI legs (test-drills, suite 24 ACCOUNT tier) are
   first exercised by your push. Deploy order for the licensing changes: account
   servers (migration 0047 + worker) BEFORE renet BEFORE CLI.

## Found-not-fixed ledger (final)

- Foreign in-flight work: pkg/infra/docker pull-retry (their session's; 2 i18n
  findings are theirs to clear).
- Account-side coded 403s for the six enroll causes (CLI branches on message text
  until then; upgrades automatically via code-precedence when added).
- Six commands with NO -o json rendering at all (repo admin template list, machine
  infra cert status, backup strategy list/show, subscription repo status, vscode
  list): a build-json-rendering task, flagged with sites, awaiting packaging call.
- renet `rules.go detectWordBlends` is blind to wholly-ASCII blends; making it
  ASCII-aware needs a per-locale false-positive measurement pass (worklist
  #a607ed3f).
- `renet list` section lacks datastoreId/blockedBackup/lastRenewal (CLI does a second
  license-status read; one-round-trip alternative = 3 fields + contract regen).
- CA fingerprint has no CLI surface (clusterId sends config cluster name).
- check-e2e-coverage's registry self-check is line-scoped (folded YAML invocations
  invisible; documented sharp edge).
- Standing out-of-scope ledger from the design docs: /en/docs/ cross-link sweep (now
  with per-locale counts: ja ~55, ko ~64, pt ~43 + ru/tr files; needs its own gate),
  config-store hardening bundle, invalidSignatureDetected rename, dual-keypair
  consolidation, account.team retirement, tutorial-account integration (#421),
  overage billing atop soft-claim data, uniform executor-layer backup enforcement.

## Rollout notes

- Datastore-resident repos re-issue once on first licensed touch after upgrade
  (clean-break store scope; activation rows refresh, no new slots).
- ENTERPRISE payment-grace no longer collapses the cap to COMMUNITY's 1 (column
  survives until the Stripe webhook resets it).
- Old blobs without chainHash/renewalUrl keep validating; renewal skips no-url blobs
  with a note until the next CLI-driven refresh stamps the field.
- `/test/ensure-subscription` gained `maxActivations` (1..10000) for slot-wall tests.

## New durable assets for future sessions

`.claude/agents/`: licensing-ops, i18n-guardian, ops-vms, account-dev,
config-universe (operational knowledge distilled from this campaign, incl. every
trap named above).
