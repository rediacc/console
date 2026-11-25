---
title: MCP-Server-Einrichtung
description: Verknüpfen Sie KI-Agenten über den Model Context Protocol (MCP) Server mit Ihrer Rediacc-Infrastruktur.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: de
sourceHash: "5ffb60357e13aeab"
sourceCommit: "a2b1f5471f48c44fb704157f615369df9c354832"
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

<!-- >>> translated-table: mcp-tools -->

| Tool | Destruktiv | Beschreibung |
|---|---|---|
| `backup_browse` | nein | Die Dateien auflisten, die ein Repository enthält. |
| `backup_cancel` | nein | Ein laufendes Backup auf einer Remote-Maschine abbrechen. |
| `backup_check` | nein | Prüfen, dass sich ein gespeicherter Snapshot mit der Passphrase öffnen lässt, indem eine Datei wiederhergestellt wird. |
| `backup_immutability_show` | nein | Das geltende Zeitfenster für verzögertes Löschen anzeigen. |
| `backup_list` | nein | Backup-Artefakte auf einer Maschine auflisten. |
| `backup_manifests` | nein | Die auf dem Server erfassten Backup-Snapshot-Manifeste auflisten. |
| `backup_reconcile` | ja | Das Ledger der gespeicherten Bytes eines Repositorys auf den tatsächlichen Stand des Speichers zurücksetzen (löscht nie einen Chunk). |
| `backup_repair` | ja | Chunks, die der Speicher verloren hat oder fehlerhaft vorhält, vom Anker dieser Maschine aus neu hochladen. |
| `backup_restore` | ja | Ein Backup-Artefakt in ein aktives Repository umwandeln. |
| `backup_retention` | nein | Die Aufbewahrungsrichtlinie für Snapshots anzeigen, die der Server durchsetzt. |
| `backup_retention_preview` | nein | Anzeigen, welche Snapshots der nächste Bereinigungslauf löschen würde und wie viel Speicherplatz dadurch frei wird. |
| `backup_run` | nein | Ein Backup sofort ausführen. |
| `backup_snapshot` | nein | Einen Chunk-Store-Snapshot hochladen: zuerst das vollständige Inventar, danach die geänderten Zellen. |
| `backup_status` | nein | Backup-Status und Timer-Zustand auf einer Remote-Maschine anzeigen. |
| `backup_strategy_list` | nein | Alle Backup-Strategien auflisten. |
| `backup_strategy_show` | nein | Details einer Backup-Strategie anzeigen. |
| `backup_toc-key_sync` | nein | Den Listing-Schlüssel des Repositorys auf dessen Maschine installieren oder einen abweichenden ersetzen. |
| `backup_undelete` | nein | Das verzögerte Löschen eines Snapshots abbrechen, bevor es wirksam wird. |
| `backup_usage` | nein | Backup-Speicherkontingent, gespeicherte Bytes und Nutzung pro Repository anzeigen. |
| `backup_verify` | nein | Den Backup-Anker eines Repositorys gegen den Chunk-Store verifizieren. |
| `cluster_snapshot_list` | nein | Die Gruppen-Snapshots des Clusters auflisten. |
| `cluster_status` | nein | Alle Cluster auflisten oder mit einem Clusternamen die vollständige Konfiguration dieses Clusters anzeigen. |
| `config_access_list` | nein | Die Zugriffsschlüssel der Konfiguration auflisten. |
| `config_prune` | nein | Ballast aus der lokalen Konfigurationsdatei ~/.config/rediacc/<config>.json entfernen. |
| `config_reconcile` | nein | Den lokalen Zustandsspeicher anhand des tatsächlichen Maschinenzustands neu aufbauen (renet list all). |
| `config_show` | nein | Details der aktuellen Konfiguration anzeigen. |
| `credits` | nein | Das verbleibende Guthaben dieses Kontos anzeigen. |
| `datastore_list` | nein | Benannte Datastores auflisten, wo sie eingebunden sind und was sie enthalten. |
| `datastore_snapshot_list` | nein | Die Snapshots eines Datastores auflisten. |
| `datastore_status` | nein | Einen Datastore anzeigen: Backend, Anbindung, Nutzung, Repositories und Snapshots. |
| `feedback_list` | nein | Die für diese Maschine sichtbaren Feedback-Berichte auflisten: ID, kurzer Fingerabdruck, Status und Daten. |
| `feedback_report` | nein | Einen Bericht aus dem neuesten fehlgeschlagenen Befehl (--last), einem aufgezeichneten Befehl (--command <n>) oder nur aus einer Nachricht erstellen, genau anzeigen, was gesendet würde, und nach Bestätigung senden. |
| `feedback_show` | nein | Einen Feedback-Bericht anhand seiner ID (oder eines eindeutigen Präfixes) mit Status, Anzahl der Vorkommen und Daten anzeigen. |
| `job_cancel` | ja | Einen laufenden losgelösten Job abbrechen. |
| `job_dismiss` | ja | Job-Tickets lokal aufgeben: Die offenen Schritte entfallen, und das Ticket erscheint nicht mehr. |
| `job_gc` | ja | Abgeschlossene Jobs und ihre Logs entfernen. |
| `job_list` | nein | Losgelöste Jobs auf einer Maschine auflisten, neueste zuerst. |
| `job_logs` | nein | Das Ereignisprotokoll eines losgelösten Jobs wiedergeben oder live verfolgen. |
| `job_status` | nein | Den Status eines losgelösten Jobs anzeigen. |
| `job_wait` | nein | Bis zu 50 s auf das Ende eines Jobs warten. |
| `legal` | nein | Die Links zu den Rechtsdokumenten in der CLI-Sprache samt verbindlichen englischen Links ausgeben, dazu die aktuelle Version der Nutzungsbedingungen mit Prüfsumme und Archiv-URL, die hinterlegte Zustimmung (vom Account-Server bei Anmeldung, aus dieser Konfiguration anonym) und die Vertragspartei. |
| `machine_access_show` | nein | Die an eine Maschine gebundenen Zugriffsschlüssel und die dort jeweils aufgelösten Bereiche anzeigen. |
| `machine_add` | nein | Eine vorhandene Maschine registrieren, die sich per SSH erreichen lässt. |
| `machine_containers` | nein | Docker-Container auf einer Maschine auflisten. |
| `machine_converge` | ja | Jeden Repository-Daemon, der noch mit einem älteren Runtime-Layout läuft, nacheinander neu starten, damit er auf das aktuelle wechselt. |
| `machine_deprovision` | ja | Eine per Cloud bereitgestellte Maschine zerstören und aus der Konfiguration entfernen. |
| `machine_gpu_list` | nein | Die auf einer Maschine erkannten GPUs, die in ihren Spezifikationen definierten CDI-Gerätenamen und die Repositories auflisten, denen jedes Gerät zugewiesen ist. |
| `machine_health` | nein | Den Zustand einer Maschine für CI/CD-Pipelines prüfen. |
| `machine_infra_show` | nein | Infrastrukturkonfiguration einer Maschine anzeigen (Basis-Domain, öffentliche IPs, Ports), gemeinsame TLS-Einstellungen (Zertifikats-E-Mail, CF-DNS-Token) und die Cloudflare-Zonen-ID. |
| `machine_list` | nein | Maschinen auflisten. |
| `machine_provider_add` | nein | Einen Cloud-Anbieter hinzufügen. |
| `machine_provider_list` | nein | Konfigurierte Cloud-Anbieter für die Maschinenbereitstellung auflisten. |
| `machine_provider_remove` | ja | Die Konfiguration eines Cloud-Anbieters entfernen. |
| `machine_provision` | ja | Eine neue Maschine bei einem Cloud-Anbieter mit OpenTofu bereitstellen. |
| `machine_prune` | ja | Verwaiste Datastore-Ressourcen und veraltete Snapshots von einer Maschine entfernen. |
| `machine_remove` | ja | Eine Maschine aus der Konfiguration entfernen. |
| `machine_repos` | nein | Bereitgestellte Repositories auf einer Maschine auflisten. |
| `machine_restart-services` | ja | Die renet-Daemons, die noch eine ersetzte Binärdatei ausführen, einheitenweise auf die installierte umstellen und jeweils bestätigen, dass sie aktiv ist, bevor die nächste folgt. |
| `machine_scan-keys` | nein | Die SSH-Hostschlüssel der Maschine in der lokalen Konfiguration erfassen. |
| `machine_services` | nein | Von Rediacc verwaltete systemd-Dienste auf einer Maschine auflisten (Name, Zustand, Unterzustand, Neustartanzahl, Speicher, Repository als Name aufgelöst, Original in repository_guid). |
| `machine_setup` | nein | Die Einrichtung einer Maschine abschließen: renet installieren und sie für das Hosten von Repositories vorbereiten. |
| `machine_status` | nein | Verbindungsdetails (IP, Benutzer, Port, Datastore), Systeminformationen, Container (Repository als Name aufgelöst, Original in repository_guid, Domain, autoRoute), Dienste (Repository als Name aufgelöst), Repositories (Name aus GUID aufgelöst, Original in guid) und Ressourcennutzung einer Maschine abrufen. |
| `repo_admin_fsck` | nein | Konfigurationsreferenzen (Branches/HEAD) gegen die auf einer Maschine vorhandenen Objekte prüfen und hängende Referenzen sowie verwaiste Commits melden. |
| `repo_cat` | nein | Einen begrenzten Ausschnitt einer Datei in einem Repository auf stdout lesen (Diagnosen gehen an stderr). |
| `repo_checkout` | ja | Einen unveränderlichen Commit (oder Branch-Spitze) per Reflink in einen frischen beschreibbaren Arbeits-Fork klonen und HEAD darauf setzen. |
| `repo_commit` | ja | Einen eingebundenen Arbeits-Fork in einen neuen unveränderlichen Commit einfrieren (wie bei Git). |
| `repo_create` | ja | Ein neues Repository erstellen. |
| `repo_delete` | ja | Ein Repository samt Daten löschen. |
| `repo_diff` | nein | Datei-Diff im Git-Stil zwischen zwei Copy-on-Write-Fork-Repositories. |
| `repo_down` | ja | Die Docker-Container eines Repositorys stoppen (führt Rediaccfile down aus). |
| `repo_exec` | ja | Einen Befehl in einem Repository-Container ausführen. |
| `repo_fork` | ja | Einen nahezu sofortigen CoW-Fork eines Repositorys mit NEUER GUID und networkId erstellen (vollständig unabhängige Kopie). |
| `repo_gc` | ja | Garbage-Collection nach Erreichbarkeit: unveränderliche Commit-Objekte auf einer Maschine löschen, die kein Branch/HEAD erreicht. |
| `repo_health` | nein | Die health()-Prüfungen des Rediaccfile eines Repositorys ausführen und mit 0 (ok), 1 (Warnung) oder 2 (Fehler) beenden. |
| `repo_list` | nein | Repositories auf einer Maschine auflisten. |
| `repo_log` | nein | Den Commit-Verlauf ausgeben, der vom aktuellen Commit eines Arbeits-Forks (oder einer Commit-Referenz) erreichbar ist, entlang der von 'rdc repo commit' erfassten Elternkette. |
| `repo_logs` | nein | Anwendungslogs aus den Containern eines Repositorys anzeigen. |
| `repo_merge` | ja | Einen Quell-Commit oder -Fork lebenszyklussicher in einen Ziel-Arbeits-Fork mergen. |
| `repo_migrate` | ja | Ein Repository mit minimaler Ausfallzeit auf eine andere Maschine verschieben: zweiphasige Kopie (Massensynchronisation im Betrieb, dann kurzer Stopp, Delta-Sync und Start am Ziel) mit DNS-Umschaltung. |
| `repo_pull` | ja | Ein Repository von einer anderen Maschine holen. |
| `repo_push` | ja | Ein Repository-Backup in den Speicher oder direkt auf eine andere Maschine übertragen. |
| `repo_replicate` | nein | Lese-Replikate eines Repositorys bereitstellen. |
| `repo_replicate_remove` | ja | Ein Replikat-Set entfernen: seine erzeugten k8s-Objekte (label-begrenzt) löschen, seine Fork-Datastores verwerfen, seinen Snapshot entfernen und den Zustand vergessen. |
| `repo_replicate_status` | nein | Verwaltete Replikat-Sets anzeigen: Replikate, Host-Knoten, Fork-Datastores, Snapshot und Aktualisierungszeitpunkte. |
| `repo_secret_get` | nein | Den SHA-256-Digest eines Secrets anzeigen. |
| `repo_secret_list` | nein | Secret-Schlüssel und -Modi auflisten (nie Werte, nie Digests). |
| `repo_status` | nein | Repository-Status abrufen (Mount-Zustand, Docker-Daemon läuft, Container-Anzahl, Festplattennutzung). |
| `repo_trim` | nein | Speicherplatz des Datastore-Pools aus eingebundenen Repositories freigeben (online, ohne Ausfallzeit). |
| `repo_up` | ja | Ein Repository bereitstellen oder aktualisieren (führt Rediaccfile up über renet compose aus, startet Container). |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| Tool | Destruktiv | Beschreibung |
|---|---|---|
| `cluster_kubeconfig` | nein | Die kubeconfig vom Control-Node des Clusters per SSH abrufen und lokal für kubectl zwischenspeichern (0600). |
| `config_audit_log` | nein | Das Audit-Log der über diese Konfiguration vorgenommenen Änderungen lesen. |
| `config_audit_verify` | nein | Prüfen, dass die Hash-Kette des Audit-Logs nicht manipuliert wurde. |
| `config_current` | nein | Die aktive Konfiguration anzeigen: Name, Datei, aufgelöster Server und Kanal, Token-Zustand. |
| `config_list` | nein | Alle Konfigurationsdateien auflisten. |
| `machine_infra_cert_status` | nein | Das zwischengespeicherte Zertifikatsinventar anzeigen. |
| `server_status` | nein | Zustand, Tarif, Zertifikat und Image eines installierten Servers anzeigen. |
| `version` | nein | Die CLI-Version, Plattform, den Update-Kanal und die aktive Lizenz ausgeben: den Tarif bei Anmeldung, "anonymous (FREE per repository)" ohne Anmeldung und "unknown (server unreachable)", wenn der Account-Server nicht erreichbar ist. |

