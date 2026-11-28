# breach-forensics: verified context

Read against the tree on 2026-11-23 by read-only research agents and spot-checked by the planning session. Each citation is a hypothesis a writer re-reads before relying on it. External facts carry their source in agent/programs/breach-forensics/03-external-research.md.

## 1. What exists for forensics today: nothing below the control plane

- Every log Rediacc keeps records control-plane operations (who ran which `rdc` command); nothing records what software inside a repo sent over the network or read from disk. The executor audit vocabulary is `cli.machine.*`, `cli.repo.*` and `cli.backup.*` only, and `cli.*` counts as telemetry (private/account/src/services/event-log.service.ts:35).
- Traefik runs with `--accesslog=true` to container stdout only (private/renet/pkg/proxy/infra.go:260), and every per-repo dockerd keeps json-file logs capped at about 30 MB (private/renet/pkg/daemon/systemd.go:718), so even HTTP access history rotates away.
- `pkg/repodiff` shows what changed between a snapshot or fork and the live repo (private/renet/pkg/repodiff/engine.go:24); nothing records reads.

## 2. renet's network model and eBPF

- Repo containers use host networking: each per-repo dockerd runs with bridge none and iptables off (private/renet/pkg/daemon/systemd.go:718). Outbound traffic leaves with the machine's own IP, so a repo cannot be identified by source address.
- renet already runs eBPF in production through cilium/ebpf, attaching cgroup socket programs once at `rediacc.slice` with a cgroup to repo map (private/renet/pkg/ebpf/manager.go:178). The outbound `connect4` program returns allow at once for any non-loopback destination (private/renet/pkg/ebpf/socket_isolation.c:137), so outbound connections are neither filtered nor logged (private/renet/pkg/hostmetrics/hostmetrics.go:20).
- The kernel floor is 6.1 with cgroup v2 and bpffs (floor constants at private/renet/pkg/ebpf/kernel.go:14, check at :53); every supported distribution ships a 6.x kernel with BTF.
- renet builds `CGO_ENABLED=0` for linux amd64 and arm64 with `GOAMD64` unset (private/renet/build.sh:552); it reads the CPU model but no CPU feature flags (private/renet/pkg/list/system.go:185).

## 3. Shipping and storage building blocks

- Machines hold no API token; the signed licence blob mints a backup session bound to subscription, lineage, machine and intent (private/account/src/routes/backups.ts:267, minted by renet at private/renet/cmd/renet/backup_snapshot.go:1151).
- Each presigned URL covers one key and one verb, is create-only through If-None-Match and lasts one hour (private/account/src/services/backup-chunk-store.ts:660). Keys are per lineage, not per machine, and there is no log object type.
- Storage quotas are plan constants with a per-subscription override and a hard stop at the limit (packages/shared/src/subscription/constants.ts:60, private/account/src/services/backup-storage.service.ts:1497); no metered or overage billing exists.
- The repo licence carries plan and size claims but no feature flags (private/renet/pkg/license/types.go:38); renet already verifies Ed25519 signatures for licences (private/renet/pkg/license/validator.go:42).

## 4. Model distribution building blocks

- The `rediacc-public-data` bucket at `https://data.rediacc.com` was created by hand and serves only demo archives with an unsigned `SHA256SUMS` (agent/plans/PLAN-health-checks-local.md:603); no config defines it and `.ci/docs/r2-media-setup.md` never documents it, although the setup plan says it does.
- renet never self-updates; the CLI pushes it over SFTP. renet's pinned-download pattern (download, sha256 pin, staging, `.ok` stamp) is in private/renet/cmd/renet/vscode_server_install.go:146.
- Air-gapped installs use `rdc server bundle` (packages/cli/src/services/server/bundle/build.ts:9), whose manifest is checked by sha256 only, with no signature.

## 5. Notices, reports, legal

- Account notices have a fixed kind list and three severities (private/account/src/types/notice.ts:21); the terms sweep is the precedent for a mandatory mass notice (private/account/src/services/notification.service.ts:77). No security-incident kind, no org security-contact field, no `security.txt`, no vulnerability disclosure policy.
- PDF generation with QR codes and a public verify route exist (private/account/src/services/pdf/certificate-pdf.ts:55, private/account/src/routes/certificate-verify.ts:30); the verify route checks a database lookup, not a signature (private/account/src/routes/certificate-verify.ts:35).
- The DPA promises breach notice within 72 hours (packages/www/src/i18n/translations/en.json:2442).
- Over-claims to correct (F23): packages/www/src/content/docs/en/legal-nis2-dora.md:53 and its "forensic trail" and "detection" lines, packages/www/src/content/docs/en/legal-gdpr.md:28, packages/www/src/content/docs/en/legal-hipaa.md:36, the NIS2 blog's "forensic-grade artefacts", and private/account/web/src/data/study-content/ms6-compliance.ts:117 calling the server audit log hash-chained (it is not until agent/plans/PLAN-console-audit-r2.md lands).
