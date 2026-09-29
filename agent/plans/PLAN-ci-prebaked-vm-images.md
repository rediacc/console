# PLAN: pre-baked per-distro VM images for the E2E Workers legs (spec W follow-on)

Status: proposed
Depends-On: PLAN-ci-time-budget.md -- both own .github/workflows/ct-tests.yml, so they run in sequence; the in-flight renet setup-speed edits land before B0
Owner: d778be9d
Updated: 2026-09-28
Priority: P2 -- AI-proposed; saves runner-minutes and a few minutes of E2E Workers wall time; fixes no correctness problem
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone
Owns: .github/workflows/ci-vm-bake.yml, .github/workflows/ct-tests.yml, .ci/rediacc_ci/infra/vm_bake_key.py, .ci/rediacc_ci/tests/infra/test_vm_bake_key.py, packages/e2e-tests/src/base/bridge-global-setup.ts, packages/e2e-tests/src/utils/infrastructure/InfrastructureManager.ts, private/renet/cmd/renet/setup_command.go, private/renet/cmd/renet/pkg_install_retry.go, private/renet/pkg/infra/image/one_shot_builder.go, private/renet/cmd/renet/image_build_command.go

Line numbers refer to console cdcd4f5a6 and renet 6f715a0 plus uncommitted setup-speed edits (setup_command.go, pkg_install_retry.go, docker/service.go, worker/service.go, kvm/driver.go).
The setup_command.go lines move when those land, and B1 re-checks them.

## 0. What exists today

- Every E2E Workers leg (5 distros x 8 shards, .github/workflows/ct-tests.yml:244-290) runs `renet ops up --force --parallel` in global setup (packages/e2e-tests/src/base/bridge-global-setup.ts:347-348), and the kvm driver copies the stock base image in full per VM (private/renet/pkg/infra/vm/kvm/driver.go:164-174).
- `renet setup` takes a quick path when `/var/lib/rediacc/setup_<uid>_completed` exists (private/renet/cmd/renet/setup_command.go:147; marker path private/renet/pkg/config/paths.go:10-12, private/renet/pkg/config/constants.go:93; written at :367-368).
- The quick path still reaches the network: `installEmbeddedTools` (:169) always runs `installCriuFromPackages` (:853), a dnf, zypper or apt criu install (:930-940), plus on ubuntu 24.04 a curl to download.opensuse.org and an apt index refresh (:912-922).
  The builder runs `dnf clean all` (private/renet/pkg/infra/image/one_shot_builder.go:467-471), so on a baked RPM image that quick path refetches repo metadata.
- The bridge runs `renet setup --skip-datastore` only when Docker is absent (private/renet/pkg/infra/docker/service.go:108-113), then rewrites daemon.json and restarts Docker (:118-120).
  Workers always run `sudo renet setup` (private/renet/pkg/infra/worker/service.go:57-64).
  On a baked image the bridge skips setup and each worker takes the quick path.
- The harness skips Step 3 when the marker exists and the VM's renet md5 matches the local one (packages/e2e-tests/src/base/bridge-global-setup.ts:138-141, packages/e2e-tests/src/utils/infrastructure/InfrastructureManager.ts:483-489); its comment says the marker "can only come from the setup ops up ran with that binary" (packages/e2e-tests/src/utils/infrastructure/InfrastructureManager.ts:477-482), which a baked image makes untrue.
- `renet ops image build` runs `renet setup --auto` in the VM (private/renet/pkg/infra/image/one_shot_builder.go:454).
  Its cleanup removes the scp'd renet binary (:467) and the package cache (:468-471), but does not run `cloud-init clean`, reset the machine-id, remove the `builder` user (password `builder123`, `ssh_pwauth: true`, :276-289) or remove `/opt/rediacc/proxy`.
