# eBPF Network Isolation Plan

## Problem

All containers use `network_mode: host`, placing them in PID 1's network namespace. Services bind to assigned loopback IPs (`127.x.x.x`) for port isolation, but any process can connect to any loopback address on the machine — including addresses belonging to other repos. A fork's pgadmin can connect to the production postgres and mutate data.

---

## What Was Tried and Why Each Failed

### 1. Subnet-based iptables INPUT rules
**Idea:** DROP packets where source is in subnet A going to subnet B.

**Why it failed:** For loopback traffic, the Linux kernel always selects the *destination* IP as the source IP. A connection from any process to `127.0.39.195` produces `SRC=127.0.39.195 DST=127.0.39.195`. Source-based subnet rules never match. Confirmed via iptables LOG rule in production.

### 2. GID-based iptables OUTPUT rules (`-m owner --gid-owner`)
**Idea:** Inject networkID as container's supplementary GID via `group_add`. Match outbound connections by `--gid-owner networkID` in OUTPUT chain.

**Why it failed:** `iptables --gid-owner` only checks the process's effective/filesystem GID (`fsgid`). Container processes run as root (`fsgid=0`). Even though the injected GID appeared in `/proc/pid/status` under `Groups:`, iptables only matched `--gid-owner 0`. Confirmed by LOG: `--gid-owner 0` fired, `--gid-owner 16640` did not.

### 3. Per-repo named network namespaces + `network_mode: ns:/path`
**Idea:** Run each Docker daemon inside `ip netns add rediacc-<networkID>`. Containers with `network_mode: "ns:/var/run/netns/rediacc-<N>"` would land in the repo's isolated namespace.

