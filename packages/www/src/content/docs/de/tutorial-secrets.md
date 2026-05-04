---
title: "Geheimnisse verwalten"
description: "Pro-Repo-Geheimnisse setzen, in compose einbinden, im Container verifizieren, rotieren und bestätigen, dass Forks nichts erben."
category: "Tutorials"
order: 7
language: de
sourceHash: "fb8bc967ed22fc10"
---

# Pro-Repo-Geheimnisse mit Rediacc verwalten

Echte Anwendungen brauchen Anmeldedaten: einen Stripe-Live-Key, ein Datenbankpasswort, ein API-Token. Der falsche Ort dafür ist im Repository selbst. Ein Fork erbt alles, was im verschlüsselten Image lebt, und seine Container identifizieren sich gegenüber externen Diensten als der Parent. Der richtige Ort ist `rdc repo secret`. Werte landen außerhalb des verschlüsselten Images, also starten Forks mit einer leeren Geheimnis-Map.

In diesem Tutorial setzen Sie beide Modi, binden sie in eine compose-Datei ein, prüfen, dass sie den Container erreichen, rotieren einen davon und bestätigen, dass ein Fork nichts erbt.

## Voraussetzungen

- Die `rdc`-CLI installiert mit initialisierter Konfiguration
- Eine bereitgestellte Maschine und ein erstelltes Repository (siehe [Tutorial: Repository-Lebenszyklus](/de/docs/tutorial-repos))
- Ein `Rediaccfile` und `docker-compose.yml`, die Sie bearbeiten können

## Schritt 1: Ein Geheimnis setzen

Es gibt zwei Liefermodi. `env` exportiert den Wert als `REDIACC_SECRET_<KEY>` für die `${...}`-Interpolation in compose. `file` schreibt den Wert in eine host-seitige tmpfs-Datei unter `/var/run/rediacc/secrets/<networkID>/<KEY>` zur Verwendung mit dem `secrets:`-Block von Docker compose. Verwenden Sie `file` für alles Sensible. Werte im env-Modus erscheinen in `docker inspect` und in `/proc/<pid>/environ`.

Beim ersten Schreiben eines neuen Schlüssels übergeben Sie `--current ""` (leer), um zu bestätigen, dass es keinen vorherigen Wert gibt.

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## Schritt 2: Auflisten

```bash
rdc repo secret list --name my-app
```

Die Ausgabe ist JSON mit Name und Modus jedes Geheimnisses. Werte tauchen niemals in der Auflistung auf. Sie werden nicht einmal von der Festplatte gelesen.

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## Schritt 3: In compose einbinden

Beide Modi werden aus derselben `docker-compose.yml` referenziert:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

Das kleingeschriebene `stripe_key` am Service ist der `/run/secrets/<name>`-Dateiname im Container. Das großgeschriebene `STRIPE_KEY` im Host-Pfad entspricht dem `--key`, das Sie gesetzt haben. `${REDIACC_NETWORK_ID}` wird automatisch von `renet compose` interpoliert. Das ist wichtig, weil die Netzwerk-ID pro Fork ist, sodass dieselbe compose-Datei im Parent und in jedem Fork funktioniert (wo, wie Sie in Schritt 6 sehen, die Datei einfach nicht existiert).

> **Repo-übergreifende Isolation erzwungen.** Der compose-Validator von renet lehnt jeden `secrets: file:`-Pfad (oder `configs: file:` oder `env_file:`) ab, der auf die Netzwerk-ID eines anderen Repos zielt. Das wörtliche `${REDIACC_NETWORK_ID}`-Token (oder Ihre eigene Netzwerk-ID als Zahl) ist die einzige akzeptierte Form, und `--unsafe` überschreibt dies NICHT. Die Landlock-Sandbox um den Rediaccfile-bash-Subprozess scopt Dateisystem-Lesezugriffe auf das Geheimnis-Verzeichnis Ihres eigenen Netzwerks. Selbst ein böswilliges `cat /var/run/rediacc/secrets/<andere>/X` aus einem Rediaccfile schlägt mit EACCES auf der Kernel-Schicht fehl. Sie müssen nichts aktivieren; der Schutz ist standardmäßig aktiv.

## Schritt 4: Bereitstellen und verifizieren

```bash
rdc repo up --name my-app -m server-1
```

Nach dem Deploy ins Container exec'en, um zu bestätigen, dass beide Modi gelandet sind:

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# sk_test_xxx
```

Wenn Sie die host-seitige tmpfs-Datei direkt inspizieren möchten:

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## Schritt 5: Rotieren ohne den vorherigen Wert zu kennen

Sie können einen Digest mit `rdc repo secret get` lesen, aber niemals den Klartext-Wert. Das ist das Write-Only-Modell. Wenn Sie verifizieren wollen, dass ein gespeicherter Wert mit dem übereinstimmt, was Sie haben, übergeben Sie ihn über `--current` und beobachten Sie die Vorbedingung bestehen oder scheitern:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

Wenn Sie den vorherigen Wert komplett vergessen haben (Ihr Passwortmanager hat ihn verloren oder Sie haben das Repo geerbt), verwenden Sie `--rotate-secret`, um die Vorbedingung zu überspringen. Das Audit-Log markiert dies deutlich als Rotation:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` und `--rotate-secret` schließen sich gegenseitig aus. Wählen Sie eines.

## Schritt 6: Bestätigen, dass Forks nichts erben

Der ganze Punkt: forken Sie das Repo und prüfen Sie die Geheimnisse-Liste des Forks:

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

Leer. Die Container des Forks können `${REDIACC_SECRET_DB_HOST}` nicht interpolieren (die Variable ist nicht gesetzt, also leerer String), und die Datei unter `/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY` existiert einfach nicht. Wenn das `repo up` des Forks versucht, sie über den compose-`secrets:`-Block einzubinden, schlägt der Deploy mit einem klaren Fehler fehl. Genau der Fehlermodus, den Sie wollen, denn er bedeutet, dass die Sandbox sich gegenüber externen Diensten nicht als Produktion ausgeben kann.

Um Geheimnisse im Fork zu verwenden, setzen Sie sie explizit auf dem Fork mit sandbox-bezogenen Werten:

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Jetzt spricht der Fork mit einer Test-Datenbank und einem Stripe-Sandbox-Konto. Die Produktions-Anmeldedaten des Parents verlassen den Parent niemals.

## Aufräumen

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## Siehe auch

- [Repositories § Geheimnisse](/de/docs/repositories#secrets). Die vollständige Referenz
- [RDC CLI Spickzettel § Pro-Repo-Geheimnisse](/de/docs/rdc-cheat-sheet#per-repo-secrets). Befehls-Schnellreferenz
- [KI-Agenten-Sicherheit](/de/docs/ai-agents-safety). Das symmetrische Mutation-Gate und strukturierte `next`-Aktion-Hinweise in Fehlerumschlägen
- [Dienste § Pro-Repo-Geheimnisse in compose verwenden](/de/docs/services#using-per-repo-secrets-in-compose). Compose-Muster-Referenz
