---
title: "Bereinigung"
description: "Verwaiste Backups, überholte Snapshots, Repo-Images und lokale Konfigurationsreste entfernen, um Speicherplatz zurückzugewinnen und den Zustand kohärent zu halten."
category: "Guides"
order: 12
language: de
sourceHash: "98bb2d50d75a1d3d"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Bereinigung

Die Bereinigung entfernt Zustand, der keiner aktiven Ressource mehr entspricht. Drei Befehle decken drei verschiedene Bereiche ab:

| Befehl | Was bereinigt wird | Wo die Wahrheitsquelle liegt |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | Verwaiste Backups im Cloud-Speicher | Lokale CLI-Konfiguration (mit der Executor-Maschine zur Mount-Sicherheit abgeglichen) |
| `rdc machine prune --name <machine>` | Datastore-Artefakte auf der Maschine (immer); verwaiste oder unbekannte Repo-Images (opt-in) | Lokale CLI-Konfiguration + der `.interim/state`-Mirror der Maschine |
| `rdc config prune` | Reste in der lokalen Konfiguration (Cert-Cache, abgelaufene Archive, hängende Querverweise) | Nur die lokale CLI-Konfiguration |

Die drei sind unabhängig. Sie können jeden einzeln ohne die anderen ausführen. Sie teilen sich ein gemeinsames Sicherheitsmodell, beschrieben unter [Sicherheit](#safety-model) weiter unten.

## Mount-Safety-Preflight

`storage prune` und `machine prune --prune-unknown` führen beide vor jedem Löschen einen **Mount-Safety-Preflight** aus: Sie fragen die Executor-Maschine nach derzeit eingebundenen oder laufenden Repositories ab, schneiden diese Liste mit den Löschkandidaten und **weigern sich, einen Kandidaten zu löschen, der auf der Maschine noch aktiv ist**. Das Löschen des externen Backups eines eingebundenen Repos oder das Löschen eines aktiven Repo-Images ist eine echte Datenverlust-Falle. Der Preflight macht es unmöglich, dies versehentlich zu tun.

Um dies zu übergehen (selten; nur wenn Sie wirklich wissen, dass der Live-Zustand falsch ist), übergeben Sie `--force-delete-mounted`. Dies ist ein eigenes Flag, getrennt von `--force` (das die Archiv-Schonfrist steuert), damit die beiden Notausgänge unterscheidbar bleiben.

## Storage Prune

Durchsucht einen Speicheranbieter und löscht Backups, deren GUIDs in keiner lokalen Konfigurationsdatei mehr vorkommen.

```bash
# Nur Vorschau — zeigt, was gelöscht würde
rdc storage prune --name my-s3 -m server-1 --dry-run

# Verwaiste Backups tatsächlich löschen (Standardverhalten)
rdc storage prune --name my-s3 -m server-1

# Schonfrist überschreiben (Standard 7 Tage)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# Mount-Safety-Prüfung übergehen (vorsichtig verwenden)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` ist erforderlich, weil die rclone-Aufrufe auf der Executor-Maschine laufen, nicht auf Ihrem Laptop. Von Clients wird nicht erwartet, dass sie rclone lokal installiert haben. Die Speicher-Zugangsdaten kommen weiterhin aus Ihrer lokalen Konfiguration; die Maschine ist lediglich der rclone-Runner.

### Was geprüft wird

1. Listet alle Backup-GUIDs im benannten Speicher auf (über beide Unterverzeichnisse `hot/` und `cold/`. Siehe [Backup & Restore](/de/docs/backup-restore#geplante-backups)).
2. Durchsucht alle Konfigurationsdateien auf der Festplatte (`~/.config/rediacc/*.json`).
3. Ein Backup ist **verwaist**, wenn seine GUID in keinem Repositories-Abschnitt einer Konfiguration referenziert wird.
4. Kürzlich archivierte Repos innerhalb der Schonfrist sind **geschützt**, auch wenn sie aus der aktiven Konfiguration entfernt wurden.
5. Mount-Safety-Preflight: GUIDs, die derzeit auf `--machine` eingebunden sind, werden übersprungen und gemeldet, niemals gelöscht.

### Performance

Löschungen werden pro Speicher-Unterpfad gebündelt: ein rclone-Aufruf pro `hot/`- oder `cold/`-Verzeichnis, unabhängig davon, wie viele GUIDs entfernt werden. Ein Rückstand von 11 verwaisten Backups schrumpft so von ~50 s SSH-Overhead auf einen einzigen Roundtrip pro Unterpfad.

## Machine Prune

Bereinigt Ressourcen auf der Maschine in drei Phasen. Phase 1 läuft immer; die Phasen 2 und 3 sind opt-in und können kombiniert werden.

### Phase 1: Datastore-Bereinigung (wird immer ausgeführt)

Entfernt jede Art von Ressource, die zurückbleiben kann, wenn ein Repository gelöscht wird oder wenn ein Refactoring auf Maschinenebene eine Namenskonvention ablöst. Jede Kategorie wird unabhängig gescannt, und die Bereinigung erfolgt in einem einzigen idempotenten Durchlauf, sodass wiederholtes Ausführen von Prune sicher ist und gegen einen sauberen Datastore konvergiert.

| Kategorie | Was entfernt wird |
|-----------|-------------------|
| Leere Mount-Verzeichnisse | `mounts/<guid>/`-Verzeichnisse ohne zugehöriges Repository-Image |
| Verwaiste immovable-Verzeichnisse | `immovable/<guid>/`-Verzeichnisse ohne zugehöriges Repository-Image |
| Veraltete Lock-Dateien | `repositories/.lock-<guid>` für gelöschte Repos |
| Veraltete Backup-Snapshots | `.snapshot-*` und `.backup-*`, die von abgebrochenen Backup-Läufen zurückgelassen wurden |
| Verwaiste VS-Code-Sandbox-Verzeichnisse | `.interim/sandbox/<name>` für Repos, die auf der Maschine nicht mehr aktiv sind |
| Verwaiste iptables-Chains | `REDIACC_WILDCARD_<N>`- und `DOCKER_ISOLATED_NET_<N>`-Chains für gelöschte Netzwerke |
| Verwaiste authorized_keys-Einträge | `sandbox-gateway <repo> --guid <uuid>`-Zeilen, deren `--guid` keinem aktiven Mount-Verzeichnis mehr entspricht |

Der authorized_keys-Scan betrachtet `/home/*/.ssh/authorized_keys` und `/root/.ssh/authorized_keys`. Ein Eintrag wird nur dann behalten, wenn sein `--guid`-Tag einer GUID eines aktiven Mount-Verzeichnisses entspricht, sodass Repos, die aktuell auf der Maschine bereitgestellt sind, stets erhalten bleiben, unabhängig davon, ob ihr Name zufällig irgendwo auf der Festplatte auftaucht. Altlasten-Einträge, die geschrieben wurden, bevor renet das `--guid`-Tag hinzuzufügen begann, können nicht validiert werden und werden stets als verwaist gemeldet.

```bash
# Dry-run, zeigt, was entfernt würde (keine Änderungen)
rdc machine prune --name server-1 --dry-run

# Bereinigung ausführen
rdc machine prune --name server-1
```

> **Kaskadierende Bereinigung.** Einige Kategorien hängen von früheren ab. Beispielsweise kann das Löschen leerer Mount-Verzeichnisse zusätzliche verwaiste Sandbox-Einträge freilegen, deren zugehöriger Mount gerade verschwunden ist. Ein zweiter Aufruf von `rdc machine prune` erfasst die Kaskade und schließt die Bereinigung ab. Der abschließende Dry-Run endet mit `No orphaned resources found. Datastore is clean.`, wenn nichts mehr zu tun ist.

### Phase 2: `--orphaned-repos` (grob)

Mit `--orphaned-repos` löscht die CLI zusätzlich Repository-Images auf der Maschine, die in **keiner** lokalen Konfigurationsdatei erscheinen.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

Dies ist **grob**. Es löscht alles, was nicht in Ihrer lokalen Konfiguration steht, einschließlich legitimer Forks, die von anderen Tools oder dem CLI-Checkout eines anderen Operators verwaltet werden. Wenn der renet-`.interim/state`-Mirror ein Repo korrekt als Fork erkennt, die lokale Konfiguration es aber noch nie gesehen hat, entfernt diese Phase es trotzdem. Bevorzugen Sie Phase 3 (`--prune-unknown`), wenn Sie konservativ vorgehen möchten.

### Phase 3: `--prune-unknown` (chirurgisch)

Mit `--prune-unknown` löscht die CLI nur Repos, die **beide** Signale nicht klassifizieren können: nicht in irgendeiner lokalen Konfiguration **und** kein als Fork markierter Eintrag im `.interim/state`-Mirror der Maschine (siehe [Repositories. `Type`-Spalte](/de/docs/repositories#type-column-and-the-state-mirror)).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

In der Praxis ist `--prune-unknown` das, was Sie für die routinemäßige Bereinigung wollen; `--orphaned-repos` ist nur dann korrekt, wenn Sie sicher sind, dass Ihre lokale Konfiguration die vollständige und autoritative Liste jedes Repos auf der Maschine ist. Sowohl Pre-Mirror-Legacy-Waisen als auch Repos, deren Konfigurationseintrag versehentlich gelöscht wurde, fallen in den "unknown"-Bereich. Sie sind tatsächlich unklar, und das chirurgische Flag verlangt vom Operator, dies ausdrücklich zu bestätigen.

Der Mount-Safety-Preflight läuft auch in dieser Phase: ein Repo, das derzeit auf `--machine` eingebunden ist, wird gemeldet und übersprungen, sofern nicht `--force-delete-mounted` übergeben wird.

```bash
# Kombiniert: vollständige Maschinenbereinigung mit dem chirurgischen Fork-bewussten Pfad
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

Räumt veraltete Reste **innerhalb der lokalen Konfigurationsdatei** unter `~/.config/rediacc/<config>.json` auf. Rein lokal. Kein SSH, keine renet-Aufrufe. Drei Bereiche werden bereinigt:

1. **ACME-Cert-Cache-Einträge**, deren Anker (GUID, Repository-Name oder Maschinenname) nicht mehr in der aktiven Konfiguration steht. Die Cert-Wildcards können nirgendwohin mehr routen, sind also Ballast.
2. **Abgelaufene archivierte Repositories** in `resources.deletedRepositories[]`. Einträge, deren `deletedAt` älter ist als `defaults.pruneGraceDays` (Standard 7 Tage). Einträge in der Schonfrist werden gemeldet (mit verbleibenden Tagen) und behalten.
3. **Hängende Querverweise** zwischen Konfigurationsbereichen:
   - `resources.machines.<m>.backupStrategies[]`-Einträge, die eine nicht mehr existierende Strategie nennen.
   - `resources.backupStrategies.<s>.exclude[]`- und `include[]`-Einträge, die ein nicht mehr existierendes Repo nennen.
   - Speicherziele, deren Zielspeicher fehlt. Als Warnung markiert, nicht automatisch entfernt (eine automatische Entfernung würde die Strategie-Semantik verändern).

```bash
# Nur Vorschau
rdc config prune --dry-run

# Anwenden (Standardverhalten)
rdc config prune

# Auf einen Bereich beschränken
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# ALLE archivierten Repositories unabhängig von der Schonfrist verwerfen
rdc config prune --purge-archived

# Archiv-Schonfrist für diesen Aufruf überschreiben
rdc config prune --grace-days 30
```

### Was NICHT angefasst wird

- Aktive Ressourcen (Maschinen, Speicher, Repositories, Backup-Strategien, Cloud-Anbieter).
- Zugangsdaten, der Account-Block, der Encryption-Block, defaults.
- Storage-`vaultContent` (einschließlich abgelaufener OneDrive-`access_token`. Der refresh_token erzeugt weiterhin neue; eine Bereinigung würde eine erneute Authentifizierung erzwingen).
- `knownHosts`-Einträge (der Auto-Refresh-Pfad ist `rdc config machine scan-keys`).
- Das komprimierte Cert-Blob-Array (`infra.acmeCertCache.<base>.data[]`) wird automatisch aus der bereinigten Cert-Liste neu aufgebaut; Sie verlieren keine Kette, die noch einen behaltenen Namen abdeckt.

### Beispiel aus der Praxis

Ausgabe eines echten Laufs auf einer Maschine mit vier Wildcards mit verwaisten GUIDs und zwei veralteten Maschinen-Wildcards:

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

Cert-Namen, deren Anker eine aktive Maschine, ein aktives Repo oder eine aktive GUID ist, werden in Ruhe gelassen, ebenso wie jede einzelne Wildcard auf der Form `<service>.<base>` oder root `*.<base>`.

## Migration: State-Mirror-Backfill

Der Mirror unter `.interim/state/<guid>/.rediacc.json`, der `--prune-unknown` und die `Type`-Spalte in `rdc repo list -m` antreibt, wird geschrieben:

- **Beim Forken** (`rdc repo fork`). Sofort, noch bevor der Fork überhaupt eingebunden wird.
- **Bei jedem State-Save** (`rdc repo mount` und jede Operation, die den Repo-Zustand aktualisiert). Für Repos, die vor Auslieferung des Mirror-Codes erstellt wurden.

Repositories, die **vor Existenz des Mirrors erstellt und seit dem Upgrade nicht erneut eingebunden** wurden, haben keine Mirror-Datei. Sie erscheinen als `unknown` in `rdc repo list -m`, obwohl einige davon legitime Forks sind. Um dies für Legacy-Waisen zu beheben, führen Sie den einmaligen Backfill auf der Maschine aus:

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

Der Backfill kopiert den aktuellen In-Volume-Zustand für derzeit eingebundene Repos in den Mirror und schreibt einen synthetischen Fork-markierten Mirror für alle GUIDs, die Sie unter `--mark-as-fork` auflisten. Nach dem Backfill laden geplante Backups die aufgelisteten Forks nicht mehr hoch (die Upload-Pipeline prüft den Mirror auf `is_fork: true`).

## Sicherheitsmodell

Die Bereinigung ist standardmäßig für Multi-Konfigurations-Setups sicher konzipiert.

### Multi-Konfigurations-Bewusstsein

`storage prune` und `machine prune --orphaned-repos` durchsuchen **alle** Konfigurationsdateien in `~/.config/rediacc/`, nicht nur die aktive. Ein Repository, das von `production.json` referenziert wird, wird nicht gelöscht, auch wenn es in `staging.json` fehlt. Dies verhindert versehentliches Löschen, wenn Konfigurationen auf unterschiedliche Umgebungen ausgerichtet sind.

### Schonfrist

Wenn ein Repository mit `--archive-config` aus einer Konfiguration entfernt wird, wird sein Credential-Eintrag mit einem `deletedAt`-Zeitstempel nach `resources.deletedRepositories[]` verschoben. Die Prune-Befehle respektieren eine Schonfrist (standardmäßig 7 Tage), während der kürzlich archivierte Repos vor dem Löschen geschützt sind. Dies gibt Ihnen Zeit, ein Repo wiederherzustellen (`rdc config repository restore-archived --name <guid>`), falls es versehentlich entfernt wurde. Sobald die Schonfrist abläuft, entfernen `storage prune`, `machine prune` und `config prune` den Eintrag automatisch.

### Mount-Safety-Preflight

Oben behandelt. `storage prune` und `machine prune --prune-unknown` weigern sich, Repos zu löschen, die derzeit auf der Executor-Maschine eingebunden sind oder laufen. Übergehen Sie dies nur mit `--force-delete-mounted`.

### Standardmäßig anwenden; `--dry-run` für Vorschau

Alle drei Prune-Befehle **wenden** Änderungen standardmäßig **an**. Übergeben Sie `--dry-run`, um eine Vorschau ohne Schreiben zu erhalten. Das passt zum Verb: "prune" ist von sich aus destruktiv, und ein Dry-Run-Flag ist der explizite Opt-out.

## Konfiguration

### `pruneGraceDays`

Legen Sie eine benutzerdefinierte Standard-Schonfrist in Ihrer Konfigurationsdatei fest, damit Sie nicht jedes Mal `--grace-days` übergeben müssen:

```bash
# Schonfrist in der aktiven Konfiguration auf 14 Tage setzen
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

Das CLI-Flag `--grace-days` überschreibt diesen Wert, wenn es angegeben wird.

### Rangfolge

1. `--grace-days <N>`-Flag (höchste Priorität)
2. `pruneGraceDays` in der Konfigurationsdatei
3. Eingebauter Standard: 7 Tage

## Bewährte Methoden

- **Auf Produktion zuerst Dry-Run ausführen.** Immer eine Vorschau anzeigen, bevor eine destruktive Bereinigung durchgeführt wird, besonders auf Produktivspeicher.
- **Mehrere Konfigurationen aktuell halten.** Storage- und Machine-Prune prüfen alle Konfigurationen im Konfigurationsverzeichnis. Wenn eine Konfigurationsdatei veraltet oder gelöscht ist, verlieren ihre Repos den Schutz. Halten Sie Konfigurationsdateien akkurat.
- **`--prune-unknown` gegenüber `--orphaned-repos` bevorzugen.** Das chirurgische Flag respektiert den renet-Mirror; das grobe Flag löscht bereitwillig Forks, die andere Tools erstellt haben.
- **Großzügige Schonfristen für Produktion verwenden.** Die standardmäßige 7-Tage-Schonfrist eignet sich für die meisten Workflows. Für Produktionsumgebungen mit seltenen Wartungsfenstern sollten Sie 14 oder 30 Tage in Betracht ziehen.
- **Storage Prune nach Backup-Läufen planen.** Kombinieren Sie `storage prune` mit Ihrem Backup-Zeitplan, um die Speicherkosten ohne manuellen Eingriff unter Kontrolle zu halten.
- **Machine Prune mit dem Backup-Zeitplan kombinieren.** Nach dem Bereitstellen von Backup-Zeitplänen (`rdc machine backup schedule`) fügen Sie eine periodische Maschinenbereinigung hinzu, um veraltete Snapshots und verwaiste Datastore-Artefakte zu bereinigen.
- **`config prune` regelmäßig ausführen.** Das Anwachsen der lokalen Konfiguration (insbesondere des Cert-Cache) geschieht stillschweigend; ein vierteljährliches `config prune --dry-run` reicht, um es zu erfassen.
- **Vor Verwendung von `--force` oder `--force-delete-mounted` prüfen.** Beide Flags umgehen Sicherheitsprüfungen. Verwenden Sie `--force` nur, wenn Sie sicher sind, dass keine andere Konfiguration die betreffenden Repos referenziert; verwenden Sie `--force-delete-mounted` nur, wenn Sie sicher sind, dass der Live-Zustand auf der Maschine falsch ist.
