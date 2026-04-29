---
title: Repositories
description: >-
  LUKS-verschlüsselte Repositories auf entfernten Maschinen erstellen, verwalten
  und betreiben.
category: Guides
order: 4
language: de
sourceHash: "689a84ee2873fe00"
sourceCommit: "8165b06e0d06dd07530fff343b0df6ecb1697a47"
---

# Repositories

Ein **Repository** ist ein LUKS-verschlüsseltes Disk-Image auf einem entfernten Server. Nach dem Einbinden bietet es:
- Ein isoliertes Dateisystem für Ihre Anwendungsdaten
- Einen dedizierten Docker-Daemon (getrennt vom Docker des Hosts)
- Einzigartige Loopback-IPs für jeden Dienst innerhalb eines /26-Subnetzes

## Repository erstellen

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `-m, --machine <name>` | Ja | Zielmaschine, auf der das Repository erstellt wird |
| `--size <size>` | Ja | Größe des verschlüsselten Disk-Images (z. B. `5G`, `10G`, `50G`) |
| `--skip-router-restart` | Nein | Neustart des Route-Servers nach der Operation überspringen |

Die Ausgabe zeigt drei automatisch generierte Werte:

- **Repository-GUID** -- Eine UUID, die das verschlüsselte Disk-Image auf dem Server identifiziert.
- **Credential** -- Eine zufällige Passphrase zum Ver- und Entschlüsseln des LUKS-Volumes.
- **Netzwerk-ID** -- Eine Ganzzahl (beginnend bei 2816, um 64 inkrementiert), die das IP-Subnetz für die Dienste dieses Repositories bestimmt.

> **Bewahren Sie das Credential sicher auf.** Es ist der Verschlüsselungsschlüssel für Ihr Repository. Bei Verlust können die Daten nicht wiederhergestellt werden. Das Credential wird in Ihrer lokalen `config.json` gespeichert, jedoch nicht auf dem Server.

## Einbinden und Aushängen

Das Einbinden entschlüsselt und macht das Repository-Dateisystem zugänglich. Das Aushängen schließt das verschlüsselte Volume.

```bash
rdc repo mount --name my-app -m server-1  # Entschlüsseln und einbinden
rdc repo unmount --name my-app -m server-1  # Aushängen und wieder verschlüsseln
```

| Option | Beschreibung |
|--------|-------------|
| `--checkpoint` | Einen CRIU-Checkpoint vor dem Einbinden/Aushängen erstellen (für Container mit dem Label `rediacc.checkpoint=true`) |
| `--skip-router-restart` | Neustart des Route-Servers nach der Operation überspringen |

## Status prüfen

```bash
rdc repo status --name my-app -m server-1
```

## Repositories auflisten

```bash
rdc repo list -m server-1
```

## Größe ändern

