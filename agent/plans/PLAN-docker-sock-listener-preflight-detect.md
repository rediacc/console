# PLAN: Name a foreign listener on the docker socket before docker hangs

Status: executing
Depends-On: no-dep -- no box waits on another plan
Priority: P2 -- on 2026-11-10 a hijacked docker socket hung every local docker call and crashed build_server onprem (item #a064d591)
Concurrency: parallel -- one writer, files disjoint from every live writer
Owns: .ci/rediacc_ci/core/dockerx.py, .ci/rediacc_ci/drills/backup.py, .ci/rediacc_ci/tests/test_core_dockerx.py, .ci/rediacc_ci/tests/test_core_dockerx_socket.py, .ci/config/shards/quality-pytest.json
First-Seen: 2026-11-10
Owner: d778be9d
Updated: 2026-11-10

## Finding

Measured on 2026-11-10 on this WSL host:

- Docker Desktop's WSL proxy (`docker-desktop-user-distro proxy`, pid 17405) bound `/var/run/docker.sock`, which is the same path as `/run/docker.sock`. It sat over the systemd `docker.socket` that `dockerd -H fd://` listens on.
- `sudo ss -xlpn` showed two listeners on two inodes. The path belonged to the proxy.
- The proxy's disk, sdg, logged `I/O error, dev sdg` in dmesg.
- `timeout 20 docker version` returned rc 124, and a raw `_ping` over the socket hung.
- `build_server onprem` crashed with SIGBUS in the docker client (grpc `status.FromError`).
- `systemctl restart docker` and a containerd restart changed nothing. What worked was `sudo systemctl stop docker docker.socket; sudo rm -f /run/docker.sock; sudo systemctl start docker.socket docker`, after which `docker version` answered 29.9.2.

## Design

`.ci/rediacc_ci/core/dockerx.py` already classifies docker that does not work: its states at :86-90, `state()` at :368, `_ADVICE` near :395, `cannot_run_reason()` at :419 and `require_ready()` at :432. Its WSL advice names Docker Desktop's integration but not the stolen socket, so the detector extends this module instead of starting a new file.

`socket_defect(path="/var/run/docker.sock", *, ping_timeout=3.0, net_unix=None, proc_root="/proc")` returns None when the host is clean. Otherwise it returns one sentence ending in the re-bind command above, and says that a restart of docker alone does not fix it.

It reads listening rows for the realpath of the socket from `/proc/net/unix`, then matches owners through `/proc/<pid>/fd` links (`socket:[<inode>]`) and `/proc/<pid>/comm`. It never shells out to docker. It reports a defect in any of these cases:

- the owner is not `dockerd`, `systemd` or `containerd`;
- more than one listener holds the path;
- a stdlib `AF_UNIX` `GET /_ping` gets no `OK` within the timeout.

It does not report a defect in these cases:

- the path is missing, which is `STATE_UNREACHABLE`'s case;
- the owner cannot be read because of EACCES. Then the ping alone decides, and the message names `sudo ss -xlpn | grep docker.sock`.

The devbox, setup and build_server modules stay untouched. All three are ports checked against a recorded transcript of their bash twins (`.ci/rediacc_ci/core/devbox.py:26`, `test_setup_port.py:58`, `test_ops_build_server.py`), so a new probe there would break parity. They gain the hint through the `socket-check` verb.

## Tasks

- [x] D1 Add the detector `socket_defect` to `dockerx.py`, with an entry in `__all__` and a `socket-check` verb in `main()` that exits 0 when clean and 77 (`CANNOT_RUN_RC`) on a defect. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.core.dockerx socket-check; echo rc=$?` prints rc=0 on this host now.
    (ticked) 2026-11-10T19:00:51Z by d778be9d: commit:db1c62fbd6 commit:994df3ab75; pytest dockerx, socket, backup-integrity, build_server, setup rc 0 (144 passed); socket-check rc 0
- [x] D2 Append `socket_defect()` to the reason in `cannot_run_reason` and `require_ready` when the state is not READY. Extend `_ADVICE[STATE_UNREACHABLE]` and the module docstring with this measurement. Accept: the pytest run of `test_core_dockerx.py` exits 0.
    (ticked) 2026-11-10T19:00:52Z by d778be9d: commit:db1c62fbd6 commit:994df3ab75; pytest dockerx, socket, backup-integrity, build_server, setup rc 0 (144 passed); socket-check rc 0
- [x] D3 In the backup drill preflight, have `preflight_tools` (`drills/backup.py:560-564`) use `dockerx.cannot_run_reason()` in place of the bare, unbounded `docker info` in `_docker_ok` (:3476), and delete `_docker_ok`. Accept: `rg -n "_docker_ok" .ci/rediacc_ci` is empty and the backup preflight tests pass.
    (ticked) 2026-11-10T19:00:53Z by d778be9d: commit:db1c62fbd6 commit:994df3ab75; pytest dockerx, socket, backup-integrity, build_server, setup rc 0 (144 passed); socket-check rc 0
- [x] D4 Add the tests in a new `test_core_dockerx_socket.py`, then run `npm run shard:place -- quality-pytest`. The tests fire on a planted `docker-desktop-` owner, on two listeners, and on a listener that accepts and never answers. They stay silent on a clean host, a missing path, and an EACCES on fd. A control plants a no-op detector and asserts the firing cases go silent. Accept: the pytest run of the new file exits 0 and the shard file changed.
    (ticked) 2026-11-10T19:00:54Z by d778be9d: commit:db1c62fbd6 commit:994df3ab75; pytest dockerx, socket, backup-integrity, build_server, setup rc 0 (144 passed); socket-check rc 0
- [x] D5 Twin guard. Accept: `git diff --name-only` for the plan's commits names nothing under `core/devbox`, `ops/build_server` or `setup/`, and `test_ops_build_server.py` plus `test_setup_port.py` exit 0.
    (ticked) 2026-11-10T19:00:55Z by d778be9d: commit:db1c62fbd6 commit:994df3ab75; pytest dockerx, socket, backup-integrity, build_server, setup rc 0 (144 passed); socket-check rc 0

## Risks

The proxy may run as root, which leaves its fds unreadable. The owner check then degrades to the ping, and the message says so.

A lingering row in `/proc/net/unix` during a restart could trip the two-listener rule, so the message says to verify with `sudo ss -xlpn`.

The ping adds at most 3 s, and only to a preflight that is already failing.
