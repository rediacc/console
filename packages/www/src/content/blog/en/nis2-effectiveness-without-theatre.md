---
title: "Your Annual Pen Test is Compliance Theatre. NIS2 Article 21(2)(f) Just Made That a Problem."
description: "Continuous effectiveness assessment, the constant-time fork that makes it cheap, and the Article 23 reporting timeline you cannot meet without forensic-grade artefacts."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - sre
  - dr-testing
  - effectiveness
  - incident-reporting
featured: false
language: en
---

> **TL;DR.** Most security programs test recovery once a year, against a staging environment forked from production sometime last summer. They commission a pen test against an environment that does not look like production, get a clean report, and file it. NIS2 Article 21(2)(f) just introduced a phrase auditors are about to lean on hard: "policies and procedures to assess the effectiveness" of the measures. Annual is not continuous. Stale staging is not the system under test.
>
> - The directive read: 21(2)(e) and (f) together require recovery and security testing that actually work, on demand, against current production.
> - The cost-of-doing-it-right with Delphix-class tooling, Veeam Instant Recovery, or Rubrik Live Mount is what makes most teams quietly opt for staging instead.
> - When a production fork takes seven seconds, the economics flip. Weekly drills become realistic. Continuous effectiveness becomes documentable.
> - Article 23 reporting (24-hour early warning, 72-hour notification, one-month report) is unmeetable without forensic-grade artefacts. We have the artefacts; the SOC and the SIEM and the ENISA filing workflow are still on you.

Walk into any mid-sized SRE team and ask one question: when did you last do a full end-to-end recovery, not a backup-file verification, but actually spin up the recovered system with apps, databases and configs, and validate it works? The honest answer, in most teams, is "in last year's tabletop exercise." Then everyone goes back to work.

NIS2 Article 21(2)(f) introduces a phrase auditors are about to lean on hard:

> "policies and procedures to assess the effectiveness of cybersecurity risk-management measures"

It does not say "annual." It says "policies and procedures." Read alongside Article 21(2)(e), which mandates:

> "security in network and information systems acquisition, development and maintenance, including vulnerability handling and disclosure"

the obligation is continuous, not periodic. The 2024 ENISA implementing guidance (Annex IV of Implementing Regulation (EU) 2024/2690) <!-- nis2-quote-skip: ENISA Implementing Regulation 2024/2690, separate source --> confirms the direction with phrases like "ongoing assessment" and "documented evidence of testing covering current production environments, not legacy or staging snapshots."

If your effectiveness story is "annual pen test against staging," 2026 is going to be uncomfortable.

This post is for SRE leads, ops managers, and the security engineers who actually run the drills. It is also the post that names the wedge an incumbent will pivot to in any counter-pitch: managed reporting and SIEM connector services for Article 23 timelines. We do not solve that. We give you the artefacts. The reporting workflow, the SOC, the ENISA filing engine, those are still on you.

## Reading 21(2)(e) and (f) together

Article 21 lists ten minimum measures. Two of them are about how you build and how you check.

(e) **Security in acquisition, development and maintenance**: this is the supply-side measure. When you accept a CVE patch, when you ship a new microservice, when you run a maintenance window, the change has to be validated against the actual environment it is going into. ENISA's guidance is explicit that staging environments which differ from production in data shape, scale, secrets, or configuration do not satisfy the testing obligation for security-relevant changes.

(f) **Effectiveness assessment**: this is the verification measure. Whatever controls you have, you need policies and procedures to confirm they actually work. The phrasing "effectiveness" is doing real work. It is the difference between "we have a backup" (control exists) and "we proved we can restore from it last Tuesday and the restored system passed a smoke test" (control is effective).

Read together, the two measures require that security-relevant changes are tested in current production-equivalent environments, and that the testing produces evidence the change worked. Annual is too rare. Stale staging is the wrong target. Restoration that is not validated is not effective.

The traditional response to this obligation is what most teams already do: declare staging to be production-like, run drills against staging on a yearly cadence, write a runbook describing what would happen in a real incident, and hope the regulator does not ask too many questions. That worked when the regulator was the GDPR DPA and the incident was a privacy event. NIS2 puts a different regulator in the seat (the national CSIRT, or BSI in Germany, ANSSI in France, ACN in Italy), and that regulator is asking operational questions.

## The stale-staging trap

Three things make staging not-production by the time most teams are testing against it.

**Data shape**: production data has long-tail edge cases. The customer with the 8,000-character notes field, the legacy account with a NULL where every other row has a value, the joined table that returned 12 million rows for the one tenant who imported their entire CRM history. Staging has 1% of production volume and the long tail is not in the sample.

**Scale**: a query that returns in 50ms against 10,000 rows in staging returns in 8 seconds against 12 million in production. A pen-test scenario that fails to find an exhaustion vulnerability in staging finds it in production immediately. The vulnerability shape depends on the data scale.

