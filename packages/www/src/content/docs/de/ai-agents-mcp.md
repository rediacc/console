---
title: MCP-Server-Einrichtung
description: Verknüpfen Sie KI-Agenten über den Model Context Protocol (MCP) Server mit Ihrer Rediacc-Infrastruktur.
category: Guides
order: 33
language: de
sourceHash: "ce5f1392ebaa380b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

## Überblick

`rdc mcp serve` startet einen lokalen MCP-Server (Model Context Protocol), den KI-Agenten zur Verwaltung Ihrer Infrastruktur nutzen können. Der Server verwendet stdio-Transport; der Agent startet ihn als Unterprozess und kommuniziert über JSON-RPC.

**Voraussetzungen:** `rdc` installiert und mit mindestens einer Maschine konfiguriert.

## Claude Code

Fügen Sie Folgendes zur `.mcp.json` Ihres Projekts hinzu:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

Oder mit einer benannten Konfiguration:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Öffnen Sie Einstellungen → MCP Servers → Server hinzufügen:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

## Verfügbare Tools

### Lese-Tools (sicher, keine Seiteneffekte)

| Tool | Beschreibung |
|------|-------------|
| `machine_query` | Systeminformationen, Container, Dienste und Ressourcennutzung einer Maschine abrufen |
| `machine_containers` | Docker-Container mit Status, Health, Ressourcennutzung, Labels und Auto-Route-Domain auflisten |
| `machine_services` | Von Rediacc verwaltete systemd-Dienste auflisten (Name, Zustand, Sub-Zustand, Neustartanzahl, Speicher, zugehöriges Repository) |
| `machine_repos` | Bereitgestellte Repositories auflisten (Name, GUID, Größe, Mount-Status, Docker-Zustand, Container-Anzahl, Festplattennutzung, Änderungsdatum, Rediaccfile vorhanden) |
| `machine_health` | Gesundheitsprüfung auf einer Maschine durchführen (System, Container, Dienste, Speicher) |
| `machine_list` | Alle konfigurierten Maschinen auflisten |
| `config_repositories` | Konfigurierte Repositories mit Name-zu-GUID-Zuordnungen auflisten |
| `config_show_infra` | Infrastrukturkonfiguration einer Maschine anzeigen (Basis-Domain, öffentliche IPs, TLS, Cloudflare-Zone) |
| `config_providers` | Konfigurierte Cloud-Anbieter für die Maschinenbereitstellung auflisten |
| `agent_capabilities` | Alle verfügbaren rdc-CLI-Befehle mit Argumenten und Optionen auflisten |
| `repo_secret_list` | Secret-Namen und Übergabemodus für ein Repository auflisten (niemals Werte, niemals Digests). Lesezugriff-sicher. |
| `repo_secret_get` | SHA-256-Digest und Übergabemodus eines Secrets abrufen. Der Klartextwert wird by design niemals zurückgegeben. Dient zur Überprüfung, ob ein Secret vorhanden ist oder rotiert wurde. |

### Schreib-Tools (destruktiv)

| Tool | Beschreibung |
|------|-------------|
| `repo_create` | Neues verschlüsseltes Repository auf einer Maschine erstellen |
| `repo_up` | Repository bereitstellen/aktualisieren (führt Rediaccfile up aus, startet Container). Für erste Bereitstellung oder nach Pull `mount` verwenden |
| `repo_down` | Repository-Container stoppen. Hebt die Einbindung standardmäßig NICHT auf. Mit `unmount` wird auch der LUKS-Container geschlossen |
| `repo_delete` | Repository löschen (zerstört Container, Volumes, verschlüsseltes Image). Credential wird für Wiederherstellung archiviert |
| `repo_fork` | CoW-Fork mit neuer GUID und networkId erstellen (vollständig unabhängige Kopie, Online-Forking unterstützt) |
| `backup_push` | Repository-Backup in den Speicher oder auf eine andere Maschine übertragen (gleiche GUID -- Backup/Migration, kein Fork) |
| `backup_pull` | Repository-Backup aus dem Speicher oder von einer Maschine abrufen. Nach dem Pull mit `repo_up` (mount=true) bereitstellen |
| `machine_provision` | Neue Maschine bei einem Cloud-Anbieter mit OpenTofu bereitstellen |
| `machine_deprovision` | Cloud-bereitgestellte Maschine zerstören und aus der Konfiguration entfernen |
| `config_add_provider` | Cloud-Anbieter-Konfiguration für Maschinenbereitstellung hinzufügen |
| `config_remove_provider` | Cloud-Anbieter-Konfiguration entfernen |
| `term_exec` | Befehl auf einer Remote-Maschine über SSH ausführen |

## Beispiel-Workflows

**Maschinenstatus prüfen:**
> „Wie ist der Status meiner Produktionsmaschine?"

Der Agent ruft `machine_query` auf → gibt Systeminformationen, laufende Container, Dienste und Ressourcennutzung zurück.

**Eine Anwendung bereitstellen:**
> „Stelle GitLab auf meiner Staging-Maschine bereit"

Der Agent ruft `repo_up` mit `name: "gitlab"` und `machine: "staging"` auf → stellt das Repository bereit, gibt Erfolg/Fehler zurück.

**Einen fehlerhaften Dienst debuggen:**
> „Mein Nextcloud ist langsam, finde heraus, was los ist"

Der Agent ruft `machine_health` → `machine_containers` → `term_exec` auf, um Logs zu lesen → identifiziert das Problem und schlägt eine Lösung vor.

