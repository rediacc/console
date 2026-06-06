---
title: KI-Agent-Sicherheit & Schutzmaßnahmen
description: >-
  Wie Rediaccs CLI KI-Coding-Assistenten daran hindert, Geheimnisse preiszugeben,
  Anmeldedaten zu überschreiben oder Berechtigungen zu eskalieren. Wissens-Gates,
  Schwärzung, abstammungsverifizierte Überschreibungen und ein hash-verkettetes Audit-Log.
category: Concepts
order: 35
language: de
sourceHash: "ae23c9bc851ecfcd"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
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
| `rdc config edit --dump` (geschwärztes JSONC) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (sensibles Feld, kein `--current`) | 🔴 refused | `--current "<alter Wert>"` angeben |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Stattdessen `--digest` verwenden |
| `rdc config show --reveal` | 🔴 refused | Einfaches `rdc config show` verwenden |
| `rdc config edit` (interaktiver Editor) | 🔴 refused | Mensch setzt `REDIACC_ALLOW_CONFIG_EDIT=*` vor dem Start des Agents |
| `rdc config edit --apply <file>` | 🔴 refused | Gleiche Überschreibung |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | Gleiche Überschreibung; nutzt interaktive Bestätigung |
| `rdc term connect -m <machine>` (direktes Maschinen-SSH) | 🔴 refused | Zuerst ein Repository forken und mit dem Fork verbinden |

Jede Verweigerung gegenüber einem Agent wird mit `outcome: refused` und einem Grund in das Audit-Log geschrieben.

## Wie Agents erkannt werden

Die CLI behandelt einen Prozess als Agent, wenn eine der folgenden Bedingungen zutrifft:

- Eines der Umgebungsvariablen `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` ist auf `"1"` gesetzt, oder `CURSOR_TRACE_ID` ist überhaupt gesetzt.
- Unter Linux: Ein übergeordneter Prozess in der Abstammungskette hat eine dieser Variablen in seiner Umgebung (über `/proc/<pid>/environ`). Selbst wenn der Agent seine eigenen Variablen mit `env -i` oder einem Wrapper-Skript entfernt, verrät die übergeordnete Kette der CLI, wer ihn gestartet hat.

Die Erkennung läuft einmal pro Prozess und wird gecacht. Sie kann nicht deaktiviert werden.

## Das Wissens-Gate-Modell

Sensible Mutationen folgen der `passwd(1)`-Konvention: Um ein Geheimnis zu ändern, muss man beweisen, dass man es bereits kannte. **Symmetrisch für Menschen und Agents**. Beide durchlaufen dasselbe Gate. Es gibt keinen „Ich sitze an der Tastatur"-Bypass.

- Sie wollen ein API-Token, das unter `/credentials/cfDnsApiToken` gespeichert ist, rotieren?
- Die CLI fragt: „Was ist der aktuelle Wert?"
- Der Agent (oder Mensch) gibt den Klartext über `--current "$OLD"` an. Die CLI hasht `$OLD` mit SHA-256 und vergleicht ihn mit dem Digest des aktuell gespeicherten Werts. Übereinstimmung → Schreibvorgang wird durchgeführt. Abweichung → verweigert, protokolliert.
- Um ohne Verifizierung des vorherigen Werts zu rotieren, übergeben Sie `--rotate-secret` (schließt sich mit `--current` gegenseitig aus). Dies wird explizit als Rotation protokolliert.

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
          "run": "rdc repo secret get --name mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Agents sollten `next.options[].run` wortgenau an den Menschen weitergeben, anstatt eigene Befehle zu erfinden.** Das vermeidet das Fehlermuster, bei dem ein Agent einen nicht existierenden Befehl erfindet, und hält den Operator über die tatsächliche Aktion in der Kontrolle.

### Konkretes Beispiel

