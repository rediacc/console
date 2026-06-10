---
title: Repositories
description: >-
  LUKS-verschlüsselte Repositories auf entfernten Maschinen erstellen, verwalten
  und betreiben.
category: Guides
order: 4
language: de
sourceHash: "a74e56f7c047115a"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Repositories

Ein **Repository** ist ein mit LUKS verschlüsseltes Disk-Image auf einem entfernten Server. Nach dem Mounten bietet es:
- Ein isoliertes Dateisystem für deine Anwendungsdaten
- Einen dedizierten Docker-Daemon (getrennt vom Docker des Hosts)
- Eindeutige Loopback-IPs für jeden Service in einem /26-Subnetz

## Repository erstellen

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Option | Erforderlich | Beschreibung |
|--------|----------|-------------|
| `-m, --machine <name>` | Ja | Zielmaschine, auf der das Repository erstellt wird |
| `--size <size>` | Ja | Größe des verschlüsselten Disk-Images (z.B. `5G`, `10G`, `50G`) |
| `--skip-router-restart` | Nein | Überspringe den Neustart des Route-Servers nach der Operation |

Die Ausgabe zeigt drei automatisch generierte Werte:

- **Repository GUID** - Eine UUID, die das verschlüsselte Disk-Image auf dem Server identifiziert.
- **Credential** - Eine zufällige Passphrase, die zum Ver- und Entschlüsseln des LUKS-Volumes verwendet wird.
- **Network ID** - Eine Ganzzahl (beginnend bei 2816, erhöht sich um 64), die das IP-Subnetz für die Services dieses Repositories bestimmt.

> **Speichere die Credential sicher.** Sie ist der Verschlüsselungsschlüssel für dein Repository. Bei Verlust können Daten nicht wiederhergestellt werden. Die Credential wird in deiner lokalen `config.json` gespeichert, aber nicht auf dem Server.

## Mounten und Unmounten

Mounten entschlüsselt und macht das Repository-Dateisystem zugänglich. Unmounten schließt das verschlüsselte Volume.

```bash
rdc repo mount --name my-app -m server-1  # Entschlüsseln und mounten
rdc repo unmount --name my-app -m server-1  # Unmounten und erneut verschlüsseln
```

| Option | Beschreibung |
|--------|-------------|
| `--checkpoint` | Erstelle einen CRIU-Checkpoint vor Mount/Unmount (für Container mit `rediacc.checkpoint=true` Label) |
| `--skip-router-restart` | Überspringe den Neustart des Route-Servers nach der Operation |

## Status überprüfen

```bash
rdc repo status --name my-app -m server-1
```

## Repositories auflisten

```bash
rdc repo list -m server-1
```

### Type-Spalte und der State Mirror

Die Ausgabetabelle enthält eine `Type`-Spalte mit drei Werten:

- **`grand`**. Ein Repository auf der obersten Ebene, das in deiner lokalen CLI-Konfiguration ohne Parent registriert ist. Der Basisfall.
- **`fork`**. Ein Copy-on-Write-Fork eines anderen Repos. Identifiziert entweder über `grandGuid` in der lokalen Konfiguration **oder** über den renet `.interim/state` Mirror auf der Maschine. Beide Quellen sind autorativ; beide sollten übereinstimmen, sobald der Mirror gefüllt ist.
- **`unknown`**. Kein Signal kann das Repo klassifizieren. Meist ein Legacy-Fork vor dem Mirror (erstellt, bevor der Mirror-Code ausgeliefert wurde und seitdem nicht erneut gemountet), oder ein veralteter `grand`, dessen Eintrag in der lokalen Konfiguration versehentlich gelöscht wurde. Die CLI weigert sich zu raten; der Operator sollte die [Mirror-Nachfüllung](/de/docs/pruning#migration-state-mirror-backfill) ausführen oder das Verzeichnis entfernen, wenn es wirklich verwaist ist.

Der Mirror `.interim/state/<guid>/.rediacc.json` ist eine kleine Sidecar-Datei, die **außerhalb** des mit LUKS verschlüsselten Volumes geschrieben wird, damit Backup-Tools und `repo list` die Fork-Abstammung lesen können, ohne jedes Image zu entsperren. Sie hat die gleiche Form wie die `.rediacc.json` im Volume (`is_fork`, `grand_guid`, `name`, usw.) und wird bei jedem `Repository.SaveState` aufgefrischt. Also bei jedem Mount und jeder Zustandsmutation. Sie ist die Quelle der Wahrheit für die Fork-Erkennung in geplanten Backups: Ein unmounteter Fork mit einem Mirror, der `is_fork: true` sagt, wird korrekt aus `cold`- und `hot`-Uploads übersprungen.

Für routinemäßige Bereinigung unbekannter Einträge siehe [`rdc machine prune --prune-unknown`](/de/docs/pruning#phase-3---prune-unknown-surgical).

## Größe ändern

Stelle das Repository auf eine exakte Größe oder erweitere es um einen bestimmten Betrag:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Auf exakte Größe setzen
rdc repo expand --name my-app -m server-1 --size 5G  # Füge 5G zur aktuellen Größe hinzu
```

> Das Repository muss vor der Größenänderung unmountet sein. `repo expand` funktioniert im laufenden Betrieb. Eine Größenänderung verändert die maximale Größe des Repositories. Um freigegebene Blöcke ohne Änderung der Maximalgröße an den Pool zurückzugeben, verwende stattdessen [`repo trim`](#speicherplatz-zuruckgewinnen-trim).

## Speicherplatz zurückgewinnen (trim)

Das Löschen von Dateien innerhalb eines Repositories gibt Speicherplatz für dieses Repository frei, und `repo trim` übergibt diese freigegebenen Blöcke an den gemeinsamen Datastore-Pool zurück. Der Befehl läuft im laufenden Betrieb ohne Ausfallzeit:

```bash
rdc repo trim -m server-1                       # Trim every mounted repository plus the datastore
rdc repo trim -m server-1 --name my-app          # Trim one repository
rdc repo trim -m server-1 --report-only          # Show reclaimable space without trimming
rdc repo trim -m server-1 --docker               # Also clear stopped containers, dangling images, and build cache first
```

Funktionsweise: Repository-Images sind Sparse-Dateien, und das verschlüsselte Volume leitet Discards durch. Ein Trim weist das Dateisystem innerhalb des Repositories an, jeden ungenutzten Block freizugeben, was Lücken in das Backing-Image stanzt und die Pool-Auslastung sofort reduziert.

Hinweise:

- Repositories, auf denen ein aktives Backup läuft, werden übersprungen und gemeldet. Ein Trim während eines Backups würde keinen Speicher freigeben, da der Backup-Snapshot die Blöcke weiterhin referenziert.
- Zweimaliges aufeinanderfolgendes Ausführen von Trim meldet beim zweiten Mal 0 Byte. Das Dateisystem merkt sich, welche Block-Gruppen bereits getrimmt wurden; das ist erwartet, kein Fehler.
- `--docker` entfernt niemals getaggte Images, sondern nur dangling Images, gestoppte Container und den Build-Cache. Mit `--docker-volumes` werden zusätzlich unbenutzte Volumes entfernt (löscht Daten; nur CLI).

## Automatische Größenrichtlinie

Anstatt die Größe manuell anzupassen, kann die Maschine Repository-Größen selbst verwalten. Eine Richtlinie aktiviert Online-Auto-Grow (die maximale Größe des Repositories wächst automatisch, wenn es sich füllt) sowie geplante Trims. Die Maschine wendet Richtlinien alle paar Minuten über den systemd-Timer `rediacc-storage-maintain` an.

```bash
# Machine-wide default: trim every repository daily
rdc repo policy set -m server-1 --auto-trim true

# Per-repository: grow my-app automatically, up to a hard ceiling
rdc repo policy set -m server-1 --name my-app --auto-grow true --max-quota 50G

# Inspect the stored and effective policy
rdc repo policy get -m server-1 --name my-app
```

Richtlinienfelder:

| Feld | Bedeutung | Standard |
|---|---|---|
| `--auto-grow` | Repository im laufenden Betrieb vergrößern, wenn das Dateisystem den Schwellenwert überschreitet | aus |
| `--max-quota` | Hartes Maximum für Auto-Grow. Pflichtfeld: seine Angabe ist die explizite Zustimmung, den Pool zu überprovisionieren | keins |
| `--grow-threshold` | Dateisystemauslastung in Prozent, ab der ein Grow ausgelöst wird | 85 |
| `--grow-step` | Wie viel pro Grow hinzugefügt wird: absolut (`10G`) oder Prozent der aktuellen Größe (`20%`) | 20% |
| `--auto-trim` | Geplante Trims ausführen | aus |
| `--trim-interval` | Mindeststunden zwischen automatischen Trims | 24 |

Schutzmaßnahmen: Auto-Grow verweigert die Ausführung, wenn der freie Pool-Speicher unter eine Reserve fällt (10 GB oder 5 % des Pools, je nachdem was größer ist), wartet mindestens 30 Minuten zwischen Grows desselben Repositories und überschreitet niemals `--max-quota`. Es gibt kein automatisches Verkleinern: Das manuelle, offline durchzuführende [`repo resize`](#grosse-andern) ist der einzige Weg, die maximale Größe eines Repositories zu reduzieren.

Einstellungen pro Repository überschreiben den maschinenweiten Standard. Wiederholte `policy set`-Aufrufe ändern nur die übergebenen Flags.

## Fork

Erstelle eine Kopie eines bestehenden Repositories in seinem aktuellen Zustand:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Forks verwenden das name:tag-Modell: Der resultierende Fork heißt `my-app:staging`. Dies erstellt eine neue verschlüsselte Kopie mit ihrer eigenen GUID und Network ID, während sie den Namen des Parents teilt. Der Fork teilt die gleiche LUKS-Credential wie der Parent.

> Forks teilen die Daten des Parents über BTRFS Reflink, einschließlich aller auf der Festplatte gespeicherten Credentials. Siehe [What Rediacc does not isolate](/de/docs/ai-agents-safety#what-rediacc-does-not-isolate) für die Auswirkungen, wenn diese Credentials externe Services wie Stripe, AWS oder Railway autorisieren. Um Deploy-Zeit-Credentials vor dem Zugriff des Forks zu schützen, verwende [Per-Repo-Secrets](#secrets) statt Werte in `.env`-Dateien einzubacken.

Beim Fork-Erstellen schreibt `repo fork` das [State-Mirror-Sidecar](#type-spalte-und-der-state-mirror) sofort unter `<datastore>/.interim/state/<fork-guid>/.rediacc.json`. Ohne das Volume zu entsperren. So wird der neue Fork korrekt als `is_fork: true` ab dem Moment der Erstellung identifiziert. Dies ermöglicht es geplanten Backups, ihn zu überspringen (Forks sind standardmäßig aus der Upload-Pipeline ausgeschlossen), auch wenn er nie gemountet wird. Beim Forken eines Forks wird `grand_guid` korrekt verkettet: Der Mirror des neuen Forks zeigt auf die ursprüngliche Grand-Parent-GUID, nicht auf den Zwischenfork.

### Fork und Start in einem Schritt

Mit `--up` werden Fork, Einbinden und Dienststart in einem einzigen Remote-Vorgang zusammengefasst. Wer das Terminal sofort zurückbekommen möchte, sobald die Container gestartet sind, hängt zusätzlich `--detach` an — Gesundheitsprüfungen laufen dann im Hintergrund weiter, und der Proxy versucht so lange, die Verbindung aufzubauen, bis jeder Dienst erreichbar ist:

```bash
rdc repo fork --parent my-app --tag staging -m server-1 --up
rdc repo fork --parent my-app --tag scratch -m server-1 --up --detach
```

In unseren Tests hat ein 128-GB-Repository geforkt und laufende Dienste in etwa 57 Sekunden erreicht, mit `--detach` in etwa 31 Sekunden. Beim abgetrennten Lauf wird ein Hinweis ausgegeben, wie der Fortschritt verfolgt werden kann: `rdc machine query --containers --name <machine>`.

### Wo die Zeit bleibt

Läufe, die mehr als ein paar Sekunden dauern, schließen mit einer Zeitübersicht ab: einer schrittweisen Aufschlüsselung, einem Wasserfalldiagramm mit parallelen Phasen und einer Zuordnungszeile, die die Rediacc-Pipeline vom eigentlichen Dienststartup trennt:

```
  Rediacc pipeline 19.2s (61%) · service startup 12.3s (39%)
```

Das Dienststartup entspricht dem Hochfahren Ihrer Container — Images laden, Init-Prozesse, Gesundheitsprüfungen, wie im Rediaccfile des Repositories definiert — und variiert daher je nach Anwendung. Die Diagramme werden auf interaktiven Terminals gerendert; mit `RDC_TIMING_CHART=1` lassen sie sich auch in weitergeleiteter Ausgabe erzwingen.

## Git-ähnliche Versionierung

Forks können als Git-Commits eingesetzt werden. `rdc repo commit` friert einen arbeitenden Fork zu einem unveränderlichen, byte-stabilen Commit ein; `rdc repo branch` benennt eine Historienfolge; `rdc repo checkout` klont einen Commit per Reflink zurück in einen beschreibbaren Fork; `rdc repo log` geht die Elternkette durch; und `rdc repo merge` kombiniert zwei Entwicklungslinien, ohne ein laufendes Repository direkt zu ändern. `rdc repo fork --immutable` erzeugt eine commit-äquivalente Basis in einem einzigen Schritt.

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

Siehe die [Referenz für git-ähnliches Branching](/de/docs/repo-branching) für den vollständigen Befehlssatz, Optionen und Beispiele.

## Secrets

Per-Repository-Secrets sind Deploy-Zeit-Anmeldedaten, die in Container eingespritzt werden, ohne in das verschlüsselte Repository-Image geschrieben zu werden. Sie werden auf einer separaten Ebene von den Repository-Daten gehalten, so dass `rdc repo fork` sie nicht propagiert. Ein Fork startet mit einer leeren Secrets-Map und seine Container identifizieren sich beim Start als ein anderer externer Principal als der Parent.

> Willst du eine Schritt-für-Schritt-Erklärung? Siehe das [Tutorial zum Verwalten von Secrets](/de/docs/tutorial-managing-secrets) für den vollständigen Satz/Liste/Deploy/Verify/Rotate-Zyklus.

**Write-Only-Modell (GitHub-Stil):** `get` gibt nur den SHA-256-Digest zurück. Der Klartextwert wird niemandem zurückgegeben, weder Mensch noch Agent. Wenn du vergisst, welcher Wert es ist, schlag ihn in deinem Passwort-Manager nach und rotiere ihn; du kannst ihn von Rediacc aus nicht zurücklesen, das ist absichtlich. Das eliminiert eine ganze Klasse von Lecks: Terminal-Aufzeichnungen, Shell-Verlauf, versehentliche Umleitung, Schultermitschau.

Zwei Zustellungsmodi:

- `env`. Das Secret wird als `REDIACC_SECRET_<KEY>` in der renet-Shell auf der Zielmaschine exportiert. Referenziere es von deiner `docker-compose.yml` über `${REDIACC_SECRET_<KEY>}` Interpolation. Sichtbar in der Container-Umgebung, also nutze das für Connection-String-ähnliche Werte, die die Anwendung bereits in der Umgebung erwartet.
- `file`. Das Secret wird auf dem Host unter `/var/run/rediacc/secrets/<networkID>/<KEY>` geschrieben (tmpfs, nie persisted). Referenziere es von deiner Compose-Datei über eine Top-Level `secrets:` Deklaration mit `file:` Quelle, plus einer Per-Service `secrets:` Liste. Container lesen von `/run/secrets/<key>`. Bevorzuge diesen Modus für alles Sensible. Es erscheint nie in `docker inspect` oder `/proc/<pid>/environ`.

```bash
# Setzen, auflisten, abrufen (nur Digest), entfernen
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — kein Wert
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**Symmetrisches Mutations-Gate.** Sowohl Menschen als auch Agents benötigen `--current <previous-value>`, um ein Secret zu überschreiben oder zu löschen (passwd-ähnliche Vorbedingung). Für das erste Schreiben eines neuen Keys übergebe `--current ""` (leer). Um zu rotieren, ohne den vorherigen Wert zu überprüfen, übergebe stattdessen `--rotate-secret`. Dies wird laut als Rotation überprüft. `--current` und `--rotate-secret` schließen sich gegenseitig aus.

Übergebe `--value -`, um von stdin statt von argv zu lesen (vermeidet Shell-Verlaufs-Exposition für One-Shot-Writes).

In deiner `docker-compose.yml`:

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

Die Referenz auf Service-Seite in Kleinbuchstaben (`stripe_live_key`) ist der Dateiname `/run/secrets/<name>` im Container; das Großbuchstaben-Ende des Host-Pfads (`STRIPE_LIVE_KEY`) stimmt überein mit dem, was du mit `--key` gesetzt hast. `${REDIACC_NETWORK_ID}` wird automatisch von `renet compose` interpoliert.

> **Cross-Repo-Isolation erzwungen**: Der Compose-Validator von renet lehnt `secrets: file:` (und `configs: file:` und `env_file:`) Pfade ab, die auf die Network ID eines anderen Repos verweisen. Das wörtliche `${REDIACC_NETWORK_ID}` Token (oder deine eigene Netzwerk-Int) ist die einzige akzeptierte Form für `/var/run/rediacc/secrets/...` Referenzen. Und `--unsafe` überschreibt diese Prüfung NICHT. Die Landlock-Sandbox um den Rediaccfile-Bash-Subprocess begrenzt auch den Dateisystem-Zugriff nur auf dein eigenes Netzwerk-Secrets-Verzeichnis, so dass ein böswilliges `cat /var/run/rediacc/secrets/<other>/X` von einem Rediaccfile mit EACCES auf Kernel-Ebene fehlschlägt.

> **Forks**: `rdc repo fork` kopiert Secrets **nicht**. Um Secrets in einem Fork zu verwenden, führe `rdc repo secret set --name <fork>` auf dem Fork explizit aus. Das ist die tragende Sicherheitseigenschaft. Die Container des Forks sollten nicht als produktiver Principal gegenüber externen Services handeln können.

> **Agents** (Claude Code, Cursor, usw.): `repo secret list` und `repo secret get` werden als MCP-Tools verfügbar gemacht (lesarsicher: nur Namen + Digests, nie Werte). `set` und `unset` sind nur CLI, weil die `--current`/`--rotate-secret` Zeremonie menschliche Augen erfordert; Agents die sie über Shell aufrufen, bekommen das gleiche Gate wie Menschen. Wenn die Vorbedingung fehlschlägt, enthält die JSON-Hülle ein strukturiertes Feld `errors[].next.options[].run`. Agents sollten diese Befehle wörtlich an den Benutzer weitergeben. Siehe [KI-Agent-Sicherheit](/de/docs/ai-agents-safety) für das vollständige Modell.

## Validieren

Überprüfe die Dateisystem-Integrität eines Repositories:

```bash
rdc repo validate --name my-app -m server-1
```

## Eigentümerschaft

Stelle den Dateieigentümer innerhalb eines Repositories auf den universellen Benutzer (UID 7111). Dies ist normalerweise notwendig, nachdem du Dateien von deiner Workstation hochgeladen hast, die mit deiner lokalen UID ankommen.

```bash
rdc repo ownership --name my-app -m server-1
```

Der Befehl erkennt automatisch Docker-Container-Datenverzeichnisse (beschreibbare Bind-Mounts) und schließt sie aus. Dies verhindert, dass Container beschädigt werden, die Dateien mit ihren eigenen UIDs verwalten (z.B. MariaDB=999, www-data=33).

| Option | Beschreibung |
|--------|-------------|
| `--uid <uid>` | Setze eine benutzerdefinierte UID statt 7111 |
| `--skip-router-restart` | Überspringe den Neustart des Route-Servers nach der Operation |

Um den Eigentümer auf allen Dateien zu erzwingen, einschließlich Container-Daten:

```bash
rdc repo ownership --name my-app -m server-1
```


Siehe den [Migrationsleitfaden](/de/docs/migration) für eine vollständige Erklärung, wann und wie du den Eigentümer während der Projektmigration verwendest.

## Vorlage

Wende eine Vorlage an, um ein Repository mit Dateien zu initialisieren:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Löschen

Zerstöre ein Repository und alle darin enthaltenen Daten dauerhaft:

```bash
rdc repo delete --name my-app -m server-1
```

> Dies zerstört das verschlüsselte Disk-Image dauerhaft. Diese Aktion kann nicht rückgängig gemacht werden.

## Repository migrieren

Migriere ein Repository live von einer Maschine zu einer anderen. Die einzige Ausfallzeit ist die finale Delta-Sync-Phase: normalerweise Sekunden bis wenige Minuten, abhängig von der Schreibgeschwindigkeit beim Cutover.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Beschreibung |
|--------|-------------|
| `--provision` | Stelle das Repository auf der Zielmaschine bereit, bevor du migrierst (erstellt LUKS-Image und registriert Konfiguration) |
| `--checkpoint` | Erstelle einen CRIU-Checkpoint der laufenden Container vor dem Cutover |
| `--bwlimit <kbps>` | Begrenzte rsync-Bandbreite in Kilobyte pro Sekunde |
| `--skip-dns` | Überspringe DNS-Records-Update nach dem Cutover |

**Drei-Phasen-Ablauf:**

1. **Hot pre-copy** - rsync überträgt Daten, während das Repository auf der Quelle läuft. Große Dateien werden vor der Ausfallzeit übertragen.
2. **Cutover** - Das Repository wird auf der Quelle gestoppt, ein finaler rsync-Durchgang synchronisiert verbleibende Änderungen, und das Repository startet auf dem Ziel.
3. **Start auf dem Ziel** - renet mountet und startet das Repository auf der Zielmaschine. DNS wird aktualisiert, es sei denn `--skip-dns` wird übergeben.

![Repository Live Migration](/img/repo-migrate-flow.svg)

**Push vs. migrieren:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Operation | Kopieren | Verschieben |
| Quelle danach | Unverändert | Gestoppt |
| Ausfallzeit | Keine (nur Kopie) | Kurzes Cutover-Fenster |
| DNS-Update | Nein | Ja (es sei denn `--skip-dns`) |
| Use Case | Backup, Staging-Klon | Maschinenwechsel, Server-Umzug |

## Bereinigung

Nach dem Löschen von Repositories oder der Wiederherstellung nach fehlgeschlagenen Operationen können verwaiste Mount-Verzeichnisse, Lock-Dateien und nicht zu bewegende Marker übrig bleiben. Prune entfernt diese sicher:

```bash
# Vorschau, was entfernt würde
rdc machine prune --name server-1 --dry-run

# Entferne verwaiste Ressourcen
rdc machine prune --name server-1
```

Nur Ressourcen ohne zugehörendes Repository-Image sind betroffen. Nicht-leere Mount-Verzeichnisse werden nie entfernt.