## Konfigurationsoptionen

| Option | Standard | Beschreibung |
|--------|---------|-------------|
| `--config <name>` | (Standardkonfiguration) | Benannte Konfiguration für alle Befehle |
| `--timeout <ms>` | `120000` | Standard-Befehls-Timeout in Millisekunden |
| `--allow-grand` | off | Destruktive Operationen auf Grand-Repositories (keine Forks) erlauben |

## Sicherheit

Der MCP-Server setzt zwei Schutzebenen durch:

### Fork-only-Modus (Standard)

Standardmäßig läuft der Server im **Fork-only-Modus**: Schreib-Tools (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) können nur auf Fork-Repositories operieren. Agenten können Grand-Repositories (Originale) nicht anfassen. By design.

> **Per-Repo-Secrets sind by design ausschließlich über die CLI zugänglich.** `repo_secret_set` und `repo_secret_unset` werden absichtlich **nicht** als MCP-Tools bereitgestellt. Schreibvorgänge erfordern eine `--current <previous-value>`-Vorbedingung (oder `--rotate-secret`, um eine ungeprüfte Rotation zu bestätigen), und dieser Vorgang erfordert menschliche Aufsicht. Agenten, die eine Secret-Rotation vorschlagen möchten, sollten `repo_secret_get` aufrufen, um den Digest zu bestätigen, und dann den operatorseitigen CLI-Befehl über das strukturierte Feld `next.options[].run` im JSON-Fehler-Envelope an den Benutzer weitergeben. Weitere Informationen finden Sie unter [AI Agent Safety](/en/docs/ai-agents-safety#structured-next-action-hints) sowie unter [Repositories § Secrets](/en/docs/repositories#secrets).

Um einem Agenten zu erlauben, Grand-Repos zu ändern, starten Sie den Server mit `--allow-grand`:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

Sie können die Umgebungsvariable `REDIACC_ALLOW_GRAND_REPO` auch auf einen einzelnen Repo-Namen, auf eine durch Kommas getrennte Liste von Repo-Namen (zum Beispiel `repo1,repo2,repo3`) oder auf `*` für alle Repos setzen. Leerzeichen um die Einträge werden ignoriert, `repo1, repo2` funktioniert also ebenfalls. Maschinenweiter Zugriff (etwa `term connect -m <machine>` ohne Repo) erfordert weiterhin `*`; eine Liste von Repo-Namen schaltet ihn nicht frei.

### Per-Repo-SSH-Schlüssel und serverseitige Sandbox

Jedes Repository verfügt über ein eigenes SSH-Schlüsselpaar. Der öffentliche Schlüssel wird in `authorized_keys` mit einem `command=`-Präfix deployed, das alle SSH-Sitzungen durch `renet sandbox-gateway <repo-name>` leitet -- ein serverseitiger ForceCommand, der von keinem Client umgangen werden kann, einschließlich VS Code.

**Funktionsweise:**
1. `rdc repo create` oder `rdc repo fork` generiert ein eindeutiges ed25519-Schlüsselpaar pro Repository
2. Der öffentliche Schlüssel wird mit `command="renet sandbox-gateway <name>"` auf dem Remote-Server deployed
3. Jede SSH-Verbindung über diesen Schlüssel wird durch das Gateway geleitet, das folgendes anwendet:
   - **Landlock LSM**: kernelseitige Dateisystemeinschränkungen auf den Mount-Pfad des Repositories
   - **OverlayFS-Home-Overlay**: Schreibvorgänge in `$HOME` werden pro Repository erfasst, Lesevorgänge fallen auf das echte Home-Verzeichnis durch
   - **Repo-eigenes TMPDIR** unter `<datastore>/.interim/sandbox/<name>/tmp/`
   - **Docker-Zugriff** über den isolierten Docker-Socket des Repositories
   - **Privilege Drop** auf den universellen Benutzer (`rediacc`)
4. Die `.envrc` des Repositories wird automatisch für Docker und die Umgebungseinrichtung geladen

**Erlaubt RW**: Mount-Pfad des Repositories, repo-eigener Sandbox-Workspace, Home-Verzeichnis (via Overlay), Docker-Socket
**Erlaubt RO**: Systempfade (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**Gesperrt**: Mount-Pfade anderer Repositories, Systemdateien außerhalb der Allowlist

**VS-Code-Integration**: Jedes Repository erhält eine eigene VS-Code-Server-Installation unter `<datastore>/.interim/sandbox/<name>/.vscode-server/`. Mehrere Repositories können gleichzeitig geöffnet sein, mit unabhängig voneinander gesandboxten Umgebungen -- kein gemeinsam genutzter Server zwischen Repositories.

Dies verhindert laterale Bewegungen. Selbst wenn ein Agent Shell-Zugriff auf einen Fork erlangt, kann er keine anderen Repositories auf derselben Maschine lesen oder ändern. SSH auf Maschinenebene (ohne Repository) verwendet den Team-Schlüssel und ist nicht sandboxed.

## Architektur

Der MCP-Server ist zustandslos. Jeder Tool-Aufruf startet `rdc` als isolierten Kindprozess mit den Flags `--output json --yes --quiet`. Das bedeutet:

- Kein Zustandsüberlauf zwischen Tool-Aufrufen
- Verwendet Ihre bestehende `rdc`-Konfiguration und SSH-Schlüssel
- Funktioniert sowohl mit dem lokalen als auch dem Cloud-Adapter
- Fehler in einem Befehl beeinflussen andere nicht
