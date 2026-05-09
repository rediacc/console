---
title: "Gestione dei Segreti"
description: "Metti le credenziali di deploy in un posto che i fork non possono raggiungere. Solo scrittura per design. È la soluzione più sicura perché i segreti non vengono mai esposti."
category: "Tutorials"
subcategory: advanced
order: 8
language: it
sourceHash: "0b4d72c80b489e12"
---

# Gestione dei Segreti

Le app reali hanno bisogno di credenziali reali: una chiave live Stripe, una password del database, un token API. Il posto sbagliato dove metterle è nel repo, perché un fork eredita tutto ciò che si trova all'interno dell'immagine cifrata: e improvvisamente la tua sandbox sta addebitando le carte dei clienti reali.

Il posto giusto è `rdc repo secret`. Due modalità di consegna, solo scrittura per design, e il fork inizia senza nulla.

## Guarda il tutorial

![Tutorial: Gestione dei segreti](/assets/tutorials/tutorial-managing-secrets.cast)

## La trappola: `.env` nel repo

![Un file .env all'interno dell'immagine del repo viene clonato da ogni fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

La maggior parte dei team mette `.env` nel repo. È la mossa ovvia.

Poi fanno il fork.

Il fork e' una copia byte per byte dell'immagine del parent. Qualunque cosa ci sia in `.env` è nel `.env` del fork. I container del fork si avviano. Leggono la stessa chiave Stripe. Chiamano la stessa API Stripe con le credenziali di produzione. Dal punto di vista di Stripe, quella chiamata sei *tu*.

Brutta giornata.

## Imposta un segreto

La soluzione è `rdc repo secret`. Impostane uno in modalità `env`: arriva come variabile d'ambiente nel container:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Due cose da notare:

- `--mode env`. Il valore arriva come variabile d'ambiente.
- `--current ""`. Stringa vuota. Stiamo dichiarando che questo è un segreto nuovo senza valore precedente.

Impostane un altro, in modalita' `file`, per qualsiasi cosa sensibile:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

La modalità `file` non inserisce mai il valore nell'ambiente del container. Lo scrive invece in `/run/secrets/stripe_key`: il meccanismo standard di Docker.

Elenca quello che hai:

```bash
time rdc repo secret list --name my-app
```

Vedi nomi e modalita'. **Nessun valore.** La lista non mostra mai i valori.

## Collegalo a compose

Apri `docker-compose.yml`. Fai riferimento a entrambe le modalita':

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

`${REDIACC_SECRET_DB_HOST}` è la modalità `env`: il wrapper compose di `renet` lo espande dal tuo store di segreti al momento del deploy.

Il blocco `secrets:` è la modalità `file`: il meccanismo standard di Docker. Il percorso host usa `${REDIACC_NETWORK_ID}` in modo che lo stesso compose funzioni per parent e fork. Ogni fork ha il proprio ID di rete.

Distribuisci:

```bash
time rdc repo up --name my-app -m my-server
```

## Verifica nel container

Entrambe le modalità dovrebbero essere all'interno del container ora. Controlla il segreto in modalità env:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`: il segreto in modalita' env ha raggiunto l'ambiente del container.

Ora quello in modalità file:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`: il file e' montato tramite il meccanismo standard di segreti di Docker.

## Non puoi mai rileggerlo

![Modello solo scrittura: get restituisce un digest, mai il valore](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Ora la parte che sorprende le persone:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

Ottieni un digest. **Non il valore.** Non esiste un flag che lo faccia restituire il valore. Non esiste alcun comando che ti restituirà il testo in chiaro.

Questo e' il modello GitHub Actions: solo scrittura. Puoi dimostrare di sapere cosa e' un segreto passando `--current <value>` e osservando la precondizione soddisfatta. Non puoi chiedere a Rediacc di dirtelo.

Hai perso il valore? **Non spiare. Ruota.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` salta la precondizione. Il log di audit lo segna come rotazione: esplicito, deliberato.

Se ricordi il vecchio valore, dimostracelo invece:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

Questo è il percorso più sicuro: cattura l'errore "sono nel terminale sbagliato".

## La conclusione del fork

![Dopo il fork, la lista dei segreti e' vuota](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

Ricordi la trappola? Fai il fork del repo e guarda:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Vuoto.**

Il fork non ha la chiave Stripe. Nessuna password del database. Nessun token API. I container nel fork non possono interpolare `${REDIACC_SECRET_STRIPE_KEY}`. Il file in `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` non esiste.

Il fork non puo' fingersi te.

Se vuoi segreti nel fork per i test, impostali esplicitamente nel fork, con valori sandbox:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Ora il fork comunica con la sandbox di Stripe. Le credenziali di produzione non hanno mai lasciato la produzione.

## Riepilogo

- `rdc repo secret` mette le tue credenziali fuori dall'immagine del repo.
- Il fork non puo' raggiungerle.
- `get` restituisce un digest, mai il valore.
- Ruota quando dimentichi. Non spiare.

Segreti che il fork non puo' seguire.

---

Successivo: [Rete e Domini](/it/docs/tutorial-networking).
