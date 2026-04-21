---
title: "ISO 27001-Konformität"
description: "Wie Rediacc den Informationssicherheitskontrollen von ISO 27001 für Verschlüsselung, Zugangsverwaltung und Betriebssicherheit entspricht."
category: "Legal"
order: 5
language: de
sourceHash: "fa8c17a9c2914241"
---

ISO/IEC 27001 ist ein internationaler Standard für Informationssicherheits-Managementsysteme (ISMS), veröffentlicht von der Internationalen Organisation für Normung (ISO) und der Internationalen Elektrotechnischen Kommission (IEC). Die aktuelle Version ist ISO/IEC 27001:2022.

Referenz: [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Rediacc ist eine Komponente der technischen Kontrollschicht innerhalb eines ISMS. Die folgende Tabelle ordnet die Fähigkeiten von Rediacc den relevanten Kontrolldomänen des Annex A zu.

## Annex A Kontrollen-Zuordnung

| Kontrolldomäne | Kontrolle | Rediacc-Fähigkeit |
|----------------|-----------|-------------------|
| **A.8**, Asset-Management | A.8.1 Inventar der Assets | Jedes Repository ist ein diskretes, identifizierbares Asset mit einer einzigartigen GUID. `rdc machine query --name <machine> --repositories` listet alle Repositories mit Größe, Mount-Status und Container-Anzahl. |
| **A.8**, Asset-Management | A.8.24 Einsatz von Kryptographie | LUKS2 AES-256 obligatorische Verschlüsselung aller Repositories. Key-Management: Anmeldedaten nur in der lokalen Konfiguration des Operators, nie auf dem Server. |
| **A.9**, Zugangskontrolle | A.9.2 Benutzerzugangsverwaltung | SSH-Schlüssel-Authentifizierung. API-Tokens mit IP-Bindung, Team-Scoping und automatischem Widerruf bei Team-Entfernung. Zwei-Faktor-Authentifizierung (TOTP). |
| **A.10**, Kryptographie | A.10.1 Kryptographische Kontrollen | LUKS2 mit konfigurierbaren Schlüsselparametern. Pro-Repository-Verschlüsselungsanmeldedaten. Gesamter Remote-Transport über SSH. Config Store implementiert Zero-Knowledge-Verschlüsselung: AES-256-GCM mit HKDF-Schlüsselableitung, X25519-Mitglieder-Schlüsselaustausch und zeitlich begrenzte SDK-Schlüssel für sofortigen Widerruf. |
| **A.12**, Betriebssicherheit | A.12.3 Backup | `rdc repo backup push/pull` mit verschlüsseltem Offsite-Speicher auf mehrere Ziele (SSH, S3, B2, Azure, GDrive). CoW-Snapshots für Point-in-Time-Recovery. `rdc repo validate` überprüft Backup-Gesundheit und Repository-Integrität. |
| **A.12**, Betriebssicherheit | A.12.4 Protokollierung und Überwachung | Über 40 Ereignistypen auf Kontoebene (Auth, API-Tokens, Config, Lizenzierung). Maschinengesundheitsüberwachung via `rdc machine query`. Container-Status und Ressourcenüberwachung. |
| **A.13**, Kommunikationssicherheit | A.13.1 Netzwerksicherheitsmanagement | Pro-Repository Docker-Daemon-Isolation. iptables-Regeln blockieren repositoryübergreifenden Verkehr. Loopback-IP-Subnetze (/26) pro Repository. Reverse Proxy mit TLS-Terminierung für externen Zugang. |
| **A.14**, Systementwicklung | A.14.2 Sicherheit in der Entwicklung | Fork-basierte Entwicklungsumgebungen bieten Produktionsparität ohne Produktionsdatenexposition. Rediaccfile-Lebenszyklus-Hooks ermöglichen automatisierte Datenbereinigung in geklonten Umgebungen. |

## Asset-Management

Das Repository-Modell von Rediacc unterstützt natürlich die Anforderungen an das Asset-Inventar:

- Jedes Repository hat eine einzigartige GUID, die bei der Erstellung zugewiesen wird
- Repositories sind pro Maschine aufzählbar (`rdc machine query --repositories`)
- Verschlüsselungsstatus, Mount-Status, Container-Anzahl und Festplattennutzung jedes Repositories sind sichtbar
- Fork-Beziehungen verfolgen die Herkunft geklonter Umgebungen

## Änderungsmanagement

Der Fork-Test-Promote-Workflow entspricht den Änderungsmanagement-Anforderungen von ISO 27001:

1. **Fork**: Erstellen einer isolierten Kopie der Produktionsumgebung
2. **Test**: Anwenden und Validieren von Änderungen im Fork
3. **Promote**: `rdc repo takeover` verwenden, um den Fork in die Produktion zu überführen
4. **Audit**: Alle Operationen werden mit Zeitstempel und Akteuridentifikation protokolliert

## Kontinuierliche Verbesserung

- Audit-Log-Export unterstützt regelmäßige Sicherheitsüberprüfungen
- Maschinengesundheitsprüfungen (`rdc machine query --system`) unterstützen Betriebsüberwachung
- `rdc repo validate` überprüft Backup-Gesundheit nach jeder Operation
