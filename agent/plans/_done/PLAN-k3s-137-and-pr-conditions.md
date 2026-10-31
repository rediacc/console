# PLAN: k3s 1.37.1, and a liveness clause for "REVISIT WHEN PR #N MERGES"

Status: done -- 2026-10-15, every box ticked (5 of 5); closed when check:ci-plan-record RF refused the open Status (operator order 2026-10-15, #1201d7b9). Was: approved -- operator /ask 2026-10-08T02:13Z: "Next branch, own commit" (worklist #9b4e7449)
Depends-On: no-dep -- the k3s hold it lifts is stale since PR #589 merged on 2026-09-22; writer B lands after writer A inside this plan
Owner: d778be9d
First-Seen: 2026-10-08
Priority: P1 -- a stale hold kept an embedded runtime one minor behind for 16 days and no gate noticed
Concurrency: parallel -- two writers, disjoint files; A commits before B
Owns: private/renet/Dockerfile, private/renet/embed-assets.lock.json, private/renet/pkg/embed/embed.go, private/renet/pkg/embed/credits_data.go, packages/cli/src/data/third-party-credits.json, .ci/policy/.embed-assets-upgrade-blocklist, .ci/rediacc_ci/core/allowlist.py, scripts/lib/blocker-validator.ts, scripts/lib/suppression-liveness.ts, scripts/gates/check-suppression-liveness.ts, scripts/gates/check-pr-condition-ledger.ts, .ci/config/merged-prs.json, docs/agent-reference/suppressions.md
Worklist: #9b4e7449

## Why

`.ci/policy/.embed-assets-upgrade-blocklist` (lines 15-28 at 6779389a9, before f0354ce23 lifted the hold) held k3s at 1.36.4+k3s1 with "REVISIT WHEN PR #589 MERGES". PR #589 merged 2026-09-22T08:22:16Z.

The list parser (`.ci/rediacc_ci/core/allowlist.py` `parse_text` ~300-321) uses only the `# BLOCKER:` line as the reason, so the condition never reaches a checker. The liveness probes ask only whether the entry still exists (`scripts/gates/check-suppression-liveness.ts:339-348`).

## A. k3s 1.36.4+k3s1 -> 1.37.1+k3s1

The release was published 2026-09-30. Upstream sha256 files give:
- amd64 `92b94582eb7b34a8cf532e6006842b9ed215a6783cf56a3dd6271fd35243b2c0`;
- arm64 `a1561ca4aef8b99f5588a840d4468ac39c8c1cd92470bbcb9634823fa221741a`.

The writer re-verifies both against the upstream files before using them.

The version lives in these places:
- Dockerfile `K3S_VERSION`, at 333 and 353;
- `K3S_SHA256_AMD64` (334) and `K3S_SHA256_ARM64` (354);
- `private/renet/pkg/embed/embed.go:61` `AssetK3sVersion`, which `private/renet/pkg/kube/distro/k3s.go:229,265,407` read;
- `embed-assets.lock.json`: version 142, upstreamSourceUrl 148, plannedMirrorUrl 149, and the arches url+sha256 at 160-161 and 165-166. check:ci-embed-arch-parity cross-checks the arches (10679ea46).
- The generated credits: `credits_data.go` and `third-party-credits.json`, via `npx tsx scripts/gen/generate-embed-credits.ts`.
- The blocklist block, which is deleted.

Old version strings stay as they are:
- `private/renet/pkg/kube/distro/distro_test.go:25` (a fixture);
- `scripts/gates/check-embed-asset-versions.ts:331` (a parser self-test);
- the design-spec measurements.

**Kubernetes 1.37 against renet.** Its manifests use only stable groups (`private/renet/pkg/kube/csidriver/objects.go:34-181`, `private/renet/pkg/kube/csidriver/pki.go:105`), and none of its k3s flags (`private/renet/pkg/kube/distro/k3s.go:132-200`) is among the removed flags. Three things still need a live run:
- `--embedded-registry` under 1.37.1's change that rejects anonymous supervisor endpoints. The Multinode lane exercises it.
- SELinuxMount going GA, which matters on RHEL hosts only.
- In-place `kube upgrade` of a 1.36 data dir (kine 0.16.4 -> 0.17.1, etcd 3.6.14 -> 3.7.1). No lane covers it, so it is a manual check or a recorded gap.

**VM bake.** `.ci/rediacc_ci/infra/vm_bake_key.py:86,102` hashes `pkg/embed` and the lockfile, so the first run rebakes the VM images. Budget for it.

**Steps and checks:**
1. `npx tsx scripts/gates/check-embed-asset-freshness.ts --upgrade`, then set the hashes and `embed.go`.
2. The lockfile; check: `check:ci-embed-arch-parity`.
3. Regenerate the credits; checks: `check:ci-embed-credits` and `--check`.
4. Delete the hold; check: `check:ci-embed-asset-freshness` rc 0.
5. renet `go build ./...`, `go vet ./pkg/embed/`, `go test ./pkg/kube/... ./pkg/embed/...`, then `check:ci-renet`.
6. CI acceptance: E2E K8s, E2E K8s Ceph and E2E K8s Multinode SUCCEEDED, not skipped (`.github/workflows/ct-tests.yml:1232/1404/1585`).

**Packaging.** One renet commit on a renet branch named like the console branch, and one console commit with the pointer, the CLI credits and the lifted hold. This follows the zot precedent (a322a9215).

## B. The PR-condition clause

**Clause.** `REVISIT WHEN PR #<N> MERGES`, case-insensitive. It also takes the form `<owner>/<repo>#N` and may sit anywhere in an entry's comment block.
- It is parsed by a new canonical verb, `allowlist.py conditions <file>`, which emits `<line>\t<entry>\t<repo#N>\t<clauseLine>`. The `records` output and the contract version stay unchanged.
- `blocker-validator.ts` gets `parseConditions()`.
- A lint refuses loose wording that names a PR (the regex `(?i)\b(revisit|lift|remove|drop)\b.*\b(when|once|after|until)\b.*#\d+`).

**Offline.** check-suppression-liveness gets a fail-tier probe, `pr-conditions`, over every BLOCKER file. `BLOCKER_FILES` (:851-862) moves to `scripts/lib/suppression-liveness.ts`. The probe reads a committed `.ci/config/merged-prs.json` (`{format:1, refreshed_at, prs:{"rediacc/console#589":{mergedAt}}}`): an entry whose PR is listed fails, naming the clause and the merge time. This keeps the rule that a gate is offline by construction (`docs/agent-reference/suppressions.md:48,111`).

**Online.** A new `check-pr-condition-ledger.ts` with `--refresh`:
- It asks GitHub only about the PRs clauses name, and fails when one is merged on GitHub but not in the file.
- With no token, it skips loudly locally and fails in CI. A network error is `::warning` and exit 0.
- It has a `PR_STATE_FIXTURE` seam.
- `/pr-merge` runs `--refresh` when it cuts the next branch.

**Tests** (in `test_gate_suppression_liveness.py`, on the frozen corpus `goldens/allowlist/corpus/embed-assets-upgrade-blocklist.list`, which still holds the #589 clause):
- the corpus is red with #589 in the file and green without it;
- the probe-removed mutant is green;
- loose wording is red;
- the online fixture covers merged-but-not-recorded (red), a network error (warning) and CI with no token (red).

**Docs.** `suppressions.md`: the clause format, a liveness table row, and the committed merged-PR file.

**Sweep.** The only PR-conditioned entry is the #589 one, which A deletes. Two `.go-deps-upgrade-blocklist` entries depend on a tag rather than a PR:
- `:23`: protobuf v1.36.12 is tagged, and renet's `go.mod:36` is already on it, so this hold looks half-met.
- `:32`: waits on a grpc tag.

Both get their own worklist item.

## Writers

- **A (sonnet): the renet bump.**
  - Owns: `private/renet/{Dockerfile, embed-assets.lock.json, pkg/embed/embed.go, pkg/embed/credits_data.go}`, `packages/cli/src/data/third-party-credits.json` and `.ci/policy/.embed-assets-upgrade-blocklist`.
- **B (opus, gate-author): the clause.**
  - Owns: `.ci/rediacc_ci/core/allowlist.py`, `scripts/lib/{blocker-validator.ts, suppression-liveness.ts}`, `scripts/gates/check-suppression-liveness.ts`, the new `scripts/gates/check-pr-condition-ledger.ts`, `.ci/config/merged-prs.json`, the tests and `docs/agent-reference/suppressions.md`.
  - The `package.json` script and the generated ci-quality step are reported to the lead to apply.

## Boxes

- [x] A: k3s 1.37.1 in the Dockerfile, embed.go, the lockfile and the credits; hold deleted; embed gates, renet tests and check:ci-renet green
    (ticked) 2026-10-08T10:15:17Z by d778be9d: commit:7f9c30578 k3s 1.37.1+k3s1 in the Dockerfile, private/renet/pkg/embed/embed.go:61, lockfile and credits; hold deleted; embed freshness, arch-parity and credits gates rc0
- [x] B: `allowlist.py conditions`, the `pr-conditions` probe and the merged-PR file; corpus red/green, mutant and loose-wording controls
    (ticked) 2026-10-08T10:15:20Z by d778be9d: commit:87ff68b45 parse_conditions at .ci/rediacc_ci/core/allowlist.py:445, the pr-conditions probe and .ci/config/merged-prs.json
- [x] B: `check-pr-condition-ledger.ts` online gate with its fixture cases; wired by the lead
    (ticked) 2026-10-08T10:15:25Z by d778be9d: commit:87ff68b45 scripts/gates/check-pr-condition-ledger.ts wired; selftest 25 controls; its pytest assertion fixed in commit:8f8aaaa84
- [x] Sweep: worklist items for the two go-deps tag holds
    (ticked) 2026-10-08T10:15:29Z by d778be9d: commit:d93a1be4c kubelet hold lifted (renet 1dbe423); the grpc and go-landlock holds stay valid
- [x] CI: E2E K8s, K8s Ceph and K8s Multinode SUCCEEDED on the branch head (not skipped); in-place upgrade of a 1.36 data dir checked by hand or recorded as a gap
    (ticked) 2026-10-13T19:51:43Z by d778be9d: commit:33373f934 PR 600 run 38451759370 on b6a60de8c: E2E K8s 115487816638, K8s Ceph 115487816554, K8s Multinode 115487816657 success, 0 skipped; in-place 1.36 upgrade is the recorded gap (plan line 42)

## Risks

- If B lands before A, the branch is red until A lands.
- The online gate turns branches red when an unrelated PR merges. That is intended.
- The bake-key change forces a VM rebake.
- The K8s lanes can be scoped out.
- No lane tests an in-place 1.36 -> 1.37 upgrade.
