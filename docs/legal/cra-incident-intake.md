# CRA incident intake (runbook)

English-only internal runbook. It is not a translated page and is not published on the website. It covers Rediacc's own reporting as the manufacturer of products with digital elements (the `rdc` CLI, renet and the account server) under Regulation (EU) 2024/2847 (Cyber Resilience Act, CRA), and its parallel duties under GDPR Art. 33. Customer-side reports for incidents in a customer's own repositories are a separate flow and are not covered here.

Official texts, quoted below from the Publications Office of the European Union rendition of the Official Journal (retrieved 2026-11-23):

- CRA: <https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng> (CELEX 32024R2847; machine-readable copy at <http://publications.europa.eu/resource/celex/32024R2847>)
- GDPR: <https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng> (CELEX 32016R0679; machine-readable copy at <http://publications.europa.eu/resource/celex/32016R0679>)

Art. 14 CRA applies from 11 September 2026 (Art. 71(2) CRA), including to products placed on the market before 11 December 2027 (Art. 69(3) CRA). The obligations are therefore in force.

## 1. Who opens the intake

An intake is opened by an elevated root operator (`requireElevated()`) in the admin console at `/admin/security-incidents`. Any Rediacc staff member who becomes aware of a suspected actively exploited vulnerability or severe incident reports it to the security inbox (security@rediacc.com) and to the elevated operator on duty at once. The intake is opened on the same working session, because the deadlines run from awareness, not from the opening of the record.

The record stores `awareAt`, the moment Rediacc became aware. Every deadline below is computed from it. `awareAt` is set to the earliest credible moment of awareness and is never moved later to gain time. A later correction is kept in the incident's audit trail.

## 2. Choosing `craClass`

`craClass` takes one of three values.

| Value | Choose when | CRA basis |
|---|---|---|
| `exploited_vulnerability` | A vulnerability in a Rediacc product with digital elements is being exploited by a malicious actor, with reliable evidence of it. | Art. 14(1) and (2) |
| `severe_incident` | An incident has an impact on the security of a Rediacc product and meets Art. 14(5): it negatively affects or can negatively affect the protection of the availability, authenticity, integrity or confidentiality of sensitive or important data or functions, or it has led or can lead to the introduction or execution of malicious code in the product or in a user's network and information systems. | Art. 14(3) to (5) |
| `none` | Neither applies. The incident still follows the GDPR Art. 33 stages when personal data is affected, and still gets the customer notice. | none |

When the class is uncertain between `none` and one of the other two, the stricter class is chosen and the intake is downgraded later, since a filed early warning can be followed by a correction while a missed 24-hour deadline cannot be undone. A class change is recorded with its reason.

## 3. Stage deadlines

Three stages exist: `early_warning`, `notification` and `final`. The admin page shows the three clocks counted from `awareAt`: 24 hours, 72 hours and one month. The CRA and GDPR texts below set the legal deadlines. The one-month clock on the page counts from `awareAt`, which is never later than the CRA deadline for a severe incident (one month after the incident notification is submitted), so it is a safe bound. For an actively exploited vulnerability the final report is due 14 days after a corrective or mitigating measure is available, so its date is set by hand when the fix ships.

| Stage | Actively exploited vulnerability (Art. 14(2)) | Severe incident (Art. 14(4)) | GDPR Art. 33 |
|---|---|---|---|
| `early_warning` | within 24 hours of awareness, (a) | within 24 hours of awareness, (a) | not separate |
| `notification` | within 72 hours of awareness, (b) | within 72 hours of awareness, (b) | within 72 hours of awareness, Art. 33(1), when personal data is affected |
| `final` | no later than 14 days after a corrective or mitigating measure is available, (c) | within one month after the submission of the incident notification, (c) | phases allowed, Art. 33(4) |

## 4. Quoted text

### CRA Art. 14, notification duties

Source: <https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng>, Article 14 "Reporting obligations of manufacturers".

> 1. A manufacturer shall notify any actively exploited vulnerability contained in the product with digital elements that it becomes aware of simultaneously to the CSIRT designated as coordinator, in accordance with paragraph 7 of this Article, and to ENISA. The manufacturer shall notify that actively exploited vulnerability via the single reporting platform established pursuant to Article 16.
>
> 2. For the purposes of the notification referred to in paragraph 1, the manufacturer shall submit:
>
> (a) an early warning notification of an actively exploited vulnerability, without undue delay and in any event within 24 hours of the manufacturer becoming aware of it, indicating, where applicable, the Member States on the territory of which the manufacturer is aware that their product with digital elements has been made available;
>
> (b) unless the relevant information has already been provided, a vulnerability notification, without undue delay and in any event within 72 hours of the manufacturer becoming aware of the actively exploited vulnerability, which shall provide general information, as available, about the product with digital elements concerned, the general nature of the exploit and of the vulnerability concerned as well as any corrective or mitigating measures taken, and corrective or mitigating measures that users can take, and which shall also indicate, where applicable, how sensitive the manufacturer considers the notified information to be;
>
> (c) unless the relevant information has already been provided, a final report, no later than 14 days after a corrective or mitigating measure is available, including at least the following:
>
> (i) a description of the vulnerability, including its severity and impact;
>
> (ii) where available, information concerning any malicious actor that has exploited or that is exploiting the vulnerability;
>
> (iii) details about the security update or other corrective measures that have been made available to remedy the vulnerability.
>
> 3. A manufacturer shall notify any severe incident having an impact on the security of the product with digital elements that it becomes aware of simultaneously to the CSIRT designated as coordinator, in accordance with paragraph 7 of this Article, and to ENISA. The manufacturer shall notify that incident via the single reporting platform established pursuant to Article 16.
>
> 4. For the purposes of the notification referred to in paragraph 3, the manufacturer shall submit:
>
> (a) an early warning notification of a severe incident having an impact on the security of the product with digital elements, without undue delay and in any event within 24 hours of the manufacturer becoming aware of it, including at least whether the incident is suspected of being caused by unlawful or malicious acts, which shall also indicate, where applicable, the Member States on the territory of which the manufacturer is aware that their product with digital elements has been made available;
>
> (b) unless the relevant information has already been provided, an incident notification, without undue delay and in any event within 72 hours of the manufacturer becoming aware of the incident, which shall provide general information, where available, about the nature of the incident, an initial assessment of the incident, as well as any corrective or mitigating measures taken, and corrective or mitigating measures that users can take, and which shall also indicate, where applicable, how sensitive the manufacturer considers the notified information to be;
>
> (c) unless the relevant information has already been provided, a final report, within one month after the submission of the incident notification under point (b), including at least the following:
>
> (i) a detailed description of the incident, including its severity and impact;
>
> (ii) the type of threat or root cause that is likely to have triggered the incident;
>
> (iii) applied and ongoing mitigation measures.
>
> 5. For the purposes of paragraph 3, an incident having an impact on the security of the product with digital elements shall be considered to be severe where:
>
> (a) it negatively affects or is capable of negatively affecting the ability of a product with digital elements to protect the availability, authenticity, integrity or confidentiality of sensitive or important data or functions; or
>
> (b) it has led or is capable of leading to the introduction or execution of malicious code in a product with digital elements or in the network and information systems of a user of the product with digital elements.

Paragraph 8 adds the duty toward users: "After becoming aware of an actively exploited vulnerability or a severe incident having an impact on the security of the product with digital elements, the manufacturer shall inform the impacted users of the product with digital elements, and where appropriate all users, of that vulnerability or incident and, where necessary, of any risk mitigation and corrective measures that the users can deploy to mitigate the impact of that vulnerability or incident, where appropriate in a structured, machine-readable format that is easily automatically processable." The staged customer notice with its STIX 2.1 bundle is that duty's implementation.

Paragraph 7 sets the destination: the notification is "submitted via the single reporting platform referred to in Article 16 using one of the electronic notification end-points referred to in Article 16(1)", through the end-point of "the CSIRT designated as coordinator of the Member State where the manufacturers have their main establishment in the Union", and "shall be simultaneously accessible to ENISA".

### GDPR Art. 33(3) and 33(4)

Source: <https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng>, Article 33 "Notification of a personal data breach to the supervisory authority".

> 3. The notification referred to in paragraph 1 shall at least:
>
> (a) describe the nature of the personal data breach including where possible, the categories and approximate number of data subjects concerned and the categories and approximate number of personal data records concerned;
>
> (b) communicate the name and contact details of the data protection officer or other contact point where more information can be obtained;
>
> (c) describe the likely consequences of the personal data breach;
>
> (d) describe the measures taken or proposed to be taken by the controller to address the personal data breach, including, where appropriate, measures to mitigate its possible adverse effects.
>
> 4. Where, and in so far as, it is not possible to provide the information at the same time, the information may be provided in phases without undue further delay.

For context, Art. 33(1) sets the 72-hour limit: "the controller shall without undue delay and, where feasible, not later than 72 hours after having become aware of it, notify the personal data breach to the supervisory authority competent in accordance with Article 55, unless the personal data breach is unlikely to result in a risk to the rights and freedoms of natural persons. Where the notification to the supervisory authority is not made within 72 hours, it shall be accompanied by reasons for the delay." Art. 33(2) obliges a processor to notify the controller "without undue delay". Where Rediacc acts as a processor for a customer's data, the staged customer notice serves Art. 33(2), and the customer files toward its own supervisory authority.

## 5. Procedure

1. Open the intake, set `awareAt` and `craClass` (sections 1 and 2).
2. Pick the affected organizations and write the `early_warning` stage fields. The four Art. 33(3) fields (nature with categories and approximate counts, contact point, likely consequences, measures taken or proposed) are mandatory on every stage, and the stage is published as soon as they are filled, not when everything is known. Art. 33(4) admits phases.
3. Publish the stage. The notice and mail go to owners, admins and the org security contact of each affected organization, ignoring email preferences.
4. Export the stage for ENISA: `GET /admin/security-incidents/:id/cra-export?stage=<stage>` emits the stage fields mapped to the Art. 14 report contents.
5. File the export manually on the single reporting platform (Art. 16), through the end-point named in Art. 14(7). Record the filing time and the platform's reference on the stage (`enisaFiledAt` and the reference field). A stage without both is not closed.
6. Repeat for `notification` and `final`. For an actively exploited vulnerability the `final` date is set when the corrective measure ships (14 days). For a severe incident it is one month after the `notification` was submitted. A CSIRT's request for an intermediate report (Art. 14(6)) is answered as an extra stage entry.
7. Close the incident only when every stage is published, filed and referenced, and the root cause is recorded.

## 6. Records

Everything the intake produces is evidence: the audit trail of `awareAt` and class changes, each stage's fields, the exported JSON as filed, the STIX bundle sent to customers, and the platform reference. Records are kept with the incident and are never edited after filing. A correction is a new stage entry that cites the earlier one.

## 7. Contact

Inbound reports arrive at security@rediacc.com and are described on the public disclosure policy and incident-response pages (`security-disclosure-policy`, `security-incident-response`). The `security.txt` file at `/.well-known/security.txt` points reporters there.
