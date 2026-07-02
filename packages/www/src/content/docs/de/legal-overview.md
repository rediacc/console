---
title: "Was Compliance wirklich erfordert"
description: "Rediacc läuft auf Ihrer Infrastruktur. Sie kontrollieren Ihre Daten. So stimmt das mit den wichtigsten Compliance-Frameworks überein."
category: "Legal"
order: 0
language: de
sourceHash: "e6044a3b067b54d5"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc läuft vollständig auf Ihrer Infrastruktur. Während Kloning-, Backup- und Deployment-Operationen verlassen Ihre Daten Ihre Maschinen nie. Sie sind sowohl der Verantwortliche als auch der Auftragsverarbeiter. Kein Drittanbieter-SaaS, kein externer Zugriff.

Wir ordnen die technischen Fähigkeiten von Rediacc den Anforderungen wichtiger Compliance-Frameworks zu. Jede Seite behandelt eine spezifische Verordnung mit Verweisen auf die offiziellen Rechtstexte.

## Compliance-Matrix

| Framework | Geltungsbereich | Wichtige Rediacc-Fähigkeiten |
|-----------|----------------|------------------------------|
| [DSGVO](/de/docs/legal-gdpr) | EU-Datenschutz und Privatsphäre | CoW-Kloning auf derselben Maschine, LUKS2-Verschlüsselung, Zero-Knowledge-Config-Store, Audit-Logging, Recht auf Löschung via `rdc repo delete` |
| [SOC 2](/de/docs/legal-soc2) | Trust-Service-Kriterien für Dienstleistungsorganisationen | Verschlüsselung im Ruhezustand, Zero-Knowledge-Config-Sync, Netzwerkisolation, Audit-Trail, Backup und Wiederherstellung |
| [HIPAA](/de/docs/legal-hipaa) | US-Schutz von Gesundheitsinformationen | LUKS2-Verschlüsselung, Zero-Knowledge-Config-Store, ausschließlicher SSH-Zugang, isolierte Docker Daemons, Übertragungssicherheit |
| [CCPA](/de/docs/legal-ccpa) | Datenschutzrechte kalifornischer Verbraucher | Self-Hosted (kein Datenverkauf/-weitergabe), Zero-Knowledge-Verschlüsselung, verschlüsselte Löschung, Dateninventar pro Repository |
| [ISO 27001](/de/docs/legal-iso27001) | Informationssicherheits-Management-Kontrollen | Asset-Management, kryptographische Kontrollen, Zero-Knowledge-Config-Store, Zugriffskontrolle, Betriebssicherheit |
| [PCI DSS](/de/docs/legal-pci-dss) | Schutz von Zahlungskartendaten | Netzwerksegmentierung durch Architektur, obligatorische Verschlüsselung, Audit-Logging, Scope-Reduktion durch Self-Hosting |
| [NIS2 und DORA](/de/docs/legal-nis2-dora) | EU-Cybersicherheit und finanzielle Resilienz | Eliminierung von Lieferkettenrisiken, Resilienztests via CoW-Kloning, Verschlüsselung, Vorfallserkennung |
| [Datenhoheit](/de/docs/legal-data-sovereignty) | Globale Datenresidenzgesetze (PIPL, LGPD, KVKK, PIPA und weitere) | Self-Hosted: Daten verlassen nie Ihre Jurisdiktion. Keine grenzüberschreitenden Transfers, keine Angemessenheitsbewertungen |

## Architektonische Grundlagen

Hier ist, was sie alle verbindet: Jedes Compliance-Framework in diesem Abschnitt leitet sich auf dieselbe technische Grundlage zurück.

