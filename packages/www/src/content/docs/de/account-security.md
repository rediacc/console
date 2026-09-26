---
title: Kontosicherheit & API-Schlüssel
description: Authentifizierung, API-Token-Verwaltung, Sitzungsüberwachung und das Zugriffs- und Berechtigungsmodell für Ihre Organisation.
category: Guides
tags:
  - account
  - security
subcategory: account
order: 13
language: de
sourceHash: "cbfa1730b069f73c"
sourceCommit: "c707ed4d0e178e7c4cec46e5ff989a1472a8eb82"
---

### Authentifizierung

Rediacc unterstützt mehrere Authentifizierungsmethoden:

![Auth Flow](/img/account-auth-flow.svg)

- **Passwort**: Traditionelle Anmeldung mit E-Mail und Passwort
- **Magic Link**: Passwortlose Anmeldung per E-Mail-Link (15 Minuten gültig)
- **Zwei-Faktor-Authentifizierung (2FA)**: TOTP-basiert mit Backup-Codes

Wenn 2FA aktiviert ist, erfordert die Anmeldung sowohl Ihr Passwort (oder Magic Link) als auch einen 6-stelligen TOTP-Code.

### API-Token

API-Token authentifizieren Maschine-zu-Maschine-Operationen (CLI-Lizenzaktivierung, Statusprüfungen).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Bereiche:**
- `license:read` -- Abonnement- und Lizenzstatus abfragen
- `license:activate` -- Maschinen aktivieren und Repository-Lizenzen ausstellen
- `subscription:read` -- Abonnementdetails lesen

**Sicherheitsfunktionen:**
- IP-Bindung: Ein Token gilt nur für die IP-Adresse seiner ersten Anfrage; eine neue Adresse erfordert eine TOTP-Prüfung oder eine neue Anmeldung (siehe unten)
- Team-Einschränkung: Token können auf ein bestimmtes Team beschränkt werden
- Automatischer Widerruf: Token werden widerrufen, wenn der Ersteller aus der Organisation entfernt wird

Token erstellen:
```bash
# Über das Portal: API Tokens > Create
# Der Token-Wert wird nur einmal angezeigt -- sicher aufbewahren
```

#### Wenn sich die IP-Adresse ändert

Ein an eine IP-Adresse gebundener Token wird von jeder anderen Adresse abgelehnt, etwa wenn der Internetanbieter eine neue Adresse vergibt. Die CLI übernimmt die Übertragung:

- **Interaktives Terminal, 2FA aktiv**: Die CLI fragt nach dem 6-stelligen Code aus der Authenticator-App, überträgt den Token auf die neue Adresse und führt den Befehl erneut aus. Backup-Codes werden dafür nicht akzeptiert.
- **Skripte und CI (kein Terminal)**: Der Befehl schlägt fehl und nennt beide Lösungen: einmal einen beliebigen `rdc`-Befehl in einem interaktiven Terminal ausführen (zum Beispiel `rdc subscription status`) und den Code eingeben, oder `rdc subscription login` ausführen.
- **2FA aus**: Der Token lässt sich nicht übertragen. `rdc subscription login` stellt einen neuen aus; mit aktivierter 2FA genügt beim nächsten Mal ein Code.
- **Falsche Codes**: 5 falsche Codes innerhalb von 15 Minuten sperren die Übertragung, zuerst für 5 Minuten, danach jeweils doppelt so lange, höchstens 1 Stunde. Nach 4 Sperren ist die Übertragung für diesen Token abgeschaltet, bis zur nächsten Anmeldung mit `rdc subscription login`.
- **Executor-Token** mit der IP-Bindung `unbound` oder `cloudflare` sind nicht betroffen.

Jede Übertragung erscheint im Aktivitätsprotokoll des Portals, mit der alten und der neuen Adresse.

### Device-Code-Ablauf

