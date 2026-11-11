# Enterprise Order Form (template)

English-only template for an Enterprise Subscription. It is not a translated page and is not published on the website. Each executed copy is filled in per customer, signed by both parties (or by the Partner and the Customer, with Rediacc's license terms incorporated), and kept with the customer's records.

Entity facts appear as tokens (`{{legalName}}`, `{{registryCode}}`, `{{registeredAddress}}`, `{{vatNumber}}`, `{{country}}`) and are filled from the vault record `SELLER_PROFILE_JSON` (through `./run.sh legal-entity sync`) when a copy is prepared, never typed by hand.

## 1. Parties

| | Provider | Customer |
|---|---|---|
| Legal name | {{legalName}} | |
| Registry code | {{registryCode}} | |
| VAT number | {{vatNumber}} | |
| Registered address | {{registeredAddress}} | |
| Country | {{country}} | |
| Contract contact | contact@rediacc.com | |
| Billing contact | contact@rediacc.com | |

Partner (only when sold through a Partner): legal name, registered address and contact.

## 2. Agreement

This Order Form is entered into under, and incorporates by reference, the following documents as published at www.rediacc.com on the Effective Date. The version identifier of each is recorded below.

| Document | URL | Version |
|---|---|---|
| Terms of Service | https://www.rediacc.com/en/terms-of-service | |
| Enterprise Software License | https://www.rediacc.com/en/enterprise-license | |
| Data Processing Agreement | https://www.rediacc.com/en/data-processing-agreement | |
| Service Level Agreement | https://www.rediacc.com/en/service-level-agreement | |
| Acceptable Use Policy | https://www.rediacc.com/en/acceptable-use-policy | |

Order of precedence: this Order Form, then the Enterprise Software License, then the Terms of Service. The English version of every document governs.

## 3. Subscription

| Item | Value |
|---|---|
| Effective Date | |
| Subscription Term | (for example, 12 months from the Effective Date) |
| Renewal | (automatic for equal terms unless either party gives 60 days' notice, or none) |
| Activation Ceiling (Machines) | (25 when left blank) |
| Clustering | (included / not included) |
| Self-hosted account server | (included / not included) |
| Hosted backup storage | (amount, or not included) |
| Support level and hours | (default: email support on business days) |
| Service Level Agreement | (the published SLA, or the agreed variation in section 6) |

## 4. Fees and payment

| Item | Amount | Currency | Billing period |
|---|---|---|---|
| Subscription fee | | USD | |
| Additional Machines above the ceiling (per Machine) | | USD | |
| Professional services | | USD | |

Payment terms: invoices are payable within 30 days of the invoice date unless stated otherwise here. Fees exclude taxes. When the Subscription is sold through a Partner, fees and payment are agreed between the Customer and the Partner, and this section records only the Activation Ceiling and the term.

## 5. Liability cap

The cap of the Enterprise Software License applies (fees paid or payable under this Order Form in the 12 months before the claim) unless an agreed amount is entered here:

## 6. Agreed variations

Any variation from the incorporated documents is written here, with the section it changes. An empty section means there is none.

## 7. Data processing

The Data Processing Agreement applies. Customer-specific details, if any (for example, a required data region or an additional notice contact):

## 8. Governing law

Estonian law and the Harju County Court apply, as in the Terms of Service, unless an agreed variation is entered in section 6. The arbitration section of the Terms of Service applies only when the Customer's principal place of business is in the United States.

## 9. Signatures

| | Provider ({{legalName}}) | Customer |
|---|---|---|
| Name | | |
| Title | | |
| Signature | | |
| Date | | |

## Source

Section headings and the order of precedence follow the Common Paper Order Form and the Common Paper Software License Agreement Standard Terms Version 1.1 (https://commonpaper.com/standards/software-license-agreement/1.1), published by Common Paper, Inc. under the Creative Commons Attribution 4.0 International license (https://creativecommons.org/licenses/by/4.0/). The text has been modified and adapted to the Services. Common Paper, Inc. does not endorse this template.
