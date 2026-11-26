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
sourceHash: "ece2cec7cd2f4bc9"
sourceCommit: "948dc510c78b93b73ea5b1b7b379cdb93141486e"
---

## Überblick

Zwei MCP-Server (Model Context Protocol) beziehen ihre Tools aus einer Registry, der Remote-Server bietet davon eine Teilmenge:

| Server | Transport | Läuft als | Tools |
|---|---|---|---|
| Lokal | stdio | `rdc mcp serve`, vom Agenten gestartet | Alle Tools |
| Remote | Streamable HTTP | `https://mcp.<region>.rediacc.cloud/g/<grantId>` | Die Remote-Tools, also alle bis auf die Tabelle der rein lokalen |

**Voraussetzungen:** Für den lokalen Server ist `rdc` installiert und mit mindestens einer Maschine konfiguriert. Für den Remote-Server wird ein Grant auf einer Konfiguration benötigt.

## Lokaler Server

`rdc mcp serve` startet einen MCP-Server über stdio. Der Agent startet ihn als Unterprozess und spricht per JSON-RPC mit ihm.

### Claude Code

Die `.mcp.json` des Projekts enthält den Eintrag:

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

### Cursor

Öffnen Sie Einstellungen → MCP Servers → Server hinzufügen:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

### Optionen

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `--config <name>` | (Standardkonfiguration) | Benannte Konfiguration für alle Befehle |
| `--timeout <ms>` | `120000` | Standard-Timeout für Befehle in Millisekunden |

## Remote-Server

In jeder Region läuft ein MCP-Worker unter `mcp.<region>.rediacc.cloud`. Jeder Agent verbindet sich mit der URL genau eines Grants: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Der Grant benennt eine Konfiguration, ein Ablaufdatum und einen Geltungsbereich: ein Nur-Lesen-Flag, eine Tool-Allowlist sowie Namensmuster (Globs) für Maschinen und Repositories. Tool-Aufrufe laufen auf dem Organisations-Executor des Grants.

### Zugangsdaten

Beide Formen identifizieren den Grant; die Grant-ID in der URL benennt ihn nur.

| Form | Einsatz | Übermittlung |
|---|---|---|
| OAuth-Zugriffstoken | Interaktive Clients wie claude.ai | `Authorization: Bearer <token>` |
| Agent-Bearer `rmcp_<grantId>.<secret>` | Headless-Agenten | `Authorization: Bearer` oder `x-api-key` |

Zugangsdaten in der Query-Zeichenfolge werden mit 400 abgelehnt. Ein fehlendes, abgelaufenes oder zu einem anderen Grant gehörendes OAuth-Token erhält 401 mit einem `WWW-Authenticate: Bearer resource_metadata=...`-Header, der auf das Protected-Resource-Dokument des Grants verweist; so kann ein OAuth-Client das Token erneuern oder sich anmelden. Ein unbekannter Grant, ein falsches Secret und ein Agent-Bearer eines anderen Grants erhalten jeweils dieselbe schlichte 401.

### OAuth

Der Worker ist ein OAuth-2.1-Autorisierungsserver mit PKCE (nur S256). Clients registrieren sich über ein Client-ID-Metadata-Dokument oder per dynamischer Client-Registrierung unter `/register`.

| Endpunkt | Zweck |
|---|---|
| `/.well-known/oauth-authorization-server` | Server-Metadaten |
| `/.well-known/oauth-protected-resource/g/<grantId>` | Protected-Resource-Dokument eines Grants |
| `/authorize` | Startet die Autorisierung und leitet auf die Account-Seite `/account/mcp/authorize` weiter |
| `/oauth/token` | Code-Austausch, Refresh und Widerruf |
| `/register` | Dynamische Client-Registrierung |

Der Client sendet `resource=https://mcp.<region>.rediacc.cloud/g/<grantId>`. Die Autorisierung gelingt nur für den Grant, den die Ressource benennt, und ein Token funktioniert nur unter der URL seines Grants. Die Weiterleitung von `/authorize` trägt ein signiertes Einmal-Handle und kein Secret.

### Token-Laufzeiten

Ein Token überdauert nie seinen Grant.

| Token | Laufzeit |
|---|---|
| Zugriffstoken | Der kürzere Wert aus 1 Stunde und der Restlaufzeit des Grants |
| Refresh-Token | Der kürzere Wert aus 30 Tagen und der Restlaufzeit des Grants |

Bei jedem Code-Austausch und jedem Refresh wird der Grant erneut nachgeschlagen. Ein abgelaufener, widerrufener oder durch Schlüsselrotation ungültiger Grant antwortet mit `invalid_grant` und widerruft den OAuth-Grant. Refresh-Tokens rotieren; wer eines zweimal vorlegt, widerruft den Grant.

### Eine Konfiguration pro Grant

