# PLAN-local-release input A: reuse map (Plan agent a8259d47, 2026-10-27)

Timings source: CI run 39898575743 and CD run 39902042581, read through ci-trace.py. No local build was timed, because a read-only agent cannot write build output.

Corrections to the brief:
- `bump.sh` does not exist. The module is `.ci/rediacc_ci/version/bump.py`.
- The CLI ships 8 targets: 6 native plus 2 musl.

## Steps, by phase

### A. Version and gates
| Step | Code | Local status | Secrets |
|---|---|---|---|
| A1 version | `rediacc_ci.ci.initialize` (cd-v2.yml:170-182) | Wrap. Use `resolve_version --bump-type` | — |
| A2 current version | `resolve_version --current` (cd-v2.yml:160-167) | As is | — |
| A3 existing release | `release.check_existing_release` (cd-v2.yml:190-197) | As is | gh |
| A4 artifact version | `release.assert_artifact_version` (cd-v2.yml:220-234) | Wrap. Read `dist/cli/manifest.json` | — |
| A5 sibling-run gate | (ci.yml:2208-2215) | Replaced by the local receipts | — |
| A6 PR preflight | `release.cd_preflight --phase pr` | As is | `r2-artifacts` |

### B. Builds
| Step | Code | Local status | Secrets |
|---|---|---|---|
| B1 renet, 6 targets | `build_renet` (ci-build-renet.yml:155; build_renet.py:582-607) | As is: CGO=0 cross-build, QEMU for the asset image, BPF falls back to the committed `.o` because clang is missing | `ACCOUNT_ED25519_PUBLIC_KEY`, which only `deploy-proxy` binds |
| B2 release-binary gates | check_no_otlp_creds, no-rclone, proxy_image_smoke | As is | — |
| B3 CLI bundle and npm tarball | `version.bump`, `build.build_cli`, `pack_cli_npm` (ci-build-docker.yml:81-109) | As is | — |
| B4 www and json | `build.build_www` | As is | — |
| B5 SEA linux-x64 | `build.build_cli_executables` | As is, native with smoke | — |
| B6 SEA musl x64 and arm64 | `build.build_cli_musl` | As is; arm64 runs under QEMU | — |
| B7 SEA linux-arm64 glibc | same script | Wrap: run in a linux/arm64 node:24 container | — |
| B8 SEA mac arm64 and x64 | build_cli_executables.py:714 copies the host node, then codesign (:718-760) | CI-only: needs a macOS host node and ad-hoc codesign. No notarization | — |
| B9 SEA win x64 and arm64 | same script | CI-only today. A cross-build is feasible later (blob portable; injector handles PE at :728) | — |
| B10 docker renet amd64 and arm64 | ci-build-docker.yml:621-646 and create_manifest.py | As is with buildx and QEMU | GHCR (operator gh token has write:packages) |
| B11 docker rdc | ci-build-docker.yml:521-545 | As is | GHCR |
| B12 docker server | `build.buildx_push_web` (:310-468) | As is; arm64 under QEMU is the long pole | GHCR, ED25519 |

### C. Stage (cd-stage.yml)
| Step | Code | Local status | Secrets |
|---|---|---|---|
| C1 signed packages | `build.build_linux_packages` (:158) | As is; needs nfpm | `RELEASE_GPG_*`, with no profile yet |
| C2 manifest | `generate_cli_manifest` | As is | — |
| C3 pages | `build_pages` | As is | — |
| C4 package repos | `build_pkg_repo` (:197-224) | As is | GPG |
| C5 retag `:edge` | `.ci/scripts/docker/retag_image.py` (:236-258) | As is | GHCR |
| C6 validate | `release.validate_stage_artifacts` | As is | — |
| C7 R2 cli/edge | `deploy.upload_to_r2` (:332) | As is; the aws CLI is not installed | `r2-artifacts` |
| C8 R2 repos and purge | `deploy.upload_repos_to_r2` (:345) | As is | R2, CF token, `CLOUDFLARE_ZONE_ID` with no profile |
| C9 R2 sentinel | `release.assert_r2_sentinel` | As is | R2 |
| C10 Sigstore provenance | (:379-393) | CI-only: GitHub OIDC | — |

### D. Seal
| Step | Code | Local status |
|---|---|---|
| D1 seal | `deploy.write_release_sentinel` (ci.yml:2216-2226) | As is |
| D2 dispatch CD | `ci.dispatch_release` | Replaced by the orchestrator |

