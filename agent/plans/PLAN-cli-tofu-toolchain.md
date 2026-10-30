# PLAN: rdc installs a pinned, checksum-verified OpenTofu itself (rdc tools install tofu), doctor reports missing local tools, and cloud providers are pinned by hash

Status: approved -- operator 2026-10-29 "we must also think about other machines (customers') so maybe rdc doctor warn or maybe rdc install local may install?"; ASKED answers: Install command + doctor, Pin provider hashes, PATH-only fallback (worklist #9a7c3258)
Depends-On: no-dep -- the CLI tools service, the pins leaf and doctor need nothing outside this plan
Owner: d778be9d
Priority: P1 -- `rdc machine provision` fails on every host without tofu ("Neither OpenTofu (tofu) nor Terraform (terraform) is installed", packages/cli/src/services/tofu/executor.ts:69-79), which blocked the R2-to-Linode DR proof on 2026-10-29; customers on Linux, macOS and Windows hit the same wall with an unpinned manual install
Owns: agent/plans/PLAN-cli-tofu-toolchain.md, .ci/config/pins.json (the cli-tool:opentofu and tofu provider leaves only), scripts/pins/**, packages/cli/src/services/tools/** (new), packages/cli/src/commands/tools.ts (new), packages/cli/src/commands/__tests__/tools*.test.ts (new), packages/cli/src/services/tofu/executor.ts, packages/cli/src/services/tofu/tf-generator.ts, packages/cli/src/services/tofu/provider-registry.json, packages/cli/src/services/tofu/__tests__/**, packages/cli/src/commands/doctor.ts, packages/cli/src/commands/__tests__/doctor*.test.ts, packages/cli/src/cli.ts (one register call), packages/cli/src/i18n/locales/*/cli.json, packages/shared/src/cli-contract/data/** (regenerated only), packages/www/src/content/docs/*/cli-application.md (regenerated only), .devcontainer/toolchain.env, .devcontainer/Dockerfile, run.sh (the setup step that calls rdc tools install tofu)
Concurrency: parallel -- the tools service, doctor and the pins leaf have disjoint files; T3 waits for T1's generated constants
Live-Proof: bench -- the DR proof of PLAN-backup-program provisions a temporary bench-side Linode through this install path, which is the live proof that a fresh host can provision
Updated: 2026-10-29
First-Seen: 2026-10-29
Worklist: #9a7c3258, PR-TASK 9f92c43e

## Finding (read-only investigation, 2026-10-29)

- Lookup: TofuExecutor.resolveBinary tries `tofu version` then `terraform version` on PATH with no version floor (executor.ts:69-79); provisioning calls it first (provision.ts:109, cluster-provision.ts:128).
- No plugin cache: each machine's work dir `<configDir>/tofu/<machine>/` re-downloads its provider on `init`; the 31 providers in provider-registry.json carry only `~>` ranges and no lock hashes.
- rsync is not embedded locally either (remote/sync/rsync.ts:21-37); the SEA embeds only renet (.ci/rediacc_ci/build/prepare_cli_assets.py:128-140). `rdc doctor` exists (commands/doctor.ts:507) but checks neither tofu nor rsync, and its commandExists shells out to `which`, which Windows lacks (doctor.ts:44-50).
- Pins: `.ci/config/pins.json` leaves model a release-age pin with per-platform sha256 sites (toolchain:shfmt at :1869-1941); no leaf has Windows checksum roles yet, and the pins driver verifies no signatures.
- The provider token in main.tf.json was world-readable; fixed in 1e9a72f02 (0700 dir, 0600 file).

## Decisions (operator, 2026-10-29)

1. Delivery: an explicit `rdc tools install tofu` plus a doctor check; no embedding, no lazy download.
2. Providers: lock hashes committed through a pins leaf, plus a shared plugin cache.
3. Terraform: accepted only when the user installed it on PATH; rdc never installs or bundles it (BUSL); both engines need a version floor.

## Boxes

- [x] T1 [opus] Pins leaf `cli-tool:opentofu`: an exact version at least 1440 minutes old, sha256 sites for linux, darwin and windows on amd64 and arm64 (new Windows roles in the driver), and a generated TS constants file the CLI imports, so the checksums ship inside rdc. Accept: `npm run pins -- lockfiles` and the pins gates rc 0, and a changed checksum fails the pins check.
    (ticked) 2026-10-29T17:14:34Z by d778be9d: commit:21f9b926d check:ci-pin-registry rc=0, pins verify rc=0
    (review note 2026-10-29, 9f92c43e) The changed-checksum half of the Accept, run at 2026-10-29T22:40Z: one sha256 in packages/cli/src/services/tools/opentofu-pin.generated.ts altered, `npm run pins -- verify` rc=1 ("the sha256:linux-amd64 sites disagree") and `npm run check:ci-pin-registry` rc=1 against scripts/pins/data/opentofu/SHA256SUMS:27, then the file restored byte-identical.
- [x] T2 [opus] The pins driver verifies the OpenTofu release SHA256SUMS against its cosign signature at bump time, refusing a bump whose signature does not verify. Accept: the pins driver tests rc 0, with a tampered SUMS file refused.
    (ticked) 2026-10-29T17:14:37Z by d778be9d: commit:21f9b926d signed-release selftest 13 controls rc=0, verify-record with cosign rc=0
- [x] T3 [opus] packages/cli/src/services/tools: platform map, download over HTTPS, sha256 check against the T1 constants before anything is extracted, zip/tar extraction, atomic placement into rdc's tools dir (`@rediacc/shared/paths`), and `rdc tools install|list` with i18n in 13 locales. A checksum mismatch deletes the download and refuses. Accept: `cd packages/cli && npx vitest run src/commands/__tests__/tools` rc 0, covering the bad-checksum refusal, an interrupted download, and Windows paths.
    (ticked) 2026-10-29T17:14:40Z by d778be9d: commit:95a124a7c tools vitest rc=0; rdc tools install tofu placed 1.13.2 rc=0
- [x] T4 Executor lookup order: REDIACC_TOFU, then rdc's tools dir, then tofu on PATH, then terraform on PATH; a version floor for both; the not-installed error names `rdc tools install tofu`; TF_PLUGIN_CACHE_DIR set to a shared cache dir. Accept: `npx vitest run src/services/tofu` rc 0.
    (ticked) 2026-10-29T17:14:44Z by d778be9d: commit:95a124a7c executor-resolve tests rc=0
- [x] T5 Doctor gains a Tools section (tofu with its version and source, rsync), and commandExists uses a cross-platform lookup instead of `which`. Accept: `npx vitest run src/commands/__tests__/doctor` rc 0, with a Windows-path case.
    (ticked) 2026-10-29T17:14:47Z by d778be9d: commit:95a124a7c doctor-tools tests rc=0
- [x] T6 [opus] Provider pinning: a pins leaf carrying `.terraform.lock.hcl` hashes for every provider in provider-registry.json, written into each machine's work dir before `init`, so `tofu init` refuses an unpinned provider build. Accept: the provider-lock test rc 0, and a lock file with a changed hash makes `tofu init` fail in the test fixture.
    (ticked) 2026-10-30T00:10:15Z by d778be9d: commit:466afe701 provider-lock vitest rc=0 with the real tofu init cases run: a changed h1 hash makes tofu init fail with the checksum mismatch; pins verify rc=0 (62 pins), check:ci-pin-registry rc=0
- [x] T7 Dev wiring: `./run.sh setup` and the devcontainer call `rdc tools install tofu`, so dev uses the customer path and keeps no second copy of the pin. Accept: `./run.sh setup` on a host without tofu leaves `rdc tools list` showing the pinned version, rc 0.
    (ticked) 2026-10-30T01:10:39Z by d778be9d: commit:b81120ebf setup phase rdc-tools-install rc=0 on a host with no tofu or terraform (tools dir moved aside): installed 1.13.2, ./rdc.sh tools list -o json shows tofu 1.13.2 installed by rdc; full ./run.sh setup --no-start rc=1 stops earlier at the Go 1.26.6 < 1.27.3 consent gate (.ci/rediacc_ci/setup/host.py:561), owed to the next interactive setup per the #bf4d459d DEFAULT
- [x] T8 Regenerate the CLI contract and docs for the new verb. Accept: `npm run check:ci-cli-contract`, `npm run check:cli-docs` and `npm run check:i18n` rc 0.
    (ticked) 2026-10-29T17:14:50Z by d778be9d: commit:95a124a7c check:ci-cli-contract rc=0, check:cli-docs rc=0, check:i18n rc=0
- [ ] L1 [live] On this workstation (no tofu installed): `rdc tools install tofu`, then the approved R2-to-Linode DR proof provisions `dr-mail` with `--no-infra`, and `machine deprovision` removes it. Accept: provision and deprovision rc 0, with the Linode id, region and teardown recorded.
