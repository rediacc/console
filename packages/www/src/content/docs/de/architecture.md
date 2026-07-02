---
title: Architektur
description: >-
  Wie Rediacc funktioniert: Zwei-Tool-Architektur, Adapter-Erkennung,
  Sicherheitsmodell und Konfigurationsstruktur.
category: Concepts
order: 0
language: de
sourceHash: "947fcefa63eac600"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Architektur

Also: rdc auf Ihrer Workstation, renet auf Ihren Servern, Kommunikation über SSH. Auf dieser Aufteilung ruht die gesamte Architektur von Rediacc. Diese Seite beschreibt, wie die beiden Tools ihre Verantwortungen aufteilen, wie die Adapter-Erkennung den Zustand leitet, wie das Sicherheitsmodell aussieht und wie die Konfiguration strukturiert ist.

## Gesamtstack-Überblick

Der Traffic fließt vom Internet durch einen Reverse-Proxy in isolierte Docker-Daemons, die jeweils durch verschlüsselten Speicher abgesichert sind:

![Gesamtstack-Architektur](/img/arch-full-stack.svg)

Jedes Repository erhält seinen eigenen Docker-Daemon, ein Loopback-IP-Subnetz (/26 = 64 IPs) und ein LUKS-verschlüsseltes BTRFS-Volume. Der Route-Server erkennt laufende Container über alle Daemons hinweg und speist die Routing-Konfiguration in Traefik ein.

## Zwei-Tool-Architektur

Rediacc verwendet zwei Binaries, die über SSH zusammenarbeiten:

![Zwei-Tool-Architektur](/img/arch-two-tool.svg)

- **rdc** läuft auf Ihrer Workstation (macOS, Linux oder Windows). Es liest Ihre lokale Konfiguration, verbindet sich über SSH mit entfernten Rechnern und ruft renet-Befehle auf.
- **renet** läuft auf dem entfernten Server mit Root-Rechten. Es verwaltet LUKS-verschlüsselte Disk-Images, isolierte Docker-Daemons, Service-Orchestrierung und Reverse-Proxy-Konfiguration.

Jeder Befehl, den Sie lokal eingeben, wird in einen SSH-Aufruf übersetzt, der renet auf dem entfernten Rechner ausführt. Sie müssen sich nie manuell per SSH auf den Servern anmelden.

Für eine operatorfokussierte Faustregel, siehe [rdc vs renet](/en/docs/rdc-vs-renet). Sie können auch `rdc ops` verwenden, um einen lokalen VM-Cluster zum Testen zu starten, siehe [Experimentelle VMs](/en/docs/experimental-vms).

## Konfiguration

Der gesamte CLI-Zustand wird in flachen JSON-Konfigurationsdateien unter `~/.config/rediacc/` gespeichert.

Der gesamte Zustand liegt in einer Konfigurationsdatei auf Ihrer Workstation (z. B. `~/.config/rediacc/rediacc.json`).

- Direkte SSH-Verbindungen zu Maschinen
- Keine externen Dienste erforderlich
- Die Standardkonfiguration wird beim ersten CLI-Aufruf automatisch erstellt. Benannte Konfigurationen werden mit `rdc config init --name <name>` erstellt
- Optionale verschlüsselte Config-Synchronisation speichert dieselbe Datei im Config Store, team-spezifisch

## Der rediacc-Benutzer

Wenn Sie `rdc config machine setup` ausführen, erstellt renet einen Systembenutzer namens `rediacc` auf dem entfernten Server:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (kann sich nicht per SSH anmelden)
- **Zweck**: Besitzt Repository-Dateien und führt Rediaccfile-Funktionen aus

Der `rediacc`-Benutzer kann nicht direkt per SSH erreicht werden. Stattdessen verbindet sich rdc als der von Ihnen konfigurierte SSH-Benutzer (z. B. `deploy`), und renet führt Repository-Operationen über `sudo -u rediacc /bin/sh -c '...'` aus. Das bedeutet:

1. Ihr SSH-Benutzer benötigt `sudo`-Rechte
2. Alle Repository-Daten gehören `rediacc`, nicht Ihrem SSH-Benutzer
3. Rediaccfile-Funktionen (`up()`, `down()`) laufen als `rediacc`

Diese Trennung stellt sicher, dass Repository-Daten unabhängig vom verwaltenden SSH-Benutzer eine konsistente Eigentümerschaft haben.

## Docker-Isolation

Jedes Repository erhält seinen eigenen isolierten Docker-Daemon. Wenn ein Repository eingebunden wird, startet renet einen dedizierten `dockerd`-Prozess mit einem einzigartigen Socket:

![Docker-Isolation](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Zum Beispiel verwendet ein Repository mit Netzwerk-ID `2816`:
```
/var/run/rediacc/docker-2816.sock
```

Das bedeutet:
- Container aus verschiedenen Repositories können sich gegenseitig nicht sehen
- Jedes Repository hat seinen eigenen Image-Cache, eigene Netzwerke und Volumes
- Der Docker-Daemon des Hosts (falls vorhanden) ist vollständig getrennt

Rediaccfile-Funktionen haben automatisch `DOCKER_HOST` auf den korrekten Socket gesetzt.

Wenn ein KI-Agent über `rdc term connect -r <repo>` ein Repository betritt, gilt dieselbe Isolation: Die Sitzung läuft als unprivilegierter `rediacc`-Benutzer (UID 7111), in einem eigenen Mount-Namespace, mit `DOCKER_HOST`, das auf den Daemon-Socket dieses einen Repositories beschränkt ist. Der Fork-First-Workflow kombiniert diese Laufzeitisolation mit einer CoW-Klon-Primitive: Der Agent arbeitet auf einem Fork pro Aufgabe, niemals auf Grand-Repositories (Produktion). Siehe [KI-Agent-Sicherheit & Schutzmaßnahmen](/en/docs/ai-agents-safety) für das vollständige Sandbox-Modell, die Überschreibungssemantik und die Entwicklerverantwortungsgrenze für Anmeldedaten externer Dienste.

### Daemon-Pfadstruktur

Docker-Daten und -Konfiguration werden innerhalb des Repository-Einhängepunkts gespeichert, wodurch jeder Daemon vollständig vom Host und von anderen Repositories isoliert bleibt.

**Pro-Repository-Struktur:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Docker-Datenwurzel
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Docker-Konfiguration
```

**Standalone-Struktur** (Daemons ohne angehängten Repository-Einhängepunkt):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**Gemeinsamer Laufzeitpfad** (unverändert):
```
/run/rediacc/docker-{N}.sock
```

Diese einheitliche Struktur beseitigt Konflikte zwischen schreibgeschützten und schreibbaren Einhängepunkten, die auftraten, wenn Daemon-Pfade zwischen dem Host-Dateisystem und dem verschlüsselten Volume aufgeteilt waren. Wir sind auf diese Aufteilung mehr als einmal gestoßen, bevor wir uns auf diese Lösung einigten. Sowohl Pro-Repository- als auch Standalone-Daemons folgen derselben Verzeichnisstruktur, sodass Werkzeuge und Diagnosen in beiden Fällen identisch funktionieren.

## LUKS-Verschlüsselung

Repositories sind LUKS-verschlüsselte Disk-Images, die im Datastore des Servers gespeichert werden (Standard: `/mnt/rediacc`). Jedes Repository:

1. Hat eine zufällig generierte Verschlüsselungs-Passphrase (das "Credential")
2. Wird als Datei gespeichert: `{datastore}/repos/{guid}.img`
3. Wird über `cryptsetup` eingebunden, wenn darauf zugegriffen wird

Das Credential wird in Ihrer Konfigurationsdatei gespeichert, jedoch **niemals** auf dem Server. Ohne das Credential können die Repository-Daten nicht gelesen werden. Wenn Autostart aktiviert ist, wird eine sekundäre LUKS-Schlüsseldatei auf dem Server gespeichert, um das automatische Einbinden beim Hochfahren zu ermöglichen.

## Konfigurationsstruktur

Jede Konfiguration ist eine flache JSON-Datei, die in `~/.config/rediacc/` gespeichert wird. Die Standardkonfiguration ist `rediacc.json`; benannte Konfigurationen verwenden den Namen als Dateiname (z. B. `production.json`). Felder sind nach Zweck eingeteilt: `resources` enthält Deployments, `credentials` enthält Geheimnisse, `account` enthält Cloud-Standardwerte, `infra` enthält TLS/DNS und `encryption` enthält den verschlüsselten Zustand einzelner Felder. Der Top-Level-Diskriminator `schemaVersion: 2` verankert die Vorwärtskompatibilität.

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
    "machines": {
      "prod-1": {
        "ip": "203.0.113.50",
        "user": "deploy",
        "port": 22,
        "datastore": "/mnt/rediacc",
        "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
      }
    },
    "storages": {
      "backblaze": {
        "provider": "b2",
        "vaultContent": { "...": "..." }
      }
    },
    "repositories": {
      "webapp": {
        "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "credential": "base64-encoded-random-passphrase",
        "networkId": 2816
      }
    }
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**Wichtige Buckets:**

| Bucket | Inhalt |
|---|---|
| `schemaVersion` | Diskriminator (aktuell `2`). Loader lehnen unbekannte Versionen ab. |
| `id` / `version` | Unveränderliche UUID + monotoner Zähler; werden für optimistisches Locking im Remote-Config-Store verwendet. |
| `defaults.*` | Nicht-sensible Laufzeit-Standardwerte (`machine`, `language`, `pruneGraceDays`, `universalUser`, `nextNetworkId`). |
| `credentials.ssh` | Inline-SSH-Schlüsselpaar + `knownHosts`. Ersetzt den veralteten `ssh.privateKeyPath` (keine Datei-Pfad-Indirection mehr; der Inhalt wird zur Ladezeit aufgelöst und inline gespeichert). |
| `credentials.cfDnsApiToken` | Cloudflare-DNS-01-ACME-Token. |
| `credentials.masterPasswordVerifier` | Nur vorhanden, wenn `encryption.mode === "master-password"`. |
| `resources.machines.*` | SSH-Verbindungsdetails pro Maschine. |
| `resources.storages.*` | rclone-kompatible Backups-Anmeldedaten für externe Speicher. |
| `resources.repositories.*` | Pro-Repo GUID + LUKS-Credential + SSH-Schlüssel für Sandbox-isolierten Agent-Zugriff. |
| `infra.acmeCertCache.*` | Gecachte Traefik-acme.json, gzip+base64, nach Domäne indiziert. |
| `encryption.mode` | `"plaintext"` (Standard) oder `"master-password"`. |
| `encryption.encryptedFields` | Wenn verschlüsselt, eine Per-Pointer-AES-GCM-Blob-Map (`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`). Eine Entsperraufforderung pro Sitzung entschlüsselt Felder bei Lesezugriff. |
| `remote` | Nur vorhanden, wenn die Konfiguration mit dem verschlüsselten Config-Store synchronisiert wird; siehe [Verschlüsselter Config-Store](/en/docs/config-storage). |

**Sicher mit der CLI bearbeiten, nicht mit `vim`:**

```bash
# Pointer-adressierte Einzelfeld-Bearbeitungen (Wissens-gated für sensible Pfade)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# Vollständiger Editor mit redaktierter JSONC-Projektion (nur Menschen)
rdc config edit

# Schreibgeschützter JSONC-Dump, sicher für Skripte und Agenten
rdc config edit --dump

# Inspizieren Sie jede Mutation, Verweigerung und Offenlegung im Audit-Log
rdc config audit log --since 24h
rdc config audit verify
```

> Diese Datei enthält sensible Daten (SSH-Privatschlüssel, LUKS-Credentials, Cloudflare-Token). Sie wird mit `0600`-Berechtigungen gespeichert (nur Eigentümer lesen/schreiben). Teilen Sie sie nicht und committen Sie sie nicht in die Versionsverwaltung. Wenn ein `rdc`-Befehl sie liest, werden sensible Felder standardmäßig [redaktiert](/en/docs/ai-agents-safety): Klartext erscheint nur mit `--reveal` auf einem interaktiven menschlichen TTY.

### Envelope v2 und serverseitige Durchsetzung

Wenn die Konfiguration mit dem [verschlüsselten Config-Store](/en/docs/config-storage) synchronisiert wird, wickelt die CLI jedes sensible Feld in eine Per-Feld-HMAC-Verpflichtung ein und trägt diese Verpflichtungen in der Klartext-Hülle. Der Server sieht nur Hex-Digests: Niemals die Werte: Kann aber Wissens-Gates auf jeden Schreibzugriff durchsetzen:

- **Vorbedingungsprüfung**: Bei `PUT /configs/<id>` sendet der Client die Digests, die er für die Pfade, die er mutieren möchte, kennt. Der Server vergleicht gegen die Verpflichtungen der gespeicherten Hülle. Nichtübereinstimmung -> `409 precondition_failed` mit `mismatchedPaths`. Zero-Knowledge: Der Server sieht niemals Klartext.
- **Anti-Downgrade**: Die neue Hülle muss jeden sensiblen Pfad committen, den die vorherige Hülle committed. Ein Agent kann einen Pfad nicht aus den Verpflichtungen streichen, um zukünftige Vorbedingungen zu umgehen.
- **Hüllen-Versionsfreigabe**: Der Server lehnt Hüllen ohne `envelopeVersion: 2` mit `400 unsupported_envelope_version` ab. Kein Dual-Accept-Fenster.
- **Pro-Feld-Verschlüsselung-im-Ruhezustand** (CLI-Seite): Wenn `encryption.mode === "master-password"`, wird jedes Geheimnis zu einem einzelnen AES-GCM-Blob mit Schlüssel vom Master-Passwort. Lesezugriffe triggern keine Aufforderung, es sei denn, der Befehl berührt tatsächlich ein Geheimnis (daher bleibt `rdc machine list` aufforderungsfrei).

Der Commitments-Schlüssel (FCK) wird clientseitig vom CEK über `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")` mit einem Pro-Config-Salt abgeleitet. Das Rotieren von `fckSalt` macht alle bisherigen Verpflichtungen ungültig, erzwingt eine Neuberechnung: nützlich beim Rotieren von CEK.