```bash
# Den kurzen Digest des Schwärzungs-Stubs abrufen (sicher für Agents).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Ohne Nachweis überschreiben versuchen: verweigert.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Den aktuellen Klartext angeben: erlaubt.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Wenn der Agent `$OLD_CF_TOKEN` nie hatte, kann er die Vorbedingung nicht erfüllen und die Rotation wird verweigert. Der Benutzer, der ihn *hat*, kann sie dennoch über den Editor oder durch Übergabe von `--current` aus seiner Shell durchführen.

## Schwärzung als Standard

Jeder `rdc`-Befehl, der sensiblen Zustand liest: `config show`, `config field get`, `config machine list`, `config edit --dump`: gibt **Schwärzungs-Stubs** für Geheimnisfelder zurück, nicht Klartext:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Das 8-stellige Hex-Suffix des Stubs sind die ersten 8 Zeichen von `sha256(canonicalize(value))`: genug, um zwei verschiedene Werte auf einen Blick zu unterscheiden, aber nicht genug zum Umkehren. Ein Agent kann einen Stub verwenden, um zu verfolgen, ob sich ein Wert geändert hat, ohne ihn jemals zu sehen.

`--reveal` hebt die Schwärzung für Menschen auf einem interaktiven TTY auf. Agents werden unabhängig vom TTY-Status verweigert. Jede Gewährung schreibt einen `reveal_granted`-Audit-Eintrag; jede Verweigerung schreibt einen `refused`-Eintrag mit den Agent-Signalen des Akteurs.

## Die Überschreibung `REDIACC_ALLOW_CONFIG_EDIT`

Einige Operationen: der interaktive Editor, `--apply`, `field rotate`: sind für Menschen gedacht und haben keinen agentensicheren Pfad. Wenn Sie explizit möchten, dass ein Agent eine davon ausführt, setzen Sie:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # vollständige Umgehung
# oder
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (kommagetrennte Bereichs-Globs: * Wildcards pro Segment erlaubt)
```

…und der Agent erbt es.

**Wichtiges Detail**: Die Überschreibung muss in einem Prozess **oberhalb** des Agents in der Abstammungskette erscheinen. Wenn der Agent sie in seiner eigenen Umgebung setzt (oder in einer Subshell, die er gestartet hat), verweigert die CLI und teilt Ihnen dies mit:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

Der Effekt: Ein Agent kann eine Schutzmaßnahme nicht umgehen, indem er mitten in einer Sitzung `export REDIACC_ALLOW_CONFIG_EDIT='*'` ausführt. Nur ein übergeordneter Prozess (Sie, in Ihrem Terminal, vor dem Start des Agents) kann diese Tür öffnen.

## Plattformunterstützung: Linux-only für die Überschreibungen

`REDIACC_ALLOW_CONFIG_EDIT` und `REDIACC_ALLOW_GRAND_REPO` stützen sich beide auf die Abstammungsverifizierung, um zu beweisen, dass die Überschreibung von Ihnen gesetzt wurde und nicht vom Agent injiziert wurde. Die Verifizierung liest `/proc/<pid>/environ` für jeden Prozess in der Kette. Diese Datei wird vom Kernel zur Exec-Zeit gesetzt und kann vom Prozess selbst nicht modifiziert werden, sodass die Umgebung der übergeordneten Shell ein manipulationssicherer Zeuge ist.

Diese Datei existiert auf macOS oder Windows nicht. Ohne Möglichkeit, die Legitimität zu verifizieren, schlägt die CLI sicher fehl. Selbst wenn Sie die Überschreibung in Ihrer Shell vor dem Start des Agents korrekt setzen, wird die Überschreibung abgelehnt. Die Fehlermeldung sagt Ihnen genau, was zu tun ist:

> The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. … To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).

Nicht-Linux-Benutzer haben keinen Notausstieg aus dem Fork-First-Workflow. Das ist beabsichtigt. Es gibt keine Möglichkeit für einen Agent, die Sandbox zu umgehen, unabhängig davon, wie er aufgefordert wurde. Führen Sie Ihren Agent in WSL, einem Linux-Container oder einer Linux-VM aus, wenn Sie die Überschreibung benötigen; andernfalls arbeiten Sie auf einem Fork.

## Audit-Log

Jede Mutation, jede Verweigerung, jede `--reveal`-Gewährung schreibt eine JSONL-Zeile in `~/.config/rediacc/audit.log.jsonl` (Modus `0600`, rotiert bei 10 MB). Jede Zeile ist hash-verkettet: Ihr `prevHash`-Feld ist `sha256("<vorherige Zeile>")`. Das Manipulieren einer Zeile bricht die Kette in allen nachfolgenden Zeilen.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
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

