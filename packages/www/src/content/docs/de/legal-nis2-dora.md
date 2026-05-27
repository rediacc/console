---
title: "NIS2 und DORA"
description: "Wie Rediacc die Anforderungen der EU NIS2-Cybersicherheitsrichtlinie und der DORA-Verordnung zur digitalen operationellen Resilienz erfüllt."
category: "Legal"
order: 8
language: de
sourceHash: "a2078388f7ae1906"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

NIS2 und DORA sind EU-Verordnungen, die Cybersicherheits- und operationelle Resilienzanforderungen an kritische Infrastruktur- und Finanzsektor-Organisationen stellen. Beide traten 2025 in Kraft und gelten breit über EU-Branchen hinweg.

## NIS2-Richtlinie

Die Richtlinie zur Netz- und Informationssicherheit 2 (NIS2) legt Cybersicherheitsanforderungen für "wesentliche" und "wichtige" Einrichtungen in Sektoren wie Energie, Verkehr, Gesundheit, digitale Infrastruktur und öffentliche Verwaltung fest.

Volltext: [Richtlinie (EU) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### NIS2-Anforderungszuordnung

| NIS2-Anforderung | Rediacc-Fähigkeit |
|-----------------|-------------------|
| Risikomanagement-Maßnahmen (Art. 21) | LUKS2-Verschlüsselung im Ruhezustand, Netzwerkisolation pro Repository, ausschließlicher SSH-Zugang, Audit-Logging auf Kontoebene (40+ Ereignistypen) |
| Vorfallsbehandlung (Art. 21(2)(b)) | 40+ Ereignistypen auf Kontoebene (Auth, Tokens, Config, Lizenzierung) bieten forensischen Trail. Repository-Isolation begrenzt den Wirkungsradius. |
| Geschäftskontinuität (Art. 21(2)(c)) | `rdc repo push/pull` mit verschlüsseltem Multi-Destination-Backup. CoW-Snapshots für sofortiges Rollback. |
| Lieferkettensicherheit (Art. 21(2)(d)) | Self-Hosting eliminiert SaaS-Lieferkettenrisiken. Kein Drittanbieter-Cloud-Provider verarbeitet Ihre Daten. |
| Netzwerksicherheit (Art. 21(2)(e)) | Pro-Repository Docker Daemons, iptables-Regeln, Loopback-IP-Isolation (/26-Subnetze). |
| Verschlüsselung (Art. 21(2)(h)) | Obligatorische LUKS2 AES-256-Verschlüsselung. Zero-Knowledge-Config-Store mit AES-256-GCM. |
| Zugangskontrolle (Art. 21(2)(i)) | SSH-Schlüssel-Authentifizierung, bereichsbezogene API-Tokens mit IP-Bindung, Zwei-Faktor-Authentifizierung (TOTP). |
| Vorfallsmeldung, 24h-Frühwarnung (Art. 23) | Audit-Logging ermöglicht schnelle Vorfallserkennung und -eingrenzung. |

### Lieferkettenrisiko

Lieferkettensicherheit ist ein zentrales NIS2-Anliegen (Art. 21(2)(d)). Organisationen müssen Risiken ihrer ICT-Dienstleister und Lieferanten bewerten und managen.

Self-Hosted Rediacc entfernt die größte Lieferketten-Angriffsfläche: Kein Drittanbieter-SaaS verarbeitet Ihre Daten, kein Cloud-Provider hat logischen Zugang zu Ihrer Infrastruktur, und keine Multi-Tenant-Umgebung setzt Sie der Sicherheitslage anderer Kunden aus. SaaS-Anbieter-Breaches haben kaskadierende Schäden über Tausende von Organisationen verursacht. [Blackbauds Ransomware-Angriff 2020 legte Daten von über 13.000 Kundenorganisationen offen und kostete 49,5 Millionen Dollar an Vergleichen.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (Digital Operational Resilience Act)

DORA legt Anforderungen für ICT-Risikomanagement, Vorfallsmeldung, Resilienztests und Drittanbieter-Risikomanagement für den EU-Finanzsektor fest. Es gilt für Banken, Versicherungen, Investmentfirmen, Krypto-Asset-Dienstleister und deren kritische ICT-Drittanbieter.

Volltext: [Verordnung (EU) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### DORA-Anforderungszuordnung

| DORA-Anforderung | Rediacc-Fähigkeit |
|-----------------|-------------------|
| ICT-Risikomanagement-Framework (Art. 6) | Verschlüsselung, Isolation, Audit-Logging und Backup bilden die technische Kontrollschicht. |
| Schutz und Prävention (Art. 9) | LUKS2 AES-256-Verschlüsselung im Ruhezustand. Netzwerkisolation verhindert laterale Bewegung. Ausschließlicher SSH-Zugang. |
| Erkennung (Art. 10) | 40+ Ereignistypen auf Kontoebene. Admin-Dashboard mit Filterung pro Benutzer und Team. Maschinenoperationen über SSH und Systemlogs auditierbar. |
| Reaktion und Wiederherstellung (Art. 11) | CoW-Snapshots für sofortiges Rollback. `rdc repo push/pull` für Multi-Destination-Recovery. Fork-basierte Disaster-Recovery-Tests. |
| ICT-Drittanbieter-Risiko (Art. 28-30) | Self-Hosting eliminiert die Klassifikation als "kritischer ICT-Drittanbieter" vollständig. |
| Digitale operationelle Resilienztests (Art. 24-27) | CoW-Kloning ermöglicht bedrohungsgeleitete Penetrationstests auf produktionsnahen Umgebungen ohne Datenexposition. Klonen, testen, zerstören. |

### ICT-Drittanbieter-Risiko

DODAs aufwändigste Anforderungen betreffen das Management kritischer ICT-Drittanbieter (Art. 28-30). Finanzinstitute müssen Register von ICT-Anbietern führen, Risikobewertungen durchführen, spezifische Vertragsklauseln verhandeln und Exit-Strategien planen.

Self-Hosted Rediacc vermeidet dies vollständig. Kein ICT-Drittanbieter zu registrieren, zu bewerten oder zu überwachen. Das Finanzinstitut kontrolliert seine eigene Infrastruktur direkt.

### Resilienztests

DORA schreibt digitale operationelle Resilienztests vor, einschließlich bedrohungsgeleiteter Penetrationstests (TLPT) für große Institute (Art. 26). CoW-Kloning behandelt dies direkt:

1. Produktionsumgebung forken (sofort, gleiche Maschine, kein Datentransfer)
2. Penetrationstests gegen den Fork ausführen
3. Fork nach Abschluss zerstören

Produktion wird nie berührt, doch die Testumgebung ist eine exakte Replik. Keine Daten verlassen die Maschine.
