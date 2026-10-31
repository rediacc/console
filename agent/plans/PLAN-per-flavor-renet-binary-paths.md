# PLAN: each renet build flavor gets its own binary path and stamp, so a plain ./rdc.sh can never change the flavor of the enforcing binary another process is using

Status: executing
Owner: d778be9d
Updated: 2026-10-28
Depends-On: no-dep -- the fix touches the dev build path, its stamps and their consumers; no open plan has to land first
Priority: P1 -- vm:check A2.3 ends NOT_VERIFIED whenever another session runs a plain ./rdc.sh during the license drill (run vmc-10280533-5ddf37), which blocks every receipt that needs the account side
Concurrency: parallel -- P1 first and alone (renet submodule commit plus the pointer bump). P2 follows P1. P3, P4 and P5 run in parallel after P2. P6 runs after P2 and only while no PLAN-tested-on-bench.md writer holds .ci/rediacc_ci/drills/vm_check.py or .ci/rediacc_ci/tests/test_drills_vm_check.py, which that plan also owns. P7 follows P2. P8 runs last and alone.
Owns: private/renet/build.sh, private/renet/CLAUDE.md, private/renet (the gitlink bump only), .ci/rediacc_ci/core/renet_flavor.py (new), .ci/rediacc_ci/core/local_common.py, .ci/rediacc_ci/core/local_common_actions_shadow_driver.py (the ensure-renet-built rows only), rdc.sh, .ci/rediacc_ci/infra/build_renet.py, .ci/rediacc_ci/drills/license.py, .ci/rediacc_ci/drills/vm_check.py (the RDC_RENET_LICENSE scrub and two comments only), packages/cli/src/services/renet/renet-execution.ts, packages/cli/src/services/renet/renet-clean-build-fs.ts, packages/cli/src/services/renet/__tests__/renet-clean-build.test.ts, .ci/rediacc_ci/tests/test_private_renet_build_dev_flavor.py (new), .ci/rediacc_ci/tests/test_core_renet_flavor.py (new), .ci/rediacc_ci/tests/test_core_local_common_renet_stamp.py, .ci/rediacc_ci/tests/test_infra_build_renet.py, .ci/rediacc_ci/tests/test_drills_license_flavor.py (new), .ci/rediacc_ci/tests/test_drills_vm_check.py, .ci/config/shards/quality-pytest.json, .ci/config/lane-durations.json, .ci/config/python-env-registry.json, docs/agent-reference/local-env.md, docs/environment-variables.md, docs/dev-environments.md, .claude/agents/licensing-ops.md, agent/plans/PLAN-per-flavor-renet-binary-paths.md
Live-Proof: none -- the change picks a local dev build's output path and its stamp; a plain build keeps the same bytes at the same path and no release or bench artifact changes (the release build writes private/bin through `build.sh build`, read by .ci/rediacc_ci/deploy/executor_artifacts.py:389); the proof instrument is the VM tier (vm:check A2.3 plus P1/V1.1); finding #950036d0
First-Seen: 2026-10-28
Worklist: #950036d0 (finding), PR-TASK 9f92c43e

## Problem

`private/renet/bin/renet` is one shared, mutable binary, and its flavor flips with `RDC_RENET_LICENSE`. Every reader picks it up through PATH or a hard-coded path, so any process that builds the other flavor swaps the binary under every other process.

