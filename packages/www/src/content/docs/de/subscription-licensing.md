---
title: Abonnement & Lizenzierung
description: Erfahren Sie, wie Account, rdc und renet Maschinenplätze, Repo-Lizenzen und Planlimits verwalten.
category: Guides
order: 7
language: de
sourceHash: "e7a65f722fbb1093"
---

# Abonnement & Lizenzierung

Die Rediacc-Lizenzierung besteht aus drei beweglichen Teilen:

- `account` signiert Berechtigungen und verfolgt die Nutzung
- `rdc` authentifiziert, fordert Lizenzen an, liefert sie an Maschinen und setzt sie zur Laufzeit durch
- `renet` (die maschinenseitige Laufzeitumgebung) validiert installierte Lizenzen lokal, ohne den Account-Server zu kontaktieren

Diese Seite erklärt, wie diese Teile bei lokalen Bereitstellungen zusammenwirken.

## Was Lizenzierung bewirkt

Lizenzierung steuert zwei verschiedene Dinge:

- **Maschinenzeugangsbuchhaltung** durch **Floating-Lizenzen**
- **Repository-Laufzeit-Autorisierung** durch **Repo-Lizenzen**

Diese sind verwandt, aber nicht dasselbe Artefakt.

## Wie Lizenzierung funktioniert

`account` ist die maßgebliche Quelle für Pläne, Vertragsüberschreibungen, Maschinenaktivierungsstatus und monatliche Repo-Lizenzausstellungen.

`rdc` läuft auf Ihrer Workstation. Es meldet Sie beim Account-Server an, fordert die benötigten Lizenzen an und installiert sie über SSH auf entfernten Maschinen. Wenn Sie einen Repository-Befehl ausführen, stellt `rdc` sicher, dass die erforderlichen Lizenzen vorhanden sind, und validiert sie zur Laufzeit auf der Maschine.

Der normale Ablauf sieht wie folgt aus:

1. Sie authentifizieren sich mit `rdc subscription login`
2. Sie führen einen Repository-Befehl wie `rdc repo create`, `rdc repo up` oder `rdc repo down` aus
3. Wenn die erforderliche Lizenz fehlt oder abgelaufen ist, fordert `rdc` sie von `account` an
4. `rdc` schreibt die signierte Lizenz auf die Maschine
5. Die Lizenz wird lokal auf der Maschine validiert und die Operation wird fortgesetzt

Siehe [rdc vs renet](/de/docs/rdc-vs-renet) für die Aufteilung Workstation/Server und [Repositories](/de/docs/repositories) für den Repository-Lebenszyklus selbst.

Für Automatisierung und KI-Agenten verwenden Sie statt Browser-Login ein bereichsspezifisches Abonnement-Token:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Sie können das Token auch direkt über die Umgebung injizieren, sodass die CLI Repo-Lizenzen ohne interaktiven Login-Schritt ausstellen und aktualisieren kann:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Maschinenlizenzen vs. Repo-Lizenzen

### Maschinenaktivierung

Die Maschinenaktivierung erfüllt eine Doppelrolle:

- **Serverseitig**: Floating-Maschinen-Slot-Buchhaltung, maschinenseitige Aktivierungsprüfungen, Verknüpfung der konto-gestützten Repo-Ausstellung mit einer bestimmten Maschine
- **Auf der Festplatte**: `rdc` schreibt während der Aktivierung einen signierten Abonnement-Blob nach `/var/lib/rediacc/license/machine.json`. Dieser Blob wird lokal für Bereitstellungsoperationen (`rdc repo create`, `rdc repo fork`) validiert. Die Maschinenlizenz ist 1 Stunde ab der letzten Aktivierung gültig.

### Repo-Lizenz

Eine Repo-Lizenz ist eine signierte Lizenz für ein Repository auf einer Maschine.

Sie wird verwendet für:

- `rdc repo resize` und `rdc repo expand` — vollständige Validierung einschließlich Ablauf
- `rdc repo up`, `rdc repo down`, `rdc repo delete` — validiert mit **übersprungener Ablaufprüfung**
- `rdc backup push`, `rdc backup pull`, `rdc backup sync` — validiert mit **übersprungener Ablaufprüfung**
- Repo-Autostart beim Maschinenneustart — validiert mit **übersprungener Ablaufprüfung**

Repo-Lizenzen sind an die Maschine und das Ziel-Repository gebunden, und Rediacc verstärkt diese Bindung durch Repository-Identitätsmetadaten. Bei verschlüsselten Repositories umfasst dies die LUKS-Identität des zugrunde liegenden Volumes.

