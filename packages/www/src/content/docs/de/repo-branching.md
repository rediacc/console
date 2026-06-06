---
title: "Git-ähnliches Branching"
description: "Copy-on-Write-Forks wie Git-Commits behandeln: einen Fork in einen unveränderlichen Commit einfrieren, Branches benennen, Commits in beschreibbare Forks auschecken, den Verlauf durchlaufen und mergen, ohne jemals ein aktives Repository direkt zu verändern."
category: Reference
subcategory: advanced
order: 41
language: de
sourceHash: "2448559f0fcfc0e0"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Git-ähnliches Branching

Hier ist das Denkmuster: Rediacc verwandelt Copy-on-Write-Forks in eine git-ähnliche Versionsgeschichte. Jeder unveränderliche Fork ist ein **Commit**: ein bytegenau eingefrorenes Abbild, das sich nicht einbinden lässt. Branches sind benannte Refs, die auf einen Commit zeigen. `rdc repo checkout` klont einen Commit per Reflink zurück in einen beschreibbaren Arbeitsfork, und `rdc repo merge` kombiniert zwei Verlaufslinien, ohne jemals ein aktives Repository direkt zu verändern.

Das Modell bildet sich auf zwei Speicher ab. Die **Maschine ist der Objektspeicher**: Commits sind unveränderliche Fork-Abbilder, die auf dem Datenspeicher liegen. Die **CLI-Konfiguration ist der Ref-Speicher**: Branch-Namen, der aktuelle `HEAD` und das Reflog liegen in Ihrer lokalen Konfiguration, nicht auf der Maschine. Das ist dieselbe Aufteilung, die Git zwischen `.git/objects` und `.git/refs` verwendet.

## Wann zu verwenden

Greifen Sie auf Branching zurück, wenn ein Fork einen Namen verdient hat. Ein KI-Agent ist in einem Fork der Produktion frei gelaufen, das Ergebnis sieht gut aus, und Sie möchten einen eingefrorenen, benannten Checkpoint, zu dem Sie später zurückkehren oder den Sie befördern können: `rdc repo commit` friert ihn ein, `rdc repo branch` benennt ihn. Vor einer riskanten Migration committen Sie den Arbeitsfork, damit Sie einen exakten Rollback-Punkt haben, der garantiert nie verändert wird (ein unveränderlicher Commit lehnt das Einbinden ab, sodass nichts in ihn schreiben kann). Um zwei Checkpoints zu vergleichen, funktioniert `rdc repo diff` zwischen beliebigen zwei Commits, weil sie einen gemeinsamen Copy-on-Write-Vorfahren teilen. Um eine überprüfte Arbeitslinie auf einen Ziel-Fork zurückzuführen, erstellt `rdc repo merge` das Ergebnis in einem Reflink-Klon und tauscht ihn atomar aus, sodass ein laufendes Ziel nie mitten beim Merge beschädigt wird.

Verwenden Sie es nicht als Ersatz für `rdc repo fork`, wenn Sie nur eine wegwerfbare Kopie benötigen. Ein einfacher Fork ist die richtige Einheit für ephemere, testweise Isolation. Commits sind wertvoll, wenn ein Zustand es wert ist, behalten, benannt oder ausgeliefert zu werden.

## Wie Commits und Forks zusammenhängen

Ein Repository ist eine LUKS-Abbilddatei auf einem btrfs-Pool. Ein Fork ist ein konstant-zeitlicher Reflink dieses Abbilds, sodass das Forken eines 1-GB-Repos und eines 100-GB-Repos gleich lang dauert. Ein **Commit** ist ein Fork, der als unveränderlich markiert wurde: renet lehnt das Einbinden ab, was sein Abbild dauerhaft bytestabil hält. Diese Bytestabilität macht einen Commit zu einem zuverlässigen Rollback-Punkt und einer deterministischen Basis für maschinenübergreifenden Delta-Push.