- Runners have no virt-sparsify (`ops host setup` installs no libguestfs, private/renet/cmd/renet/ops_host.go:445), so the builder falls back to `qemu-img convert -c` (private/renet/pkg/infra/image/virtcustomize.go:39-61), which copies freed but unzeroed blocks.
- The builder has never run in CI (image-build is out of CI by design, .github/workflows/ct-tests.yml:3-7).
- The disks directory defaults to `$RUNNER_TEMP/renet/disks` in CI (private/renet/pkg/infra/opsconfig/config.go:287, :298-305); `REDIACC_OPS_DISKS_PATH` overrides it (:592-594).
  The driver looks the image up by URL basename (private/renet/pkg/infra/vm/kvm/driver.go:808-811), and `imagedl.Ensure` accepts any non-empty file already present (private/renet/pkg/infra/vm/imagedl/imagedl.go:173-176).
- The stock image cache key is `vm-base-image-e2e-<distro>-<YYYY-MM>` (.github/workflows/ct-tests.yml:400-402), restored at :403-409 and saved when `cache-hit != 'true'` (:483-488).

## 1. Measured before

| Distro | Stock cache size | Restore per leg (s), run 36427771349 |
|---|---|---|
| ubuntu-24.04 | 239 MB | 2-4 |
| debian-13 | 558 MB | 4-6 |
| opensuse-16.0 | 558 MB | 3-9 |
| fedora-43 | 793 MB | 5-13 |
| oracle-10 | 1217 MB | 9-12 |

- The Actions cache holds 10,848,291,195 bytes in 22 entries against a 10 GB repository limit, and the storage-limit API returns HTTP 402, so eviction is already happening (the fedora and opensuse stock entries now live under refs/pull/590/merge, not main).
- B0, measured 2026-09-29 on run 36528227779 (fa737eb91, renet e474204), 5 green E2E Workers legs per distro, 3 VMs per leg, from renet's `[setup] <phase> end` markers.
  Bridge and workers set up concurrently (private/renet/pkg/infra/worker/service.go:166-169), so a leg saves the slowest VM's setup, not the sum.
  Per VM, median/max seconds:

| Distro | essentials | docker-repo | docker-install | criu | total | slowest VM per leg |
|---|---|---|---|---|---|---|
| debian-13 | 24/50 | 1/2 | 14/18 | 3/4 | 51/73 | 65/73 |
| fedora-43 | 31/35 | 0/0 | 32/36 | 1/2 | 69/76 | 71/76 |
| opensuse-16.0 | 17/18 | - | 35/38 | 2/3 | 59/62 | 60/62 |
| oracle-10 | 24/34 | 0/0 | 34/43 | 2/2 | 62/83 | 66/83 |
| ubuntu-24.04 | 37/47 | 5/33 | 17/28 | 16/53 | 75/148 | 78/148 |

  Jobs: debian 109276479400/495/510/528/548; fedora 109276479410/444/451/465/519; opensuse 109276479460/468/476/505/521; oracle 109276479450/471/474/512/525; ubuntu 109276479414/492/506/520/523.
  The pre-fix estimate (52 s debian to 224 s oracle, run 36427771349) no longer holds: the bounded apt, one-call installs and concurrent setup brought every distro to 60-78 s for the slowest VM. Every distro stays above the 30 s go/no-go bar.
- 9 renet commits since 2026-07-28 touched setup_command.go, pkg_install_retry.go, opsconfig/images.go or pkg/infra/image.

## 2. Design

### 2a. The bake job