**Configuration drift**: production has accumulated environment variables, IAM roles, network policies, secrets rotated three times, an SSL cert renewed last week, a feature flag that was supposed to be turned off in March but stayed on. Staging has a clean copy of last summer's configuration plus whatever was added for the most recent project. The deltas are exactly where security bugs hide.

So when the patch passes in staging, the team's confidence is misplaced. When the pen test reports clean against staging, the report is misleading. When the recovery drill restores staging successfully, the team has not validated production recovery.

Auditors in 2026 are not arguing about whether staging is good enough. They are asking for evidence of testing against current production. The evidence has to be timestamped, has to show the system under test looked like production at the time of the test, and has to show the test produced a result.

Most teams cannot produce that evidence today, because the cost of running drills against current production is prohibitive with traditional tooling.

## The cost of doing it right with traditional tooling

The market has answers. The answers are expensive.

**Veeam Instant Recovery**: spin up a VM directly from a backup, mount it, point a network interface at it. Used for application-consistent recovery testing. Capable of testing recovery against a recent backup; the staging environment becomes the recovered backup. Capacity-light because the disk reads come from the backup repository. Cost: Veeam Data Platform Premium licensing scales by VM count, and the recovery test still has to be planned and operated by an engineer. Most teams run this once a quarter.

**Rubrik Live Mount**: similar concept, instant mount of a backup snapshot for testing. Better integration with cloud-native workloads. Same operational pattern. Same per-test engineering overhead.

**Delphix (Perforce DevOps Data)**: virtualises source databases so dev gets near-instant clones. Fixes the prod-shaped-data-in-dev problem. Database only. It will not clone your app services, configs, secrets, or container state. The annual licence hits six figures for mid-market teams.

**Tonic.ai, Redgate Test Data Manager**: mask or synthesise data for dev and test. Good fix for the privacy-vs-realism tradeoff. The data shape and scale look like prod. But these tools clone the data, not the app stack. Use them for QA, not for security drills where the config is the bug.

**Custom build**: take a hot backup, restore it to a parallel environment, run the test, tear it down. Conceptually possible. Operationally a multi-day engineering effort per drill. The team does this once because they were forced to, then never again.

Cloning full prod, including app state, has always meant one of three things. Copy every byte (slow, expensive at scale). Snapshot the VM (works for IaaS, breaks for containers and Kubernetes). Or virtualise the database only. All three cost more per drill as the environment grows.

When per-test cost scales with size, drills become rare events. Rare events do not satisfy continuous effectiveness assessment.

## What changes when a production fork takes seven seconds

Rediacc uses BTRFS reflinks for repository forking. The mechanism is filesystem-level copy-on-write: the fork shares blocks with the parent until either side writes new data, at which point only the changed blocks diverge. The fork operation itself is constant time regardless of repository size.

In our [PocketOS test post](/en/blog/i-tested-rediacc-against-the-pocketos-incident), we forked a 128 GB production repository in 7.2 seconds end to end. The reflink itself was 2.3 seconds. Most of the rest is provisioning a new Docker daemon, mounting the LUKS-encrypted volume, and bringing up the service stack on a new loopback IP subnet.

The shape of the fork matters as much as the speed. A Rediacc fork is full-stack. The forked repository contains:

- The LUKS-encrypted volume with all data files and database state.
- The Docker daemon configuration and container state.
- The Rediaccfile lifecycle hooks (`up`, `down`, `info`).
- The repository's loopback IP subnet (a fresh `/26` carved out for the fork).
- The repository's network ID, daemon socket, and mount namespace.

What it does not contain by default is the secrets your services need to talk to external SaaS (Stripe, mail relays, DKIM keys, webhook signing keys). For those, `rdc repo secret` keeps credentials out of the fork image entirely so external SaaS calls from a fork are explicit, not inherited. See [Repositories](/en/docs/repositories) for the secret model.

This shape, full-stack with explicit secret handling, is what makes the fork suitable as a target for security testing. The fork is the production system, with current production data, current production config, current container state, ten seconds ago. That is the system the auditor wants you to be testing against.

For the documented use cases, see [Risk-Free Upgrades](/en/docs/risk-free-upgrades) and [Tutorial: Forking](/en/docs/tutorial-forking).

## A continuous-effectiveness routine you can run weekly

Here is a concrete routine that satisfies Article 21(2)(e) and (f) for a production repository, runnable on a weekly cadence by a single SRE.

**Step 1**: Fork production.

```bash
rdc repo fork --parent prod-app --tag effectiveness-2026w19 -m hostinger
```

The fork is named with the ISO week so the audit log reads itself. The repo comes up under a fork subdomain (`<service>-fork-effectiveness-2026w19.prod-app.<machine>.<basedomain>`). The parent wildcard cert covers it. No new TLS handshake.

