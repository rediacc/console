---
title: "Networking"
description: "Expose services with the reverse proxy, Docker labels, TLS certificates, DNS, and TCP/UDP port forwarding."
category: "Guides"
order: 6
language: en
---

# Networking

This page explains how services running inside isolated Docker daemons become accessible from the internet. It covers the reverse proxy system, Docker labels for routing, TLS certificates, DNS, and TCP/UDP port forwarding.

For how services get their loopback IPs and the `.rediacc.json` slot system, see [Services](/en/docs/services#service-networking-rediaccjson).

## How It Works

Rediacc uses a two-component proxy system to route external traffic to containers:

1. **Route server** — a systemd service that discovers running containers across all repository Docker daemons. It inspects container labels and generates routing configuration, served as a YAML endpoint.
2. **Traefik** — a reverse proxy that polls the route server every 5 seconds and applies the discovered routes. It handles HTTP/HTTPS routing, TLS termination, and TCP/UDP forwarding.

The flow looks like this:

```
Internet → Traefik (ports 80/443/TCP/UDP)
               ↓ polls every 5s
           Route Server (discovers containers)
               ↓ inspects labels
           Docker Daemons (/var/run/rediacc/docker-*.sock)
               ↓
           Containers (bound to 127.x.x.x loopback IPs)
```

When you add the right labels to a container and start it with `renet compose`, it automatically becomes routable — no manual proxy configuration needed.

## Docker Labels

Routing is controlled by Docker container labels. There are two tiers:

### Tier 1: `rediacc.*` Labels (Automatic)

These labels are **automatically injected** by `renet compose` when starting services. You do not need to add them manually.

| Label | Description | Example |
|-------|-------------|---------|
| `rediacc.service_name` | Service identity | `myapp` |
| `rediacc.service_ip` | Assigned loopback IP | `127.0.11.2` |
| `rediacc.network_id` | Repository's daemon ID | `2816` |

When a container has only `rediacc.*` labels (no `traefik.enable=true`), the route server generates an **auto-route**:

```
{service}-{networkID}.{baseDomain}
```

For example, a service named `myapp` in a repository with network ID `2816` and base domain `example.com` gets:

```
myapp-2816.example.com
```

Auto-routes are useful for development and internal access. For production services with custom domains, use Tier 2 labels.

### Tier 2: `traefik.*` Labels (User-Defined)

Add these labels to your `docker-compose.yml` when you want custom domain routing, TLS, or specific entrypoints. Setting `traefik.enable=true` tells the route server to use your custom rules instead of generating an auto-route.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

These use standard [Traefik v3 label syntax](https://doc.traefik.io/traefik/routing/providers/docker/).

> **Tip:** Internal-only services (databases, caches, message queues) should **not** have `traefik.enable=true`. They only need `rediacc.*` labels, which are injected automatically.

## Exposing HTTP/HTTPS Services

### Prerequisites

1. Infrastructure configured on the machine ([Machine Setup — Infrastructure Configuration](/en/docs/setup#infrastructure-configuration)):

   ```bash
   rdc context set-infra server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   rdc context push-infra server-1
   ```

2. DNS records pointing your domain to the server's public IP (see [DNS Configuration](#dns-configuration) below).

### Adding Labels

Add `traefik.*` labels to the services you want to expose in your `docker-compose.yml`:

```yaml
services:
  myapp:
    image: myapp:latest
    network_mode: host
    environment:
      - LISTEN_ADDR=${MYAPP_IP}:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    network_mode: host
    command: ["-c", "listen_addresses=${DATABASE_IP}"]
    # No traefik labels — database is internal only
```

| Label | Purpose |
|-------|---------|
| `traefik.enable=true` | Enables custom Traefik routing for this container |
| `traefik.http.routers.{name}.rule` | Routing rule — typically `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | Which ports to listen on: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Certificate resolver — use `letsencrypt` for automatic Let's Encrypt |
| `traefik.http.services.{name}.loadbalancer.server.port` | The port your application listens on inside the container |

The `{name}` in labels is an arbitrary identifier — it just needs to be consistent across related router/service/middleware labels.

> **Note:** The `rediacc.*` labels (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) are injected automatically by `renet compose`. You do not need to add them to your compose file.

## TLS Certificates

TLS certificates are obtained automatically via Let's Encrypt using the Cloudflare DNS-01 challenge. This is configured once during infrastructure setup:

```bash
rdc context set-infra server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

When a service has `traefik.http.routers.{name}.tls.certresolver=letsencrypt`, Traefik automatically:
1. Requests a certificate from Let's Encrypt
2. Validates domain ownership via Cloudflare DNS
3. Stores the certificate locally
4. Renews it before expiry

The Cloudflare DNS API token needs `Zone:DNS:Edit` permission for the domains you want to secure. This approach works for any domain managed by Cloudflare, including wildcard certificates.

## TCP/UDP Port Forwarding

For non-HTTP protocols (mail servers, DNS, databases exposed externally), use TCP/UDP port forwarding.

### Step 1: Register Ports

Add the required ports during infrastructure configuration:

```bash
rdc context set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc context push-infra server-1
```

This creates Traefik entrypoints named `tcp-{port}` and `udp-{port}`.

> After adding or removing ports, always re-run `rdc context push-infra` to update the proxy configuration.

### Step 2: Add TCP/UDP Labels

Use `traefik.tcp.*` or `traefik.udp.*` labels in your compose file:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    network_mode: host
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993) — TLS passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Key concepts:
- **`HostSNI(\`*\`)`** matches any hostname (for protocols that don't send SNI, like plain SMTP)
- **`tls.passthrough=true`** means Traefik forwards the raw TLS connection without decrypting — the application handles TLS itself
- Entrypoint names follow the convention `tcp-{port}` or `udp-{port}`

### Pre-Configured Ports

The following TCP/UDP ports have entrypoints by default (no need to add via `--tcp-ports`):

| Port | Protocol | Common Use |
|------|----------|------------|
| 80 | HTTP | Web (auto-redirect to HTTPS) |
| 443 | HTTPS | Web (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000–10010 | TCP | Dynamic range (auto-allocation) |

## DNS Configuration

Point your domains to the server's public IP addresses configured in `set-infra`:

### Individual Service Domains

Create A (IPv4) and/or AAAA (IPv6) records for each service:

```
app.example.com      A     203.0.113.50
app.example.com      AAAA  2001:db8::1
gitlab.example.com   A     203.0.113.50
mail.example.com     A     203.0.113.50
```

### Wildcard for Auto-Routes

If you use auto-routes (Tier 1), create a wildcard DNS record:

```
*.example.com   A     203.0.113.50
*.example.com   AAAA  2001:db8::1
```

This routes all subdomains to your server, and Traefik matches them to the correct service based on the `Host()` rule or auto-route hostname.

## Middlewares

Traefik middlewares modify requests and responses. Apply them via labels.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Large File Upload Buffering

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Multiple Middlewares

Chain middlewares by comma-separating them:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

For the full list of available middlewares, see the [Traefik middleware documentation](https://doc.traefik.io/traefik/middlewares/overview/).

## Diagnostics

If a service is not accessible, SSH into the server and check the route server endpoints:

### Health Check

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Shows overall status, number of discovered routers and services, and whether auto-routes are enabled.

### Discovered Routes

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Lists all HTTP, TCP, and UDP routers with their rules, entrypoints, and backend services.

### Port Allocations

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Shows TCP and UDP port mappings for dynamically allocated ports.

### Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| Service not in routes | Container not running or missing labels | Verify with `docker ps` on the repository's daemon; check labels |
| Certificate not issued | DNS not pointing to server, or invalid Cloudflare token | Verify DNS resolution; check Cloudflare API token permissions |
| 502 Bad Gateway | Application not listening on the declared port | Verify the app binds to its `{SERVICE}_IP` and the port matches `loadbalancer.server.port` |
| TCP port not reachable | Port not registered in infrastructure | Run `rdc context set-infra --tcp-ports ...` and `push-infra` |

## Complete Example

This deploys a web application with a PostgreSQL database. The app is publicly accessible at `app.example.com` with TLS; the database is internal only.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      LISTEN_ADDR: ${WEBAPP_IP}:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    network_mode: host
    restart: unless-stopped
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # No traefik labels — internal only
```

### Rediaccfile

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

Create an A record pointing `app.example.com` to your server's public IP:

```
app.example.com   A   203.0.113.50
```

### Deploy

```bash
rdc repo up my-app -m server-1 --mount
```

Within a few seconds, the route server discovers the container, Traefik picks up the route, requests a TLS certificate, and `https://app.example.com` is live.
