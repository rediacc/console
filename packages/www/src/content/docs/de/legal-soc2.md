---
title: "SOC 2-Konformität"
description: "Das ist der Knackpunkt bei SOC 2: Auditoren brauchen Nachweise, dass Ihre Controls funktionieren. Rediacc liefert Ihnen die Logs, den Änderungsmanagement-Trail und alles andere, das Auditoren fragen werden."
category: "Legal"
order: 2
language: de
sourceHash: "9ba8477a07292a7d"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Ich kenne SOC 2 aus Audit-Meetings. Auditoren nutzen das AICPA-Framework, um zu prüfen, ob Ihre Controls tatsächlich funktionieren, nicht nur, ob Sie behaupten, dass sie funktionieren. Es gibt fünf Trust Service Criteria: Sicherheit, Verfügbarkeit, Verarbeitungsintegrität, Vertraulichkeit und Datenschutz.

Referenz: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Trust Service Criteria Zuordnung

| Trust-Prinzip | Kriterium | Rediacc-Fähigkeit |
|---------------|-----------|-------------------|
| **Sicherheit** (CC6) | Logische Zugriffskontrollen, Verschlüsselung | LUKS2 AES-256-Verschlüsselung im Ruhezustand. Anmeldedaten werden ausschließlich in der lokalen Konfiguration des Operators (`~/.config/rediacc/`) gespeichert, nie auf dem Server. SSH-Schlüssel-basierter Zugang. Isolierte Docker Daemons pro Repository. |
| **Verfügbarkeit** (A1) | Systemwiederherstellung und Resilienz | `rdc repo push/pull` mit verschlüsselten Offsite-Kopien auf SSH, S3, B2, Azure oder GDrive. CoW-Snapshots für sofortiges Rollback. Fork-basierte Upgrades für Änderungen ohne Ausfallzeit. |
| **Verarbeitungsintegrität** (PI1) | Genaue und vollständige Verarbeitung | Deterministische Rediaccfile-Lebenszyklus-Hooks (`up`/`down`) gewährleisten konsistente Deployments. `rdc repo validate` überprüft Repository-Integrität und Backup-Gesundheit nach unerwarteten Abschaltungen oder Backup-Operationen. |
| **Vertraulichkeit** (C1) | Datenschutz vor unbefugtem Zugriff | Pro-Repository-Verschlüsselung mit einzigartigen LUKS-Anmeldedaten. Netzwerkisolation via iptables, separate Docker Daemons und Loopback-IP-Subnetze. Container verschiedener Repositories können sich nicht sehen. Zero-Knowledge-Config-Store verschlüsselt Configs clientseitig vor dem Upload. Der Server speichert nur opake Blobs, die er nicht entschlüsseln kann. |
| **Datenschutz** (P1-P8) | Umgang mit personenbezogenen Daten | Self-Hosted: kein Datenabfluss während Operationen. Audit-Trail für alle Datenzugriffe. Verschlüsselungs-Key-Management unter Kundenkontrollen. Config Store verwendet Split-Key-Ableitung (Passkey PRF + Server-Geheimnis), sodass keine Partei allein Zugang zu den Daten hat. |

## Audit-Trail

Rediacc protokolliert also über 70 verschiedene Ereignistypen. Benutzeraktionen, Systemänderungen, Konfigurationsaktualisierungen, Zugriffskontroll-Modifikationen, Sicherheitsereignisse, Fork-Operationen, Audit-Trails. Das klingt nach viel, aber Auditoren interessieren sich tatsächlich für diese Daten.

- **Authentifizierung**: Login, Logout, Passwortänderungen, 2FA-Aktivierung/-Deaktivierung, Sitzungswiderruf
- **Autorisierung**: API-Token-Erstellung/-Widerruf, Rollenänderungen, Teammitgliedschaft
- **Konfiguration**: Config-Store-Push/Pull, Mitgliederverwaltung, Zugriffsfehler (IP-Mismatch, SDK verweigert)
- **Lizenzierung**: Repository-Lizenzausstellung, Maschinenschlitz-Tracking, Abonnementänderungen
- **Maschinenoperationen**: Repository erstellen/starten/stoppen/löschen, Fork, Backup Push/Pull, Dateisynchronisierung, Terminal-Sitzungen

Es gibt zwei Wege, an diese Logs zu kommen. Admin-Dashboard mit Benutzer-, Team- und Datumsfilter. Portal-Aktivitätsseite für Org-Admins, Typ- und Datumsfilter, mit JSON-Export, den Sie in Ihre eigenen Tools pipen können. Maschinenoperationen protokollieren auch auf Ihren Systemlogs, was eine mehrschichtige Sicherheit bietet.

## Änderungsmanagement

Forks machen Änderungsmanagement auditierbar. Forken Sie Ihre Produktionsumgebung und Sie haben eine Kopie des aktuellen Zustands. Testen Sie diese. Überprüfen Sie sie. Stufen Sie sie hoch oder verwerfen Sie sie. Jeder Schritt wird mit Zeitstempel versehen und an eine Person gebunden. Das ist das, was Auditoren sehen wollen: keine anonymen Änderungen.

1. Produktions-Repository forken (`rdc repo fork`)
2. Änderungen am Fork anwenden und testen
3. Fork unabhängig validieren
4. Fork in Produktion überführen (`rdc repo takeover`)

Jeder Schritt wird mit Zeitstempel und Akteuridentifikation protokolliert.

## Zugriffskontrolle

- **Maschinenzugang**: Ausschließlich SSH-Schlüssel-Authentifizierung. Kein passwortbasiertes SSH.
- **API-Tokens**: Bereichsbezogene Berechtigungen, optionale IP-Bindung, automatischer Widerruf bei Team-Entfernung.
- **Repository-Isolation**: Jedes Repository hat seinen eigenen Docker-Daemon-Socket. Der Zugang zu einem Repository gewährt keinen Zugang zu einem anderen auf derselben Maschine.
- **Config-Store-Tokens**: Rotierende Einmal-Tokens mit IP-Bindung bei erster Nutzung, automatischem 24-Stunden-Ablauf und 3-Request-Toleranzfenster für Nebenläufigkeit. Mitgliederzugang via X25519-Schlüsselaustausch mit sofortigem Widerruf.