In der Praxis:

- Maschinenaktivierung beantwortet: "Kann diese Maschine neue Repositories bereitstellen?"
- Repo-Lizenz beantwortet: "Kann dieses spezifische Repository auf dieser spezifischen Maschine laufen?"

## Standardlimits

Die Repository-Größe hängt vom Berechtigungsniveau ab:

- Community: bis zu `10 GB`
- Kostenpflichtige Pläne: Plan- oder Vertragslimit

Standard-Limits für kostenpflichtige Pläne:

| Plan | Floating-Lizenzen | Repository-Größe | Monatliche Repo-Lizenzausstellungen |
|------|-------------------|------------------|-------------------------------------|
| Community | 2 | 10 GB | 500 |
| Professional | 5 | 100 GB | 5.000 |
| Business | 20 | 500 GB | 20.000 |
| Enterprise | 50 | 2048 GB | 100.000 |

Vertragsspezifische Limits können diese Werte für einen bestimmten Kunden erhöhen oder verringern.

## Was bei Repo-Erstellung, -Start, -Stopp und -Neustart passiert

### Repo erstellen und forken

Wenn Sie ein Repository erstellen oder forken:

1. `rdc` stellt sicher, dass Ihr Abonnement-Token verfügbar ist (löst Device-Code-Authentifizierung aus, falls nötig)
2. `rdc` aktiviert die Maschine und schreibt den signierten Abonnement-Blob auf die entfernte Maschine
3. Die Maschinenlizenz wird lokal validiert (sie muss innerhalb von 1 Stunde nach Aktivierung sein)
4. Nach erfolgreicher Erstellung stellt `rdc` die Repo-Lizenz für das neue Repository aus

Diese kontogestützte Ausstellung zählt zu Ihrer monatlichen Nutzung der **Repo-Lizenzausstellungen**.

### Repo starten, stoppen und löschen

`rdc` validiert die installierte Repo-Lizenz auf der Maschine, **überspringt jedoch die Ablaufprüfung**. Signatur, Maschinen-ID, Repository-GUID und Identität werden weiterhin geprüft. Benutzer werden nie vom Betrieb ihrer Repositories ausgesperrt, auch nicht mit einem abgelaufenen Abonnement.

### Repo skalieren und erweitern

`rdc` führt eine vollständige Repo-Lizenz-Validierung einschließlich Ablauf und Größenlimits durch.

### Maschinenneustart und Autostart

Autostart verwendet dieselben Regeln wie `rdc repo up` — die Ablaufprüfung wird übersprungen, sodass Repositories immer frei neu starten.

Repo-Lizenzen verwenden ein langlebiges Gültigkeitsmodell:

- `refreshRecommendedAt` ist der weiche Aktualisierungspunkt
- `hardExpiresAt` ist der blockierende Punkt

Wenn die Repo-Lizenz veraltet ist, aber noch vor dem Hard-Ablauf liegt, kann die Laufzeit fortgesetzt werden. Sobald der Hard-Ablauf erreicht ist, muss `rdc` sie für Resize/Expand-Operationen aktualisieren.

### Andere Repository-Operationen

Operationen wie das Auflisten von Repos, das Inspizieren von Repo-Informationen und das Einbinden erfordern keine Lizenzvalidierung.

## Status prüfen und Lizenzen aktualisieren

Menschliche Anmeldung:

```bash
rdc subscription login
```

Automatisierungs- oder KI-Agenten-Anmeldung:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Für nicht-interaktive Umgebungen ist das Setzen von `REDIACC_SUBSCRIPTION_TOKEN` die einfachste Option. Das Token sollte nur für die Abonnement- und Repo-Lizenz-Operationen des Agenten berechtigt sein.

Kontogestützten Abonnementstatus anzeigen:

```bash
rdc subscription status
```

Maschinenaktivierungsdetails für eine Maschine anzeigen:

```bash
rdc subscription activation-status -m hostinger
```

Installierte Repo-Lizenz-Details auf einer Maschine anzeigen:

```bash
rdc subscription repo-status -m hostinger
```

Maschinenaktivierung aktualisieren und Repo-Lizenzen im Batch aktualisieren:

```bash
rdc subscription refresh -m hostinger
```

