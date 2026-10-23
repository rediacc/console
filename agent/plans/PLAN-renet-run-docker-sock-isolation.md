# PLAN: a repo compose can likely reach the host's system Docker through /run/docker.sock, because the dockerd sandbox binds host /run read-write and the compose validator does not flag /run

Status: draft -- write-up only (operator decision 2026-10-23: record it, do not fix in the hostinger follow-up); needs a repro on a throwaway fork before a fix is chosen
Depends-On: no-dep -- a write-up that cites no other plan's work
Owner: 5008cebe
First-Seen: 2026-10-23
Priority: P1 -- proposed by AI. If the repro confirms it, any repo (including a fork or a third-party template) can drive the system Docker daemon that runs `rediacc-proxy` (Traefik) and therefore every machine's routing, and through it start a privileged container on the host. That breaks the per-repo isolation renet's sandbox exists to provide.
Concurrency: parallel
Owns: private/renet/pkg/compose/validate.go, private/renet/pkg/compose/validate_test.go, private/renet/cmd/renet/daemon_containerd_exec.go (the RW bind list only), private/renet/docs/DOCKERD_SANDBOX.md
Worklist: (the lead adds this with worklist.py --add)

## How it was found

On hostinger (2026-10-23), the observability repo's Alloy bound `/var/run/docker.sock:/var/run/docker.sock:ro`. Inside the container that path was an empty directory, because the per-repo dockerd resolves bind sources inside its mount sandbox, where `/var/run` holds only the `rediacc` bind (`docs/DOCKERD_SANDBOX.md` table, lines 95-130). Reading why led to the gap below.

## The gap

- The sandbox binds the host's `/run` recursively and read-write: `private/renet/cmd/renet/daemon_containerd_exec.go:169` (`"/run"`, commented as needed for `/run/containerd` visibility; `private/renet/docs/DOCKERD_SANDBOX.md:111`). On Ubuntu the system Docker socket is `/run/docker.sock` (`/var/run` is a symlink to `/run` on the host).
- The compose validator does not flag `/run`: `private/renet/pkg/compose/validate.go:31` lists `dangerousHostPaths = {"/etc", "/sys", "/proc", "/var", "/boot", "/root"}`, and `checkVolumeHostPath` (`private/renet/pkg/compose/validate.go:214`) returns no error for a path outside that list. A bind of `/run/docker.sock` therefore passes without even the soft "outside the repo" error that `--unsafe` would be needed for.
- Expected effect: `volumes: ["/run/docker.sock:/var/run/docker.sock"]` in any repo gives its container the host's system Docker API. The same applies to anything else under host `/run` (systemd, containerd's system socket at `/run/containerd/containerd.sock`).

## Repro (do this first, on a throwaway fork, never on a production repo)

1. Fork any small repo, add a service `image: docker:cli`, `command: ["docker", "ps"]`, volume `/run/docker.sock:/var/run/docker.sock:ro`.
2. `rdc repo up <repo>:<tag>`; expected if the gap is real: the output lists `rediacc-proxy` (a system Docker container), and no validator warning was printed.
3. Repeat with `/run/containerd/containerd.sock`.
4. Delete the fork.

## Fix options (to decide after the repro)

- **A (validator):** add `/run` (and `/var/run` is already covered) to `dangerousHostPaths`, and treat `*/docker.sock` / `*/containerd.sock` outside `/var/run/rediacc/` as a hard error, not a soft one. Cheap, but it guards only compose files renet validates.
- **B (sandbox):** stop binding all of host `/run`. Bind only what dockerd/containerd need (`/run/containerd` if still needed, or nothing), so the host sockets do not exist in the sandbox at all. This is the real isolation fix; it needs the containerd/dockerd startup re-tested on Ubuntu 24.04 and Debian.
- Both together are likely right: B for isolation, A so users get a clear error instead of an empty directory.
- Also document the supported way for a container to reach its own repo's daemon: `${DOCKER_SOCKET}:/var/run/docker.sock` (`private/renet/pkg/orchestration/up_down_workflows.go:224`).

## Tasks

- [ ] T1 [lead] Run the repro above on a throwaway fork and record the outcome here.
- [ ] T2 [R] Implement the chosen fix (A and/or B) with `validate_test.go` cases for `/run/docker.sock`, `/run/containerd/containerd.sock` and `${DOCKER_SOCKET}` (allowed).
- [ ] T3 [R] Update `docs/DOCKERD_SANDBOX.md` with the outcome and the `${DOCKER_SOCKET}` guidance.

## T1 result (2026-10-23)

CONFIRMED: a repo compose that binds host `/run/docker.sock` passes renet's validator with no error or warning, and the container it starts drives the host's system Docker daemon -- a different daemon from the repo's own. The per-repo isolation is breached exactly as the gap predicted.

