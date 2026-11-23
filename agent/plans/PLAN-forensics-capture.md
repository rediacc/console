# PLAN: Forensics capture -- renet eBPF flow, DNS and sensitive file-open capture per repo, three levels with a spike trigger, and a root-owned collector writing a signed, hash-chained local spool
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #772cfd55 (agent/programs/breach-forensics/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: no-dep -- the first plan of agent/programs/breach-forensics/README.md; every box builds on renet and console code at the 1121-1 tip, and the gate-registration box waits on PLAN-tooling-code-reduction.md#CR2 as a box edge only
Priority: P1 -- no record of what software inside a repo sends or reads exists today (agent/programs/breach-forensics/01-verified-context.md section 1), and plans 2 to 6 of the program read this plan's spool
Concurrency: parallel -- wave 1 FC1, FC4, FC5, FC8 (file-disjoint); wave 2 FC2, FC3, FC6; wave 3 FC7; then FC9, FC10, FC11; private/renet/go.mod and go.sum belong to FC4 alone
Owns: agent/plans/PLAN-forensics-capture.md, private/renet (gitlink bump only), private/renet/pkg/ebpf/gen.go, private/renet/pkg/ebpf/netaudit*, private/renet/pkg/ebpf/fileopen*, private/renet/pkg/netaudit/**, private/renet/cmd/renet/netaudit*.go, private/renet/pkg/list/system.go, private/renet/pkg/list/types.go, private/renet/pkg/list/system_test.go, packages/shared/src/renet-contract/data/list-types.generated.ts, private/renet/pkg/i18n/locales/*.go, private/renet/pkg/i18n/locales/hashes.json, private/renet/go.mod, private/renet/go.sum, .ci/config/renet-test-map.json, .ci/config/shards/test-renet-go.json
Live-Proof: hostinger, bench -- hostinger proves renet eBPF capture, the netaudit collector and its signed spool on a real paid repo (renet-live); bench proves the regenerated list-types contract in packages/shared still serves the account and CLI (account-smoke)

## Ask

The operator asked how to answer "when was data stolen" and "what data was stolen" per machine and per repo after software inside a customer repo is compromised (F1). This plan builds the capture half: the levels a customer picks (F2), the outbound-spike switch to Full (F3), and the renet eBPF capture with a root-owned collector outside the repo sandbox, attributed by cgroup (F4). Shipping is agent/plans/PLAN-forensics-shipping.md; detectors are agent/plans/PLAN-forensics-detection.md. CPU feature flags land here because the detectors dispatch on them (F13).

## Context

1. renet attaches four cgroup socket programs once at `rediacc.slice` through pinned bpf_links (private/renet/pkg/ebpf/manager.go:48, private/renet/pkg/ebpf/manager.go:152), pinned under `/sys/fs/bpf/rediacc` (private/renet/pkg/ebpf/manager.go:30).
2. The `connect4` program returns allow at once for every non-loopback destination (private/renet/pkg/ebpf/socket_isolation.c:137), and the cgroup config map is an LRU hash of 65,536 entries keyed by cgroup id (private/renet/pkg/ebpf/socket_isolation.c:35).
3. bpf2go generates the objects with clang-18 for amd64 and arm64 (private/renet/pkg/ebpf/gen.go:3), against cilium/ebpf v0.22.0 and Go 1.27.4 (private/renet/go.mod:6, private/renet/go.mod:3).
4. The kernel floor is 6.1 with cgroup v2 and bpffs (private/renet/pkg/ebpf/kernel.go:14, private/renet/pkg/ebpf/kernel.go:53).
5. A repo's processes sit under `/rediacc.slice/rediacc-<N>` with one level per service (private/renet/pkg/ebpf/manager.go:340); Rediaccfile processes sit under `renet-exec-<N>` (private/renet/pkg/ebpf/manager.go:272), parsed back by private/renet/pkg/ebpf/manager.go:520. The network's unit records `--repo-mount-path` (private/renet/pkg/daemon/systemd.go:228), read by private/renet/pkg/daemon/systemd_parse.go:18.
6. The machine-level precedent service is rediacc-host-metrics, root-run outside the repo slice with a root-only key at `/etc/rediacc/host-metrics.key` (private/renet/pkg/proxy/install.go:80, private/renet/pkg/hostmetrics/hostmetrics.go:57); extra unit sets register through private/renet/cmd/renet/host_metrics_units.go:13.
7. A repo licence carries `planCode` and `status` (private/renet/pkg/license/types.go:18); plan codes are FREE, COMMUNITY, PROFESSIONAL, BUSINESS, ENTERPRISE (private/renet/pkg/subscription/types.go:12). Licences live per datastore and repo GUID (private/renet/pkg/license/store.go:114).
8. `renet list` reads the CPU model only (private/renet/pkg/list/system.go:175); its types (private/renet/pkg/list/types.go:166) project into packages/shared/src/renet-contract/data/list-types.generated.ts, which `check:ci-renet-types` compares.
9. renet builds `CGO_ENABLED=0` (private/renet/build.sh:552). The KVM job runs `TestEBPF_` tests in pkg/ebpf under sudo with the `ebpf_e2e` tag (.github/workflows/ci-ops-test.yml:319).

## Design

D1. **A second BPF object, not an edit of the isolation object.** `netaudit.c` (bpf2go ident `Netaudit`) and `fileopen.c` (ident `FileOpen`) are separate objects with their own pins under `/sys/fs/bpf/rediacc/netaudit/`, so a capture load failure never touches isolation. Links are multi-attach at `rediacc.slice`; every capture program returns allow, so the isolation verdict alone decides.

D2. **Programs.** `cgroup_skb/ingress` and `egress` count bytes and packets per flow; `sockops` marks TCP start (active and passive established) and end (`BPF_SOCK_OPS_STATE_CB` to TCP_CLOSE) and emits the closed flow to a ringbuf; `cgroup/connect4|6` and `cgroup/sendmsg4|6` record UDP destinations; `cgroup/sock_release` ends UDP flows; `cgroup/post_bind4|6` stamps the listener. Loopback is skipped except DNS answers from source port 53.

D3. **Maps.** Flow map: LRU hash of 131,072 entries keyed by (cgroup id, family, proto, saddr, daddr, sport, dport), value bytes and packets per direction, first and last ns, pid, comm. Process attribution: `sk_storage` with `BPF_F_CLONE` written in process context (connect, sendmsg, post_bind), so accepted sockets inherit the listener's pid and comm. Enable map: repo cgroup id (ancestor level 2, `bpf_skb_ancestor_cgroup_id`) to level; a repo absent from it costs one lookup. Ringbufs: closed flows 8 MiB, DNS payloads 2 MiB, file opens 4 MiB; per-CPU drop and eviction counters become `gap` records.

D4. **Long-lived flows** are read every 60 s (Standard, Full) or 300 s (Basic) with BatchLookup; the collector emits per-interval deltas.

D5. **DNS.** The ingress program copies up to 512 bytes of UDP payloads from port 53 into the DNS ringbuf; the collector parses them with golang.org/x/net/dns/dnsmessage (made a direct dependency) and keeps a per-repo IP-to-name cache with the answer TTL. Repos resolve through the 127.0.0.53 stub, so this covers the stub and direct resolvers. DNS over HTTPS stays unnamed (Risks).

D6. **File opens (Full) use fentry on `security_file_open`.** eBPF LSM needs `lsm=bpf` on the boot line, which the default Debian and Ubuntu kernels lack; fanotify needs a mark per mount, reports a pid that may be gone before its cgroup is read, and wakes the collector for every open. fentry needs BTF and trampolines, present on every 6.1+ distro kernel on amd64 and arm64 (Context 4), filters by the enable map in kernel, and reads the path with `bpf_d_path`, which the verifier allows for this hook. A kernel-side LRU of (cgroup, inode, pid) drops repeats within 60 s and a per-repo token bucket caps 200 events/s. The collector matches the path against the repo's sensitive list. A failed attach degrades Full to Standard and records `file_opens_unavailable`.

D7. **Sensitive paths**, relative to the repo mount, default to `**/.env`, `**/.env.*`, `**/*.pem`, `**/*.key`, `**/id_rsa*`, `**/id_ed25519*`, `**/*.kdbx`, `**/*.sql`, `**/*.dump`, `**/*.bak`, `**/*.sqlite*`, `**/pgdata/**`, `**/mysql/**`, `**/secrets/**`; a repo's list replaces or extends them.

D8. **Levels and their source.** `/etc/rediacc/forensics/<guid>.json` (root 0600: `level`, `sensitive_paths`, `trigger_until`, `trigger_reason`, `set_by`, `set_at`) is the local setting, written by `renet forensics level <guid> basic|standard|full`. Entitlement is a Go interface `Entitlement.Max(guid) (Level, bool)`; this plan's implementation reads the repo licence: an ACTIVE licence on PROFESSIONAL, BUSINESS or ENTERPRISE is entitled, anything else records nothing (F6). PLAN-forensics-shipping.md replaces the implementation with its licence claim and account setting without touching callers. Effective level: Full while a trigger is active, else the file's level, else Basic (F2), capped by entitlement.

D9. **Levels select output, not kernel work per packet.** Basic writes 5-minute summaries per (repo, destination, port, proto) with bytes each way; Standard writes 1-minute flow records with pid, comm and DNS name; Full adds file opens.

D10. **Spike trigger (F3), simple form.** Per repo, an EWMA of outbound bytes per minute (alpha 0.05) after a 24 h warm-up; a minute above max(10x EWMA, 50 MiB) sets `trigger_until` to now plus 24 h and writes a `trigger` record. The check sits behind `trigger.Detector` (`Observe(RepoMinute) (fire bool, reason Reason)`), the seam PLAN-forensics-detection.md fills.

D11. **The collector.** `renet netaudit serve` runs as `rediacc-netaudit.service`: root, `Slice=system.slice` (outside `rediacc.slice`), `ProtectSystem=strict`, writable paths `/var/lib/rediacc/netaudit` and `/etc/rediacc/forensics` only, capabilities CAP_BPF, CAP_PERFMON, CAP_NET_ADMIN, CAP_SYS_RESOURCE. It loads and pins D1, maps cgroup to network id to mount to GUID (Context 5), and writes the spool. `renet netaudit status` reports per repo level, entitlement, drops and file-open availability.

D12. **Spool: Ed25519, not HMAC.** An HMAC key would have to be shared with the server, which could then forge records; a per-machine Ed25519 key (`/etc/rediacc/netaudit/spool.ed25519`, root 0600, created at install; public half beside it 0644) lets the server verify without the power to sign.
A batch is cut every 30 s, empty batches included so silence is visible (F5): a signed header plus sections, so a per-repo day file verifies on its own and a 30-day redaction of inbound client addresses never breaks a signature: header `{schema, machine_id, seq, prev_hash, cut_at, level, sections: [{repo_guid, kind: records|pii, sha256, bytes}]}`, each section zstd-compressed on its own (inbound client addresses truncated in `records`, kept whole in `pii`), the header Ed25519-signed; batch hash = SHA-256 of header bytes plus signature; files `spool/<seq>.batch` written through rename. `prev_hash` chains each batch to the last, `genesis` for the first.
Known-answer vectors live in packages/shared/src/forensics/__fixtures__/batch-vectors.json, which PLAN-forensics-shipping.md FS2 owns and this plan's tests read by relative path. The API PLAN-forensics-shipping.md ships through is `spool.Reader` (`Pending`, `Open`, `MarkShipped`). The spool caps at 1 GiB: shipped batches go first; then the oldest unshipped batch goes and a `gap` record names it. A root attacker can sign future batches; shipping every 30 s bounds what can be rewritten to the unshipped tail.

D13. **CPU feature flags.** `SystemInfo.CPUFeatures` (`cpu_features`) lists avx2, avx512f, avx512bw, avx512vl, avx512dq, avx512vbmi and neon from golang.org/x/sys/cpu, which reports what the OS enabled, not only what the chip lists.

D14. **Budget.** Basic and Standard cost at most 3% throughput on an iperf3 run off the host and on loopback; the collector averages at most 2% of one core and 96 MiB RSS at 1,000 new flows/s; Full adds at most 5% to an open-close loop.

## Ordering against other live plans

- PLAN-forensics-shipping.md consumes `spool.Reader`, the spool public key and the `Entitlement` interface; PLAN-forensics-detection.md fills `trigger.Detector` and adds `finding` records; PLAN-forensics-investigation.md registers the renet function and the `rdc forensics level` command over FC7's verb.
- FC10 edits .ci/config and waits on PLAN-tooling-code-reduction.md#CR2.

## Tasks

- [ ] FC1 [writer] Write `pkg/ebpf/netaudit.c` with the D2 programs and D3 maps (no file-open hook), add the `Netaudit` and `FileOpen` bpf2go lines to `gen.go`, and commit the generated amd64 and arm64 objects and Go bindings for `Netaudit`.
  Owns: private/renet/pkg/ebpf/gen.go, private/renet/pkg/ebpf/netaudit.c, private/renet/pkg/ebpf/netaudit_x86_bpfel.*, private/renet/pkg/ebpf/netaudit_arm64_bpfel.*
  Depends on: none.
  Accept: `cd private/renet && go generate ./pkg/ebpf/` leaves `git status --porcelain pkg/ebpf` empty on a second run; `go vet ./pkg/ebpf/` rc 0.
- [ ] FC2 [writer] Write the Netaudit loader in `pkg/ebpf/netaudit.go`: load, multi-attach at rediacc.slice with links pinned under `/sys/fs/bpf/rediacc/netaudit/`, per-repo enable and disable, BatchLookup reads with deltas, ringbuf readers, drop counters, plus a root load test that attaches to a scratch cgroup, moves a TCP and a UDP client into it and reads both flows with byte counts and comm.
  Owns: private/renet/pkg/ebpf/netaudit.go, private/renet/pkg/ebpf/netaudit_other.go, private/renet/pkg/ebpf/netaudit_test.go, private/renet/pkg/ebpf/netaudit_root_test.go
  Depends on: FC1.
  Accept: `cd private/renet && sudo go test -tags=root -run TestNetaudit -v ./pkg/ebpf/` rc 0; `go test ./pkg/ebpf/` rc 0; the isolation tests `sudo go test -tags=root -run TestEBPF_ ./pkg/ebpf/` stay rc 0 with capture attached.
- [ ] FC3 [writer] Write `pkg/ebpf/fileopen.c` (fentry on security_file_open, enable-map filter, `bpf_d_path`, the 60 s dedupe LRU and per-repo token bucket of D6), its generated objects, and `fileopen.go` with a loader whose attach failure returns a typed unavailable error, plus a root test opening a matching and a non-matching file from a scratch cgroup.
  Owns: private/renet/pkg/ebpf/fileopen*
  Depends on: FC1.
  Accept: `cd private/renet && sudo go test -tags=root -run TestFileOpen -v ./pkg/ebpf/` rc 0 and shows one event for repeated opens of one file within 60 s.
- [ ] FC4 [writer] Write `pkg/netaudit` core: levels and the `/etc/rediacc/forensics/<guid>.json` file (D8), the `Entitlement` interface with the licence implementation, the D7 defaults and glob matcher, the cgroup to network id to GUID mapper, Basic and Standard aggregation (D4, D9), the DNS parser and cache (D5) and the record schema, with unit tests; make golang.org/x/net a direct dependency.
  Owns: private/renet/pkg/netaudit/*.go, private/renet/go.mod, private/renet/go.sum
  Depends on: none.
  Accept: `cd private/renet && go test ./pkg/netaudit/` rc 0, covering a FREE licence recording nothing, a missing file meaning Basic, and a compressed DNS answer resolving.
- [ ] FC5 [writer] Write `pkg/netaudit/spool`: key creation and loading, the 30 s batch cutter with empty batches, the signed header with per-repo `records` and `pii` sections of D12, zstd per section, sha256 chain, Ed25519 signature, rename-written files, `Reader` (`Pending`, `Open`, `MarkShipped`), the 1 GiB cap with `gap` records, and a verifier used by tests.
  Owns: private/renet/pkg/netaudit/spool/**
  Depends on: none.
  Accept: `cd private/renet && go test ./pkg/netaudit/spool/` rc 0, including a test that flips one byte in a middle batch and sees the verifier name that seq, and a test that drops one `pii` section while keeping its hash and still verifies the batch as redacted.
- [ ] FC6 [writer] Write `pkg/netaudit/trigger`: the `Detector` interface, the D10 EWMA threshold implementation and the 24 h Full switch writing `trigger_until` and a `trigger` record.
  Owns: private/renet/pkg/netaudit/trigger/**
  Depends on: FC4.
  Accept: `cd private/renet && go test ./pkg/netaudit/trigger/` rc 0: no fire during warm-up, a fire at 11x baseline, expiry after 24 h.
- [ ] FC7 [writer] Write `renet netaudit serve|status` and `renet forensics level` in cmd/renet, the `rediacc-netaudit.service` template of D11 in pkg/netaudit, and its registration through a new `netaudit_units.go` calling `proxy.RegisterUnitInstaller`.
  Owns: private/renet/cmd/renet/netaudit*.go, private/renet/pkg/netaudit/unit.go, private/renet/pkg/netaudit/unit_test.go
  Depends on: FC2, FC3, FC5, FC6.
  Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/netaudit/...` rc 0; a unit test asserts `Slice=system.slice` and the two writable paths; `./build.sh dev` rc 0.
- [ ] FC8 [writer] Add `CPUFeatures` (`cpu_features`) to `SystemInfo` from golang.org/x/sys/cpu (D13) and regenerate list-types.generated.ts.
  Owns: private/renet/pkg/list/system.go, private/renet/pkg/list/types.go, private/renet/pkg/list/system_test.go, packages/shared/src/renet-contract/data/list-types.generated.ts
  Depends on: none.
  Accept: `cd private/renet && go test ./pkg/list/` rc 0; `npm run check:ci-renet-types` rc 0.
- [ ] FC9 [writer] Add every new user-facing renet string (status output, errors, verb help) to the en catalog and the 12 other locales, naturalized; the translation writer runs on sonnet.
  Owns: private/renet/pkg/i18n/locales/*.go, private/renet/pkg/i18n/locales/hashes.json
  Depends on: FC7.
  Accept: `cd private/renet && go test ./pkg/i18n/...` rc 0; `npm run check:ci-renet` rc 0.
- [ ] FC10 [writer] Add the ops-VM test `TestEBPF_Netaudit*` (D14 budget measured with iperf3 and an open-close loop, results printed) in pkg/ebpf, and place pkg/netaudit and its sub-packages in the renet test map and the test-renet-go shard.
  Owns: private/renet/pkg/ebpf/netaudit_e2e_test.go, .ci/config/renet-test-map.json, .ci/config/shards/test-renet-go.json
  Depends on: FC7, PLAN-tooling-code-reduction.md#CR2.
  Accept: `npm run check:ci-renet-test-map` rc 0; `sudo go test -tags=ebpf_e2e -run TestEBPF_Netaudit -v ./pkg/ebpf/` rc 0 on an ops VM, its budget lines within D14.
- [ ] FC11 [lead] Land the renet commits submodule-first, bump the gitlink, and run the VM battery on the touched areas.
  Depends on: FC1, FC2, FC3, FC4, FC5, FC6, FC7, FC8, FC9, FC10.
  Accept: `npm run vm:check -- --changed` VERIFIED receipt; `npm run check:ci-renet` rc 0.
- [ ] LP-hostinger [live] On hostinger, set one paid repo to Full, generate outbound traffic and a `.env` read inside it, and show the flow, DNS name, file open and a valid chain through `renet netaudit status` and the spool verifier.
  Accept: live-proof hostinger renet-live machine=hostinger
- [ ] LP-bench [live] Deploy the branch's account Worker to the eu bench and confirm the regenerated list-types contract serves machine status; `cli-bench` is the additional check.
  Accept: live-proof bench account-smoke

## Risks

- **Per-packet cost on busy repos.** The enable-map check keeps non-entitled repos at one lookup; FC10 measures D14 and the budget refuses regressions.
- **Flow-map eviction under connection floods** loses per-flow detail; evictions are counted into `gap` records, so loss is visible, never silent.
- **DNS over HTTPS or a resolver inside the repo** leaves destinations unnamed; records still carry IP, port and bytes.
- **Kernels without fentry trampolines** lose file opens only; the status says so and Full degrades to Standard.
- **Root compromise of the host** can stop the collector or sign forged future batches; heartbeats in PLAN-forensics-shipping.md make a stop visible, and the server detector of PLAN-forensics-detection.md scores what was shipped before.
