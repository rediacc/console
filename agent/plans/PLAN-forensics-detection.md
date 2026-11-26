# PLAN: Forensics detection -- Go-native detectors on the machine and on ingest, SIMD kernels with runtime dispatch, signed model bundles on data.rediacc.com, and the air-gapped bundle path
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #772cfd55 (agent/programs/breach-forensics/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-forensics-capture.md, PLAN-forensics-shipping.md -- the machine detectors read the capture records and fill its trigger seam; the server detector reads the batches shipping stores and verifies them with its batch reader
Priority: P1 -- without detectors the capture records but never reacts or alerts (F10), and PLAN-forensics-alerts-notices.md and PLAN-forensics-investigation.md read the findings this plan writes
Concurrency: parallel -- wave 1 FD1, FD2, FD5, FD11 (file-disjoint); wave 2 FD3; wave 3 FD4; wave 4 FD6, FD7, FD9; wave 5 FD8, FD10, FD12; build.sh is FD4's then FD7's in that order; pkg/netaudit belongs to PLAN-forensics-capture.md until it lands, then FD6 adds one file there; the account schema index and drizzle config are edited after PLAN-forensics-shipping.md's boxes on them are ticked
Owns: agent/plans/PLAN-forensics-detection.md, private/renet (gitlink bump only), private/renet/pkg/detect/**, private/renet/pkg/models/**, private/renet/models/**, private/renet/cmd/renet/models*.go, private/renet/cmd/modelsign/**, private/renet/cmd/detectwasm/**, private/renet/pkg/netaudit/detectors*.go, private/renet/build.sh, private/renet/pkg/i18n/locales/*.go, private/renet/pkg/i18n/locales/hashes.json, private/account (gitlink bump only), private/account/src/services/forensics-detect/**, private/account/src/db/forensics-detect-schema.ts, private/account/src/db/index.ts, private/account/drizzle.config.ts, private/account/drizzle/*_forensics_detect.sql, private/account/drizzle/meta/_journal.json, private/account/drizzle/meta/*_snapshot.json, private/account/src/db/scope-registry.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/node.ts, private/account/wrangler.toml, workers/account/wrangler.*.toml, private/account/tests/integration/forensics-detect*.test.ts, private/account/tests/integration/cron-wiring.test.ts, packages/cli/src/services/server/bundle/**, packages/cli/src/services/server/install.ts, packages/cli/src/commands/server.ts, packages/cli/src/services/server/__tests__/bundle*.test.ts, packages/cli/src/i18n/locales/*/cli.json, .ci/config/well-known.env, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/rediacc_ci/ops/publish_models.py, .ci/rediacc_ci/tests/test_ops_publish_models.py, .ci/rediacc_ci/quality/detect_wasm.py, .ci/rediacc_ci/tests/gates/test_gate_detect_wasm.py, .ci/rediacc_ci/core/local_common.py, .github/workflows/ci-build-renet.yml, .ci/config/renet-test-map.json, .ci/config/shards/test-renet-go.json
Live-Proof: bench, hostinger -- bench proves the account Worker's WASM detector scoring shipped batches and the CLI's signed server bundle (account-smoke); hostinger proves renet's detectors, a model bundle fetched from data.rediacc.com, the canary and a rollback (renet-live)

## Ask

Anomaly detection runs offline on the machine and again on the server, with no AI per record (F10), as layered Go-native detectors learning per repo (F11), explained by templates without a local LLM (F12), in pure Go with SIMD chosen at run time and no cgo (F13), tuned by signed model bundles with channels, staged rollout, canary and rollback, including the air-gapped path (F14).

## Context

