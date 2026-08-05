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

## Live battery results (added 2026-08-04 evening — the drill ran, and it earned its keep)

`./run.sh drill license` is **39/39 GREEN** (final logs full16/17/18 in the session
scratchpad), after an iterative run that caught NINE more defects the entire offline
pyramid had missed — every one fixed in-session:

1. **Poisoned renet build artifact**: bin/renet had been overwritten by a foreign bare
   `go build` (enforcing flavor, NO key baked) and the build stamp only fingerprinted
   inputs, so the wrong binary kept deploying — every validation failed
   "public key not configured". Fixed three ways: stamp now fingerprints the artifact
   (.ci/lib/local-common.sh), the drill pins its flavor (RDC_RENET_LICENSE=1) and
   proves it pre-deploy (verify_renet_flavor), knowledge agents document the trap.
2. **Config schema rejected datastore fork keys** (`name:tag` → "Invalid key in
   record", poisoning every later config load). Fixed: datastoreRef key grammar in
   schemas.ts + state-schema.ts, pin tests.
3. **Fork mount naming**: renet mounts a fork at `<parent>-<tag>` (hyphen);
   namedDatastoreMount() and the drill probe both assumed the ref's colon. Fixed at
   the single derivation point.
4. **Chain state lacked the datastore scope** (S8d live catch): parent and datastore
   fork share a repo GUID, so the fork's fresher reissue regressed the parent →
   sequence_regression. Fixed: 4-part chain key
   `<keyId>:<subscriptionId>:<repositoryGuid>:<datastoreId>`, self-GC migration,
   13-language license-chain.md delta.
5. **`repo migrate` never declared the repo's datastore** (five executor legs ran
   against the default pool). Fixed + the leg-b contract corrected: a repo-level
   migrate OUT of a datastore re-meters BY DESIGN; identity travel is a DATASTORE
   move (`datastore attach --to`).
6. **Datastore relocation could strand the datastore attached nowhere** (detach
   succeeded, target refused "not registered"). Fixed with renet's own
   `datastore_adopt`, adopt-before-detach (non-destructive first).
7. **The E2E tunnel laundered every caller's IP to 'unknown'**, silently disabling
   api-token IP binding for all CLI traffic. Fixed server-side (app.ts threads the
   outer address inward, drops spoofable envelope forwarding headers).
8. **The missing-datastore CLASS (20 sites)**: 16 dispatch sites lacking
   ExecuteOptions.datastore (a named-datastore repo could not be deleted, promoted,
   committed, logged, exec'd, trimmed, gc'd, backed up...) + 4 repository_list
   sites blind to named datastores (fsck called their refs dangling). One
   comprehensive sweep, 21 behavior-pin tests, full suite 2244/2244.
9. **`backup restore --datastore` dropped its flag** (image landed in the default
   pool with no placement recorded — permanent divergence). Fixed as a birth-record
   placement write, not a one-shot mount declaration.

Also proven by the battery: renewal from a credential-less machine (the blob is the
credential), per-repo refusal codes on a lapsed subscription, soft-claim over-cap
with visible overage, and chainHash surviving the HTTP boundary with a planted-strip
control.

## Operator actions outstanding

1. ~~Live drill legs a-e~~ **DONE 2026-08-04 evening** — 39/39, see above. VMs still
   up; tear down with `./rdc.sh ops down` when the wave is done.
2. **PR wave 0804-1 in flight overnight** (delegated babysitter): console #551
   (draft) + renet #98 + account #74. The new CI legs (test-drills, suite 24 ACCOUNT
   tier) get their first exercise here. Deploy order unchanged: account servers
   (migration 0047 + worker) BEFORE renet BEFORE CLI.
