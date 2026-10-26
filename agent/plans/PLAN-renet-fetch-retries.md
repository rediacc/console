# PLAN: renet fetch hardening (the two sites still unhardened from closed renet PR #96)
Status: approved -- the operator approved the rewrite 2026-10-23 (/ask, ruling #0c1cbd0d): a validation found six of the eight sites done or superseded, leaving two boxes
Owner: d778be9d
Updated: 2026-10-23
Depends-On: no-dep -- cites no other plan
First-Seen: 2026-09-17
Priority: P3 -- a flake here costs a retry or a CI re-run, not a broken machine
Concurrency: parallel -- the two boxes edit disjoint files; Owns: decides overlaps
Owns: private/renet/pkg/infra/ceph/provisioner.go, private/renet/pkg/infra/ceph/prepare_script_test.go, private/renet/build.sh, private/renet/scripts/ci-test.sh

renet PR #96 (rediacc/renet, a PRIVATE repo, so deliberately NOT hyperlinked here: check:ci-external-links reaches it unauthenticated and a private URL always reads as a 404 broken link) was closed without merging, and its inventory of unretried fetches is what this plan descends from. The inventory was keyed to line numbers, which drifted twice; this rewrite keys every site to a function or command, so it cannot decay the same way.

A retry loop with no post-loop "did the thing happen" check is NOT a fix: a bare `for ... done` exits with the status of its last command, the `sleep` in the failure branch, always 0. Every box below lands with its own assertion.

## Already fixed (not boxes)

Validated against `private/renet` on 2026-10-23.

- Rsync tarball curls in `private/renet/Dockerfile` (`rsync-builder-amd64`, `rsync-builder-arm64`): the 5x/15s loops and the non-empty check are in.
- The apt install in `kube_fork_dest_prep` (`private/renet/cmd/renet/kube_fork_dest_prep.go`): goes through `retryPkgInstall` (`private/renet/cmd/renet/pkg_install_retry.go`).
- The VM tool-install helper (`private/renet/pkg/infra/docker/service.go`): the retry loops are in, with a post-loop check.
- The `get.docker.com` fetch in `private/renet/cmd/renet/ops_host.go`: split into a retried fetch and a single execute.
- Superseded: the Ceph prerequisites apt in `InstallPrerequisites`. The node prep now runs `renet ceph install --profile node`, whose package install goes through `retryPkgInstall` in `private/renet/cmd/renet/ceph_install.go`.
- Superseded: the CRIU runtime-deps apt in `private/renet/pkg/infra/worker/service.go`. It is delegated to `renet setup`, which retries it.
- The Docker GPG key fetch in `private/renet/cmd/renet/setup_command.go` was fixed 2026-08-05 and is the reference shape (5 attempts, 15s backoff, a non-empty assertion after the loop).
- The retried bounded pre-pull of `CephImagePin` already exists: the prerequisites script in `private/renet/pkg/infra/ceph/provisioner.go` runs `docker.PullRetryScript(CephImagePin, CephImagePin)` (`renderPullRetry` in `private/renet/pkg/infra/docker/service.go`, 5 attempts, 15s, `exit 125` after the last) in the background beside the Ceph package install. What is missing is the post-pull assertion, which Box A below carries.

## Out of scope (deliberate)

`docker compose up` in `private/renet/pkg/compose/exec.go` and `private/renet/pkg/proxy/compose.go` pulls images implicitly. These are the user-facing product path (`rdc repo up`, proxy bring-up), and a silent retry changes how long the command appears to hang, what a Ctrl-C interrupts and whether a wrong image tag fails fast. That is a failure-UX decision, not this mechanical consistency fix.

## Boxes

- [x] Box A: in `private/renet/pkg/infra/ceph/provisioner.go`, assert the image is present after the existing bounded pre-pull of `CephImagePin`, with `docker image inspect` run after the pull wait in the prerequisites script, failing the step with a message naming the image when it is absent. It composes with `verifyBootstrapAfterDisconnect` and never retries the whole bootstrap, which runs 15+ minutes and is not safe to re-run blind. Acceptance: from `private/renet`, `gofmt -l pkg/infra/ceph` prints nothing, `go build -tags nolicense ./...` and `go vet -tags nolicense ./cmd/... ./pkg/...` exit 0, `go test -tags nolicense ./pkg/infra/ceph/...` exits 0 with a new case in `private/renet/pkg/infra/ceph/prepare_script_test.go` that makes the inspect fail and requires the step to fail naming `CephImagePin`.
    (ticked) 2026-10-25T05:50:33Z by d778be9d: renet f2034e7: docker image inspect after image-pull-wait, TestPrereqScriptAbsentImageAfterPullFails; go test ./pkg/infra/ceph/... rc=0 Accept re-run 2026-10-26 from private/renet: gofmt -l pkg/infra/ceph prints nothing; go build -tags nolicense ./... rc=0; go vet -tags nolicense ./cmd/... ./pkg/... rc=0; go test -tags nolicense ./pkg/infra/ceph/... rc=0.
- [x] Box B: give the bare `docker pull "$DOCKER_REGISTRY/rediacc/renet:latest"` in `private/renet/build.sh` and the bare `docker pull traefik:v3.7.16` in `private/renet/scripts/ci-test.sh` retry loops (5 attempts, 15s, matching `renderPullRetry`), each followed by a post-loop `docker image inspect` check that fails the step when the image is missing. The `docker pull "$image" || log_warn` line in `private/renet/scripts/ci-test.sh` already degrades rather than aborts and stays. Acceptance: from `private/renet`, `shfmt -i 4 -ci -d build.sh scripts/ci-test.sh` prints nothing, and `grep -n "image inspect" build.sh scripts/ci-test.sh` shows a check after each loop.
    (ticked) 2026-10-25T05:50:54Z by d778be9d: renet f2034e7: 5-attempt pull loops with a post-loop image inspect in build.sh and scripts/ci-test.sh; bash -n rc=0 Accept re-run 2026-10-26: shfmt -i 4 -ci -d build.sh scripts/ci-test.sh rc=0 with empty output (run in the devbox). The loops later moved into the shared helper scripts/pull-with-retry.sh (renet 9a0c631), whose post-pull docker image inspect sits at private/renet/scripts/pull-with-retry.sh:21 and is covered by private/renet/scripts/pull_with_retry_test.go; private/renet/build.sh:706 and private/renet/scripts/ci-test.sh:335 call it.

## Verification

From `private/renet`, the module root, never the console root:

```
gofmt -l <files>                                          # clean
go build -tags nolicense ./...                            # exit 0
go vet -tags nolicense ./cmd/... ./pkg/...                # exit 0
golangci-lint run --build-tags nolicense ./cmd/... ./pkg/...  # 0 issues
```

Shell files also need `shfmt -i 4 -ci -d`.
