---
title: "Config Storage (Rediacc Provider)"
description: "CLI-Konfiguration sicher geräteübergreifend und im Team synchronisieren mit Zero-Knowledge-Verschlüsselung."
category: "Guides"
order: 9
language: de
---

# Config Storage

Der Rediacc Config Storage Provider synchronisiert Ihre CLI-Konfiguration geräteübergreifend und im Team mit Zero-Knowledge-Verschlüsselung. Ihre SSH-Schlüssel, Maschinen-IPs und Zugangsdaten werden clientseitig verschlüsselt, bevor sie Ihren Rechner verlassen -- selbst Rediacc-Betreiber können Ihre Daten nicht lesen.

## Voraussetzungen

- **Passkey-Anbieter mit PRF-Unterstützung**: Bitwarden, iCloud Keychain oder Windows Hello
- **2FA aktiviert** für Org-Inhaber/Admins (erforderlich für Store-Einrichtung und Mitgliederverwaltung)
- **Account-Abonnement** mit aktiviertem Config Storage

## Schnellstart

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## Einrichtung

### Desktop (mit Browser)

```bash
rdc store add my-config --type rediacc
```

1. Ein Browserfenster öffnet sich zum Rediacc-Kontoportal
2. Registrieren Sie einen Passkey (Bitwarden/iCloud/Windows Hello Popup)
3. Die PRF-Erweiterung des Passkeys leitet Ihre Verschlüsselungsschlüssel ab
4. Schlüssel werden im nativen sicheren Speicher Ihres Betriebssystems gespeichert (Keychain/keyctl/DPAPI)
5. Fertig -- kein Passwort zum Merken

### Headless-Server (kein Browser)

```bash
rdc store add my-config --type rediacc --headless
```

1. CLI zeigt eine URL mit einem Gerätecode an
2. Öffnen Sie die URL auf Ihrem Handy oder Laptop
3. Schließen Sie die Passkey-Registrierung im Browser ab
4. Die CLI empfängt automatisch Ihre verschlüsselten Schlüssel über ein sicheres Relay
5. Zero-Knowledge bleibt erhalten -- der Server leitet nur einen opaken verschlüsselten Blob weiter

### Benutzerdefinierte Server-URL

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

Nach der Einrichtung funktionieren Push und Pull ohne Passwörter oder Eingabeaufforderungen:

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

Jede Operation verwendet einen rotierenden Token, der sich nach einmaliger Verwendung selbst zerstört. Keine statischen Zugangsdaten.

## Teamverwaltung

Teammitglieder werden über das Webportal unter `/account/config-storage/members` verwaltet.

### Mitglieder hinzufügen

1. Admin öffnet die Config Storage Mitgliederseite
2. Klickt auf "Add Member" (erfordert 2FA)
3. Der Browser des Admins verschlüsselt den Team-Verschlüsselungsschlüssel für das neue Mitglied
4. Das neue Mitglied meldet sich an und nimmt die Einladung an
5. Beide können nun dieselben Konfigurationen pushen/pullen

### Mitglieder entfernen

1. Admin klickt auf "Remove" neben dem Mitglied (erfordert 2FA)
2. Die Verschlüsselungsschlüssel des Mitglieds werden sofort gelöscht
3. Innerhalb von 30 Sekunden verliert das Mitglied jeglichen Zugriff auf verschlüsselte Konfigurationen

Keine Schlüsselrotation erforderlich -- der Server stellt dem entfernten Mitglied einfach keine Entschlüsselungsschlüssel mehr zur Verfügung.

## Sicherheitseigenschaften

| Eigenschaft | Wie |
|-------------|-----|
| **Zero-Knowledge** | Client verschlüsselt vor dem Senden; Server sieht nur opake Blobs |
| **Kein Master-Passwort** | Passkey-Biometrie ersetzt Passwörter vollständig |
| **Split-Key-Ableitung** | CEK erfordert sowohl passkey_secret (Client) + server_secret (Server) |
| **Rotierende Tokens** | Jeder API-Aufruf generiert einen neuen Token; alte werden ungültig |
| **IP-Bindung** | Tokens werden bei erster Verwendung an die Client-IP gebunden |
| **Dreifache Verschlüsselung** | SDK (zeitlich begrenzt) + CEK (Client) + Org-Passphrase (Server) |
| **Sofortiger Widerruf** | SDK-Auslieferung an entfernte Mitglieder stoppen; max. 30 Sekunden Verzögerung |
| **Manipulationserkennung** | HMAC über verschlüsselte Blobs; bei jedem Pull verifiziert |

Die vollständige Sicherheitsarchitektur finden Sie im [Security Guide](/docs/SECURITY-CONFIG-STORAGE.md).

## Fehlerbehebung

### "Passkey must support PRF extension"

Ihr Passkey-Anbieter unterstützt die PRF-Erweiterung nicht. Verwenden Sie:
- Bitwarden (Desktop-App oder Browser-Erweiterung)
- iCloud Keychain (Safari auf macOS/iOS)
- Windows Hello

### "Two-factor authentication required"

Org-Inhaber und Admins müssen 2FA aktivieren, bevor sie Config Storage einrichten. Gehen Sie zu Account Settings -> Security -> Enable 2FA.

### "Version conflict"

Ein anderes Teammitglied hat eine neuere Version gepusht. Ziehen Sie zuerst:
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

Tokens laufen nach 24 Stunden Inaktivität ab. Führen Sie einen beliebigen Befehl aus, um zu aktualisieren:
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

Der Verschlüsselungsschlüssel ging aus Ihrem sicheren OS-Speicher verloren (Neustart unter Linux, Keychain-Reset). Führen Sie die Einrichtung erneut durch:
```bash
rdc store add my-config --type rediacc
```
