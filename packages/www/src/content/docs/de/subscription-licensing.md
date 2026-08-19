---
title: Abonnement & Lizenzierung
description: >-
  Erfahren Sie, wie Account, rdc und renet Maschinenplätze, Repo-Lizenzen und
  Planlimits verwalten.
category: Guides
tags:
  - account
order: 7
language: de
sourceHash: "15886ad7ee04e90c"
sourceCommit: "fd9d3476b1fdf0ac6ffaa14f486f20f9642fe2d5"
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

Siehe [rdc vs renet](/de/docs/rdc-vs-renet) für die Aufteilung Workstation/Server und [Repositories](/de/docs/repositories) für den Repository-Lebenszyklus selbst.

Für Automatisierung und KI-Agenten verwenden Sie statt Browser-Login ein bereichsspezifisches Abonnement-Token:

```bash
rdc subscription login --token "$REDIACC_TOKEN"
```

Sie können das Token auch direkt über die Umgebung injizieren, sodass die CLI Repo-Lizenzen ohne interaktiven Login-Schritt ausstellen und aktualisieren kann:

```bash
export REDIACC_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Maschinenplätze und Repo-Lizenzen

### Maschinenplätze (serverseitig)

Das Tracking von Maschinenplätzen wird serverseitig durchgesetzt. Wenn die CLI eine Repo-Lizenz ausstellt, prüft der Account-Server das Maschinenplatz-Kontingent des Abonnements. Jeder Self-Service-Plan (Community, Professional, Business) umfasst einen Maschinenplatz; Multi-Maschinen-Deployments sind ein Enterprise-Setup, das gemeinsam mit unseren Partnern dimensioniert wird. Ein Platz wird 5 Stunden ab der letzten Repo-Lizenzausstellung auf dieser Maschine gehalten und wird nach Inaktivität automatisch freigegeben. Da ein Platz nur während der aktiven Bereitstellung gehalten wird, kann ein einzelner Platz im Laufe eines Monats dennoch mehrere Maschinen abdecken.

Die Obergrenze wird aus Ihrem Abonnementdatensatz gelesen, nicht aus einer fest einprogrammierten Plankonstante. Eine ausgehandelte Aktivierungszahl gilt daher, sobald sie am Abonnement hinterlegt ist. Die Planstufe legt lediglich den Startwert fest.

Ausstellung und Erneuerung werden unterschiedlich durchgesetzt, und dieser Unterschied ist wichtig:

- **Das Ausstellen einer neuen Lizenz blockiert an der Obergrenze.** Ist jeder Platz belegt, schlägt die Anfrage mit `MAX_MACHINES_REACHED` fehl und es wird nichts bereitgestellt.
- **Das Erneuern einer bestehenden Lizenz blockiert nie.** Eine Maschine, die erneuert, während jeder Platz belegt ist, läuft weiter, und ihr Platz wird als über dem Limit vermerkt. Sichtbar ist das im Portal auf der Seite Maschinen, in `rdc subscription status` und im Feld `overLimitCount` der License-Status-API. Die Markierung verschwindet von selbst, sobald die Maschine wieder innerhalb des Limits liegt.

Die Erneuerung ist bewusst der nachsichtigere Weg. Eine Maschine, die eine Lizenz erneuert, die sie ohnehin schon hält, ist keine neue Kapazität, und eine Ablehnung würde Backups auf bereits bezahlter Infrastruktur stoppen. Blockiert bleibt das Hinzufügen von Kapazität.

Es wird keine Maschinenlizenz auf der Maschine gespeichert. Die Durchsetzung der Plätze erfolgt zum Ausstellungszeitpunkt auf dem Server.

### Repo-Lizenz

Eine Repo-Lizenz ist eine signierte Lizenz für ein Repository auf einer Maschine. Sie ist die einzige auf der Maschine gespeicherte Lizenzdatei, angeordnet pro Datastore und pro Signierschlüssel:

```
/var/lib/rediacc/license/repos/{guid}/{keyId}.json
/var/lib/rediacc/license/datastores/{datastoreId}/repos/{guid}/{keyId}.json
```

Repositories auf dem Standardspeicher einer Maschine nutzen den ersten Pfad. Repositories in einem benannten Datastore nutzen den zweiten, wobei `{datastoreId}` die Identität ist, die dieser Datastore bei seiner Erstellung erhalten hat. Genau diese Abgrenzung sorgt dafür, dass ein Datastore-Fork ehrlich abgerechnet wird: Ein geforkter Datastore bekommt eine völlig neue Identität, seine Repositories starten also ohne jede Lizenz, melden bei ihrer ersten lizenzpflichtigen Operation `missing` und bekommen eigene Lizenzen ausgestellt. Ein Repository, dessen Lizenz einen anderen Datastore nennt als den, in dem es liegt, scheitert sofort mit `identity_mismatch`, statt automatisch neu ausgestellt zu werden. Damit lässt sich eine Lizenzdatei nicht seitwärts kopieren.

`{keyId}` ist ein 16-stelliger Hex-Fingerabdruck (die ersten 8 Bytes von `SHA-256` des Ed25519-Öffentlichschlüssels des signierenden Servers). Ein Repository, das von mehr als einem Account-Universum verwaltet wird (zum Beispiel Produktion und Bench, die auf dieselbe Maschine bereitstellen), enthält eine Datei pro Signierschlüssel in seinem `{guid}`-Verzeichnis. Der Renet-Build der Maschine validiert nur die Datei, die sein eingebackener Schlüssel oder ein daran verketteter Delegierungszertifikat verifizieren kann; Dateien anderer Universen sind inert. Der Wechsel zwischen Universen macht Lizenzen nie ungültig: Die erste Operation in einem neuen Universum stellt dessen Lizenz einmal aus (ein `missing`-Ergebnis stellt automatisch aus), und beide koexistieren danach.

Sie wird verwendet für:

- `rdc repo create`, `rdc repo fork` und `rdc repo commit`, validiert vor der Bereitstellung (vorab ohne Identitätsnachweise ausgestellt, dann nach der Erstellung mit Identitätsnachweisen neu ausgestellt, weil das Repository zum Zeitpunkt der Prüfung noch gar nicht existiert)
- `rdc repo resize`, `rdc repo expand`, `rdc repo merge` und `rdc repo promote`, **vollständig validiert einschließlich Ablauf**
- Backup-Übertragung, **vollständig validiert einschließlich Ablauf**: `rdc repo push`, `rdc repo pull`, `rdc repo migrate` und geplante Backups
- `rdc repo up`, `rdc repo up --all`, `rdc repo exec` und Repo-Autostart beim Maschinenneustart, validiert mit **übersprungener Ablaufprüfung und übersprungenem Gültigkeitsfenster des Delegierungszertifikats**
- `rdc repo down`, `rdc repo delete` und lesende Befehle wie das Auflisten von Repos brauchen überhaupt keine Lizenz

Signaturen, Schlüsselbindung, Maschinenbindung, Repository-Bindung und jede Beschränkung des Delegierungszertifikats werden bei all diesen Operationen durchgesetzt. Die letzte Gruppe lockert allein die beiden Zeitfenster, damit eine abgelaufene Lizenz oder ein abgelaufenes Zertifikat Sie nie daran hindern kann, Ihre eigenen Daten zu starten oder herunterzufahren.

Repo-Lizenzen sind an die Maschine und das Ziel-Repository gebunden. Jede Lizenz enthält die Maschinen-ID, die Repository-GUID, die Abonnement-ID, die Plan-Limits und den Ablauf. Bei verschlüsselten Repositories verifiziert Rediacc auch die LUKS-Identität des zugrunde liegenden Volumes.

Mehrere Abonnements können auf derselben Maschine koexistieren. Jedes Repository trägt seine eigene Lizenz mit seinem eigenen Abonnement-Kontext.

## Cluster

Clustering wird über unsere Partner als Teil einer Enterprise-Vereinbarung verkauft. Es ist keine Self-Service-Planoption, und die folgenden Abschnitte beschreiben, wie es abgerechnet wird, nicht, wie man es kauft.

**Ein Knoten ist eine Maschine.** Ein Cluster hat keine eigene Lizenzidentität. Jeder Knoten darin ist eine gewöhnliche Maschine mit installiertem Renet Agent und wird genauso gezählt wie eine einzeln stehende Maschine.

**Es gibt kein Pooling.** Ein Cluster aus fünf Knoten zieht nicht aus einem gemeinsamen Cluster-Platz. Jeder Knoten beansprucht seinen eigenen Platz, sobald das erste Repository auf ihm landet, und dieser Platz folgt derselben 5-Stunden-Regel wie jeder andere: Er wird ab der letzten Repo-Lizenzausstellung auf diesem Knoten 5 Stunden gehalten und danach von selbst wieder freigegeben.

**Den Cluster aufzubauen kostet nichts. Abgerechnet wird das Platzieren von Repositories.** Den Cluster anzulegen, Knoten beitreten zu lassen, die verteilte Speicherschicht zu installieren und die Kubernetes-Steuerungsebene hochzuziehen, kostet keine Plätze. Die Abrechnung beginnt, sobald ein Repository auf einem Knoten landet.

**Ein Cluster-Fork rechnet pro Repository neu ab.** Wird ein ganzer Cluster geforkt, bekommt der geforkte Datastore eine neue Identität. Jedes Repository im Fork erhält deshalb beim ersten Zugriff seine eigene Lizenz, auf dem Knoten, auf dem es gerade läuft. Eine schlichte Migration ist der umgekehrte Fall: Verschieben Sie ein Repository zwischen Maschinen, nimmt es seine Lizenz mit und bleibt gültig, weil sich an seiner Speicheridentität nichts geändert hat.

**Die Erneuerung in einem Cluster folgt der weichen Regel von oben.** Knoten erneuern ihre Lizenzen unbeaufsichtigt selbst. Ein Cluster, der über seine Aktivierungszahl hinausgewachsen ist, läuft also weiter und meldet seine Knoten über dem Limit, statt mitten in der Nacht Backups scheitern zu lassen. Ein neuer Knoten blockiert weiterhin an der Obergrenze.

Einen Cluster zu dimensionieren ist ein Gespräch, kein Häkchen. Aktivierungszahlen für Cluster werden in der Bestellung vereinbart, und Ihr Partner hinterlegt sie direkt am Abonnement. Siehe [Kontakt](/de/contact), um dieses Gespräch zu beginnen.

## Standardlimits

Die Repository-Größe hängt vom Berechtigungsniveau ab:

- Community: bis zu `10 GB`
- Kostenpflichtige Pläne: Plan- oder Vertragslimit

Standard-Limits für kostenpflichtige Pläne:

| Plan | Floating-Lizenzen | Repository-Größe | Monatliche Repo-Lizenzausstellungen | Delegierungszert. Standard / Max |
|------|-------------------|------------------|-------------------------------------|---|
| Community | 1 | 10 GB | 100 | 15d / 30d |
| Professional | 1 | 100 GB | 2.000+ | 60d / 120d |
| Business | 1 | 500 GB | 5.000+ | 90d / 180d |
| Enterprise | Individuell | 1 TB+ | 15.000+ | 120d / 365d |

Vertragsspezifische Limits können diese Werte für einen bestimmten Kunden erhöhen oder verringern. Die Gültigkeit von Delegierungszertifikaten ist zusätzlich auf `subscription.expiresAt + 3 day grace` begrenzt, sodass monatlich abgerechnete Abonnements natürlicherweise Zertifikate erhalten, die auf ihren Abrechnungszeitraum ausgerichtet sind. Siehe [License Chain & Delegation - Validity Policy](/de/docs/license-chain) für die vollständigen Regeln.

## Kostenlose Testphase und der Community-Fallback

Neuanmeldungen starten eine 14-tägige kostenlose Testphase im Plan Professional oder Business. Bei der Anmeldung wird eine Kreditkarte hinterlegt, und die erste Abbuchung erfolgt erst, wenn die Testphase endet, sodass eine Kündigung davor kostenlos ist. Pro Kunde ist eine Testphase verfügbar.

Community ist die dauerhafte kostenlose Grundstufe. Für neue Konten ist sie keine direkte Anmeldeoption mehr; stattdessen landet ein Konto auf Community, sobald ein Abonnement endet: durch Kündigung während der Testphase, spätere Kündigung eines kostenpflichtigen Plans oder eine fehlgeschlagene Zahlung. Im Community-Fallback behalten Sie eine Maschine mit 10 GB pro Repository und 100 Setups pro Monat. Konten, die vor der Einführung des testphasenbasierten Modells erstellt wurden, behalten ihren bestehenden Community-Zugang.

Die Durchsetzung bleibt dort nachsichtig, wo es am meisten zählt: Laufende Repositories funktionieren auch nach Ablauf eines Abonnements weiter (`up`, `down`, `delete`, Autostart). Darüber hinaus gelten zwei verschiedene Regeln, und ihre Verwechslung ist der Grund, warum die 60-tägige Kulanzfrist widersprüchlich wirkt:

- **Operationen, die den Account-Server brauchen**, sind ohne aktives Abonnement nicht möglich, weil der Server die Signatur verweigert. Das sind `create`, `fork` und jede Lizenzaktualisierung oder -erneuerung. Sobald das Abonnement ausläuft, wird nichts Neues mehr bereitgestellt.
- **Operationen, denen eine gültige installierte Lizenz genügt**, funktionieren ohne jeden Serverkontakt weiter, bis diese Lizenz hart abläuft. Das sind `resize` und `expand` an Repositories, die Sie bereits haben, sowie die Backup-Übertragung (`push`, `pull`, geplante Backups). Die primäre Lizenz eines Repositories läuft 60 Tage nach dem Abonnementende hart ab, und genau daher kommt die 60-tägige Kulanzfrist. Die Lizenz eines Forks ist deutlich kurzlebiger und auf 7 Tage begrenzt, weshalb Maschinen mit vielen Forks auf die unten beschriebene Selbsterneuerung angewiesen sind.

Ein ausgelaufenes Abonnement hindert Sie also sofort daran, Ihre Flotte zu vergrößern, und 60 Tage später daran, die Repositories darin wachsen zu lassen.

## Übergangsfrist für VM-Migration

Wenn ein Hosting-Anbieter einen virtuellen Computer auf andere physische Hardware migriert, ändert sich die Maschinen-ID (sie leitet sich von Hardware-Identifikatoren wie DMI UUID, `/etc/machine-id` und NIC MAC-Adressen ab). Repo-Lizenzen sind an die Maschinen-ID gebunden, daher würde eine Migration normalerweise alle Lizenzen ungültig machen.

Um dies transparent zu handhaben, enthalten Repo-Lizenzen eine **40-Tage-Übergangsfrist für die Maschinen-ID**. Wenn die Maschinen-ID nicht übereinstimmt, aber die Lizenz vor weniger als 40 Tagen ausgestellt wurde, wird die Lizenz weiterhin akzeptiert. Da Lizenzen alle 30 Tage aktualisiert werden, wird die nächste Aktualisierung automatisch an die neue Maschinen-ID gebunden.

In der Praxis:
- VM migriert, Maschinen-ID ändert sich: Repos funktionieren weiterhin (innerhalb des 40-Tage-Fensters)
- Nächste `rdc`-Operation aktualisiert die Lizenz mit der neuen Maschinen-ID
- Keine manuelle Intervention erforderlich
- Maschinen-ID und Lizenzbewertung überprüfen mit `rdc machine status <machine> --system --licenses`

**Edge-Kanal-Konten** laufen auf dem Community-Plan mit doppelten Limits (20 GB Repos, 200 Setups/Monat, 2 Maschinen). Kostenpflichtige Pläne sind nur im Stable-Kanal verfügbar. Siehe [Release Channels](/de/docs/release-channels) für Details.

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
rdc subscription login --token "$REDIACC_TOKEN"
```

