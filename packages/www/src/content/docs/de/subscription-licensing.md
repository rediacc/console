---
title: "Abonnement & Lizenzierung"
description: "Erfahren Sie, wie Account, rdc und renet Maschinenplätze, Repo-Lizenzen und Planlimits verwalten."
category: "Guides"
order: 7
language: de
sourceHash: "ed0aef562aad7367"
sourceCommit: "68c6d120013af4c092bcfd997ed8e9b47101be34"
---

# Abonnement & Lizenzierung

Die Rediacc-Lizenzierung besteht aus drei beweglichen Teilen:

- `account` signiert Berechtigungen und verfolgt die Nutzung
- `rdc` authentifiziert, fordert Lizenzen an, liefert sie an Maschinen und setzt sie zur Laufzeit durch
- `renet` (die maschinenseitige Laufzeitumgebung) validiert installierte Lizenzen lokal, ohne den Account-Server zu kontaktieren

Diese Seite erklärt, wie diese Teile bei lokalen Bereitstellungen zusammenwirken.

## Was Lizenzierung bewirkt

Lizenzierung steuert zwei verschiedene Dinge:

- **Maschinenzugangsabrechnung** durch **Floating-Lizenzen**
- **Repository-Laufzeit-Autorisierung** durch **Repo-Lizenzen**

Diese sind verwandt, aber nicht dasselbe Artefakt.

## Wie Lizenzierung funktioniert

`account` ist die maßgebliche Quelle für Pläne, Vertragsüberschreibungen, Maschinenplatz-Status und monatliche Repo-Lizenzausstellungen.

`rdc` läuft auf Ihrer Workstation. Es meldet Sie beim Account-Server an, fordert die benötigten Lizenzen an und installiert sie über SSH auf entfernten Maschinen. Wenn Sie einen Repository-Befehl ausführen, stellt `rdc` sicher, dass die erforderlichen Lizenzen vorhanden sind, und validiert sie zur Laufzeit auf der Maschine.

Der normale Ablauf sieht wie folgt aus:

1. Sie authentifizieren sich mit `rdc subscription login`
2. Sie führen einen Repository-Befehl wie `rdc repo create`, `rdc repo up` oder `rdc repo down` aus
3. Wenn die erforderliche Lizenz fehlt oder abgelaufen ist, fordert `rdc` sie von `account` an
4. `rdc` schreibt die signierte Lizenz auf die Maschine
5. Die Lizenz wird lokal auf der Maschine validiert und die Operation wird fortgesetzt

Siehe [rdc vs renet](/en/docs/rdc-vs-renet) für die Aufteilung Workstation/Server und [Repositories](/en/docs/repositories) für den Repository-Lebenszyklus selbst.

Für Automatisierung und KI-Agenten verwenden Sie statt Browser-Login ein bereichsspezifisches Abonnement-Token:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Sie können das Token auch direkt über die Umgebung injizieren, sodass die CLI Repo-Lizenzen ohne interaktiven Login-Schritt ausstellen und aktualisieren kann:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Maschinenplätze und Repo-Lizenzen

### Maschinenplätze (serverseitig)

Das Tracking von Maschinenplätzen wird serverseitig durchgesetzt. Wenn die CLI eine Repo-Lizenz ausstellt, prüft der Account-Server das Maschinenplatz-Kontingent des Abonnements (z.B. 2 Maschinen für Community, 3 für Professional). Ein Platz wird 5 Stunden ab der letzten Repo-Lizenzausstellung auf dieser Maschine gehalten und wird nach Inaktivität automatisch freigegeben. Ein 10-Platz-Business-Plan kann daher im Laufe der Zeit Dutzende von Maschinen abdecken, da Plätze nur während der aktiven Bereitstellung gehalten werden.

Es wird keine Maschinenlizenz auf der Maschine gespeichert. Die Durchsetzung der Plätze erfolgt zum Ausstellungszeitpunkt auf dem Server.

### Repo-Lizenz

Eine Repo-Lizenz ist eine signierte Lizenz für ein Repository auf einer Maschine. Sie ist die einzige auf der Maschine gespeicherte Lizenzdatei (`/var/lib/rediacc/license/repos/{guid}.json`).

Sie wird verwendet für:

