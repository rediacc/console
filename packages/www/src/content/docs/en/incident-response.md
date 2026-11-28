---
title: "Incident Response: Investigate, Declare and Preserve Evidence"
description: "Open an investigation on a repository or machine, read one timeline of audit, runs, flows and file opens, verify the hash chains, declare an incident to freeze the evidence and start the 24 hour, 72 hour and one month clocks, and drive it all from rdc."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: en
---

# Incident Response

An incident here means one that happens inside a customer's own repositories. The investigation page, the `rdc incident` verbs and the `rdc repo flows` and `rdc repo opens` readers all work from the records described in [forensics](/en/docs/forensics). Incidents in Rediacc's own systems follow [Security Incident Response](/en/docs/security-incident-response).

## Access

Investigation needs a paid plan and an owner or admin role. Opening one asks for a recent re-authentication, and an opened investigation stays valid for 60 minutes. Every view is written to the audit log.

Rediacc support sees forensics data only under a support grant that the customer issues. A grant lasts at most 7 days and can be revoked at any time.

The CLI reads need the `forensics:read` scope, and declare and close need `incident:manage`. A CLI login carries both for owners and admins after an elevated browser approval. When a command answers that a recent elevated approval is required, the account portal asks for the approval and the command runs again.

## The timeline

The Investigate page merges one scope (a repository or a machine) into one timeline of five row kinds: console audit events, runs, network flows, file opens and anomalies. Changes since the last snapshot can be compared against it. A time-window scrubber sets the window, and a window covers at most 31 days.

A stretch with no evidence appears as a gap row that names the machine and the reason, never as an empty stretch. A chart of bytes out per minute and a list of top destinations sit above the rows.

The same reads are available from the command line:

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` and `--until` take an ISO 8601 instant or a span back from now such as `90m`, `24h` or `7d`. The default window is the last 24 hours. Flow rows show time, process, destination, bytes out and in, and ASN and country when known. Open rows show time, process and path, with sensitive paths marked.

## Verify evidence

Verify evidence recomputes the hash chain of the audit day files and the signed batch chains of the forensics records for the window, in the browser, and lists every gap and edit. Batch signatures are checked under the spool keys the account server pinned for each machine. A key written inside the evidence is never trusted. The result is stamped into exported reports.

Evidence above 2 GiB is too large for the browser. The same module runs from the command line:

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

The command exits 1 when any gap or edit is found. `--machine-key <machine>=<public-key-hex>` (the key is 64 hex characters) supplies a key from outside the directory and can be repeated. A machine with no outside key fails.

## Declare an incident

Declaring freezes the evidence. The account record goes in first, and then the repository is prepared for investigation:

1. The incident is recorded with its window, who declared it and when the organization became aware.
2. An eviction hold covers the window, and the bucket lock rules extend over it, so FIFO cannot remove those days.
3. The repository is forked as a forensic snapshot, tagged `incident-<id>`.
4. The repository's capture level switches to Full.

Three clocks start from the moment of awareness, which can be set earlier than the declaration and never later: the early warning is due 24 hours after awareness, the notification 72 hours after, and the final report one calendar month after the notification (counted from the notification deadline until a notification is recorded). The page shows each clock as pending, due within 6 hours, overdue or done.

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

A failed machine step leaves the record and its hold in place, exits 1 and names the command that runs only the failed steps again:

```bash
rdc incident declare mail --resume <id>
```

`--resume` keeps the window and awareness of the original declaration, so `--since`, `--until` and `--aware-at` are not combined with it.

## Export the evidence

`rdc incident export` writes the incident's window to a directory: the incident record with its clocks, the merged timeline, the bytes-out aggregates, the raw chain manifest and the raw files it lists. When the manifest lists audit day files or forensics headers files, the chains are verified on the way and the result goes to `verification.json`. The command exits 1 when the evidence shows a gap or an edit.

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

With `--stage`, the same command writes a signed report instead. See [incident reports](/en/docs/incident-reports).

## Close an incident

```bash
rdc incident close <id>
```

Nothing is released at once. The eviction hold and the bucket lock rules end 30 days after the close.

## Ask AI

The investigation page has an assistant that answers questions about the open scope and window. It reads only that scope and window, under a single-use ticket minted from the open investigation that stays redeemable for 15 minutes. The question and the rows it reads go to the organization's own AI provider. The assistant can run the `rdc` verbs above under the same permission rules as any other command.

## Commands

| Command | Purpose |
|---|---|
| `rdc repo flows <ref>` | Network flows of a repository in a window |
| `rdc repo opens <ref>` | Sensitive file opens of a repository in a window |
| `rdc forensics level <ref> <level>` | Set the capture level |
| `rdc forensics verify` | Verify an evidence directory or a signed report |
| `rdc incident declare <ref>` | Record an incident, fork the repository and switch to Full |
| `rdc incident status [id]` | List incidents, or show one with its clocks |
| `rdc incident export <id>` | Write the evidence window, or a signed report with `--stage` |
| `rdc incident close <id>` | Close an incident |
