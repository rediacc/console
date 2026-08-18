# PLAN: renet fetch hardening (remaining sweep from closed renet PR #96)
Status: draft
Owner: housekeeping writer agent, branch main
Updated: 2026-08-05

## Status

One of the eight sites is fixed; seven remain, plus two recorded as out of
scope. renet PR #96 (rediacc/renet, a PRIVATE repo, so deliberately NOT
hyperlinked here: check:ci-external-links reaches it unauthenticated and a
private URL always reads as a 404 broken link) was closed without
merging, and its closing comment is the only surviving record of the inventory,
so this file exists to keep that inventory somewhere a future session will
actually find it.

**2026-08-18: THE LINE NUMBERS HAVE DRIFTED AGAIN. RE-VERIFY EVERY ONE BEFORE
ACTING.** Spot-checked against `private/renet` at `d53e1d3` (2026-08-17): the two
reference sites quoted just below no longer resolve. `setup_command.go:1128` is
now the tail of one function plus the head of `installPackagesDnf`, and
`:1375-1376` is `installDockerRHEL`'s doc comment, not the retry loop. The
inventory's own file:line entries are therefore suspect too; treat them as
search hints and re-locate each site by CONTENT.

This file already records that the numbers it inherited from PR #96 had drifted
once. They have now drifted a second time, which says the failure is structural:
an inventory keyed to line numbers in a moving file decays on its own. If this
sweep is picked up, key it to function names.

Every file:line below was re-verified against the working tree on 2026-08-05.
Several of the numbers carried on the PR had drifted and are corrected here;
one entry (`build.sh`) was recorded with three line numbers that no longer
describe anything, and the correction is noted inline.

The retry idiom this sweep converges on is already in the tree in two places
and is what "hardened" means for the rest of the list:

- `cmd/renet/setup_command.go:1128` (`installPackagesApt`): 5 attempts, 15s
  backoff, `exit 1` after the loop.
- `cmd/renet/setup_command.go:1375-1376` (Docker install): the same loop, plus a
  `dpkg -l docker-ce` check after it so an all-attempts-failed loop cannot
  report success. This is the shape to copy, because the post-loop check is
  the part that matters: a bare `for ... done` exits with the status of its
  LAST command, which is the `sleep` in the failure branch, always 0.

## DONE

### `cmd/renet/setup_command.go:1329-1346` (Docker GPG key fetch)

Fixed 2026-08-05. Was a single unretried
`curl -fsSL https://download.docker.com/linux/<os>/gpg -o /etc/apt/keyrings/docker.asc`,
sitting between two neighbours that both already retried 5x/15s. Now carries
the same loop, streams its output, and asserts a NON-EMPTY keyring after the
loop (`[ -s ... ] || exit 1`) rather than mere existence: `curl -f` writes
nothing on an HTTP error, but a partial transfer leaves a truncated file that
an existence check would accept.

Gates: `gofmt -l` clean, `go build -tags nolicense ./...` clean,
`go vet -tags nolicense ./cmd/...` clean, `golangci-lint run --build-tags
nolicense ./cmd/renet/...` 0 issues.

## REMAINING (7 sites, roughly in priority order)

### 1. `Dockerfile:165` and `Dockerfile:223`: the two rsync tarball curls

```
RUN curl -fsSL "https://download.samba.org/pub/rsync/src/rsync-${RSYNC_VERSION}.tar.gz" -o /tmp/rsync.tar.gz && \
```

One in `rsync-builder-amd64`, one in `rsync-builder-arm64`, byte-identical
otherwise. **Corrected count:** the PR said "2 of 12"; the file actually has 8
`curl -fsSL <url>` fetch invocations (165, 223, 286, 311, 338, 358, 382, 402)
and these are the only 2 without a retry loop. The other 9 `curl` mentions are
apt package names, not fetches. The neighbours at 286/311 (rclone) and
338/358/382/402 (zot, k3s) all use the 5x/15s idiom already, so this is a
consistency gap inside one file.

Risk: `download.samba.org` is a single origin with no CDN in front of it, and a
flake fails the whole multi-arch image build, not one layer. The SHA256 pin on
the following line (`166`, `224`) verifies WHAT was downloaded, never THAT the
download happened, so the pin is no mitigation here.

### 2. `pkg/infra/ceph/provisioner.go:351-352`: Ceph prerequisites apt

```
sudo apt-get update -y && \
sudo apt-get install -y cephadm ceph-common sshpass btrfs-progs xfsprogs lvm2
```

Inside `InstallPrerequisites`, which loops over `p.cfg.VMCephNodes`. Risk: this
runs once PER NODE, so an N-node cluster is N independent chances to hit a
mirror flake, and any one of them aborts the whole provision with a
`failed to install prerequisites on node <n>` that says nothing about the
mirror. Highest expected-value fix on this list for that reason.

