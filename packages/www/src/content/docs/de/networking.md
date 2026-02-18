---
title: "Netzwerk"
description: "Dienste mit dem Reverse Proxy, Docker-Labels, TLS-Zertifikaten, DNS und TCP/UDP-Portweiterleitung bereitstellen."
category: "Guides"
order: 6
language: de
---

# Netzwerk

Diese Seite erklärt, wie Dienste, die in isolierten Docker-Daemons laufen, aus dem Internet erreichbar werden. Sie behandelt das Reverse-Proxy-System, Docker-Labels für das Routing, TLS-Zertifikate, DNS und TCP/UDP-Portweiterleitung.

Wie Dienste ihre Loopback-IPs erhalten und das `.rediacc.json`-Slot-System funktioniert, erfahren Sie unter [Dienste](/de/docs/services#dienst-netzwerk-rediaccjson).

## Funktionsweise

Rediacc verwendet ein Zwei-Komponenten-Proxy-System, um externen Traffic an Container weiterzuleiten:

1. **Route Server** -- ein systemd-Dienst, der laufende Container über alle Repository-Docker-Daemons hinweg erkennt. Er inspiziert Container-Labels und generiert Routing-Konfiguration, die als YAML-Endpunkt bereitgestellt wird.
2. **Traefik** -- ein Reverse Proxy, der den Route Server alle 5 Sekunden abfragt und die erkannten Routen anwendet. Er übernimmt HTTP/HTTPS-Routing, TLS-Terminierung und TCP/UDP-Weiterleitung.

Der Ablauf sieht so aus:

```
Internet → Traefik (Ports 80/443/TCP/UDP)
               ↓ fragt alle 5s ab
           Route Server (erkennt Container)
               ↓ inspiziert Labels
           Docker Daemons (/var/run/rediacc/docker-*.sock)
               ↓
           Container (gebunden an 127.x.x.x Loopback-IPs)
```

Wenn Sie die richtigen Labels zu einem Container hinzufügen und ihn mit `renet compose` starten, wird er automatisch routbar -- keine manuelle Proxy-Konfiguration nötig.

## Docker-Labels

Das Routing wird über Docker-Container-Labels gesteuert. Es gibt zwei Stufen:

### Stufe 1: `rediacc.*`-Labels (Automatisch)

Diese Labels werden **automatisch** von `renet compose` beim Starten von Diensten injiziert. Sie müssen sie nicht manuell hinzufügen.

| Label | Beschreibung | Beispiel |
|-------|-------------|---------|
| `rediacc.service_name` | Dienst-Identität | `myapp` |
| `rediacc.service_ip` | Zugewiesene Loopback-IP | `127.0.11.2` |
| `rediacc.network_id` | Docker-Daemon-ID des Repositories | `2816` |

Wenn ein Container nur `rediacc.*`-Labels hat (kein `traefik.enable=true`), generiert der Route Server eine **Auto-Route**:

```
{service}-{networkID}.{baseDomain}
```

Zum Beispiel erhält ein Dienst namens `myapp` in einem Repository mit Netzwerk-ID `2816` und Basis-Domain `example.com`:

```
myapp-2816.example.com
```

Auto-Routen sind nützlich für die Entwicklung und den internen Zugriff. Für Produktionsdienste mit eigenen Domains verwenden Sie Stufe-2-Labels.

### Stufe 2: `traefik.*`-Labels (Benutzerdefiniert)

Fügen Sie diese Labels in Ihre `docker-compose.yml` ein, wenn Sie benutzerdefiniertes Domain-Routing, TLS oder bestimmte Einstiegspunkte wünschen. Das Setzen von `traefik.enable=true` weist den Route Server an, Ihre benutzerdefinierten Regeln anstelle einer Auto-Route zu verwenden.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

Diese verwenden die Standard-[Traefik v3 Label-Syntax](https://doc.traefik.io/traefik/routing/providers/docker/).

> **Tipp:** Rein interne Dienste (Datenbanken, Caches, Nachrichtenwarteschlangen) sollten **kein** `traefik.enable=true` haben. Sie benötigen nur `rediacc.*`-Labels, die automatisch injiziert werden.

## HTTP/HTTPS-Dienste bereitstellen

### Voraussetzungen

1. Infrastruktur auf der Maschine konfiguriert ([Maschineneinrichtung -- Infrastruktur-Konfiguration](/de/docs/setup#infrastruktur-konfiguration)):

   ```bash
   rdc context set-infra server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   rdc context push-infra server-1
   ```

2. DNS-Einträge, die Ihre Domain auf die öffentliche IP des Servers verweisen (siehe [DNS-Konfiguration](#dns-konfiguration) unten).

### Labels hinzufügen

Fügen Sie `traefik.*`-Labels zu den Diensten hinzu, die Sie in Ihrer `docker-compose.yml` bereitstellen möchten:

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
    # Keine Traefik-Labels — Datenbank ist nur intern
```

| Label | Zweck |
|-------|-------|
| `traefik.enable=true` | Aktiviert benutzerdefiniertes Traefik-Routing für diesen Container |
| `traefik.http.routers.{name}.rule` | Routing-Regel -- typischerweise `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | Auf welchen Ports gelauscht wird: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Zertifikat-Resolver -- verwenden Sie `letsencrypt` für automatisches Let's Encrypt |
| `traefik.http.services.{name}.loadbalancer.server.port` | Der Port, auf dem Ihre Anwendung im Container lauscht |

Der `{name}` in den Labels ist ein beliebiger Bezeichner -- er muss nur über zusammengehörige Router-/Service-/Middleware-Labels konsistent sein.

> **Hinweis:** Die `rediacc.*`-Labels (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) werden automatisch von `renet compose` injiziert. Sie müssen sie nicht in Ihre Compose-Datei einfügen.

## TLS-Zertifikate

TLS-Zertifikate werden automatisch über Let's Encrypt mittels der Cloudflare DNS-01-Challenge bezogen. Dies wird einmalig bei der Infrastruktureinrichtung konfiguriert:

```bash
rdc context set-infra server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Wenn ein Dienst `traefik.http.routers.{name}.tls.certresolver=letsencrypt` hat, führt Traefik automatisch folgende Schritte durch:
1. Fordert ein Zertifikat von Let's Encrypt an
2. Validiert die Domain-Eigentümerschaft über Cloudflare DNS
3. Speichert das Zertifikat lokal
4. Erneuert es vor dem Ablauf

Das Cloudflare DNS API-Token benötigt `Zone:DNS:Edit`-Berechtigung für die Domains, die Sie absichern möchten. Dieser Ansatz funktioniert für jede von Cloudflare verwaltete Domain, einschließlich Wildcard-Zertifikaten.

## TCP/UDP-Portweiterleitung

Für Nicht-HTTP-Protokolle (Mailserver, DNS, extern bereitgestellte Datenbanken) verwenden Sie TCP/UDP-Portweiterleitung.

### Schritt 1: Ports registrieren

Fügen Sie die erforderlichen Ports bei der Infrastruktur-Konfiguration hinzu:

```bash
rdc context set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc context push-infra server-1
```

Dies erstellt Traefik-Einstiegspunkte namens `tcp-{port}` und `udp-{port}`.

> Nach dem Hinzufügen oder Entfernen von Ports führen Sie immer `rdc context push-infra` erneut aus, um die Proxy-Konfiguration zu aktualisieren.

### Schritt 2: TCP/UDP-Labels hinzufügen

Verwenden Sie `traefik.tcp.*`- oder `traefik.udp.*`-Labels in Ihrer Compose-Datei:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    network_mode: host
    labels:
      - "traefik.enable=true"

      # SMTP (Port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (Port 993) — TLS-Passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Wichtige Konzepte:
- **`HostSNI(\`*\`)`** stimmt mit jedem Hostnamen überein (für Protokolle, die kein SNI senden, wie unverschlüsseltes SMTP)
- **`tls.passthrough=true`** bedeutet, dass Traefik die rohe TLS-Verbindung weiterleitet, ohne zu entschlüsseln -- die Anwendung übernimmt die TLS-Verarbeitung selbst
- Einstiegspunkt-Namen folgen der Konvention `tcp-{port}` oder `udp-{port}`

### Vorkonfigurierte Ports

Die folgenden TCP/UDP-Ports haben standardmäßig Einstiegspunkte (kein Hinzufügen über `--tcp-ports` erforderlich):

| Port | Protokoll | Häufige Verwendung |
|------|----------|-------------------|
| 80 | HTTP | Web (automatische Weiterleitung zu HTTPS) |
| 443 | HTTPS | Web (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000–10010 | TCP | Dynamischer Bereich (automatische Zuordnung) |

## DNS-Konfiguration

Verweisen Sie Ihre Domains auf die öffentlichen IP-Adressen des Servers, die in `set-infra` konfiguriert wurden:

### Individuelle Dienst-Domains

Erstellen Sie A- (IPv4) und/oder AAAA- (IPv6) Einträge für jeden Dienst:

```
app.example.com      A     203.0.113.50
app.example.com      AAAA  2001:db8::1
gitlab.example.com   A     203.0.113.50
mail.example.com     A     203.0.113.50
```

### Wildcard für Auto-Routen

Wenn Sie Auto-Routen (Stufe 1) verwenden, erstellen Sie einen Wildcard-DNS-Eintrag:

```
*.example.com   A     203.0.113.50
*.example.com   AAAA  2001:db8::1
```

Dies leitet alle Subdomains an Ihren Server weiter, und Traefik ordnet sie anhand der `Host()`-Regel oder des Auto-Routen-Hostnamens dem richtigen Dienst zu.

## Middlewares

Traefik-Middlewares modifizieren Anfragen und Antworten. Wenden Sie sie über Labels an.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Pufferung für große Datei-Uploads

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Mehrere Middlewares

Verketten Sie Middlewares durch Kommatrennung:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

Die vollständige Liste verfügbarer Middlewares finden Sie in der [Traefik-Middleware-Dokumentation](https://doc.traefik.io/traefik/middlewares/overview/).

## Diagnose

Wenn ein Dienst nicht erreichbar ist, verbinden Sie sich per SSH mit dem Server und prüfen Sie die Route-Server-Endpunkte:

### Gesundheitsprüfung

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Zeigt den Gesamtstatus, die Anzahl erkannter Router und Dienste und ob Auto-Routen aktiviert sind.

### Erkannte Routen

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Listet alle HTTP-, TCP- und UDP-Router mit ihren Regeln, Einstiegspunkten und Backend-Diensten auf.

### Port-Zuordnungen

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Zeigt TCP- und UDP-Port-Zuordnungen für dynamisch zugewiesene Ports.

### Häufige Probleme

| Problem | Ursache | Lösung |
|---------|---------|--------|
| Dienst nicht in Routen | Container läuft nicht oder Labels fehlen | Mit `docker ps` auf dem Repository-Daemon überprüfen; Labels prüfen |
| Zertifikat nicht ausgestellt | DNS zeigt nicht auf den Server oder ungültiges Cloudflare-Token | DNS-Auflösung überprüfen; Cloudflare-API-Token-Berechtigungen prüfen |
| 502 Bad Gateway | Anwendung lauscht nicht auf dem deklarierten Port | Überprüfen, ob die App an ihre `{SERVICE}_IP` gebunden ist und der Port mit `loadbalancer.server.port` übereinstimmt |
| TCP-Port nicht erreichbar | Port nicht in der Infrastruktur registriert | `rdc context set-infra --tcp-ports ...` und `push-infra` ausführen |

## Vollständiges Beispiel

Dieses Beispiel stellt eine Webanwendung mit einer PostgreSQL-Datenbank bereit. Die App ist öffentlich unter `app.example.com` mit TLS erreichbar; die Datenbank ist nur intern verfügbar.

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
    # Keine Traefik-Labels — nur intern
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

Erstellen Sie einen A-Eintrag, der `app.example.com` auf die öffentliche IP Ihres Servers verweist:

```
app.example.com   A   203.0.113.50
```

### Bereitstellung

```bash
rdc repo up my-app -m server-1 --mount
```

Innerhalb weniger Sekunden erkennt der Route Server den Container, Traefik übernimmt die Route, fordert ein TLS-Zertifikat an, und `https://app.example.com` ist live.