**Why it failed:**
- Docker Engine does NOT support `network_mode: "ns:/path"`. The daemon rejects it with "network ns:/path not found" (treats it as a named Docker network). Only nerdctl supports this (PR #3538, Oct 2024). Upstream blocker: **moby/moby#47828** — open feature request.
- `ip netns exec` calls `unshare(CLONE_NEWNS)` creating a new mount namespace where `/sys/fs/cgroup` is missing → Docker fails with "Devices cgroup isn't mounted". Switching to `nsenter --net` fixes cgroup visibility but the root problem remains:
- `network_mode: host` in Docker **always** uses PID 1's namespace regardless of which namespace the daemon runs in. Containers in `host` mode escape to PID 1's namespace. Confirmed: container cgroup inode ≠ repo namespace inode.

### Why Docker bridge networking achieves isolation but ours cannot
Docker bridge creates separate network namespaces per container. Inter-container traffic flows via veth pairs through a bridge — real interfaces. The FORWARD chain intercepts this with genuine source IPs (e.g. `172.17.0.2`). Subnet-based FORWARD rules work because source ≠ destination. Our host mode puts everything on PID 1's shared loopback where source=destination.

---

## The eBPF Solution

### Core idea
`BPF_PROG_TYPE_CGROUP_SOCK_ADDR` programs attach per-cgroup and intercept socket calls **before** they reach the kernel's networking stack. Two hooks solve everything:

| Hook | What it does |
|------|-------------|
| `BPF_CGROUP_INET4_BIND` | Intercepts `bind()` — transparently rewrites `0.0.0.0`/`127.0.0.1` → `SERVICE_IP` |
| `BPF_CGROUP_INET4_CONNECT` | Intercepts `connect()` — blocks loopback connections outside the container's own `/26` subnet |

Since Docker containers each have their own cgroup (cgroupv2), one BPF program per container achieves complete per-container isolation. Works for all binaries regardless of language, static/dynamic linking, or setuid — the program runs at the kernel cgroup boundary, not the library layer.

### Why this fixes the source IP problem
With `bind()` rewriting, the socket is explicitly bound to `SERVICE_IP`. The kernel then uses `SERVICE_IP` as the outbound source for connections. Our original subnet-based rules would work too — but the `connect()` hook makes them redundant.

---

## Minimum Kernel Version

**Required: Linux 6.1 — NO fallback, NO graceful degradation.**

renet must refuse to start (exit with error) on kernels below 6.1.

### eBPF requirements (all met at 6.1)
- `BPF_PROG_TYPE_CGROUP_SOCK_ADDR` with address rewriting: 4.17
- `bpf_get_current_cgroup_id()`: 4.18
- `BPF_PROG_REPLACE` for atomic program updates: 5.5
- cgroupv2 unified hierarchy as default: 5.10 LTS
- Combined with CRIU requirement (`CHECKPOINT_RESTORE` capability): 5.9

### BTRFS requirements — the primary driver for 6.1 minimum

renet uses BTRFS for all repository storage and relies on CoW cloning for forking. The 6.x series contains critical BTRFS improvements that are not backported to 5.x:

| Fix / Feature | Kernel | Why it matters for renet |
|---------------|--------|--------------------------|
| Block-group-tree (`-O bg-tree`) | **6.1** | Reduces mount time to 21% of original on large datastores with many repos; 30s → <1s |
| Inode logging optimization | **6.1** | ~25% throughput improvement, ~21% lower latency — directly benefits repo up/down |
| Async buffered writes (io_uring) | **6.1** | 2× throughput, 2.2× IOPS for CoW fork operations |
| FIEMAP orders-of-magnitude speedup | **6.1** | Used for disk space reporting and backup size estimation |
| Snapshot deletion optimization | **6.1** | Prevents qgroup bottleneck when deleting many fork repos |
| Async discard by default | **6.2** | Automatic SSD trim on freed repo storage; reduces space waste |
| **RAID5 destructive RMW fix** | **6.2** | Critical data corruption fix: without this, small writes to RAID5 could silently corrupt parity |
| Async discard IOPS tuning | **6.3** | Prevents disks from never idling under default settings |
| **Direct I/O page-fault corruption fix** | **6.4** | Critical: partial DIO write could write zeros instead of data |

**Kernel 6.1 LTS** is the minimum because it ships the block-group-tree feature and the inode/snapshot optimizations that make BTRFS operationally sound for a repo store with O(100s) of repositories. 6.2+ fixes are also critical but Debian 12 (the most conservative supported distro) ships 6.1.

### Combined kernel requirement matrix

| Image (from `pkg/infra/config/images.go`) | Kernel | eBPF (≥5.10) | BTRFS (≥6.1) | Status |
|-------------------------------------------|--------|--------------|--------------|--------|
| ubuntu-24.04 | **6.8** | ✓ | ✓ | Recommended |
| debian-12 | **6.1 LTS** | ✓ | ✓ (baseline) | Supported |
| fedora-43 | **6.12** | ✓ | ✓ | Supported |
| fedora-41 | **6.8** | ✓ | ✓ | Supported |
| centos-10-stream | **6.10+** | ✓ | ✓ | Supported |
| opensuse-15.6 | **5.14** | ✓ | ✗ misses 6.1 fixes | **Needs upgrade** |
| rocky-9 | **5.14** (RHCK) | ✓ | ✗ | **Needs upgrade** |
| oracle-9 (UEK R8) | **6.8** | ✓ | ✓ | Supported |
| oracle-9 (RHCK) | **5.14** | ✓ | ✗ | **Needs upgrade** |
| oracle-8 | **5.4** (UEK6) | ✗ | ✗ | **Unsupported** |

**Action required in `pkg/infra/config/images.go`:**
- `opensuse-15.6` (kernel 5.14): does not meet BTRFS minimum. Options:
  - Replace with openSUSE Tumbleweed (rolling, kernel 6.x) for cutting-edge use
  - Or wait for openSUSE Leap 16 (expected 2025, will ship kernel 6.x)
  - For now: add a `MinKernelVersion` field to `OSImage` struct and set it to "6.1" as documentation; renet should warn/reject when deploying BTRFS-dependent features on this image
- `oracle-8`: below eBPF minimum entirely — remove or mark unsupported
- `rocky-9`: ships 5.14 with RHCK by default; Rocky 9 with kernel 6.x requires EPEL or ELrepo — document as "needs kernel upgrade"

**Startup check in renet** (`cmd/renet/main.go` or `pkg/ebpf/manager.go`):
```go
// minKernelVersion is the minimum for full renet functionality:
// - 5.9: CRIU CHECKPOINT_RESTORE capability
// - 5.10: eBPF cgroupv2 support (BPF_PROG_TYPE_CGROUP_SOCK_ADDR)
// - 6.1: BTRFS production stability (block-group-tree, CoW optimizations,
//         snapshot qgroup fixes, inode logging ~25% improvement)
// All supported images in pkg/infra/config/images.go ship ≥6.1 kernels
// except opensuse-15.6 (5.14) which needs upgrading.
const minKernelVersion = "6.1"

func checkKernelVersion() error {
    var uname syscall.Utsname
    if err := syscall.Uname(&uname); err != nil {
        return fmt.Errorf("cannot determine kernel version: %w", err)
    }
    version := utsRelease(uname.Release[:])
    if !meetsMinimum(version, minKernelVersion) {
        return fmt.Errorf(
            "kernel %s is too old (minimum: %s). "+
            "Reasons: eBPF cross-repo isolation requires 5.10+; "+
            "BTRFS production stability (CoW fork performance, snapshot safety, "+
            "direct I/O corruption fixes) requires 6.1+. "+
            "Upgrade to kernel 6.1 LTS or later.",
            version, minKernelVersion,
        )
    }
    return nil
}
```

Also check:
- cgroupv2 is mounted at `/sys/fs/cgroup` (type `cgroup2fs`)
- `BPF_PROG_TYPE_CGROUP_SOCK_ADDR` is supported via `bpf(BPF_PROG_TYPE_CGROUP_SOCK_ADDR, ...)` probe

### Recommended kernel for new deployments

**6.6 LTS or higher** — captures all 6.1–6.6 BTRFS improvements including the direct I/O corruption fix (6.4) and full async discard tuning. Ubuntu 24.04 (kernel 6.8) is the ideal default image and is already set as default in `GetDefaultImage()`.

---

## Implementation

### Dependency
```
github.com/cilium/ebpf v0.21.0
```
(Released March 2025. Requires Go 1.21+ which renet already uses.)

### Repository structure
```
private/renet/pkg/ebpf/
├── socket_isolation.c           # BPF program — runs inside kernel (~80 lines C)
├── socket_isolation_bpf.go      # Auto-generated by bpf2go (Go bindings + embedded bytecode)
├── socket_isolation_bpfeb.o     # Big-endian BPF object (generated)
├── socket_isolation_bpfel.o     # Little-endian BPF object (generated, primary)
├── manager.go                   # Go: load, attach, detach, atomic update
└── manager_test.go              # Tests: verifier pass, map ops, attach/detach
```

The C file is compiled to BPF bytecode at **build time only** by `bpf2go` using `clang --target=bpf`. Bytecode is embedded in the renet binary via `//go:embed`. `clang` is NOT required on target machines.

### BPF program (socket_isolation.c)

```c
//go:build ignore

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>
#include <sys/socket.h>

struct cgroup_config {
    __u32 service_ip;    // container's assigned loopback IP (network byte order)
    __u32 subnet_base;   // e.g. 0x7F002700 for 127.0.39.192/26
    __u32 subnet_mask;   // /26 = 0xFFFFFFC0
};

// Per-cgroup config map: cgroup_id -> {service_ip, subnet_base, subnet_mask}
//
// Map sizing rationale:
//   - Key: __u64 cgroup_id (8 bytes)
//   - Value: struct cgroup_config (12 bytes)
//   - Kernel overhead: ~64-96 bytes per entry (htab_elem + bucket metadata)
//   - Total per entry: ~84 bytes
//   - 65,536 entries × 84 bytes ≈ 5.5 MB — trivial on any modern machine
//
// 65,536 covers ~1,300 repos × 50 containers each — sufficient for the largest
// practical single-machine deployments. The networkID space allows ~261,944
// total repos but no single machine would run that many simultaneously.
//
// BPF_MAP_TYPE_LRU_HASH instead of HASH: automatically evicts least-recently-used
// entries if the limit is ever hit, rather than failing with E2BIG.
// BPF_F_NO_PREALLOC: memory grows on demand instead of allocating all 5.5 MB upfront.
struct {
    __uint(type, BPF_MAP_TYPE_LRU_HASH);
    __uint(max_entries, 65536);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, __u64);   // cgroup_id
    __type(value, struct cgroup_config);
} cgroup_configs SEC(".maps");

// Intercept bind(): rewrite 0.0.0.0 and 127.0.0.1 to SERVICE_IP
SEC("cgroup/bind4")
int handle_bind(struct bpf_sock_addr *ctx) {
    if (ctx->user_family != AF_INET) return 1;
    __u64 cgid = bpf_get_current_cgroup_id();
    struct cgroup_config *cfg = bpf_map_lookup_elem(&cgroup_configs, &cgid);
    if (!cfg || !cfg->service_ip) return 1;
    __u32 dst = ctx->user_ip4;
    // Rewrite wildcard (0.0.0.0) and standard localhost (127.0.0.1) to SERVICE_IP
    if (dst == 0 || dst == bpf_htonl(0x7F000001))
        ctx->user_ip4 = cfg->service_ip;
    return 1;
}

// Intercept connect(): block cross-repo loopback connections
SEC("cgroup/connect4")
int handle_connect(struct bpf_sock_addr *ctx) {
    if (ctx->user_family != AF_INET) return 1;
    __u32 dst = ctx->user_ip4;
    // Only care about loopback range (127.x.x.x)
    if ((bpf_ntohl(dst) & 0xFF000000) != 0x7F000000) return 1;
    // Always allow standard localhost (health checks, internal loopback)
    if (dst == bpf_htonl(0x7F000001)) return 1;
    __u64 cgid = bpf_get_current_cgroup_id();
    struct cgroup_config *cfg = bpf_map_lookup_elem(&cgroup_configs, &cgid);
    if (!cfg) return 1; // no config = system process, allow
    // Allow if destination is within our own /26 subnet
    if ((dst & cfg->subnet_mask) == (cfg->subnet_base & cfg->subnet_mask)) return 1;
    return 0; // block cross-repo loopback access
}

char _license[] SEC("license") = "GPL";
```

### Go manager (manager.go)

Key functions:
- `NewManager()` — load BPF objects from embedded bytecode; probe kernel support; fail hard if unsupported
- `AttachContainer(cgroupPath, networkID, serviceIP)` — write config to BPF map, attach bind+connect programs to cgroup
- `DetachContainer(cgroupPath)` — delete map entry, detach programs
- `ReplaceProgram(newObjs)` — atomic `BPF_F_REPLACE` on all attached cgroups; no container restart, zero dropped connections
- `Close()` — detach all, unload programs and maps

Cgroup path for container: derived from `docker inspect` PID → `/proc/<pid>/cgroup` → maps to `/sys/fs/cgroup/<slice>/docker-<containerID>.scope` (cgroupv2 systemd). All supported distros use cgroupv2 + systemd by default.

### Coverage: Docker containers AND Rediaccfile processes

**Problem:** A Rediaccfile can run processes directly without Docker containers (e.g. `python3 -m http.server 8080`). These processes run in renet's own cgroup, not a Docker container cgroup — so per-container BPF attachment would miss them. They'd bind to `0.0.0.0` for real with no safety net (since the wildcard firewall is being removed).

**Solution: per-repo cgroup with `BPF_F_ALLOW_MULTI` inheritance.**

cgroupv2 BPF supports `BPF_F_ALLOW_MULTI`: a program attached to a parent cgroup is automatically inherited by all child cgroups. renet creates one per-repo cgroup at repo startup and attaches the BPF program there. All repo processes — Docker containers AND Rediaccfile processes — run inside this cgroup and inherit the BPF rules:

```
/sys/fs/cgroup/rediacc/repo-<networkID>/     ← BPF attached here (BPF_F_ALLOW_MULTI)
├── docker-daemon.scope                       ← inherits BPF
│   └── docker-<containerID>.scope            ← inherits BPF (containers)
└── rediaccfile-exec.scope                    ← inherits BPF (direct processes)
```

**Implementation change:** Instead of `AttachContainer(containerCgroupPath, ...)`, the primary attachment is `AttachRepoCgroup(repoCgroupPath, networkID)` using `BPF_F_ALLOW_MULTI`. Per-container map entries are still written (each container has its own `service_ip`), but the BPF program is attached once at the repo level.

The `BPF_F_ALLOW_MULTI` flag means: "allow this program alongside other programs already attached to parent/child cgroups" — Docker's own cgroup programs (if any) continue to work alongside ours.

**How to move Rediaccfile processes into the repo cgroup:**
```go
// Before executing the Rediaccfile up() function:
cgroupPath := "/sys/fs/cgroup/rediacc/repo-" + strconv.Itoa(networkID)
os.MkdirAll(cgroupPath, 0755)
// Move current process (which will exec the Rediaccfile) into the cgroup
os.WriteFile(cgroupPath+"/cgroup.procs", []byte(strconv.Itoa(os.Getpid())), 0644)
```

For Rediaccfile processes that don't have their own `service_ip` (they're not a named service), the BPF program sees `cfg == nil` (no map entry for their cgroup ID) and allows all traffic — so non-service Rediaccfile helper commands work normally. Only named services with an entry in the BPF map get the bind rewrite and connect filtering.