Fleet and binary. The worker `ops-worker` is 192.168.111.11, running `renet version` `0.0.0-dev` (`/usr/bin/renet` -> `/usr/lib/rediacc/renet/0.0.0-dev/renet`), Ubuntu 24.04.4, Docker 29.9.2. The repro ran on a throwaway fork of `vmcheck-base`, deleted at the end.

The host's two system sockets and a canary. On the worker, `/run/docker.sock` and `/var/run/docker.sock` are both live (`/var/run` is a symlink to `/run`), and `/run/containerd/containerd.sock` is present. The system daemon's id is the discriminator used throughout:

```
$ sudo docker --host unix:///run/docker.sock info -f '{{.ID}}'
2bf0ce0d-5e5e-4577-92a6-2e231872ad48
```

A labelled canary container was planted on that system daemon (`t1-host-canary`, `busybox:latest`) so "can the repo container list host containers" has a positive answer. It stayed in `Created` state because the system daemon's `docker0` bridge is absent on this VM; it still lists, which is all the probe needs.

The fork. `rdc repo fork vmcheck-base@ops-worker --tag t1sock` created `vmcheck-base:t1sock` (guid `1144757e-3bb8-4706-98cc-16cbb6c754e4`, network 8000); `rdc repo up` mounted it and started its own dockerd at `/var/run/rediacc/docker-8000.sock`, whose id differs from the system daemon's:

```
$ sudo docker --host unix:///var/run/rediacc/docker-8000.sock info --format '{{.ID}}'
c07f454f-ec96-4a72-8be1-95a47b5e0dad
```

The validator gap. A `docker-compose.yml` was written into the fork mount with one service binding both host sockets, sources under `/run`:

```yaml
    volumes:
      - "/run/docker.sock:/var/run/docker.sock:ro"
      - "/run/containerd/containerd.sock:/mnt/containerd.sock:ro"
```

`renet compose --network-id 8000 --show-config` accepted it with exit 0 and no validation line at all, keeping both binds verbatim in the processed config. By contrast, an earlier variant that bound the host directory `/var/run` did draw the soft error `bind mount to "/var/run" is outside the repo`, because `/var` is in `dangerousHostPaths` -- but the socket binds under `/run` drew nothing, hard or soft. `/run` is not in `dangerousHostPaths` (`private/renet/pkg/compose/validate.go:31`), and `*/docker.sock` is not special-cased, so the dangerous mount sails through where a harmless data directory under `/var` would at least warn.

The breach. `renet compose --network-id 8000 -- up -d` started the service, and its logs show the container reached the system daemon, not its own:

```
RUN_SOCK:
srw-rw----    1 root     991              0 Oct 21 09:11 /var/run/docker.sock
DAEMON_ID:
2bf0ce0d-5e5e-4577-92a6-2e231872ad48
HOST_PS:
t1-host-canary|busybox:latest|Created
CONTAINERD_SOCK:
srw-rw----    1 root     root             0 Oct 21 09:11 /mnt/containerd.sock
```

The `DAEMON_ID` the container read through its bound `/var/run/docker.sock` is `2bf0ce0d...`, the host system daemon -- not the repo's own `c07f454f...`. It listed `t1-host-canary`, a container this repo never created. The host's containerd socket is likewise a live socket node inside the container (`srw-rw----`, the host's Oct 21 timestamp), though `docker:cli` cannot speak the containerd API to exercise it. The per-repo dockerd resolves the bind source inside its mount sandbox, where host `/run` is bound read-write recursively (`private/renet/cmd/renet/daemon_containerd_exec.go:169`), so `/run/docker.sock` there is the host socket.

The `:ro` on the bind is not a mitigation. It makes the socket file node read-only, not the Docker API: `info` and `ps` are ordinary API calls that succeeded, and `create`/`run` would too (only the absent `docker0` bridge stopped the canary from reaching `running`). On a routing host the system daemon runs `rediacc-proxy` and every machine's routing, so a repo reaching it can start a privileged container on the host and drive the proxy.

What a fix must block. A bind whose source resolves to a host socket under `/run` (and the `/var/run` symlink alias) -- at least `/run/docker.sock`, `/var/run/docker.sock`, `/run/containerd/containerd.sock` -- must be a hard validator error, not the soft "outside the repo" notice, and `${DOCKER_SOCKET}` (the repo's own daemon, `private/renet/pkg/orchestration/up_down_workflows.go:224`) must stay allowed. That is fix A. Because the validator only guards compose files renet parses, the durable fix is B: stop binding all of host `/run` read-write into the sandbox, so the host sockets do not exist in the repo's view at all. The repro supports doing both.

Teardown. `renet compose -- down` removed the service, the canary was removed from the system daemon, and `rdc repo delete vmcheck-base:t1sock --yes` deleted the fork; `renet repository list` afterwards shows only the two pre-existing repos and the system daemon has no containers.
