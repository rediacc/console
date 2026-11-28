---
title: KI-Agent-Sicherheit & Schutzmaßnahmen
description: >-
  Wie Rediacc KI-Coding-Assistenten daran hindert, Geheimnisse preiszugeben,
  Anmeldedaten zu überschreiben oder Berechtigungen zu eskalieren. Eine
  Entscheidung für jede Oberfläche, Opt-in UND Richtlinien-Obergrenze,
  Wissens-Gates, Schwärzung und ein Audit-Log, das auf dem Server pro Organisation und Tag hash-verkettet ist, in der CLI in einer lokalen Datei.
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: de
sourceHash: "43350a2e682cebcc"
sourceCommit: "cc655e698ed2c42faef5311e268425c04997f243"
---

Sie setzen einen KI-Coding-Assistenten auf Ihre Infrastruktur an. Wenn Claude Code, Cursor, Gemini CLI, Copilot CLI oder etwas Ähnliches `rdc` steuert, erkennt die CLI das und wendet einen anderen Regelsatz an als bei einem Menschen an der Tastatur. Diese Seite erklärt, was der Agent tun kann, was er nicht tun kann, und wie die Schutzmaßnahmen auch dann greifen, wenn der Agent versucht, sie zu umgehen.

## Kurzreferenz: was Agents können und nicht können