Für nicht-interaktive Umgebungen ist das Setzen von `REDIACC_TOKEN` die einfachste Option. Das Token sollte nur für die Abonnement- und Repo-Lizenz-Operationen des Agenten berechtigt sein.

Kontogestützten Abonnementstatus anzeigen:

```bash
rdc subscription status
```

Maschinenaktivierungsdetails für eine Maschine anzeigen:

```bash
rdc subscription status -m hostinger
```

Installierte Repo-Lizenz-Details auf einer Maschine anzeigen:

```bash
rdc subscription status -m hostinger
```

Die Lizenz eines Repositories auf einer Maschine aktualisieren:

```bash
rdc subscription refresh -m hostinger --repo my-app
```

Der `--repo`-Ref muss in Ihrer lokalen `rdc`-Konfiguration auflösbar sein. Ein Repository, das auf der Maschine entdeckt wird, aber in der lokalen Konfiguration fehlt, wird abgelehnt: Es wird als Fehler gemeldet und nicht automatisch klassifiziert.

Bei der ersten Verwendung kann eine lizenzierte Repo- oder Backup-Operation, die keine verwendbare Repo-Lizenz findet, automatisch eine Konto-Autorisierungs-Übergabe auslösen. Die CLI gibt eine Autorisierungs-URL aus, versucht den Browser in interaktiven Terminals zu öffnen, und wiederholt die Operation einmal nach erfolgreicher Autorisierung und Ausstellung.

