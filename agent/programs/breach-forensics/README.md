# breach-forensics

Evidence that survives a compromise of the software customers run inside their repos: per-repo network flows and sensitive file opens captured by renet's eBPF at a customer-chosen level, shipped every 30 seconds as signed, hash-chained batches to a locked R2 bucket, scored offline by Go-native detectors on the machine and again on the server, investigated on one timeline in the console, frozen by Declare incident, and turned into staged incident reports for NIS2, GDPR and DORA. Paid plans only.

Planned in session `9b22c347` on 2026-11-23, branch `1121-1`, after the operator asked how to answer "when was data stolen" and "what data was stolen" machine-wide and repo-wide. One plan per PR.

## Read order

1. `02-decisions.md`: the operator rulings F1 to F23. Binding; cited by id.
2. `01-verified-context.md`: the tree as read on 2026-11-23, with `file:line` evidence.
3. `03-external-research.md`: breaches, industry practice, models and reporting duties, with sources.
4. The plans, in the order below.

## The plans

| # | Plan | Box prefix | Delivers | Depends-On |
|---|---|---|---|---|
| 1 | `agent/plans/PLAN-forensics-capture.md` | `FC` | renet eBPF flow and file-open capture, the three levels and the spike trigger, the root-owned collector and its signed local spool, CPU feature flags (F2-F4, F13) | none |
| 2 | `agent/plans/PLAN-forensics-shipping.md` | `FS` | licence-minted create-only log grants, per-machine prefix, signed hash-chained batches, heartbeats, the locked bucket, nightly compaction, quota accounting, FIFO past the 7-day lock, plan quotas and the enterprise admin override, the paid-only entitlement (F5-F9) | 1 |
| 3 | `agent/plans/PLAN-forensics-detection.md` | `FD` | Go-native detectors on the machine and on ingest, SIMD kernels with runtime dispatch, signed model bundles on data.rediacc.com with channels and rollback, the air-gapped bundle path (F10-F14) | 1, 2 |
| 4 | `agent/plans/PLAN-forensics-investigation.md` | `FI` | the incident timeline, Verify evidence, Declare incident with deadline clocks, step-up access and support grants, Ask AI, the new rdc commands (F16-F20) | 2, 3, console-audit-r2, console-run-index, console-confirm-stepup |
| 5 | `agent/plans/PLAN-forensics-alerts-notices.md` | `FN` | anomaly notices and emails with offline delivery, the security-incident notice for Rediacc's own incidents, security contact, security.txt, disclosure and incident-response policies, the CRA intake (F15, F21) | 3 |
| 6 | `agent/plans/PLAN-forensics-reports.md` | `FR` | staged repo incident reports as signed PDF, JSON and STIX with QR verify and the regulatory field map (F22) | 4 |
| 7 | `agent/plans/PLAN-forensics-docs-legal.md` | `FL` | feature docs, the corrected legal and marketing wording, the public-data bucket documentation (F23) | 1-6 |

`Owns:` in each plan header is the authoritative list. Where two plans touch one file, the later plan in `Depends-On` order owns the edit after the earlier one lands.

## Neighbours

- **console-rework** (`agent/programs/console-rework/`): plan 4 builds on PLAN-console-audit-r2.md (audit chain and Audit page), PLAN-console-run-index.md (runs and the block stream), PLAN-console-confirm-stepup.md (step-up) and the AI plans for Ask AI; plan 2 reuses the console audit's nightly compaction pattern.
- **PLAN-stripe-disable.md**: no in-product purchase (F9).
- **PLAN-tooling-code-reduction.md** CR2: new gates use its header grammar.
- **PLAN-d1-scaling.md**: owns backup-storage.service.ts; plan 2 keeps forensics accounting in its own service.