Die primäre Gegenmaßnahme ist bereits eingebaut: **[Repository-Geheimnisse](/de/docs/repositories#secrets)** werden in einer separaten Ebene vom verschlüsselten Repository-Image gespeichert und nicht über die Fork-Grenze hinweg kopiert. Die Container eines Forks starten mit einer leeren Secrets-Map und identifizieren sich gegenüber externen Diensten als ein anderes Subjekt als das übergeordnete Repository. Setzen Sie sie mit `rdc repo secret set` (env-Modus für Compose-Interpolation, file-Modus für tmpfs-`secrets:`-Blöcke). Das Mutations-Gate ist symmetrisch. Menschen und Agents müssen gleichermaßen `--current` (passwd-ähnliche Vorbedingung) oder `--rotate-secret` (protokollierte Rotation) angeben, um einen bestehenden Wert zu überschreiben oder zu löschen.

**Cross-Repository-Isolation ist durchgesetzt.** Eine böswillige oder fehlerhafte Compose-Datei in Repository B kann nicht auf das Secrets-Verzeichnis von Repository A verweisen. Renets Compose-Validator lehnt jeden `secrets: file:`, `configs: file:` oder `env_file:`-Pfad hart ab, der außerhalb des `${REDIACC_NETWORK_ID}`-Verzeichnisses des aktuellen Repositories liegt, und diese Ablehnung ist durch `--unsafe` NICHT überschreibbar. Defense-in-Depth: Die Landlock-Sandbox um den Rediaccfile-Bash-Subprozess begrenzt Dateisystem-Lesevorgänge ausschließlich auf das Secrets-Verzeichnis des aktuellen Netzwerks, sodass ein `cat /var/run/rediacc/secrets/<other>/X` aus einer böswilligen Rediaccfile auf Kernel-Ebene mit EACCES fehlschlägt.

Zwei weitere Muster schließen Randfälle:

1. **Keine Produktions-Anmeldedaten direkt im Repository-Dateisystem ablegen.** Eine ins Image eingecheckte `.env`-Datei oder Anmeldedaten, die während `up()` in ein Volume geschrieben wurden, werden in den Fork reflinkt. Das Per-Repository-Secrets-Feature schützt nur Werte, die in der Secrets-Ebene liegen. Es kann keine Bytes, die bereits im LUKS-Image existieren, nachträglich schützen. Bei bestehenden Repositories mit eingecheckten `.env`-Dateien müssen diese manuell in Repository-Geheimnisse überführt werden.
2. **Das ausgehende Netzwerk des Forks mit eBPF-Egress-Filterung einschränken**, sodass der Fork nur Localhost und explizite Sandbox-Endpunkte erreichen kann. Rediaccs Pro-Repository-Netzwerkisolation ist die Grundlage; Egress-Allowlists pro Fork sind heute noch nicht eingebaut, aber der Weg ist offen.

Rediacc übernimmt die Deploy-Zeit-Injektion, die Cross-Fork-Isolation und die Cross-Repository-Isolation. Die Hälfte „Nichts ins Image einbacken" liegt bei Ihnen.

## Schnellrezepte

### Einem Agent erlauben, ein einzelnes Cloud-Token zu rotieren

```bash
# Als Sie, vor dem Start des Agents:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # oder cursor, gemini, usw.
```

Jetzt kann der Agent `config field rotate /credentials/cfDnsApiToken --new …` ausführen, aber `/credentials/ssh/privateKey` immer noch nicht bearbeiten oder den interaktiven Editor öffnen.

### Einem Agent eine umfassende Konfigurationsbearbeitungssitzung ermöglichen

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

Der Agent kann `rdc config edit` öffnen, `--reveal` verwenden und `field rotate` ausführen. Jede Aktion wird weiterhin im Audit-Log mit `actor.kind: agent` und dem `CLAUDECODE`-Signal protokolliert.

### Herausfinden, welche Felder ein Agent bearbeiten darf

```bash
rdc config field list --sensitive --output json
```

Gibt jede Pointer-Vorlage, ihre Art (`secret` / `credential` / `pii` / `identifier`) und ob sie im serverseitigen HMAC-Envelope gespeichert ist zurück.

## Siehe auch

- [KI-Agent-Integrationsübersicht](/de/docs/ai-agents-overview): die übergreifende Einführung
- [Claude Code Einrichtung](/de/docs/ai-agents-claude-code): Integrationsvorlage
- [JSON-Ausgabe-Envelope](/de/docs/ai-agents-json-output): maschinenlesbare Antworten
- [Verschlüsselter Config-Speicher](/de/docs/config-storage): serverseitige kryptografische Durchsetzung
- [Kontosicherheit](/de/docs/account-security): sicherheitsbezogene Betreibereinstellungen
