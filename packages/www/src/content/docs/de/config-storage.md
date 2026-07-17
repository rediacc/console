---
title: Konfigurationsspeicher
description: Zero-Knowledge-verschlüsselte Konfigurationssynchronisierung mit Passkey, Master-Passwort und Wiederherstellungscode-Entsperrung
category: Guides
order: 8
language: de
sourceHash: "73c75b1f00630553"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Konfigurationsspeicher

Der Konfigurationsspeicher bietet Zero-Knowledge-verschlüsselte Synchronisierung Ihrer CLI-Konfiguration über Geräte hinweg. Ihre Konfigurationen werden clientseitig mit einem Content Encryption Key (CEK) verschlüsselt, der Server sieht niemals Klartextdaten.

## Entsperrmethoden (Key-Slots)

Es gibt eine CEK pro Speicher, die für jede Entsperrmethode unabhängig verpackt wird, ähnlich wie LUKS-Key-Slots. Jeder einzelne Slot öffnet denselben Schlüssel, und Slots lassen sich hinzufügen oder entfernen, ohne die Daten neu zu verschlüsseln:

| Methode | Was es ist | Hinweise |
|--------|-----------|-------|
| **Passkey** | WebAuthn-Passkey mit PRF-Erweiterung | Die stärkste Option; hardwaregestützt |
| **Master-Passwort** | Ein selbst gewähltes Passwort, gestreckt mit PBKDF2-SHA256 (600.000 Iterationen) | Funktioniert ohne PRF-fähige Hardware; ermöglicht außerdem die headless CLI-Einbindung |
| **Wiederherstellungscode** | Ein generierter Code der Form `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Wird bei der Erstellung nur einmal angezeigt; sicher aufbewahren |

Jede Methode speist dieselbe Verarbeitungskette: Der Slot liefert ein Geheimnis, das sich mit einem serverseitigen Geheimnis kombiniert, um die CEK zu entschlüsseln. Keine der beiden Hälften reicht allein aus, sodass die Zero-Knowledge-Eigenschaft für alle drei Methoden gilt - das Slot-Geheimnis erreicht den Server nie.

Slots werden im Portal auf der Seite Konfigurationsspeicher verwaltet. Organisationen, die eine reine Hardware-Entsperrung wünschen, können die Richtlinie **Passkey erforderlich** aktivieren, die Nicht-Passkey-Slots für den gesamten Speicher ablehnt und widerruft.

Die Entsperrung erfolgt pro Gerät: Sie entsperren einmal auf einem neuen Gerät, und danach funktionieren tägliche CLI-Operationen (Push/Pull), ohne dass ein Passkey oder ein Passwort nötig ist.

## Voraussetzungen

- **Zwei-Faktor-Authentifizierung** auf Ihrem Konto aktiviert
- Für die **Passkey**-Methode: ein Passkey-Anbieter mit PRF-Unterstützung, etwa ein FIDO2-Sicherheitsschlüssel (z. B. YubiKey), iCloud Keychain, Google Password Manager, 1Password oder Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+ oder Safari 17+

Die PRF-Anforderung gilt nur für den Passkey-Slot. Die Methoden Master-Passwort und Wiederherstellungscode funktionieren mit jedem unterstützten Browser.

## Einrichtung

1. Navigieren Sie zu **Konfigurationsspeicher** in der Seitenleiste und klicken Sie auf **Konfigurationsspeicher einrichten**
2. Die Anforderungscheckliste überprüft Ihren Browser, 2FA und den Sitzungsstatus
3. Klicken Sie auf **Einrichtung starten**. Für einen Passkey-Slot berühren Sie Ihren Sicherheitsschlüssel zweimal:
   - Erste Berührung: registriert den Passkey
   - Zweite Berührung: leitet Verschlüsselungsschlüssel über PRF ab
4. Einrichtung abgeschlossen - Ihr Passkey-Geheimnis wird in Ihrem Betriebssystem-Schlüsselbund gespeichert

Fügen Sie nach der Einrichtung über die Seite Konfigurationsspeicher einen Master-Passwort- oder Wiederherstellungscode-Slot hinzu, damit Sie ein verlorener oder nicht unterstützter Authentifikator nicht aussperrt.

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

## Headless CLI-Einbindung

Eine Maschine ohne Browser (ein Server, ein CI-Runner, ein Executor-Daemon) kann sich mit der Master-Passwort-Methode in einen bestehenden Speicher einbinden:

```bash
rdc config remote enable --password
```

Voraussetzungen:

- Ein bereits über das Portal eingerichteter **Master-Passwort-Slot** (der Browser hält den Schlüssel während der Einrichtung, dieser Schritt kann also selbst nicht headless erfolgen)
- Ein **API-Token mit dem Scope `config:enroll`**, um den Aufruf zu authentifizieren

Die Einbindung ist ein Lesevorgang: Die CLI ruft die öffentlichen KDF-Parameter des Slots und den verpackten Schlüssel ab, leitet das Passwort-Geheimnis lokal ab und entschlüsselt die CEK auf dem Gerät. Sie gewährt dem Gerät die Fähigkeit, die Konfiguration zu entschlüsseln und zu synchronisieren; der Speicher selbst wird dabei nicht verändert.

## Schlüsselrotation

Beim Rotieren der CEK des Speichers wird diese unter einer neuen Generation neu verpackt:

- **Wiederherstellungscodes werden bei jeder Rotation ungültig** - erzeugen und sichern Sie danach einen neuen
- Ein **Master-Passwort-Slot** übersteht die Rotation nur, wenn das Passwort im Rotationsassistenten erneut eingegeben wird
- Ein Slot, der bei einer älteren Generation zurückbleibt, wird als veraltet gemeldet, statt mit einem kryptischen Entschlüsselungsfehler zu scheitern

## Mitgliederverwaltung

Der Konfigurationsspeicher ist pro Organisation begrenzt. Mitglieder werden über das Webportal verwaltet:

- **Mitglieder anzeigen**: Konfigurationsspeicher → Mitglieder
- **Mitglied hinzufügen**: Derzeit nur über CLI (Web-UI geplant)
- **Mitglied entfernen**: Klicken Sie auf die Entfernen-Schaltfläche auf der Mitgliederseite (erfordert 2FA + erneute Authentifizierung)

Sicherheitsvorkehrungen verhindern das Entfernen des letzten aktiven Mitglieds oder das Entfernen von sich selbst.

## Sicherheit

- **Zero-Knowledge**: Der Server speichert dreifach verschlüsselte Daten, die er nicht entschlüsseln kann
- **Split-Key**: Die Entschlüsselung erfordert sowohl Ihr Slot-Geheimnis (Client) als auch das Server-Geheimnis (Server)
- **Rotierende Token**: Jeder API-Aufruf verwendet ein neues Token; alte Token zerstören sich selbst
- **IP-Bindung**: Token werden bei der ersten Verwendung an Ihre IP gebunden
- **Sofortiger Widerruf**: Entfernte Mitglieder verlieren den Zugriff innerhalb von 30 Sekunden

## Fehlerbehebung

| Fehler | Ursache | Lösung |
|-------|-------|-----|
| PRF not supported | Authentifikator unterstützt keine PRF-Erweiterung | Verwenden Sie YubiKey, iCloud Keychain, 1Password oder Dashlane, oder fügen Sie einen Master-Passwort-Slot hinzu |
| X25519 not supported | Browser-Version zu alt | Aktualisieren Sie auf Chrome 133+, Edge 133+, Firefox 130+ oder Safari 17+ |
| Already configured | Speicher existiert bereits für Ihre Organisation | Besuchen Sie /account/config-storage zur Verwaltung |
| Config storage not configured | Server fehlt Blob-Speicher | Kontaktieren Sie Ihren Administrator zur Konfiguration von R2/RustFS |
| Token expired | Keine Aktivität seit 24 Stunden | Führen Sie einen beliebigen Konfigurationsspeicher-Befehl zum Aktualisieren aus |
| Cannot remove last member | Würde den Speicher dauerhaft sperren | Fügen Sie zuerst ein weiteres Mitglied hinzu |
| Stale slot | Slot stammt aus der Zeit vor der letzten Schlüsselrotation | Fügen Sie den Slot erneut hinzu (Wiederherstellungscodes müssen nach jeder Rotation neu erzeugt werden) |

## Verwandte Seiten

- [Web-Konsole](/de/docs/web-console), den Speicher im Browser entsperren, um Befehle auszuführen
- [Proxy & Executor](/de/docs/proxy-and-executor), wie der entsperrte Schlüssel an einen Executor übergeben wird
