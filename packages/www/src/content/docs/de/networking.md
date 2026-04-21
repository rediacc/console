---
title: Netzwerk
description: >-
  Dienste über den Reverse Proxy, Docker-Labels, TLS-Zertifikate, DNS und
  TCP/UDP-Portweiterleitung für externe Erreichbarkeit bereitstellen.
category: Guides
order: 6
language: de
sourceHash: 5f8a1092ed53e1b4
sourceCommit: 8b0f83c57ebaaa0a2bee93143db34ab677b4e68b
---

# Netzwerk

Diese Seite erklärt, wie Dienste, die in isolierten Docker-Daemons laufen, aus dem Internet erreichbar werden. Sie behandelt das Reverse-Proxy-System, Docker-Labels für das Routing, TLS-Zertifikate, DNS und TCP/UDP-Portweiterleitung.

Wie Dienste ihre Loopback-IPs erhalten und das `.rediacc.json`-Slot-System funktioniert, erfahren Sie unter [Dienste](/de/docs/services#dienst-netzwerk-rediaccjson).

## Netzwerkisolierung

Jedes Repository wird automatisch auf Kernel-Ebene über Netzwerk-Hooks isoliert. Dies erfordert Linux-Kernel 6.1 oder neuer. Keine Konfiguration erforderlich.

- **Automatisches Bind-Rewriting**: Dienste können sich wie gewohnt an `0.0.0.0` oder `127.0.0.1` binden. Der Kernel schreibt die Adresse transparent auf die zugewiesene Loopback-IP des Dienstes um. Kein explizites Binden an `${SERVICE_IP}` nötig.
- **Verbindungsblockierung zwischen Repos**: Versucht ein Dienst, eine Loopback-IP außerhalb des `/26`-Subnetzes seines Repositories zu kontaktieren, blockiert der Kernel dies. Ein Prozess in Repo A kann Dienste in Repo B nicht erreichen.
- **Keine Anwendungsanpassungen nötig**: Dienste verwenden `0.0.0.0` oder `localhost` zum Binden, und der Kernel stellt sicher, dass sie nur auf ihrer korrekten Loopback-IP lauschen. Die Isolierung ist vollständig transparent.

## Funktionsweise

Rediacc verwendet ein Zwei-Komponenten-Proxy-System, um externen Traffic an Container weiterzuleiten:

1. **Route Server**, ein systemd-Dienst, der laufende Container über alle Repository-Docker-Daemons hinweg erkennt. Er inspiziert Container-Labels und generiert Routing-Konfiguration, die als YAML-Endpunkt bereitgestellt wird.
2. **Traefik**, ein Reverse Proxy, der den Route Server alle 5 Sekunden abfragt und die erkannten Routen anwendet. Er übernimmt HTTP/HTTPS-Routing, TLS-Terminierung und TCP/UDP-Weiterleitung.

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

Wenn Sie die richtigen Labels zu einem Container hinzufügen und ihn mit `renet compose` starten, wird er automatisch routbar, keine manuelle Proxy-Konfiguration nötig.

> Das Route-Server-Binary wird mit Ihrer CLI-Version synchron gehalten. Wenn die CLI das renet-Binary auf einer Maschine aktualisiert, wird der Route Server automatisch neu gestartet (~1-2 Sekunden). Dies verursacht keine Ausfallzeit, Traefik bedient weiterhin Traffic mit seiner letzten bekannten Konfiguration während des Neustarts und übernimmt die neue Konfiguration beim nächsten Poll. Bestehende Client-Verbindungen sind nicht betroffen. Ihre Anwendungscontainer werden nicht berührt.

## Docker-Labels

Das Routing wird über Docker-Container-Labels gesteuert. Es gibt zwei Stufen:

### Stufe 1: `rediacc.*`-Labels (Automatisch)

Diese Labels werden **automatisch** von `renet compose` beim Starten von Diensten injiziert. Sie müssen sie nicht manuell hinzufügen.

| Label | Beschreibung | Beispiel |
|-------|-------------|---------|
| `rediacc.service_name` | Dienst-Identität | `myapp` |
| `rediacc.service_ip` | Zugewiesene Loopback-IP | `127.0.11.2` |
| `rediacc.network_id` | Docker-Daemon-ID des Repositories | `2816` |
| `rediacc.repo_name` | Repository-Name | `marketing` |
| `rediacc.tcp_ports` | TCP-Ports, auf denen der Dienst lauscht | `8080,8443` |
| `rediacc.udp_ports` | UDP-Ports, auf denen der Dienst lauscht | `53` |

Wenn ein Container nur `rediacc.*`-Labels hat (kein `traefik.enable=true`), generiert der Route Server eine **Auto-Route** unter Verwendung des Repository-Namens und der Maschinen-Subdomain:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

Zum Beispiel erhält ein Dienst namens `myapp` in einem Repository namens `marketing` auf Maschine `server-1` mit Basis-Domain `example.com`:

```
myapp.marketing.server-1.example.com
```

Bei Forks wird der Dienstname mit dem reservierten Wort `fork` und dem Tag kombiniert:

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

Zum Beispiel erhält ein Fork von `marketing` mit Tag `staging`:

```
myapp-fork-staging.marketing.server-1.example.com
```

Jede Fork-URL liegt unter der Subdomain des übergeordneten Repos und wird durch das bestehende Wildcard-Zertifikat abgedeckt, sodass kein neues Zertifikat benötigt wird. Der `-fork-`-Trenner verhindert Kollisionen mit echten Dienstnamen im Produktions-Repo. Für Dienste mit benutzerdefinierten Domains verwenden Sie Stufe-2-Labels oder das `rediacc.domain`-Label.

#### Benutzerdefinierte Domain via `rediacc.domain`

Sie können eine benutzerdefinierte Domain für einen Dienst über das `rediacc.domain`-Label in Ihrer `docker-compose.yml` festlegen. Sowohl Kurznamen als auch vollständige Domains werden unterstützt:

```yaml
labels:
  # Kurzname, wird zu cloud.example.com aufgelöst unter Verwendung der baseDomain der Maschine
  - "rediacc.domain=cloud"

  # Vollständige Domain, wird wie angegeben verwendet
  - "rediacc.domain=cloud.example.com"
```

Ein Wert ohne Punkte wird als Kurzname behandelt und die `baseDomain` der Maschine wird automatisch angehängt. Ein Wert mit Punkten wird als vollständige Domain verwendet.

Wenn `machineName` konfiguriert ist, erhalten Dienste mit benutzerdefinierter Domain **zwei Routen**: eine auf der Basis-Domain (`cloud.example.com`) und eine auf der Maschinen-Subdomain (`cloud.server-1.example.com`).

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

1. Infrastruktur auf der Maschine konfiguriert ([Maschineneinrichtung, Infrastruktur-Konfiguration](/de/docs/setup#infrastruktur-konfiguration)):

   ```bash
   # Gemeinsame Zugangsdaten (einmal pro Konfiguration, gilt für alle Maschinen)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # Maschinenspezifische Einstellungen
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. DNS-Einträge, die Ihre Domain auf die öffentliche IP des Servers verweisen (siehe [DNS-Konfiguration](#dns-konfiguration) unten).

### Labels hinzufügen

Fügen Sie `traefik.*`-Labels zu den Diensten hinzu, die Sie in Ihrer `docker-compose.yml` bereitstellen möchten:

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # Keine Traefik-Labels, Datenbank ist nur intern
```

| Label | Zweck |
|-------|-------|
| `traefik.enable=true` | Aktiviert benutzerdefiniertes Traefik-Routing für diesen Container |
| `traefik.http.routers.{name}.rule` | Routing-Regel, typischerweise `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | Auf welchen Ports gelauscht wird: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Zertifikat-Resolver, verwenden Sie `letsencrypt` für automatisches Let's Encrypt |
| `traefik.http.services.{name}.loadbalancer.server.port` | Der Port, auf dem Ihre Anwendung im Container lauscht |

Der `{name}` in den Labels ist ein beliebiger Bezeichner, er muss nur über zusammengehörige Router-/Service-/Middleware-Labels konsistent sein.

> **Hinweis:** Die `rediacc.*`-Labels (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) werden automatisch von `renet compose` injiziert. Sie müssen sie nicht in Ihre Compose-Datei einfügen.

## TLS-Zertifikate

TLS-Zertifikate werden automatisch über Let's Encrypt mittels der Cloudflare DNS-01-Challenge bezogen. Die Zugangsdaten werden einmal pro Konfiguration eingerichtet (gemeinsam für alle Maschinen):

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Auto-Routen verwenden **Wildcard-Zertifikate** auf Repository-Subdomain-Ebene (`*.marketing.server-1.example.com`) anstelle von Zertifikaten pro Dienst. Das Zertifikat wird automatisch von Traefik beim ersten `repo up` bereitgestellt, kein manueller Schritt erforderlich. Forks verwenden das bestehende Wildcard-Zertifikat des übergeordneten Repos wieder, sodass nie eine neue Zertifikatsanforderung ausgelöst wird. Routen mit benutzerdefinierten Domains verwenden Maschinen-Wildcards (`*.server-1.example.com`).

> **Erfordert Cloudflare-Zugangsdaten.** Wildcard-Zertifikate verwenden DNS-01-Challenge. Ohne `--cf-dns-token` (und optional `--cert-email`) kann Traefik die Challenge nicht abschließen und HTTPS wird nicht funktionieren. HTTP bleibt funktionsfähig. Konfigurieren Sie die Zugangsdaten mit `rdc config infra set` vor dem ersten Deployment.

Für Stufe-2-Routen mit `traefik.http.routers.{name}.tls.certresolver=letsencrypt` werden Wildcard-Domain-SANs automatisch basierend auf dem Hostnamen der Route injiziert.

Das Cloudflare DNS API-Token benötigt `Zone:DNS:Edit`-Berechtigung für die Domains, die Sie absichern möchten.

### TLS-Zertifikatslebenszyklus

Der vollständige Weg, den ein Let's Encrypt-Zertifikat von der Ausstellung bis zu den Containern jedes Repos zurücklegt:

1. **Ausstellung auf dem Host.** Ein Traefik-Container auf Maschinenebene (`rediacc-proxy`, bereitgestellt unter `/opt/rediacc/proxy/`) besitzt die ACME-Erneuerung. Er speichert den gesamten Zustand in `/opt/rediacc/proxy/letsencrypt/acme.json` auf dem Host. Die Erneuerung wird automatisch ca. 30 Tage vor Ablauf ausgelöst; kein Eingriff des Betreibers erforderlich, solange `--cf-dns-token` konfiguriert ist.

2. **Pro-Repo-Dumping (optional).** Dienste, die Zertifikatsdateien innerhalb ihres eigenen Containers benötigen (z. B. ein Mailserver, der eine `.pem`-Datei direkt liest), stellen einen kleinen `traefik-certs-dumper`-Container neben sich her. Der Dumper bindet `/opt/rediacc/proxy/letsencrypt` schreibgeschützt ein und schreibt das extrahierte Zertifikat und den Schlüssel als `cert.pem` / `key.pem` in das Datenvolume des Repos. Dafür muss der pro-Repo Docker-Daemon `/opt/rediacc/proxy` in seiner Mount-Namespace-Positivliste haben. Dies ist standardmäßig bereits enthalten.

3. **Client-seitiger Cache (`rediacc.json`).** Die CLI speichert eine komprimierte Kopie von `acme.json` unter `acmeCertCache` in Ihrer Konfigurationsdatei, indexiert nach `baseDomain`. Dies ermöglicht mehreren Maschinen die gemeinsame Nutzung von Zertifikaten (via `rdc config cert-cache push -m <machine>`) und dient als Offline-Inventar.

**Sync-Auslöser für den Client-Cache:**

- Automatisch nach `rdc repo up`, aber nur wenn der lokale Cache für die `baseDomain` der Maschine älter als 6 Stunden ist. Frische Caches werden in Ruhe gelassen, damit Back-to-back-Deployments SSH nicht belasten.
- Auf Anfrage: `rdc config cert-cache pull -m <machine>` (Force-Pull) oder `rdc machine query --name <machine> --sync-certs` (Pull als Nebeneffekt einer Statusabfrage).
- Bei `rdc config infra push` wird der Cache auf die Maschine hochgeladen (lokale Zertifikate mit längerem Ablauf gewinnen gegenüber Remote-Zertifikaten).

**Cache-Wartung:**

- Veraltete Auto-Route-Einträge (alte netzwerk-ID-getaggte Domains wie `service-3200.rediacc.io`) werden bei jedem Pull bereinigt.
- Zertifikate, deren `notAfter` mehr als 7 Tage in der Vergangenheit liegt, werden vollständig entfernt. Sie sind inert und blähen nur den Cache auf.
- `rdc config cert-cache clear` löscht alles; `rdc config cert-cache status` zeigt das Inventar.

**Fehlerbehebung:** Wenn `traefik-certs-dumper` mit `/traefik/acme.json: no such file or directory` abstürzt, kann der Pro-Repo-Daemon den letsencrypt-Speicher des Hosts nicht sehen. Überprüfen Sie (a), ob `/opt/rediacc/proxy/letsencrypt/acme.json` auf dem Host existiert (dies liegt in der Verantwortung des host-level `rediacc-proxy`), und (b), ob der Pro-Repo-Daemon mit einem ausreichend neuen renet gestartet wurde, das `/opt/rediacc/proxy` auf die Positivliste setzt. Führen Sie nach dem Upgrade von renet `rdc repo up` aus, um dies anzuwenden.

> **Experimentell:** Die automatische Sync-Kadenz und ablaufbasierte Bereinigung wurden in renet 0.9+ eingeführt. Ältere CLI/renet-Versionen verwenden ausschließlich manuelle Synchronisierung via `rdc config cert-cache pull`.

## TCP/UDP-Portweiterleitung

Für Nicht-HTTP-Protokolle (Mailserver, DNS, extern bereitgestellte Datenbanken) verwenden Sie TCP/UDP-Portweiterleitung.

### Schritt 1: Ports registrieren

Fügen Sie die erforderlichen Ports bei der Infrastruktur-Konfiguration hinzu:

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

Dies erstellt Traefik-Einstiegspunkte namens `tcp-{port}` und `udp-{port}`.

> Nach dem Hinzufügen oder Entfernen von Ports führen Sie immer `rdc config infra push` erneut aus, um die Proxy-Konfiguration zu aktualisieren.

### Schritt 2: TCP/UDP-Labels hinzufügen

Verwenden Sie `traefik.tcp.*`- oder `traefik.udp.*`-Labels in Ihrer Compose-Datei:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (Port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (Port 993), TLS-Passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Wichtige Konzepte:
- **`HostSNI(\`*\`)`** stimmt mit jedem Hostnamen überein (für Protokolle, die kein SNI senden, wie unverschlüsseltes SMTP)
- **`tls.passthrough=true`** bedeutet, dass Traefik die rohe TLS-Verbindung weiterleitet, ohne zu entschlüsseln, die Anwendung übernimmt die TLS-Verarbeitung selbst
- Einstiegspunkt-Namen folgen der Konvention `tcp-{port}` oder `udp-{port}`

### Einfaches TCP-Beispiel (Datenbank)

Um eine Datenbank extern ohne TLS-Passthrough bereitzustellen (Traefik leitet rohes TCP weiter):

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Port 5432 ist vorkonfiguriert (siehe unten), sodass kein `--tcp-ports`-Setup erforderlich ist.

> **Sicherheitshinweis:** Eine Datenbank im Internet zu exponieren ist ein Risiko. Verwenden Sie dies nur, wenn Remote-Clients direkten Zugriff benötigen. Für die meisten Setups halten Sie die Datenbank intern und verbinden Sie sich über Ihre Anwendung.

### Vorkonfigurierte Ports

Die folgenden TCP/UDP-Ports haben standardmäßig Einstiegspunkte (kein Hinzufügen über `--tcp-ports` erforderlich). Einstiegspunkte werden nur für konfigurierte Adressfamilien generiert, IPv4-Einstiegspunkte erfordern `--public-ipv4`, IPv6-Einstiegspunkte erfordern `--public-ipv6`:

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
| 10000-10010 | TCP | Dynamischer Bereich (automatische Zuordnung) |

## DNS-Konfiguration

### Automatisches DNS (Cloudflare)

Wenn `--cf-dns-token` konfiguriert ist, erstellt `rdc config infra push` automatisch die erforderlichen DNS-Einträge in Cloudflare:

| Eintrag | Typ | Inhalt | Erstellt von |
|---------|-----|--------|-------------|
| `server-1.example.com` | A / AAAA | Öffentliche IP der Maschine | `push-infra` |
| `*.server-1.example.com` | A / AAAA | Öffentliche IP der Maschine | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | Öffentliche IP der Maschine | `repo up` |

Maschinen-Einträge werden von `push-infra` erstellt und decken Routen mit benutzerdefinierten Domains (`rediacc.domain`) ab. Pro-Repository-Wildcard-Einträge werden automatisch von `repo up` erstellt und decken Auto-Routen für dieses Repository ab.

Dies ist idempotent, bestehende Einträge werden aktualisiert, wenn sich die IP ändert, und bleiben unverändert, wenn sie bereits korrekt sind.

Der Basis-Domain-Wildcard (`*.example.com`) muss manuell erstellt werden, wenn Sie benutzerdefinierte Domain-Labels wie `rediacc.domain=erp` verwenden.

### Manuelles DNS

Wenn Sie Cloudflare nicht verwenden oder DNS manuell verwalten, erstellen Sie A- (IPv4) und/oder AAAA- (IPv6) Einträge:

```
# Maschinen-Subdomain (für Routen mit benutzerdefinierter Domain wie rediacc.domain=erp)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# Pro-Repository-Wildcards (für Auto-Routen wie myapp.marketing.server-1.example.com)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# Basis-Domain-Wildcard (für Dienste mit benutzerdefinierter Domain wie rediacc.domain=erp)
*.example.com                  A     203.0.113.50
```

Mit konfiguriertem Cloudflare DNS werden Pro-Repository-Wildcard-Einträge automatisch von `repo up` erstellt. Bei mehreren Maschinen erhält jede Maschine ihre eigenen DNS-Einträge, die auf ihre eigene IP verweisen.

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
| 502 Bad Gateway | Anwendung lauscht nicht auf dem deklarierten Port | Überprüfen, ob die App läuft und der Port mit `loadbalancer.server.port` übereinstimmt |
| TCP-Port nicht erreichbar | Port nicht in der Infrastruktur registriert | `rdc config infra set --tcp-ports ...` und `push-infra` ausführen |
| Route Server verwendet alte Version | Binary wurde aktualisiert, aber Dienst nicht neu gestartet | Passiert automatisch bei der Bereitstellung; manuell: `sudo systemctl restart rediacc-router` |
| STUN/TURN-Relay nicht erreichbar | Relay-Adressen beim Start zwischengespeichert | Dienst nach DNS- oder IP-Änderungen neu erstellen, damit er die neue Netzwerkkonfiguration übernimmt |

## Vollständiges Beispiel

Dieses Beispiel stellt eine Webanwendung mit einer PostgreSQL-Datenbank bereit. Die App ist öffentlich unter `app.example.com` mit TLS erreichbar; die Datenbank ist nur intern verfügbar.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
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
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # Keine Traefik-Labels, nur intern
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
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
rdc repo up --name my-app -m server-1
```

Innerhalb weniger Sekunden erkennt der Route Server den Container, Traefik übernimmt die Route, fordert ein TLS-Zertifikat an, und `https://app.example.com` ist live.