- A new workflow, `.github/workflows/ci-vm-bake.yml`, with a 5-distro matrix on ubuntu-latest, running on main only; PRs read the result and never write it.
- Triggers: push to main with paths `private/renet`, `.ci/rediacc_ci/infra/vm_bake_key.py`, the workflow itself; a schedule at 02:00 UTC on the 1st (the key carries the month); workflow_dispatch.
- Per distro: compute the key and stop if the artifact exists; build renet with `rediacc_ci.infra.build_renet`; `ops host setup`; restore the stock cache; `renet ops image build --os <distro> --output <dir> --bake-key <key>` (new flag, B2); add the stock ubuntu default image every leg also needs (.github/workflows/ct-tests.yml:394-397); publish (D1).
- `timeout-minutes: 20`; estimated 8-14 min per distro, measured in B0.
- One module, `.ci/rediacc_ci/infra/vm_bake_key.py`, computes the key `vm-bake-v1-<distro>-<YYYY-MM>-<sha256[:16]>` for both workflows, hashing:
  1. private/renet/cmd/renet/setup_command.go and pkg_install_retry.go;
  2. private/renet/pkg/config/**;
  3. private/renet/pkg/infra/opsconfig/images.go;
  4. private/renet/pkg/infra/image/** and cmd/renet/image_build_command.go;
  5. private/renet/embed-assets.lock.json;
  6. vm_bake_key.py itself and the v1 salt.
- Excluded by name: pkg/embed/proxy/** (the bake deletes it and the quick path redeploys it, private/renet/cmd/renet/setup_command.go:185), pkg/datastore, pkg/i18n.
  A completeness test (B3) parses the Go imports of both setup files and fails on any internal package neither hashed nor excluded.

### 2b. Consumption and fallback

- Before "Restore VM base image cache" (.github/workflows/ct-tests.yml:403), each leg computes the key and, unless `matrix.stock-image == '1'`, the event is schedule, or `vars.VM_BAKE == 'off'`, fetches the artifact into `$RUNNER_TEMP/renet/disks-baked` with `continue-on-error: true`.
- On a hit it writes `REDIACC_OPS_DISKS_PATH` and `BAKED_IMAGE_KEY` to `$GITHUB_ENV`; the harness spawns renet directly (.github/workflows/ct-tests.yml:476-478), so renet inherits both.
- The stock restore runs only on a miss, so a PR that changes a key input gets stock on all 40 legs.
- The stock save condition becomes `always() && steps.bake.outputs.hit != 'true' && steps.vm-image-cache.outputs.cache-hit != 'true'`; without it a baked hit would save an empty directory under the stock key.

### 2c. Fresh-install coverage that survives

- Shard 2 of each distro stays on stock every run (`include: [{shard: 2, stock-image: '1'}]`, 5 of 40 legs); it holds 02-machine-setup.
- A key miss runs all 40 legs on stock; the nightly schedule runs all 40 on stock (D3); every bake runs a full `renet setup --auto` on all 5 distros.

### 2d. `renet setup` on a baked image

- The builder writes `/var/lib/rediacc/baked-image` holding `<bake-key>|<distro>|<renet Version>` right after setup.
- `installEmbeddedTools` first runs `verifyCriuRuntime` on /usr/sbin/criu and /usr/bin/criu, and calls `installCriuFromPackages` only when neither runs; the rsync extract (:880), configureDockerExperimental, ensureSandboxInfra and deployProxyFiles stay (all local).
  This also removes the network call on ordinary reruns.
- `runPkgInstallN` and `runPkgInstallCaptured` (private/renet/cmd/renet/pkg_install_retry.go:153-167) count calls, both paths print `[setup] pkg-calls <n>`, and with the bake marker present and `RENET_SETUP_OFFLINE=1` any package-manager call on the quick path is an error.
- Builder cleanup (private/renet/pkg/infra/image/one_shot_builder.go:467-471) adds: `rm -rf /opt/rediacc/proxy`; `userdel -rf builder`; `cloud-init clean --logs --seed`; `truncate -s0 /etc/machine-id`; `rm -f /etc/ssh/ssh_host_*`; `systemctl stop docker && rm -f /var/lib/docker/engine-id`; `fstrim -av`.

## 3. Operator decisions

- D1. Where the baked images live: a GHCR package pushed with oras (outside the 10 GB Actions quota; the E2E job already has `packages: read` and a GHCR login, .github/workflows/ct-tests.yml:236-238, :321-326), or the Actions cache replacing each distro's stock entry (the 5 stock legs then download upstream every run, and the cache grows by about 1.6 GB over a quota it already exceeds).
  Decided 2026-09-28T18:38Z by the #fa91780e DEFAULT, no operator answer in 130 min: a private GHCR package.
- D2. Visibility: a baked image carries no renet binary (removed at :467) and B2 removes /opt/rediacc/proxy; what remains is distro packages, Docker, CRIU, rsync-renet (GPL, pinned), the rediacc user and sudoers, and the markers.
  Whether the GHCR package may be public is the operator's call after B2's content audit; until then it stays private (the #fa91780e DEFAULT).
- D3. Nightly on stock for all legs: recommended, and part of the design unless vetoed.

## 4. Savings against cost (B0 measurements; B7 replaces them with baked-run numbers)

| Distro | Setup saved per baked leg (s), slowest VM median | Baked legs per run | Runner-s saved per run |
|---|---|---|---|
| debian-13 | 65 | 7 | 455 |
| fedora-43 | 71 | 7 | 497 |
| opensuse-16.0 | 60 | 7 | 420 |
| oracle-10 | 66 | 7 | 462 |
| ubuntu-24.04 | 78 | 7 | 546 |

- The total is about 2380 runner-s (39.7 runner-min) per run, down from the 54.8 estimated before the setup fixes; after the added fetch and key cost (about 7 runner-min) the net is about 33 runner-min per run, above B7's 20 runner-min floor.
- The E2E stage shortens by the saving on its slowest leg, about 1.1-1.3 min (up to 2.5 min on ubuntu's 148 s outlier).
- Bake cost: the local timing B0 asked for could not run on the devbox (it has /dev/kvm but no libvirt, qemu-img, virt-install or xorrisofs, and installing a hypervisor stack is a host change), so B4's first dispatch measures it per leg instead.
  The only local data is the uncached base-image download: 8 s (ubuntu, 252 MiB) to 38 s (opensuse, 322 MiB), 34 s for oracle's 996 MiB.
  The 40-70 runner-min per bake estimate stands until B4 replaces it.

## 5. Boxes

- [x] B0 Measure first: after the in-flight setup edits land, collect the `[setup]` phase lines for bridge and workers from 5 green runs per distro including ubuntu, and time one local `renet ops image build` per distro (duration and output size). Verification: sections 1 and 4 regenerated with run ids; if every distro's per-leg saving is under 30 s, close this plan as not worth it. Done 2026-09-29: sections 1 and 4 from run 36528227779 (every distro 60-78 s, above the 30 s bar); the local bake timing moves to B4 (no libvirt on the devbox).
- [ ] B1 renet offline quick path and `pkg-calls` counter (2d), in setup_command.go and pkg_install_retry.go. Verification: Go tests with a package-manager seam (runnable CRIU gives 0 calls, missing CRIU gives 1, offline mode with the bake marker and missing CRIU errors), and a control that removing the health check fails the first test.
- [ ] B2 renet builder bake marker, `--bake-key` flag and hygiene cleanup (2d), in one_shot_builder.go and image_build_command.go. Verification: a unit test on the rendered cleanup script, and one local bake per distro booted with `ops up`: no builder user, a distinct machine-id on each VM, no /opt/rediacc/proxy before setup, and the bake marker holding the key. B0's failed local runs found five more builder defects, fixed here too: the build dir `one-shot.<pid>` (one_shot_builder.go:107) is never removed and keeps the base image, which is re-downloaded on every build instead of coming from the ops disk cache; `ops image cleanup` matches `custom-image-builder-` (builder.go:126) while the builder names its VM `renet-image-builder-<pid>` (one_shot_builder.go:156), and `os.RemoveAll("/tmp/rediacc-build*")` (builder.go:95) treats `*` literally and ignores REDIACC_TEMP_DIR; missing qemu-img, virsh, virt-install or xorrisofs is found only after the download, and the `virsh net-start` error is discarded (one_shot_builder.go:117); the build command lacks SilenceUsage, so a runtime error prints the usage block and the error twice.
- [x] B3 console vm_bake_key.py and its completeness test (2a). Verification: pytest, where a fixture adding an internal import to setup_command.go fails and touching an excluded path leaves the key unchanged. Done 2026-09-29: .ci/rediacc_ci/infra/vm_bake_key.py (key vm-bake-v1-<distro>-<YYYY-MM>-<sha256[:16]>, 35 inputs, a completeness walk over internal imports and same-package references), tested by .ci/rediacc_ci/tests/test_infra_vm_bake_key.py (37 cases), not tests/infra/.
- [ ] B4 console ci-vm-bake.yml (2a, D1). Verification: one workflow_dispatch publishes 5 artifacts named by key, a second exits at the key check within 1 min on every leg, and no leg exceeds 20 min.
- [ ] B5 console E2E Workers consumption, fallback, save guard and the shard-2 stock include (2b, 2c). Verification: one PR run where 35 legs report a baked hit and every worker logs `[setup] pkg-calls 0`, 5 shard-2 legs log full setup, and no baked leg saves the stock cache; control: a PR changing setup_command.go runs all 40 legs on stock.
- [x] B6 console harness baked-image assertion in bridge-global-setup.ts and InfrastructureManager.ts: with `BAKED_IMAGE_KEY` set, every VM's /var/lib/rediacc/baked-image must equal it or the leg fails naming the VM; the packages/e2e-tests/src/utils/infrastructure/InfrastructureManager.ts:477-482 comment names the second marker source. Verification: vitest with a mocked executeOnVM (match passes, mismatch or missing marker fails). Done 2026-09-29: InfrastructureManager.assertBakedImageOnVMs, called in bridge-global-setup before Step 2; 5 vitest cases with a disabled-comparison control.
- [ ] B7 Measure after: 5 PR runs, per-distro leg duration and setup phases against B0, and section 4 rewritten from measurements. Verification: the table with run ids; under 20 runner-min net per run sets `vars.VM_BAKE=off` and reopens the plan.

## 6. Risks

| Risk | Where | Mitigation |
|---|---|---|
| The key misses a setup input, so images go stale silently | 2a | B3 completeness test, monthly rebake, B6 key assertion on every VM |
| CI loses fresh-install coverage | 2c | shard 2 on stock, all legs on stock on a key miss and nightly, the bake itself |
| The quick path still reaches the network | private/renet/cmd/renet/setup_command.go:853, :912-935; private/renet/pkg/infra/image/one_shot_builder.go:470 | B1 health check, the pkg-calls marker, the offline hard error |
| Cloned identity (machine-id, SSH host keys, Docker engine-id) and stale cloud-init state | private/renet/pkg/infra/image/one_shot_builder.go:464-471 | B2 cleanup and the distinct machine-id check |
| A known-password builder user ships in the image | private/renet/pkg/infra/image/one_shot_builder.go:276-289 | B2 `userdel -rf builder` |
| Private renet content in a published artifact | /opt/rediacc/proxy from pkg/embed/proxy | B2 removes it; D2 needs the operator |
| Actions cache over quota causes eviction churn | 10.85 GB of 10 GB | D1 GHCR outside the quota |
| Bigger images mean slower fetches and full per-VM copies | private/renet/pkg/infra/vm/kvm/driver.go:164-174; private/renet/cmd/renet/ops_host.go:445 | B2 fstrim, B0 size measurement, B7 net check |
| Compressed qcow2 reads slower at runtime | private/renet/pkg/infra/image/virtcustomize.go:41, :60 | B7 compares test-step time, not only setup |
| The builder has never run on a GitHub runner | .github/workflows/ct-tests.yml:3-7 | B0 local bake, B4 dispatch before B5 |
| A baked file poisons the stock cache entry | .github/workflows/ct-tests.yml:484 | B5 separate directory and the three-part save condition |
| The harness skip rule assumes the marker came from ops up | packages/e2e-tests/src/utils/infrastructure/InfrastructureManager.ts:477-482 | B6 assertion and comment |
| The bake's +4G resize changes the guest disk size | private/renet/cmd/renet/image_build_command.go:118; private/renet/pkg/infra/vm/kvm/driver.go:171-174 | B0 records the virtual size; B2 passes `--resize +0G` if a test depends on it |
| In-flight setup-speed edits shrink the savings | uncommitted renet setup_command.go | B0 re-measures after they land, with its closure threshold |
| The bake misses its 20-min cap on oracle | 2a estimate | B4 verification; a key hit keeps most runs under 1 min |
| The GHCR fetch fails or is rate-limited | D1 | continue-on-error fetch, stock fallback, `vars.VM_BAKE=off` |