**The two writers to one path, with two stamps.**
- `ensure_renet_built` (`.ci/rediacc_ci/core/local_common.py:1348-1444`) runs on every `./rdc.sh` through `prepare_cli` (`.ci/rediacc_ci/core/local_common.py:842-844`, called from `rdc.sh:80`). It derives `license_mode` from the environment (`.ci/rediacc_ci/core/local_common.py:1361`), keys `.ci/cache/build-renet.stamp` (`.ci/rediacc_ci/core/local_common.py:1360`) on source, renet HEAD, mode and account key plus a `bin=size:mtime` fingerprint (`.ci/rediacc_ci/core/local_common.py:1382-1396`, `1442`). It runs `./build.sh dev` with no flavor flag (`.ci/rediacc_ci/core/local_common.py:1403`), so `build.sh` re-reads the inherited environment to choose the flavor.
- `build.sh dev` (`private/renet/build.sh:787-850`) sets `-tags nolicense` unless `RDC_RENET_LICENSE=1` (`private/renet/build.sh:788`, `794-796`). An explicit `--license`/`--nolicense` wins over the env (`private/renet/build.sh:797-803`). Both flavors are written to `$SCRIPT_DIR/bin/renet` (`private/renet/build.sh:835-839`), and both stage `bin/renet-linux-{amd64,arm64}` in the same directory (`private/renet/build.sh:849`).
- `.ci/rediacc_ci/infra/build_renet.py` is the second writer. Line numbers are those of the file before P3 rewrote it (`git show 6de769e7e^:.ci/rediacc_ci/infra/build_renet.py`). It builds the same path (lines 185 and 239-244 of that revision) under a second stamp, `bin/.renet-build-identity` (lines 193 and 267). Its `build_identity` lets `RDC_RENET_LICENSE=1` override an explicit `--nolicense` (lines 93-118, the override at line 115), the opposite of `private/renet/build.sh:797-803`. So `RDC_RENET_LICENSE=1 build_renet --nolicense` builds nolicense and stamps it `enforce`.
- `ensure_renet_built` also cross-compiles `bin/renet-linux-<arch>` on a non-Linux host with no `-tags` (`.ci/rediacc_ci/core/local_common.py:1410-1440`). A plain build on macOS therefore ships ENFORCING Linux binaries, after `build.sh dev` already staged them (`private/renet/build.sh:849`).

**Who reads it.**
- `rdc.sh:96-98` puts `private/renet/bin` first on PATH, and `rdc.sh:104-106` says the file does not read `RDC_RENET_LICENSE`.
- The CLI's default `renetPath` is `renet` (`packages/shared/src/config/defaults.ts:359`, `packages/cli/src/services/config/config-resources.ts:165`). `resolveRenetPath` resolves it with `which` (`packages/cli/src/services/renet/renet-execution.ts:63-85`), and `acquireRemoteRenet` uses it (`packages/cli/src/services/renet/renet-execution.ts:370-386`).
- `machine setup` uploads that host binary when the remote arch matches. Otherwise it uploads `renet-linux-<arch>` from the SAME directory (`packages/cli/src/services/renet/renet-provisioner.ts:492-517`). The SEA path uploads the embedded binary (`packages/cli/src/services/renet/renet-provisioner.ts:497`), which `build.sh stage_linux` always builds nolicense (`private/renet/build.sh:510-517`), so it is unaffected.
- A dirty renet tree swaps in a clean build of HEAD (`selectRenetUploadBinary`, `packages/cli/src/services/renet/renet-execution.ts:217-241`; `buildRenetAtCommit`, `packages/cli/src/services/renet/renet-execution.ts:252-311`).
  - Its cache `.ci/cache/renet-head/<commit>` is keyed by commit and keyed/keyless only (`packages/cli/src/services/renet/renet-clean-build-fs.ts:30-55`), never by flavor.
  - Its build inherits `process.env`, `RDC_RENET_LICENSE` included (`packages/cli/src/services/renet/renet-clean-build-fs.ts:88-104`).
  - It reads `work/bin/<name>` (`packages/cli/src/services/renet/renet-execution.ts:286-295`, `packages/cli/src/services/renet/renet-clean-build-fs.ts:25-27`).
  - So a cached nolicense build at commit X is handed to an enforcing request at commit X.
- The license drill:
  - `setup_sandbox` sets `RDC_RENET_LICENSE=1` for every CLI call (`.ci/rediacc_ci/drills/license.py:574-575`).
  - `setup_config` runs `config init` and then `verify_renet_flavor` (`.ci/rediacc_ci/drills/license.py:654-659`), which reads `go version -m private/renet/bin/renet` (`.ci/rediacc_ci/drills/license.py:627-652`, path at `.ci/rediacc_ci/drills/license.py:631`).
  - `machine setup` then uploads whatever is on PATH (`.ci/rediacc_ci/drills/license.py:674`). The drill allows a dirty tree (`.ci/rediacc_ci/drills/license.py:1350`), so it uploads the working-tree binary.
  - The check and the use are two separate moments, and any plain `./rdc.sh` in between rebuilds the path as nolicense.