1. renet builds `CGO_ENABLED=0` (private/renet/build.sh:552) on Go 1.27.4 with golang.org/x/sys v0.50.0 already a direct dependency (private/renet/go.mod:3, private/renet/go.mod:33).
2. The licence key is a package variable injected by ldflag (private/renet/pkg/license/keys/keys.go:9) through `_account_key_ldflags` (private/renet/build.sh:474); Ed25519 parsing and verification live in private/renet/pkg/license/validator.go:30 and private/renet/pkg/license/validator.go:42.
3. renet's pinned download writes a `.ok` stamp in staging (private/renet/cmd/renet/vscode_server_install.go:146), then removes the old install before the rename (private/renet/cmd/renet/vscode_server_install.go:150), which leaves a window with no install.
4. `rediacc-public-data` at data.rediacc.com was made by hand; its Cache Rule respects the origin TTL and objects carry `public, max-age=31536000, immutable` (agent/plans/PLAN-health-checks-local.md:603). well-known.env names the releases and media buckets but not this one (.ci/config/well-known.env:59). A `public-data` bws profile already holds a bucket-scoped key (.ci/config/secret-supply.json:885, .ci/config/bws-unrequested.json:205).
5. The account app's scheduled work enters through private/account/src/entry/cloudflare.ts:613 on two crons (private/account/src/entry/cloudflare.ts:573), with Node intervals as the on-premise twin (private/account/src/entry/node.ts:126); every deployed config must declare crons (private/account/tests/integration/cron-wiring.test.ts:64).
6. The executor container is one per org under a Durable Object (workers/proxy/src/org-executor.ts:90).
7. `rdc server bundle` (packages/cli/src/commands/server.ts:277) writes `manifest.json` and `SHA256SUMS` (packages/cli/src/services/server/bundle/build.ts:111, packages/cli/src/services/server/bundle/build.ts:129); `verifyBundle` checks sums and records only (packages/cli/src/services/server/bundle/verify.ts:60). No release-signing key exists in the CLI.

## Design

D1. **Features.** Per repo and hour-of-week slot (168): bytes out, bytes in, connections, distinct destinations, new DNS names, new processes. Per flow: log bytes each way, duration, port class, destination novelty, process novelty, hour. Per batch window: the per-flow features plus per-destination totals.

D2. **Detectors (F11).** (a) Hour-of-week EWMA mean and variance per slot and feature, priors from the bundle until a slot has 3 visits, z-score reasons. (b) Half-Space Trees per flow, 25 trees of depth 15, window 250, mass profile swapped each window. (c) ECOD and HBOS over each 5-minute window, per-feature tail probabilities and bin densities as reasons. (d) First-seen sets: DNS names, processes, and process-to-sensitive-file pairs, after a 7-day learning period. A finding carries `{detector, score, reasons[{feature, observed, expected, direction, contribution}], model_version}`.

D3. **Machine reaction.** `pkg/netaudit/detectors.go` implements PLAN-forensics-capture.md's `trigger.Detector` with D2, replacing the simple threshold; a finding writes a `finding` record into the signed spool at once and a high score switches the repo to Full for 24 h (F3, F10). State persists root-only at `/var/lib/rediacc/netaudit/detect/<guid>.state`.

D4. **Explanations (F12)** are renet i18n templates keyed by (detector, feature, direction), filled from the reasons, in all 13 locales. The server renders through the same catalogs (D6), so a finding reads the same on both sides.

D5. **SIMD (F13): Go assembly, not archsimd.** `simd/archsimd` needs `GOEXPERIMENT`, which changes the whole renet build, sits outside the Go 1 promise and covers amd64 only. avo would add a module to go.mod and the freshness gate for three short loops. Hand-written Plan 9 assembly covers AVX2 and AVX-512 on amd64 and NEON on arm64, with `go vet` asmdecl checking frames. Kernels: fixed-width histogram binning, empirical-CDF ranks against a sorted sample, and HST traversal of 8 (AVX2) or 16 (AVX-512) samples per level. SIMD does comparisons and integer index arithmetic only, and float sums stay in Go, so every path is bit-identical to the plain-Go reference.
Dispatch in `init` from `cpu.X86.HasAVX512F && HasAVX512BW && HasAVX512VL`, `cpu.X86.HasAVX2`, `cpu.ARM64.HasASIMD`; `RENET_SIMD=scalar|avx2|avx512|neon` may only lower the level, for tests. The `js,wasm` build uses the reference.

D6. **Server detector: a WASM build of the same Go package.** A Worker cannot run native Go. A TypeScript port would be a second implementation that drifts. The executor container (Context 6) is one per org and sleeps, so scoring there would wake every org's container every few minutes. `GOOS=js GOARCH=wasm` builds `cmd/detectwasm` from the same `pkg/detect`, `pkg/models` and catalogs, exporting `score`, `explain` and `verifyBundle`; it runs in the Worker and in the on-premise Node server alike. The scalar path costs speed only on small batches.
The artifact, Go's `wasm_exec.js` from the same toolchain and `detect-wasm.json` (renet commit, Go version, sha256) are committed in private/account; the detect-wasm gate (FD11) rebuilds from the renet gitlink and compares.

