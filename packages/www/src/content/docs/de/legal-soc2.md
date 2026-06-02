---
title: "SOC 2-Konformität"
description: "Wo Rediacc Ihnen SOC 2-Nachweise liefert: die Logs, den Änderungsmanagement-Trail und die Controls, nach denen Auditoren fragen."
category: "Legal"
order: 2
language: de
sourceHash: "29b0c745e631e4f8"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

SOC 2 ist das AICPA-Framework, das Auditoren heranziehen, wenn sie Nachweise dafür wollen, dass Ihre Controls tatsächlich funktionieren. Es umfasst fünf Trust Service Criteria: Sicherheit, Verfügbarkeit, Verarbeitungsintegrität, Vertraulichkeit und Datenschutz.

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

Rediacc protokolliert über 40 Ereignistypen auf Kontoebene:

- **Authentifizierung**: Login, Logout, Passwortänderungen, 2FA-Aktivierung/-Deaktivierung, Sitzungswiderruf
- **Autorisierung**: API-Token-Erstellung/-Widerruf, Rollenänderungen, Teammitgliedschaft
- **Konfiguration**: Config-Store-Push/Pull, Mitgliederverwaltung, Zugriffsfehler (IP-Mismatch, SDK-Verweigerung)
- **Lizenzierung**: Maschinenaktivierung, Lizenzausstellung, Abonnementänderungen

Diese Logs sind über das Admin-Dashboard (mit Filterung nach Benutzer, Team und Datum) und `rdc audit` CLI für programmatischen Export zugänglich. Operationen auf Maschinenebene (Fork, Backup, Deploy) werden über SSH auf Ihrer Infrastruktur ausgeführt, sodass diese Audit-Trails in Ihren Systemlogs liegen.

## Änderungsmanagement

Forks machen das Änderungsmanagement auditierbar: Jeder Fork ist eine Kopie des Live-Zustands, gegen die getestet, überprüft und entweder hochgestuft oder verworfen werden kann, wobei jeder Schritt mit Zeitstempel und Akteuridentifikation protokolliert wird.

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