- vm:check:
  - P1 reads the build identity of `bin/renet` (`.ci/rediacc_ci/drills/vm_check.py:12`, `928`, `1431-1458`).
  - V1.1 accepts the deployed hash of `bin/renet` or `bin/renet-linux-amd64` (`.ci/rediacc_ci/drills/vm_check.py:2150-2156`).
  - A2 runs before P5 on the assumption that P5's plain `./rdc.sh` deploys the default build back (`.ci/rediacc_ci/drills/vm_check.py:17`, `1361`).
  - The proof receipt binds `bin/renet` (`.ci/rediacc_ci/proof/surfaces.py:43`, `647-686`; `.ci/rediacc_ci/proof/receipt.py:10-11`, `212-219`) and records no flavor.
- Readers that need nolicense and stay on `bin/renet`:
  - `.ci/rediacc_ci/proxies/ops_host_check.py:88`
  - `.ci/rediacc_ci/drills/backup.py:302-303`
  - `.ci/rediacc_ci/drills/converge_preflight.py:327-329` and `.ci/rediacc_ci/drills/upgrade_converge.py:247` (copy `ctx.renet_bin`)
  - the CI workflows, all through `build_renet --nolicense`: `.github/workflows/ci-vm-bake.yml:127`, `.github/workflows/ci-ops-test.yml:81`, `.github/workflows/ci-ops-test.yml:272`, `.github/workflows/ct-e2e-probe.yml:133`, `.github/workflows/ct-e2e-probe.yml:232`
- Not readers:
  - `check:ci-renet-types` builds into its own scratch directory (`.ci/rediacc_ci/quality/renet_types.py:151-158`).
  - The proxy image smoke and the executor stage read `private/bin/renet-linux-amd64` from the release build (`.ci/rediacc_ci/quality/proxy_image_smoke.py:21`, `.ci/rediacc_ci/deploy/executor_artifacts.py:389`).
  - `.ci/rediacc_ci/release/local_gates.py` has zero matches for `renet`.

**Evidence.**
- vm:check run vmc-10280533-5ddf37 (2026-10-28) ended NOT_VERIFIED at A2.3. The license drill's `verify_renet_flavor` found `tags=nolicense` in `bin/renet` after its own `config init` had rebuilt the binary enforcing, because concurrent plain `./rdc.sh` calls from other work rebuilt it in between.
- Reproduced: a plain `./rdc.sh` leaves `go version -m bin/renet` with `-tags=nolicense`, and `RDC_RENET_LICENSE=1 ./rdc.sh` leaves it with no tags and the key in ldflags. Both rewrite the same path.

## Design

1. **Two flavors, two directories, decided in one place.**
   - `nolicense` keeps `private/renet/bin/` (`renet`, `renet-linux-amd64`, `renet-linux-arm64`).
   - `enforce` gets `private/renet/bin/enforce/` with the same three names.
   - `build.sh dev` derives the output directory from the tags it already computes, through one helper `_dev_out_dir`. Flag precedence stays as it is (env first, then the last `--license`/`--nolicense` wins).
   - Every `go build -o` in `dev` and `_build_linux_arches` writes to `<dir>/.<name>.tmp.$$` and then `mv -f` into place. A reader of the same flavor then sees a whole old or a whole new binary, never a partly written one.
   - A direct `RDC_RENET_LICENSE=1 ./build.sh dev` also lands in `bin/enforce/`, so the documented repro (`docs/agent-reference/local-env.md:141-168`) can no longer flip `bin/renet`.

2. **One Python home for the mapping: `.ci/rediacc_ci/core/renet_flavor.py`.**
   - Pure functions with no `os.environ` reads, so the env registry entries stay on the files that read the env:
     - `FLAVORS = ("nolicense", "enforce")`
     - `SUBDIR = {"nolicense": "bin", "enforce": "bin/enforce"}`
     - `flavor_for(license_env, args)`, with build.sh's precedence
     - `build_flag(flavor)`, which returns `--nolicense` or `--license`
     - `binary(renet_dir, flavor, exe)`
     - `linux_binaries(renet_dir, flavor)`
     - `stamp_path(renet_dir, flavor)` = `<flavor dir>/.renet-build-stamp`
     - `buildinfo_flavor(go_version_m_text)`, which returns `nolicense`, `enforce` or `""`
     - `flavor_refusal(want, info)`, which returns `None` or the message
   - A test pins `SUBDIR` against `build.sh`'s `_dev_out_dir`, the `rdc.sh` PATH block and the CLI constant, so the copies cannot drift.