In nicht-interaktiven Umgebungen wartet die CLI nicht auf Browser-Genehmigung. Stattdessen fordert sie Sie auf, ein bereichsspezifisches Token mit `rdc subscription login --token ...` oder `REDIACC_TOKEN` anzugeben.

Für die erstmalige Maschineneinrichtung siehe [Machine Setup](/de/docs/setup).

## Selbsterneuerung von Lizenzen

Alles bisher Beschriebene setzt voraus, dass Sie an der Tastatur sitzen. Geplante Backups tun das nicht, und genau für diesen Fall gibt es die Selbsterneuerung.

Ein geplantes Backup wird auf der strengen Stufe validiert und braucht daher eine Lizenz, die nicht abgelaufen ist. Die Lizenz eines Forks ist auf 7 Tage begrenzt. Ihre Maschinen halten aus Prinzip keine Account-Zugangsdaten, deshalb blieb das Backup eines Forks vor der Selbsterneuerung eine Woche nach dessen Erstellung einfach stehen, klanglos, um drei Uhr morgens.

### Wie sich eine Maschine ohne Token erneuert

Jede Lizenz, die Rediacc ausstellt oder erneuert, trägt eine `renewalUrl`, die vollständige Adresse des Erneuerungsendpunkts auf dem Account-Server, der sie signiert hat. Eine Maschine liest diese Adresse aus ihrer eigenen installierten Lizenz und muss daher nie erfahren, wo ihr Account-Server steht.

