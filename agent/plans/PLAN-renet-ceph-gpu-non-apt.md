# PLAN: port renet's apt-only Ceph, fork-dest and GPU flows to dnf and zypper

Status: active
Depends-On: PLAN-ci-prebaked-vm-images.md, PLAN-ci-time-budget.md
Owner: d778be9d
Updated: 2026-09-29
Priority: P2 (operator) -- ruling 2026-09-29: full port rather than keeping these flows apt-only
Concurrency: exclusive -- operator ruling 2026-09-26
Owns: private/renet/pkg/infra/pkgset/pkgset.go, private/renet/pkg/infra/aptretry/**, private/renet/pkg/infra/cephpkg/** (new), private/renet/cmd/renet/ceph_install.go, private/renet/cmd/renet/kube_fork_dest_prep.go, private/renet/cmd/renet/pkg_install_retry.go, private/renet/cmd/renet/setup_command.go, private/renet/cmd/renet/gpu_drivers.go (new), private/renet/pkg/infra/ceph/provisioner.go, private/renet/.ceph-image-pin, scripts/gates/check-ceph-image-pin.ts, .github/workflows/ct-tests.yml, .ci/rediacc_ci/infra/renet_pkg_matrix.py (new), .ci/rediacc_ci/tests/test_infra_renet_pkg_matrix.py (new), .ci/rediacc_ci/infra/vm_bake_key.py, packages/e2e-tests/src/base/bridge-global-setup.ts, private/renet/pkg/i18n/locales/*.go

The bake plan comes first because its B4/B5 also own ct-tests.yml; the time-budget plan sets the per-job caps and lane-durations.json these legs must fit.

Line numbers refer to console ff26e55f5 and renet 5a3a984; ct-tests.yml moved since in a312694e9 (bake B4/B5), so P6 re-reads its lines first.

## 0. What exists today

- **The guards.** `requireApt` (private/renet/cmd/renet/pkg_install_retry.go:314-319) refuses when `detectPackageManager` (private/renet/cmd/renet/setup_command.go:51-62) does not return apt. Its shell twin `aptretry.RequireApt` is at private/renet/pkg/infra/aptretry/aptretry.go:18-21. The call sites are:
  - private/renet/cmd/renet/ceph_install.go:37
  - private/renet/cmd/renet/kube_fork_dest_prep.go:50
  - private/renet/cmd/renet/setup_command.go:1633 (AMD) and :1674 (Nvidia)
  - private/renet/pkg/infra/ceph/provisioner.go:518 (node prep) and :1886 (client install)
- **Package registry.** pkgset carries only an `Apt` entry for these sets:
  - `AMDGPU` and `NvidiaDriverTools`: private/renet/pkg/infra/pkgset/pkgset.go:194-203
  - `CephClient`, `CephAdmin`, `CephNode` and `ClusterForkDest`: :205-230
  - `KernelModulesExtra` has no zypper entry: :189-192
  - `DistroDocker` Dnf is `docker`, which "may resolve to podman-docker" on EL: :151-159
- **Retry helpers.**
  - `aptretry.Shell` (private/renet/pkg/infra/aptretry/aptretry.go:43-85) renders apt-only bounded shell for the remote scripts.
  - On the Go side, `runPkgInstall`/`runPkgInstallN`/`runPkgInstallCaptured` (private/renet/cmd/renet/pkg_install_retry.go:250-283) and `pkgIndexRefresh` (:96) already handle dnf and zypper.
  - dnf and zypper installs are deliberately left without an outer deadline (policy comment :35-46). Only apt splits into a bounded download (`pkgInstallAttempt`, :285-295; `runStreamedBounded`, :297).
- **`renet ceph install`.** It is hand-rolled apt (`sudoBoundedApt`, private/renet/cmd/renet/ceph_install.go:131-138; install at :51-65). It runs `cephadm bootstrap` with no `--image` (:110-113). It has no E2E coverage.
- **Ceph node prep.**
  - `prepareNodeSSH` (private/renet/pkg/infra/ceph/provisioner.go:428-459) first installs renet on every Ceph node (:429).
  - Worker+Ceph nodes get the full Docker install (:432-437). Ceph-only nodes get `cephPrereqScript(true)` (:515-561): apt update, `docker.io`, a background `docker pull` of `CephImagePin`, then `CephNode` packages.
  - `CleanupState` uses `docker ps` (:578-579).
  - Bootstrap runs `cephadm --image CephImagePin bootstrap` (:667-670).
- **Client install.** `configureClientSSH` installs `CephClient` on workers over SSH, 2 attempts (private/renet/pkg/infra/ceph/provisioner.go:1886-1889).
- **fork-dest-prep.** It runs as function `kube_fork_dest_prep` (private/renet/pkg/functions/commands/kube.go:205, :565-573). E2E covers it only in packages/e2e-tests/tests/kube/16-datastore-cluster.test.ts:301 and packages/e2e-tests/tests/kube/17-multinode-cluster.test.ts:483.
- **The pin.**
  - `CephImagePin = quay.io/ceph/ceph:v19.2.3-20250717` (private/renet/pkg/infra/ceph/provisioner.go:31-46) must equal noble's ceph-common exactly. The reason is recorded there: a 19.2.6 cluster's key is rejected by a 19.2.3 client.
  - private/renet/.ceph-image-pin holds `host-version=19.2.3` and `review=2026-11-18`.
  - scripts/gates/check-ceph-image-pin.ts:43-48 checks the image and review date only. It does not check host-version.
- **Bug in the Nvidia path today:** `ubuntu-drivers autoinstall` is retried with an apt index refresh (private/renet/cmd/renet/setup_command.go:1683-1686).
- **The AMD flow is not ROCm.** Despite its comment (private/renet/cmd/renet/setup_command.go:1638), it installs only mesa-utils and vulkan-tools (private/renet/pkg/infra/pkgset/pkgset.go:195-197), plus a best-effort `linux-modules-extra-<release>` (:1646-1651).
- **Existing repo-trust pattern.** dnf Docker uses a fetched .repo (private/renet/cmd/renet/setup_command.go:1383-1395). SUSE uses `zypper addrepo` plus `--gpg-auto-import-keys` (:1537-1541), which trusts the key on first use. Nothing verifies a fingerprint.
- **Distro limits.** rocky-10 and centos-10-stream are "KNOWN-BROKEN" as workers because their kernels have no btrfs (private/renet/pkg/infra/opsconfig/images.go:28-37, :90-121). `VMImage` is one value for every VM (private/renet/pkg/infra/opsconfig/config.go:57, :221, :430), so a Ceph-node-only distro cannot be set.
- **CI.**
  - All four Ceph jobs set no `VM_IMAGE` and so run on ubuntu-24.04 (`DEFAULT_VM_IMAGE`, .ci/rediacc_ci/env/create_e2e_env.py:110; the cache key is hard-coded to ubuntu in each job).
  - Jobs: E2E Ceph (.github/workflows/ct-tests.yml:531, `--ceph` :653), E2E Ceph Workers (:697, `--vm-ceph-nodes "21 22"` :830), E2E K8s Ceph (:1036), E2E K8s Multinode (:1208).
  - Measured p90 (.ci/config/lane-durations.json:1094-1105): 13.0 / 12.5 / 18.7 / 23.5 min.
  - Caps (agent/plans/PLAN-ci-time-budget.md:376): Ceph and Ceph Workers take the ordinary 15-minute cap. K8s Ceph is exempt at 20/25 and K8s Multinode at 25/30. The `timeout-minutes` values still read 45/90/90/100.
- **Existing mismatch found (not asked about):** Debian 13 passes `requireApt` but ships ceph-common 18.2.7+ds-1+deb13u1, one major behind the pinned cluster. That direction of skew was never measured.

## 1. Research findings (fetched 2026-09-29)

| Distro | Where 19.2.3 is available | Newer versions there | Can we pin to exactly 19.2.3? |
|---|---|---|---|
| Ubuntu noble | archive, 19.2.3-0ubuntu0.24.04.3 (pin file) | download.ceph.com debian-20.2.4 has noble; debian-19.2.6 does not | yes (today's path) |
| Fedora 43 | `fedora` GA repo: ceph-common-19.2.3-8.fc43, cephadm-19.2.3-8.fc43 | `updates`: 19.2.6-1.fc43; F44 20.2.4; F45 21.1.0 | yes. The GA repo is frozen, but `updates` must be locked out |
| EL10 (Oracle, Rocky, CentOS Stream) | CentOS Storage SIG `ceph-squid` c10s: every build 19.2.0 to 19.2.6-2, including 19.2.3-1.el10s (ceph-common, cephadm, librados2) | download.ceph.com has no rpm-19.2.3/el10. rpm-19.2.6/el10 is an empty dir. el10 exists only in rpm-20.2.4 | yes, via the SIG. Whether its builds install on OL10/Rocky 10 is unproven |
| openSUSE Leap 16.0 | OBS `filesystems:ceph:squid/16.0`: ceph-common and cephadm 19.2.3-lp160.2.96 (published 2026-09-24) | `filesystems:ceph/16.0` is reef 18.2.7. Leap 16 OSS has no ceph | yes today. OBS keeps only the latest build, so the pin disappears on the next rebuild |
| Debian 13 | none (18.2.7 only) | none | no |

- **One upstream release everywhere is impossible today.** The only release download.ceph.com builds for both noble and el10 is 20.2.4 (tentacle). It has no Fedora or SUSE builds, F43 and Leap 16 have no 20.x, and 20.x would also need noble moved off its distro package.
- **The container engine.** The cephadm RPM `Recommends: podman` (ceph.spec.in v19.2.3:535-544). cephadm prefers podman over docker (`CONTAINER_PREFERENCE = (Podman, Docker)`, ceph v19.2.3 src/cephadm/cephadmlib/container_engines.py, lines 111-122), and `--docker` is a per-invocation flag that the mgr does not carry to other hosts. So:
  - A non-apt node must install without weak dependencies and have no podman.
  - The EL `docker` package (podman-docker) is unusable for this. Ceph-only nodes must use Docker CE (`installDockerRHEL`, private/renet/cmd/renet/setup_command.go:1381-1415).
- **Nvidia (developer.download.nvidia.com/compute/cuda/repos).**

  | Repo dir | Repo file | Signing key | Driver package |
  |---|---|---|---|
  | rhel10 | cuda-rhel10.repo | CDF6BA43.pub | nvidia-open-615.71.09 |
  | fedora43 | cuda-fedora43.repo | 1940C73E.pub | nvidia-open-595.91.07 |
  | suse16 | cuda-suse16.repo | 3A8B5622.pub | nvidia-open-driver-G07-615.71.09 |

  - `nvidia-open` is the open kernel module, Turing or newer. `ubuntu-drivers` may pick a proprietary branch for older GPUs.
  - EL10 needs EPEL for dkms and a kernel-devel that matches the running kernel (kernel-uek-devel on Oracle UEK). Nvidia's precompiled kmods target the RHEL kernel, not UEK.
- **AMD (repo.radeon.com/amdgpu-install/latest).**
  - It has rhel/10 and 10.1, plus el/, but sle/ holds only 15.7: no SLE 16 or Leap 16.
  - Fedora carries ROCm in its own repos.
  - Parity with today's apt flow needs only the mesa demo tools and vulkan-tools. Expected names are glx-utils + vulkan-tools on dnf and Mesa-demo-x + vulkan-tools on zypper; P1's dry run confirms them.
  - The amdgpu module is in-tree everywhere. But Leap 16 Minimal ships kernel-default-base, which drops most GPU drivers.
- **GPU in CI (no GPU).**
  - Provable: repo file written; key fetched and its fingerprint matched; a full dependency resolution; for dnf an rpm test transaction (`--setopt=tsflags=test`), for zypper `--dry-run`.
  - Provable only on a VM leg: the DKMS build against the running kernel (`modinfo nvidia`).
  - Not provable: module load, device binding, `nvidia-smi`/`rocminfo`, Secure Boot MOK enrolment.
- **Sources:**
  - Fedora: packages.fedoraproject.org/pkgs/ceph/ceph-common; mirrors.kernel.org/fedora/releases/43/Everything/x86_64/os/Packages/c/
  - Ceph upstream: download.ceph.com/{rpm-19.2.3,rpm-19.2.6/el10,rpm-20.2.4/el10,debian-19.2.6/dists,debian-20.2.4/dists}
  - CentOS SIG: mirror.stream.centos.org/SIGs/10-stream/storage/x86_64/ceph-squid/Packages/c/ and …/extras/x86_64/extras-common/Packages/c/ (centos-release-ceph-squid-1.0-2.el10s)
  - openSUSE: download.opensuse.org/repositories/filesystems:/ceph{,:/squid}/16.0/
  - Debian: packages.debian.org/trixie/ceph-common
  - Ceph source: raw.githubusercontent.com/ceph/ceph/v19.2.3/{ceph.spec.in,src/cephadm/cephadmlib/container_engines.py}
  - Nvidia: developer.download.nvidia.com/compute/cuda/repos/{rhel10,fedora43,suse16}/x86_64/
  - AMD: repo.radeon.com/amdgpu-install/latest/{rhel,sle}/

### 1a. P0 measured (2026-09-29, local Docker, one run each, x86_64)

The pinned 19.2.3 installs on all five distros with weak dependencies off; podman never came in, and `rbd --version` reports 19.2.3 squid everywhere.

| Distro | Repos needed | Setup s | Install s | Download | Lock holds |
|---|---|---|---|---|---|
| Fedora 43 | GA + an `updates` exclude (repos.override.d) | 12 | 24 | 93 MiB | yes; unlocked it offers 19.2.6-1.fc43 |
| OL 10.2 | SIG + EPEL (oracle-epel-release-el10) + CRB (ol10_codeready_builder) | 33 | 25 | 71 MiB | yes (dnf4 versionlock); unlocked it offers 19.2.6-2 |
| Rocky 10.2 | SIG + EPEL + CRB | 34 | 26 | 76 MiB | yes |
| CentOS Stream 10 | SIG + EPEL (lttng-ust is in appstream there) | 27 | 28 | 77 MiB | yes |
| Leap 16.0 | OBS filesystems:ceph:squid, `--no-recommends` | 16 | 23-41 | 94 MiB | `addlock` registered; untestable until OBS offers a newer build |

Corrections to the section above, each measured:

- OL10 and Rocky 10 need CRB as well as EPEL: with the SIG alone ceph-common lacks libtcmalloc, libarrow, libparquet and liboath (EPEL), and with EPEL added librbd1 still lacks liblttng-ust.so.1, which only CRB carries there (1 package from CRB, 12 from EPEL). EPEL is always needed, not "if the dry run needs it".
- `centos-release-ceph-squid` writes `gpgcheck=0` into CentOS-Ceph-Squid.repo; renet must set `gpgcheck=1` (the install passes with it).
- Leap 16 OSS does carry ceph: ceph-common and cephadm 18.2.7-160000.1.2 (reef), which the OBS pin must outrank.
- `--repo=fedora` for the whole transaction downgrades six base packages (util-linux-core family, systemd-libs); writing the `updates` exclude first and installing the exact NEVRs with every repo on gives the same NEVRs and no downgrade.
- dnf4 `versionlock add` on a package not yet installed locks every available version, so the lock step runs after the install, over the installed names.
- Keys: CentOS SIG Storage `7412 9C0B 173B 071A 3775 951A D4A2 E50B E451 E5B5` (https://www.centos.org/keys/RPM-GPG-KEY-CentOS-SIG-Storage, no expiry); OBS filesystems `B1FB 5374 8720 4722 05FA 6019 98C9 7FE7 324E 6311`, which EXPIRES 2027-05-07 (a review item for D2).
- Package names: `sqlite` on dnf, `sqlite3` on zypper; `btrfs-progs` on dnf (present on OL10, Rocky 10, Stream 10, F43), `btrfsprogs` on zypper; sshpass, xfsprogs, lvm2 identical and in base repos.

## 2. Design

### 2a. Pinning: one Ceph version, each distro from its own repo (recommended, D1)

Every host installs exactly `host-version` (19.2.3), and the cluster image stays `CephImagePin`. A new package `pkg/infra/cephpkg` holds, per distro ID:

| Target | Repo | How the key is trusted | Pinned version |
|---|---|---|---|
| ubuntu | noble archive | distro key | `=19.2.3-0ubuntu0.24.04.3` (D4) |
| fedora 43 | `--repo=fedora` for the ceph packages | distro key | 19.2.3-8.fc43 |
| ol / rocky / centos 10 | SIG `ceph-squid`. On CentOS: `dnf install centos-release-ceph-squid` (extras, distro-signed). On OL and Rocky: renet writes `rediacc-ceph-squid.repo` pointing at mirror.stream.centos.org/SIGs/10-stream/storage/$basearch/ceph-squid/ | `gpgcheck=1`; RPM-GPG-KEY-CentOS-SIG-Storage embedded in renet with its fingerprint; EPEL from `oracle-epel-release-el10` or `epel-release` (private/renet/pkg/infra/pkgset/pkgset.go:242-248) if the dry run needs it | 19.2.3-1.el10s |
| opensuse 16.0 | OBS `filesystems:ceph:squid/16.0` | the project's `repomd.xml.key`, embedded with its fingerprint and imported by `rpm --import`. Never `--gpg-auto-import-keys` | 19.2.3-lp160.2.96, or the mirror from D2 |

- Every non-apt install uses exact versions (`ceph-common-<V>`, `cephadm-<V>`) with weak dependencies off (`--setopt=install_weak_deps=False`, zypper `--no-recommends`).
- It then locks the packages so `dnf upgrade` or `zypper up` cannot introduce skew:
  - dnf5 (Fedora): a `repos.override.d` exclude on `updates`.
  - dnf4 (EL10): the versionlock plugin.
  - zypper: `addlock`.
- Debian keeps refusing, now with a message that says why (no 19.x source). See D5.
- `.ceph-image-pin` gains one `host.<distro>=<NEVR>` line per distro. check-ceph-image-pin.ts checks that every line's upstream version equals `host-version` and that the Go table matches the file.
- A nightly drift check confirms each pinned version still resolves in its repo, which catches the OBS rebuild case.

### 2b. One implementation, run on the node

- `renet ceph install` gains `--profile admin|node|client|fork-dest`, which maps to the CephAdmin, CephNode, CephClient and ClusterForkDest sets. It runs `cephpkg.EnsureRepo(osID)` and then `runPkgInstall` on the detected manager. On apt, behaviour is unchanged: 3 attempts with a bounded 120 s download (private/renet/cmd/renet/pkg_install_retry.go:23-55 equals `cephAptBounds`, private/renet/pkg/infra/ceph/provisioner.go:480).
- The provisioner stops rendering apt:
  - `cephPrereqScript` keeps the background image pull and the prep markers.
  - It replaces the apt lines with `sudo renet ceph install --profile node --prep-markers`. renet is already on the node (private/renet/pkg/infra/ceph/provisioner.go:429).
  - `configureClientSSH` sends `sudo renet ceph install --profile client`.
  - `KubeForkDestPrepCommand` calls `--profile fork-dest`. `renet kube fork-dest-prep` becomes an alias for it.
- On a dnf Ceph-only node, Docker comes from `renet install-docker` (Docker CE, `--allowerasing`) instead of the `docker` package. zypper keeps `docker`.
- The prep fails with a clear message if `podman` is on PATH after install. Bootstrap also passes `--docker`.
- The package sets gain Dnf and Zypper entries:
  - `sqlite3` becomes `sqlite` on dnf.
  - On dnf, `btrfs-progs` in CephNode is best-effort. EL10 base repos lack it; Oracle has it.
  - sshpass, xfsprogs and lvm2 keep their names; the P1 dry run confirms them.
- `requireApt` and `aptretry.RequireApt` become `requireSupportedManager(flow)`, which refuses only Unknown or an unpinned distro.

### 2c. GPU

- `installAMDDriver` and `installNvidiaDriver_` move to cmd/renet/gpu_drivers.go. setup_command.go keeps the two calls at :310 and :319.
- **AMD:** the parity package set per manager. KernelModulesExtra stays best-effort. On zypper, the driver warns when `kernel-default-base` is installed, because amdgpu is absent from it. ROCm is D3.
- **Nvidia:**
  - apt keeps `ubuntu-drivers`. The autoinstall retry stops calling the apt refresh on non-apt hosts.
  - dnf and zypper add the CUDA repo for `fedora43`, `rhel10` (Oracle, Rocky and CentOS all use rhel10) or `suse16`. The key is embedded and fingerprint-checked.
  - The install adds `nvidia-open` (dnf, with kernel-devel-$(uname -r) or kernel-uek-devel-$(uname -r) and, on EL, EPEL for dkms) or `nvidia-open-driver-G07` (zypper).
- A hidden `--gpu-resolve-only` flag runs repo setup for real, then a resolve-only install (apt `--simulate`, dnf `--setopt=tsflags=test`, zypper `--dry-run`), so CI can exercise it.

### 2d. CI

1. **New job `Renet pkg matrix (<distro>)`.** It has 5 legs, one container each: fedora:43, oraclelinux:10, rockylinux/rockylinux:10, quay.io/centos/centos:stream10 and opensuse/leap:16.0. It runs from `.ci/rediacc_ci/infra/renet_pkg_matrix.py` and executes for real:
   - `renet ceph install --profile admin`, `--profile client` and `--profile fork-dest`;
   - the installed-version checks: `rpm -q ceph-common cephadm` equals the pin, `rbd --version`, `sqlite3 --version`, no podman;
   - `upgrade --assumeno`, which must show no ceph package (the lock holds);
   - the two GPU resolve-only runs.

   This is the only CI proof possible for Rocky and CentOS, since a btrfs-less kernel cannot run the E2E Ceph functions. It triggers on PRs whose paths touch the owned renet files, and on the nightly schedule. `timeout-minutes: 12`.
2. **E2E Ceph Workers non-apt legs** (fedora-43, oracle-10, opensuse-16.0). They set `VM_IMAGE` and restore that distro's stock cache key (`vm-base-image-e2e-<distro>-YYYY-MM`) as a restore-only step, never saving, because the cache is over quota. This job alone exercises Ceph-only node prep, Docker on Ceph-only nodes, the client install on workers and the full test suite. E2E Ceph (`--ceph`, no workers) adds nothing beyond it.
   - These legs run nightly and on the same path filter (D6). The ubuntu leg is unchanged.
   - bridge-global-setup.ts (next to :361) asserts that `ceph --version` on every Ceph node and worker equals `host-version`.
3. **K8s Ceph and Multinode** (the only fork-dest-prep E2E) get no non-apt legs. fork-dest-prep is covered by (1) and by the shared `--profile client` path in (2).
4. **Optional nightly VM leg** (D7): `renet setup --install-nvidia-driver=true` on fedora-43 and oracle-10, asserting that `modinfo nvidia` succeeds (the DKMS module built for the running kernel).

## 3. Operator decisions still needed

- **D1. Pinning strategy.** Default: per-distro exact pins of one version (2a). The alternative, one upstream tentacle release, cannot cover F43 or Leap 16 (section 1).
- **D2. OBS pin durability.** OBS drops 19.2.3 on the next rebuild. Default: mirror the pinned Leap RPM set plus its signature into a private GHCR artifact (the same store as bake D1) and install from it. The drift check reds before breakage either way.
- **D3. AMD scope.** Default: parity (mesa and vulkan tools) on dnf and zypper. ROCm through amdgpu-install on EL10 only, as an opt-in `--amd-rocm` flag, is a separate follow-up. There is no SLE 16 ROCm repo.
- **D4. Also pin the apt version to exactly 19.2.3.** Default: yes, so a noble SRU cannot silently move the host ahead of the image. The review gate still governs moving it.
- **D5. Debian 13.** Default: refuse Ceph flows with a message (18.2.7 only). The alternative is to measure an 18-client/19-cluster pairing and allow it.
- **D6. Triggers for the non-apt Ceph Workers legs.** Default: nightly plus path-filtered PRs. They take the 15-minute cap if P0 measures p90 ≤ 13, and otherwise need a named exemption at 18/20.
- **D7. Nightly Nvidia DKMS VM leg.** Default: yes, about 16 runner-min per night.
- **D8. Fedora 43 lifetime.** F43 reaches EOL around 2026-12, and F44 ships only 20.2.4. Default: when the image review moves to 20.x, move every pin together. Until then the ops image list keeps fedora-43.

## 4. Cost (estimates; P0 and P7 replace them with measurements)

| Item | Legs | Minutes per leg | Runner-min per triggered run | When |
|---|---|---|---|---|
| Renet pkg matrix | 5 | 4-6 (build 1.5, ceph install 1.5, Nvidia test transaction ~300 MB 1-2) | ~25 | path-filtered PR, nightly |
| E2E Ceph Workers non-apt | 3 | 13-15 (ubuntu 12.5 plus a larger rpm download and Docker CE on 2 Ceph nodes) | ~43 | path-filtered PR, nightly |
| Nvidia DKMS VM (D7) | 2 | ~8 | ~16 | nightly |

- About 84 runner-min per night, roughly 2,500 per month, plus about 70 per matching PR.
- Wall time adds nothing to a PR: the legs run in parallel with existing jobs. They do take 8-10 concurrency slots out of the Free plan's 20 (PLAN-ci-time-budget D-W1).
- Every new job must fit the 12-minute target and 15-minute cap except under an approved D6 exemption.

## 5. Boxes

- [x] P0 Measure first. Dispatch the existing E2E Ceph Workers job once each with `VM_IMAGE` = fedora-43, oracle-10 and opensuse-16.0, with the guards patched out on a scratch branch so the phase times can be seen. Record where each fails and how long the steps before the failure take. Hand-run the SIG and OBS installs in the 5 containers. Owned: none (scratch). Verification: a table of run ids, prep phases and minutes per distro, written into sections 1 and 4. If the SIG 19.2.3 RPMs fail to install on OL10 or Rocky 10, stop and put D1 back to the operator. The E2E dispatch half cannot run on a scratch branch (one branch per repo, CLAUDE.md rule 1), so it moves to P6's first PR run of the non-apt legs; the container half is section 1a.
    (ticked) 2026-09-29T09:03:42Z by d778be9d: section 1a (agent/plans/PLAN-renet-ceph-gpu-non-apt.md:97), local Docker runs 2026-09-29, 5/5 distros install 19.2.3 rc=0
- [x] P1 pkgset: Dnf and Zypper entries for CephClient, CephAdmin, CephNode, ClusterForkDest, AMDGPU and the Nvidia sets, plus the zypper KernelModulesExtra decision. Owned: private/renet/pkg/infra/pkgset/pkgset.go and its tests. Verification: `go test ./pkg/infra/pkgset/...`, and a table test that every set a ported flow uses is non-empty for all three managers.
    (ticked) 2026-09-29T11:18:56Z by d778be9d: renet 0f45c5d private/renet/pkg/infra/pkgset/pkgset.go:208 go test -race rc=0, quality scripts rc=0
- [ ] P2 `pkg/infra/cephpkg`: the per-distro repo, key and version table, the embedded keys with fingerprint check, the lock step and EnsureRepo. Also .ceph-image-pin `host.*` lines and check-ceph-image-pin.ts. Owned: private/renet/pkg/infra/cephpkg/**, private/renet/.ceph-image-pin, scripts/gates/check-ceph-image-pin.ts. Verification: Go tests on the rendered repo files; the gate's `--selftest` fails when one `host.*` line's version differs from `host-version` or the Go table.
- [ ] P3 `renet ceph install --profile`, fork-dest-prep as its alias, `requireSupportedManager` in place of both guards, and i18n. Owned: private/renet/cmd/renet/{ceph_install.go,kube_fork_dest_prep.go,pkg_install_retry.go}, private/renet/pkg/infra/aptretry/**, private/renet/pkg/functions/commands/kube.go, private/renet/pkg/i18n/locales/*.go. Verification: Go tests with a package-manager seam covering exact NEVRs, weak dependencies off and the lock per manager; a control that dropping the version pin fails the test.
- [ ] P4 Provisioner: the node and client installs via renet, Docker CE on dnf Ceph-only nodes, the podman refusal, `--docker` on bootstrap, and prep markers kept. Owned: private/renet/pkg/infra/ceph/provisioner.go and tests. Verification: script-render tests (no `apt-get` literal remains; the pull still starts before the install); the P6 E2E legs.
- [ ] P5 GPU: gpu_drivers.go with dnf and zypper support, the CUDA repos with fingerprinted keys, `--gpu-resolve-only`, the autoinstall refresh fix, and vm_bake_key.py inputs extended to the new file (its completeness walk will otherwise red). Owned: private/renet/cmd/renet/{gpu_drivers.go,setup_command.go}, .ci/rediacc_ci/infra/vm_bake_key.py and its test. Verification: Go tests on the command sequence per manager; the bake-key pytest passes; P6's matrix resolves on all 5 distros.
- [ ] P6 CI: the `Renet pkg matrix` job (renet_pkg_matrix.py with pytest), the 3 non-apt E2E Ceph Workers legs with restore-only cache, the bridge-global-setup.ts version assertion, lane-durations entries, and an OBS/SIG drift check in the nightly. Owned: .github/workflows/ct-tests.yml, .ci/rediacc_ci/infra/renet_pkg_matrix.py and its test, packages/e2e-tests/src/base/bridge-global-setup.ts, .ci/config/lane-durations.json. Verification:
  - one PR run with all 5 matrix legs and all 3 Ceph Workers legs green;
  - a control branch that sets the fedora pin to 19.2.6 fails both the matrix and the harness assertion;
  - no leg exceeds its cap.
- [ ] P7 Measure after: 5 nightly runs. Owned: this plan. Verification: section 4 rewritten with run ids; a p90 over 13 on any new leg returns D6 to the operator.

## 6. Risks

| Risk | Where | Mitigation |
|---|---|---|
| The SIG c10s builds need newer libraries than OL10U1 or Rocky 10 provide | section 1, EL10 row | P0 stop condition; fallback is a joint move to 20.2.4 later |
| OBS rebuild removes the 19.2.3 RPMs | filesystems:ceph:squid/16.0 | D2 mirror, nightly drift check |
| cephadm picks podman, so the pre-pull, `CleanupState` and the other hosts disagree on the engine | ceph container_engines.py line 111; private/renet/pkg/infra/ceph/provisioner.go:578 | weak dependencies off, podman refusal, Docker CE, `--docker` |
| `updates`, the SIG or OBS pushes ceph past the pin | 2a | per-manager lock; matrix `upgrade --assumeno` check |
| The apt node prep regresses while moving into renet | private/renet/pkg/infra/ceph/provisioner.go:515-561 | same bounds (private/renet/cmd/renet/pkg_install_retry.go:23-55); the ubuntu Ceph jobs unchanged in P6 |
| Non-apt Ceph Workers legs break the 15-minute cap | .ci/config/lane-durations.json:1097 | P0 measurement, D6, nightly-only fallback |
| Rocky and CentOS never get E2E proof | private/renet/pkg/infra/opsconfig/images.go:28-37 | container matrix proves install and client tools; stated in the docs |
| GPU proof is resolution only | 1, GPU in CI | D7 DKMS leg; release notes say "not tested on hardware" |
| Leap Minimal's kernel-default-base lacks GPU modules | 2c | warning plus documented kernel-default swap |
| UEK needs kernel-uek-devel; Nvidia kmods target the RHEL kernel | 1, Nvidia | DKMS path; D7 on oracle-10 |
| A key fetch without a fingerprint check trusts the key on first use (today's zypper pattern) | private/renet/cmd/renet/setup_command.go:1541 | embedded keys and fingerprint asserts in P2 and P5 |
| A new cmd/renet file escapes the bake key | vm_bake_key.py completeness walk | P5 updates the inputs |
| F43 reaches EOL and F44 has only 20.x | D8 | pins move together at the image review (.ceph-image-pin review=2026-11-18) |
| ct-tests.yml is contended by the bake plan and the time-budget plan | Depends-On | sequence after bake B5 |

### Critical Files for Implementation
- /home/developer/console/private/renet/pkg/infra/ceph/provisioner.go
- /home/developer/console/private/renet/pkg/infra/pkgset/pkgset.go
- /home/developer/console/private/renet/cmd/renet/ceph_install.go
- /home/developer/console/private/renet/cmd/renet/setup_command.go
- /home/developer/console/.github/workflows/ct-tests.yml
