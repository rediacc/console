# Review eeaffe5a: fix(renet): the backup hook machine stand-in compiles only under the renet_test tag

Commit: eeaffe5a5c727f8c32e6f4a4b08d64efb714ce3b
Repo: private/renet
Branch: 1104-1
Parent: 1bbaa073371941c20a6cbdabfa04086b2787ba5f
Patch-Id: 374399f6afa52833fc424c2bf4e4cb015f0c1efe
Reviewed-At: 2026-11-04T17:41:47Z
Model: claude-haiku-5-5
Cost: $0.0052 USD, 1 call(s), 57.2s
Diff: 13816 bytes, 7 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Removes a test seam from the default build and adds the renet_test tag to test and lint invocations; no user-facing behaviour change.
Dropped: 0
Body-Sig: a56adebec9c7d8a7

## Findings

### eeaffe5a.1 [medium] .golangci.yml:12
Anchor: in-diff
Claim: The commit adds renet_test to golangci-lint build-tags, which brings tag-gated files into lint scope; the recorded run exits 1 with four goconst findings and no run before the change is recorded, so the lint gate's state before this commit is unknown and it is failing after it.
Resolution: not-a-bug | cmd/renet/umask_unix.go:10 resolved: golangci-lint with renet_test reports 0 issues on linux, darwin and windows in check:ci-renet | d778be9d 2026-11-06T04:52:44Z

### eeaffe5a.2 [low] pkg/backuphook/standin.go:17
Anchor: in-diff
Claim: UseMachineStandIn is an exported symbol of the public pkg/backuphook package and is removed from default builds, so any external importer of github.com/rediacc/renet/pkg/backuphook that called it stops compiling; the commit does not record whether such importers exist.
Resolution: not-a-bug | private/renet/pkg/backuphook/standin.go:1 no importer outside the private module, and the renet_test tag is deliberate | d778be9d 2026-11-06T21:44:37Z

### eeaffe5a.3 [low] .ci/scripts/quality/deadcode.sh:94
Anchor: in-diff
Claim: Adding renet_test to TEST_BUILD_TAGS makes any production function reachable only from a renet_test-tagged test count as live, so the deadcode gate will no longer report such functions as dead.
Resolution: not-a-bug | private/renet/.ci/scripts/quality/deadcode.sh:90 treating a function reachable from a tag-gated test as live is the script's stated rule | d778be9d 2026-11-06T21:44:37Z
