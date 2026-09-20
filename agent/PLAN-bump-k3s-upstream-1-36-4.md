# PLAN: bump embedded k3s 1.36.3+k3s1 -> 1.36.4+k3s1
Status: compacted
Owner: 9d92d9b6
Full-Text-Blob: eefe7025241c5f21ca0cc86305aec372fdad62b9
Record-Sig: 9b20962c

## Why
check:ci-embed-asset-freshness went red on console PR #579 (branch 0827-1) when k3s upstream released v1.36.4+k3s1 on 2026-08-27 past the soak window. The gate runs on every PR push and blocks with hard mode when a pin is behind upstream. Unrelated to the PR's own work—the world moved, not the tree.

## Outcome
Plan drafted but not executed. The working tree is now on branch 0914-1 with no commits reflecting the bump. The gate failure on 0827-1 and its coordinated rediacc/renet PR #109 remain open but the implementation was deferred in favor of other priorities. The k3s pin remains at 1.36.3+k3s1 in the repositories.

## Lessons
- Checksum drift in lockfiles (k3s arches still named v1.36.2) goes undetected by shape-only validation (check-embed-arch-parity). A single assertion that each arches[*].url contains the component's version would catch this entire class at introduction, not in a follow-up sweep.
- The Dockerfile's sha256sum -c - during Docker build is the expensive, true checksum proof and runs only when the lockfile hash changes (cache miss)—the two hand-checked upstream manifests provided sufficient confidence to defer the full build, but verification still required CI's automated re-run.
- Pre-existing defects found during a bump fix belong in the same commit with a stated reason, not left for a follow-up task—the 1.36.2 drift was already false in embed-assets.lock.json and only became visible during this review.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T17:50:35Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: private/renet/pkg/kube/distro/k3s.go, .github/workflows/ci-build-renet.yml, .gitignore, scripts/gates/check-embed-asset-versions.ts
Gates: check:ci-embed-arch-parity, check:ci-embed-asset-freshness, check:ci-embed-asset-versions, check:ci-embed-credits
Why-Source: model
Read-History: `git show eefe7025241c5f21ca0cc86305aec372fdad62b9` recovers the text; `git log --find-object=eefe7025241c5f21ca0cc86305aec372fdad62b9 --all` names the commit

## History
- 2026-09-20T17:50:35Z compacted by d778be9d from `draft` (record-sig 9b20962c)