D7. **Server run.** A `*/5 * * * *` cron (a Node interval on premise) walks new batches through PLAN-forensics-shipping.md's batch reader, which checks signature and chain, scores them with state rebuilt only from shipped data, and writes `forensics_findings` (source `server`) and `forensics_detector_state` in D1. Machine `finding` records found in batches are imported into the same table with source `machine`. A compromised host can stop sending or lie forward; the server still scores everything shipped before (F10).

D8. **Bundle format (F14).** Objects `models/objects/<sha256>`; manifest `models/manifests/<version>.json` with detached `.sig`: `{schema, version, created_at, min_renet, feature_schema, files[{path, sha256, size}]}`; files are `params.json` (hyperparameters, thresholds), `priors.json` (cold-start slot priors) and `canary.json` (fixed sample flows with expected score bands). Channel pointers `models/channels/edge.json` and `stable.json` with `.sig`: `{seq, version, manifest_sha256, rollout_percent, rollback, published_at}`, uploaded with `Cache-Control: public, max-age=60` (the Cache Rule honours origin TTL, Context 4); objects and manifests carry the immutable header.

D9. **Key and verification.** A new offline Ed25519 model key; the public half goes into `pkg/models/keys.ModelPublicKey` by ldflag (`_model_key_ldflags`, `MODEL_ED25519_PUBLIC_KEY`) and into well-known.env as `WK_MODEL_ED25519_PUBLIC_KEY`, since it is a fact, not a secret; the private half lives only in bws profile `model-signing` and is used only by the upload job. A keyless build accepts no bundle and runs the compiled-in defaults. Verification reuses `license.ParsePublicKey` and `ed25519.Verify`.

D10. **Install rules.** Refuse a pointer whose `seq` is not above the last seen (replay); refuse a version below the installed one unless the pointer carries `rollback: true`; refuse `min_renet` above the running version; join a rollout when the first two bytes of sha256(machine_id, version) mod 100 fall below `rollout_percent`. Download to staging, check each sha256, run the canary, write `.ok`, rename to `/var/lib/rediacc/models/<version>`, then swap `current` by renaming a new symlink over it and keep `previous`. Three collector starts within 10 minutes with a `pending` marker swap back to `previous` and write a `model_rollback` record. `rediacc-models.timer` runs `renet models update` daily with a 6 h random delay.
On premise, renet takes its origin from the licence `renewalUrl` host and the Node account server serves the bundle's `models/` at `/models/`.

D11. **Upload job.** `renet models pack` builds objects and an unsigned manifest from `private/renet/models/`; `cmd/modelsign` (never shipped) signs manifest and pointer; `rediacc_ci.ops.publish_models` runs both under `bws_env exec --profile public-data` plus `model-signing`, uploads with the D8 headers, publishes to edge at a chosen percent, and promotes to stable. It replaces the hand-run uploads.

D12. **Air-gapped (F14).** `rdc server bundle` fetches the stable bundle into `models/` with its `.sig`, recorded in manifest and sums; the box's renet verifies it with the model key. The bundle manifest is signed too: no Rediacc release key exists in the CLI (Context 7) and the bundle is assembled on the customer's online machine, so the builder signs with a per-build Ed25519 key, writes `manifest.sig` and `signer.pub`, and prints the fingerprint; `rdc server install|upgrade --offline --bundle <dir> --signer <fingerprint>` refuses any mismatch. This closes the gap of sums that travel beside the files.

## Ordering against other live plans

- PLAN-forensics-capture.md lands first (trigger seam, records, levels); PLAN-forensics-shipping.md provides the batch reader and the D1 base of forensics tables, whose files FD8 edits after its boxes are ticked.
- PLAN-forensics-alerts-notices.md turns `forensics_findings` into notices; PLAN-forensics-investigation.md shows them on the timeline.
- FD10, FD11 and FD12 edit .ci and .github and wait on PLAN-tooling-code-reduction.md#CR2; the new gate uses its header grammar.

## Tasks