Die CLI kann sich auf Headless-Maschinen über den Device-Code-Ablauf authentifizieren:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc subscription login
# Zeigt an: Code XXXX-XXXX-XX eingeben unter https://www.rediacc.com/account/authorize
# Nach Genehmigung erhält die CLI automatisch Zugangsdaten
```

### Config Storage

Für verschlüsselte, serversynchronisierte Konfiguration siehe [Config Storage](/de/docs/config-storage) für die vollständige Anleitung. Config Storage verwendet:
- Zero-Knowledge-Verschlüsselung (Server sieht nie Klartext)
- Passkey-basierte Schlüsselableitung (WebAuthn + PRF)
- Rotierende Token mit Rotation pro Anfrage

### Sitzungssicherheit

| Token-Typ | Lebensdauer | Speicherung | Aktualisierung |
|-----------|-------------|-------------|----------------|
| Access Token (JWT) | 15 Minuten | HttpOnly-Cookie | Automatisch via Refresh Token |
| Refresh Token | 7 Tage | HttpOnly-Cookie | Bei jeder Nutzung rotiert |
| Erhöhte Sitzung | 10 Minuten | Serverseitig | Ausgelöst durch erneute Authentifizierung |

Erhöhte Sitzungen sind erforderlich für sensible Operationen: Passwortänderungen, E-Mail-Änderungen, 2FA-Einrichtung, Eigentumsübertragungen und destruktive Admin-Aktionen.

### Berechtigungsmodell

Rediacc verwendet drei unabhängige Berechtigungsebenen:

![Permission Flow](/img/account-permission-flow.svg)

**Ebene 1: Systemrolle** -- Bestimmt den Zugriff auf Systemadministrations-Endpunkte.

**Ebene 2: Organisationsrolle** -- Steuert, was ein Benutzer innerhalb seiner Organisation tun kann (Owner, Admin, Member).

**Ebene 3: Teamrolle** -- Beschränkt den Zugriff auf bestimmte Team-Ressourcen (team_admin, member). Organisationseigentümer und Admins umgehen Team-Rollenprüfungen.

Jede API-Anfrage durchläuft alle zutreffenden Ebenen nacheinander. Eine Anfrage an einen teamspezifischen Endpunkt muss Sitzungsauthentifizierung, Organisationsmitgliedschaft und Teamzugriff erfüllen.

### Update-Kanäle

Die CLI unterstützt zwei Release-Kanäle:
- **stable** (Standard): Nach 7-tägiger Einlaufphase von Edge befördert; wählen Sie diesen Kanal für eine konservative Update-Kadenz
- **edge**: Neueste Funktionen, bei jedem Release aktualisiert

```bash
rdc update --channel edge      # Zu edge wechseln
rdc update --channel stable    # Zurück zu stable
rdc update --status            # Aktuellen Kanal anzeigen
```

### CLI-Sicherheitshaltung für KI-Agenten

Coding-Agenten, die `rdc` aufrufen, sind eine echte Angriffsfläche, deshalb behandeln wir sie als separaten Principal. Jeder `rdc`-Aufruf wird beim Start als **Mensch** oder **Agent** klassifiziert, basierend auf Umgebungssignalen (CLAUDECODE, GEMINI_CLI, COPILOT_CLI, CURSOR_TRACE_ID, REDIACC_AGENT) plus einem Linux-`/proc`-Abstammungs-Walk. Die Erkennung ist bestmöglich. Ein entschlossener Wrapper kann Umgebungsvariablen fälschen, weshalb die Abstammung wichtig ist. Agenten erhalten ein reduziertes Berechtigungsset: sensible Konfigurations-Mutationen erfordern das Knowledge-Gate (`--current <alt>`), der interaktive Editor wird ohne einen abstammungsverifizierten `REDIACC_ALLOW_CONFIG_EDIT`-Override verweigert, und `--reveal` bei jedem Anzeigebefehl ist gesperrt. Jede Entscheidung (erlauben, verweigern oder `--reveal` gewähren) schreibt eine hash-verkettete JSONL-Zeile in `~/.config/rediacc/audit.log.jsonl`. Führen Sie `rdc config audit verify` aus, um die Kettenintegrität zu prüfen.

Siehe [Sicherheit und Schutzmechanismen für KI-Agenten](/de/docs/ai-agents-safety) für die vollständige Matrix dessen, was Agenten tun und nicht tun können, mit Beispielen zum Knowledge-Gate und Scope-Override-Mechaniken.
