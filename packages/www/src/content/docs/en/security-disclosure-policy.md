---
title: "Vulnerability Disclosure Policy"
description: "How to report a security vulnerability in Rediacc: scope, safe harbour, how to report, and what response times to expect."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 9
language: en
---

Rediacc welcomes reports of security vulnerabilities in its products and services. This policy describes what is in scope, how to report, and what a reporter can expect in return. The machine-readable contact file is at [`/.well-known/security.txt`](https://www.rediacc.com/.well-known/security.txt) (RFC 9116).

## Scope

In scope:

- the `rdc` CLI and the `renet` machine orchestrator
- the account server, its web portal and its API
- the Rediacc websites under `rediacc.com` and `rediacc.cloud`
- the release artifacts: binaries, container images and installers

Out of scope:

- findings that need physical access to a machine, or a compromised endpoint the reporter already controls
- denial of service by volume, spam, or social engineering of staff
- reports from automated scanners with no demonstrated impact
- vulnerabilities in third-party software that Rediacc only redistributes unchanged; those go to the upstream project, with a copy welcome here

## How to report

Send the report to [security@rediacc.com](mailto:security@rediacc.com). Include:

- the affected product and version, or the URL
- the steps to reproduce, or a proof of concept
- the impact the reporter expects
- whether the issue is already public or being exploited
- a contact address for follow-up, and whether credit is wanted

Reports in English are preferred. Real customer data stays out of the report: a minimal proof of the access is enough.

## Safe harbour

Rediacc will not pursue or support legal action against a reporter who acts in good faith under this policy, which means that the reporter:

- tests only against own accounts, machines and data, or against assets Rediacc owns
- stops at the point of proving the issue, and does not read, change, copy or delete data that belongs to others
- does not degrade the service for other users
- reports promptly, and keeps details private until the coordinated disclosure date below

Work that stays within these limits is treated as authorised, and Rediacc will say so to a third party that asks.

## Response times

| Step | Target |
|------|--------|
| Acknowledgement of the report | 2 business days |
| First assessment, with severity | 5 business days |
| Status updates while open | at least every 14 days |
| Fix or mitigation for a critical issue | 14 days from the assessment |
| Fix or mitigation for other confirmed issues | 90 days from the assessment |

The targets are goals, and a report that needs more time gets an explanation and a new date.

## Coordinated disclosure

Details are published together with the fix, normally within 90 days of the first assessment. A reporter who wants earlier or later publication names the date in the report, and the two sides agree on one. A vulnerability already exploited in the wild is handled as an incident, as described on the [incident response page](/en/docs/security-incident-response).

## Credit

A confirmed report is credited in the release notes or advisory under the name or handle the reporter chooses. Rediacc does not run a paid bounty programme.

## Related

- [Incident response](/en/docs/security-incident-response)
- [Account security and API](/en/docs/account-security)