Anschließend legt die Maschine die installierte Lizenz genau diesem Endpunkt wieder vor. Die Lizenz ist ihr eigener Berechtigungsnachweis: Sie ist signiert, der Server prüft diese Signatur, und an keiner Stelle ist ein API-Token beteiligt. Der Server gibt eine frische Lizenz mit neuen Gültigkeitsfenstern zurück, und die Maschine installiert und validiert sie erneut, bevor sie die Erneuerung als erledigt betrachtet.

Die Erneuerung ist eine maschinenweite Operation:

```bash
sudo renet license renew
```

Repositories werden nach dem Server gruppiert, der sie signiert hat, sodass eine Maschine, die zwei Account-Universen bedient, jedes davon genau einmal kontaktiert. Eine Lock-Datei verhindert, dass zwei Erneuerungen gleichzeitig laufen, und `--jitter` verteilt eine Flotte von Maschinen, die sonst alle zur vollen Stunde aufwachen würden.

Der Server verweigert eine Erneuerung in drei Fällen, und jeder bedeutet etwas anderes:

| Ablehnung | Was sie bedeutet |
|---|---|
| Das Abonnement ist ausgelaufen, ausgesetzt oder über seine Kulanzfrist hinaus | Abrechnung. Die Erneuerung läuft von selbst wieder an, sobald das Abonnement wieder aktiv ist |
| Das Delegierungszertifikat ist abgelaufen oder widerrufen | On-Premise-Einrichtung. Erneuern Sie das Zertifikat auf Ihrem On-Premise-Server, danach erneuern die Maschinen wieder normal |
| Die Maschinenidentität passt nicht mehr und die 40-Tage-Kulanzfrist ist vorbei | Die Lizenz gehört zu einer Maschine, die diese hier nicht ist. Stellen Sie sie aus dem aktuellen Maschinenkontext neu aus |

