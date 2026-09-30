# PLAN: decision D2 -- keep the openSUSE Leap 16.0 Ceph pin alive after OBS drops it
Status: active -- D2 of PLAN-renet-ceph-gpu-non-apt was approved 2026-09-29 (operator took D1-D8 defaults) and never built; OBS dropped 19.2.3-lp160.2.96 on 2026-09-30 and reddened the Leap legs of #591
Depends-On: no-dep -- the parent plan is closed and its bake store (D1) is live and private
Owner: d778be9d
First-Seen: 2026-09-30
Date: 2026-09-30
Parent: agent/plans/_done/PLAN-renet-ceph-gpu-non-apt.md (D2, line 187; risk table line 233)
Scope: design verified against renet 0699199. Worklist #3ee91218.
Priority: P1 -- the captured build 2.97 disappears on the next OBS rebuild
Concurrency: exclusive -- it edits the Leap install path and the pkg matrix every Ceph leg depends on
Owns: .ci/rediacc_ci/infra/obs_mirror.py, .ci/rediacc_ci/tests/test_infra_obs_mirror.py, .github/workflows/ci-obs-mirror.yml, .ci/rediacc_ci/infra/renet_pkg_matrix.py, private/renet/cmd/renet/ceph_install.go, private/renet/cmd/renet/ceph_mirror_test.go, private/renet/pkg/infra/cephpkg/cephpkg.go, private/renet/pkg/infra/opsconfig/config.go

## 1. Problem