### Integration points in renet

**`pkg/daemon/setup.go` → `SetupDaemon`:**
```
Step 1c (new): LoadEBPFManager()
  - Probes kernel version (≥6.1) and cgroupv2 — exits with error if unmet
  - Loads BPF objects from embedded bytecode
  - Creates per-repo cgroup: /sys/fs/cgroup/rediacc/repo-<networkID>/
  - Attaches BPF program to repo cgroup with BPF_F_ALLOW_MULTI
  - Stores manager in daemon state
```

**`pkg/orchestration/workflows.go` → before Rediaccfile execution:**
```
Move Rediaccfile executor process into repo cgroup:
  → echo $PID > /sys/fs/cgroup/rediacc/repo-<networkID>/cgroup.procs
  → Rediaccfile processes and their children now inherit BPF rules
```

**`pkg/compose/exec.go` — after `docker compose up`:**
```
For each running container with rediacc.service_ip label:
  → get PID via docker inspect
  → write {cgroupID: {service_ip, subnet}} entry to BPF map
  (no separate attach needed — container inherits from repo cgroup)
```

**`pkg/daemon/setup.go` → `TeardownDaemon`:**
```
→ ebpfManager.DetachRepoCgroup()  (removes BPF from repo cgroup)
→ ebpfManager.Close()
→ os.RemoveAll("/sys/fs/cgroup/rediacc/repo-<networkID>/")
```

