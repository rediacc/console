---
title: "HIPAA-Konformität"
description: "Wie die Verschlüsselungs- und Isolationsarchitektur von Rediacc den HIPAA-Schutzanforderungen für Gesundheitsinformationen entspricht."
category: "Legal"
order: 3
language: de
sourceHash: "13bf006e6e3d481f"
---

Der Health Insurance Portability and Accountability Act (HIPAA) ist ein US-amerikanisches Bundesgesetz, das Standards zum Schutz sensibler Gesundheitsinformationen von Patienten (PHI) festlegt. Es gilt für betroffene Einrichtungen (Gesundheitsdienstleister, Krankenversicherungen, Clearingstellen) und deren Geschäftspartner.

Volltext: [Public Law 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## Schutzmaßnahmen-Zuordnung

HIPAA erfordert administrative, technische und physische Schutzmaßnahmen. Die folgende Tabelle ordnet diese den Fähigkeiten von Rediacc zu.

### Technische Schutzmaßnahmen

| Anforderung | HIPAA-Referenz | Rediacc-Fähigkeit |
|-------------|----------------|-------------------|
| Zugriffskontrolle | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | SSH-Schlüssel-basierte Authentifizierung. API-Tokens mit IP-Bindung und Bereichseinschränkungen. Docker-Daemon-Isolation pro Repository verhindert repositoryübergreifenden Zugriff. |
| Audit-Kontrollen | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Über 40 Ereignistypen auf Kontoebene für Authentifizierung, API-Tokens, Config-Operationen und Lizenzierung. Nachverfolgung pro Benutzer und Team. Export über Admin-Dashboard oder `rdc audit` CLI. |
| Integritätskontrollen | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | CoW-Snapshots bewahren Originaldaten vor Änderungen. `rdc repo validate` überprüft Repository-Integrität und Backup-Gesundheit (LUKS-Container, Dateisystemkonsistenz, Konfiguration). |
| Verschlüsselung im Ruhezustand | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | LUKS2 AES-256-Verschlüsselung auf allen Repository-Volumes. Anmeldedaten werden nur in der lokalen Konfiguration des Operators gespeichert, nie auf dem Server. Config Store verwendet Zero-Knowledge AES-256-GCM-Verschlüsselung mit Split-Key-Ableitung. Selbst der Server kann gespeicherte Configs nicht entschlüsseln. |
| Übertragungssicherheit | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Alle Remote-Operationen verwenden SSH. Backup-Transport ist Ende-zu-Ende verschlüsselt. Kein unverschlüsselter Datentransfer. |

### Administrative Schutzmaßnahmen

| Anforderung | Rediacc-Fähigkeit |
|-------------|-------------------|
| Zugriffsverwaltung für Mitarbeiter | API-Tokens mit bereichsbezogenen Berechtigungen. Teambasierte Zugriffskontrolle. Automatischer Token-Widerruf bei Team-Entfernung. |
| Sicherheitsvorfallverfahren | Audit-Logs bieten forensischen Trail aller Operationen. Repository-Isolation begrenzt den Wirkungsradius. |
| Notfallplanung | `rdc repo backup push/pull` unterstützt verschlüsselte Multi-Destination-Backups. CoW-Snapshots ermöglichen sofortige Wiederherstellung. |

### Physische Schutzmaßnahmen

| Anforderung | Rediacc-Fähigkeit |
|-------------|-------------------|
| Zugangskontrollen für Einrichtungen | Self-Hosted: Ihre Organisation kontrolliert die physische Sicherheit Ihrer Server. Keine Abhängigkeit von Drittanbieter-Rechenzentren für Kernoperationen. |
| Workstation-Sicherheit | LUKS verschlüsselt alle Daten im Ruhezustand. Nicht gemountete Repositories sind verschlüsselte Blobs auf der Festplatte, ohne die Anmeldedaten des Operators nicht lesbar. |

## Geschäftspartnervereinbarung (BAA)

Da Rediacc eine Self-Hosted-Software ist, die auf Ihrer Infrastruktur läuft, verarbeitet, speichert oder überträgt es keine PHI über die Systeme von Rediacc (dem Unternehmen). Die typische BAA-Anforderung gilt für Ihren Infrastrukturanbieter (Cloud-Anbieter oder Colocation-Einrichtung), nicht für Rediacc.

Rediacc funktioniert als Software-Tool auf Ihren Servern, ähnlich einem Betriebssystem oder einer Datenbank-Engine. Es hat keinen Zugriff auf Ihre Daten. Der optionale Config Store synchronisiert verschlüsselte Blobs über Rediacc's Server, aber sein Zero-Knowledge-Design bedeutet, dass der Server die Inhalte nicht entschlüsseln kann. Er speichert nur opaken Chiffretext.

## Entwicklungsumgebungen mit PHI

Beim Klonen von Produktionsumgebungen, die PHI enthalten, für Entwicklungszwecke verwenden Sie den Rediaccfile-`up()`-Lebenszyklus-Hook, um Bereinigungsskripte auszuführen, die:

- PHI aus Datenbanktabellen entfernen
- Patientenidentifikatoren durch synthetische Daten ersetzen
- Sitzungstoken und API-Schlüssel entfernen

Entwickler erhalten produktionsnahe Infrastruktur mit de-identifizierten Daten und erfüllen damit den HIPAA-Grundsatz des Minimalbedarfs.
