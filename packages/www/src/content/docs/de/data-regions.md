---
title: "Datenregionen"
description: "Wo Daten gespeichert werden und wie regionale Datenhaltung für Compliance-Anforderungen funktioniert."
category: "Concepts"
order: 3
language: de
sourceHash: "107d8ef496686b0e"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Bei der Erstellung eines Rediacc-Kontos wird eine Datenregion gewählt. Alle Daten verbleiben in dieser Region. Diese Entscheidung ist dauerhaft und kann nach der Registrierung nicht mehr geändert werden.

## Verfügbare Regionen

| Region | Standort | Domain |
|---|---|---|
| **Europa (EU)** | Frankfurt, Deutschland | `eu.rediacc.com` |
| **Vereinigte Staaten (US)** | Virginia, USA | `us.rediacc.com` |
| **Asien-Pazifik** | Tokio, Japan | `asia.rediacc.com` |

Die Region wird bei der Registrierung automatisch anhand der Zeitzone erkannt. Der Vorschlag kann im Regionenauswahlfeld überschrieben werden.

## Was in der Region verbleibt

Diese Datentypen werden ausschließlich in der gewählten Region gespeichert und verarbeitet:

- **Kontodaten**: E-Mail, Name, Organisation, Teammitgliedschaften
- **Abrechnungs- und Abonnementdatensätze**: Plan, Aktivierungen, Lizenzausstellungen
- **Verschlüsselte Konfigurationsblobs**: Zero-Knowledge-verschlüsselt, clientseitig. Der Server kann sie nicht entschlüsseln.
- **Transaktions-E-Mails**: Passwortzurücksetzungen, Magic-Links, Benachrichtigungen. Werden von einem regionalen E-Mail-Endpunkt gesendet.

## Was global ist

Folgendes ist nicht regionsspezifisch:

- **CLI-Release-Artefakte**: Öffentliche Binärdateien, gehostet auf einem globalen CDN
- **Marketing-Website**: Global von Edge-Standorten bereitgestellt
- **Stripe-Zahlungsabwicklung**: Von Stripes eigener Infrastruktur im Rahmen ihrer Datenverarbeitungsvereinbarung abgewickelt

## Regionale Infrastruktur

| Komponente | EU | US | Asien |
|---|---|---|---|
| Datenbank (D1) | Osteuropa (EEUR) | Ostnordamerika (ENAM) | Asien-Pazifik (APAC) |
| Konfigurationsspeicher (R2) | EU-Jurisdiktion | US | Asien-Pazifik |
| E-Mail (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Tokio (ap-northeast-1) |

Jede Region betreibt unabhängige Infrastruktur. Es gibt keine regionsübergreifenden Abfragen oder Datenflüsse zwischen Regionen.

## EU-Datengarantien

Die EU-Region bietet zusätzliche Garantien für Organisationen mit europäischen Datenhaltungsanforderungen:

- **D1-Datenbank**: läuft in Osteuropa (EEUR-Standorthinweis)
- **R2-Konfigurationsspeicher**: verwendet EU-Jurisdiktionsdurchsetzung (vertragliche Garantie, nicht nur ein Standorthinweis)
- **E-Mail**: gesendet aus Frankfurt (eu-central-1)
- **EU-Japan gegenseitiger Angemessenheitsbeschluss (2019)**: ermöglicht konformen Datenaustausch für die Infrastruktur der Asien-Region

Eine detaillierte DSGVO-Zuordnung findet sich unter [DSGVO-Compliance](/de/docs/legal-gdpr).

## Zero-Knowledge-Verschlüsselung

In R2 gespeicherte Konfigurationsblobs werden clientseitig vor dem Upload mit X25519-Schlüsselaustausch und AES-256-GCM verschlüsselt. Der Server speichert nur Ciphertext. Weder Rediacc noch ein Infrastrukturanbieter können die Konfigurationsdaten lesen.

Schlüssel werden von einem Passkey mit PRF-Erweiterung abgeleitet. Der Server speichert ein serverseitiges Geheimnis, das an der Schlüsselableitung beteiligt ist, aber weder der Passkey allein noch das Servergeheimnis allein können die Daten entschlüsseln.

Details zur Verschlüsselungsarchitektur finden sich unter [Konfigurationsspeicher](/de/docs/config-storage).

## Wie die Wahl treffen

- **Die dem Standort nächste Region wählen** für die geringste Latenz.
- **Die von der Organisation geforderte Region wählen** aus Compliance-Gründen. Wenn das Unternehmen EU-Datenhaltung vorschreibt, EU wählen.
- **Die Wahl ist dauerhaft.** Das Konto kann nach der Registrierung nicht in eine andere Region verschoben werden.

## Für Compliance-Beauftragte

Technische Eigenschaften der regionalen Architektur:

- **Separate Datenbanken pro Region**: Jede Region hat ihre eigene Cloudflare-D1-Datenbank. Keine regionsübergreifenden Abfragen.
- **Separater Speicher pro Region**: Jede Region hat ihren eigenen R2-Bucket. EU verwendet Jurisdiktionsdurchsetzung.
- **Separate E-Mail-Endpunkte pro Region**: Transaktions-E-Mails werden von regionalen AWS-SES-Endpunkten gesendet.
- **Ein Benutzer, eine Region**: Ein Benutzerkonto existiert in genau einer Region. Es kann keine mehreren Regionen umfassen.
- **Webhook-Isolation**: Stripe-Webhook-Ereignisse werden von allen regionalen Workern empfangen, aber nur von der Region verarbeitet, der der Kundendatensatz gehört.
- **Zero-Knowledge-Konfigurationsverschlüsselung**: Der Server kann keine Konfigurationsdaten lesen. Verschlüsselungsschlüssel verlassen das Client-Gerät nie.

Eine umfassendere Sicht auf die Compliance im Bereich Datensouveränität findet sich unter [Datensouveränität](/de/docs/legal-data-sovereignty).
