---
title: "Netzwerk und Domains"
description: "Machen Sie Ihre App mit einer Domain, automatischem TLS und einem Traefik-Reverse-Proxy im Internet erreichbar."
category: "Tutorials"
subcategory: advanced
order: 9
language: de
sourceHash: "9f72a61ed1ff4cb9"
---

# Netzwerk und Domains

Ihre App läuft, aber niemand kann sie noch erreichen. Dieses Tutorial verschafft Ihnen eine echte Domain, automatisches TLS über Let's Encrypt und einen Traefik-Proxy, der Ihre Container automatisch erkennt. Sie benötigen eine Domain bei Cloudflare und ein API-Token.

## Tutorial ansehen

![Tutorial: Netzwerk und Domains](/assets/tutorials/tutorial-networking.cast)

## Vier Schritte

![Token, konfigurieren, übertragen, deployen](/img/tutorials/tutorial-networking/slide-1.svg)

1. **Token** von Cloudflare holen.
2. **Infrastruktur** bei `rdc` konfigurieren.
3. **Auf Ihren Server übertragen.**
4. **Proxy deployen.**

## Schritt 1: Cloudflare-API-Token

Gehen Sie in Ihrem Cloudflare-Dashboard zu **Mein Profil - API-Tokens** und erstellen Sie ein Token mit der Berechtigung **Zone DNS Edit**. Kopieren Sie den Token-Wert. Sie sehen ihn nur einmal.

## Schritt 2: Infrastruktur konfigurieren

Teilen Sie `rdc` Ihre öffentliche IP, Basisdomain, Zertifikats-E-Mail und das Token mit:

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

Ersetzen Sie IP, Domain, E-Mail und Token durch Ihre eigenen Angaben.

`--cert-email` und `--cf-dns-token` werden über alle Ihre Maschinen geteilt, sodass Sie sie nur einmal setzen müssen.

## Schritt 3: Auf den Server übertragen

```bash
time rdc config infra push -m my-server
```

Hiermit werden die DNS-Einträge bei Cloudflare automatisch erstellt und die Proxy-Konfiguration auf Ihrem Server vorbereitet.

## Schritt 4: Proxy deployen

Der Proxy selbst läuft noch nicht. Deployen Sie ihn aus der integrierten `proxy`-Vorlage, in einem kleinen Repo namens `infra`:

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

Das war es. Traefik läuft jetzt. Ihre App ist erreichbar unter:

```
myapp.my-app.my-server.yourdomain.com
```

Traefik erkennt Ihre Container alle 5 Sekunden. TLS-Zertifikate kommen automatisch von Let's Encrypt. Keine manuelle Proxy-Konfiguration erforderlich.

---

Weiter: [Produktionsmodus](/de/docs/tutorial-production-mode).