**Step 2**: Apply the patch under test, on the fork.

```bash
rdc repo up --name prod-app:effectiveness-2026w19 -m hostinger
rdc term connect -m hostinger -r prod-app:effectiveness-2026w19 -c "apt-get install -y openssl=3.5.5-1"
```

The term session runs as the unprivileged `rediacc` user (UID 7111), in a separate mount namespace, with `DOCKER_HOST` scoped to the fork's daemon socket. Cross-repo access is blocked at the kernel level (the fork cannot reach production's loopback subnet). See [Architecture § Docker Isolation](/en/docs/architecture) for the isolation model.

**Step 3**: Run the smoke test against the fork.

```bash
curl -fsS https://app-fork-effectiveness-2026w19.prod-app.hostinger.example.com/health
# (your project-specific smoke test goes here)
```

**Step 4**: Run the restore drill. Use the most recent hot backup of production, pulled to a fork-aligned target.

```bash
rdc repo backup pull --from offsite-b2 --name prod-app:restore-2026w19 -m hostinger
rdc repo up --name prod-app:restore-2026w19 -m hostinger
# verify the restored fork answers the same smoke test
curl -fsS https://app-fork-restore-2026w19.prod-app.hostinger.example.com/health
```

This is the recovery test that 21(2)(c) and (f) ask for: not "the backup file integrity verified" but "the recovered system answers a smoke test."

**Step 5**: Audit log the result, then tear down.

```bash
rdc audit log --since "1 hour ago" > /tmp/effectiveness-2026w19.json
rdc repo destroy --name prod-app:effectiveness-2026w19 -m hostinger --force
rdc repo destroy --name prod-app:restore-2026w19 -m hostinger --force
```

The audit log captures every step (fork creation, repo up, term sessions, backup pull, repo destroy). It is hash-chained. `rdc audit verify` on the operator's workstation confirms the chain has not been modified since the events were written. See [Account Security § CLI Security Posture for AI Agents](/en/docs/account-security) for the audit model.

The total wall-clock time for the routine, on a 128 GB repository, is under 15 minutes. Most of that is the smoke test and the network round-trip for the backup pull. The fork operations themselves are seconds each.

A single SRE running this once a week produces 52 timestamped, audit-logged effectiveness records per year. That is the evidence shape an auditor is asking for.

Want the full recovery story? [Cross Backup Strategy](/en/docs/cross-backup) covers drills across machines and continents. [Backup & Restore](/en/docs/backup-restore) is the primer. For a partial-corruption event, see [Time Travel Recovery](/en/docs/time-travel-recovery).

## Article 23: the reporting timeline you cannot meet without artefacts

NIS2 Article 23 is the incident reporting clock. Three deadlines:

- **24 hours** from awareness of a significant incident: an early warning to the national CSIRT or competent authority. Indicates the incident is occurring and provides initial information on cross-border impact.
- **72 hours** from awareness: a full incident notification. Includes severity assessment, initial indicators of compromise, type of threat, and known impact.
- **One month** from notification: a final report. Detailed description, root cause, mitigations applied, ongoing risk.

This is a tight clock. It is also a clock that runs while the incident is still ongoing. The most painful version of Article 23 is the one where the team is restoring services, preserving forensic evidence, coordinating with law enforcement, briefing the executive team, and writing the early warning, all in the first 24 hours.

Standard backup tools force a tradeoff: restore the system to get service back, or preserve the system to investigate. Once you restore from backup, the live evidence of the compromise is gone. Once you freeze the compromised system to investigate, you are not serving customers. Both are bad in an Article 23 timeline.

The fork mechanism resolves the tradeoff. The compromised state can be forked (the parent repository becomes the forensic snapshot) and a parallel fork can be brought up from the most recent clean backup to serve traffic. The forensic fork is read-only for analysis. The serving fork answers customers. Both exist simultaneously on the same machine, sharing blocks via reflink, which is why this is operationally affordable.

Concretely, in an incident:

```bash
# Snapshot the compromised state for forensics. The fork is the snapshot.
rdc repo fork --parent prod-app --tag forensic-2026-05-09T14-23Z -m hostinger

# Bring up a serving fork from the last clean backup. Different tag.
rdc repo backup pull --from offsite-b2 --name prod-app:serving-2026-05-09T14-30Z -m hostinger
rdc repo up --name prod-app:serving-2026-05-09T14-30Z -m hostinger
# Cut traffic to the new serving fork via DNS or the route server.
```

The forensic fork answers the regulator's question at hour 60: "show us the exact state of your systems at the moment of compromise." The serving fork answers the customer's question. The 70+-event audit log answers "who did what, when" in a hash-chained, verifiable way.

That is what Rediacc gives the operator. What we do not give:

- **The SIEM**. We do not stream to Splunk, Datadog, Sentinel, or your homegrown stack. The audit log is local JSONL on the operator's workstation; piping it to a SIEM is the operator's integration job.
- **The SOC**. We do not run a 24x7 detection capability. We do not produce alerts. We do not triage.
- **The managed reporting**. We do not file the ENISA report. We do not draft the early warning. We do not coordinate with the national CSIRT on your behalf.

This is the wedge an incumbent will use against us. Veeam Data Platform with Coveware integrations, Rubrik with their managed services arm, and a few specialised IR-retainer firms (Mandiant, Kroll, S-RM in Europe) sell exactly the operational layer Rediacc does not. Pretending otherwise is the marketing move that gets us into trouble. The defensible position is: Rediacc gives you forensic-grade artefacts that those services cannot produce by themselves; those services give you the operational reporting layer that Rediacc cannot provide. They are complementary. A NIS2 program needs both.

## What Rediacc does not run for you

Two things an SRE should know upfront, before deciding the rest of the post is interesting.

**Rediacc does not run pen tests**. The fork-as-a-target is the environment, not the testing capability. A real adversarial pen test is still your red team or your contracted testing firm (Pentera, Horizon3.ai for autonomous; specialised consulting firms for human-led). Rediacc removes their excuse that the test environment was unrealistic. It does not remove the cost of the test.

**Rediacc does not write your runbooks**. The CLI commands above are the moving parts. The decisions about when to fork, when to fail over, how to communicate with customers, when to engage law enforcement, are runbook decisions. Those still need to be authored, exercised, and updated by your team. NIS2 Article 21(2)(b) (incident handling) is a process obligation, not a tooling obligation, and we satisfy a portion of it, not all of it.

On the procurement side (certifications, GRC, the supplier-register problem), see the [supply chain post](/en/blog/nis2-supply-chain-self-hosted). On the cost side (what stays on the budget once you self-host), see the [real bill post](/en/blog/nis2-the-real-bill).

The right read of these: Rediacc is a tooling layer, not a security program. It removes excuses and produces evidence. It does not run the program for you.

## What an auditor wants to see in 2026

Three artefacts. Produce these and the Article 21(2)(e) and (f) conversation gets short.

**Artefact 1: the fork-drill cadence**. A timestamped log of effectiveness drills run on a weekly or bi-weekly cadence over a rolling twelve months. Each entry shows the parent repository, the fork tag, the patch or change under test, the smoke test result, and the teardown timestamp. The audit log produced by `rdc audit log --since` captures all of this.

**Artefact 2: the audit log of those drills, hash-chained**. The hash chain on the audit log is what turns "we ran 47 drills last year" from a claim into evidence. `rdc audit verify` validates the chain end-to-end. The validation result is a single command output that an auditor can re-run.

**Artefact 3: the backup-verify trail**. For each scheduled backup strategy, the systemd unit produces a status sidecar at `/var/run/rediacc/cold-backup-<guid>.status.json` per repo per run, and a final summary log line. `rdc machine backup status` surfaces both. Combined with the weekly restore drill from Step 4 of the routine above, this gives the auditor a "backup-and-restore-tested" trail, not just a "backup-taken" trail. See [Monitoring](/en/docs/monitoring) for the diagnostic surface.

Together, the artefacts answer the question "are your controls effective" with timestamps and a hash chain. Not attestation. Evidence.

## What this means for the next quarterly planning meeting

If your team is heading into Q3 planning and Article 21(2)(f) is on the security backlog, three concrete moves:

1. Audit your current effectiveness story. Pull the last twelve months of pen-test reports, recovery drills, and patch-validation tickets. Count how many of them targeted current production. The honest count is usually under five.
2. Pick one production repository and run the weekly routine above against it for a month. The routine is shaped to be operable by one SRE without scheduling overhead. After four weeks, you have four timestamped effectiveness records; that is more than most teams produce in a year.
3. Have the conversation about who covers the SIEM, the SOC, and the Article 23 reporting workflow. If the answer is "we have not got that far," the right place to start is not Rediacc, it is a 24x7 detection capability. We are complementary to that conversation; we are not the start of it.

If you want to see the fork timing on your largest repository, the offer is simple. Run it on a call with us. If the fork takes longer than ten seconds, you owe us nothing. If it takes seven, we will spend the rest of the call walking through the routine on your stack.

The structural cost story (what gets collapsed across the rest of the security stack and what stays on the budget line) is in the companion post on [the real bill](/en/blog/nis2-the-real-bill). For the supplier-register and procurement angle, see [Article 21(2)(d) and self-hosting](/en/blog/nis2-supply-chain-self-hosted).

For the public map of what Rediacc does against each NIS2 article, see [NIS2 and DORA](/en/docs/legal-nis2-dora).