### 3. `pkg/infra/ceph/provisioner.go:434`: cephadm bootstrap

```
sudo cephadm bootstrap --mon-ip %s --ssh-user %s 2>&1 | tee /tmp/ceph_admin_info.txt
```

Risk: `cephadm bootstrap` pulls container images from `quay.io` implicitly, so
this is a network fetch that does not look like one. It is also the longest
step in the flow (15+ minutes, per the keepalive comment at
`pkg/infra/ceph/provisioner.go:1438`), which makes a naive retry expensive and
a partial-bootstrap re-run non-trivial. Note that `verifyBootstrapAfterDisconnect`
already exists as a recovery path for the disconnect case; whatever retry lands
here must compose with it rather than duplicate it.

### 4. `cmd/renet/kube_fork_dest_prep.go:53-54`: unretried apt

```
sudo apt-get update -y && \
sudo apt-get install -y ceph-common sqlite3
```

### 5. `pkg/infra/worker/service.go:100-101`: unretried apt

```
sudo apt-get update -qq
sudo apt-get install -y -qq libprotobuf-c1 libnet1 libnl-3-200
```

### 6. `pkg/infra/docker/service.go:688-693` (`ensureRclone`): unretried apt

```
sudo apt-get update -y >/dev/null
sudo apt-get install -y rclone >/dev/null
```

Risk for 4, 5 and 6 together: all three are the SAME operation
`installPackagesApt` already retries at `cmd/renet/setup_command.go:1128`, so
whether a package install survives a mirror flake currently depends on which
code path happened to reach it. `ensureRclone` is the worst of the three
because it is called from four sites (`pkg/infra/docker/service.go:441, 564,
612, 669`) and swallows its output to `/dev/null`, so its failure arrives with
no diagnostic at all.

### 7. `cmd/renet/ops_host.go:371` and `:402`: `curl get.docker.com | sh`

```
curl -fsSL https://get.docker.com | sh
```

371 is the apt/Debian branch, 402 the dnf/RHEL branch. Risk: both run under
`set -e` inside a provisioning script, and a piped `curl | sh` fails in two
distinct ways that look alike here (fetch failure vs. the fetched script
failing). Any retry must not re-run a half-applied Docker install, so this one
needs the fetch and the execute separated before it can be looped, which is why
it sits below the plain apt sites despite being a raw internet pipe.

### 8. Build- and CI-only pulls (lowest priority, not product code)

- `build.sh:586`: `docker pull "$DOCKER_REGISTRY/rediacc/renet:latest"`.
  **Correction:** the PR recorded `build.sh:324,521,577`. Those line numbers do
  not correspond to any fetch in the current file; `build.sh` contains no
  `curl`/`wget` at all, and its only network operations are `docker push` at
  540 and 582 plus this pull.
- `scripts/ci-test.sh:326`: `docker pull traefik:v3.6`.
- `scripts/ci-test.sh:343`: `docker pull "$image"` (already `|| log_warn`, so
  it degrades rather than aborts).

Risk: a flake here costs a CI re-run, not a broken machine. Note also that the
two real download sites in `scripts/ci-test.sh` (103 and 147, the CRIU tarball)
already pass `--retry 3 --retry-delay 5`, so this file is mostly done.

## OUT OF SCOPE (deliberate, not forgotten)

### `pkg/compose/exec.go:312` and `pkg/proxy/compose.go:90-92`

```
cmd := exec.Command("docker", "compose", "--project-directory", projectDir, "-f", tmpFileName)
args := append(composeCmd[1:], "up", "-d", "--wait")
```

Both are `docker compose up`, and both pull images implicitly as part of that.
They are excluded because they are the USER-FACING PRODUCT PATH: `rdc repo up`
and the proxy bring-up are commands an operator runs and watches, and a silent
retry changes observable behaviour (how long the command appears to hang, what
a Ctrl-C interrupts, whether a genuinely wrong image tag fails fast or after
five backoffs). Hardening these is a product decision about the failure UX, not
the mechanical consistency fix the rest of this list is, and it wants its own
decision rather than riding along here.

## Verification

Anything landing from this list carries, from `private/renet`:

```
gofmt -l <files>                                          # clean
go build -tags nolicense ./...                            # exit 0
go vet -tags nolicense ./cmd/... ./pkg/...                # exit 0
golangci-lint run --build-tags nolicense ./cmd/... ./pkg/...  # 0 issues
```

Go commands must run from `private/renet`, the module root, not the console
root. Shell files (`build.sh`, `scripts/ci-test.sh`) also need
`shfmt -i 4 -ci -d`.

A retry loop with no post-loop failure check is NOT a fix, for the reason
recorded at `cmd/renet/setup_command.go:1118-1125`: 5 failed attempts still
exit 0, so the hardening reads as green while the install is broken. Every
entry above must land with its own "did the thing actually happen" assertion.