`rdc repo commit` zeichnet die Commit-Nachricht, den Autor, den Zeitstempel und den übergeordneten Commit **innerhalb des Volumes** auf (damit die Metadaten beim Push mit dem Abbild reisen) und spiegelt sie auch außerhalb des Volumes (damit `rdc repo log` den Verlauf durchlaufen kann, ohne etwas zu entsperren). Der Arbeitsfork, den Sie committet haben, bleibt unverändert, genau wie Git Ihren Arbeitsbaum nach einem Commit intakt lässt.

## Befehle

### rdc repo commit

Friert einen eingebundenen Arbeitsfork in einen neuen unveränderlichen Commit ein.

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `--name <name>` | Einzufrierende Arbeitsfork. Muss eingebunden sein. Erforderlich. | erforderlich |
| `--message <msg>` | Commit-Nachricht. Erforderlich. | erforderlich |
| `--author <author>` | In den Commit-Metadaten aufgezeichneter Autor. | nicht gesetzt |
| `-m, --machine <name>` | Zielmaschine. Erforderlich. | erforderlich |
| `--debug` | Ausführliche Diagnose auf stderr. | aus |

Der neue Commit wird in der lokalen Konfiguration mit `immutable: true` registriert, und der `headCommit` des Arbeitsforks wird aktualisiert, um auf ihn zu zeigen. Das Committen eines unveränderlichen Repositories wird abgelehnt: Checken Sie es zuerst in einen beschreibbaren Fork aus.

### rdc repo branch

Erstellt eine benannte Branch-Referenz, die auf den aktuellen Commit eines Arbeitsforks zeigt.

```bash
rdc repo branch --branch <name> --name <fork>
```

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `--branch <branch>` | Name des neuen Branches. Erforderlich. | erforderlich |
| `--name <name>` | Arbeitsfork, dessen aktueller Commit der Branch referenziert. Erforderlich. | erforderlich |

Dies ist eine reine Konfigurationsoperation. Auf der Maschine geschieht nichts. Die Branch-Referenz bildet einen Namen auf den `headCommit` des Arbeitsforks ab, daher muss der Fork zuerst mindestens einen Commit haben.

### rdc repo checkout

Klont einen unveränderlichen Commit (oder eine Branch-Spitze) per Reflink in einen neuen beschreibbaren Arbeitsfork.

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `--ref <commit\|branch>` | Einzucheckende Commit-GUID oder ein Branch-Name, wenn `--from` angegeben ist. Erforderlich. | erforderlich |
| `--tag <name>` | Name des neuen beschreibbaren Arbeitsforks. Erforderlich. | erforderlich |
| `-m, --machine <name>` | Zielmaschine. Erforderlich. | erforderlich |
| `--from <workingFork>` | `--ref` als Branch-Namen auf dem Branch-Set dieses Arbeitsforks auflösen. | direkter Commit |
| `--debug` | Ausführliche Diagnose auf stderr. | aus |
| `--skip-router-restart` | Router-Neustart überspringen. | aus |

Checkout verwendet denselben Fork-Reflink-Pfad, ist also nahezu sofortig und konstant-zeitlich unabhängig von der Repository-Größe. Der `headCommit` des neuen Arbeitsforks wird auf den ausgecheckten Commit gesetzt.

### rdc repo log

Durchläuft den Commit-Verlauf, der von einem Arbeitsfork oder einem Commit erreichbar ist.

```bash
rdc repo log --name <fork> -m <machine>
```

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `--name <name>` | Arbeitsfork oder Commit, von dem aus der Verlauf durchlaufen wird. Erforderlich. | erforderlich |
| `-m, --machine <name>` | Zielmaschine. Erforderlich. | erforderlich |
| `--json` | Commit-Verlauf als JSON ausgeben. | aus |
| `--debug` | Ausführliche Diagnose auf stderr. | aus |

`log` durchläuft die von `rdc repo commit` aufgezeichnete Elternkette und liest den außerhalb des Volumes gespeicherten Zustandsspiegel, sodass kein Commit entsperrt oder eingebunden wird. Es ist schreibgeschützt.