- **Verschlüsselung im Ruhezustand**: Jedes Repository ist mit LUKS2 AES-256 verschlüsselt. Anmeldedaten werden ausschließlich in der lokalen Konfiguration des Operators gespeichert, niemals auf dem Server.
- **Netzwerkisolation**: Jedes Repository erhält seinen eigenen Docker Daemon, ein Loopback-IP-Subnetz (/26) und iptables-Regeln. Container verschiedener Repositories können nicht miteinander kommunizieren.
- **Copy-on-Write-Kloning**: `rdc repo fork` verwendet Dateisystem-Reflinks (`cp --reflink=always`). Daten werden auf derselben Maschine dupliziert, ohne Netzwerktransfer.
- **Audit-Logging**: Über 70+ Ereignistypen, die Authentifizierung (Login, 2FA, Passwortänderungen, Sitzungswiderruf), API-Token-Lebenszyklus, Config-Store-Operationen, Abonnement-/Lizenzaktivitäten und CLI-Operationen auf Maschinenebene (Repository-Lebenszyklus, Backup, Synchronisierung, Terminal-Sessions) abdecken. Zugänglich über das Admin-Dashboard und die Portal-Aktivitätsseite (mit organisations-weiter Filterung und JSON-Export). Operationen auf Maschinenebene werden auch in Ihren Systemlogs für vertiefte Verteidigung aufgezeichnet.
- **Verschlüsseltes Backup**: `rdc repo push/pull` überträgt Daten über SSH. Das Backup-Ziel empfängt LUKS-verschlüsselte Volumes.
- **Zero-Knowledge-Config-Store**: Optionale verschlüsselte Config-Synchronisation über Geräte hinweg. Configs werden clientseitig mit AES-256-GCM vor dem Upload verschlüsselt. Der Server speichert nur opake Blobs. Der Server kann keine SSH-Schlüssel, Anmeldedaten, IP-Adressen oder Klartext-Konfigurationsdaten lesen. Die Schlüsselableitung verwendet passkey PRF extension + HKDF mit Domain-Separation. Mitgliederzugang wird über X25519-Schlüsselaustausch verwaltet, und der Widerruf ist sofort wirksam.

Weitere Details zu diesen Fähigkeiten finden Sie unter [Architektur](/de/docs/architecture), [Repositories](/de/docs/repositories), [Config Storage](/de/docs/config-storage) und [Kontosicherheit](/de/docs/account-security).

## Warum es wichtig ist

Compliance-Verstöße sind teuer. Wirklich teuer. Die Fälle unten zeigen Probleme, die Rediacc's Architektur strukturell verhindert:

| Vorfall | Strafe | Was schiefging |
|---------|--------|----------------|
| [Meta: EU-US-Datentransfers](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 1,2 Mrd. EUR | Personenbezogene Daten wurden ohne ausreichende Schutzmaßnahmen über Grenzen hinweg übertragen. Self-Hosted bedeutet keinen Transfer. |
| [Equifax: unverschlüsselte Daten](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 700 Mio. USD | 147 Millionen Datensätze unverschlüsselt gespeichert mit schlechter Netzwerksegmentierung. LUKS2 ist obligatorisch, nicht optional. |
| [Target: laterale Bewegung](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 18,5 Mio. USD | Angreifer wechselten von einem HVAC-Lieferanten zu Zahlungssystemen über ein flaches Netzwerk. Repository-Isolation verhindert dies. |
| [Anthem: unverschlüsselte PHI](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 16 Mio. USD | 79 Millionen Gesundheitsdatensätze ohne Verschlüsselung gespeichert. LUKS2 AES-256 ist immer aktiv. |
| [Blackbaud: SaaS-Breach-Kaskade](https://www.sec.gov/newsroom/press-releases/2023-48) | 49,5 Mio. USD | Ransomware bei einem SaaS-Anbieter legte Daten von über 13.000 Kundenorganisationen offen. Self-Hosted bedeutet, dass ein Anbieter-Breach Ihre Daten nicht erreichen kann. |
| [British Airways: schlechte Segmentierung](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 20 Mio. GBP | Angreifer injizierten Schadcode aufgrund unzureichender Netzwerkkontrollen. Isolierte Docker Daemons und iptables verhindern lateralen Zugriff. |
| [Google: Recht auf Löschung](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 50 Mio. EUR | Schwierigkeit, Daten vollständig über verteilte Systeme zu löschen. Kryptographische Löschung via LUKS destroy ist sofort und vollständig. |

## Wichtiger Hinweis

Diese Seiten erklären, wie Rediacc's Architektur mit Compliance-Anforderungen übereinstimmt. Aber hier ist die Realität: Compliance ist größer als Software. Sie werden Richtlinien, Verfahren, Schulungen und wahrscheinlich Audits durch Dritte benötigen. Rediacc behandelt den Infrastruktur-Teil. Arbeiten Sie mit Ihren Rechts- und Compliance-Teams bei der Bewältigung des Rests zusammen.