**`SafeStartup` (workflows.go) — on restore:**
```
Before docker start --checkpoint:
  → ebpfManager.AttachContainer(newCgroupPath, networkID, newServiceIP)
  Map updated with new SERVICE_IP before process wakes — no polling needed
```

**renet binary update (atomic):**
```
New binary embeds new BPF bytecode
→ SetupDaemon runs → NewManager() loads new bytecode
→ ReplaceProgram() atomically swaps all attached cgroup programs
→ Zero container restarts, zero downtime
```

---

## build.sh Integration

Add `ebpf_generate()` function to `build.sh` called by both `build()` and `dev()`:

```bash
# Generate BPF Go bindings from C source.
# Requires: clang with BPF target (clang-14+), bpf2go (installed via go tool)
# Output:   pkg/ebpf/socket_isolation_bpf*.go + *.o (embedded in binary)
# Only needed when socket_isolation.c changes — output is committed to repo.
ebpf_generate() {
    local ebpf_dir="$SCRIPT_DIR/pkg/ebpf"

    # Skip if C source unchanged (compare mod times)
    if [[ -f "$ebpf_dir/socket_isolation_bpfel.o" ]] && \
       [[ "$ebpf_dir/socket_isolation_bpfel.o" -nt "$ebpf_dir/socket_isolation.c" ]]; then
        echo "✓ BPF objects up-to-date (use --force-ebpf to regenerate)"
        return 0
    fi

    echo "Generating BPF objects from socket_isolation.c..."
    command -v clang >/dev/null 2>&1 || { echo "ERROR: clang not found — required for BPF compilation"; exit 1; }

    (cd "$SCRIPT_DIR" && go generate ./pkg/ebpf/...)
    echo "✓ BPF objects generated"
}
```