<!-- <<< translated-table -->

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

## Sicherheit

Der MCP-Server setzt zwei Schutzebenen durch:

### Fork-only-Modus (Standard)

Standardmäßig läuft der Server im **Fork-only-Modus**: Schreib-Tools (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) können nur auf Fork-Repositories operieren. Agenten können Grand-Repositories (Originale) nicht anfassen. By design.

> **Per-Repo-Secrets sind by design ausschließlich über die CLI zugänglich.** `repo_secret_set` und `repo_secret_unset` werden absichtlich **nicht** als MCP-Tools bereitgestellt. Schreibvorgänge erfordern eine `--current <previous-value>`-Vorbedingung (oder `--rotate-secret`, um eine ungeprüfte Rotation zu bestätigen), und dieser Vorgang erfordert menschliche Aufsicht. Agenten, die eine Secret-Rotation vorschlagen möchten, sollten `repo_secret_get` aufrufen, um den Digest zu bestätigen, und dann den operatorseitigen CLI-Befehl über das strukturierte Feld `next.options[].run` im JSON-Fehler-Envelope an den Benutzer weitergeben. Weitere Informationen finden Sie unter [AI Agent Safety](/en/docs/ai-agents-safety#structured-next-action-hints) sowie unter [Repositories § Secrets](/en/docs/repositories#secrets).

Um einem Agenten zu erlauben, Grand-Repos zu ändern, exportieren Sie `REDIACC_ALLOW_GRAND_REPO` in Ihrem Terminal **vor dem Start des Agenten, der den MCP-Server hostet**:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # ein Repo
# oder 'repo1,repo2,repo3' (Leerzeichen um Einträge werden ignoriert), oder '*' für alle Repos
claude   # oder cursor, gemini, usw.
```

Die Überschreibung wird gegen die Prozessabstammung verifiziert: Sie zählt nur, wenn sie bereits in der Umgebung des Agent-Prozesses selbst vorhanden war, was bedeutet, dass Sie sie exportiert haben, bevor der Agent (und der MCP-Server, den er startete) gestartet wurde. Ein Agent kann sich selbst Zugriff gewähren, indem er die Variable mitten in einer Sitzung setzt. Es gibt bewusst keine Server-Flag dafür: Eine Flag in den MCP-Server-Argumenten trägt keinen Beweis dafür, wer sie dort eingefügt hat, während die Abstammungsverifizierung das tut. Maschinenstufe-Zugriff (etwa `term connect <machine>` ohne Repo) erfordert weiterhin `*`; eine Liste von Repo-Namen schaltet ihn nicht frei.

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
- Fehler in einem Befehl beeinflussen andere nicht