3. **One builder, one stamp per flavor.**
   - `ensure_renet_built(env, flavor=None)` resolves the flavor from `RDC_RENET_LICENSE` (the one env read, which stays in `local_common.py`). It runs `./build.sh dev <build_flag>` explicitly and stamps `stamp_path(flavor)` with the existing key (source, head, flavor, account key) plus `bin=`.
   - The non-Linux cross-compile block (`.ci/rediacc_ci/core/local_common.py:1410-1440`) is deleted, because `build.sh dev` already stages both Linux arches with the right tags.
   - `ensure_docker_installed` runs the binary of the flavor it built and removes that flavor's stamp (`.ci/rediacc_ci/core/local_common.py:1233-1245`).
   - `build_renet.py` becomes a thin CI wrapper. It keeps the embed-cache verdict and the `RENET_BINARY`/`GITHUB_ENV` output, and calls `ensure_renet_built(flavor=flavor_for(...))`.
   - `bin/.renet-build-identity` and `.ci/cache/build-renet.stamp` are no longer read or written. A first run after the change rebuilds each flavor once (clean break, no migration code).

4. **Only processes that asked for enforcement see it, and they name it.**
   - `rdc.sh` sets `renet_bin_dir` to `private/renet/bin/enforce` when `RDC_RENET_LICENSE=1` and to `private/renet/bin` otherwise. The PATH export is unchanged, and PATH stays the only name `rdc.sh` exports (`check:ci-rdc-sh-env` allowlist).
   - The license drill selects the enforcing binary explicitly in two ways:
     - `config init ... --renet-path <root>/private/renet/bin/enforce/renet`, so the sandbox config pins it regardless of PATH.
     - `verify_renet_flavor` reads all three binaries in `bin/enforce/` through `renet_flavor.flavor_refusal("enforce", ...)`, refuses a nolicense or keyless one, and never reads `bin/renet`.
   - vm:check drops `RDC_RENET_LICENSE` from its own environment for P1, P5 and its own `./rdc.sh` calls. Its receipt and V1.1 then always describe the nolicense `bin/renet`, and the license drill sets enforcement for itself.

5. **The CLI's clean build carries the flavor.**
   - `selectRenetUploadBinary` reads the flavor of the working-tree binary it would have uploaded (`deps.goVersionM` plus the same `tags=nolicense` rule).
   - `buildRenetAtCommit` builds with the explicit flag and reads from the clone's flavor directory (`bin` or `bin/enforce`). It verifies the built flavor, caches in `.ci/cache/renet-head/<commit>-<flavor>` with the flavor as a third marker line, and prunes other commits only, keeping both flavors of the current commit.
   - The plain flavor keeps the same flags, commit and bytes, so a hostinger upload sees no hash change.

## Alternatives rejected

- **A lock around build plus use.** The "use" runs from the drill's `config init` through `machine setup` and every leg after it, tens of minutes in which each `./rdc.sh` re-checks the stamp. A lock that wide stalls every plain `./rdc.sh` of every session on the workstation. A lock around the build alone does not fix the flip, which happens between build and use. It also leaves two stamps describing one path.
- **An env var naming the binary (for example `RDC_RENET_BIN`) read by the CLI.** It adds a CLI knob that the existing `renetPath` config field already provides (`packages/cli/src/commands/config.ts:387`). It still needs a separate output path, or it names a path that flips. The drill gets this alternative's benefit through `config init --renet-path` without a new name in `env-manifest.json`.
- **The drill copies the enforcing binary into its work directory and points `renetPath` at the copy.** That fixes one consumer and leaves the flip for every other `RDC_RENET_LICENSE=1` user, the clean-build cache and the CI wrapper. The copy itself also races the build.
- **Content-addressed builds (`bin/<sha>/renet`).** That needs a garbage collector and a PATH entry that moves on every commit, for no gain over two fixed flavor directories.

## Tasks