The `pkg/ebpf/socket_isolation.c` file carries a `//go:generate` directive:
```go
//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -cc clang -cflags "-O2 -g -Wall -Werror" SocketIsolation socket_isolation.c
```

**Generated objects are committed to the repo** — developers without clang can still build. Only regeneration requires clang.

---

## CI/CD Integration

### ci-build-renet.yml — add clang install + go generate step

Add before the existing `build-renet` step:
```yaml
- name: Install clang for BPF compilation
  run: |
    # clang is available on ubuntu-latest; explicit install for reproducibility
    sudo apt-get install -y clang llvm libbpf-dev linux-headers-generic
    clang --version

- name: Generate BPF bindings
  run: |
    cd private/renet
    go generate ./pkg/ebpf/...
    echo "Generated files:"
    ls -la pkg/ebpf/socket_isolation_bpf*.go pkg/ebpf/socket_isolation_bpf*.o
```

### ci.yml — add eBPF kernel version check job

New job in the quality column (runs on ubuntu-latest, no special hardware needed):
```yaml
ebpf-verify:
  name: eBPF BPF Objects
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@...
    - uses: actions/setup-go@...
      with: { go-version: stable }
    - name: Install clang
      run: sudo apt-get install -y clang llvm libbpf-dev
    - name: Verify BPF objects are up-to-date
      run: |
        cd private/renet
        go generate ./pkg/ebpf/...
        git diff --exit-code pkg/ebpf/  # fail if generated files differ from committed
    - name: Verify BPF verifier accepts program
      run: |
        cd private/renet
        go test ./pkg/ebpf/ -run TestBPFVerifier -v
        # TestBPFVerifier loads the BPF objects without attaching — verifier pass = no kernel bugs
```

### ct-tests.yml — add eBPF isolation test to existing OS matrix

The existing bridge test matrix already covers `ubuntu-24.04`, `debian-12`, `fedora-43`, `opensuse-15.6`. Add an eBPF-specific test step after existing bridge tests:

```yaml
# In test-bridge-workers job, after existing steps:
- name: Test eBPF Isolation
  run: |
    # Verify kernel version meets minimum
    KVER=$(uname -r | cut -d- -f1)
    echo "Kernel: $KVER on ${{ matrix.os-image }}"
    go test ./private/renet/pkg/ebpf/ -run TestIsolation -v -timeout 60s
    # TestIsolation: start two containers, verify cross-repo connect is blocked
```

Per-OS notes for the matrix:

| OS | Kernel | cgroupv2 default | clang install |
|----|--------|-----------------|---------------|
| ubuntu-24.04 | 6.8 | ✓ | `apt install clang` |
| debian-12 | 6.1 | ✓ | `apt install clang` |
| fedora-43 | 6.x | ✓ | `dnf install clang` |
| opensuse-15.6 | 5.14 | ✓ | `zypper install clang` |

All meet the 5.10 minimum. cgroupv2 is the default on all four. No special configuration needed.

### cd-v2.yml — ensure BPF objects compiled before binary release

The release binary must include the embedded BPF bytecode. Add to the build step:
```yaml
- name: Generate BPF objects (before renet build)
  run: |
    sudo apt-get install -y clang llvm libbpf-dev
    cd private/renet && go generate ./pkg/ebpf/...
```
This runs before the existing `build-renet.sh` call in the release workflow.

---

## What Gets Eliminated Once eBPF Ships

### Application code
- **`setInterval` IP rebind loop** in `packages/cli/templates/app-postgres-criu/app/server.mjs` — the entire polling pattern is removed. After CRIU restore on a different machine with a new SERVICE_IP, renet updates the BPF map before the process wakes. The application never knows.
- **`process.env.SERVICE_IP`** in application `listen()` calls — optional. `server.listen(3000)` or `server.listen('0.0.0.0', 3000)` both work; eBPF rewrites transparently.

