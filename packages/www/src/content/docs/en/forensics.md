---
title: "Forensics: Evidence From Inside a Compromised Repository"
description: "Per-repository network flow and sensitive file-open records at a level the customer chooses, shipped every 30 seconds as signed, chained batches. Covers the three capture levels, the spike trigger, plan quotas, offline and server detection, and what the server can read."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 9
language: en
---

# Forensics

Forensics answers two questions after software running inside a repository is compromised: when was data taken, and which data was taken. Rediacc cannot close a hole in third-party software, so the feature records evidence that survives the compromise. The records are written by a root-owned collector on the machine, outside the repository sandbox, and shipped to a bucket that the customer's administrators cannot reach.

The records show volume, destination and timing. Flow records prove volume and destination, not content. The [incident workflow](/en/docs/incident-response) reads them, and [incident reports](/en/docs/incident-reports) turn them into signed documents for a regulator.

## What is recorded

Capture is per repository. Repositories use host networking, so traffic is attributed by cgroup (the repository's own slice), never by IP address.

| Record | Content |
|---|---|
| Network flow | Time, process, destination address and port, protocol, bytes out and in, DNS name when known, and the destination's ASN and country when known |
| File open | Time, process and path, for a path that matches the sensitive list |
| Heartbeat | A signed marker in every batch, so a stopped collector shows as a gap rather than as silence |

The default sensitive list covers `.env` files, key and certificate files (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), password databases (`*.kdbx`), database dumps and files (`*.sql`, `*.dump`, `*.bak`, `*.sqlite*`) and database data directories such as `pgdata`. A repository can extend the list or replace it with its own patterns.

Packet payloads and file contents are never recorded.

## Capture levels

Each repository has one level, and the smallest is the default. A higher level records everything a lower one does.

| Level | Recorded |
|---|---|
| `basic` | A summary every 5 minutes per destination, port and protocol, with bytes in and out |
| `standard` | A flow record every minute, with process and DNS name |
| `full` | Standard, plus file opens on sensitive paths |

The level is set per repository:

```bash
rdc forensics level mail basic
rdc forensics level mail standard
rdc forensics level mail full
```

The collector caps the level at what the plan includes. When a plan has no forensics quota, the repository records nothing.

### The spike trigger

Every level arms a trigger. When a repository's outbound bytes in one minute rise above ten times its own moving average (and above 50 MiB per minute), once the repository has been observed for 24 hours, the repository switches to Full for 24 hours. A firing minute does not feed the average, so one exfiltration cannot raise the baseline that should catch the next one.

## Plans and quotas

Forensics is for paid plans, and it records only while the plan is paid. An upgrade starts with no history.

| Plan | Forensics quota |
|---|---|
| Free, Community | 0 (nothing recorded) |
| Professional | 25 GB |
| Business | 125 GB |
| Enterprise | 512 GB, or a custom quota set by Rediacc administrators |

The quota is a quarter of the plan's backup quota and is separate from backup accounting. More quota comes from a plan upgrade only.

When the quota is full, the oldest records are evicted first (FIFO). The newest 7 days are locked and never evicted, because the bucket locks them for 7 days. When locked bytes alone would exceed the quota, new batches are refused. When the projected 7-day ingest would not fit, the level is capped at Basic. Owners and admins receive a notice at 80 percent of the quota, when the cap drops to Basic and when a batch is refused.

Records that fall inside a declared incident are held out of eviction until 30 days after the incident closes. See [incident response](/en/docs/incident-response).

## Shipping and integrity

The collector cuts a batch every 30 seconds. Each batch is signed with the machine's spool key and carries the hash of the previous batch, so a removed or edited batch breaks the chain. Batches are uploaded through create-only presigned URLs minted from the machine's license blob, so the machine can add records but cannot overwrite or delete them. When connectivity is lost, batches wait in a local signed spool and ship when the connection returns.

Nightly compaction merges the batches into one day file per repository and one headers file per machine, in which every signed header is listed and any gap is marked. The audit day files of the account chain the same way, per organization and day.

`rdc forensics verify` and the Verify evidence button of the investigation page recompute these chains. See [incident response](/en/docs/incident-response).

## Detection

Anomaly detection runs twice. A statistical detector on the machine reacts at once, switching the repository to Full. The server runs its own detectors on ingest, so detection survives a compromised host. No AI runs per log record.

The detectors are layered and each repository learns from its own traffic:

| Detector | Looks for |
|---|---|
| Hour-of-week baselines | Bytes, connections, distinct destinations, new DNS names and new processes outside the repository's usual rhythm for that hour of the week |
| Half-Space Trees | A flow unlike the flows seen before |
| ECOD and HBOS | Batches of flows that score as outliers, with the features that drove the score |
| First seen | A process opening a sensitive file it has not opened before |

Each finding carries the per-feature reasons that produced it, and the explanation is a template built from those reasons. Offline there is no language model. A finding becomes an account notice and an email to owners, admins and the security contact. When the machine is offline, it acts locally at once (Full capture and a record in its signed spool) and delivers the alert when connectivity returns, keeping the original detection time.

### Model bundles

The detector parameters are distributed as signed bundles under `data.rediacc.com/models/`, uploaded by the publish job (no channel is published there yet): content-addressed files, a manifest signed with an offline Ed25519 model key that is built into renet, a minimum renet version and a version that only increases, so a downgrade is refused. A bundle is verified before it installs, and the previous one can be restored.

```bash
renet models status
renet models update
renet models rollback
```

Air-gapped installs receive the same signed bundle inside `rdc server bundle`, unless `--no-models` is passed.

## What the server can read

The account server reads the records, because the timeline, the verification and the server detectors need them: destinations, ports, process names, DNS names, byte counts and sensitive file paths. It does not receive packet payloads or file contents.

An inbound client address is stored truncated (to /24 for IPv4 and /48 for IPv6) in the records, and the whole address sits in a separate section that is deleted after 30 days. The hash of the deleted section stays in the signed header, so the chain still verifies and the verifier reports the address as redacted. Outbound destinations stay whole, because they are the evidence.

Customers open the records through an investigation, which needs a paid plan, an owner or admin role and a recent re-authentication, and every view is audited. Rediacc support sees forensics data only under a time-limited grant that the customer issues. The processing terms are in the [data processing agreement](/en/data-processing-agreement).
