# Review ac47a2ab: feat(reporuntime): the kube and docker runtimes run Rediaccfile functions under the lifecycle default

Commit: ac47a2ab89dc656d5addd64d4d0aa1ff29f79df2
Repo: private/renet
Branch: 1104-1
Parent: cb9be231ca5720fa5f14bf84915495ce8204c73b
Patch-Id: 8c1d3259b6338032e1828ae83d5ed910fb79d501
Reviewed-At: 2026-11-04T13:58:10Z
Model: claude-haiku-5-5
Cost: $0.0130 USD, 1 call(s), 93.1s
Diff: 80472 bytes, 22 files, truncated: yes
Unreviewed: pkg/reporuntime/kube.go
Verdict: findings
Attempt: 1
Labels: bump=minor kind=bug,feature why=Changes the default so kube and docker Rediaccfile functions run sandboxed as the universal user, a security fix that alters runtime behaviour.
Dropped: 0
Body-Sig: 27da4603b4fa41fb

## Findings

### ac47a2ab.1 [medium] cmd/renet/sandbox_exec_runtime_linux_test.go:591
Anchor: in-diff
Claim: Docker up/down/health now run under the sandboxed default, but TestDockerRuntime_FunctionsRunAsTheUniversalUser's Rediaccfile never calls docker, so the universal user's access to the per-network DOCKER_HOST socket is untested by this commit.
Resolution: open

### ac47a2ab.2 [medium] pkg/reporuntime/contract_fixture_docker_test.go:50
Anchor: in-diff
Claim: Setting rt.lifecycle = unsandboxedLifecycle means the package's CT-01..15 contract suite no longer runs docker functions through the production lifecycle default, so a regression that drops the sandbox is caught only by the root-only cmd/renet test.
Resolution: not-a-bug | read against the current tree: private/renet/cmd/renet/sandbox_exec_runtime_linux_test.go:586 root-only test covers the production default | d778be9d 2026-11-04T17:14:44Z

### ac47a2ab.3 [low] pkg/orchestration/rediaccfile.go:229
Anchor: in-diff
Claim: AddReadExecutePath (and AddReadOnlyPath at 222) return silently when sandboxOpts is nil, so a path a runtime asks to grant on an executor built without a sandbox is dropped with no error or log.
Resolution: open