- [x] P1 [writer] `private/renet/build.sh`: add `_dev_out_dir <tags>` (`-tags nolicense` gives `$SCRIPT_DIR/bin`, empty tags give `$SCRIPT_DIR/bin/enforce`). `dev` builds the host binary and both Linux arches into that directory. `_build_linux_arches` and `dev` write through `.tmp.$$` plus `mv -f`. Update the help text (`private/renet/build.sh:859`) and the build table in `private/renet/CLAUDE.md`. Commit in the renet submodule and bump the pointer. The new test sources `build.sh` (the `.ci/rediacc_ci/tests/test_private_renet_build_vcs_stamp.py:108-118` precedent), stubs `_embed_assets_or_die`, `embed_proxy` and `ebpf_generate`, and puts a fake `go` on PATH that writes its argv into the `-o` file. It asserts that plain `dev` writes `bin/renet` with `-tags nolicense` and leaves an existing `bin/enforce/renet` byte-identical, that `RDC_RENET_LICENSE=1` and `--license` write only `bin/enforce/` (all three names), and that `RDC_RENET_LICENSE=1 dev --nolicense` writes `bin/`. A planted control copy of `build.sh` with `_dev_out_dir` collapsed to `bin` must fail the "enforce untouched" assertion. Owns: private/renet/build.sh, private/renet/CLAUDE.md, private/renet, .ci/rediacc_ci/tests/test_private_renet_build_dev_flavor.py, .ci/config/shards/quality-pytest.json, .ci/config/lane-durations.json. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_private_renet_build_dev_flavor.py -q` rc 0.
    (ticked) 2026-10-28T08:03:32Z by d778be9d: 2026-10-28 by d778be9d: commit:7b1bcec49 (renet 1e42b57 pointer); pytest test_private_renet_build_dev_flavor.py rc=0, the collapsed-directory control fails; P8 vm:check VERIFIED under the race
- [x] P2 [writer] Add `.ci/rediacc_ci/core/renet_flavor.py` (Design 2). Rework `ensure_renet_built` per Design 3 (explicit flag, per-flavor stamp, cross-compile block deleted, `ensure_docker_installed` on the flavor path). Change `rdc.sh` per Design 4 and correct its comment at `rdc.sh:104-106`. Update the `ensure-renet-built` rows in `.ci/rediacc_ci/core/local_common_actions_shadow_driver.py:760-780` to the explicit flag. Tests:
  - With a recording fake `build.sh` that writes `<flag>` into the flavor directory, the sequence enforce, plain, enforce leaves `bin/enforce/renet` and `bin/enforce/.renet-build-stamp` unchanged after the plain run, and the third call does not build.
  - A mutant that monkeypatches `SUBDIR` to map both flavors to `bin` turns that test red.
  - The two stamps are distinct files.
  - `flavor_for` follows build.sh's precedence.
  - The `rdc.sh` PATH block, extracted and run under bash with `RDC_RENET_LICENSE` unset and set to `1`, prints `bin` and `bin/enforce`.
  - `SUBDIR` equals what `_dev_out_dir` prints for both tag sets.
    (ticked) 2026-10-28T08:00:50Z by d778be9d: 2026-10-28 by d778be9d: commit:15ed5e3ba; pytest test_core_renet_flavor, test_core_local_common_renet_stamp, test_security_rdc_sh_env_check rc=0

  Owns: .ci/rediacc_ci/core/renet_flavor.py, .ci/rediacc_ci/core/local_common.py, .ci/rediacc_ci/core/local_common_actions_shadow_driver.py, rdc.sh, .ci/rediacc_ci/tests/test_core_renet_flavor.py, .ci/rediacc_ci/tests/test_core_local_common_renet_stamp.py, .ci/config/shards/quality-pytest.json, .ci/config/lane-durations.json. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_core_renet_flavor.py .ci/rediacc_ci/tests/test_core_local_common_renet_stamp.py .ci/rediacc_ci/tests/test_security_rdc_sh_env_check.py -q` rc 0.
- [x] P3 [writer] `build_renet.py` becomes the thin wrapper of Design 3. The flavor comes from `renet_flavor.flavor_for` (build.sh precedence, so the `build_identity` inversion in `build_renet.py` goes (removed in c0e67f9c9)). `RENET_BINARY` is the flavor's binary, and `bin/.renet-build-identity` is gone. Retire the twin-differential cases in `test_infra_build_renet.py` that pin the shared-path identity stamp. Add three cases, each with the existing fake `build.sh`:
  - `--license` and then `--nolicense` leaves `bin/enforce/renet` byte-identical.
  - `RDC_RENET_LICENSE=1 --nolicense` prints `RENET_BINARY=<root>/private/renet/bin/renet`.
  - A second `--nolicense` run skips on the per-flavor stamp.
    (ticked) 2026-10-28T08:00:53Z by d778be9d: 2026-10-28 by d778be9d: commit:15ed5e3ba; pytest test_infra_build_renet and test_infra_renet_embed_cache rc=0

  Update the module's entry in `python-env-registry.json` if its env reads move. Owns: .ci/rediacc_ci/infra/build_renet.py, .ci/rediacc_ci/tests/test_infra_build_renet.py, .ci/config/python-env-registry.json. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_infra_build_renet.py .ci/rediacc_ci/tests/test_infra_renet_embed_cache.py -q` rc 0.