- `rdc repo create` und `rdc repo fork`, validiert vor der Bereitstellung (vorab ohne Identitätsnachweise ausgestellt, dann nach der Erstellung mit Identitätsnachweisen neu ausgestellt)
- `rdc repo resize` und `rdc repo expand`, vollständige Validierung einschließlich Ablauf
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, validiert mit **übersprungener Ablaufprüfung**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, validiert mit **übersprungener Ablaufprüfung**
- Repo-Autostart beim Maschinenneustart, validiert mit **übersprungener Ablaufprüfung**

Repo-Lizenzen sind an die Maschine und das Ziel-Repository gebunden. Jede Lizenz enthält die Maschinen-ID, die Repository-GUID, die Abonnement-ID, die Plan-Limits und den Ablauf. Bei verschlüsselten Repositories verifiziert Rediacc auch die LUKS-Identität des zugrunde liegenden Volumes.

Mehrere Abonnements können auf derselben Maschine koexistieren. Jedes Repository trägt seine eigene Lizenz mit seinem eigenen Abonnement-Kontext.

## Standardlimits

Die Repository-Größe hängt vom Berechtigungsniveau ab:

- Community: bis zu `10 GB`
- Kostenpflichtige Pläne: Plan- oder Vertragslimit

Standard-Limits für kostenpflichtige Pläne:

| Plan | Floating-Lizenzen | Repository-Größe | Monatliche Repo-Lizenzausstellungen | Delegierungszert. Standard / Max |
|------|-------------------|------------------|-------------------------------------|---|
| Community | 2 | 10 GB | 100 | 15d / 30d |
| Professional | 3 | 50 GB | 1.000 | 60d / 120d |
| Business | 10 | 200 GB | 10.000 | 90d / 180d |
| Enterprise | 25+ | 1 TB+ | 25.000+ | 120d / 365d |

Vertragsspezifische Limits können diese Werte für einen bestimmten Kunden erhöhen oder verringern. Die Gültigkeit von Delegierungszertifikaten ist zusätzlich auf `subscription.expiresAt + 3 day grace` begrenzt, sodass monatlich abgerechnete Abonnements natürlicherweise Zertifikate erhalten, die auf ihren Abrechnungszeitraum ausgerichtet sind. Siehe [License Chain & Delegation - Validity Policy](/en/docs/license-chain) für die vollständigen Regeln.

## Übergangsfrist für VM-Migration

Wenn ein Hosting-Anbieter einen virtuellen Computer auf andere physische Hardware migriert, ändert sich die Maschinen-ID (sie leitet sich von Hardware-Identifikatoren wie DMI UUID, `/etc/machine-id` und NIC MAC-Adressen ab). Repo-Lizenzen sind an die Maschinen-ID gebunden, daher würde eine Migration normalerweise alle Lizenzen ungültig machen.

Um dies transparent zu handhaben, enthalten Repo-Lizenzen eine **40-Tage-Übergangsfrist für die Maschinen-ID**. Wenn die Maschinen-ID nicht übereinstimmt, aber die Lizenz vor weniger als 40 Tagen ausgestellt wurde, wird die Lizenz weiterhin akzeptiert. Da Lizenzen alle 30 Tage aktualisiert werden, wird die nächste Aktualisierung automatisch an die neue Maschinen-ID gebunden.

In der Praxis:
- VM migriert, Maschinen-ID ändert sich: Repos funktionieren weiterhin (innerhalb des 40-Tage-Fensters)
- Nächste `rdc`-Operation aktualisiert die Lizenz mit der neuen Maschinen-ID
- Keine manuelle Intervention erforderlich
- Maschinen-ID und Lizenzbewertung überprüfen mit `rdc machine query --system --licenses --name <machine>`

**Edge-Kanal-Benutzer** erhalten kostenlos doppelte Community-Limits (20 GB Repos, 1.000 Ausstellungen/Monat, 4 Maschinen). Kostenpflichtige Pläne sind nur im Stable-Kanal verfügbar. Siehe [Release Channels](/en/docs/release-channels) für Details.

## Was bei Repo-Erstellung, -Start, -Stopp und -Neustart passiert

### Repo erstellen und forken

Wenn Sie ein Repository erstellen oder forken:

1. `rdc` stellt sicher, dass Ihr Abonnement-Token verfügbar ist (löst Device-Code-Authentifizierung aus, falls nötig)
2. `rdc` stellt eine Repo-Lizenz vom Account-Server vorab aus (der Server prüft an dieser Stelle das Maschinenplatz-Kontingent und monatliche Ausstellungslimits)
3. Die vorab ausgestellte Repo-Lizenz wird auf die Maschine geschrieben und lokal validiert (Signatur, Maschinen-ID, Repo-GUID, Ablauf und Größenlimit)
4. Nach erfolgreicher Erstellung stellt `rdc` die Repo-Lizenz mit Repository-Identitätsnachweisen neu aus (LUKS-UUID oder Speicherfingerabdruck)

Diese kontogestützte Ausstellung zählt zu Ihrer monatlichen Nutzung der **Repo-Lizenzausstellungen**. Jede Lizenz enthält die E-Mail-Adresse und den Firmennamen des Kontoinhabers, die protokolliert werden, wenn renet die Lizenz validiert.

### Repo starten, stoppen und löschen

`rdc` validiert die installierte Repo-Lizenz auf der Maschine, **überspringt jedoch die Ablaufprüfung**. Signatur, Maschinen-ID, Repository-GUID und Identität werden weiterhin geprüft. Benutzer werden nie vom Betrieb ihrer Repositories ausgesperrt, auch nicht mit einem abgelaufenen Abonnement.

### Repo skalieren und erweitern

`rdc` führt eine vollständige Repo-Lizenz-Validierung einschließlich Ablauf und Größenlimits durch.

### Maschinenneustart und Autostart