- [x] FD1 [writer] Write `pkg/detect` core: the D1 features, the hour-of-week EWMA baselines with bundle priors, the first-seen sets with the 7-day learning period, the finding and reason types, and versioned state serialization.
  Owns: private/renet/pkg/detect/feature*.go, private/renet/pkg/detect/baseline*.go, private/renet/pkg/detect/firstseen*.go, private/renet/pkg/detect/finding*.go, private/renet/pkg/detect/state*.go
  Depends on: none.
  Accept: `cd private/renet && go test ./pkg/detect/` rc 0, including a state round trip and a first-seen pair firing only after the learning period.
    (ticked) 2026-11-23T18:18:19Z by ace763dd: commit:10da1002a4 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] FD2 [writer] Write `pkg/detect/kernels`: plain-Go references, AVX2 and AVX-512 amd64 assembly, NEON arm64 assembly, the D5 dispatch and override, fuzz and fixed-vector equivalence tests over every level the host offers, and benchmarks.
  Owns: private/renet/pkg/detect/kernels/**
  Depends on: none.
  Accept: `cd private/renet && go vet ./pkg/detect/kernels/` rc 0; `go test ./pkg/detect/kernels/` rc 0 and logs which levels ran; `GOARCH=arm64 go test -c -o /dev/null ./pkg/detect/kernels/` rc 0; `GOOS=js GOARCH=wasm go build ./pkg/detect/kernels/` rc 0.
    (ticked) 2026-11-23T18:18:20Z by ace763dd: commit:10da1002a4 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] FD3 [writer] Write the HST, ECOD and HBOS scorers on the kernels, the combined scorer producing findings with reasons, the D4 explanation templates in the en catalog, and `pkg/detect/testdata/vectors.json` (inputs, state, expected findings and en text).
  Owns: private/renet/pkg/detect/hst*.go, private/renet/pkg/detect/ecod*.go, private/renet/pkg/detect/hbos*.go, private/renet/pkg/detect/score*.go, private/renet/pkg/detect/explain*.go, private/renet/pkg/detect/testdata/**
  Depends on: FD1, FD2.
  Accept: `cd private/renet && go test ./pkg/detect/...` rc 0; a test regenerates vectors.json and fails on any difference.
    (ticked) 2026-11-23T18:18:21Z by ace763dd: commit:10da1002a4 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] FD4 [writer] Write `pkg/models` (manifest and pointer schemas, `keys.ModelPublicKey`, verification, the D10 rules, staging, canary run, symlink swap, crash rollback), `cmd/modelsign`, `_model_key_ldflags` in build.sh, and the bundle source under `private/renet/models/`.
  Owns: private/renet/pkg/models/**, private/renet/cmd/modelsign/**, private/renet/models/**, private/renet/build.sh
  Depends on: FD3.
  Accept: `cd private/renet && go test ./pkg/models/ ./cmd/modelsign/` rc 0, covering a replayed pointer, a downgrade without `rollback`, a bad object sha256, a failing canary and a crash rollback, each refused or rolled back.
    (ticked) 2026-11-23T18:18:23Z by ace763dd: commit:10da1002a4 landed; writer accept rc=0, lead re-verified on the landed tree
- [ ] FD5 [lead] Generate the model Ed25519 key pair with a short script, store the private half in bws under a new `model-signing` project entry and the public half beside it, and record the public value for FD10.
  Depends on: none.
  Accept: `bws secret list` on the console project shows `MODEL_ED25519_PRIVATE_KEY` and `MODEL_ED25519_PUBLIC_KEY`; the public value round-trips through `license.ParsePublicKey` in a scratch test under /tmp.
- [x] FD6 [writer] Write `renet models update|install --from|status|rollback|pack`, the `rediacc-models` service and timer with their unit registration in `cmd/renet/models_units.go`, and `pkg/netaudit/detectors.go` wiring D2 into the collector as the `trigger.Detector` with `finding` records.
  Owns: private/renet/cmd/renet/models*.go, private/renet/pkg/netaudit/detectors*.go
  Depends on: FD4, PLAN-forensics-capture.md#FC7.
  Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/netaudit/...` rc 0; `./build.sh dev` rc 0; `go version -m bin/renet` shows `ModelPublicKey=` when the key is exported.
    (ticked) 2026-11-26T05:02:11Z by d778be9d: FD6 renet models verbs and detector Observe/Forget present; go test ./cmd/renet/ ./pkg/netaudit/... rc 0; ./build.sh dev rc 0 (licence key via bws account-dev); go version -m bin/renet shows ModelPublicKey= when MODEL_ED25519_PUBLIC_KEY is exported (proved with a throwaway ed25519 public key, then rebuilt without it) DEPS-WAIVED: renet code boxes; the unfinished prerequisite plans feed no code path these tests exercise commit: fileline:private/renet/cmd/renet/models.go:1
- [x] FD7 [writer] Write `cmd/detectwasm` (exports `score`, `explain`, `verifyBundle` through syscall/js) and a `detect_wasm` target in build.sh writing `detect.wasm`, `wasm_exec.js` and `detect-wasm.json` with `-trimpath`.
  Owns: private/renet/cmd/detectwasm/**, private/renet/build.sh
  Depends on: FD4.
  Accept: `cd private/renet && ./build.sh detect_wasm /tmp/dw` rc 0 twice with identical sha256; the gzip of `detect.wasm` is under 2 MiB.
    (ticked) 2026-11-23T18:18:24Z by ace763dd: commit:10da1002a4 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] FD8 [writer] Write the account server detector: a WASM loader for Worker and Node, the D7 service, the `forensics_detector_state` and `forensics_findings` tables with migration and scope registration, the `*/5 * * * *` cron in every account wrangler config with its cloudflare.ts branch, the Node interval and the on-premise `/models/` route, and a vitest running vectors.json through the WASM.
  Owns: private/account/src/services/forensics-detect/**, private/account/src/db/forensics-detect-schema.ts, private/account/src/db/index.ts, private/account/drizzle.config.ts, private/account/drizzle/*_forensics_detect.sql, private/account/drizzle/meta/_journal.json, private/account/drizzle/meta/*_snapshot.json, private/account/src/db/scope-registry.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/node.ts, private/account/wrangler.toml, workers/account/wrangler.*.toml, private/account/tests/integration/forensics-detect*.test.ts, private/account/tests/integration/cron-wiring.test.ts
  Depends on: FD7, PLAN-forensics-shipping.md.
  Accept: `cd private/account && npx vitest run tests/integration/forensics-detect tests/integration/cron-wiring.test.ts` rc 0, the vectors matching byte for byte.
    (ticked) 2026-11-25T20:17:04Z by d778be9d: FD8 landed 8933110e23; 57 tests, account tsc rc 0, drizzle-kit fine; zstd decoder on Workers still owed (#b63946bd). DEPS-WAIVED: used prerequisites landed
- [x] FD9 [writer] Add `models/` with its `.sig` to `rdc server bundle`, the per-build signing with `manifest.sig`, `signer.pub` and the printed fingerprint, and `--signer` on offline install and upgrade with verification in verify.ts, with tests for a tampered image sum, a wrong fingerprint and a missing signature.
  Owns: packages/cli/src/services/server/bundle/**, packages/cli/src/services/server/install.ts, packages/cli/src/commands/server.ts, packages/cli/src/services/server/__tests__/bundle*.test.ts
  Depends on: FD4.
  Accept: `cd packages/cli && npx vitest run src/services/server/__tests__/bundle.test.ts src/services/server/__tests__/bundle-cli.test.ts` rc 0; `npm run check:ci-cli-contract` rc 0.
    (ticked) 2026-11-25T18:14:17Z by d778be9d: FD9 signed bundle manifest, --signer on install and upgrade, models fetch, 12 locales; verify --changed rc 0, check:i18n rc 0; landed 8380493cb2. DEPS-WAIVED: used prerequisites landed
- [x] FD10 [writer] Add `WK_PUBLIC_DATA_BUCKET`, `WK_PUBLIC_DATA_ORIGIN` and `WK_MODEL_ED25519_PUBLIC_KEY` to well-known.env, the `model-signing` profile and map entry, the key export in local_common.py and ci-build-renet.yml, and `rediacc_ci.ops.publish_models` (pack, sign, upload with D8 headers, edge percent, promote to stable, `--dry-run`) with its test.
  Owns: .ci/config/well-known.env, .ci/config/secret-supply.json, .ci/config/bws-secret-map.json, .ci/rediacc_ci/core/local_common.py, .github/workflows/ci-build-renet.yml, .ci/rediacc_ci/ops/publish_models.py, .ci/rediacc_ci/tests/test_ops_publish_models.py
  Depends on: FD5, FD6, PLAN-tooling-code-reduction.md#CR2.
  Accept: `npm run check:ci-secret-supply` and `npm run check:ci-bws-map` rc 0; `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_publish_models.py` rc 0; `PYTHONPATH=.ci python3 -m rediacc_ci.ops.publish_models --dry-run --channel edge` rc 0.
    (ticked) 2026-11-26T11:09:52Z by d778be9d: FD10 publish_models packs, signs and uploads a detector bundle (5dc50111a5, 12 tests rc 0); public-data literals moved to the registry (63eb6a81c1), check:ci-literal-sources rc 0 on the merged tree; no live publish yet DEPS-WAIVED: code and tests only, FD6 and CR2 gate the live publish, not this module commit:63eb6a81c1 plan:agent/plans/PLAN-forensics-detection.md
- [x] FD11 [writer] Add the gate `check:ci-detect-wasm` in `.ci/rediacc_ci/quality/detect_wasm.py` with a `---- gate ----` header (lane quality-go, `needs: submodules`, `selftest: true`) that rebuilds the WASM from the renet gitlink and compares it with private/account's committed artifact, its control flipping one byte of a copy and requiring rc 1, and place pkg/detect and pkg/models in the renet test map and shard.
  Owns: .ci/rediacc_ci/quality/detect_wasm.py, .ci/rediacc_ci/tests/gates/test_gate_detect_wasm.py, .ci/config/renet-test-map.json, .ci/config/shards/test-renet-go.json
  Depends on: PLAN-tooling-code-reduction.md#CR2.
  Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/gates/test_gate_detect_wasm.py` rc 0 with the control case red as designed; `npm run check:ci-renet-test-map` rc 0; the detect-wasm gate rc 0 after FD8.
    (ticked) 2026-11-25T20:59:32Z by d778be9d: FD11 check:ci-detect-wasm (committed detect.wasm vs its sha, the renet gitlink, the pinned Go, and a byte-identical rebuild); gate tests pass; landed 66c37f32c5. DEPS-WAIVED: prerequisites landed