3. **Submodule Claude-Review tokens — one mandatory paste**: renet+account
   repo-level CLAUDE_CODE_OAUTH_TOKEN secrets (created 07-28) were dead (every
   review run 401 since). The overnight org-inherit experiment REFUTED the org
   route structurally: the org is on GitHub Free, which delivers org secrets to
   PUBLIC repos only — console (public) gets them, renet/account (private) never
   can. The dead repo secrets were deleted during the experiment (tombstone in the
   babysit round log; nothing lost — dead token, zero successful runs ever), org
   scoping reverted to console-only. THE FIX: paste console's working
   CLAUDE_CODE_OAUTH_TOKEN value (repo-level secret, created 2026-02-16) into
   repo-level secrets on rediacc/renet and rediacc/account. Structural alternative:
   upgrade the org to Team. Until then submodule Claude-Review reds are expected
   and non-required.

## The pattern worth naming: "works on the operator's box"

Three separate CI reds on the night of 2026-08-04 shared one shape — a dependency
that is warm, present, or already running on the operator's workstation and cold,
absent, or unstarted on a fresh runner. None was detectable by reading code, and
each cost a CI round to find:

1. **`llvm-strip` absent on runners.** renet's `ebpf_generate` probed for `clang`
   only; bpf2go also shells out to `llvm-strip`, so a runner with clang and no llvm
   binutils took neither the mtime skip nor the documented pre-committed-objects
   fallback. Fixed by probing both tools.
2. **A 434MB image pull that is cached locally.** `rustfs/rustfs:latest` is resident
   on the operator's box, so `./run.sh account dev` never pays the pull there.
3. **A liveness probe that returns true for a dead port** (the sharpest of the
   three, and the one the other two disguised). `.ci/lib/account.sh`'s
   `account_rustfs_alive` ran `code=$(curl -w '%{http_code}' ... || echo 000)`; on a
   refused connection curl PRINTS `000` and exits non-zero, so `|| echo 000` appends
   a second one and the captured value is `000000`, which is `!= "000"` — so the
   probe reported ALIVE. On a fresh runner that made `account_dev` announce
   "Reusing RustFS already serving on port 9100", never start the container, and
   export `CONFIG_R2_*` anyway; the gateway then advertised config storage that did
   not exist and the drill died on `ECONNREFUSED`. Masked on the operator's box
   because RustFS genuinely IS listening there. **Blast radius is wider than CI**:
   every developer whose RustFS is not already up got the same false reassurance.

The lesson generalizes past these three: a check that cannot distinguish "absent"
from "present" is worse than no check, because it converts a loud failure into a
confident lie — and the operator's own environment is the one place that lie is
never exposed.

## Found-not-fixed ledger (final)

- **renet `build.sh::ebpf_generate` staleness guard is mtime-based** (`.o -nt .c`).
  Git does not preserve mtimes, so on a fresh checkout the committed BPF object is
  never newer than its source and the fast path can never fire — CI attempts a
  regeneration on every run. Found live 2026-08-04 when the Drills CI leaf reded:
  bpf2go also shells out to `llvm-strip`, which the capability probe did not check,
  so a runner with clang but no llvm binutils took neither the skip nor the
  documented "use pre-committed BPF objects" fallback. The probe was fixed (renet
  c74e0e8, proven with a control under the runner's exact toolchain condition); the
  mtime guard was deliberately NOT touched — smallest correct fix. Residual hazard,
  pre-existing and identical for missing clang before this change: editing
  `socket_isolation.c` on a host without the toolchain silently uses stale objects.
  The real cure is a content-hash guard replacing the mtime guard, which changes
  when regeneration fires for every developer and CI job and therefore needs its
  own verification pass (fresh checkout / edited source / unchanged source, each
  with and without the toolchain).
- **`validate:translation-freshness` cannot distinguish an honest hash bump from a
  lazy one.** `computeEnglishDiff` diffs English-at-sourceCommit against
  English-now and never inspects locale content; the only content-ish check is a
  40%-of-English line-count floor. Its "Sections added (translate and add these)"
  message describes the ENGLISH delta, which reads as "the locale is missing this"
  and nearly caused 12 already-correct professional translations to be rewritten
  on 2026-08-04. A gate that is satisfiable by bumping a hash cannot tell a
  finished translation from an absent one.

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