Eine Ablehnung stoppt nie den gesamten Lauf. Ein einzelnes ausgelaufenes Repository blockiert nicht die Erneuerung der übrigen auf derselben Maschine.

### Geplante Backups erneuern sich selbst

Jede Backup-Unit, die Rediacc schreibt, führt zuerst eine Erneuerung aus:

```
ExecStartPre=-<renet> license renew --jitter 45s
```

Das führende `-` kennzeichnet den Schritt bewusst als Best-Effort. Eine abgelehnte Erneuerung, ein Netzwerkaussetzer oder ein älterer Renet Agent, der den Befehl noch nicht kennt, darf niemals das Backup selbst zu Fall bringen. Das Backup läuft, und die Lizenz wird dabei erneuert, wann immer es möglich ist.

### Wenn ein Backup blockiert wird

Verweigert die Lizenzierung tatsächlich ein Backup, hält die Maschine das fest. Diese Markierung ist das einzige Signal dafür, dass unbeaufsichtigte Backups keine Daten mehr kopieren, und wird deshalb deutlich sichtbar gemacht:

```bash
rdc machine status <machine> --licenses
```

Die Spalte `backups` zeigt dann `BLOCKED` samt Grund, und dieselbe Information wird unter der Tabelle als Fehler ausgegeben, damit sie zwischen dreißig Repositories nicht untergeht. Die Spalte `renewed` zeigt, wie die letzte unbeaufsichtigte Erneuerung verlaufen ist, einschließlich des Ablehnungscodes des Servers, falls es einen gab. Daran erkennen Sie, ob die Lösung eine Abrechnungsfrage oder eine Frage des On-Premise-Zertifikats ist.