### Compose templates (all `${SERVICE_IP}` in `command:` and environment binding fields)
- `redis-server --bind ${SERVICE_IP}` → just `redis-server`
- `postgres -c listen_addresses=${DB_IP}` → `postgres` (default `localhost`, eBPF handles it)
- `memcached -l ${SERVICE_IP}` → `memcached`
- `PGADMIN_LISTEN_ADDRESS: "${SERVICE_IP}"` → remove
- `sed -i "s/Listen 80/Listen ${SERVICE_IP}:80/" ...` (WordPress) → remove
- Health checks: `curl http://localhost:PORT` works since `127.0.0.1` is explicitly allowed through the connect hook and the service now listens there (via bind rewrite)

### renet infrastructure
- **Wildcard firewall** (`pkg/daemon/wildcard_firewall.go`) — exists solely because services bind to `0.0.0.0`. With eBPF bind rewriting, `0.0.0.0` never reaches the kernel. Remove `REDIACC_WILDCARD_*` chains entirely.
- **Service binding warnings** (`pkg/compose/healthcheck.go` hint map) — the "use PGADMIN_LISTEN_ADDRESS=${SERVICE_IP}" warning message category. Remove.
- **`getHostListeningPorts`** in wildcard_firewall.go — remove along with wildcard firewall.

### Docs
See dedicated section below.

---

## Prune Command Enhancements

`renet prune` currently cleans: orphaned networks, loopback IPs, orphaned systemd units. eBPF introduces three new categories of orphaned resources.

### New orphan types

**1. Orphaned BPF programs** — if renet crashes while a BPF program is attached to a repo cgroup, it remains attached indefinitely. BPF programs are kernel-reference-counted; they persist as long as the cgroup attachment holds a reference. A repo that is fully deleted but had a crash mid-teardown can leave a live BPF program filtering traffic on a cgroup that should no longer exist.

Detection: walk `/sys/fs/cgroup/rediacc/` and use `bpf(BPF_PROG_QUERY, ...)` on each cgroup to list attached programs. Cross-reference with active repo networkIDs — any BPF program attached to a cgroup with no matching active repo is orphaned.

**2. Orphaned BPF map entries** — deleted containers and repos leave stale `{cgroupID → service_ip}` entries in the `cgroup_configs` BPF hash map. cgroup IDs are 64-bit integers assigned by the kernel and can be recycled over time, meaning a stale map entry could accidentally apply to a new cgroup that happens to reuse the same ID — causing wrong bind rewriting or incorrect filtering for an unrelated process.

Detection: enumerate all entries in the `cgroup_configs` map. For each entry, check if `/sys/fs/cgroup` has a cgroup with that ID (via `bpf_get_current_cgroup_id` equivalent, or by scanning cgroup files). Remove entries whose cgroup no longer exists.

**3. Orphaned repo cgroups** — the per-repo cgroup at `/sys/fs/cgroup/rediacc/repo-<networkID>/` persists if `TeardownDaemon` was interrupted (crash, power loss, OOM kill). An empty cgroup with no processes is harmless but accumulates over time and holds a BPF program reference.

Detection: list all `/sys/fs/cgroup/rediacc/repo-*/` directories. For each, check if `cgroup.procs` is empty AND no active repo with that networkID exists. If both true, it's orphaned.

### Implementation in `pkg/prune/`

Add to `PrunableResources`:
```go
type PrunableResources struct {
    Networks       []OrphanedNetwork
    IPs            []OrphanedIP
    OrphanedUnits  []OrphanedUnit
    BPFPrograms    []OrphanedBPFProgram  // new
    BPFMapEntries  []OrphanedBPFMapEntry // new
    RepoCgroups    []OrphanedRepoCgroup  // new
}
```

Add to `Config`:
```go
type Config struct {
    // existing fields ...
    PruneBPF     bool // prune orphaned BPF programs, map entries, and repo cgroups
}
```

Add `--bpf` flag to `pruneCmd` (defaults to true when `--networks` is not explicitly set, since BPF resources are part of network cleanup).

### `GetPrunableResources` additions

```go
if cfg.PruneBPF {
    // 1. Find orphaned BPF programs attached to /sys/fs/cgroup/rediacc/repo-*/
    bpfProgs, err := findOrphanedBPFPrograms(activeNetworkIDs)
    resources.BPFPrograms = bpfProgs

    // 2. Find stale entries in cgroup_configs BPF map
    staleEntries, err := findOrphanedBPFMapEntries(ebpfManager)
    resources.BPFMapEntries = staleEntries

    // 3. Find empty /sys/fs/cgroup/rediacc/repo-*/ with no active repo
    orphanCgroups, err := findOrphanedRepoCgroups(activeNetworkIDs)
    resources.RepoCgroups = orphanCgroups
}
```

### `ExecutePrune` additions