### E. Tag and publish (cd-v2.yml)
| Step | Code | Local status | Secrets |
|---|---|---|---|
| E1 tag | inline bash (:256-272) | Wrap: lift into a module | bot name and email, with no profile |
| E2 CD preflight | `release.cd_preflight --phase cd` | As is | — |
| E3 promote to `:V` and `:latest` | retag_image (:382-392) | As is | — |
| E4 Stripe sync | stripe-sync.ts (:412) | As is | `STRIPE_SECRET_KEY` |
| E5 webhook verify | (:419) | As is | same |
| E6 verify attestation | (:443) | Needs C10 | — |
| E7 hotfix R2 promote | | As is | — |
| E8 hotfix docker promote | | As is | — |
| E9 cleanup channel tags | | As is | — |

### F. Edge Worker deploys
- F1 www: `deploy.deploy_edge` / `deploy_www` (cd-deploy-worker.yml:186). Secrets go through `set_www_worker_secrets`, which has no local profile.
- F2 executor artifacts: `deploy.executor_artifacts stage` (cd-deploy-account.yml:220). Wrap it to take local paths.
- F3 account: `deploy.deploy_account` (:502).
- F4 account secrets: `deploy.account_secrets_local`, 6 profiles.
- F5 proxy: `deploy.deploy_proxy` (:572-610), profile `deploy-proxy`.
- F6 console executor enable, rollback and record: `deploy.console_executor` (:613-662).
- F7 Turnstile drift and price checks (:403-428).

### G. Verify
- G1: `deploy.verify_edge_endpoints` (cd-v2.yml:653).
- G2: install matrix `ct-install-methods.yml` (:668). macOS and Windows stay CI; the Linux quick check can run in local docker.

### H. Tag-and-release (cd-v2.yml:707-855)
- H1: what is owed (inline bash).
- H2: `release.tag_submodules`.
- H3: `release.update_homebrew_tap`.
- H4: `release.advance_contract_floor`.
- H5: `release.create_github_release`.
- H6: hotfix stable deploys.

### I. Stable (promote-stable.yml)
- Soak, tag and rollback checks (:95-176).
- `deploy.promote_r2_to_stable` (:190).
- Docker `:V` to `:stable` for renet and rdc only (:215-227). The hotfix lane also moves server: a divergence.
- Stable deploys (:252-287).
- `verify_stable_endpoints` (:322) and `release.mark_production` (:352).

## ED25519 key
- Baked in through `-X .../keys.ProductionPublicKey` (build_renet.py:156, 266-273, 582).
- No release gate refuses an empty key or the DEV key. build.sh:414-444 falls back to the DEV key from `private/account/.cache/public-keys.env` with only a warning.
- On the cached path, extract_renet_from_image.py:478-486 cross-builds darwin and windows renet with no key and no version.
- Gate to add: a fingerprint check reusing `testrun/start_backup_plane.py --verify-renet`, which reads the key through `go version -m`. It refuses an empty key, the DEV fingerprint and `tags=nolicense`.

## New bws profile
`release-local` binds `RELEASE_GPG_PRIVATE_KEY`, `RELEASE_GPG_PASSPHRASE`, `GIT_BOT_NAME`, `GIT_BOT_EMAIL`, `CLOUDFLARE_ZONE_ID`, `STRIPE_SECRET_KEY` and the www Worker secrets. All of these are already in bws-secret-map.json.

## CI-only gaps and the smallest job to keep
- mac and win SEAs, plus the mac and win install legs: one dispatch workflow, "local-release-assist", with 4 legs. It uploads to R2 staging and runs in parallel from minute zero.
- Provenance: operator choice. Either a local-release bypass in `verify_artifact_attestation` with a SHA256 manifest, or an attest dispatch.
- Tag, tap and Release pushes on the App token: check the rulesets. If they refuse the operator token, a tiny dispatch job mints the cd token.

## Timings
- CI from push to dispatch: about 39 min. The CD critical path is about 19-20 min. One green pair end to end: about 60 min.
- CI per job:
  - renet: 3.8 min warm, 16.7 min cold
  - SEAs: linux 1.8, musl 1.6 and 1.3, mac 1.1 and 3.5, win 2.4 and 9.0 min
  - docker: renet 6.9, server 3.2 per arch, rdc 2.3 min
  - stage: 10.7 min
  - publish: 4.2 min
  - www: 3.1 min
  - account: 1.7 min per region
  - install: 5.6 min
  - Tag and GitHub Release: 3.8 min
- Local estimate: 30-45 min sequential, 20-25 min parallel. Uploading about 1.5 GB over home bandwidth may dominate.

## Risks
- R1: the DEV-key fallback.
- R2: sentinel and tag ordering, which needs its own local test.
- R3: token and ruleset attribution.
- R4: attestation.
- R5: mac and win.
- R6: tools missing locally (aws, nfpm, clang), so the devbox may be required.
- R7: www media.
- R8: no concurrency lock, so the plan needs a release lock.
- R9: server:stable divergence.
- R10: upload size.