Eine erfolgreiche Erneuerung löscht die Markierung, und ein Backup, das seine Lizenzprüfung besteht, ebenso. Es gibt nichts von Hand zu bestätigen oder zurückzusetzen.

## Offline-Verhalten und Ablauf

Die Lizenzvalidierung erfolgt lokal auf der Maschine. Sie benötigen keine Live-Verbindung zum Account-Server.

Das bedeutet:

- Eine laufende Umgebung benötigt bei jedem Befehl keine Live-Kontoverbindung
- Alle Repos können immer gestartet, gestoppt und gelöscht werden, auch mit abgelaufenen Lizenzen, Benutzer werden nie vom Betrieb ihrer eigenen Repositories ausgesperrt
- Bereitstellungsoperationen (`create`, `fork`) erfordern eine vorab ausgestellte Repo-Lizenz, und Wachstumsoperationen (`resize`, `expand`) erfordern eine gültige Repo-Lizenz
- Wirklich abgelaufene Repo-Lizenzen müssen vor Resize/Expand ersetzt werden, entweder über `rdc` von Ihrer Workstation aus oder indem die Maschine sich selbst erneuert
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
- `cert_expired`: schlägt bei Wachstumsoperationen (`create`, `fork`, `resize`) und beim Backup-Transfer (`push`, `pull`) sofort fehl; `repo up` und Autostart funktionieren weiterhin, passend zum weichen Lizenzablaufmodell. Erneuern Sie das Delegierungszertifikat
- `cert_invalid`: schlägt sofort fehl, das Delegierungszertifikat hat eine Beschränkung nicht erfüllt (ungültige Master-Key-Signatur, Abonnement-/Plan-Mismatch, Größenobergrenze oder Sequenz über `maxTotalIssuances`). Stellen Sie das Zertifikat nach Behebung der zugrunde liegenden Beschränkung neu aus

Diese Sofort-Fehlschlag-Fälle verbrauchen nicht automatisch kontogestützte Aktualisierungs- oder Ausstellungsaufrufe.