Ein Grant bedient genau die Konfiguration, die er benennt. Ein `tools/call` mit einem Argument, das eine andere Konfiguration benennt (`config` oder eine Schreibweise davon), wird mit `REDIACC_GRANT_SCOPE` abgelehnt, bevor irgendetwas läuft. Wer mehrere Konfigurationen hat, autorisiert pro Konfiguration einen Grant. Ein Tool außerhalb der Allowlist des Grants oder ein Schreib-Tool unter einem Nur-Lesen-Grant fehlt in `tools/list` und wird beim Aufruf abgelehnt.

### Regionen

Eine Grant-ID beginnt mit ihrer Region, etwa `eu_`. Eine Anfrage an `/g/<grantId>` beim Worker einer anderen Region wird mit 421 und der richtigen URL beantwortet:

```json
{
  "code": "REDIACC_WRONG_REGION",
  "message": "This grant lives in the us region. Use https://mcp.us.rediacc.cloud/g/us_...",
  "region": "us",
  "mcpUrl": "https://mcp.us.rediacc.cloud/g/us_..."
}
```

Ein Grant wird außerhalb seiner Region nie als OAuth-Ressource, Token-Audience oder Autorisierungsziel akzeptiert.

### Grant-Zustände und Limits

Ein Grant, der abgelaufen ist, widerrufen wurde oder durch eine Schlüsselrotation im Config-Store seinen Schlüssel verloren hat, beantwortet `initialize` und `tools/list` weiterhin. Jedes `tools/call` liefert dann `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` oder `REDIACC_KEY_ROTATED` mit einer `reauthUrl`, über die der Benutzer erneut autorisiert.

Jeder Grant erlaubt 60 Aufrufe pro Minute und 5 gleichzeitig laufende Aufrufe. Ein Aufruf über einem der beiden Limits liefert `REDIACC_RATE_LIMITED` mit `retryAfterSeconds`.

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
| `backup_toc-key_sync` | ja | Den Listing-Schlüssel des Repositorys auf dessen Maschine installieren oder einen abweichenden ersetzen. |
| `backup_undelete` | nein | Das verzögerte Löschen eines Snapshots abbrechen, bevor es wirksam wird. |
| `backup_usage` | nein | Backup-Speicherkontingent, gespeicherte Bytes und Nutzung pro Repository anzeigen. |
| `backup_verify` | nein | Den Backup-Anker eines Repositorys gegen den Chunk-Store verifizieren. |
| `cluster_snapshot_list` | nein | Die Gruppen-Snapshots des Clusters auflisten. |
| `cluster_status` | nein | Alle Cluster auflisten oder mit einem Clusternamen die vollständige Konfiguration dieses Clusters anzeigen. |
| `config_access_list` | nein | Die Zugriffsschlüssel der Konfiguration auflisten. |
| `config_prune` | ja | Ballast aus der lokalen Konfigurationsdatei `~/.config/rediacc/<config>.json` entfernen. |
| `config_reconcile` | nein | Den lokalen Zustandsspeicher anhand des tatsächlichen Maschinenzustands neu aufbauen (renet list all). |
| `config_show` | nein | Details der aktuellen Konfiguration anzeigen. |
| `credits` | nein | Das verbleibende Guthaben dieses Kontos anzeigen. |
| `datastore_list` | nein | Benannte Datastores auflisten, wo sie eingebunden sind und was sie enthalten. |
| `datastore_snapshot_list` | nein | Die Snapshots eines Datastores auflisten. |
| `datastore_status` | nein | Einen Datastore anzeigen: Backend, Anbindung, Nutzung, Repositories und Snapshots. |
| `feedback_list` | nein | Die für diese Maschine sichtbaren Feedback-Berichte auflisten: ID, kurzer Fingerabdruck, Status und Daten. |
| `feedback_report` | nein | Einen Bericht aus dem neuesten fehlgeschlagenen Befehl (--last), einem aufgezeichneten Befehl (`--command <n>`) oder nur aus einer Nachricht erstellen, genau anzeigen, was gesendet würde, und nach Bestätigung senden. |
| `feedback_show` | nein | Einen Feedback-Bericht anhand seiner ID (oder eines eindeutigen Präfixes) mit Status, Anzahl der Vorkommen und Daten anzeigen. |
| `incident_status` | nein | Die Vorfälle der Organisation auflisten oder einen einzelnen mit Umfang, Zeitfenster, Maschinenschritten und den Fristuhren für Frühwarnung, Meldung und Abschlussbericht anzeigen. |
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
| `repo_flows` | nein | Die für ein Repository in einem Zeitfenster aufgezeichneten Netzwerkflüsse auflisten: Zeit, Prozess, Ziel, ausgehende und eingehende Bytes sowie ASN und Land des Ziels, sofern bekannt. |
| `repo_fork` | ja | Einen nahezu sofortigen CoW-Fork eines Repositorys mit NEUER GUID und networkId erstellen (vollständig unabhängige Kopie). |
| `repo_gc` | ja | Garbage-Collection nach Erreichbarkeit: unveränderliche Commit-Objekte auf einer Maschine löschen, die kein Branch/HEAD erreicht. |
| `repo_health` | nein | Die health()-Prüfungen des Rediaccfile eines Repositorys ausführen und mit 0 (ok), 1 (Warnung) oder 2 (Fehler) beenden. |
| `repo_list` | nein | Repositories auf einer Maschine auflisten. |
| `repo_log` | nein | Den Commit-Verlauf ausgeben, der vom aktuellen Commit eines Arbeits-Forks (oder einer Commit-Referenz) erreichbar ist, entlang der von 'rdc repo commit' erfassten Elternkette. |
| `repo_logs` | nein | Anwendungslogs aus den Containern eines Repositorys anzeigen. |
| `repo_merge` | ja | Einen Quell-Commit oder -Fork lebenszyklussicher in einen Ziel-Arbeits-Fork mergen. |
| `repo_migrate` | ja | Ein Repository mit minimaler Ausfallzeit auf eine andere Maschine verschieben: zweiphasige Kopie (Massensynchronisation im Betrieb, dann kurzer Stopp, Delta-Sync und Start am Ziel) mit DNS-Umschaltung. |
| `repo_opens` | nein | Die für ein Repository in einem Zeitfenster aufgezeichneten Dateiöffnungen auflisten: Zeit, Prozess und Pfad, sensible Pfade markiert. |
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
| `forensics_verify` | nein | Die Hash-Kette der Audit-Tagesdateien und die signierten Forensik-Batch-Ketten eines Beweisverzeichnisses (eines Exportverzeichnisses von rdc incident) neu berechnen und jede Lücke und jede Änderung auflisten. |
| `incident_export` | nein | Das Zeitfenster des Vorfalls in ein Verzeichnis schreiben: den Vorfallsdatensatz mit seinen Uhren, die zusammengeführte Zeitachse, die Aggregate der ausgehenden Bytes, das rohe Ketten-Manifest und die darin aufgeführten Rohdateien unter ihren Manifest-Schlüsseln. |
| `machine_infra_cert_status` | nein | Das zwischengespeicherte Zertifikatsinventar anzeigen. |
| `server_status` | nein | Zustand, Tarif, Zertifikat und Image eines installierten Servers anzeigen. |
| `version` | nein | Die CLI-Version, Plattform, den Update-Kanal und die aktive Lizenz ausgeben: den Tarif bei Anmeldung, "anonymous (FREE per repository)" ohne Anmeldung und "unknown (server unreachable)", wenn der Account-Server nicht erreichbar ist. |