```go
// Detach orphaned BPF programs (order matters: detach before cgroup removal)
for _, prog := range resources.BPFPrograms {
    ebpfManager.DetachFromCgroup(prog.CgroupPath)
}

// Remove stale BPF map entries
for _, entry := range resources.BPFMapEntries {
    ebpfManager.DeleteMapEntry(entry.CgroupID)
}

// Remove orphaned repo cgroups (after BPF detach)
for _, cg := range resources.RepoCgroups {
    os.Remove(cg.Path)  // only succeeds if cgroup.procs is empty
}
```

### Output additions

```
Networks:  2 orphaned
IPs:       5 orphaned loopback aliases
BPF:       1 orphaned program (repo-16640), 3 stale map entries, 2 empty repo cgroups
```

### `rdc machine prune` (CLI)

The CLI `machine prune` command calls `repository_prune` bridge function. Add `prune_bpf: true` to the params so the machine-side prune also cleans BPF resources. Update the prune description to mention BPF cleanup.

---

## Documentation Updates

All of the following must be updated as part of the eBPF PR. Docs that instruct users to use `${SERVICE_IP}` for binding become incorrect — eBPF handles it transparently. Docs about cross-repo isolation change from "not implemented" to "enforced by kernel".

### `packages/www/src/content/docs/en/`

**`rules-of-rediacc.md`**
- Remove: "Bind to `SERVICE_IP`, each service gets a unique loopback IP" — no longer required
- Remove: "Health checks must use `${SERVICE_IP}`, not localhost" — `localhost` now works
- Replace inter-service communication note with: "Services communicate using sibling service names (auto-resolved via `extra_hosts`). eBPF transparently binds services to their assigned loopback IP — application code can use `0.0.0.0` or `localhost`"
- Update networking section: add that cross-repo connections are now kernel-blocked
- Remove "Bind to `SERVICE_IP`" from the docker-compose example labels

**`services.md`**
- Remove `${SERVICE_IP}` from the compose example `command:` fields
- Update the "Using Service IPs" section: "Services may bind to `0.0.0.0` or `localhost`. eBPF automatically redirects to the correct loopback IP. Use `${SERVICE_IP}` only if you need the exact IP (e.g. for explicit binding in health check labels)"
- Remove the `${POSTGRES_IP}` warning about fork isolation (eBPF enforces this now)
- Update health check examples: `curl http://localhost:PORT` is now valid

**`networking.md`**
- Update the "Cross-Repository Isolation" section from (currently absent/documented as not implemented) to: "Services in different repositories cannot connect to each other's loopback IPs — enforced at the kernel level by eBPF cgroup socket programs"
- Remove the `> **Note:** Currently not implemented` caveat from NETWORK_ISOLATION.md reference

**`migration.md`**
- Step 4: Remove "Bind services to `${SERVICE_IP}`" as a migration requirement — services bind automatically
- Step 5: Update to just: "Use service names for inter-service connections"
- Troubleshooting "Port conflicts": update to reflect eBPF ensures correct binding

### `packages/cli/src/i18n/locales/en/cli.json`

- `keyConcepts` (compose section): Remove "Bind to ${SERVICE_IP}" requirement; replace with "eBPF automatically binds services to their loopback IP — use `0.0.0.0` or `localhost` in application code"
- `keyConcepts` (compose section): Remove health check `${SERVICE_IP}` requirement; `localhost` works
- Template descriptions for `app-postgres` and `app-postgres-criu`: remove SERVICE_IP binding instructions
- `rules-of-rediacc` keyConcepts routing section: add "Cross-repo isolation is kernel-enforced via eBPF"

### `private/renet/cmd/renet/dev_agent_template.go`

- Rule 5: "Bind to `${SERVICE_IP}`" → change to: "Services bind automatically via eBPF. Use `0.0.0.0` or `localhost` — the kernel rewrites it to the correct loopback IP"
- Rule 6: "Health checks should use `${SERVICE_IP}`" → "Health checks can use `localhost` or `${SERVICE_IP}`"
- Rule 7 (the one we added about service names): keep, it still applies for connection strings

### `packages/cli/templates/app-postgres-criu/`

**`app/server.mjs`**
- Remove the entire `setInterval` polling block (lines ~113–125)
- Remove `process.env.SERVICE_IP` as the listen host — just use `0.0.0.0` or remove host parameter entirely
- Keep the `uncaughtException` ECONNRESET handler (still valid for CRIU TCP stale sockets)
- Update the comment block explaining CRIU awareness — remove the IP rebind explanation

**`docker-compose.yml`**
- Remove `PGADMIN_LISTEN_ADDRESS: "${SERVICE_IP}"` equivalent (if present)
- Health checks: change to use `localhost` instead of `${SERVICE_IP}`

**`README.md` (if exists)**
- Remove any instruction about handling SERVICE_IP changes after restore

### `private/renet/docs/NETWORK_ISOLATION.md`

