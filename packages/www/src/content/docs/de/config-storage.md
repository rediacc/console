---
title: Konfigurationsspeicher
description: Zero-Knowledge-verschlüsselte Konfigurationssynchronisierung mit Passkey, Master-Passwort und Wiederherstellungscode-Entsperrung
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: de
sourceHash: "e4b2eecb8bdf0015"
sourceCommit: "433347c5ea4754300fe3da80c4bfcee42dd161bc"
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

## Aktivierung und Offline-Lesezugriffe

`rdc config remote enable` verbindet die aktive Konfiguration mit dem Speicher. Wenn der Speicher leer ist, **befüllt die Aktivierung ihn mit Ihrer aktuellen lokalen Konfiguration**: Die lokalen Ressourcen werden als erste Version des Speichers gepusht und anschließend zurückgeholt, um den Round-Trip zu belegen. Enthält der Speicher bereits Inhalte, gleicht die Aktivierung stattdessen mit ihm ab, statt ihn zu überschreiben (sie bricht bei einer echten Abweichung ab, sofern Sie nicht `--force` übergeben).

Nach der Aktivierung führt die Konfiguration einen vollständigen **Lese-Cache**, der mit demselben Mechanismus wie jede lokale Konfiguration verschlüsselt gespeichert wird, sodass der Speicher auch nutzbar bleibt, wenn der Account-Server nicht erreichbar ist:

- **Lesevorgänge funktionieren offline.** Der zwischengespeicherte Inhalt wird mit einer Veraltungswarnung auf stderr ausgeliefert, versehen mit der zwischengespeicherten Version und dem Zeitstempel (`cachedVersion` / `cachedAt`).
- **Schreibvorgänge erfordern den Server und schlagen sicher fehl.** Es gibt keine Offline-Schreibwarteschlange: Ein Schreibvorgang, der den Server nicht erreicht, bricht mit einer Fehlermeldung ab, die den Server benennt. Ist ein Schreibbefehl erfolgreich, ist die Änderung auf dem Server.
- **Gleichzeitige Änderungen von zwei Geräten** werden per Pull-Replay-Repush auf Ebene des Ressourcen-Buckets aufgelöst, sodass eine zeitgleiche Änderung an anderer Stelle Ihre nicht überschreibt.

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

Konfigurationen im Speicher sind zusätzlich pro Team begrenzt, aber diese Begrenzung ist **serverseitige Zugriffskontrolle, keine kryptografische Isolierung**: Eine organisationsweite CEK verschlüsselt die Konfigurationen aller Teams, und der Server setzt durch, welche Teams ein Mitglied lesen darf.

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
