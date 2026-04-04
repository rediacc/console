---
title: Konfigurationsspeicher
description: >-
  Zero-Knowledge-verschlüsselte Konfigurationssynchronisierung mit
  Passkey-basierter Verschlüsselung
category: Guides
order: 8
language: de
sourceHash: "9612a5fecf063eea"
---

# Konfigurationsspeicher

Der Konfigurationsspeicher bietet Zero-Knowledge-verschlüsselte Synchronisierung Ihrer CLI-Konfiguration über Geräte hinweg. Ihre Konfigurationen werden mit Schlüsseln verschlüsselt, die von Ihrem Passkey abgeleitet werden -- der Server sieht niemals Klartextdaten.

## Voraussetzungen

- **Zwei-Faktor-Authentifizierung** auf Ihrem Konto aktiviert
- **Passkey-Anbieter mit PRF-Unterstützung**: FIDO2-Sicherheitsschlüssel (z. B. YubiKey), iCloud Keychain, Google Password Manager, 1Password oder Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+ oder Safari 17+

## Einrichtung

1. Navigieren Sie zu **Konfigurationsspeicher** in der Seitenleiste und klicken Sie auf **Konfigurationsspeicher einrichten**
2. Die Anforderungscheckliste überprüft Ihren Browser, 2FA und den Sitzungsstatus
3. Klicken Sie auf **Einrichtung starten** -- Sie müssen Ihren Sicherheitsschlüssel zweimal berühren:
   - Erste Berührung: registriert den Passkey
   - Zweite Berührung: leitet Verschlüsselungsschlüssel über PRF ab
4. Einrichtung abgeschlossen -- Ihr Passkey-Geheimnis wird in Ihrem Betriebssystem-Schlüsselbund gespeichert

Nach der Einrichtung funktionieren tägliche CLI-Operationen (Push/Pull) ohne den Passkey.

## PRF-Anbieter-Kompatibilität

| Anbieter | PRF-Unterstützung | Plattformen |
|----------|:-----------:|-----------|
| YubiKey / FIDO2-Sicherheitsschlüssel | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Plattformübergreifend |
| Bitwarden-Erweiterung | ❌ | In Entwicklung |
| Windows Hello | ❌ | Nicht unterstützt |

## Mitgliederverwaltung

Der Konfigurationsspeicher ist pro Organisation begrenzt. Mitglieder werden über das Webportal verwaltet:

- **Mitglieder anzeigen**: Konfigurationsspeicher → Mitglieder
- **Mitglied hinzufügen**: Derzeit nur über CLI (Web-UI geplant)
- **Mitglied entfernen**: Klicken Sie auf die Entfernen-Schaltfläche auf der Mitgliederseite (erfordert 2FA + erneute Authentifizierung)

Sicherheitsvorkehrungen verhindern das Entfernen des letzten aktiven Mitglieds oder das Entfernen von sich selbst.

## Sicherheit

- **Zero-Knowledge**: Der Server speichert dreifach verschlüsselte Daten, die er nicht entschlüsseln kann
- **Split-Key**: Die Entschlüsselung erfordert sowohl Ihr Passkey-Geheimnis (Client) als auch das Server-Geheimnis (Server)
- **Rotierende Token**: Jeder API-Aufruf verwendet ein neues Token; alte Token zerstören sich selbst
- **IP-Bindung**: Token werden bei der ersten Verwendung an Ihre IP gebunden
- **Sofortiger Widerruf**: Entfernte Mitglieder verlieren den Zugriff innerhalb von 30 Sekunden

## Fehlerbehebung

| Fehler | Ursache | Lösung |
|-------|-------|-----|
| PRF not supported | Authentifikator unterstützt keine PRF-Erweiterung | Verwenden Sie YubiKey, iCloud Keychain, 1Password oder Dashlane |
| X25519 not supported | Browser-Version zu alt | Aktualisieren Sie auf Chrome 133+, Edge 133+, Firefox 130+ oder Safari 17+ |
| Already configured | Speicher existiert bereits für Ihre Organisation | Besuchen Sie /account/config-storage zur Verwaltung |
| Config storage not configured | Server fehlt Blob-Speicher | Kontaktieren Sie Ihren Administrator zur Konfiguration von R2/RustFS |
| Token expired | Keine Aktivität seit 24 Stunden | Führen Sie einen beliebigen Konfigurationsspeicher-Befehl zum Aktualisieren aus |
| Cannot remove last member | Würde den Speicher dauerhaft sperren | Fügen Sie zuerst ein weiteres Mitglied hinzu |
