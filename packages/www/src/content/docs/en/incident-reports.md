---
title: "Incident Reports: Staged, Signed and Verifiable"
description: "Generate the early warning, the notification and the final report for an incident in a customer repository as JSON, STIX 2.1 or PDF. Each report is Ed25519-signed, carries a QR verify link, and maps its fields onto NIS2, the 2025/302 format and GDPR Art. 33(3)."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 11
language: en
---

# Incident Reports

A declared incident ([incident response](/en/docs/incident-response)) produces three staged reports for the customer to file with a regulator. Rediacc generates the documents from the evidence. Whether an incident is significant or reportable stays the customer's judgement, and every report says so.

## Stages

Each stage lists the sections it requires and no others, so a section a stage does not call for is omitted rather than left blank.

| Stage | Due | Adds |
|---|---|---|
| Early warning | 24 hours after awareness | Header, timeline, indicators of compromise, suspected malicious and cross-border impact |
| Notification | 72 hours after awareness | Initial assessment, data impact (categories, approximate counts, Member States) and ATT&CK techniques |
| Final | One calendar month after the notification | Root cause and mitigation steps |

The final report follows a notification, so the notification is generated first. Each stage includes the sections of the stage before it.

Every fact in a report says how it is known: observed in the evidence, entered by the customer, or inferred. An inferred fact carries a confidence and the detector's reason. The assessment, data categories, Member States, suspected cause, actions taken, contact point and techniques are inputs that the customer enters on the incident page before generating.

## Formats

| Format | Use |
|---|---|
| JSON | The canonical, verifiable form |
| STIX 2.1 | A bundle of indicators for threat-intelligence tools |
| PDF | A readable document, rendering non-Latin scripts, with the disclaimer, a QR code and the report hash on every page footer |

From the incident page, each stage has a download button per format. From the command line:

```bash
rdc incident export <id> --stage early-warning
rdc incident export <id> --stage notification --format stix
rdc incident export <id> --stage final --format pdf --out ./reports
```

The format defaults to JSON. `--format` applies only with `--stage`. The file is written under its report id.

## Signing and verification

Each report is signed with an Ed25519 report key, and the report id, stage and hash are on a public record. The signature covers the report's canonical content, so any change after signing is detected.

A report is checked in three places:

- The verify page at `/account/verify/report/<id>`, which the QR code on the PDF opens. The check runs in the browser against the published report key, and nothing is uploaded. A JSON file is fully checked. A PDF cannot be re-hashed in the browser, so the page confirms that the PDF carries the report's hash and points to the JSON file for a full check.
- The command line, for a JSON report:

```bash
rdc forensics verify --report ./reports/<report-id>.json
```

The command exits 1 when the content or the signature does not match. A PDF is verified through the JSON report it was made from.

- The evidence stamp inside the report, which records the result of Verify evidence for the window: who verified, with which version and when.

## Field map

Each report field maps onto the regimes the customer reports under, so the content can be carried across without retyping. The map covers three regimes: NIS2 Art. 23(4), the Implementing Regulation (EU) 2025/302 incident notification format, and GDPR Art. 33(3). Examples:

| Report field | NIS2 | GDPR |
|---|---|---|
| Time of awareness | Art. 23(4)(a) | Art. 33(1) |
| Chronology | Art. 23(4)(d) | Art. 33(3)(a) |
| Contact point | Art. 23(4) | Art. 33(3)(b) |

A field with no counterpart in a regime says why instead of being left out. The GDPR Art. 33(3) notification has no reference number or closing time, for example.

## What a report does not claim

Two statements are printed in every stage:

- Flow records prove volume and destination, not content.
- Whether the incident is significant or reportable is the customer's judgement.

Rediacc files nothing with a regulator on the customer's behalf.
