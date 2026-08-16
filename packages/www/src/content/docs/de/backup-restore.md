---
title: "Backup & Wiederherstellung"
description: "Sichern Sie verschlüsselte Repositories per Snapshot in inhaltsadressiertem Chunk-Storage, wo nur geänderte Zellen hochgeladen werden und sich jeder Snapshot direkt wiederherstellen lässt. Oder bewahren Sie eine Kopie auf einer anderen Maschine auf. Stellen Sie überall wieder her und automatisieren Sie es mit benannten Strategien und systemd-Timern."
category: "Guides"
order: 7
language: de
sourceHash: "91f6072e230b059c"
sourceCommit: "79c84ad044d5730b6d0a20aaf7b21f21914b6bda"
---

# Backup & Wiederherstellung

Rediacc sichert verschlüsselte Repositories und stellt sie auf derselben oder einer anderen Maschine wieder her. Backups sind verschlüsselt, weil das Repository es ist: Was die Maschine verlässt, ist der Chiffretext, und das LUKS-Credential Ihres Repositories wird zur Wiederherstellung benötigt.

Es gibt zwei Wege zu sichern, und sie beantworten unterschiedliche Fragen.

- **Snapshots in den Chunk-Storage** (`rdc backup snapshot`) bewahren eine Historie, durch die Sie zurückgehen können. Das ist der Hauptweg.
- **Eine Kopie auf einer anderen Maschine** (`rdc repo push`, `rdc repo pull`) bewahrt das Repository so, wie es jetzt ist, auf Hardware, die Sie kontrollieren. Kein Cloud-Konto ist beteiligt.

Sie sind unabhängig voneinander. Ein Repository, das auf die eine Weise gesichert wurde, ist nicht auf die andere Weise gesichert.

## Wie Snapshots funktionieren

Das Repository-Image wird auf einem festen Raster in Zellen fester Größe geschnitten. Jede Zelle ist entweder ein Loch, das heißt, dort wurde nie etwas geschrieben, oder sie wird unter einem Schlüssel gespeichert, der **der** SHA-256-Wert des Chiffretexts dieser Zelle ist.

Aus dieser einen Entscheidung ergeben sich die Eigenschaften.

**Nur echte Änderungen kosten etwas.** Der erste Snapshot lädt jede beschriebene Zelle hoch. Jeder Lauf danach fragt das Dateisystem, welche Extents berührt wurden, liest und hasht nur diese und lädt nur die Zellen hoch, die der Store noch nicht hat. Ein Repository, dessen Daten sich kaum bewegt haben, lädt fast nichts hoch, und der Lauf dauert Minuten statt so lange, wie das Image groß ist.

**Identische Daten werden einmal gespeichert.** Da der Schlüssel der Inhalts-Hash ist, teilen sich zwei Snapshots, die eine Zelle gemeinsam haben, dasselbe Objekt, und das gilt auch für ein Repository und seine [Forks](/de/docs/tutorial-forking): Eine Fork-Familie sichert gegen eine einzige Abstammungslinie, statt ihren Parent zu duplizieren.

**Einen alten Snapshot wiederherzustellen ist nicht langsamer als einen aktuellen.** Es gibt keine Kette von Inkrementen, die durchgespielt werden muss. Die Wiederherstellung löst den Snapshot in eine vollständige Liste von Zellen auf und ruft diese Zellen direkt ab, sodass die Wiederherstellungszeit von der Größe des Images und Ihrer Bandbreite abhängt, nicht davon, wie lange Sie schon Backups machen. Löcher bleiben Löcher, sodass ein sparse Image sparse wiederhergestellt wird, und eine Zelle, die mehrfach im Image vorkommt, wird nur einmal heruntergeladen.

**Jeder Snapshot steht für sich.** Es gibt kein "Vollbackup", das Sie nicht verlieren dürfen, und kein Fenster, in dem ein defektes Inkrement die folgenden ungültig macht. Jeder Snapshot in der Liste ist direkt wiederherstellbar.

**Verifizierung heißt erneut hashen, nicht vertrauen.** Da der Schlüssel der Hash des Inhalts ist, bedeutet die Prüfung eines Backups, Zellen abzurufen und zu hashen. `rdc backup verify` prüft stichprobenartig; `rdc backup verify --deep` hasht jede erfasste Zelle erneut.

**Ein unterbrochener Lauf ist nicht verloren.** Der Upload setzt fort, ohne bereits angekommene Zellen erneut zu senden, und ein Neustart einer unterbrochenen Wiederherstellung hasht erneut, was bereits auf der Platte liegt, und nutzt es wieder, statt es erneut herunterzuladen.

### Was es Sie kostet

Das Kontingent wird in **physisch eindeutig gespeicherten Bytes** gezählt: was nach Deduplizierung tatsächlich gehalten wird, nicht die Summe dessen, was Ihre Snapshots logisch darstellen. Dreißig Snapshots eines Repositorys, das sich nur langsam ändert, kosten fast wie einer. `rdc backup usage` zeigt gespeicherte Bytes gegen Ihr Kontingent, eine Zahl pro Abonnement, die bei 10 GB im Community-Plan beginnt.

### Was Snapshots brauchen

Der Snapshot-Upload läuft über den Account-Server, der jeden Lauf gegen die installierte Lizenz des Repositorys autorisiert und der Maschine eine kurzlebige Berechtigung zum Schreiben aushändigt. Dieser Weg braucht also einen Account-Server, den die Maschine erreichen kann, und ein lizenziertes Repository. Ohne diese wird der Snapshot zurückgewiesen statt still übersprungen, und `rdc backup manifests`, `rdc backup usage` und `rdc backup retention` haben nichts zu lesen.

Das gilt auch für `--dry-run`. Die Lizenz wird gelesen, bevor der Lauf entscheidet, ob er plant oder hochlädt, sodass ein Probelauf eine Vorschau der Arbeit ist, kein Weg, den Befehl ohne Credentials auszuprobieren.

Maschine-zu-Maschine-Push und -Pull brauchen keins von beidem. Sie sind eine direkte Übertragung zwischen zwei Maschinen, die bereits in Ihrer Konfiguration stehen.

### Was ein Snapshot nicht verspricht

- **Ein Snapshot deckt ein Repository ab, nicht Ihre ganze Maschine auf einmal.** Jedes Repository wird zu seinem eigenen Zeitpunkt erfasst. Wenn zwei Repositories voneinander abhängen, sind ihre Snapshots kein koordiniertes Paar.
- **Es ist keine kontinuierliche Replikation.** Ein Snapshot ist ein Zeitpunkt, den Sie erfasst haben, und Sie können alles verlieren, was seit dem letzten geschrieben wurde. Wie viel das ist, hängt davon ab, wie oft Sie laufen lassen.
- **Gespeicherte Objekte sind write-once, nicht zertifiziertes WORM.** Zellen werden mit einer Nur-Erstellen-Bedingung geschrieben, die Berechtigung, die eine Maschine erhält, kann nichts löschen, und Löschungen geschehen serverseitig nach Aufbewahrungsrichtlinie. Das ist eine echte Barriere dagegen, dass eine kompromittierte Maschine ihre eigenen Backups zerstört. Es ist keine Compliance-Zertifizierung, und es wird nicht als eine geprüft.

