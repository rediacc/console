---
title: Konfigurationsspeicher
description: Clientseitig verschlüsselte Konfigurationssynchronisierung mit Passkey- und Wiederherstellungscode-Entsperrung
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: de
sourceHash: "d3fbda10a9432f55"
sourceCommit: "4db12448b1a702a53a57ca01d7311ad9b3cbefda"
---

# Konfigurationsspeicher

Der Konfigurationsspeicher synchronisiert eine CLI-Konfiguration über Geräte hinweg. Konfigurationen werden auf dem Gerät mit einem Content Encryption Key (CEK) verschlüsselt, den der Server nie besitzt. Der Abschnitt [Sicherheit](#security) beschreibt genau, wovor das schützt und wovor nicht.

## Entsperrmethoden (Key-Slots)

Es gibt eine CEK pro Speicher, die für jede Entsperrmethode unabhängig verpackt wird, ähnlich wie LUKS-Key-Slots. Jeder einzelne Slot öffnet denselben Schlüssel, und Slots lassen sich hinzufügen oder entfernen, ohne die Daten neu zu verschlüsseln:

| Methode | Was es ist | Hinweise |
|--------|-----------|-------|
| **Passkey** | WebAuthn-Passkey mit PRF-Erweiterung | Die stärkste Option; hardwaregestützt |
| **Wiederherstellungscode** | Ein generierter Code der Form `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Wird bei der Erstellung nur einmal angezeigt; sicher aufbewahren |

Jede Methode speist dieselbe Verarbeitungskette: Der Slot liefert ein Geheimnis, das sich mit einem serverseitigen Geheimnis kombiniert, um die CEK zu entschlüsseln. Keine der beiden Hälften reicht allein aus, und das Slot-Geheimnis erreicht den Server nie. Beide Geheimnisse haben genug Entropie, sodass der Server, der den verpackten Schlüssel und seine Hälfte des Verpackungsschlüssels kennt, offline nichts zu erraten hat.

Slots werden im Portal auf der Seite Konfigurationsspeicher verwaltet. Organisationen, die eine reine Hardware-Entsperrung wünschen, können die Richtlinie **Passkey erforderlich** aktivieren, die Nicht-Passkey-Slots für den gesamten Speicher ablehnt und widerruft.

Die Entsperrung erfolgt pro Gerät: Sie entsperren einmal auf einem neuen Gerät, und danach funktionieren tägliche CLI-Operationen (Push/Pull), ohne dass ein Passkey oder ein Wiederherstellungscode nötig ist.

## Voraussetzungen

- **Zwei-Faktor-Authentifizierung** auf Ihrem Konto aktiviert
- Für die **Passkey**-Methode: ein Passkey-Anbieter mit PRF-Unterstützung, etwa ein FIDO2-Sicherheitsschlüssel (z. B. YubiKey), iCloud Keychain, Google Password Manager, 1Password oder Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+ oder Safari 17+

Die PRF-Anforderung gilt nur für den Passkey-Slot. Der Wiederherstellungscode funktioniert mit jedem unterstützten Browser.

## Einrichtung

1. Navigieren Sie zu **Konfigurationsspeicher** in der Seitenleiste und klicken Sie auf **Konfigurationsspeicher einrichten**
2. Die Anforderungscheckliste überprüft Ihren Browser, 2FA und den Sitzungsstatus
3. Registrieren Sie einen Passkey und klicken Sie auf **Konfigurationsspeicher erstellen**. Der Anbieter muss PRF unterstützen: Sie berühren Ihren Sicherheitsschlüssel zweimal, einmal zur Registrierung und einmal zum Ableiten der Schlüssel.
   - Ein **Wiederherstellungscode** wird mit dem Speicher erzeugt und einmal in einem Wiederherstellungs-Kit angezeigt. Sichern Sie das Kit, bevor der Speicher angelegt wird; ohne diesen Schritt wird die Einrichtung nicht abgeschlossen.
4. Die Einrichtung ist abgeschlossen. Die CLI bewahrt das Entsperrgeheimnis im Schlüsselbund Ihres Betriebssystems auf.

Ein Passkey lässt sich später auf der Seite „Config Storage“ hinzufügen. Behalten Sie mindestens zwei Entsperrmethoden, damit ein verlorener oder nicht unterstützter Authenticator Sie nicht aussperrt.

## PRF-Anbieter-Kompatibilität

| Anbieter | PRF-Unterstützung | Plattformen |
|----------|:-----------:|-----------|
| YubiKey / FIDO2-Sicherheitsschlüssel | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Plattformübergreifend |
| Bitwarden-Erweiterung | ❌ | Einen Hardware-Schlüssel oder einen anderen Passkey-Anbieter verwenden |
| Windows Hello | ❌ | Nicht unterstützt |

## Headless CLI-Einbindung

Eine Maschine ohne Browser (ein Server, ein CI-Runner, ein Executor-Daemon) kann sich mit einem Maschinengeheimnis in einen bestehenden Speicher einbinden:

```bash
export REDIACC_MACHINE_SECRET=RM1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
rdc config remote enable --machine-secret <id>
```

Voraussetzungen:

- Ein über das Portal erzeugtes **Maschinengeheimnis** (der Browser hält den Schlüssel, während er ihn unter dem Geheimnis verpackt, dieser Schritt kann also selbst nicht headless erfolgen). Das Portal zeigt das `RM1-`-Geheimnis einmalig zusammen mit seiner ID an; das Geheimnis gilt für die Organisation, ein Team oder eine einzelne Konfiguration
- Ein **API-Token mit dem Scope `config:enroll`**, um den Aufruf zu authentifizieren

Das Geheimnis stammt aus `REDIACC_MACHINE_SECRET`, sonst aus der Standardeingabe, wenn diese per Pipe befüllt wird, sonst aus einer verdeckten Eingabeaufforderung; es ist nie ein Kommandozeilenargument. Die Einbindung ist ein Lesevorgang: Die CLI ruft die öffentlichen KDF-Parameter des Geheimnisses und den verpackten Schlüssel ab, leitet das Verpackungsgeheimnis lokal ab und entschlüsselt die CEK auf dem Gerät. Sie gewährt dem Gerät die Fähigkeit, die Konfiguration zu entschlüsseln und zu synchronisieren; der Speicher selbst wird dabei nicht verändert. Wird das Geheimnis im Portal widerrufen, sind damit keine neuen Einbindungen mehr möglich.

## Wie die Schlüssel zu Ihrer CLI gelangen

`rdc config remote enable` (und `rdc config rotate-cek`) übergeben das Entsperrgeheimnis über den Account-Server an die CLI. CLI und Browser sprechen nie direkt miteinander, deshalb funktioniert das auf einem Server ohne Browser genauso wie in WSL mit dem Browser unter Windows oder auf einem Smartphone.

1. Melden Sie zuerst die CLI mit `rdc subscription login` an. Der Server bindet die Anfrage an dieses Konto.
2. Die CLI erstellt eine kurzlebige Anfrage und gibt einen Link sowie einen **Kopplungscode** wie `7KQ2-M9XD-P4RT` aus. Alles, was der Link trägt, steht hinter dem `#`, und Browser senden diesen Teil nie an einen Server.
3. Öffnen Sie den Link in einem beliebigen Browser, der mit demselben Konto angemeldet ist. Eine Anfrage von einem anderen Konto wird abgelehnt.
4. Geben Sie den Kopplungscode aus Ihrem Terminal ein, sobald die Seite danach fragt. Die Schaltfläche zum Entsperren bleibt deaktiviert, bis er übereinstimmt.
5. Entsperren Sie mit Ihrem Passkey oder Wiederherstellungscode. Der Browser versiegelt den Schlüssel für die CLI, und der Server leitet einen Datenblock weiter, den er nicht lesen kann.
6. Die CLI entschlüsselt den Datenblock, legt das Geheimnis im Schlüsselbund des Betriebssystems ab und meldet den Erfolg.

Die Anfrage läuft nach 10 Minuten ab. Mit **Ctrl+C** in der CLI brechen Sie sie ab: Die CLI fordert den Server auf, den Link zu verwerfen, der dann sofort nicht mehr funktioniert, und die Seite weist darauf hin, den Befehl erneut auszuführen. Kommt diese Anfrage nicht an, bleibt der Link bis zum Ablauf der Anfrage nutzbar. Wird der Link nach Ablauf geöffnet oder hat eine Weiterleitung nach der Anmeldung den Teil nach dem `#` verloren, führen Sie den Befehl einfach noch einmal aus.

Der Kopplungscode wird aus dem Schlüssel im Link abgeleitet. Tauscht jemand den Link gegen einen eigenen aus, stimmt der Code in Ihrem Terminal nicht mit dem überein, was die Seite erwartet, und es wird nichts freigegeben.

Das schützt vor manipulierten Links und vor einem Relay, das einen Datenblock austauscht oder fälscht. Es schützt nicht vor einem Server, der veränderten Seitencode ausliefert: Die Seite, die Sie öffnen, kommt vom Account-Server, und die Schlüssel sind nur so sicher wie dieser Code. Dasselbe Vertrauen gilt für jede Portalseite, die den Konfigurationsschlüssel verarbeitet.

## Aktivierung und Offline-Lesezugriffe

`rdc config remote enable` verbindet die aktive Konfiguration mit dem Speicher. Wenn der Speicher leer ist, **befüllt die Aktivierung ihn mit Ihrer aktuellen lokalen Konfiguration**: Die lokalen Ressourcen werden als erste Version des Speichers gepusht und anschließend zurückgeholt, um den Round-Trip zu belegen. Enthält der Speicher bereits Inhalte, gleicht die Aktivierung stattdessen mit ihm ab, statt ihn zu überschreiben (sie bricht bei einer echten Abweichung ab, sofern Sie nicht `--force` übergeben).

Nach der Aktivierung führt die Konfiguration einen vollständigen **Lese-Cache**, der mit demselben Mechanismus wie jede lokale Konfiguration verschlüsselt gespeichert wird, sodass der Speicher auch nutzbar bleibt, wenn der Account-Server nicht erreichbar ist:

- **Lesevorgänge funktionieren offline.** Der zwischengespeicherte Inhalt wird mit einer Veraltungswarnung auf stderr ausgeliefert, versehen mit der zwischengespeicherten Version und dem Zeitstempel (`cachedVersion` / `cachedAt`).
- **Schreibvorgänge erfordern den Server und schlagen sicher fehl.** Es gibt keine Offline-Schreibwarteschlange: Ein Schreibvorgang, der den Server nicht erreicht, bricht mit einer Fehlermeldung ab, die den Server benennt. Ist ein Schreibbefehl erfolgreich, ist die Änderung auf dem Server.
- **Gleichzeitige Änderungen von zwei Geräten** werden per Pull-Replay-Repush aufgelöst: Der Server akzeptiert einen Push nur auf der Version, die er ersetzt, und der unterlegene Push wird auf die aktuelle Kopie repliziert, sodass eine zeitgleiche Änderung an anderer Stelle nicht überschrieben wird.
- **Eine lokale Konfiguration** (ohne `remote`-Block) ist davon nicht betroffen und funktioniert vollständig offline.

## Was synchronisiert wird

Alles in einer Konfiguration wird synchronisiert, einschließlich der Netzwerk-ID jedes Repositorys, außer diesen geräteabhängigen Feldern: `schemaVersion`, `version`, `remote`, `encryption`, `renetPath`, `credentials.masterPasswordVerifier` sowie den Login-Feldern `account.accountServer` und `account.e2ePublicKey`. An- und Abmelden erfolgen pro Gerät.

## Versionen und Wiederherstellung

Der Server behält die letzten 50 Versionen jeder Konfiguration.

```bash
rdc config remote versions
rdc config remote restore <version>
```

Eine Wiederherstellung veröffentlicht den alten Inhalt als neue Version auf der aktuellen; die Versionsnummer geht dabei nie zurück. Jedes Gerät erhält den wiederhergestellten Inhalt beim nächsten Pull, und die Wiederherstellung wird im Audit-Log erfasst.

## Schlüsselrotation

Beim Rotieren der CEK des Speichers wird diese unter einer neuen Generation neu verpackt:

- **Wiederherstellungscodes werden bei jeder Rotation ungültig** - erzeugen und sichern Sie danach einen neuen
- Ein Slot, der bei einer älteren Generation zurückbleibt, wird als veraltet gemeldet, statt mit einem kryptischen Entschlüsselungsfehler zu scheitern
- Die Konfigurations-Token der anderen Mitglieder werden widerrufen, und ein Gerät, das noch den alten Schlüssel besitzt, wird aufgefordert, sich mit `rdc config remote enable` erneut zu aktivieren

## Mitgliederverwaltung

Der Konfigurationsspeicher ist pro Organisation begrenzt. Mitglieder werden über das Webportal verwaltet:

- **Mitglieder anzeigen**: Konfigurationsspeicher → Mitglieder
- **Mitglied hinzufügen**: Derzeit nur über CLI (Web-UI geplant)
- **Mitglied entfernen**: Klicken Sie auf die Entfernen-Schaltfläche auf der Mitgliederseite (erfordert 2FA + erneute Authentifizierung)

Sicherheitsvorkehrungen verhindern das Entfernen des letzten aktiven Mitglieds oder das Entfernen von sich selbst.

Konfigurationen im Speicher sind zusätzlich pro Team begrenzt, aber diese Begrenzung ist **serverseitige Zugriffskontrolle, keine kryptografische Isolierung**: Eine organisationsweite CEK verschlüsselt die Konfigurationen aller Teams, und der Server setzt durch, welche Teams ein Mitglied lesen darf.

## Sicherheit

**Was geschützt ist.** Gespeicherte Konfigurationen sind vertraulich gegenüber einer Kompromittierung des Server-Speichers und gegenüber einem passiven Betreiber. Jeder Blob ist an seinen Speicher, seine Konfiguration, sein Team und seine Version gebunden, sodass der Server den Blob einer Konfiguration nicht gegen den einer anderen austauschen oder unbemerkt verändern kann.

**Was nicht geschützt ist.** Ein Betreiber, der bösartigen Portal-Code ausliefert, kann den Schlüssel im Browser auslesen. Ein Betreiber kann einem Gerät, das eine neuere Version noch nie gesehen hat, auch diese neueste Version vorenthalten.

| Der Server kann | Der Server kann nicht |
|---|---|
| Konfigurations-IDs, Teams, Versionsnummern, Zeitstempel, Blob-Größen, die Anzahl der in einer Konfiguration festgeschriebenen Felder samt deren Typ sowie Client-IP-Adressen sehen | Maschinen-, Repository- oder Speichernamen (sie sind geblindet) oder irgendeinen Konfigurationswert sehen |
| Konfigurationen und ihren Verlauf ablehnen, verzögern oder löschen | Den Inhalt einer Konfiguration als den einer anderen ausgeben oder ihn verändern, ohne dass das Gerät es bemerkt |
| Einem Gerät, das eine neuere Version nie gesehen hat, eine alte Version ausliefern | Der CLI eine Version ausliefern, die älter ist als eine bereits gesehene: Die CLI lehnt sie ab |

Weitere Schutzmaßnahmen:

- **Geteilter Schlüssel**: Die Entschlüsselung erfordert sowohl das Slot-Geheimnis (auf dem Gerät) als auch das Server-Geheimnis
- **Löschen erfordert Kenntnis**: Das Entfernen eines festgeschriebenen Werts aus einer Konfiguration erfordert den Nachweis, dass der Wert bekannt war, sodass ein Akteur mit nur teilweisem Zugriff Felder nicht stillschweigend entfernen kann
- **Rotierende Token**: Jede Anfrage rotiert das Konfigurations-Token; ein Token ist an die IP-Adresse seiner ersten Verwendung gebunden und läuft nach 7 Tagen ab
- **Widerruf**: Das Entfernen eines Mitglieds löscht dessen Key-Slots und Token sofort; bereits abgerufene Inhalte bleiben auf dessen Gerät, und eine CEK-Rotation verhindert, dass ein zurückbehaltener Schlüssel spätere Versionen öffnen kann

## Fehlerbehebung

| Fehler | Ursache | Lösung |
|-------|-------|-----|
| PRF not supported | Authentifikator unterstützt keine PRF-Erweiterung | Verwenden Sie YubiKey, iCloud Keychain, 1Password oder Dashlane |
| X25519 not supported | Browser-Version zu alt | Aktualisieren Sie auf Chrome 133+, Edge 133+, Firefox 130+ oder Safari 17+ |
| Already configured | Speicher existiert bereits für Ihre Organisation | Besuchen Sie /account/config-storage zur Verwaltung |
| Config storage not configured | Server fehlt Blob-Speicher | Kontaktieren Sie Ihren Administrator zur Konfiguration von R2/RustFS |
| Token expired | Keine Aktivität seit 7 Tagen, oder die Maschine hat das Netzwerk gewechselt | Wird automatisch bei der Anmeldung erneuert; ist keine Anmeldung gespeichert, `rdc subscription login` oder `rdc config remote enable` ausführen |
| Config came back at an older version | Der Server hat eine ältere Kopie zurückgegeben, als dieses Gerät bereits gesehen hat | Lokal wurde nichts geändert; erneut versuchen und melden, falls es anhält |
| Cannot remove last member | Würde den Speicher dauerhaft sperren | Fügen Sie zuerst ein weiteres Mitglied hinzu |
| Stale slot | Slot stammt aus der Zeit vor der letzten Schlüsselrotation | Fügen Sie den Slot erneut hinzu (Wiederherstellungscodes müssen nach jeder Rotation neu erzeugt werden) |

## Verwandte Seiten

- [Web-Konsole](/de/docs/web-console), den Speicher im Browser entsperren, um Befehle auszuführen
- [Proxy & Executor](/de/docs/proxy-and-executor), wie der entsperrte Schlüssel an einen Executor übergeben wird