Das Repository auf eine exakte Größe setzen oder um einen bestimmten Betrag erweitern:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Auf exakte Größe setzen
rdc repo expand --name my-app -m server-1 --size 5G  # 5G zur aktuellen Größe hinzufügen
```

> Das Repository muss vor der Größenänderung ausgehängt werden.

## Forken

Eine Kopie eines vorhandenen Repositories in seinem aktuellen Zustand erstellen:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Forks verwenden das Name:Tag-Modell: Der resultierende Fork heißt `my-app:staging`. Dies erstellt eine neue verschlüsselte Kopie mit eigener GUID und Netzwerk-ID, wobei der Name des übergeordneten Repositories geteilt wird. Der Fork teilt sich das gleiche LUKS-Credential wie das übergeordnete Repository.

> Forks teilen die Daten des übergeordneten Repositories über BTRFS-Reflink, einschließlich aller auf der Festplatte gespeicherten Anmeldedaten. Siehe [Was Rediacc nicht isoliert](/de/docs/ai-agents-safety#was-rediacc-nicht-isoliert) für die Auswirkungen, wenn diese Anmeldedaten externe Dienste wie Stripe, AWS oder Railway autorisieren.

## Validieren

Die Dateisystemintegrität eines Repositories prüfen:

```bash
rdc repo validate --name my-app -m server-1
```

## Eigentümerschaft

Die Dateieigentümerschaft innerhalb eines Repositories auf den universellen Benutzer (UID 7111) setzen. Dies ist typischerweise erforderlich, nachdem Dateien von Ihrer Workstation hochgeladen wurden, die mit Ihrer lokalen UID ankommen.

```bash
rdc repo ownership --name my-app -m server-1
```

Der Befehl erkennt automatisch Docker-Container-Datenverzeichnisse (beschreibbare Bind-Mounts) und schließt sie aus. Dies verhindert das Beschädigen von Containern, die Dateien mit eigenen UIDs verwalten (z. B. MariaDB=999, www-data=33).

| Option | Beschreibung |
|--------|-------------|
| `--uid <uid>` | Eine benutzerdefinierte UID anstelle von 7111 setzen |
| `--skip-router-restart` | Neustart des Route-Servers nach der Operation überspringen |

Um die Eigentümerschaft aller Dateien zu erzwingen, einschließlich Container-Daten:

```bash
rdc repo ownership --name my-app -m server-1
```


Siehe den [Migrationsleitfaden](/en/docs/migration) für eine vollständige Anleitung, wann und wie die Eigentümerschaft bei der Projektmigration verwendet wird.

## Vorlage

Eine Vorlage anwenden, um ein Repository mit Dateien zu initialisieren:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Löschen

Ein Repository und alle darin enthaltenen Daten dauerhaft zerstören:

```bash
rdc repo delete --name my-app -m server-1
```

> Dies zerstört dauerhaft das verschlüsselte Disk-Image. Diese Aktion kann nicht rückgängig gemacht werden.

## Repository migrieren

Ein Repository mit minimaler Ausfallzeit live von einer Maschine auf eine andere migrieren.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Beschreibung |
|--------|-------------|
| `--provision` | Das Repository auf der Zielmaschine vor der Migration bereitstellen (erstellt LUKS-Image und registriert Konfiguration) |
| `--checkpoint` | Einen CRIU-Checkpoint laufender Container vor der Umschaltung erstellen |
| `--bwlimit <kbps>` | rsync-Bandbreite in Kilobytes pro Sekunde begrenzen |
| `--skip-dns` | DNS-Einträge nach der Umschaltung nicht aktualisieren |

**Drei-Phasen-Ablauf:**

1. **Heißes Pre-Copy** - rsync überträgt Daten, während das Repository auf der Quelle weiterläuft. Große Dateien werden vor jeder Ausfallzeit übertragen.
2. **Umschaltung** - Das Repository wird auf der Quelle gestoppt, ein abschließender rsync-Durchlauf synchronisiert verbleibende Änderungen, und das Repository startet auf dem Ziel.
3. **Start auf dem Ziel** - renet bindet das Repository ein und startet es auf der Zielmaschine. DNS wird aktualisiert, sofern nicht `--skip-dns` angegeben wurde.

![Repository-Live-Migration](/img/repo-migrate-flow.svg)

**Push vs. Migrieren:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Operation | Kopieren | Verschieben |
| Quelle danach | Unverändert | Gestoppt |
| Ausfallzeit | Keine (nur Kopie) | Kurzes Umschaltfenster |
| DNS-Aktualisierung | Nein | Ja (außer mit `--skip-dns`) |
| Anwendungsfall | Backup, Staging-Klon | Maschinenaustausch, Server-Umzug |

## Bereinigen

Nach dem Löschen von Repositories oder der Wiederherstellung nach fehlgeschlagenen Operationen können verwaiste Mount-Verzeichnisse, Lock-Dateien und unveränderliche Markierungen zurückbleiben. Die Bereinigung entfernt diese sicher:

```bash
# Vorschau der zu entfernenden Elemente
rdc machine prune --name server-1 --dry-run

# Verwaiste Ressourcen entfernen
rdc machine prune --name server-1
```

Nur Ressourcen ohne zugehöriges Repository-Image sind betroffen. Nicht leere Mount-Verzeichnisse werden nie entfernt.
