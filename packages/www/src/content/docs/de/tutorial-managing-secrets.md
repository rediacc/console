---
title: "Secrets verwalten"
description: "Hinterlegen Sie Deploy-Zeit-Zugangsdaten an einem Ort, den Forks nicht erreichen können. Schreibgeschützt von Grund auf."
category: "Tutorials"
subcategory: advanced
order: 8
language: de
sourceHash: "0b4d72c80b489e12"
---

# Secrets verwalten

Echte Apps benötigen echte Zugangsdaten: einen Stripe-Live-Schlüssel, ein Datenbankpasswort, ein API-Token. Der falsche Ort dafür ist im Repo, denn ein Fork erbt alles, was sich im verschlüsselten Image befindet. Plötzlich belasten Ihre Sandbox echte Kundenkarten.

Der richtige Ort ist `rdc repo secret`. Zwei Übergabemodi, schreibgeschützt von Grund auf, und der Fork startet mit nichts.

## Tutorial ansehen

![Tutorial: Secrets verwalten](/assets/tutorials/tutorial-managing-secrets.cast)

## Die Falle: `.env` im Repo

![Eine .env-Datei im Repo-Image wird von jedem Fork geklont](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

Die meisten Teams legen `.env` ins Repo. Das liegt auf der Hand.

Dann forken sie.

Der Fork ist eine Byte-für-Byte-Kopie des Parent-Images. Was in `.env` steht, steht auch in der `.env` des Forks. Die Container des Forks starten. Sie lesen denselben Stripe-Schlüssel. Sie rufen dieselbe Stripe-API mit Produktionsdaten auf. Aus Sicht von Stripe ist dieser Aufruf *Sie*.

Das ist kein guter Tag.

## Ein Secret setzen

Die Lösung ist `rdc repo secret`. Setzen Sie eines im Modus `env`. Der Wert landet als Umgebungsvariable im Container:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Zwei Dinge sind zu beachten:

- `--mode env`. Der Wert landet als Umgebungsvariable.
- `--current ""`. Leerer String. Wir deklarieren, dass dies ein brandneues Secret ohne vorherigen Wert ist.

Ein weiteres setzen, im Modus `file`, für alles Sensible:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

Der Modus `file` legt den Wert nie in der Containerumgebung ab. Stattdessen schreibt er ihn nach `/run/secrets/stripe_key`, über Dockers Standardmechanismus.

Auflisten, was vorhanden ist:

```bash
time rdc repo secret list --name my-app
```

Sie sehen Namen und Modi. **Keine Werte.** Die Liste zeigt nie Werte.

## In Compose einbinden

Öffnen Sie `docker-compose.yml`. Referenzieren Sie beide Modi:

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

`${REDIACC_SECRET_DB_HOST}` ist der Modus `env`: `renet`s Compose-Wrapper expandiert ihn beim Deployment aus Ihrem Secret-Store.

Der `secrets:`-Block ist der Modus `file`, über Dockers Standardmechanismus. Der Host-Pfad verwendet `${REDIACC_NETWORK_ID}`, damit dasselbe Compose für Parents und Forks funktioniert. Jeder Fork hat seine eigene Netzwerk-ID.

Deployen:

```bash
time rdc repo up --name my-app -m my-server
```

## Im Container verifizieren

Beide Modi sollten jetzt im Container vorhanden sein. Den Env-Modus-Secret prüfen:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`. Das Env-Modus-Secret hat die Containerumgebung erreicht.

Jetzt den File-Modus:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`. Die Datei ist über Dockers Standardsecrets-Mechanismus eingehängt.

## Es kann nie zurückgelesen werden

![Schreibgeschütztes Modell: get gibt einen Digest zurück, nie den Wert](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Jetzt der Teil, der Menschen überrascht:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

Sie erhalten einen Digest. **Nicht den Wert.** Es gibt kein Flag, das den Wert zurückgibt. Es gibt keinen Befehl irgendwo, der Ihnen den Klartext zurückgibt.

Das ist das GitHub-Actions-Modell: schreibgeschützt. Sie können beweisen, dass Sie ein Secret kennen, indem Sie `--current <value>` übergeben und die Vorbedingung prüfen lassen. Sie können Rediacc nicht bitten, Ihnen zu sagen, was es ist.

Den Wert verloren? **Nicht nachschauen. Rotieren.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` überspringt die Vorbedingung. Das Audit-Log markiert es als Rotation: laut, absichtlich.

Wenn Sie den alten Wert kennen, beweisen Sie es stattdessen:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

Das ist der sicherere Weg. Er fängt den Fehler "Ich bin im falschen Terminal" ab.

## Die Fork-Pointe

![Nach dem Fork ist die Secrets-Liste leer](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

Erinnern Sie sich an die Falle? Das Repo forken und nachsehen:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Leer.**

Der Fork hat keinen Stripe-Schlüssel. Kein Datenbankpasswort. Kein API-Token. Container im Fork können `${REDIACC_SECRET_STRIPE_KEY}` nicht interpolieren. Die Datei unter `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` existiert nicht.

Der Fork kann nicht so tun, als wären Sie es.

Wenn Sie Secrets im Fork zum Testen benötigen, setzen Sie sie explizit mit Sandbox-Werten auf dem Fork:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Jetzt spricht der Fork mit der Stripe-Sandbox. Produktionsdaten haben die Produktion nie verlassen.

## Zusammenfassung

- `rdc repo secret` hinterlegt Ihre Zugangsdaten außerhalb des Repo-Images.
- Der Fork kann sie nicht erreichen.
- `get` gibt einen Digest zurück, nie den Wert.
- Rotieren, wenn Sie vergessen. Nicht nachschauen.

Secrets, denen der Fork nicht folgen kann.

---

Weiter: [Netzwerk und Domains](/de/docs/tutorial-networking).
