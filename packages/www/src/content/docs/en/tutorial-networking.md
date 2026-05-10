---
title: "Networking & Domains"
description: "Make your app accessible on the internet with a domain, automatic TLS, and a Traefik reverse proxy."
category: "Tutorials"
subcategory: advanced
order: 9
language: en
---

# Networking & Domains

Your app is running, but nobody can reach it yet. This tutorial gets you a real domain, automatic TLS via Let's Encrypt, and a Traefik proxy that auto-discovers your containers. You need a domain on Cloudflare and an API token.

## Watch the tutorial

![Tutorial: Networking and domains](/assets/tutorials/tutorial-networking.cast)

## Four steps

![Token, configure, push, deploy](/img/tutorials/tutorial-networking/slide-1.svg)

1. **Get** your Cloudflare API token.
2. **Configure** infrastructure on `rdc`.
3. **Push** it to your server.
4. **Deploy** the proxy.

## Step 1: Cloudflare API token

In your Cloudflare dashboard, go to **My Profile → API Tokens** and create a token with **Zone DNS Edit** permission. Copy the token value. You'll only see it once.

## Step 2: Configure infrastructure

Tell `rdc` your public IP, base domain, certificate email, and the token:

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

Replace the IP, domain, email, and token with your own.

The `--cert-email` and `--cf-dns-token` are shared across all your machines, so you only set them once.

## Step 3: Push to the server

```bash
time rdc config infra push -m my-server
```

This creates the DNS records on Cloudflare automatically and prepares the proxy configuration on your server.

## Step 4: Deploy the proxy

The proxy itself doesn't run yet. Deploy it from the built-in `proxy` template, inside a small repo named `infra`:

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

That's it. Traefik is now running. Your app is accessible at:

```
myapp.my-app.my-server.yourdomain.com
```

Traefik discovers your containers every 5 seconds. TLS certificates come from Let's Encrypt automatically. No manual proxy configuration needed.

---

Next: [Production Mode](/en/docs/tutorial-production-mode).