<!-- <<< translated-table -->

## Beispiel-Workflows

**Maschinenstatus prüfen:**
> „Wie ist der Status meiner Produktionsmaschine?"

Der Agent ruft `machine_status` auf und erhält Verbindungsdetails, Systeminformationen, Container, Dienste, Repositories und Ressourcennutzung.

**Eine Anwendung bereitstellen:**
> „Stelle GitLab auf meiner Staging-Maschine bereit"

Der Agent ruft `repo_up` mit `name: "gitlab"` und `machine: "staging"` auf; das stellt das Repository bereit und meldet Erfolg oder Fehler.

**Einen langen Job verfolgen:**
> „Stelle das gestrige Backup von Nextcloud wieder her"

Der Agent ruft `backup_restore` auf. Ein Befehl, der sein Zeitfenster überschreitet, liefert ein Job-Handle zurück, und der Agent ruft `job_wait` (bis zu 50 s pro Aufruf) und `job_logs` auf, bis der Job beendet ist.

**Einen fehlerhaften Dienst debuggen:**
> „Mein Nextcloud ist langsam, finde heraus, was los ist"

Der Agent ruft `machine_health`, dann `machine_containers` und `repo_logs` auf und schlägt eine Lösung vor.

## Sicherheit

Der lokale MCP-Server setzt zwei Schutzebenen durch. Die Limits des Remote-Servers stehen unter [Remote-Server](#remote-server).

### Fork-only-Modus (Standard)

Standardmäßig läuft der Server im **Fork-only-Modus**: Schreib-Tools (`repo_up`, `repo_down`, `repo_delete`, `repo_exec`, `repo_push`, `repo_pull`) können nur auf Fork-Repositories operieren. Agenten können Grand-Repositories (Originale) nicht anfassen. By design.

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

Der lokale MCP-Server ist zustandslos. Jeder Tool-Aufruf startet `rdc` als isolierten Kindprozess mit den Flags `--output json --yes --quiet`. Das bedeutet:

- Kein Zustandsüberlauf zwischen Tool-Aufrufen
- Verwendet Ihre bestehende `rdc`-Konfiguration und SSH-Schlüssel
- Fehler in einem Befehl beeinflussen andere nicht