- Add section "Resolution" explaining that eBPF via `BPF_PROG_TYPE_CGROUP_SOCK_ADDR` resolved the isolation problem
- Mark the failed approaches section as historical context
- Note that moby/moby#47828 is no longer required (eBPF solves it without ns: network mode)

### `renet` validation and enforcement changes

Several `renet compose` / `renet up` checks currently force users to bind services to `${SERVICE_IP}`. These become unnecessary and must be removed:

**`pkg/compose/healthcheck.go`**
- Remove `serviceHints` map (lines 36–45) — the per-service binding hints shown when wildcard binding is detected:
  ```
  ⚠ pgadmin — listening on :::80 (should bind to 127.0.x.x)
    Add PGADMIN_LISTEN_ADDRESS=${SERVICE_IP} to environment
  ```
  With eBPF, wildcard binding is silently rewritten to `SERVICE_IP` — no warning needed.
- Remove `VerifyServiceBindings()` — the post-`compose up` check that detects wildcard-bound services and triggers the wildcard firewall. eBPF ensures services never actually listen on `0.0.0.0`; the check is redundant.
- Remove `CollectWildcardPorts()` — used only to feed `SetupWildcardFirewall` which is also being removed.

**`pkg/compose/validate.go`**
- Remove the `collectServiceWarnings` check at line ~92:
  ```
  "service %q: healthcheck uses localhost — use ${SERVICE_IP} instead"
  ```
  `localhost` resolves to `127.0.0.1` which eBPF's `connect()` hook explicitly allows through (it's whitelisted to prevent blocking health checks). This warning is no longer valid.
- **Keep** the `${..._IP}` in `configs.content` validation error — embedding raw IPs in configs stored by applications (like pgadmin4.db) is still wrong and eBPF doesn't help once the IP is persisted.
- **Keep** the `network_mode` override warning — still relevant.

**`pkg/daemon/wildcard_firewall.go`** (entire file)
- Remove `SetupWildcardFirewall`, `RemoveWildcardFirewall`, `getHostListeningPorts` — the wildcard firewall was the safety net for services that accidentally bind to all interfaces. With eBPF, `0.0.0.0` never reaches the kernel.
- Remove calls in `pkg/daemon/setup.go` (`SetupWildcardFirewall` in `SetupDaemon`, `RemoveWildcardFirewall` in `TeardownDaemon`).

**Net result for users:** `renet up` no longer outputs binding warnings, no longer adds iptables DROP rules for wildcard ports, and health checks using `localhost` pass without complaint. The only remaining binding-related error is `${..._IP}` in configs.content (which is about persistent storage, not runtime binding).

---

## Test Plan

1. **BPF verifier** (`TestBPFVerifier`) — `NewManager()` succeeds: verifier accepts the program without kernel errors
2. **Kernel version check** (`TestKernelVersionCheck`) — returns error on 5.9, succeeds on 5.10+
3. **cgroupv2 probe** (`TestCgroupV2Probe`) — detects cgroupv2 mount correctly
4. **Bind rewrite** (`TestBindRewrite`) — `listen(0.0.0.0:8080)` binds to `SERVICE_IP:8080` only
5. **Localhost rewrite** (`TestLocalhostRewrite`) — `server.listen(3000)` (Node default: 127.0.0.1) binds to `SERVICE_IP:3000`
6. **Cross-repo block** (`TestCrossRepoBlock`) — container in fork cannot `connect(parent's DB IP)` → returns EPERM
7. **Within-repo allow** (`TestWithinRepoAllow`) — sibling containers within the same repo connect successfully
8. **CRIU round-trip** (`TestCRIURestore`) — checkpoint + restore; verify service accessible at new SERVICE_IP without polling
9. **Atomic update** (`TestAtomicProgramReplace`) — `ReplaceProgram()` with active connections; zero dropped connections
10. **OS matrix** — tests 3-9 run in CI against ubuntu-24.04, debian-13, fedora-43, opensuse-16.0

---

## Notes

- `bpf_get_current_cgroup_id()` (kernel 4.18) identifies which container/repo a socket call belongs to without UIDs, GIDs, or application changes.
- The `connect()` hook fires on NEW connections only, not on CRIU-restored established sockets. Existing connections restored by CRIU are unaffected.
- For long-running processes (postgres master) that bind once at startup: bind rewrite fires at startup. CRIU preserves the bound socket across restore — the new SERVICE_IP is in the BPF map for subsequent restarts.
- IPv6 loopback (`::1`, `::`) requires separate `BPF_CGROUP_INET6_BIND` / `BPF_CGROUP_INET6_CONNECT` hooks — identical logic, same file, add in the same PR.
- `BPF_F_REPLACE` for atomic program updates: kernel 5.5 (already met by our 5.10 minimum).
- Generated BPF objects (`.o` files and `_bpf.go`) are committed to the repo so developers without clang can build. Only regeneration requires clang.