| Operation | Agent-Standard | Freischaltung für einen bestimmten Anwendungsfall |
|---|---|---|
| `rdc config show` (geschwärzt) | ✅ allowed |  |
| `rdc config field get --pointer <pointer>` (geschwärzter Stub oder Digest) | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (öffentliches Feld) | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (sensibles Feld, **mit korrektem `--current`**) | ✅ allowed |  |
| `rdc config edit --dump --redacted` (geschwärztes JSONC) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (sensibles Feld, kein `--current`) | 🔴 refused | `--current "<alter Wert>"` angeben |
| `rdc repo secret set <repo> --rotate-secret` (Rotation ohne `--current`) | 🔴 refused | `--current` angeben, oder ein Mensch führt die Rotation an einem Terminal aus |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Stattdessen `--digest` verwenden |
| `rdc config show --reveal` | 🔴 refused | Einfaches `rdc config show` verwenden |
| `rdc config edit` (interaktiver Editor) | 🔴 refused, keine Überschreibung | Mit `--dump --redacted` ansehen, ein einzelnes Feld mit `config field set --current` ändern |
| `rdc config edit --apply <file>` | 🔴 refused, keine Überschreibung | Ebenso; ein Mensch am Terminal wendet Änderungen am gesamten Dokument an |
| `rdc config edit --reveal` | 🔴 refused, keine Überschreibung | Ebenso |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | Ein Mensch führt es an einem interaktiven Terminal aus |
| Ein Grand-Repository (Produktion) ändern | 🔴 refused | Opt-in eines Menschen für dieses Repository, innerhalb einer Richtlinie, die Grand-Repository-Änderungen erlaubt ([unten](#one-decision-opt-in-and-policy-ceiling)) |
| Cluster- oder Datastore-Lifecycle-Operationen | 🔴 refused | Opt-in eines Menschen für diesen Cluster, innerhalb einer Richtlinie, die Cluster-Operationen erlaubt |
| `rdc term connect <machine>` (direktes Maschinen-SSH) | 🔴 refused | Zuerst ein Repository forken und mit dem Fork verbinden |

Jede Verweigerung gegenüber einem Agent wird mit `outcome: refused` und einem Grund in das Audit-Log geschrieben. Für die Bearbeitung des gesamten Konfigurationsdokuments gibt es für Agents gar keinen Pfad: Die Konfiguration enthält die LUKS-Anmeldedaten jedes Repositories, und ein Agent, der sie umschreiben könnte, könnte auch Anmeldedaten löschen, ohne die sich das verschlüsselte Volume nicht mehr öffnen lässt.

## Wie Agents erkannt werden

Die CLI behandelt einen Prozess als Agent, wenn eine der folgenden Bedingungen zutrifft:

- Eines der Umgebungsvariablen `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` ist auf `"1"` gesetzt, oder `CURSOR_TRACE_ID` ist überhaupt gesetzt.
- Unter Linux: Ein übergeordneter Prozess in der Abstammungskette hat eine dieser Variablen in seiner Umgebung (über `/proc/<pid>/environ`). Selbst wenn der Agent seine eigenen Variablen mit `env -i` oder einem Wrapper-Skript entfernt, verrät die übergeordnete Kette der CLI, wer ihn gestartet hat.

Die Erkennung läuft einmal pro Prozess und wird gecacht. Sie kann nicht deaktiviert werden. Eine Freigabe für den entfernten MCP markiert ihre Aufrufe auf dem Executor als Agent-Aufrufe, ganz ohne Erkennung.

## Eine Entscheidung: Opt-in UND Richtlinien-Obergrenze

Jede Oberfläche, die einen `rdc`-Befehl ausführt (die CLI, der lokale MCP-Server, der entfernte MCP-Server, `rdc --proxy` und die Web-Konsole), fragt dieselbe Entscheidungsfunktion, deshalb verweigern und erlauben alle dasselbe. Sie wendet zwei Bedingungen an, und ein Agent handelt nur dort, wo beide erfüllt sind:

1. **Die Richtlinien-Obergrenze.** Die Organisationsrichtlinie, eingeengt durch die Teamrichtlinie, entscheidet, welche Befehle, Maschinen und Repositories ein Aufrufer nutzen darf und ob Änderungen an Grand-Repositories (`allowGrandRepos`) und Cluster-Operationen (`allowClusterOps`) überhaupt erlaubt sind. Eine Konfiguration ohne Richtlinieneintrag fällt auf einen Standard nach Rolle zurück: Owner und Admins dürfen handeln, Mitglieder nicht. Die Richtlinie ist ein eigener versiegelter Eintrag, den nur Owner und Admins schreiben ([Sicherheitsmodell](/de/docs/security-model#policy)); kein Agent und kein CLI-Befehl kann sie bearbeiten.
2. **Das Opt-in des Menschen.** Innerhalb der Obergrenze braucht ein Agent trotzdem einen Menschen, der das Grand-Repository oder den Cluster benennt, den er ändern darf:
   - **Lokale Agents** (CLI und lokaler MCP): Der Mensch exportiert `REDIACC_ALLOW_GRAND_REPO` (Repository-Namen oder `*`) oder `REDIACC_ALLOW_CLUSTER_OPS` (Cluster-Namen oder `*`) im Terminal, bevor er den Agent startet. Die CLI prüft die Prozessabstammung, daher zählt eine Variable nicht, die der Agent mitten in der Sitzung setzt ([so wird auf jedem Betriebssystem geprüft](#how-a-local-opt-in-is-verified-on-each-os)).
   - **Entfernte Agents** (entfernter MCP): Die Opt-ins sind Teil der Freigabe, die der Mensch in der Konto-Oberfläche anlegt ([Entfernter Server](/de/docs/ai-agents-mcp#remote-server)).

Ein Opt-in erweitert die Obergrenze nie: Ein Repository, das die Richtlinie schließt, bleibt geschlossen, egal was die Umgebung oder die Freigabe sagt. Forks brauchen kein Opt-in. Ein Repository, das die CLI nicht identifizieren kann, gilt als Grand.

**Destruktive Änderungen fragen zuerst nach.** Ist ein Agent für eine destruktive Änderung an einem Grand-Repository freigegeben (zum Beispiel `repo delete`), lautet die Antwort `needs_confirmation`. Ein MCP-Client zeigt dem Benutzer eine Bestätigungsabfrage; ein Client ohne eine solche erhält ein `confirm`-Argument, das er nach Rückfrage beim Benutzer zurücksendet. In der CLI führt der Mensch den Befehl erneut mit `--confirm-grand <repo>` aus.

Jede Antwort trägt einen stabilen Code (`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`), sodass ein Skript oder ein Agent auf den Code statt auf die Meldung verzweigt ([JSON-Ausgabe](/de/docs/ai-agents-json-output)).

## Das Wissens-Gate-Modell

Sensible Mutationen folgen der `passwd(1)`-Konvention: Um ein Geheimnis zu ändern, muss man beweisen, dass man es bereits kannte. **Symmetrisch für Menschen und Agents**. Beide durchlaufen dasselbe Gate. Es gibt keinen „Ich sitze an der Tastatur"-Bypass.

- Sie wollen ein API-Token, das unter `/credentials/cfDnsApiToken` gespeichert ist, rotieren?
- Die CLI fragt: „Was ist der aktuelle Wert?"
- Der Agent (oder Mensch) gibt den Klartext über `--current "$OLD"` an. Die CLI hasht `$OLD` mit SHA-256 und vergleicht ihn mit dem Digest des aktuell gespeicherten Werts. Übereinstimmung → Schreibvorgang wird durchgeführt. Abweichung → verweigert, protokolliert.
- Um ohne Verifizierung des vorherigen Werts zu rotieren, übergeben Sie `--rotate-secret` (schließt sich mit `--current` gegenseitig aus). Dies wird explizit als Rotation protokolliert und zählt nur für einen Menschen an einem interaktiven Terminal: Ein Agent oder ein Skript ohne Terminal an stdin braucht weiterhin `--current`.

Das Modell schließt drei Angriffsflächen:

1. **Stille Rotation**: Ein Agent ohne vorherigen Zugriff auf `$OLD` kann ihn nicht durch einen eigenen Wert ersetzen.
2. **Exfiltration durch Sondierung**: Die Digest-Antwort enthält niemals Klartext; selbst ein kompromittiertes Audit-Log zeigt `expected abc12345…, got deadbeef…`, nicht die zugrunde liegenden Werte.
3. **Versehentliches Überschreiben der Produktionskonfiguration**: erfordert bei jedem Mal ein explizites `--current`, sogar an einem TTY. Deckt den Fehler „Ich wollte STRIPE_TEST setzen, bin aber in der Prod-Shell" auf.

### Strukturierte Next-Action-Hinweise

Wenn die Vorbedingung nicht erfüllt wird, enthält der JSON-Envelope (`--output json`) ein strukturiertes `errors[].next`-Feld, das Agents genau mitteilt, was sie dem Menschen vorschlagen sollen:

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Agents sollten `next.options[].run` wortwörtlich an den Menschen weitergeben, statt eigene Befehle zu erfinden.** Das vermeidet den Fehlerfall „Agent erfindet einen Befehl, der nicht existiert“ und hält den Operator bei der eigentlichen Aktion in Kontrolle. Die Rotationsoption soll der Mensch an einem Terminal ausführen; dem Agent selbst wird sie verweigert.

### Konkretes Beispiel

```bash
# Den kurzen Digest des Schwärzungs-Stubs abrufen (sicher für Agents).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Ohne Nachweis überschreiben versuchen: verweigert.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# Den aktuellen Klartext angeben: erlaubt.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Hatte der Agent `$OLD_CF_TOKEN` nie, kann er die Vorbedingung nicht erfüllen, und die Rotation wird verweigert. Wer den Wert kennt, kann sie trotzdem durchführen: mit `--current` aus der eigenen Shell oder mit `rdc config field rotate` an einem interaktiven Terminal.

## Schwärzung als Standard

Jeder `rdc`-Befehl, der sensiblen Zustand liest: `config show`, `config field get`, `config machine list`, `config edit --dump --redacted`: gibt **Schwärzungs-Stubs** für Geheimnisfelder zurück, nicht Klartext:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Das 8-stellige Hex-Suffix des Stubs sind die ersten 8 Zeichen von `sha256(canonicalize(value))`: genug, um zwei verschiedene Werte auf einen Blick zu unterscheiden, aber nicht genug zum Umkehren. Ein Agent kann einen Stub verwenden, um zu verfolgen, ob sich ein Wert geändert hat, ohne ihn jemals zu sehen.

`--reveal` hebt die Schwärzung für Menschen auf einem interaktiven TTY auf. Agents werden unabhängig vom TTY-Status verweigert. Jede Gewährung schreibt einen `reveal_granted`-Audit-Eintrag; jede Verweigerung schreibt einen `refused`-Eintrag mit den Agent-Signalen des Akteurs.

## So wird ein lokales Opt-in auf jedem Betriebssystem verifiziert

`REDIACC_ALLOW_GRAND_REPO` und `REDIACC_ALLOW_CLUSTER_OPS` verlassen sich beide auf die Abstammungsverifizierung, um zu beweisen, dass das Opt-in vom Menschen gesetzt und nicht vom Agent injiziert wurde. Die Verifizierung funktioniert auf Linux, macOS und Windows, aber der Zeuge, den sie ausliest, unterscheidet sich pro Plattform, und ebenso die Stärke der Garantie:

| Plattform | Zeuge | Stärke |
|---|---|---|
| Linux | `/proc/<pid>/environ` für jeden Prozess in der Kette | Exec-Zeit-Snapshot, vom Kernel bereitgestellt. Ein Prozess kann nicht nachträglich bearbeiten, womit er gestartet wurde. |
| macOS | `kern.procargs2` sysctl, gelesen von einem kleinen Helper, der in `rdc` enthalten ist | Gleiche Exec-Zeit-Snapshot-Eigenschaft wie Linux. Lesbar für Ihre eigenen Prozesse ohne Root. |
| Windows | Der Live-Umgebungsblock jedes Ancestor-Prozesses (PEB), gelesen vom gleichen Helper mit PID-Reuse-Schutz | Schwächer: Windows führt keinen Exec-Zeit-Snapshot durch, daher liest der Check den aktuellen Memory. Ancestors können immer noch nicht von etwas, das ein Agent normalerweise ausführt, umgeschrieben werden, aber der Zeuge ist nicht kernel-gefroren wie auf Linux und macOS. |

Auf macOS und Windows startet die CLI ihre gebündelte `renet`-Binary, um das Lesen durchzuführen; der Helper meldet, welche der überwachten Variablen jeder Ancestor trägt, und die gesamte Entscheidungslogik verbleibt in der CLI. Wenn der Helper fehlt, veraltet ist oder aus irgendeinem Grund fehlschlägt, kann die CLI das Opt-in nicht verifizieren und **schlägt sicher fehl**: Das Opt-in wird abgelehnt, und der Fehler sagt, dass die Verifizierung nicht verfügbar war, nicht dass etwas falsch gemacht wurde. Eine funktionierende Installation zeigt diese Meldung nie; die Neuinstallation von `rdc` stellt den Helper wieder her.

Was auf jeder Plattform wahr bleibt: Das Opt-in muss bereits in der Umgebung des Agent-Prozesses vorhanden sein, wenn er startet. Es wird im Terminal exportiert, danach startet der Agent. Ein Agent, der die Variable mitten in einer Sitzung setzt, wird abgelehnt.

## Audit-Log

Jede Mutation, jede Verweigerung, jede `--reveal`-Gewährung schreibt eine JSONL-Zeile in `~/.config/rediacc/audit.log.jsonl` (Modus `0600`, rotiert bei 10 MB). Jede Zeile ist hash-verkettet: Ihr `prevHash`-Feld ist `sha256("<vorherige Zeile>")`. Das Manipulieren einer Zeile bricht die Kette in allen nachfolgenden Zeilen.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### Inspektion

```bash
# Letzte Einträge auflisten
rdc config audit log --since 24h

# Nach Pointer-Glob filtern
rdc config audit log --path '/credentials/*'

# Nur agent-initiierte Einträge
rdc config audit log --actor agent

# Neue Einträge live streamen (Strg+C zum Stoppen)
rdc config audit tail

# Prüfen, ob die Hash-Kette intakt ist
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   ODER
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### Was nie im Audit-Log erscheint

- Klartextgeheimnisse
- Passphrases, Tokens, SSH-Schlüssel
- Die alten/neuen Werte bei einem `--current`-Vorbedingungsfehler (nur das 8-stellige Digest-Präfix)

Das Log ist sicher für Sicherheitsprüfer oder als Anhang an einen Fehlerbericht.

## Grenzen des Verhaltensmodells

Die Agent-Schutzmaßnahmen sind **verhaltensbasiert, nicht kryptografisch**. Ein entschlossener oder gesteuerter Agent, der unter derselben UID wie die Konfigurationsdatei läuft, kann immer `cat ~/.config/rediacc/rediacc.json` ausführen und den Klartext lesen, da die Datei vom Prozess lesbar ist.

Für echte kryptografische Durchsetzung verwenden Sie den [verschlüsselten Config-Speicher](/de/docs/config-storage): Geheimnisse liegen serverseitig, jedes sensible Feld trägt eine feldspezifische HMAC-Bindung, und der Account-Worker verweigert Schreibvorgänge, deren `--current`-Vorbedingung nicht mit dem gespeicherten Hash übereinstimmt. Der Server sieht niemals den Klartext (Zero-Knowledge), erzwingt aber das Gate.

Der lokale Dateipfad: einfacher Weg ist sicher. Der Remote-Store-Pfad: der Umgehungsweg ist kryptografisch ebenfalls schwierig.

## Was Rediacc nicht isoliert

Die Agent-Schutzmaßnahmen auf dieser Seite schützen Rediaccs eigene Infrastruktur: die Konfigurationsdatei, den Pro-Repository-Docker-Daemon, die LUKS-verschlüsselten Repository-Daten, die abgegrenzte SSH-Sandbox. Sie schützen keine externen Dienste, für die Ihr Repository Anmeldedaten enthält.

Ein Repository-Fork ist ein BTRFS-Reflink des Volumes des übergeordneten Repositories. Was auch immer auf der Festplatte des übergeordneten Repositories liegt, ist im Fork byteidentisch: Code, Daten und `.env`-Dateien gleichermaßen. Wenn Ihr Repository einen `STRIPE_LIVE_KEY`, eine `AWS_ACCESS_KEY_ID`, ein Railway-API-Token oder eine andere langlebige Anmeldedaten für einen Drittanbieter-Dienst enthält, erbt der Fork sie. Ein Agent, der in der Sandbox des Forks arbeitet, kann diese Datei lesen, den Wert exfiltrieren oder ihn verwenden, um die Drittanbieter-API aufzurufen. Der Drittanbieter-Dienst hat keine Möglichkeit zu wissen, dass der Aufruf von einem Fork und nicht von der Produktion kam.

Dies ist die Linie der gemeinsamen Verantwortung:

| Grenze | Eigentümer |
|---|---|
| Repository-Daten, Mount-Namespace, Docker-Geltungsbereich, Agent-Schutzmaßnahmen, Audit-Log, Deploy-Zeit-Geheimnisinjektion | Rediacc |
| Anwendungscode, der diese Geheimnisse verwendet, und alle ins Image eingebackenen Anmeldedaten | Repository-Entwickler |

Die primäre Gegenmaßnahme ist bereits eingebaut: **[Repository-Geheimnisse](/de/docs/repositories#secrets)** werden in einer separaten Ebene vom verschlüsselten Repository-Image gespeichert und nicht über die Fork-Grenze hinweg kopiert. Die Container eines Forks starten mit einer leeren Secrets-Map und identifizieren sich gegenüber externen Diensten als ein anderes Subjekt als das übergeordnete Repository. Setzen Sie sie mit `rdc repo secret set` (env-Modus für Compose-Interpolation, file-Modus für tmpfs-`secrets:`-Blöcke). Das Mutations-Gate ist symmetrisch. Menschen und Agents müssen gleichermaßen `--current` (passwd-ähnliche Vorbedingung) angeben, um einen bestehenden Wert zu überschreiben oder zu löschen; `--rotate-secret` (protokollierte Rotation) ist die Alternative für einen Menschen am Terminal.

**Cross-Repository-Isolation ist durchgesetzt.** Eine böswillige oder fehlerhafte Compose-Datei in Repository B kann nicht auf das Secrets-Verzeichnis von Repository A verweisen. Renets Compose-Validator lehnt jeden `secrets: file:`, `configs: file:` oder `env_file:`-Pfad hart ab, der außerhalb des `${REDIACC_NETWORK_ID}`-Verzeichnisses des aktuellen Repositories liegt, und diese Ablehnung ist durch `--unsafe` NICHT überschreibbar. Defense-in-Depth: Die Landlock-Sandbox um den Rediaccfile-Bash-Subprozess begrenzt Dateisystem-Lesevorgänge ausschließlich auf das Secrets-Verzeichnis des aktuellen Netzwerks, sodass ein `cat /var/run/rediacc/net-<other>/secrets/X` aus einer böswilligen Rediaccfile auf Kernel-Ebene mit EACCES fehlschlägt. Dasselbe gilt für die Docker-API: Der Docker-Socket jedes Repositories wird von einem renet-Policy-Proxy bedient, der `--privileged`, Host-`pid`, -`ipc` und -`uts`, Geräteanfragen sowie Binds, die die Laufzeit oder Daten eines anderen Repositories erreichen, mit `403` abweist. Ein Container mit `${DOCKER_SOCKET}` kann die API also nicht nutzen, um ein anderes Repository zu erreichen, und nicht nur eine Compose-Datei wird geprüft. Nur der Operator kann die Bind-Regel für benannte Host-Verzeichnisse erweitern, und zwar mit einer Freigabe, die root gehört und in die kein Container schreiben kann.

Zwei weitere Muster schließen Randfälle:

1. **Keine Produktions-Anmeldedaten direkt im Repository-Dateisystem ablegen.** Eine ins Image eingecheckte `.env`-Datei oder Anmeldedaten, die während `up()` in ein Volume geschrieben wurden, werden in den Fork reflinkt. Das Per-Repository-Secrets-Feature schützt nur Werte, die in der Secrets-Ebene liegen. Es kann keine Bytes, die bereits im LUKS-Image existieren, nachträglich schützen. Bei bestehenden Repositories mit eingecheckten `.env`-Dateien müssen diese manuell in Repository-Geheimnisse überführt werden.
2. **Das ausgehende Netzwerk des Forks mit eBPF-Egress-Filterung einschränken**, sodass der Fork nur Localhost und explizite Sandbox-Endpunkte erreichen kann. Rediaccs Pro-Repository-Netzwerkisolation ist die Grundlage; Egress-Allowlists pro Fork sind heute noch nicht eingebaut, aber der Weg ist offen.

Rediacc übernimmt die Deploy-Zeit-Injektion, die Cross-Fork-Isolation und die Cross-Repository-Isolation. Die Hälfte „Nichts ins Image einbacken" liegt bei Ihnen.

## Schnellrezepte

### Einem Agent erlauben, an einem Grand-Repository zu arbeiten

```bash
# Als Mensch, vor dem Start des Agents:
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # oder cursor, gemini, usw.
```

Der Agent kann nun `gitlab` ändern, sofern die Richtlinie Änderungen an Grand-Repositories erlaubt, und kein anderes Grand-Repository. Eine destruktive Änderung wie `repo delete gitlab` fragt weiterhin nach einer Bestätigung.

### Ein Cloud-Token rotieren, ohne den alten Wert zu kennen

```bash
# Als Mensch, an einem interaktiven Terminal:
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

Die Rotation ohne `--current` bleibt beim Menschen. Ein Agent, der den aktuellen Wert kennt, verwendet stattdessen `rdc config field set --current`.

### Herausfinden, welche Felder ein Agent bearbeiten darf

```bash
rdc config field list --sensitive --output json
```

Gibt jede Pointer-Vorlage, ihre Art (`secret` / `credential` / `pii` / `identifier`) und ob sie im serverseitigen HMAC-Envelope gespeichert ist zurück.

## Siehe auch

- [KI-Agent-Integrationsübersicht](/de/docs/ai-agents-overview): die übergreifende Einführung
- [MCP-Server](/de/docs/ai-agents-mcp): lokaler und entfernter MCP, Freigaben und ihre Opt-ins
- [Sicherheitsmodell](/de/docs/security-model): der Richtlinieneintrag und wer ihn schreiben darf
- [Claude Code Einrichtung](/de/docs/ai-agents-claude-code): Integrationsvorlage
- [JSON-Ausgabe-Envelope](/de/docs/ai-agents-json-output): maschinenlesbare Antworten
- [Verschlüsselter Config-Speicher](/de/docs/config-storage): serverseitige kryptografische Durchsetzung
- [Kontosicherheit](/de/docs/account-security): sicherheitsbezogene Betreibereinstellungen