- Leap installs `ceph-common`/`cephadm` pinned to one OBS build (`hostPins["opensuse-16.0"]`, private/renet/pkg/infra/cephpkg/cephpkg.go:63) with `zypper -n in --no-recommends ceph-common=<pin> cephadm=<pin>` (cephpkg.go:344-345) from `obsBaseURL` (cephpkg.go:50). The pin also lives in private/renet/.ceph-image-pin; scripts/gates/check-ceph-image-pin.ts:92-120 holds them equal.
- OBS `filesystems:ceph:squid/16.0` keeps only its latest build. 2.96 vanished on 2026-09-30 (zypper exit 104 on #591's Leap legs); renet 0699199 moved the pin to 2.97, a stopgap until the next rebuild.
- The only D2 piece in place is the unused hook `Options.ZypperBaseURL` (cephpkg.go:159-163, applied :319-321); the one production caller passes only `WithoutCephadm` (cmd/renet/ceph_install.go:146).
- `check_drift` (.ci/rediacc_ci/infra/renet_pkg_matrix.py:307-344) runs right after the install (:440-446), so it reds at the same moment the install breaks, not before.

## 2. Mechanism: the original OBS repodata, unmodified, plus only the RPMs renet takes

**Chosen (A): a plain-directory rpm-md repo.** A byte copy of OBS `repodata/` (`repomd.xml`, `.asc`, `.key` and every href it references) and only the packages renet installs from this repo, at the same `x86_64/`/`noarch/` paths. The signature on `repomd.xml` still verifies against the key renet embeds and fingerprint-checks (cephpkg.go:337-339); `repo_gpgcheck`/`pkg_gpgcheck`/`gpgcheck` (cephpkg.go:330-333) stay on; `primary` checksums match because the files are the same. libzypp fetches a package only when the solver picks it, so listed-but-absent packages cost nothing unless needed, which capture and the negative control (section 6) rule out. `leapPlan` is unchanged apart from the baseurl, and `check_drift`'s `zypper se -r rediacc-ceph-squid` keeps working.

**Rejected (B): loose RPMs, `rpm --checksig`, `zypper in /path/*.rpm`.** A second install path with its own steps, an explicit package list nothing resolves, no `repo_gpgcheck` on command-line repos, and variants of the `name=pin` argv, the `addlock` step (cephpkg.go:346-347) and the drift query.

Facts to verify in P1, each by a test: libzypp accepts `dir:`/`file:`/`http://` rpm-md baseurls; an old validly signed `repomd.xml` carries no expiry; capture reads the origin `https://downloadcontent.opensuse.org/repositories/filesystems:/ceph:/squid/16.0/`, not the redirector; the OBS key expires 2027-05-07 (`key-expiry.obs`), the mirror's hard end-of-life unless OBS extends the same key, which the existing gate reds 30 days ahead of.

## 3. The artifact

- Store: the already-private `ghcr.io/rediacc/ci-vm-bake` (`REPOSITORY`, .ci/rediacc_ci/infra/vm_bake_image.py:45). A new package is created public on first push and only the operator can flip it (.github/workflows/ci-vm-bake.yml:38-42); public Ceph binaries would also carry a GPL source-offer duty.
- Tag `obs-mirror-v1-opensuse-16.0-<pin>`; artifactType `application/vnd.rediacc.obs-mirror.v1`; one uncompressed tar whose root is the baseurl; annotations `repomd-sha256`, `repomd-revision`, `captured-at`, `obs-origin`, `packages`.
- Immutable: capture probes first (`tag_exists`, vm_bake_image.py:147-160), never overwrites, reads the tag back after push (vm_bake_image.py:219-247); a same-EVR rebuild with a new repomd keeps the first copy and warns.

## 4. File-level changes

Console:
1. New `.ci/rediacc_ci/infra/obs_mirror.py` (imports `install_oras`/`tag_exists` from vm_bake_image.py; pure parsers/verifiers):
   - `upstream`: fetch origin `repomd.xml` + `.asc`, gpgv against private/renet/pkg/infra/cephpkg/keys/RPM-GPG-KEY-obs-filesystems-ceph after asserting `OBSKeyFingerprint` (cephpkg.go:42); fetch `primary`, check its checksum; print the current `ceph-common`/`cephadm` EVR; GITHUB_OUTPUT `obs_evr`, `pin`.
   - `capture --evr <EVR>`: stop on an existing tag; download all repodata, checksum each file against repomd, retry up to 3 times from a fresh repomd on a mid-publish mismatch; refuse when `primary` does not list `<EVR>` for both packages; derive the package set in an `opensuse/leap:16.0` container with the built renet (the `cmd_run` technique, renet_pkg_matrix.py:501-535) by running `renet ceph install` for `admin`, `client`, `fork-dest` against the origin plus a `zypper -n in --dry-run --no-recommends` of `pkgset.CephNode`'s zypper names, intersecting `rpm -qa` and the dry-run's NEW rows with `primary`; download each RPM, check sha256 against `primary`, `rpm -K` with only the OBS key; run section 6's positive and negative checks; `oras push`; read back.
   - `fetch --pin <PIN> --dest <dir>`: pull and unpack; a miss is rc 1 (the mirror is mandatory in CI).
   - `serve --dir <dir> --port 8089`: detached `python3 -m http.server` on 0.0.0.0 for the E2E VMs, which reach the runner at 192.168.111.1 (private/renet/pkg/infra/opsconfig/config.go:84).
2. New `.github/workflows/ci-obs-mirror.yml`: schedule `23 */6 * * *`, `workflow_dispatch` (input `evr`), push to main on private/renet, obs_mirror.py and itself; `permissions: {}` with the job at `contents: read`, `packages: write`, main only (as ci-vm-bake.yml:10-31); GHCR login with `github.token` (ci-vm-bake.yml:86-91); `upstream`; `capture --evr $obs_evr` (OBS's CURRENT build, pinned or not) and `capture --evr $pin`; step summary. Every OBS build is captured within 6 hours while OBS still serves it.
3. .github/workflows/ct-tests.yml: `renet-pkg-matrix` (:936-997) gains `packages: read`, a GHCR login and `--obs-mirror` for opensuse-16.0; `test-e2e-ceph-workers-rpm` (:1011-1140, already `packages: read` + login at :1016-1019, :1065-1070) gains `obs_mirror fetch` + `serve` and `CEPH_ZYPPER_MIRROR=http://192.168.111.1:8089/` before `create_e2e_env`.
4. renet_pkg_matrix.py: `cmd_run --obs-mirror` fetches the tag for the pin, bind-mounts it read-only at /srv/obs-mirror and writes `/etc/rediacc/ceph-zypper-mirror` = `dir:/srv/obs-mirror` in the container, the same file customers would use; a miss is a FAIL naming the pin and the dispatch that fixes it; `check_drift` becomes `mirror serves the pin`; new zypper-only `check_upstream`; docstring (:20-22).

Renet:
5. cmd/renet/ceph_install.go `supportedPlan` (:142-147) passes `ZypperBaseURL: cephZypperMirror()`: `REDIACC_CEPH_ZYPPER_MIRROR`, else the first line of `/etc/rediacc/ceph-zypper-mirror`; validated in the style of `safeAptMirror` (cmd/renet/setup_command.go:1076-1093), schemes https/http/dir/file only; an invalid value warns and falls back to OBS; the source is logged. The file is the real channel: the provisioner runs `sudo renet ceph install` over SSH (private/renet/pkg/infra/ceph/provisioner.go:644, :1983), which drops the environment.
6. pkg/infra/cephpkg/cephpkg.go: the `ZypperBaseURL` comment (:159-162) names the file, the env var and the "OBS-signed repodata served unmodified" contract; export `MirrorConfigPath`.
7. pkg/infra/opsconfig/config.go: `CephZypperMirror` from env `CEPH_ZYPPER_MIRROR` (beside :336-446).
8. ops up writes `/etc/rediacc/ceph-zypper-mirror` on every VM before setup or provisioning (worker.Service.Setup, private/renet/pkg/infra/worker/service.go:36; the Ceph-node prep path, provisioner.go:558), including under the baked-image skip (packages/e2e-tests/src/base/bridge-global-setup.ts:190-211).
9. .ceph-image-pin: the `host.opensuse-16.0` comment states "bump only to an EVR that has an obs-mirror tag; the matrix reds otherwise".

## 5. The drift check

OBS removes the old build in the same publish that adds the new one, so "red before breakage" means CI cannot be moved onto an uncaptured build, and the upstream move reds on a schedule rather than on PRs.

| Check | Runs | Compares | Red when |
|---|---|---|---|
| mirror present (matrix fetch) | PRs touching the pin, nightly | .ceph-image-pin pin vs the GHCR tag list | the pin moved to an uncaptured EVR, at PR time, before merge |
| `mirror serves the pin` (`check_drift`) | same | `zypper se` on the mirror vs the pin | the artifact is corrupt or does not list the pin |
| `check_upstream` (new, zypper, nightly only) | scheduled matrix | OBS origin `primary` EVR vs the pin | OBS moved: RED, naming the new EVR and whether it is mirrored |
| capture freshness | ci-obs-mirror, every 6 h | OBS current EVR vs the tag list | a capture fails |

`check_upstream` does not run on PRs, so an OBS rebuild cannot redden unrelated PRs, which is what happened on #591.

## 6. Tests, each with a control

- obs_mirror unit tests: repomd parse and href listing; a checksum mismatch errors (control: correct checksum passes); gpgv refuses a one-byte-tampered `repomd.xml` (control: untampered verifies); the fingerprint assert refuses another key; the package-set intersection excludes Leap OSS packages; `capture` on an existing tag pushes nothing (control: a miss pushes once and reads back); an EVR absent from `primary` is refused.
- Capture-time, in fresh `opensuse/leap:16.0` containers with download.opensuse.org and downloadcontent resolved to 127.0.0.1: POSITIVE all three profiles install from `dir:` staging and `rpm -q` equals the EVR; NEGATIVE 1 staging minus `librados2` must FAIL (proves zypper reads the mirror); NEGATIVE 2 a one-byte change to `repomd.xml` must fail `zypper refresh` (proves `repo_gpgcheck`).
- renet: extend `TestOptionsZypperBaseURL` (private/renet/pkg/infra/cephpkg/cephpkg_test.go:517); new cmd/renet/ceph_mirror_test.go (env beats file; bad scheme or quote-escaping ignored with a warning; empty is OBS).
- renet_pkg_matrix: a fetch miss is FAIL; `check_upstream` red on EVR != pin, green on equal, skipped off-schedule.
- E2E Ceph Workers non-apt opensuse-16.0 installs node and client from the served mirror, the only proof of the `node` package set and the http scheme; one rehearsal dispatch without the mirror must fail once OBS has moved, recorded in the round log.

## 7. Customers

D2 as ruled covers CI only: a private GHCR artifact is unreachable from a customer host. Without Q1 answered otherwise, customers stay on OBS plus the exact pin; between an OBS rebuild and the renet release that bumps the pin, `renet ceph install` on Leap fails with zypper 104. `check_upstream` reds within about 24 hours, the bump is one line and already mirrored, so the window equals release latency. Customers may point `/etc/rediacc/ceph-zypper-mirror` at their own copy, documented with the "unmodified OBS repodata" contract.

## 8. Risks

- Package-set gaps on paths CI does not install surface as "not found on medium" in the first leg that needs the package; capture's profile list must grow with renet.
- Fork PRs cannot read a private package with `github.token`: skip the Leap mirror legs on forks with a notice (Q4), nightly covers them.
- A baked Leap image that already carries Ceph does not touch the mirror (RENET_SETUP_OFFLINE, ct-tests.yml:405-428); the stock-container matrix stays the proof.
- Two OBS rebuilds within 6 hours lose the middle, unpinned build.
- The OBS key expires 2027-05-07.
- Tag growth: about 4 builds a year at about 150 MB; any bake pruning must exclude the `obs-mirror-` prefix.

## 9. Open questions (defaults execute)

- Q1 customers: (a) OBS plus the pin, accepting the release-latency window; (b) publish the captured tree plus SRPMs to public R2 (`media.rediacc.com/ceph/opensuse-16.0/<pin>/`) as renet's default Leap baseurl with OBS as fallback; (c) upstream-version-only match (`ceph-common=19.2.3`), which survives same-version rebuilds only. DEFAULT (a) now, (b) as the follow-up, which needs operator approval for public redistribution and R2 cost.
- Q2 store: DEFAULT reuse the private ci-vm-bake package.
- Q3 capture cadence: DEFAULT every 6 hours.
- Q4 fork PRs: DEFAULT skip the Leap mirror legs with a notice.
- Q5 `check_upstream` severity: DEFAULT red on the nightly only.

## Tasks

- [x] P1 renet: `cephZypperMirror` (env, then /etc/rediacc/ceph-zypper-mirror; validated; logged) wired into `supportedPlan`; cephpkg comment + `MirrorConfigPath`; opsconfig `CephZypperMirror`; ops up writes the file on every VM; tests with controls
    (ticked) 2026-09-30T08:53:34Z by d778be9d: renet 3372cbb + 335ce80: cephZypperMirror wired into supportedPlan (cmd/renet/ceph_install.go:153), ops up writes/removes /etc/rediacc/ceph-zypper-mirror; go test ./cmd/renet/ ./pkg/infra/cephpkg/ ./pkg/infra/opsconfig/ ok, 9 mirror subtests with controls; renet quality rc=0
- [ ] P2 console: obs_mirror.py (upstream, capture, fetch, serve) with unit tests and the capture-time positive/negative container checks; ci-obs-mirror.yml; merge, then dispatch to capture 2.97 while OBS serves it (branch dispatch if P2 cannot merge first)
- [ ] P3 renet_pkg_matrix `--obs-mirror` and `check_upstream`; ct-tests matrix login + flag; E2E fetch/serve/env; one full-ci run
- [ ] P4 rehearsal dispatch with OBS blocked, recorded in the round log
- [ ] P5 docs (www ceph install: the mirror file), .ceph-image-pin comment, D2 moved to done in the parent plan's risk table