Autostart verwendet dieselben Regeln wie `rdc repo up`: die Ablaufprüfung wird übersprungen, sodass Repositories immer frei neu starten.

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
rdc subscription activation status -m hostinger
```

Installierte Repo-Lizenz-Details auf einer Maschine anzeigen:

```bash
rdc subscription repo status -m hostinger
```

Batch-Aktualisierung von Repo-Lizenzen auf einer Maschine:

```bash
rdc subscription refresh repos -m hostinger
```

Repositories, die auf der Maschine entdeckt wurden, aber in der lokalen `rdc`-Konfiguration fehlen, werden bei der Batch-Aktualisierung abgelehnt. Sie werden als Fehler gemeldet und nicht automatisch klassifiziert.

Repo-Lizenz-Aktualisierung für ein vorhandenes Repository erzwingen:

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

Bei der ersten Verwendung kann eine lizenzierte Repo- oder Backup-Operation, die keine verwendbare Repo-Lizenz findet, automatisch eine Konto-Autorisierungs-Übergabe auslösen. Die CLI gibt eine Autorisierungs-URL aus, versucht den Browser in interaktiven Terminals zu öffnen, und wiederholt die Operation einmal nach erfolgreicher Autorisierung und Ausstellung.

In nicht-interaktiven Umgebungen wartet die CLI nicht auf Browser-Genehmigung. Stattdessen fordert sie Sie auf, ein bereichsspezifisches Token mit `rdc subscription login --token ...` oder `REDIACC_SUBSCRIPTION_TOKEN` anzugeben.

Für die erstmalige Maschineneinrichtung siehe [Machine Setup](/en/docs/setup).

## Offline-Verhalten und Ablauf

Die Lizenzvalidierung erfolgt lokal auf der Maschine. Sie benötigen keine Live-Verbindung zum Account-Server.

Das bedeutet:

- Eine laufende Umgebung benötigt bei jedem Befehl keine Live-Kontoverbindung
- Alle Repos können immer gestartet, gestoppt und gelöscht werden, auch mit abgelaufenen Lizenzen, Benutzer werden nie vom Betrieb ihrer eigenen Repositories ausgesperrt
- Bereitstellungsoperationen (`create`, `fork`) erfordern eine vorab ausgestellte Repo-Lizenz, und Wachstumsoperationen (`resize`, `expand`) erfordern eine gültige Repo-Lizenz
- Wirklich abgelaufene Repo-Lizenzen müssen vor Resize/Expand über `rdc` aktualisiert werden
- Lizenzsignaturen werden gegen einen eingebetteten öffentlichen Schlüssel geprüft, die Signaturprüfung kann nicht deaktiviert werden

## Wiederherstellungsverhalten

Die automatische Wiederherstellung ist bewusst eng gefasst:

- `missing`: `rdc` kann bei Bedarf den Kontozugang autorisieren, Repo-Lizenzen im Batch aktualisieren und einmal wiederholen
- `expired`: `rdc` kann Repo-Lizenzen im Batch aktualisieren und einmal wiederholen
- `machine_mismatch`: schlägt sofort fehl und fordert Sie auf, aus dem aktuellen Maschinenkontext neu auszustellen
- `repository_mismatch`: schlägt sofort fehl und fordert Sie auf, Repo-Lizenzen explizit zu aktualisieren
- `sequence_regression`: schlägt sofort fehl als Repo-Lizenz-Integritäts-/Statusproblem
- `invalid_signature`: schlägt sofort fehl als Repo-Lizenz-Integritäts-/Statusproblem
- `identity_mismatch`: schlägt sofort fehl, die Repository-Identität stimmt nicht mit der installierten Lizenz überein

Diese Sofort-Fehlschlag-Fälle verbrauchen nicht automatisch kontogestützte Aktualisierungs- oder Ausstellungsaufrufe.

## Delegierungszertifikate für On-Premise

Für On-Premise- und Air-Gapped-Deployments wird es komplex. Der Upstream-Account-Server stellt ein **Delegierungszertifikat** aus, das Ihre On-Premise-Installation berechtigt, Lizenzen mit ihrem eigenen Ed25519-Schlüssel zu signieren. Das Zertifikat beschränkt Sie auf Ihre Plan-Limits und erstellt eine manipulationssichere Kette.

Wichtige Punkte für Abonnementinhaber:

- **Ein aktives Zertifikat pro Abonnement.** Jede On-Premise-Installation setzt pro Monat und pro Maschine Quoten gegen ihr eigenes lokales Ledger durch, sodass Mehrfachinstallationen das effektive Kontingent vervielfachen würden, ohne dass eine Abstimmung möglich wäre. Kunden, die Produktion + Staging + DR benötigen, müssen ein Abonnement pro Installation erwerben.
- **Planbasierte Standard-Gültigkeit** (15d / 60d / 90d / 120d) und Obergrenzen (30d / 120d / 180d / 365d) - siehe die Limits-Tabelle oben.
- **Self-Service über das Kundenportal.** Org-Inhaber und Admins können Delegierungszertifikate unter `/account/delegation-certs` erstellen, erneuern und widerrufen. Die Seite ist für alle Kunden unabhängig vom Plan sichtbar, nur die Limits unterscheiden sich.
- **Auto-Erneuerung** wird über einen Ein-Klick-Bootstrap unterstützt, der ein `delegation:renew`-bereichsspezifisches API-Token für die On-Premise-Installation ausstellt, das für Upstream-Erneuerungsaufrufe verwendet wird.
- **Air-Gapped-Erneuerung** wird über ein signiertes Erneuerungsanfrage-Manifest unterstützt, das der On-Premise-Administrator herunterlädt, offline zum Upstream überträgt und der Upstream verarbeitet, um ein neues Zertifikat auszustellen.

Siehe [On-Premise Installation - Licensing for Air-Gapped Deployments](/en/docs/on-premise) für die betriebliche Einrichtung und [License Chain & Delegation](/en/docs/license-chain) für das kryptografische Design.

## Monatliche Repo-Lizenzausstellungen

Diese Metrik zählt erfolgreiche kontogestützte Repo-Lizenz-Ausstellungsaktivitäten im aktuellen UTC-Kalendermonat.

Dazu gehören:

- Erstmalige Repo-Lizenzausstellung
- Erfolgreiche Repo-Lizenz-Aktualisierung, die eine neu signierte Lizenz zurückgibt

Nicht dazu gehören:

- Unveränderte Batch-Einträge
- Fehlgeschlagene Ausstellungsversuche
- Nicht verfolgte Repositories, die vor der Ausstellung abgelehnt wurden

Wenn Sie eine kundenseitige Ansicht der Nutzung und des Repo-Lizenz-Ausstellungsverlaufs benötigen, verwenden Sie das Account-Portal. Wenn Sie maschinenseitige Inspektion benötigen, verwenden Sie `rdc subscription activation status -m` und `rdc subscription repo status -m`.
