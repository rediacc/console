# breach-forensics: operator decisions

Every ruling below was given by the operator in session `9b22c347` on 2026-11-23, through AskUserQuestion batches recorded on worklist item #772cfd55. A plan in this program cites a decision by its id (`F7`), never by paraphrase, and does not re-litigate it.

## Purpose and capture

- **F1 The program answers "when was data stolen" and "what data was stolen"**, per machine and per repo, after software running inside a customer repo is compromised. Rediacc cannot close the third-party software's holes; it records evidence that survives the compromise.
- **F2 The customer picks a capture level per repo, trading performance for detail**, and the smallest level is the default. Three levels: Basic (connection summaries every 5 minutes: destination, port, bytes in and out), Standard (per-minute flow records with process and DNS name), Full (Standard plus file opens on sensitive paths such as database data directories, `.env` files, key stores and dumps).
- **F3 Any level arms a trigger** that switches the repo to Full for 24 hours when outbound bytes spike against the repo's own baseline.
- **F4 Capture lives in renet**, extending the eBPF cgroup programs it already attaches at `rediacc.slice`, read by a root-owned collector outside the repo sandbox. Repo containers use host networking, so attribution is by cgroup, never by IP.

## Shipping, storage, tiers

- **F5 Logs ship to Rediacc's R2 through create-only presigned URLs** minted from the machine's licence blob (the backup-session pattern), in batches every 30 seconds, each batch signed and chained to the previous batch's hash, with heartbeats so a stopped collector shows as silence. An R2 bucket lock lives in a Rediacc account that customers' admins cannot reach. Nightly compaction follows the console-audit pattern.
- **F6 Paid plans only, recorded only while paid.** Free tiers are not offered the feature and record nothing; an upgrade starts with no history.
- **F7 Each paid plan includes a forensics quota of 25% of its backup quota**: PROFESSIONAL 25 GB, BUSINESS 125 GB, ENTERPRISE 512 GB; COMMUNITY and FREE 0.
- **F8 When the quota is full, the oldest records are evicted first (FIFO)**, with guards against over-storage. The newest 7 days are locked and never evicted, even by FIFO.
- **F9 More quota comes only from a plan upgrade.** ENTERPRISE orgs get a custom quota set by Rediacc admins in the admin panel, never by the org owner. There is no in-product purchase (Stripe is being disabled, agent/plans/PLAN-stripe-disable.md).

## Detection and models

- **F10 Anomaly detection runs offline on the machine and again on the server.** A statistical detector on the machine reacts at once (switching to Full); the server detector on ingest survives a compromised host. No AI runs per log record.
- **F11 Detectors are Go-native and layered**: hour-of-week rate baselines per repo (bytes, connections, distinct destinations, new DNS names, new processes), Half-Space Trees per flow, ECOD and HBOS batch scoring with per-feature reasons, and first-seen process-to-sensitive-file pairs. Each repo learns from its own traffic. A small time-series model (Granite TTM, Apache-2.0) may come later.
- **F12 No local LLM.** Offline explanations are templates built from the detectors' per-feature reasons. AI explanations come only through the customer's online provider or enterprise credits (agent/programs/console-rework/02-decisions.md C30-C32).
- **F13 renet stays pure Go and statically built, with no cgo.** AVX-512 and AVX2 kernels are written with Go's SIMD support or assembly, chosen at run time from the CPU flags (golang.org/x/sys/cpu), each checked against a plain-Go reference; arm64 uses NEON; a scalar path covers the rest.
- **F14 Detector models are published as signed bundles on `data.rediacc.com/models/`** (the `rediacc-public-data` bucket): content-addressed files, a manifest signed with a new offline Ed25519 model key built into renet like the licence key, per-file sha256, a minimum renet version, a monotonic version against downgrade, edge and stable channels, staged rollout with a canary check and automatic rollback. A scripted upload job replaces today's hand-run one. Air-gapped installs receive the same signed bundle inside `rdc server bundle`.

## Alerts, investigation, reports

- **F15 Alerts become account notices and emails** through private/account. Offline, the machine acts locally at once (Full capture, a record in its signed local spool) and delivers the alert when connectivity returns, keeping the original detection time; on-premise installs deliver to their own account server.
- **F16 Incident investigation is one timeline per repo or machine**, merging console audit, runs, network flows, file opens and changes since the last snapshot, with a time-window scrubber, Export report, Verify evidence and Ask AI. AI support is wanted.
- **F17 Verify evidence recomputes the hash chains** of the audit days and forensics batches for the window in the browser, shows gaps and edits, and stamps the result into exported reports.
- **F18 Org owners and admins open investigations after step-up**; every view is audited; Rediacc support sees forensics data only under a time-limited grant the customer issues.
- **F19 Declare incident freezes evidence**: it forks the repo as a forensic snapshot, extends the R2 lock over the incident window so FIFO cannot evict it, switches capture to Full, records who declared it, and starts visible 24 hour, 72 hour and one month deadline clocks.
- **F20 New rdc commands**: `rdc incident declare|status|export|close`, `rdc repo flows <ref>`, `rdc repo opens <ref>`, `rdc forensics level <ref> basic|standard|full`, `rdc forensics verify`, usable by the AI assistant under the same permission rules.
- **F21 Rediacc's own incidents get a staged security notice**: a security-incident notice kind that ignores email preferences, sent to affected orgs at 24 hours, 72 hours and one month with the GDPR Art. 33(3) fields and STIX 2.1 indicators; an org security-contact field; `security.txt`, a vulnerability disclosure policy and an incident-response page; one intake that also drives Rediacc's own CRA reporting to ENISA.
- **F22 Customer repo incidents get a staged report** for the customer to file: 24 hour, 72 hour and final exports as PDF, JSON and a STIX 2.1 bundle, Ed25519-signed with a QR verify link, with a field map onto NIS2, GDPR Art. 33 and DORA, and an explicit statement that flow records prove volume and destination, not content.

## Wording

- **F23 The legal and marketing wording is corrected as one of the program's last steps**: the "detection" and "forensic trail" claims in the legal pages and the NIS2 blog, and the "hash-chained audit log" claim in sales study content, are rewritten to what the shipped program provides.