Repositories, die auf der Maschine entdeckt wurden, aber in der lokalen `rdc`-Konfiguration fehlen, werden bei der Batch-Aktualisierung abgelehnt. Sie werden als Fehler gemeldet und nicht automatisch klassifiziert.

Repo-Lizenz-Aktualisierung für ein vorhandenes Repository erzwingen:

```bash
rdc subscription refresh-repo my-app -m hostinger
```

Bei der ersten Verwendung kann eine lizenzierte Repo- oder Backup-Operation, die keine verwendbare Repo-Lizenz findet, automatisch eine Konto-Autorisierungs-Übergabe auslösen. Die CLI gibt eine Autorisierungs-URL aus, versucht den Browser in interaktiven Terminals zu öffnen, und wiederholt die Operation einmal nach erfolgreicher Autorisierung und Ausstellung.

In nicht-interaktiven Umgebungen wartet die CLI nicht auf Browser-Genehmigung. Stattdessen fordert sie Sie auf, ein bereichsspezifisches Token mit `rdc subscription login --token ...` oder `REDIACC_SUBSCRIPTION_TOKEN` anzugeben.

Für die erstmalige Maschineneinrichtung siehe [Maschinen-Setup](/de/docs/setup).

## Offline-Verhalten und Ablauf

Die Lizenzvalidierung erfolgt lokal auf der Maschine — sie erfordert keine Live-Verbindung zum Account-Server.

Das bedeutet:

- Eine laufende Umgebung benötigt bei jedem Befehl keine Live-Konto-Verbindung
- Alle Repos können immer gestartet, gestoppt und gelöscht werden, auch mit abgelaufenen Lizenzen — Benutzer werden nie vom Betrieb ihrer eigenen Repositories ausgesperrt
- Bereitstellungsoperationen (`create`, `fork`) erfordern eine gültige Maschinenlizenz, und Wachstumsoperationen (`resize`, `expand`) erfordern eine gültige Repo-Lizenz
- Wirklich abgelaufene Repo-Lizenzen müssen vor Resize/Expand über `rdc` aktualisiert werden

Maschinenaktivierung und Repo-Laufzeitlizenzen sind separate Oberflächen. Eine Maschine kann im Account-Status inaktiv sein, während einige Repositories noch gültige installierte Repo-Lizenzen haben. In diesem Fall inspizieren Sie beide Oberflächen separat, anstatt anzunehmen, dass sie dasselbe bedeuten.

## Wiederherstellungsverhalten

Die automatische Wiederherstellung ist bewusst eng gefasst:

- `missing`: `rdc` kann bei Bedarf den Kontozugang autorisieren, Repo-Lizenzen im Batch aktualisieren und einmal wiederholen
- `expired`: `rdc` kann Repo-Lizenzen im Batch aktualisieren und einmal wiederholen
- `machine_mismatch`: schlägt sofort fehl und fordert Sie auf, aus dem aktuellen Maschinenkontext neu auszustellen
- `repository_mismatch`: schlägt sofort fehl und fordert Sie auf, Repo-Lizenzen explizit zu aktualisieren
- `sequence_regression`: schlägt sofort fehl als Repo-Lizenz-Integritäts-/Statusproblem
- `invalid_signature`: schlägt sofort fehl als Repo-Lizenz-Integritäts-/Statusproblem
- `identity_mismatch`: schlägt sofort fehl — die Repository-Identität stimmt nicht mit der installierten Lizenz überein

Diese Sofort-Fehlschlag-Fälle verbrauchen nicht automatisch kontogestützte Aktualisierungs- oder Ausstellungsaufrufe.

## Monatliche Repo-Lizenzausstellungen

Diese Metrik zählt erfolgreiche kontogestützte Repo-Lizenz-Ausstellungsaktivitäten im aktuellen UTC-Kalendermonat.

Dazu gehören:

- Erstmalige Repo-Lizenzausstellung
- Erfolgreiche Repo-Lizenz-Aktualisierung, die eine neu signierte Lizenz zurückgibt

Nicht dazu gehören:

- Unveränderte Batch-Einträge
- Fehlgeschlagene Ausstellungsversuche
- Nicht verfolgte Repositories, die vor der Ausstellung abgelehnt wurden

Wenn Sie eine kundenseitige Ansicht der Nutzung und des letzten Repo-Lizenz-Ausstellungsverlaufs benötigen, verwenden Sie das Account-Portal. Wenn Sie maschinenseitige Inspektion benötigen, verwenden Sie `rdc subscription activation-status -m` und `rdc subscription repo-status -m`.