### rdc repo merge

Führt einen Quell-Commit oder -Fork in einen Ziel-Arbeitsfork zusammen, ohne das aktive Ziel direkt zu verändern.

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `--name <name>` | Ziel-Arbeitsfork, in den gemergt wird. Erforderlich. | erforderlich |
| `--from <source>` | Quell-Commit oder -Fork, aus dem gemergt wird. Erforderlich. | erforderlich |
| `-m, --machine <name>` | Zielmaschine. Erforderlich. | erforderlich |
| `--force` | Eingebundenes oder laufendes Ziel zuerst anhalten, dann mergen. Verändert niemals ein aktives Mount. | aus |
| `--resolve <ours\|theirs>` | Dateiweiser Drei-Wege-Merge: Faltet die dateiweisen Änderungen der Quelle auf das Ziel, behält (`ours`) oder übernimmt (`theirs`) die Version der Quelle für beidseitig geänderte Dateien. Weglassen für ganzes-Abbild-Take-theirs. | aus |
| `--base <guid>` | Gemeinsamer Vorfahren-Commit für den Drei-Wege-Merge (wird mit `--resolve` verwendet). Standardmäßig der Eltern-Commit der Quelle oder der aktuelle Commit des Ziels. | automatisch |
| `--debug` | Ausführliche Diagnose auf stderr. | aus |

Das Ergebnis wird in einem Reflink-Klon erstellt und hinter einem absturzsicheren Marker atomar eingetauscht, sodass ein unterbrochener Merge das ursprüngliche Ziel intakt lässt. Ein eingebundenes oder laufendes Ziel wird abgelehnt, es sei denn `--force` ist gesetzt, was das Ziel zuerst sauber herunterfährt.

Ohne `--resolve` ist der Merge ein ganzes-Abbild-Take-theirs (das Ziel wird zur Quelle). Mit `--resolve` ist es ein dateiweiser Drei-Wege-Merge gegen den aufgezeichneten Eltern-Commit der Quelle: Dateien, die nur auf einer Seite geändert wurden, werden von dieser Seite übernommen, und Dateien, die auf beiden Seiten geändert wurden, werden durch das Flag aufgelöst. Konfliktpfade werden gemeldet.

### rdc repo gc

Bereinigt unveränderliche Commit-Objekte auf einer Maschine, die kein Branch oder HEAD erreicht.

```bash
rdc repo gc -m <machine>            # Trockenlauf-Vorschau (Standard)
rdc repo gc --apply -m <machine>    # Nicht erreichbare Commits löschen
```

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `-m, --machine <name>` | Maschine, auf der bereinigt wird. Erforderlich. | erforderlich |
| `--apply` | Nicht erreichbare Commits tatsächlich löschen (sonst Trockenlauf-Vorschau). | aus |
| `--debug` | Ausführliche Diagnose auf stderr. | aus |

Die Erreichbarkeit wird aus der lokalen Konfiguration (dem Ref-Speicher) berechnet: die Menge der Commits, die durch Folgen jeder Branch-Spitze und HEAD entlang der Elternkette erreichbar sind. Unveränderliche Commits auf der Maschine außerhalb dieser Menge sind nicht erreichbar. Ein eingebundenes Objekt oder ein Arbeitsfork wird nie bereinigt.

### rdc repo fsck

Validiert die Konfigurations-Refs gegen die auf einer Maschine vorhandenen Objekte.

```bash
rdc repo fsck -m <machine>
```

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `-m, --machine <name>` | Zu prüfende Maschine. Erforderlich. | erforderlich |

Meldet hängende Refs (eine Branch-Spitze oder HEAD zeigt auf eine GUID ohne Objekt auf der Maschine) und Waisen-Commits (ein unveränderlicher Commit auf der Maschine, den keine Ref erreicht). Es ist schreibgeschützt; Waisen werden mit `rdc repo gc --apply` bereinigt.

### Unveränderliche Forks

