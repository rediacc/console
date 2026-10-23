# PLAN: a repo compose can likely reach the host's system Docker through /run/docker.sock, because the dockerd sandbox binds host /run read-write and the compose validator does not flag /run

Status: draft -- write-up only (operator decision 2026-10-23: record it, do not fix in the hostinger follow-up); needs a repro on a throwaway fork before a fix is chosen
Owner: 5008cebe
First-Seen: 2026-10-23
Priority: P1 -- proposed by AI. If the repro confirms it, any repo (including a fork or a third-party template) can drive the system Docker daemon that runs `rediacc-proxy` (Traefik) and therefore every machine's routing, and through it start a privileged container on the host. That breaks the per-repo isolation renet's sandbox exists to provide.
Concurrency: parallel
Owns: private/renet/pkg/compose/validate.go, private/renet/pkg/compose/validate_test.go, private/renet/cmd/renet/daemon_containerd_exec.go (the RW bind list only), private/renet/docs/DOCKERD_SANDBOX.md
Worklist: (the lead adds this with worklist.py --add)

## How it was found

On hostinger (2026-10-23), the observability repo's Alloy bound `/var/run/docker.sock:/var/run/docker.sock:ro`. Inside the container that path was an empty directory, because the per-repo dockerd resolves bind sources inside its mount sandbox, where `/var/run` holds only the `rediacc` bind (`docs/DOCKERD_SANDBOX.md` table, lines 95-130). Reading why led to the gap below.

## The gap

- The sandbox binds the host's `/run` recursively and read-write: `cmd/renet/daemon_containerd_exec.go:169` (`"/run"`, commented as needed for `/run/containerd` visibility; `docs/DOCKERD_SANDBOX.md:111`). On Ubuntu the system Docker socket is `/run/docker.sock` (`/var/run` is a symlink to `/run` on the host).
- The compose validator does not flag `/run`: `pkg/compose/validate.go:31` lists `dangerousHostPaths = {"/etc", "/sys", "/proc", "/var", "/boot", "/root"}`, and `checkVolumeHostPath` (`validate.go:214`) returns no error for a path outside that list. A bind of `/run/docker.sock` therefore passes without even the soft "outside the repo" error that `--unsafe` would be needed for.
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
- Also document the supported way for a container to reach its own repo's daemon: `${DOCKER_SOCKET}:/var/run/docker.sock` (`pkg/orchestration/up_down_workflows.go:224`).

## Tasks

- [ ] T1 [lead] Run the repro above on a throwaway fork and record the outcome here.
- [ ] T2 [R] Implement the chosen fix (A and/or B) with `validate_test.go` cases for `/run/docker.sock`, `/run/containerd/containerd.sock` and `${DOCKER_SOCKET}` (allowed).
- [ ] T3 [R] Update `docs/DOCKERD_SANDBOX.md` with the outcome and the `${DOCKER_SOCKET}` guidance.
