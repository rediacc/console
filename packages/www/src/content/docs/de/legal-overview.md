---
title: "Compliance-Übersicht"
description: "Wie die Self-Hosted-Architektur von Rediacc Anforderungen an Datenschutz, Privatsphäre und Sicherheits-Compliance erfüllt."
category: "Legal"
order: 0
language: de
sourceHash: "e20385eb9adfe180"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Rediacc läuft vollständig auf Ihrer Infrastruktur. Während Umgebungskloning-, Backup- und Deployment-Operationen verlassen Daten niemals Ihre Maschine. Sie bleiben sowohl der Datenverantwortliche als auch der Auftragsverarbeiter. Kein Drittanbieter-SaaS verarbeitet Ihre Daten.

Dieser Abschnitt ordnet die technischen Fähigkeiten von Rediacc den Anforderungen wichtiger Compliance-Frameworks zu. Jede Seite behandelt eine spezifische Verordnung mit Verweisen auf Artikelebene zu den offiziellen Rechtstexten.

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
| [Datenhoheit](/de/docs/legal-data-sovereignty) | Globale Datenresidenzgesetze (PIPL, LGPD, KVKK, PIPA und weitere) | Self-Hosted = Daten verlassen nie Ihre Jurisdiktion. Keine grenzüberschreitenden Transfers, keine Angemessenheitsbewertungen |

## Architektonische Grundlagen

Jedes Compliance-Framework in diesem Abschnitt verweist auf dieselben technischen Eigenschaften:

- **Verschlüsselung im Ruhezustand**: Jedes Repository ist mit LUKS2 AES-256 verschlüsselt. Anmeldedaten werden ausschließlich in der lokalen Konfiguration des Operators gespeichert, niemals auf dem Server.
- **Netzwerkisolation**: Jedes Repository erhält seinen eigenen Docker Daemon, ein Loopback-IP-Subnetz (/26) und iptables-Regeln. Container verschiedener Repositories können nicht miteinander kommunizieren.
- **Copy-on-Write-Kloning**: `rdc repo fork` verwendet Dateisystem-Reflinks (`cp --reflink=always`). Daten werden auf derselben Maschine dupliziert, ohne Netzwerktransfer.
- **Audit-Logging**: Über 40 Ereignistypen, die Authentifizierung (Login, 2FA, Passwortänderungen, Sitzungswiderruf), API-Token-Lebenszyklus, Config-Store-Operationen und Abonnement-/Lizenzaktivitäten abdecken. Zugänglich über das Admin-Dashboard und `rdc audit` CLI. Operationen auf Maschinenebene (Fork, Backup, Deploy) werden auf der Maschine selbst über SSH und Systemlogs durchgeführt.
- **Verschlüsseltes Backup**: `rdc repo push/pull` überträgt Daten über SSH. Das Backup-Ziel empfängt LUKS-verschlüsselte Volumes.
- **Zero-Knowledge-Config-Store**: Optionale verschlüsselte Config-Synchronisation über Geräte hinweg. Configs werden clientseitig mit AES-256-GCM vor dem Upload verschlüsselt. Der Server speichert nur opake Blobs. Der Server kann keine SSH-Schlüssel, Anmeldedaten, IP-Adressen oder Klartext-Konfigurationsdaten lesen. Die Schlüsselableitung verwendet passkey PRF extension + HKDF mit Domain-Separation. Mitgliederzugang wird über X25519-Schlüsselaustausch verwaltet, und der Widerruf ist sofort wirksam.

Weitere Details zu diesen Fähigkeiten finden Sie unter [Architektur](/de/docs/architecture), [Repositories](/de/docs/repositories), [Config Storage](/de/docs/config-storage) und [Kontosicherheit](/de/docs/account-security).

## Warum es wichtig ist

Compliance-Verstöße sind kostspielig. Diese Durchsetzungsfälle betrafen Probleme, die Rediacc's Architektur strukturell verhindert:

| Vorfall | Strafe | Was schiefging |
|---------|--------|----------------|
| [Meta: EU-US-Datentransfers](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 1,2 Mrd. EUR | Personenbezogene Daten wurden ohne ausreichende Schutzmaßnahmen über Grenzen hinweg übertragen. Self-Hosted bedeutet keinen Transfer. |
| [Equifax: unverschlüsselte Daten](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 700 Mio. USD | 147 Millionen Datensätze unverschlüsselt gespeichert mit schlechter Netzwerksegmentierung. LUKS2 ist obligatorisch, nicht optional. |
| [Target: laterale Bewegung](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 18,5 Mio. USD | Angreifer wechselten von einem HVAC-Lieferanten zu Zahlungssystemen über ein flaches Netzwerk. Repository-Isolation verhindert dies. |
| [Anthem: unverschlüsselte PHI](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 16 Mio. USD | 79 Millionen Gesundheitsdatensätze ohne Verschlüsselung gespeichert. LUKS2 AES-256 ist immer aktiv. |
| [Blackbaud: SaaS-Breach-Kaskade](https://www.sec.gov/newsroom/press-releases/2023-48) | 49,5 Mio. USD | Ransomware bei einem SaaS-Anbieter legte Daten von über 13.000 Kundenorganisationen offen. Self-Hosted bedeutet, dass ein Anbieter-Breach Ihre Daten nicht erreichen kann. |
| [British Airways: schlechte Segmentierung](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 20 Mio. GBP | Angreifer injizierten Schadcode aufgrund unzureichender Netzwerkkontrollen. Isolierte Docker Daemons und iptables verhindern lateralen Zugriff. |
| [Google: Recht auf Löschung](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 50 Mio. EUR | Schwierigkeit, Daten vollständig über verteilte Systeme zu löschen. Kryptographische Löschung via LUKS-Destroy ist sofort und vollständig. |

## Wichtiger Hinweis

Diese Seiten beschreiben die technischen Fähigkeiten von Rediacc in Bezug auf Compliance-Anforderungen. Die Einhaltung jeder Verordnung erfordert organisatorische Richtlinien, Verfahren, Mitarbeiterschulungen und möglicherweise Drittanbieter-Audits, die über den Umfang eines einzelnen Tools hinausgehen. Konsultieren Sie Ihr Rechts- und Compliance-Team für organisationsspezifische Beratung.