`rdc repo fork --immutable` markiert den neuen Fork bei der Erstellung als schreibgeschützt und erzeugt so eine Commit-äquivalente Basis ohne separaten `commit`-Schritt.

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

Ein unveränderlicher Fork lehnt das Einbinden ab, was sein Abbild dauerhaft bytestabil hält. Dies ist nützlich als eingefrorene Basis für maschinenübergreifenden Delta-Push, bei dem die Basis auf beiden Seiten identisch sein muss. Um Änderungen vorzunehmen, checken Sie ihn aus (oder forken Sie ihn erneut) in eine beschreibbare Kopie.

## Beispiele

### Einen Arbeitsfork committen

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### Commit mit explizitem Autor

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### Einen Branch am aktuellen Commit benennen

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### Einen Commit in einen neuen beschreibbaren Fork auschecken

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### Eine Branch-Spitze namentlich auschecken

Mit `--from` wird der `--ref`-Wert als Branch-Name auf dem angegebenen Arbeitsfork aufgelöst:

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### Den Verlauf durchlaufen

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### Verlauf als JSON

`--json` gibt den strukturierten Durchlauf aus, neueste zuerst:

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### Zwei Commits vergleichen

`rdc repo diff` funktioniert zwischen beliebigen zwei Commits, weil sie einen gemeinsamen Copy-on-Write-Vorfahren teilen. Einen Commit auschecken und dann mit einem anderen vergleichen:

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Siehe [rdc repo diff](/de/docs/repo-diff) für die vollständige Diff-Referenz.

### Eine überprüfte Arbeitslinie zurückführen

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### In ein laufendes Ziel mergen

Ein eingebundenes oder laufendes Ziel wird abgelehnt, es sei denn `--force` ist gesetzt, was es zuerst anhält:

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### Dateiweiser Drei-Wege-Merge

Zwei Forks (`feature` und `hotfix`), ausgecheckt vom selben Commit, haben jeweils einige Dateien geändert. `--resolve theirs` faltet die Quelle (`hotfix`) in das Ziel (`feature`): Dateien, die nur eine Seite geändert hat, werden von dieser Seite übernommen, und Dateien, die beide Seiten geändert haben, werden zur Quelle aufgelöst. Die Basis wird automatisch vom gemeinsamen Vorfahren erkannt (oder mit `--base` festgelegt):

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` wurde auf beiden Seiten geändert und zur Quelle aufgelöst; eine Datei, die nur `hotfix` hinzugefügt hat, wird angewendet, und eine Datei, die nur `feature` geändert hat, wird beibehalten. Die Konfliktpfade werden gemeldet, damit Sie sie überprüfen können.

### Eine unveränderliche Basis direkt erstellen

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## Delta-Push und Pull

Ein unveränderliches, bytestabiles Abbild ist auch die Grundlage für **blockweisen Delta-Transfer**. Wenn dieselbe unveränderliche Basis auf zwei Maschinen vorhanden ist, kann ein Push oder Pull die geänderten Blöcke gegen diese Basis berechnen und nur diese übertragen, anstatt das gesamte verschlüsselte Abbild zu scannen. Ein 1-GB-Repository mit einigen geänderten Blöcken wird dann in Megabytes übertragen.

Normalerweise übergeben Sie keine Basis manuell. Nach einem vollständigen Push behält die CLI das übertragene Abbild als unveränderliche Basis auf beiden Maschinen und zeichnet es auf, sodass der **nächste** Push dieses Repositories automatisch nur das Delta überträgt, ohne Flag, selbst für einen Fork, der bereits auf dem Ziel existiert. (Ein *vollständiger* Neu-Push eines vorhandenen Forks erfordert weiterhin `--force`, da dadurch das gesamte Abbild ersetzt wird, anstatt ein verifiziertes Delta anzuwenden.) Übergeben Sie `--delta-base <guid>`, um eine spezifische Basis festzulegen, und `--strategy <auto|physical|shared>`, um zu steuern, wie geänderte Blöcke erkannt werden (`auto` ist in nahezu allen Fällen korrekt).

```bash
# Der erste Push ist eine vollständige Übertragung; er behält auch eine wiederverwendbare Basis auf beiden Seiten.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Nach lokalen Änderungen überträgt der nächste Push nur die geänderten Blöcke, kein Flag nötig.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Eine explizite Basis festlegen (ein unveränderlicher Commit, der auf beiden Maschinen vorhanden ist).
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Delta funktioniert auch in umgekehrter Richtung und zieht nur geänderte Blöcke von einer Maschinenquelle.
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Ein vorhandenes lokales Repository neu ziehen (überschreiben) mit --force.
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

