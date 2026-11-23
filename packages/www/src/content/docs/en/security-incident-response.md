---
title: "Security Incident Response"
description: "How Rediacc handles its own security incidents: the staged customer notices, the GDPR Art. 33(3) fields, the CRA reporting path, and what customers receive."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 10
language: en
---

This page describes what happens when Rediacc itself has a security incident, such as a compromise of its own systems or an actively exploited vulnerability in its products. Incidents inside a customer's own repositories are the customer's to investigate and report, and Rediacc provides the evidence tooling for that. Vulnerability reports from outside are covered by the [disclosure policy](/en/docs/security-disclosure-policy).

## Stages

Each incident has a clock that starts when Rediacc becomes aware of it. Information is released in stages, because the full picture is rarely known on day one and GDPR Art. 33(4) allows information to be provided in phases.

| Stage | Due | Content |
|-------|-----|---------|
| Early warning | within 24 hours | what is known so far, and whether malicious acts are suspected |
| Notification | within 72 hours | the nature of the incident, an initial assessment, and the measures taken |
| Final report | within one month | a detailed description, the root cause, and the applied and ongoing measures |

## The Art. 33(3) fields

Every stage carries the four items listed in GDPR Art. 33(3):

1. the nature of the breach, with the categories and approximate number of data subjects and of personal data records concerned
2. the name and contact details of the contact point for more information
3. the likely consequences
4. the measures taken or proposed to address the breach, including measures to reduce its possible adverse effects

Where a value is not yet known, the stage says so and gives the date by which it will be.

## What customers receive

When an incident affects an organization:

- each stage is sent as a notice in the account portal and as an email, to the organization's owners and admins and to its security contact
- the notice and email are sent regardless of notification preferences, because they are security communications
- a banner in the portal links to the incident page, which shows every published stage
- each stage offers a STIX 2.1 bundle with the indicators of compromise, in a machine-readable format that security tooling can import

An organization that is not affected receives nothing. Owners and admins set the organization's security contact in the portal, so that the mail reaches the right person.

## Regulatory reporting

Rediacc reports its own incidents where the law requires it.

- **GDPR.** Where Rediacc acts as processor, the staged notice informs the controller without undue delay (Art. 33(2)), and the controller decides on notification to its supervisory authority. Where Rediacc is the controller, it notifies the competent supervisory authority within 72 hours where feasible (Art. 33(1)).
- **Cyber Resilience Act.** Since 11 September 2026, Art. 14 of Regulation (EU) 2024/2847 requires a manufacturer to report an actively exploited vulnerability or a severe incident affecting the security of a product with digital elements to the designated CSIRT and to ENISA, through the single reporting platform. The same 24-hour, 72-hour and final steps apply, and the same incident record feeds both the customer notice and the filing.

## Reporting a suspected incident

Anyone who suspects an incident affecting Rediacc, including a customer who sees unexpected behaviour in a Rediacc component, writes to [security@rediacc.com](mailto:security@rediacc.com). Reporting a vulnerability follows the [disclosure policy](/en/docs/security-disclosure-policy).
