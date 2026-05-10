---
title: "Rete e Domini"
description: "Rendi la tua app accessibile su internet con un dominio, TLS automatico e un reverse proxy Traefik. È già tutto configurato e pronto: la semplicità è il suo punto di forza."
category: "Tutorials"
subcategory: advanced
order: 9
language: it
sourceHash: "9f72a61ed1ff4cb9"
---

# Rete e Domini

La tua app è in esecuzione, ma nessuno può ancora raggiungerla. Questo tutorial ti fornisce un dominio reale, TLS automatico tramite Let's Encrypt e un proxy Traefik che rileva automaticamente i tuoi container. Hai bisogno di un dominio su Cloudflare e di un token API.

## Guarda il tutorial

![Tutorial: Rete e domini](/assets/tutorials/tutorial-networking.cast)

## Quattro passi

![Token, configura, invia, distribuisci](/img/tutorials/tutorial-networking/slide-1.svg)

1. **Ottieni** il tuo token API Cloudflare.
2. **Configura** l'infrastruttura su `rdc`.
3. **Invia** al tuo server.
4. **Distribuisci** il proxy.

## Passo 1: Token API Cloudflare

Nel tuo dashboard Cloudflare, vai su **Il mio profilo -> Token API** e crea un token con permesso **Zone DNS Edit**. Copia il valore del token: lo vedrai solo una volta.

## Passo 2: Configura l'infrastruttura

Comunica a `rdc` il tuo IP pubblico, dominio base, email per il certificato e il token:

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

Sostituisci IP, dominio, email e token con i tuoi.

`--cert-email` e `--cf-dns-token` sono condivisi tra tutte le tue macchine, quindi li imposti solo una volta.

## Passo 3: Invia al server

```bash
time rdc config infra push -m my-server
```

Questo crea automaticamente i record DNS su Cloudflare e prepara la configurazione del proxy sul tuo server.

## Passo 4: Distribuisci il proxy

Il proxy stesso non è ancora in esecuzione. Distribuiscilo dal template integrato `proxy`, all'interno di un piccolo repo chiamato `infra`:

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

Fatto. Traefik e' ora in esecuzione. La tua app e' accessibile a:

```
myapp.my-app.my-server.yourdomain.com
```

Traefik rileva i tuoi container ogni 5 secondi. I certificati TLS provengono automaticamente da Let's Encrypt. Nessuna configurazione manuale del proxy necessaria.

---

Successivo: [Modalità di Produzione](/it/docs/tutorial-production-mode).