Delta-Transfer gilt nur zwischen Maschinen (ein Remote mit der FIEMAP-Basis). Pushes zu Cloud-Objektspeicher übertragen immer das vollständige Abbild. Die Basis muss auf beiden Seiten byte-identisch sein, was genau ein unveränderlicher Commit oder `--immutable`-Fork garantiert.

## JSON-Schema

`rdc repo log --json` umhüllt das renet-Ergebnis in den Standardumschlag. Der durchlaufene Verlauf liegt in `entries`, neueste zuerst:

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `success` | boolean | Ob der Durchlauf abgeschlossen wurde. |
| `start` | string | GUID, von der der Durchlauf gestartet wurde. |
| `entries` | array | Ein Objekt pro Commit, neueste zuerst. |
| `entries[].guid` | string | Commit-GUID. |
| `entries[].message` | string | Commit-Nachricht. Weggelassen, wenn leer. |
| `entries[].author` | string | Commit-Autor. Weggelassen, wenn leer. |
| `entries[].parent` | string | Eltern-Commit-GUID. Weggelassen am Anfang. |
| `entries[].committed_at` | string | RFC 3339-Commit-Zeitstempel. Weggelassen, wenn nicht gesetzt. |
| `entries[].immutable` | boolean | Ob der Commit als schreibgeschützt markiert ist (immer true bei einem echten Commit). |

Für die Umschlagfelder und die automatischen Erkennungsregeln, die in Nicht-TTY-Umgebungen JSON ausgeben, siehe die [JSON-Ausgabereferenz](/de/docs/ai-agents-json-output).

## Einschränkungen

- **Refs sind lokal.** Branch-Namen, `HEAD` und das Reflog liegen in Ihrer CLI-Konfiguration, nicht auf der Maschine. Das Pushen eines Commits auf eine andere Maschine überträgt das Commit-Objekt und seine volumeninternen Metadaten, aber die Branch-Referenz ist ein Konfigurationskonzept.
- **Ein Commit lehnt das Einbinden ab.** Das ist der Punkt: Unveränderlichkeit macht einen Commit bytestabil. Um einen Commit auszuführen oder zu bearbeiten, checken Sie ihn zuerst in einen beschreibbaren Arbeitsfork aus.
- **Merge-Auflösung ist auf Dateiebene, nicht auf Zeilenebene.** Sowohl ganzes-Abbild-Take-theirs (kein `--resolve`) als auch dateiweiser Drei-Wege-Merge (`--resolve ours|theirs`) werden unterstützt. Der Drei-Wege-Merge löst Konflikte jeweils für eine ganze Datei gemäß dem Flag auf; er erzeugt keine zeilenweisen Hunks oder Merge-Marker innerhalb einer Datei.
- **Verlauf ist eine Elternkette.** `rdc repo log` durchläuft den einzelnen `parent`-Link, der beim Commit aufgezeichnet wurde. Er endet, wenn er einen Commit erreicht, dessen Metadaten auf der abgefragten Maschine nicht vorhanden sind.

## Siehe auch

- [rdc repo diff](/de/docs/repo-diff). Dateiweiser Vergleich zwischen beliebigen zwei verwandten Commits oder Forks.
- [Repositories](/de/docs/repositories). Repositories erstellen, forken, einbinden und betreiben.