- [x] P4 [writer] The CLI clean build, per Design 5: flavor read from the working-tree binary's buildinfo, explicit `--license`/`--nolicense` passed to `deps.build`, the read directory `bin` or `bin/enforce` from a `RENET_FLAVOR_DIRS` constant in `renet-clean-build-fs.ts`, a `<commit>-<flavor>` cache directory with the flavor as the marker's third line, and the prune regex widened to the suffixed names. Tests in `renet-clean-build.test.ts`:
  - A complete nolicense cache at commit X is not reused for an enforcing request at X.
  - An enforcing request reads `work/bin/enforce/renet` and refuses a clone build whose buildinfo says `tags=nolicense`.
  - The prune keeps both flavors of the current commit.
  - The plain flavor still passes `--nolicense` and reads `work/bin/renet`.
    (ticked) 2026-10-28T08:00:55Z by d778be9d: 2026-10-28 by d778be9d: commit:7b1bcec49; cd packages/cli && npx vitest run src/services/renet/__tests__/renet-clean-build.test.ts rc=0

  Owns: packages/cli/src/services/renet/renet-execution.ts, packages/cli/src/services/renet/renet-clean-build-fs.ts, packages/cli/src/services/renet/__tests__/renet-clean-build.test.ts. Accept: `cd packages/cli && npx vitest run src/services/renet/__tests__/renet-clean-build.test.ts` rc 0.
- [x] P5 [writer] License drill, per Design 4. `verify_renet_flavor` reads `renet_flavor.binary(..., "enforce")` and both `linux_binaries(..., "enforce")`, and judges them through `renet_flavor.flavor_refusal("enforce", info)`. `setup_config` passes `--renet-path <enforce binary>` to `config init`. Correct the comment at `.ci/rediacc_ci/drills/license.py:574` ("the next plain ./rdc.sh rebuilds nolicense right back" is no longer true) and the error hints at `.ci/rediacc_ci/drills/license.py:643-650`. Tests (new file, with the go reader injected):
  - Nolicense buildinfo at the enforcing path gives `SystemExit(1)`.
  - Keyless enforcing buildinfo gives `SystemExit(1)`.
  - Enforcing buildinfo with `ProductionPublicKey=` passes.
  - The paths read are exactly the `bin/enforce/` three and never `bin/renet`. A mutant that points it back at `bin/renet` fails this.
  - The recorded `config init` argv carries `--renet-path` with the enforcing path.
    (ticked) 2026-10-28T08:03:35Z by d778be9d: 2026-10-28 by d778be9d: commit:15ed5e3ba; pytest test_drills_license_flavor, test_drills_backup_license, test_drills_license_seed rc=0; P8 vm:check A2.3 ok under the race

  Owns: .ci/rediacc_ci/drills/license.py, .ci/rediacc_ci/tests/test_drills_license_flavor.py, .ci/config/shards/quality-pytest.json, .ci/config/lane-durations.json. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_drills_license_flavor.py .ci/rediacc_ci/tests/test_drills_backup_license.py .ci/rediacc_ci/tests/test_drills_license_seed.py -q` rc 0.
- [x] P6 [writer] vm:check drops `RDC_RENET_LICENSE` from `self.environ` (`.ci/rediacc_ci/drills/vm_check.py:914`) before P1, so P1, P5, V1.1 and its own `./rdc.sh` calls always mean the nolicense `bin/renet`. `drill_env` (`.ci/rediacc_ci/drills/vm_check.py:1112`) carries nothing about the flavor, and the license drill sets its own. Reword `.ci/rediacc_ci/drills/vm_check.py:17` and `.ci/rediacc_ci/drills/vm_check.py:1361`: A2.3 deploys `bin/enforce/renet`, P5 re-uploads `bin/renet`, and neither rebuilds the other. Test: a `VmCheck` built with `environ={"RDC_RENET_LICENSE": "1", ...}` runs its fake-host `./rdc.sh --version` and `go version -m` without that variable, and `renet_bin` stays `private/renet/bin/renet`. Owns: .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/tests/test_drills_vm_check.py. Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_drills_vm_check.py -q` rc 0.
    (ticked) 2026-10-28T08:01:00Z by d778be9d: 2026-10-28 by d778be9d: commit:15ed5e3ba; pytest test_drills_vm_check rc=0