Zwei Hinweise zum Lesen dieser Liste:

- `missing` ist nicht immer ein Problem. Es ist auch das normale Ergebnis beim ersten Zugriff auf ein Repository in einem frisch geforkten Datastore, und genau das lässt diesen Fork abrechnen: Die Lizenz wird ausgestellt, ein Platz wird beansprucht, und die Operation läuft weiter. `identity_mismatch` ist der bewusste Gegenfall, damit eine aus einem anderen Datastore kopierte Lizenzdatei sofort fehlschlägt, statt stillschweigend neu ausgestellt zu werden.
- Diese Liste beschreibt die Wiederherstellung von Ihrer Workstation aus. Eine Maschine, die sich selbst erneuert, hat eigene Ergebnisse, die über `rdc machine status <machine> --licenses` gemeldet und nicht als Befehlsfehler ausgelöst werden, denn ein geplantes Backup hat niemanden, dem es etwas sagen könnte.

## Delegierungszertifikate für On-Premise

Für On-Premise- und Air-Gapped-Deployments wird es komplex. Der Upstream-Account-Server stellt ein **Delegierungszertifikat** aus, das Ihre On-Premise-Installation berechtigt, Lizenzen mit ihrem eigenen Ed25519-Schlüssel zu signieren. Das Zertifikat beschränkt Sie auf Ihre Plan-Limits und erstellt eine manipulationssichere Kette.

Wichtige Punkte für Abonnementinhaber:

- **Ein aktives Zertifikat pro Abonnement.** Jede On-Premise-Installation setzt pro Monat und pro Maschine Quoten gegen ihr eigenes lokales Ledger durch, sodass Mehrfachinstallationen das effektive Kontingent vervielfachen würden, ohne dass eine Abstimmung möglich wäre. Kunden, die Produktion + Staging + DR benötigen, müssen ein Abonnement pro Installation erwerben.
- **Planbasierte Standard-Gültigkeit** (15d / 60d / 90d / 120d) und Obergrenzen (30d / 120d / 180d / 365d) - siehe die Limits-Tabelle oben.
- **Self-Service über das Kundenportal.** Org-Inhaber und Admins können Delegierungszertifikate unter `/account/delegation-certs` erstellen, erneuern und widerrufen. Die Seite ist für alle Kunden unabhängig vom Plan sichtbar, nur die Limits unterscheiden sich.
- **Auto-Erneuerung** wird über einen Ein-Klick-Bootstrap unterstützt, der ein `delegation:renew`-bereichsspezifisches API-Token für die On-Premise-Installation ausstellt, das für Upstream-Erneuerungsaufrufe verwendet wird.
- **Air-Gapped-Erneuerung** wird über ein signiertes Erneuerungsanfrage-Manifest unterstützt, das der On-Premise-Administrator herunterlädt, offline zum Upstream überträgt und der Upstream verarbeitet, um ein neues Zertifikat auszustellen.

Siehe [On-Premise Installation - Licensing for Air-Gapped Deployments](/de/docs/on-premise) für die betriebliche Einrichtung und [License Chain & Delegation](/de/docs/license-chain) für das kryptografische Design.

## Monatliche Repo-Lizenzausstellungen

Diese Metrik zählt erfolgreiche kontogestützte Repo-Lizenz-Ausstellungsaktivitäten im aktuellen UTC-Kalendermonat.

Dazu gehören:

- Erstmalige Repo-Lizenzausstellung
- Erfolgreiche Repo-Lizenz-Aktualisierung, die eine neu signierte Lizenz zurückgibt

Nicht dazu gehören:

- Unveränderte Batch-Einträge
- Fehlgeschlagene Ausstellungsversuche
- Nicht verfolgte Repositories, die vor der Ausstellung abgelehnt wurden

Wenn Sie eine kundenseitige Ansicht der Nutzung und des Repo-Lizenz-Ausstellungsverlaufs benötigen, verwenden Sie das Account-Portal. Wenn Sie maschinenseitige Inspektion benötigen, verwenden Sie `rdc subscription status -m` und `rdc subscription status -m`.