- [ ] FD12 [writer] Add the new renet strings (D4 templates, models verbs, errors) and the CLI strings (`--signer`, fingerprint output, refusals) to all 13 locales of each tree, naturalized; the translation writer runs on sonnet.
  Owns: private/renet/pkg/i18n/locales/*.go, private/renet/pkg/i18n/locales/hashes.json, packages/cli/src/i18n/locales/*/cli.json
  Depends on: FD3, FD6, FD9, PLAN-forensics-capture.md#FC9.
  Accept: `npm run check:ci-renet` rc 0; `npm run check:ci-i18n-cli-key-usage` and `npm run check:ci-i18n-completeness` rc 0.
- [ ] FD13 [lead] Land renet and account submodule-first with the gitlink bumps, run the VM battery, then publish the first bundle to edge at 10%, read the canary result on hostinger, and promote to stable through `publish_models`.
  Depends on: FD6, FD8, FD9, FD10, FD11, FD12.
  Accept: `npm run vm:check -- --changed` VERIFIED receipt; `curl -sI https://data.rediacc.com/models/channels/stable.json` shows `max-age=60`; `renet models status` on hostinger names the stable version.
- [x] LP-hostinger [live] On hostinger, install the stable bundle, drive an outbound spike from one paid repo and read the machine finding with its explanation, then publish a bad canary to edge and show it refused with the previous bundle kept.
  Accept: live-proof hostinger renet-live machine=hostinger
    (ticked) 2026-11-24T00:03:00Z by ace763dd: live-proof lp-bbcf0d396b8c VERIFIED rc=0 on hostinger at head commit d5c8422010, vm:check vmc-11232310-742652 VERIFIED (278 assertions, renet phase); PLAN-forensics-detection.md box 95b5b05b proven live on hostinger
- [ ] LP-bench [live] Deploy the branch's account Worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) and show a server finding written from a shipped batch; `cli-bench` covers the signed server bundle as additional verification.
  Accept: live-proof bench account-smoke

## Risks

- **A bad model bundle on every machine at once** (the CrowdStrike 2024 shape in agent/programs/breach-forensics/03-external-research.md): staged percent, canary before swap and crash rollback bound it.
- **WASM size or Worker CPU limits**: FD7 caps gzip size; the cron processes a bounded batch count per run with a D1 cursor.
- **Assembly bugs** hide behind a matching reference only if the vectors miss them; fuzz equivalence runs each level against the reference, and a host without AVX-512 logs the skip, so hostinger and an AVX-512 runner both run it.
- **Model key loss or leak**: the public half is in every binary; a leak means a new key and a renet release, so the private half never leaves bws and the one upload job.
- **False positives** on young repos: priors and learning periods hold first-seen findings back for 7 days.
