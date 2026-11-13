---
title: "Datenregionen"
description: "Wo Ihre Daten gespeichert werden und wie regionale Datenhaltung funktioniert."
category: "Concepts"
tags:
  - compliance
  - account
subcategory: platform
order: 3
language: de
sourceHash: "9efeb1e2b1f9c8db"
sourceCommit: "c477e296238c19495f4a07ef6c5a62f15e942f90"
---

Bei der Anmeldung für Rediacc wählen Sie eine Datenregion. Alle Daten verbleiben in dieser Region. Diese Entscheidung ist dauerhaft und kann nach der Registrierung nicht mehr geändert werden. Es gibt keinen Migrationspfad. Wählen Sie die Region basierend darauf, wo Ihre Daten rechtlich ansässig sein müssen, nicht wo Ihre Server heute sind.

## Verfügbare Regionen

| Region | Standort | Domain |
|---|---|---|
| **Europa (EU)** | Europäische Union | `eu.rediacc.cloud` |
| **Vereinigte Staaten (US)** | Östliches Nordamerika | `us.rediacc.cloud` |
| **Asien-Pazifik** | Asien-Pazifik | `asia.rediacc.cloud` |

Die Spalte Standort nennt eine Cloudflare-Region, keine Rechenzentrumsstadt. Cloudflare sagt keine Stadt zu.

Das Produkt läuft auf diesen `rediacc.cloud`-Domains. Die gesamte Dokumentation und die Marketing-Website liegen auf `www.rediacc.com`, das Sie über die Regionsauswahl zur passenden Region weiterleitet.

Bei der Registrierung schlägt die Auswahl anhand Ihres Standorts eine Region vor, die Sie bestätigen oder ändern. Beim Login leitet sie Sie nach einem kurzen Countdown, den Sie abbrechen oder ändern können, in Ihre Region weiter. Hat Ihr Unternehmen eine eigene Bereitstellung, führt die Option „Enterprise-Kunde?“ Sie anhand Ihrer geschäftlichen E-Mail-Adresse dorthin. Zur Suche der Region wird nur die Domain gesendet; die E-Mail-Adresse füllt lediglich die Anmeldeseite vor.

## Was in der Region verbleibt

Diese Datentypen werden in Ihrer gewählten Region gespeichert und verarbeitet, mit der Ausnahme, dass transaktionale E-Mails für Asien-Pazifik über den EU-Endpunkt versendet werden (was garantiert ist, steht unten unter Regionale Infrastruktur):

- **Kontodaten**: E-Mail, Name, Organisation, Teammitgliedschaften
- **Abrechnungs- und Abonnementdatensätze**: Plan, Aktivierungen, Lizenzausstellungen
- **Verschlüsselte Konfigurationsblobs**: Zero-Knowledge-verschlüsselt, clientseitig. Der Server kann sie nicht entschlüsseln.
- **Transaktions-E-Mails**: Passwortzurücksetzungen, Magic-Links, Benachrichtigungen. Werden von einem regionalen E-Mail-Endpunkt gesendet.

## Was global ist

Folgendes ist nicht regionsspezifisch:

- **CLI-Release-Artefakte**: Öffentliche Binärdateien, gehostet auf einem globalen CDN
- **Marketing-Website und Dokumentation**: `www.rediacc.com`, global von Edge-Standorten bereitgestellt
- **Stripe-Zahlungsabwicklung**: Von Stripes eigener Infrastruktur im Rahmen ihrer Datenverarbeitungsvereinbarung abgewickelt

## Regionale Infrastruktur

| Komponente | EU | US | Asien |
|---|---|---|---|
| Datenbank (D1) | Hinweis Osteuropa (EEUR) | Hinweis Ostnordamerika (ENAM) | Hinweis Asien-Pazifik (APAC) |
| Konfigurationsspeicher (R2) | EU-Jurisdiktion (garantiert) | Keine Jurisdiktion (nach bestem Bemühen) | Keine Jurisdiktion (nach bestem Bemühen) |
| E-Mail (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Frankfurt (eu-central-1) |

Nur der EU-Konfigurationsspeicher unterliegt einer garantierten Jurisdiktion: Cloudflare hält R2-Objekte unter der EU-Jurisdiktion innerhalb der EU. Die Platzierung der D1-Datenbank sowie der Speicher in US und Asien-Pazifik folgen Standorthinweisen, die nach bestem Bemühen berücksichtigt werden. Cloudflare garantiert nicht, dass sie in der angegebenen Region laufen.

Jede Region betreibt unabhängige Infrastruktur. Es gibt keine regionsübergreifenden Abfragen oder Datenflüsse zwischen Regionen.

## EU-Datengarantien

Wenn Sie europäischen Datenresidenzanforderungen unterliegen, bietet die EU-Region eine feste Garantie und eine Platzierung nach bestem Bemühen:

- **D1-Datenbank**: platziert mit dem Standorthinweis EEUR (Osteuropa), nach bestem Bemühen und ohne Garantie
- **R2-Konfigurationsspeicher**: an die EU-Jurisdiktion gebunden, was Cloudflare garantiert (eine feste Beschränkung, nicht nur ein Standorthinweis)
- **E-Mail**: gesendet aus Frankfurt (eu-central-1)

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
- **Separater Speicher pro Region**: Jede Region hat ihren eigenen R2-Bucket. Nur der EU-Bucket ist an eine Jurisdiktion gebunden; US und Asien-Pazifik werden nach bestem Bemühen platziert.
- **E-Mail-Bereitstellung über AWS SES**: Transaktions-E-Mails werden über AWS SES gesendet. EU und US verwenden dedizierte regionale Endpunkte; Asien-Pazifik wird über den EU-Endpunkt (eu-central-1) geroutet.
- **Ein Benutzer, eine Region**: Ein Benutzerkonto existiert in genau einer Region. Es kann keine mehreren Regionen umfassen.
- **Webhook-Isolation**: Stripe-Webhook-Ereignisse werden von allen regionalen Workern empfangen, aber nur von der Region verarbeitet, der der Kundendatensatz gehört.
- **Zero-Knowledge-Konfigurationsverschlüsselung**: Der Server kann keine Konfigurationsdaten lesen. Verschlüsselungsschlüssel verlassen das Client-Gerät nie.

Eine umfassendere Sicht auf die Compliance im Bereich Datensouveränität findet sich unter [Datensouveränität](/de/docs/legal-data-sovereignty).