### Der rclone-Speicherpfad ist verschwunden

`rdc repo push --to <storage>` und Verwandte kopierten früher eine ganze Backup-Datei zu einem Cloud-Anbieter, den Sie selbst registrierten. Diese verweigern jetzt ein Speicherziel und nennen ihren Ersatz. Die Maschine-zu-Maschine-Übertragung lief nie über rclone und ist unbetroffen. Wenn Sie noch ein auf diese Weise geschriebenes Archiv lesen müssen, siehe [Ein vor der Umstellung geschriebenes Archiv lesen](#ein-vor-der-umstellung-geschriebenes-archiv-lesen).

### Chunk-Storage-Befehle

```bash
# Snapshot hochladen. Der erste Lauf sät, spätere Läufe senden nur geänderte Zellen.
rdc backup snapshot my-app

# Planen, ohne hochzuladen: zeigt, was sich bewegen würde.
rdc backup snapshot my-app --dry-run

# Container stoppen, einfrieren, neu starten, dann hochladen.
rdc backup snapshot my-app --cold

# Dem lokalen Anker misstrauen und das vollständige Inventar neu hochladen.
# Dies lädt alles neu hoch und belastet erneut das Kontingent; nur verwenden,
# wenn der Anker nachweislich fehlerhaft ist.
rdc backup snapshot my-app --reseed

# Das gespeicherte Inventar und Ihr Kontingent prüfen.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

| Option | Beschreibung |
|--------|-------------|
| `<repo-ref>` (positional) | Zu sicherndes Repository |
| `--dry-run` | Nur planen: kein Upload. Zeigt, was sich bewegen würde |
| `--cold` | Container stoppen, einfrieren, neu starten, dann hochladen. Nicht mit `--dry-run` kombinierbar |
| `--reseed` | Dem lokalen Anker misstrauen und ein vollständiges Inventar hochladen. Lädt alles neu hoch und belastet das Kontingent erneut |
| `--debug` | Ausführliche Ausgabe aktivieren |

## Cold-Snapshots (`--cold`)

Ein Cold-Snapshot stoppt ein Repository, bevor es eingefroren wird. Das gespeicherte Image ist damit anwendungskonsistent statt nur absturzkonsistent. Der Befehl läuft auf der Maschine selbst:

```bash
# Jedes Repository auf dem Standard-Datastore.
sudo renet backup snapshot --cold

# Nur die genannten Repositories. --repo nimmt eine Repository-GUID und ist wiederholbar.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` lässt sich nicht mit `--dry-run` kombinieren. Ein Probelauf, der Container stoppt, ist kein Probelauf, und einer, der es nicht tut, ist nicht cold. Deshalb weist renet die Kombination zurück, statt sich selbst für eine Bedeutung zu entscheiden.

### Was bei einem Cold-Lauf passiert

Für jedes ausgewählte Repository, in dieser Reihenfolge:

1. Seine Container stoppen.
2. Repository-Mount und Datastore auf die Platte schreiben.
3. Prüfen, dass die Container wirklich gestoppt sind.
4. Einen Copy-on-Write-Reflink des Repository-Images anlegen.
5. Die Container wieder starten.

Erst danach beginnt der Upload, und zwar mit längst wieder laufenden Repositories.

Die Ausfallzeit ist das Einfrieren, nicht die Übertragung. Ein Reflink besteht nur aus Metadaten und dauert deshalb gleich lang, ob das Repository 1 GB oder 100 GB hält. Beim Upload ist das anders: er wächst mit den geänderten Bytes, und der erste Snapshot lädt das gesamte nicht-leere Inventar hoch. Container bis zum Ende des Uploads unten zu halten, würde die Ausfallzeit an die Datenmenge koppeln, was bei einer Erstsicherung Stunden statt Millisekunden bedeutet.

Alle ausgewählten Repositories werden in einem gemeinsamen Fenster gestoppt, nicht nacheinander. Das kostet pro Repository etwas mehr Ausfallzeit und bringt dafür einen einzigen Konsistenzpunkt über den ganzen Satz.

Ein Repository ohne laufende Container ist bereits ruhig. Es wird ganz ohne Ausfallzeit gesichert, und das ist ein normales Ergebnis, kein Fehler.

### Was die Ausfallzeit kostet

Auf einer echten Maschine gemessen betrug die gesamte Ausfallzeit **222 ms**:

| Phase | Gemessen | Was passiert |
|-------|----------|--------------|
| `cold_down` | 64 ms | Container stoppen |
| `cold_sync` | 26 ms | Repository-Mounts und Datastore werden auf die Platte geschrieben |
| `cold_verify` | 31 ms | Container werden als gestoppt bestätigt |
| `cold_stage` | 0 ms | Reflink des Repository-Images |
| `cold_up` | 99 ms | Container starten wieder |

Der Neustart der Container dominiert, und das Staging ist praktisch kostenlos: der Reflink taucht in Millisekunden-Auflösung gar nicht erst auf. Lesen Sie diese Null aber neben den Datensätzen der einzelnen Repositories und nicht für sich allein. Ein Lauf, der jedes Repository zurückgewiesen hat, meldet ebenfalls `cold_stage=0ms`, und nur die Datensätze sagen, welcher der beiden Fälle vorliegt.

Die Aufschlüsselung ist der Beleg, keine Dekoration. Keine dieser fünf Phasen liest oder sendet Repository-Daten, also wächst auch keine davon mit dem Backup. Der Teil, der wächst, ist der Upload, und der läuft erst, wenn die Ausfallzeit schon vorbei ist.

renet gibt dieselben Werte am Ende eines Laufs aus, sodass Sie Ihre eigenen Maschinen messen können statt uns zu glauben:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

Der JSON-Datensatz jedes Repositorys trägt dieselbe Ausfallzeit und dieselben Phasen, sodass später erkennbar bleibt, ob ein Snapshot cold oder hot entstanden ist, ohne es aus Zeiten zu erraten.

### Wann Sie cold wählen sollten

Hot ist die Voreinstellung und für die meisten Repositories die richtige Wahl. Ein Hot-Snapshot ist absturzkonsistent, also in dem Zustand, in dem ein Repository nach einem Stromausfall wäre, und kostet gar keine Ausfallzeit. Die meisten Datenbanken und Queues kommen damit von allein zurecht.

Cold ist für Daten gedacht, die sich während des Schreibens nicht sicher erfassen lassen. Eine Datenbank mit eigenem Write-Ahead-Log und Zustand im Arbeitsspeicher ist der klassische Fall. Sie tauschen eine kurze, gemessene Ausfallzeit gegen einen Snapshot, den die Anwendung ohne vorherige Reparatur öffnen kann.

### Was ein Cold-Lauf zurückweist

Das Zurückweisen ist das Feature. Ein Backup mit dem Etikett cold, das nie etwas stillgelegt hat, ist eine Lüge, die erst beim Restore auffliegt. Deshalb stuft renet einen Cold-Lauf nie stillschweigend auf hot herunter:

- **Container, die nicht gestoppt sind.** Nach dem Stoppen fragt renet den Docker-Socket des Repositorys, ob dort noch etwas läuft. Wenn ja, wird dieses Repository zurückgewiesen statt gesichert. Die Prüfung entscheidet im Zweifel gegen den Lauf: Ist der Socket nicht erreichbar oder die Containerliste nicht lesbar, gilt die Stilllegung als unbestätigt, und unbestätigt wird zurückgewiesen.
- **Eine Lizenz, die sich nicht lesen lässt.** Lizenzen werden vor der Ausfallzeit geprüft, nicht danach, denn ein Repository mit unlesbarer Lizenz hätte ohnehin nie etwas hochladen können. Ein solches Repository wird übersprungen, ohne gestoppt zu werden. Hat kein einziges der ausgewählten Repositories eine lesbare Lizenz, wird der ganze Lauf zurückgewiesen, bevor auch nur ein Container heruntergefahren wird.
- **Ein zweiter Cold-Lauf auf demselben Datastore.** Die Sperre gilt für den ganzen Datastore, und eine belegte Sperre wird sofort zurückgewiesen, ohne irgendetwas gestoppt zu haben. Zwei überlappende Läufe würden jeweils Container stoppen, die der andere für seine hält, und der zweite würde Repositories starten, die der erste noch einfriert. Den Lauf auszulassen und auf den nächsten zu warten, ist besser.

Wird ein Lauf unterbrochen, während die Container unten sind, etwa durch ein `systemctl stop` oder einen Neustart, startet renet sie vor dem Beenden wieder. Die Wiederherstellung auf der Maschine ist der Rückhalt: Sie erkennt ein Cold-Backup, dessen Besitzer verschwunden ist, und fährt diese Repositories wieder hoch.

## Ein Backup auf eine andere Maschine übertragen

Ein Repository per SSH auf eine zweite Maschine kopieren:

```bash
rdc repo push my-app --to server-1
```

`--to <machine>` löst das Ziel aus Ihrer Konfiguration auf, und `--to-machine <machine>` sagt dasselbe explizit. Ein Speichername wird zurückgewiesen: Dieser Pfad ist eingestellt.

Das verschlüsselte Image wird mit der GLEICHEN GUID kopiert, es handelt sich also um ein Backup oder eine Migration, nicht um einen Fork. Für eine unabhängige Kopie zuerst `rdc repo fork` ausführen und dann den Fork übertragen.

Die erste Übertragung trägt das gesamte Image. Jede folgende Übertragung sendet nur die geänderten Blöcke gegen ein unveränderliches Basis-Image, das auf beiden Maschinen gehalten wird, ohne dass Sie Flags setzen müssen. `--delta-base <guid>` benennt diese Basis selbst, falls nötig.

Die übertragene Kopie landet auf dem Ziel als Backup-Artefakt statt als laufendes Repository. Machen Sie mit `rdc backup restore` ein laufendes daraus:

```bash
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

Für ein Backup zu einem bestimmten Zeitpunkt stattdessen Chunk-Storage verwenden: `rdc backup snapshot my-app` lädt nur die geänderten Zellen hoch, und `rdc backup restore my-app --at <snapshot>` holt jede davon zurück.

| Option | Beschreibung |
|--------|-------------|
| `<ref>` (positional) | Zu übertragender Repository-Ref |
| `--to <remote>` | Zielmaschine oder -cluster |
| `--to-machine <machine>` | Zielmaschine, explizit angegeben |
| `--provision <provider>` | Zielmaschine über diesen Cloud-Anbieter bereitstellen, falls sie nicht existiert |
| `--checkpoint` | CRIU-Checkpoint vor dem Übertragen erstellen (für Container mit Label `rediacc.checkpoint=true`). Ziel stellt automatisch bei `repo up` wieder her |
| `--force` | Ein vorhandenes Backup überschreiben |
| `--bwlimit <limit>` | Bandbreitenlimit für den rsync-Transfer (z. B. `10M`, `500K`) |
| `--delta-base <guid>` | Nur geänderte Blöcke gegenüber dieser unveränderlichen Basis-GUID übertragen. Weglassen für automatische Basis |
| `--strategy <strategy>` | Block-Delta-Strategie bei Verwendung einer Delta-Basis: `auto`, `physical` oder `shared` |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Neustart des Route-Servers nach der Operation überspringen |

## Ein Backup von einer anderen Maschine abrufen

Ein Repository von der Maschine zurückholen, auf der es liegt:

```bash
rdc repo pull my-app --from server-1
```

`--up` hinzufügen, um es im selben Befehl einzuhängen und bereitzustellen. Um stattdessen aus dem Chunk-Storage wiederherzustellen, `rdc backup restore my-app --at <snapshot-id>` verwenden.

Pull verweigert das Überschreiben eines Repositorys, das aktuell **eingehängt** ist. Hängen Sie es zuerst aus, führen Sie den Pull aus, und bringen Sie es anschließend mit `rdc repo up` wieder hoch. Verzeichnisbasierte Repositories sind die Ausnahme: Sie synchronisieren sich im eingehängten Zustand direkt an Ort und Stelle.

| Option | Beschreibung |
|--------|-------------|
| `<ref>` (positional) | Abzurufender Repository-Ref |
| `--from <remote>` | Quellmaschine oder -cluster |
| `--from-machine <machine>` | Quellmaschine, explizit angegeben |
| `--force` | Vorhandenes lokales Backup überschreiben |
| `--up` | Repository nach dem Abrufen einhängen und bereitstellen |
| `--bwlimit <limit>` | Bandbreitenlimit für den rsync-Transfer (z. B. `10M`, `500K`) |
| `--delta-base <guid>` | Nur geänderte Blöcke gegenüber dieser unveränderlichen Basis-GUID empfangen |
| `--strategy <strategy>` | Block-Delta-Strategie bei Verwendung einer Delta-Basis: `auto`, `physical` oder `shared` |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Neustart des Route-Servers nach der Operation überspringen |

## Backups auflisten

Die Snapshots im Chunk-Storage auflisten:

```bash
rdc backup manifests my-app
```

Jede Zeile ist ein gespeicherter Zeitpunkt:

| Spalte | Bedeutung |
|---|---|
| `Repo` | Repository-Name, aufgelöst aus Ihrer lokalen Konfiguration (Fallback auf GUID für Repos, die nicht in der Konfiguration sind) |
| `Snapshot` | Die Snapshot-ID. Das nimmt `rdc backup restore --at` entgegen |
| `Created` | UTC-Zeit, zu der der Snapshot erstellt wurde |
| `Total` | Größe des Repository-Images, das dieser Snapshot repräsentiert |
| `Added` | Bytes, die dieser Snapshot tatsächlich zusätzlich zu den vorherigen hochgeladen hat |
| `Chunks` | Wie viele Zellen er hinzugefügt hat |

Um zu sehen, was ein `rdc repo push --to <machine>` auf dem Ziel hinterlassen hat, fragen Sie diese Maschine, was sie vorhält:

```bash
rdc repo list --machine server-1
```

Die übertragene Kopie erscheint unter ihrem eigenen Namen. Eine zweite Zeile mit einer rohen GUID daneben ist die aufbewahrte Delta-Basis, die den nächsten Push zu dieser Maschine inkrementell statt vollständig macht.

`rdc backup list --machine <machine>` liest die Ordner `hot/` und `cold/`, in die geplante Läufe schreiben. Es ist also das falsche Werkzeug für eine Kopie, die ein Push dort abgelegt hat, und zeigt Ihnen nichts.

| Spalte | Bedeutung |
|---|---|
| `Mode` | `hot` oder `cold`. In welchem Ordner für geplante Backups dieser Eintrag liegt |
| `Name` | Repository-Name, aufgelöst aus Ihrer lokalen Konfiguration (Fallback auf GUID für Repos, die nicht in der Konfiguration sind) |
| `GUID` | Die Repository-GUID auf der Festplatte |
| `Size` | Menschenlesbare Größe der Backup-Datei |
| `Modified` | UTC-Zeitstempel der Datei auf der Maschine |

Das Auflisten eines Storage-Backends wurde eingestellt, zusammen mit dem rclone-Zweig; der Befehl verweigert die Ausführung und nennt diese beiden Ersatzbefehle.

## Aufbewahrung

Der Server erzwingt eine Aufbewahrungsrichtlinie pro Repository über den Chunk-Store, sodass alte Snapshots bereinigt werden, ohne dass Sie von Hand etwas löschen. Ohne deklarierte Richtlinie wird jeder Snapshot behalten.

```bash
# Was gerade durchgesetzt wird.
rdc backup retention my-app

# Ein rollierendes Fenster behalten: 7 täglich, 4 wöchentlich, 6 monatlich.
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Zurück dazu, alles zu behalten.
rdc backup retention clear my-app
```

| Option | Beschreibung |
|--------|-------------|
| `--keep-last <n>` | Diese Anzahl der neuesten Snapshots behalten |
| `--keep-hourly <n>` | Den neuesten Snapshot aus jeder dieser Stunden behalten |
| `--keep-daily <n>` | Den neuesten Snapshot aus jedem dieser Tage behalten |
| `--keep-weekly <n>` | Den neuesten Snapshot aus jeder dieser Wochen behalten |
| `--keep-monthly <n>` | Den neuesten Snapshot aus jedem dieser Monate behalten |
| `--keep-yearly <n>` | Den neuesten Snapshot aus jedem dieser Jahre behalten |

Geben Sie mindestens eine Regel an. `set` ohne Regeln wird zurückgewiesen statt als "nichts behalten" behandelt zu werden, denn eine Richtlinie zu löschen ist es, wofür `clear` da ist.

## Wiederherstellung

`rdc backup restore` verwandelt ein Backup in ein laufendes Repository, und es ist derselbe Befehl für beide Wege. Was sich unterscheidet, ist, worauf Sie ihn richten.

```bash
# Ein Zeitpunkt aus dem Chunk-Storage.
rdc backup restore my-app --as my-app-yesterday --at <snapshot-id> --up

# Ein Artefakt, das ein Push auf einer Maschine hinterlassen hat.
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

`--at` nimmt eine Snapshot-ID von `rdc backup manifests`, oder eine RFC-3339-Zeit wie `2026-08-14T12:00:00Z`, die zum neuesten Snapshot aufgelöst wird, der zu diesem Zeitpunkt oder davor genommen wurde. Eine Zeit ohne Snapshot zu diesem Zeitpunkt oder davor wird zurückgewiesen statt aufgerundet.

Die Wiederherstellung unter einem neuen Namen mit `--as` überschreibt nichts, sodass eine Wiederherstellungsübung gefahrlos gegen eine Live-Maschine läuft. Die Wiederherstellung auf einen bereits vorhandenen Namen wird zurückgewiesen.

| Option | Beschreibung |
|--------|-------------|
| `<artifact-ref>` (positional) | Was wiederhergestellt werden soll. `repo` für einen Chunk-Store-Snapshot, `repo@place` für ein Artefakt auf einer Maschine |
| `--as <name>` | Name für das wiederhergestellte Repository (Standard: Name des Artefakts) |
| `-m, --machine <machine>` | Maschine, auf die wiederhergestellt wird |
| `--datastore <name>` | In diesen benannten Datastore wiederherstellen, dessen angeschlossene Maschine ihn hostet |
| `--at <time>` | Einen Zeitpunkt wiederherstellen: eine Snapshot-ID oder eine RFC-3339-Zeit |
| `--up` | Wiederhergestelltes Repository nach der Übertragung bereitstellen |
| `--health-window <seconds>` | Wie lange das bereitgestellte Repository auf Gesundheit beobachtet wird |
| `--health-timeout <seconds>` | Wie lange gewartet wird, bis es gesund wird |
| `-y, --yes` | Bestätigung überspringen |
| `--debug` | Ausführliche Ausgabe aktivieren |

Die Wiederherstellung eines Repositorys benötigt dessen LUKS-Credential, das in Ihrer Konfiguration liegt. Wenn Sie Config-Storage aktiviert haben, kommt dieses Credential mit Ihrer Konfiguration auf einer neuen Maschine zurück. Falls nicht, bewahren Sie eine Kopie der Konfiguration irgendwo auf, das die ausfallende Maschine nicht mit sich reißt.

### Die Wiederherstellung auf jeder Maschine beweisen

Eine Maschine, die nie einen vollständigen Kreislauf durchlaufen hat, ist nicht gesichert, wie grün ihre Uploads auch aussehen. Uploads und Wiederherstellungen scheitern aus unterschiedlichen Gründen, und die zweite Art zeigt sich erst, wenn Sie es versuchen.

Tun Sie dies einmal pro Maschine, bevor Sie sich auf die Backups verlassen:

1. Einen Snapshot erstellen: `rdc backup snapshot my-app`.
2. Bestätigen, dass er erfasst wurde: `rdc backup manifests my-app`.
3. Ihn unter einem Wegwerf-Namen wiederherstellen: `rdc backup restore my-app --as my-app-drill --at <snapshot-id>`.
4. Das wiederhergestellte Repository mit der Quelle vergleichen, dann die Übungskopie mit `rdc repo delete my-app-drill --yes` löschen.

Nichts in dieser Abfolge berührt das Live-Repository, sie ist also auf einer Maschine sicher, die Traffic bedient. Wenn Sie von einer älteren Backup-Anordnung wegziehen, lassen Sie diese laufen, bis dies auf dieser Maschine mindestens einmal bestanden hat. Zwei Backup-Wege kosten Speicherplatz; ein unbewiesener Weg kostet die Daten.

## Ein Repository nach dem anderen synchronisieren

Push und Pull wirken auf ein einzelnes Repository, adressiert über einen Ref (`name`, `name:tag` oder `name@machine`). Es gibt keine Form für "alle Repositories auf einmal": Führen Sie den Befehl einmal pro Repository aus.

Ein Ref, der einen Fork und eine Maschine benennt, funktioniert genauso wie ein einfacher Name:

```bash
rdc repo push shop:nightly@server-1 --to server-2
rdc repo pull shop:nightly@server-1 --from server-2
```

Die vollständigen Optionslisten finden Sie unter [Ein Backup auf eine andere Maschine übertragen](#ein-backup-auf-eine-andere-maschine-übertragen) und [Ein Backup von einer anderen Maschine abrufen](#ein-backup-von-einer-anderen-maschine-abrufen).

## Geplante Backups

Rediacc verwendet benannte Backup-Strategien. Jede Strategie definiert einen Zeitplan, einen Backup-Modus, ein optionales Bandbreitenlimit und Dateifilter. Sie binden Strategienamen an Maschinen, um zu steuern, welche Backups dort ausgeführt werden.

### Backup-Modi

| Modus | Verhalten | Ausfallzeit |
|-------|-----------|-------------|
| `hot` | Repository-Image wird eingefroren, während Dienste weiterlaufen (absturzkonsistent) | Keine |
| `cold` | Dienste gestoppt, Snapshot erstellt, Dienste neu gestartet, Snapshot hochgeladen (anwendungskonsistent) | Stop+Start-Fenster pro Repo, parallel über alle Repos. Siehe "Abschätzung der Cold-Backup-Ausfallzeit" unten. |

Verwenden Sie `hot` für Dienste, die absturzkonsistente Snapshots tolerieren. Verwenden Sie `cold`, wenn Sie garantierte Konsistenz benötigen und einen kurzen Neustart akzeptieren können.

### Cold-Backup-Semantik

Ein Cold-Backup läuft in drei Phasen pro enthaltenem Repository: **Stopp - Snapshot - Start**. Das Verstehen der Grenzen der Garantien hilft Betreibern, Teilausfälle frühzeitig zu erkennen.

**Was Cold-Backup garantiert:**

- Vor dem Snapshot wird jeder laufende Container in jedem enthaltenen Repository über den `down()`-Hook der Rediaccfile kontrolliert gestoppt, und der repository-eigene Docker-Daemon wird stillgelegt. Der Snapshot ist daher anwendungskonsistent, nicht nur absturzkonsistent.
- Die Menge der Container-IDs, die vor dem Snapshot liefen, wird in eine Sidecar-Datei unter `/var/run/rediacc/cold-backup-<guid>.running.json` geschrieben. Dies ist die Wahrheitsquelle dafür, "was nach Abschluss wieder laufen soll."
- Nach dem Snapshot wird der `up()`-Hook der Rediaccfile des Repositories aufgerufen, um den vollständigen Compose-Stack wiederherzustellen.
- Eine laufzeitbezogene Status-Sidecar-Datei unter `/var/run/rediacc/cold-backup-<guid>.status.json` zeichnet Phase, Ergebnis und etwaige Fehler jedes Versuchs auf.

**Was Cold-Backup NICHT garantiert:**

- `up()` ist ein Best-Effort-Versuch. Es kann aus Gründen scheitern, die außerhalb der Kontrolle des Cold-Backups liegen (eine `depends_on: service_healthy`-Bedingung wartet noch, ein Compose-Datei-Syntaxfehler, ein vorübergehender Netzwerkfehler beim Image-Pull). Bei einem Fehler protokolliert Cold-Backup den Fehler auf Fehlerebene, schreibt die Status-Sidecar-Datei und fährt mit dem nächsten Repository fort.
- Wenn `up()` fehlschlägt, greift ein **direkter Fallback-Neustart**: Die Running-Sidecar wird gelesen, und jede aufgezeichnete Container-ID wird direkt über die Docker API neu gestartet (ohne Compose). Dies bringt Dienste auch dann wieder zum Laufen, wenn der Compose-Ablauf ein Problem hat, allerdings ohne erneute Ausführung von Rediaccfile-Hooks.
- Wenn der Fallback für einige Container-IDs fehlschlägt (z. B. ist der Docker-Daemon selbst ausgefallen), bleibt die Sidecar-Datei **bestehen**, damit der Router-Watchdog bei jedem Tick erneut versuchen kann.

**Watchdog-Wiederherstellung:** Bei jedem Tick prüft der Watchdog, ob eine Running-Sidecar vorhanden ist. Jede dort aufgelistete Container-ID, die derzeit gestoppt ist, wird neu gestartet, *unabhängig von der gespeicherten `restart_policy` des Containers*. Dies bedeutet, dass Dienste mit `restart: on-failure` (die Docker nach einem sauberen Stopp NICHT neu starten würde) nach einem Cold-Backup wieder starten. Sobald alle aufgelisteten Container laufen, wird die Sidecar-Datei gelöscht.

**Wie Betreiber Ausfälle erkennen:**

- `rdc machine status <machine> --containers` zeigt den Laufzustand. Vergleichen Sie mit der erwarteten Menge.
- `/var/run/rediacc/cold-backup-<guid>.status.json` auf der Maschine. Prüfen Sie via `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` mit einem veralteten `startedAt` bedeutet, dass das letzte Backup nicht sauber abgeschlossen wurde.
- Protokolle des renet-Backup-Laufs (`journalctl -u renet-*` oder der direkte `rdc backup schedule`-Aufruf) geben eine abschließende Zusammenfassungszeile der Form `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` aus. Ein nicht leeres `failed_repos` ist das grep-Ziel.

### Abschätzung der Cold-Backup-Ausfallzeit

Jedes Repository ist nur während seines eigenen `down()` + `up()`-Fensters ausgefallen. Auf einem warmen Host sind das typischerweise:

| Repository-Form | Typisches Stop+Start |
|-----------------|----------------------|
| Klein (1-2 Container, keine DB) | 5-15 s |
| Mittel (Webanwendung + Cache) | 20-45 s |
| Schwer (DB + Queues + Mail) | 60-120 s |

Der Freeze-Schritt ist ein Copy-on-Write-Reflink des Repository-Images. Er besteht nur aus Metadaten und dauert deshalb gleich lang, ob das Repository 1 GB oder 100 GB hält, und bei einem gemessenen Lauf registrierte er sich nicht einmal in Millisekunden-Auflösung. Ein Repository wird nicht für die Freezes anderer Repositories heruntergefahren gehalten. Der Upload läuft dann gegen die eingefrorene Kopie, während jedes Repository bereits wieder oben ist.

**Die Gesamt-Wall-Clock für den gesamten Lauf** wird davon bestimmt, wie viele Repositories gleichzeitig neu starten. Renet leitet diesen Wert vom Host ab:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Beispiele:

| Host | Repositories | Parallelität | Wall-Clock-Neustart |
|------|--------------|-------------|---------------------|
| 4-CPU-VM | 5 Repos, ø 30 s je | 2 | ~75 s |
| 16-CPU-Server | 10 Repos, ø 40 s je | 8 | ~80 s |
| 64-CPU-Fleet-Knoten | 50 Repos, ø 40 s je | 8 | ~4 Min |

**Override per Umgebungsvariable:** Setzen Sie `REDIACC_COLD_BACKUP_CONCURRENCY=N` in der Umgebung des Backup-Dienstes (meist über ein systemd-Drop-in), um einen bestimmten Wert festzulegen. `=1` erzwingt streng serielle Neustarts, nützlich beim Debuggen eines Crashloops im `up()`-Hook eines Repositories.

Wenn Sie ein latenzempfindliches Repository betreiben (öffentliche Webanwendung, Mail), ist dessen Ausfallzeit durch sein eigenes Stop+Start begrenzt (typischerweise 30-90 s), nicht durch die Gesamtlaufzeit. Repositories werden in der Reihenfolge ihrer Erkennung in Parallelitäts-Slots eingeplant; es gibt keine Prioritätswarteschlange. Geben Sie schweren Repositories ihre eigene, mit `--include` begrenzte Strategie, wenn Sie eine feinere Zeitplanung benötigen.

### Lange Läufe und überlappende Zeitpläne

Ein Cold-Backup, das länger als sein eigenes Zeitplan-Intervall dauert (zum Beispiel eine erste Vollsicherung eines 500 GB-Repositories über eine moderate Leitung kann legitim mehr als 24 h benötigen, während der nächtliche Timer erneut feuert), löst weder einen zweiten Lauf aus noch stellt er einen in die Warteschlange. Die systemd-`Type=oneshot`-Unit ist eine Einzelinstanz: Wenn der Timer feuert und der Dienst bereits `activating` ist, fasst systemd den Start in den laufenden Job zusammen. Kein neuer Prozess wird gestartet, kein Lauf für später gespeichert.

Konkret: Ein Lauf, der am Montag um 03:00 UTC startet und am Donnerstag Mittag endet:

| Tag | 03:00 UTC feuert | Ergebnis |
|------|-----------------|----------|
| Montag | Erstes Feuern | Lauf beginnt |
| Dienstag | Zweites Feuern | Still verworfen (vorheriger Lauf ist noch aktiv) |
| Mittwoch | Drittes Feuern | Still verworfen (vorheriger Lauf ist noch aktiv) |
| Donnerstag | Lauf endet mittags | Kein Nachholen; nächster Lauf ist Freitag 03:00 UTC |

Die `Persistent=true`-Direktive des Timers rettet diese Feuer **nicht**. `Persistent=true` wiederholt Feuer, die verpasst wurden, weil der Timer selbst inaktiv war (System aus, Timer deaktiviert). Feuer, die verworfen wurden, weil der Dienst beschäftigt war, sind weg.

Dieses Verhalten ist bewusst gewählt. Zwei parallele Cold-Backups gegen denselben Datastore würden um den Freeze-Pfad, den Upload und die Per-Repo-Sidecars unter `/var/run/rediacc/cold-backup-<guid>.status.json` konkurrieren. Hinter einer laufenden Instanz zu warten schlägt es, dieselben Daten aus zwei Richtungen zu strapazieren. Die Datastore-Sperre erzwingt das: Ein zweiter Cold-Lauf findet die Sperre besetzt vor und wird rundweg zurückgewiesen, ohne etwas gestoppt zu haben.

**Monitoring-Konsequenz.** Ein hängendes Backup (zum Beispiel ein Upload, der an einem Netzwerk-Blackhole hängenbleibt) verwirft still jedes nachfolgende Timer-Feuern. Der Scheduler gibt keinen Alarm aus. Beobachten Sie `systemctl show <unit> -p ActiveEnterTimestamp`: Wenn der Dienst länger als erwartet `activating` ist (zum Beispiel mehr als 48 h bei einem nächtlichen Timer), untersuchen Sie dies.

**Wenn Sie möchten, dass jedes geplante Feuern läuft**, wechseln Sie den Timer von `OnCalendar=<cron>` zu `OnUnitInactiveSec=<Intervall>`. Das feuert N Stunden nach Abschluss des vorherigen Laufs statt nach einem festen Wall-Clock-Zeitplan, sodass lange Läufe keine Verluste verursachen. Sie schieben nur den nächsten Lauf nach hinten. Der Kompromiss ist Zeitplan-Drift: Ihr nächtliches 03:00 wird zu "24 h nach Abschluss des letzten Laufs."

### Snapshots, Unterbrechungen und Pool-Speicher

Jeder Push arbeitet von einem kurzlebigen Datastore-Snapshot, sodass die hochgeladenen Daten konsistent sind, auch während Repositories weiter schreiben. Während das Backup läuft, referenziert dieser Snapshot weiterhin jeden Block, den er mit aktiven Repositories teilt: Löschungen und [Trims](/de/docs/repositories#speicherplatz-zuruckgewinnen-trim) geben bis zum Abschluss des Zyklus und zum Löschen des Snapshots weniger Pool-Speicher frei. Der [Speichergesundheitsbericht](/de/docs/monitoring#speichergesundheit) zeigt, wie viel Speicher Backup-Snapshots aktuell belegen.

Unterbrechungen sind sicher. Wird der Dienst gestoppt (oder die Maschine neu gestartet), bricht das Backup seine Übertragung ab und löscht seinen Snapshot vor dem Beenden; der nächste geplante Lauf setzt dort fort, wo er aufgehört hat, da bereits gespeicherte Zellen nicht erneut hochgeladen werden. Wird der Prozess zu hart beendet, um aufzuräumen (Stromausfall), wird der verwaiste Snapshot vom Storage-Maintainer innerhalb von Minuten automatisch erkannt und entfernt.

### Strategie definieren

Der kanonische Standard ist eine Aufteilung in zwei Strategien: ein schneller stündlicher Hot-Stream, der jedes Repo erfasst, und ein langsamerer wöchentlicher Cold-Stream, der Container für anwendungskonsistente Snapshots ruhig stellt. Beide schreiben in denselben Chunk-Storage, und gemeinsame Blöcke werden nur einmal statt pro Stream gespeichert.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

`--destination <name>` benennt das Ziel innerhalb der Strategie; es ist ein von Ihnen gewähltes Label und beschreibt den Chunk-Store. `--include` listet die zu sichernden Repositories auf, und wiederholtes Angeben fügt weitere hinzu. Weglassen deckt mit der Strategie jedes Repository auf dem Datastore ab. Namen entsprechen dem lokalen Konfigurationsnamen des Repositorys (ohne `:tag`).

`--exclude` wird bei einem Chunk-Store-Ziel zurückgewiesen statt still verworfen, weil das zugrundeliegende `backup snapshot` Repositories auswählt, indem es sie benennt, und selbst kein Exclude hat. Es zu respektieren würde bedeuten, Repositories zu sichern, die Sie ausschließen wollten. Grenzen Sie eine Strategie stattdessen mit `--include` ein, damit schriftlich festgehalten statt erschlossen wird, was ein geplanter Lauf abdeckt.

| Option | Beschreibung |
|--------|-------------|
| `<strategy>` (positional) | Strategie-Name (wird zur Maschinenbindung verwendet) |
| `--destination <name>` | Ziel-Name innerhalb der Strategie. Standard ist der Chunk-Store |
| `--storage <name>` | Sich für die eingestellte rclone-Zielart entscheiden. Ein Zeitplan, der es nutzt, kann nicht deployt werden |
| `--cron <expression>` | Cron-Ausdruck (z. B. `"0 2 * * *"` für täglich um 2 Uhr) |
| `--mode <hot\|cold>` | Backup-Modus |
| `--bwlimit <limit>` | Bandbreitenlimit für Uploads (z. B. `10M`) |
| `--include <repos>` | Von dieser Strategie abgedeckte Repositories (wiederholbar) |
| `--exclude <repos>` | Zu überspringende Repositories (wiederholbar). Bei einem Chunk-Store-Ziel zurückgewiesen |
| `--folder <path>` | Unterordner innerhalb eines rclone-Buckets. Bei einem Chunk-Store-Ziel zurückgewiesen |
| `--enable` / `--disable` | Strategie aktivieren oder deaktivieren |

### Strategien anzeigen

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Strategie entfernen

```bash
rdc backup strategy remove weekly-cold
```

### Strategien an eine Maschine binden

Eine Strategie, die an keine Maschine gebunden ist, wird nie deployt. Binden Sie eine oder mehrere an eine Maschine:

```bash
rdc backup strategy bind hourly-hot --machine hostinger
rdc backup strategy bind weekly-cold --machine hostinger
rdc backup strategy unbind weekly-cold --machine hostinger
```

Die Bindung wird in Ihrer Konfiguration als Liste auf der Maschine festgehalten, die `rdc backup schedule` liest, um zu entscheiden, welche Units deployt werden:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **Bindung ist nur lokale Konfiguration.** Eine Strategie zu definieren und an eine Maschine zu binden, hat keine Auswirkung auf die Maschine. Führen Sie `rdc backup schedule -m <machine>` aus (siehe [Zeitplan auf Maschine deployen](#zeitplan-auf-maschine-deployen)), um die systemd-Timer zu deployen, und führen Sie den Befehl nach jeder Strategie- oder Bindungsänderung erneut aus.

## Hot vs. Cold und Repo-Filterung im Vergleich

### Hot vs. Cold auf einen Blick

| | Hot | Cold |
|---|-----|------|
| **Konsistenz** | Absturzkonsistent (Image eingefroren während des Betriebs) | Anwendungskonsistent (Stopp - Snapshot - Start) |
| **Ausfallzeit** | Keine | Stop+Start-Fenster pro Repo (typischerweise 5-120 s) |
| **Geeignete Häufigkeit** | Hoch (z. B. stündlich) | Niedrig (z. B. täglich oder wöchentlich) |
| **Typischer Einsatz** | Häufiges Sicherheitsnetz | Geplantes Backup mit garantierter Konsistenz |

**Hot** ist die richtige Standardwahl für hochfrequente Läufe. Dienste laufen weiter, während der Snapshot erstellt wird, sodass das Backup-Fenster Benutzer nicht unterbricht. Der Snapshot ist absturzkonsistent: Er entspricht dem, was Sie nach einem unsauberen Herunterfahren erhalten würden. Für die meisten modernen Datenbanken und Message-Queues ist dies akzeptabel.

**Cold** ist geeignet, wenn Sie einen garantiert anwendungskonsistenten Snapshot benötigen und einen kurzen Neustart pro Repo akzeptieren können. Dienste werden vor dem Snapshot gestoppt und vor Beginn des Uploads neu gestartet, sodass ein langsamer oder fehlgeschlagener Upload das Ausfallzeitfenster nie verlängert. Das vollständige Garantiemodell finden Sie unter [Cold-Backup-Semantik](#cold-backup-semantik).

Beide Modi schreiben in denselben Chunk-Store, und der Modus betrifft, wie das Repository behandelt wird, während das Image eingefroren wird, nicht, wo die Daten landen. Ein Repository, das sowohl von einem stündlichen Hot- als auch einem wöchentlichen Cold-Zeitplan abgedeckt wird, speichert die gemeinsamen Zellen einmal statt zweimal.

### Repos pro Strategie eingrenzen

Eine Strategie ohne `--include` deckt jedes Repository auf dem Datastore ab. Wiederholtes `--include` grenzt sie auf die von Ihnen genannten Repositories ein, abgeglichen gegen den lokalen Konfigurationsnamen des Repositorys (ohne `:tag`).

```bash
# Hot-Strategie: alles stündlich sichern
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Cold-Strategie: wöchentlich, und nur die Repositories, die stillgelegt werden müssen
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

### Wann ein Repo aus der häufigen Hot-Strategie heraushalten

Benennen Sie die Repositories, die Sie im hochfrequenten Lauf haben wollen, statt ihn alles erfassen zu lassen, wenn:

- Ein Repo groß und **vollständig aus Quelldaten regenerierbar** ist, die bereits auf dem Volume liegen, sodass jedes stündliche Backup Bandbreite verbraucht, ohne Wiederherstellungswert hinzuzufügen.
- Der Backup-Lauf bei Ihrer verfügbaren Upload-Geschwindigkeit sein eigenes Zeitplan-Intervall überschreiten würde.

**Beispiel.** Ein `analytics-demo`-Repository hält ungefähr 114 GB abgeleitete Postgres-Tabellen, die aus rohen CSV-Dumps, die im selben Volume gespeichert sind, neu aufgebaut werden können. Bei einem Upload-Limit von 6 MB/s dauert ein erster Snapshot dieses Repos über 5 Stunden. Ihn stündlich laufen zu lassen bedeutet, dass jeder Lauf noch läuft, wenn der nächste feuert, sodass jedes nachfolgende Feuern still verworfen wird (siehe [Lange Läufe und überlappende Zeitpläne](#lange-läufe-und-überlappende-zeitpläne)). Die anderen Repositories in `hourly-hot` aufzulisten und `analytics-demo` bei `weekly-cold` zu belassen bedeutet, dass es einmal pro Woche gesichert wird statt nie.

> **Wenn die Daten rein regenerierbar sind**, überlegen Sie, ob Sie sie überhaupt sichern müssen. Eine Alternative ist, nur die rohen Quelleingaben (in diesem Beispiel die CSV-Dumps) zu sichern und die abgeleitete Kopie ganz zu überspringen. Ein wöchentliches Cold-Backup der Quelleingaben ist viel kleiner und für eine Wiederherstellung vollständig ausreichend.

Ein Repo, das von beiden Strategien abgedeckt wird, erhält stündliche absturzkonsistente Snapshots und einen wöchentlichen anwendungskonsistenten. `rdc backup manifests <repo>` zeigt sie gemeinsam an, und die gemeinsamen Zellen werden einmal gespeichert.

## Backup-Operationen

### Zeitplan auf Maschine deployen

Die gebundenen Strategien als systemd-Timer auf eine Maschine übertragen:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

Das Deploy ist ein State-Reconciler. Er liest die aktuellen Unit-Dateien und den systemd-Zustand auf der Maschine, vergleicht sie mit dem, was die Konfiguration erzeugen würde (SHA-256 pro Datei), und berührt nur Units, deren Inhalt sich tatsächlich geändert hat. Ein erneuter Aufruf ohne Konfigurationsänderungen ist ein No-op: keine Writes, kein `daemon-reload`, kein Timer-Churn.

`--dry-run` gibt den Plan pro Strategie aus (`created`, `updated (service, timer, env)`, `unchanged`, `removed`), ohne die Maschine anzufassen. Kombinieren Sie es mit `--debug`, um auch die generierten Unit-Inhalte auszugeben, wobei Credentials geschwärzt werden. Eine Chunk-Store-Unit trägt von vornherein keine: Die Maschine authentifiziert sich mit ihrer eigenen signierten Repository-Lizenz, und der Server händigt eine kurzlebige Berechtigung aus, sodass nichts Sensibles in die Unit-Datei geschrieben wird.

Wenn gerade ein Backup für eine Strategie läuft, die aktualisiert oder entfernt werden soll, bricht das Deploy sofort ab und weist darauf hin, das Backup abzubrechen oder `--force` zu übergeben. Mit `--force` behält der laufende Vorgang seine In-Memory-Unit, und die neue Konfiguration greift beim nächsten Timer-Tick, sodass das laufende Backup niemals beendet wird.

`--reset-failed` ist opt-in. Wenn übergeben, löscht es nach einem erfolgreichen Deploy den Failed-Status auf berührten Services. Standardmäßig aus, damit vorherige Fehlersignale für Alerting sichtbar bleiben.

### Backup jetzt ausführen

Ein Backup sofort auslösen, ohne auf den Timer zu warten. Funktioniert auch ohne deployte Timer via `systemd-run` für Ad-hoc-Ausführung:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Backup-Status anzeigen

Den aktuellen Status der Backup-Timer und neueste Job-Ergebnisse anzeigen:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Laufendes Backup abbrechen

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Repository-Migration

Ein Repository von einer Maschine auf eine andere verschieben:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Option | Beschreibung |
|--------|-------------|
| `<ref>` (positional) | Zu migrierender Repository-Ref; dessen `@machine` benennt die Quelle |
| `--to <place>` | Zielmaschine oder -cluster |
| `--provision <provider>` | Zielmaschine automatisch über diesen Cloud-Anbieter bereitstellen (z. B. `hetzner`, `linode`) |
| `--checkpoint` | CRIU-Checkpoint vor der Migration erstellen, sodass auch der Prozessspeicher mitzieht |
| `--delta-base <guid>` | Unveränderliche Basis-GUID für das Cutover-Delta. Standardmäßig die Basis der ersten Phase |
| `--strategy <strategy>` | Block-Delta-Strategie für das Cutover: `auto`, `physical` oder `shared` |
| `--skip-dns` | Aktualisierung der DNS-Einträge nach der Migration überspringen |
| `--keep-source` | Die Quell-Images nach einem erfolgreichen Umzug behalten |
| `--bwlimit <limit>` | Bandbreitenlimit für die Übertragung (z. B. `50M`) |

Die Migration überträgt die verschlüsselten Repository-Daten in zwei Phasen per rsync: eine Massenübertragung, während das Repository weiterläuft, dann ein kurzer Stopp für das Delta. Die Migration **verschiebt** das Repository, sodass die Quell-Images gelöscht werden, sobald der Umzug gelingt. Übergeben Sie `--keep-source`, um sie zu behalten. Das ist der Unterschied zwischen `repo migrate` und `repo push`: Push lässt die Quelle laufend und unangetastet.

## Ein vor der Umstellung geschriebenes Archiv lesen

`rdc storage` ist das, was vom rclone-Zweig übrig ist, und es ist schreibgeschützt. Es kann kein Backup-Ziel mehr sein, kommt aber weiterhin an ein Archiv heran, das auf diesem Weg geschrieben wurde.

```bash
# Ein Remote registrieren, das Sie bereits für rclone konfiguriert haben.
rdc storage import rclone.conf
rdc storage list

# Ansehen, was darin liegt. Dies führt das rclone auf Ihrem PATH aus.
rdc storage browse my-storage
```

`import` liest eine rclone-Konfigurationsdatei und erfasst die Remotes in Ihrer Konfiguration; unterstützte Typen sind S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob und Swift.

**`browse` benötigt `rclone` auf Ihrem PATH.** Es führt das rclone aus, das auf der Maschine installiert ist, an der Sie gerade tippen; eine gebündelte Kopie gibt es nicht mehr. Ohne eine sagt es Ihnen das und tut sonst nichts.

Das Übertragen zu, Abrufen von, Auflisten und Wiederherstellen eines Storage-Backends sind eingestellt; jeder verweigert die Ausführung und nennt den Befehl, der ihn ersetzt.

## Bewährte Methoden

- Planen Sie tägliche Cold-Snapshots für anwendungskonsistente Kopien kritischer Daten
- Verwenden Sie Hot-Snapshots für hochfrequente Läufe, bei denen keinerlei Ausfallzeit toleriert wird
- Testen Sie Wiederherstellungen regelmäßig. `rdc backup restore --as <new-name>` überschreibt nichts, sodass eine Übung auf einer Live-Maschine gefahrlos ist
- Legen Sie eine Aufbewahrungsrichtlinie fest, statt von Hand zu bereinigen, damit das gehaltene Fenster schriftlich festgehalten ist
- Bewahren Sie neben Snapshots auch eine Maschine-zu-Maschine-Kopie auf, wenn Sie eine Kopie auf Hardware wollen, die Sie kontrollieren
- Bewahren Sie Credentials sicher auf; Backups sind verschlüsselt, aber das LUKS-Credential wird zur Wiederherstellung benötigt