- [x] P7 [writer] Docs. `docs/agent-reference/local-env.md:141-168` says an enforcing build lives in `private/renet/bin/enforce/`, is selected only by `RDC_RENET_LICENSE=1`, and never replaces `bin/renet`. The "unset it so subsequent invocations rebuild nolicense" paragraph is deleted. Update `docs/environment-variables.md:82`, `docs/dev-environments.md:80` and `.claude/agents/licensing-ops.md:71` to match. Owns: docs/agent-reference/local-env.md, docs/environment-variables.md, docs/dev-environments.md, .claude/agents/licensing-ops.md. Accept: `grep -n "bin/enforce" docs/agent-reference/local-env.md docs/environment-variables.md .claude/agents/licensing-ops.md` rc 0, and `grep -n "rebuild the dev-friendly nolicense" docs/agent-reference/local-env.md` rc 1.
    (ticked) 2026-10-28T08:01:03Z by d778be9d: 2026-10-28 by d778be9d: commit:15ed5e3ba; grep bin/enforce in the docs rc=0, the old unset paragraph gone rc=1
- [x] P8 [writer] VM-tier proof under the race that failed vmc-10280533-5ddf37. While `while sleep 20; do ./rdc.sh --version >/dev/null 2>&1; done` runs in a second shell, `npm run vm:check` ends VERIFIED. Rows P1, A2.3 and V1.1 must be ok, `go version -m private/renet/bin/enforce/renet` must show no `tags=nolicense`, and `go version -m private/renet/bin/renet` must show `-tags=nolicense`. Owns: none -- proof run only, no file edited. Accept: `npm run vm:check` rc 0.
    (ticked) 2026-10-28T08:01:05Z by d778be9d: 2026-10-28 by d778be9d: commit:6de769e7e; npm run vm:check rc=0 VERIFIED (175 assertions, 0 failed, A2.3 ok) while a plain ./rdc.sh --version ran every 20 s beside it; go version -m bin/enforce/renet shows no tags=nolicense, bin/renet shows tags=nolicense

## Risks

- **Live-Proof waiver.** `resolve_live_proof_waiver` (`.claude/hooks/stop/wl_plandeps.py:450-459`) accepts a `none` only when the cited item is closed. #950036d0 must be closed (promoted to this plan) before the header gate passes. `bench` would not be honest, because the renet surface's only live target is hostinger (`.ci/config/proof-tiers.json:6-17`).
- **Cross-submodule ordering.** P1 lands in `private/renet` first. If P2 lands before the pointer bump, an explicit `--license` goes to an old `build.sh` that still writes `bin/renet`, so P2's Accept runs only on the bumped pointer.
- **P1 and P4 together.** Once P1 lands, a CLI clean build under `RDC_RENET_LICENSE=1` reads `work/bin/renet`, which is absent, until P4 lands. P1 and P4 merge in the same PR.
- **First run rebuilds.** The first `./rdc.sh` after the change rebuilds `bin/renet` once (new stamp location), and the first enforcing run builds `bin/enforce/` from scratch. Both are a few minutes, once.
- **Shared build inputs are still racy.** `build.sh dev`'s prelude (`_embed_assets_or_die`, `embed_proxy`, `ebpf_generate`) still writes flavor-independent generated inputs under `pkg/`, which two concurrent builds of different flavors can both touch. That hazard predates this plan and is out of scope. If it reproduces, it is a separate finding.
- **CI behaviour change.** `build_renet.py` now runs `ensure_renet_built`'s source fingerprint instead of the identity-only stamp. All five workflow calls pass `--nolicense`, so their `RENET_BINARY` path is unchanged. The CI run of the PR exercises them.
- **SEA is not covered.** The SEA (`--native`) always embeds a nolicense renet (`private/renet/build.sh:510-517`), so `RDC_RENET_LICENSE=1` has no effect there, before and after this plan.
