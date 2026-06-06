---
title: "rdc repo diff"
description: "Zeigt einen git-ähnlichen, dateiebenen Diff zwischen zwei Copy-on-Write geforkten Repositories durch Vergleich ihrer verschlüsselten Images auf Block-Ebene, ohne Entschlüsselung."
category: Reference
subcategory: advanced
order: 40
language: de
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff` zeigt, welche Dateien zwischen zwei verwandten Repositories geändert wurden: zwischen einem Fork und seinem Parent oder zwischen zwei beliebigen Repositories, die einen Copy-on-Write-Vorfahren teilen. Verwende `--name <fork>`, um einen Fork gegen den Parent zu vergleichen, den die lokale Konfiguration für ihn festgehalten hat, oder füge `--base <repo>` hinzu, um gegen ein beliebiges verwandtes Repository zu vergleichen, wobei `--base` die Basis (alte) Seite und `--name` die Ziel (neue) Seite ist. Der Befehl ist schreibgeschützt und entschlüsselt die Images niemals. Er vergleicht sie auf Block-Ebene auf der Fernmaschine, sodass die Kosten der Anzahl der geänderten Blöcke folgen, nicht der Größe des Repositories: Ein 1-GB-Repository und ein 100-GB-Repository mit denselben Bearbeitungen brauchen die gleiche Zeit. Wenn sich das ganze Repository geändert hat, skaliert die Block-Anzahl mit der Größe und die Kosten auch.

## Wann sollte man es verwenden

Nutze also `repo diff` bevor du einen Fork förderst. Ein KI-Agent ist in einer gegabelten Kopie der Production losgegangen und du möchtest genau sehen, welche Dateien er berührt hat, bevor du die Änderung zurück mergst: `repo diff --name <fork> -m <machine>` gibt dir diese Dateiliste in Sekunden. Sekunden. Nach einer Notfall-Wiederherstellung kannst du den wiederhergestellten Fork gegen den Snapshot vergleichen, den er reproduzieren sollte, um zu bestätigen, dass die erwartete Dateilmenge zurückgekommen ist und sonst nichts abgewichen ist. Bei einem langlebigen Fork, der wochenlang neben seinem Parent läuft, zeigt der Diff die angesammelte Divergenz (Konfigurationsänderungen, Log-Anwachsen, Schemamigration) ohne die beiden Bäume von Hand zu mounten und durchzulaufen.

Verwende es nicht zwischen unverwandten Repositories. Die beiden Seiten müssen einen Copy-on-Write-Vorfahren teilen, da der Vergleich auf der gemeinsamen Block-Historie arbeitet. Es ist auch kein Binary-Diff-Tool: `--content` erzeugt Ausgabe auf Zeilenebene nur für Textdateien, und Binärdateien zeigen `Binary files differ`.

## Befehlsreferenz

### Syntax

```bash
rdc repo diff --name <fork> -m <machine>            # diff a fork against its parent
rdc repo diff --name <fork> --base <repo> -m <machine>   # diff against an arbitrary related repo
```

### Optionen

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `--name <name>` | Zu inspizierendes Repository (die Zielseite, neue Seite). Erforderlich. | erforderlich |
| `--base <name>` | Repository zum Vergleich (die Basis, alte Seite). Standardmäßig der Parent von `--name`, aus der lokalen Konfiguration aufgelöst. | Parent von `--name` |
| (kein Format-Flag) | Name-Status-Ausgabe: ein farbiger `A`/`M`/`D`/`R` Buchstabe pro geänderter Datei plus eine einteilige Zusammenfassung. | on |
| `--name-only` | Ein geänderter Pfad pro Zeile, kein Status-Buchstabe. Pipe-freundlich. | aus |
| `--stat` | Pro-Datei-Änderungsgröße (Byte- und Block-Deltas) mit einer Gesamt-Zeile. | aus |
| `--content <path>` | Unified Text Diff einer einzelnen Datei. Nur Text; Binärdateien zeigen `Binary files differ`. | aus |
| `--json` | Strukturierte Ausgabe für Agenten und Skripte. | aus |
| `--fast` | Überspringe den Content-Hash-Bestätigungsschritt und vertraue dem Block-Filter. Schneller, kann aber Dateien als Modified über-berichten. | aus |
| `-m, --machine <name>` | Zielmaschine. Erforderlich. | erforderlich |
| `--debug` | Verbose Diagnostik auf stderr. | aus |
| `--skip-router-restart` | Überspringe den Router-Restart-Schritt. | aus |

## Beispiele

### Standard-Name-Status gegen den Parent

Mit nur `--name` wird der Fork gegen den Parent verglichen, der in der lokalen Konfiguration festgehalten ist. Hier hat der Fork `test-1gb:fork1` eine geänderte Datei:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Diff gegen eine explizite Basis

Verwende `--base` um gegen ein beliebiges verwandtes Repository zu vergleichen. `--base` ist die Basis (alte) Seite, `--name` ist die Ziel (neue) Seite:

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Änderungsgröße mit `--stat`

`--stat` fügt das Byte- und Block-Delta pro Datei und eine Gesamt-Zeile hinzu:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### Nur Pfade, weitergeleitet an ein Tool

`--name-only` gibt einen Pfad pro Zeile ohne Status-Buchstabe aus, bereit um in einen anderen Befehl weitergeleitet zu werden:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### Zeilenebene Diff einer Datei

`--content` erzeugt einen Unified Diff einer einzelnen Textdatei:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### JSON mit jq filtern

`--json` gibt die strukturierte Envelope auf stdout aus, sodass sie sauber in `jq` weitergeleitet wird:

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## Ausgabeformate

### Name-Status (Standard)

Jede geänderte Datei erhält einen Status-Buchstabe und ihren Pfad. `A` ist hinzugefügt, `M` geändert, `D` gelöscht, `R` umbenannt (mit dem alten Pfad angezeigt). Eine Zusammenfassungszeile folgt mit der Anzahl pro Kategorie.

### `--name-only`

Ein Pfad pro Zeile, kein Status-Buchstabe, keine Zusammenfassung. Verwende es wenn ein nachgelagerter Befehl eine saubere Dateiliste möchte.

### `--stat`

Jede Zeile trägt das Byte-Delta und Block-Delta der Datei. Eine Fußzeile meldet die Gesamtdateianzahl und insgesamt berührte Bytes. Dies zeigt wo die Last einer Änderung liegt, nicht nur welche Dateien sich bewegt haben.

### `--content <path>`

Ein Standard-Unified Diff (`---`/`+++` Header, `@@` Chunks) für eine Textdatei. Binärdateien zeigen `Binary files differ` und erzeugen keine Chunks.

### `--json`

Das vollständige strukturierte Ergebnis. Daten gehen auf stdout; Fortschritt und Diagnostik gehen auf stderr, sodass das JSON sauber in `jq` oder einen anderen Parser weitergeleitet wird, auch während der Fortschritt gedruckt wird.

## JSON-Schema

Die CLI wickelt das renet-Ergebnis in die Standard-Envelope (`success`, `command`, `data`, `errors`, `warnings`, `metrics`) ein. Das Diff-Ergebnis befindet sich in `data` mit snake_case-Feldern:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

Jedes Objekt in `entries[]` beschreibt einen geänderten Pfad:

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | Hinzugefügt, Geändert, Gelöscht oder Umbenannt. |
| `path` | string | Pfad auf der Zielseite (oder Basisseite für ein Löschen). |
| `old_path` | string | Vorheriger Pfad. Nur bei Umbenennungen vorhanden. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | Eintragstyp. |
| `old_size` | number | Größe in Bytes auf der Basisseite. |
| `size` | number | Größe in Bytes auf der Zielseite. |
| `bytes_changed` | number | Bytes die unterschiedlich sind, aufgerundet auf ganze Blöcke. |
| `blocks_changed` | number | Anzahl der geänderten Blöcke. |
| `inode` | number | Inode-Nummer, verwendet für Umbenennungserkennung. |
| `content_changed` | boolean | Ob sich der Dateiinhalt (nicht nur Metadaten) geändert hat. |
| `mode_changed` | boolean | Ob sich der Dateimodus geändert hat. `old_mode`/`new_mode` sind vorhanden wenn wahr. |
| `uid_changed` | boolean | Ob sich der Besitzer geändert hat. `old_uid`/`new_uid` sind vorhanden wenn wahr. |
| `gid_changed` | boolean | Ob sich die Gruppe geändert hat. `old_gid`/`new_gid` sind vorhanden wenn wahr. |
| `old_target` / `new_target` | string | Symlink-Ziele. Vorhanden für geänderte Symlinks. |

Für die Envelope-Felder und die Auto-Detection-Regeln die JSON in Non-TTY-Umgebungen ausgeben, siehe die [JSON-Ausgabe-Referenz](/de/docs/ai-agents-json-output).

## Wie es funktioniert

Ein Repository ist eine LUKS2-Image-Datei auf einem btrfs-Pool, und ein Fork ist eine konstante Zeit Reflink dieses Image. `repo diff` vergleicht die zwei verschlüsselten Images auf Block-Ebene über FIEMAP, liest nur Dateisystem-Metadaten und entschlüsselt niemals etwas. Es verschiebt die geänderten Ciphertext-Offsets um den LUKS-Daten-Offset um ext4-Geräte-Offsets zu erhalten, ordnet dann diese Offsets zurück zu Dateinamen durch jede Datei's ext4-Extent-Karte. Ein finaler Inode-Identitätslauf beider Mounts reconciliert das Ergebnis in Added, Modified, Deleted und Renamed Einträge. Weil die Arbeit durch die Anzahl der geänderten Blöcke begrenzt ist, ist der Diff unabhängig von der Repository-Größe, und weil er eine Live-Mount an Ort und Stelle wiederverwert, stört er niemals ein laufendes Repository. Der vollständige Mechanismus ist in [Git diff for encrypted disk images](/de/blog/git-diff-for-encrypted-disk-images) beschrieben.

## Einschränkungen

- **Nur verwandte Forks.** Beide Seiten müssen einen Copy-on-Write-Vorfahren teilen. Es gibt keinen aussagekräftigen Block-Vergleich zwischen unverwandten Repositories.
- **Umbenennungserkennung ist Inode-basiert.** Eine Datei wird als umbenannt gemeldet wenn der gleiche Inode auf einem neuen Pfad erscheint. Ein Löschen-dann-Neuerstellen (ein neuer Inode) zeigt als Deleted plus Added Eintrag, nicht als Umbenennung.
- **`--content` ist nur Text.** Es erzeugt Zeilenebene Chunks für Textdateien. Binärdateien zeigen `Binary files differ`.
- **`--fast` kann Modified über-berichten.** Es vertraut dem Block-Filter und überspringt die Content-Hash-Bestätigung, sodass eine Datei deren Blöcke sich bewegten ohne Inhalt zu ändern als Modified erscheinen kann.
- **Extent-Walk-Zeit skaliert mit Fragmentierung, nicht Größe.** Ein stark fragmentiertes Dateisystem hat mehr Extents zum Abbilden, was den Walk verlängert auch wenn die Byte-Menge der Änderungen klein ist.

## Siehe auch

- [rdc repo fork](/de/docs/repositories). Erstelle den Copy-on-Write-Fork den dieser Befehl vergleicht.
- [rdc repo status](/de/docs/repositories). Aktueller Status eines einzelnen Repositories.
- [rdc repo cat](/de/docs/repositories). Lese eine einzelne Datei aus einem Repository.
