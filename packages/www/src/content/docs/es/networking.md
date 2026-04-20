---
title: Red
description: >-
  Exponga servicios con el proxy inverso, etiquetas Docker, certificados TLS,
  DNS y redirección de puertos TCP/UDP.
category: Guides
order: 6
language: es
sourceHash: "536db0c93646cad6"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# Red

Esta página explica cómo los servicios ejecutándose dentro de daemons Docker aislados se hacen accesibles desde internet. Cubre el sistema de proxy inverso, las etiquetas Docker para enrutamiento, los certificados TLS, el DNS y la redirección de puertos TCP/UDP.

Para saber cómo los servicios obtienen sus IPs de loopback y el sistema de slots de `.rediacc.json`, consulte [Servicios](/es/docs/services#red-de-servicios-rediaccjson).

## Aislamiento de Red

Cada repositorio se aísla automáticamente a nivel de kernel mediante ganchos de red. Esto requiere Linux kernel 6.1 o posterior. No se necesita configuración.

- **Reescritura automática de bind**: Los servicios pueden vincularse a `0.0.0.0` o `127.0.0.1` como de costumbre. El kernel reescribe de forma transparente la dirección a la IP de loopback asignada al servicio. No es necesario vincularse explícitamente a `${SERVICE_IP}`.
- **Bloqueo de conexiones entre repositorios**: Si un servicio intenta conectarse a una IP de loopback fuera del subred `/26` de su repositorio, el kernel lo bloquea. Un proceso en el repositorio A no puede alcanzar servicios del repositorio B.
- **No se requieren cambios en la aplicación**: Los servicios usan `0.0.0.0` o `localhost` para vincularse, y el kernel garantiza que solo escuchen en su IP de loopback correcta. El aislamiento es completamente transparente.

## Cómo Funciona

Rediacc utiliza un sistema de proxy de dos componentes para enrutar tráfico externo a los contenedores:

1. **Servidor de rutas**, un servicio systemd que descubre contenedores en ejecución en todos los daemons Docker de los repositorios. Inspecciona las etiquetas de los contenedores y genera la configuración de enrutamiento, servida como un endpoint YAML.
2. **Traefik**, un proxy inverso que consulta el servidor de rutas cada 5 segundos y aplica las rutas descubiertas. Gestiona el enrutamiento HTTP/HTTPS, la terminación TLS y la redirección TCP/UDP.

El flujo es el siguiente:

```
Internet → Traefik (puertos 80/443/TCP/UDP)
               ↓ consulta cada 5s
           Servidor de rutas (descubre contenedores)
               ↓ inspecciona etiquetas
           Daemons Docker (/var/run/rediacc/docker-*.sock)
               ↓
           Contenedores (vinculados a IPs loopback 127.x.x.x)
```

Cuando agrega las etiquetas correctas a un contenedor y lo inicia con `renet compose`, automáticamente se vuelve enrutable, no se necesita configuración manual del proxy.

> El binario del servidor de rutas se mantiene sincronizado con la versión de su CLI. Cuando la CLI actualiza el binario renet en una máquina, el servidor de rutas se reinicia automáticamente (~1-2 segundos). Esto no causa tiempo de inactividad, Traefik continúa sirviendo tráfico con su última configuración conocida durante el reinicio y recoge la nueva configuración en la siguiente consulta. Las conexiones de clientes existentes no se ven afectadas. Los contenedores de su aplicación no se tocan.

## Etiquetas Docker

El enrutamiento se controla mediante etiquetas de contenedores Docker. Hay dos niveles:

### Nivel 1: Etiquetas `rediacc.*` (Automáticas)

Estas etiquetas son **inyectadas automáticamente** por `renet compose` al iniciar servicios. No necesita agregarlas manualmente.

| Etiqueta | Descripción | Ejemplo |
|----------|-------------|---------|
| `rediacc.service_name` | Identidad del servicio | `myapp` |
| `rediacc.service_ip` | IP de loopback asignada | `127.0.11.2` |
| `rediacc.network_id` | ID del daemon del repositorio | `2816` |
| `rediacc.repo_name` | Nombre del repositorio | `marketing` |
| `rediacc.tcp_ports` | Puertos TCP en los que escucha el servicio | `8080,8443` |
| `rediacc.udp_ports` | Puertos UDP en los que escucha el servicio | `53` |

Cuando un contenedor tiene solo etiquetas `rediacc.*` (sin `traefik.enable=true`), el servidor de rutas genera una **ruta automática** usando el nombre del repositorio y el subdominio de la máquina:

```
{service}.{repoName}.{machineName}.{baseDomain}
```

Por ejemplo, un servicio llamado `myapp` en un repositorio llamado `marketing` en la máquina `server-1` con dominio base `example.com` obtiene:

```
myapp.marketing.server-1.example.com
```

Para bifurcaciones, el nombre del servicio se combina con la palabra reservada `fork` y la etiqueta:

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

Por ejemplo, una bifurcación de `marketing` etiquetada `staging` obtiene:

```
myapp-fork-staging.marketing.server-1.example.com
```

Cada URL de bifurcación se sitúa bajo el subdominio del repositorio padre y está cubierta por su certificado comodín existente, por lo que no se necesita un nuevo certificado. El separador `-fork-` evita colisiones con nombres de servicios reales en el repositorio de producción. Para servicios con dominios personalizados, use etiquetas de Nivel 2 o la etiqueta `rediacc.domain`.

#### Dominio personalizado via `rediacc.domain`

Puede establecer un dominio personalizado para un servicio usando la etiqueta `rediacc.domain` en su `docker-compose.yml`. Se admiten tanto nombres cortos como dominios completos:

```yaml
labels:
  # Nombre corto, se resuelve a cloud.example.com usando el baseDomain de la máquina
  - "rediacc.domain=cloud"

  # Dominio completo, se usa tal cual
  - "rediacc.domain=cloud.example.com"
```

Un valor sin puntos se trata como nombre corto y se le agrega automáticamente el `baseDomain` de la máquina. Un valor con puntos se usa como dominio completo.

Cuando `machineName` está configurado, los servicios con dominio personalizado obtienen **dos rutas**: una en el dominio base (`cloud.example.com`) y otra en el subdominio de la máquina (`cloud.server-1.example.com`).

### Nivel 2: Etiquetas `traefik.*` (Definidas por el Usuario)

Agregue estas etiquetas a su `docker-compose.yml` cuando desee enrutamiento con dominio personalizado, TLS o puntos de entrada específicos. Configurar `traefik.enable=true` indica al servidor de rutas que use sus reglas personalizadas en lugar de generar una ruta automática.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

Estas usan la [sintaxis estándar de etiquetas de Traefik v3](https://doc.traefik.io/traefik/routing/providers/docker/).

> **Consejo:** Los servicios solo internos (bases de datos, cachés, colas de mensajes) **no** deben tener `traefik.enable=true`. Solo necesitan etiquetas `rediacc.*`, que se inyectan automáticamente.

## Exponer Servicios HTTP/HTTPS

### Requisitos Previos

1. Infraestructura configurada en la máquina ([Configuración de Máquinas, Configuración de Infraestructura](/es/docs/setup#configuración-de-infraestructura)):

   ```bash
   # Credenciales compartidas (una vez por configuración, aplica a todas las máquinas)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # Configuración específica de la máquina
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. Registros DNS apuntando su dominio a la IP pública del servidor (consulte [Configuración de DNS](#configuración-de-dns) más abajo).

### Agregar Etiquetas

Agregue etiquetas `traefik.*` a los servicios que desea exponer en su `docker-compose.yml`:

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
    # Sin etiquetas traefik, la base de datos es solo interna
```

| Etiqueta | Propósito |
|----------|-----------|
| `traefik.enable=true` | Habilita el enrutamiento personalizado de Traefik para este contenedor |
| `traefik.http.routers.{name}.rule` | Regla de enrutamiento, típicamente `Host(\`dominio\`)` |
| `traefik.http.routers.{name}.entrypoints` | En qué puertos escuchar: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Resolvedor de certificados, use `letsencrypt` para Let's Encrypt automático |
| `traefik.http.services.{name}.loadbalancer.server.port` | El puerto en el que su aplicación escucha dentro del contenedor |

El `{name}` en las etiquetas es un identificador arbitrario, solo necesita ser consistente entre las etiquetas de router/servicio/middleware relacionadas.

> **Nota:** Las etiquetas `rediacc.*` (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) se inyectan automáticamente por `renet compose`. No necesita agregarlas a su archivo compose.

## Certificados TLS

Los certificados TLS se obtienen automáticamente vía Let's Encrypt usando el desafío DNS-01 de Cloudflare. Las credenciales se configuran una vez por configuración (compartidas entre todas las máquinas):

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Las rutas automáticas usan **certificados comodín** a nivel del subdominio del repositorio (`*.marketing.server-1.example.com`) en lugar de certificados por servicio. El certificado se provisiona automáticamente por Traefik en el primer `repo up`; no se requiere ningún paso manual. Las bifurcaciones reutilizan el comodín existente del repositorio padre, por lo que nunca desencadenan una nueva solicitud de certificado. Las rutas con dominio personalizado usan comodines a nivel de máquina (`*.server-1.example.com`).

> **Requiere credenciales de Cloudflare.** Los certificados comodín usan el desafío DNS-01. Sin `--cf-dns-token` (y opcionalmente `--cert-email`), Traefik no puede completar el desafío y HTTPS no funcionará. HTTP permanece funcional. Configure las credenciales con `rdc config infra set` antes del primer despliegue.

Para rutas de Nivel 2 con `traefik.http.routers.{name}.tls.certresolver=letsencrypt`, los SANs de dominio comodín se inyectan automáticamente basándose en el nombre de host de la ruta.

El token de la API DNS de Cloudflare necesita el permiso `Zone:DNS:Edit` para los dominios que desea asegurar.

### Ciclo de Vida del Certificado TLS

El camino completo que recorre un certificado Let's Encrypt desde su emisión hasta los contenedores de cada repositorio:

1. **Emisión en el host.** Un contenedor Traefik a nivel de máquina (`rediacc-proxy`, desplegado en `/opt/rediacc/proxy/`) posee la renovación ACME. Almacena todo el estado en `/opt/rediacc/proxy/letsencrypt/acme.json` en el host. La renovación se activa automáticamente unos 30 dias antes de la expiración; no se necesita ninguna acción del operador mientras `--cf-dns-token` esté configurado.

2. **Volcado por repositorio (opcional).** Los servicios que necesitan archivos de certificados dentro de su propio contenedor (por ejemplo, un servidor de correo que lee un `.pem` directamente) despliegan un pequeño contenedor `traefik-certs-dumper` junto a ellos. El volcador monta `/opt/rediacc/proxy/letsencrypt` como solo lectura y escribe el certificado y la clave extraídos en el volumen de datos del repositorio como `cert.pem` / `key.pem`. Para que esto funcione, el daemon Docker por repositorio debe tener `/opt/rediacc/proxy` en su lista de permisos del espacio de nombres de montaje. Esto ya está incluido por defecto.

3. **Cache del lado del cliente (`rediacc.json`).** La CLI almacena en caché una copia comprimida de `acme.json` bajo `acmeCertCache` en su archivo de configuración, indexada por `baseDomain`. Esto permite que varias máquinas compartan certificados (via `rdc config cert-cache push -m <machine>`) y actúa como un inventario sin conexión.

**Disparadores de sincronización para el cache del cliente:**

- Automáticamente después de `rdc repo up`, pero solo si el cache local para el `baseDomain` de la máquina tiene más de 6 horas. Los caches frescos se dejan solos para que los despliegues consecutivos no saturen SSH.
- Bajo demanda: `rdc config cert-cache pull -m <machine>` (forzar extracción) o `rdc machine query --name <machine> --sync-certs` (extracción como efecto secundario de una consulta de estado).
- En `rdc config infra push`, el cache se sube a la máquina (los certificados locales con mayor tiempo de expiración ganan sobre los remotos).

**Mantenimiento del cache:**

- Las entradas de rutas automáticas antiguas (dominios etiquetados con ID de red antiguo como `service-3200.rediacc.io`) se eliminan en cada extracción.
- Los certificados cuyo `notAfter` está más de 7 dias en el pasado se eliminan por completo. Son inertes y solo inflan el cache.
- `rdc config cert-cache clear` borra todo; `rdc config cert-cache status` muestra el inventario.

**Solución de problemas:** si `traefik-certs-dumper` falla con `/traefik/acme.json: no such file or directory`, el daemon del repositorio no puede ver el almacén letsencrypt del host. Verifique (a) que `/opt/rediacc/proxy/letsencrypt/acme.json` existe en el host (esto es responsabilidad del `rediacc-proxy` a nivel de host), y (b) que el daemon del repositorio se inició con una versión de renet suficientemente reciente que incluye `/opt/rediacc/proxy` en la lista de permisos. Vuelva a desplegar el repositorio con `rdc repo up` después de actualizar renet para aplicarlo.

> **Experimental:** La cadencia de sincronización automática y la poda basada en expiración se lanzaron en renet 0.9+. Las versiones anteriores de CLI/renet usan sincronización puramente manual via `rdc config cert-cache pull`.

## Redirección de Puertos TCP/UDP

Para protocolos no HTTP (servidores de correo, DNS, bases de datos expuestas externamente), use la redirección de puertos TCP/UDP.

### Paso 1: Registrar Puertos

Agregue los puertos requeridos durante la configuración de infraestructura:

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

Esto crea puntos de entrada de Traefik llamados `tcp-{port}` y `udp-{port}`.

> Después de agregar o eliminar puertos, siempre vuelva a ejecutar `rdc config infra push` para actualizar la configuración del proxy.

### Paso 2: Agregar Etiquetas TCP/UDP

Use etiquetas `traefik.tcp.*` o `traefik.udp.*` en su archivo compose:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (puerto 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (puerto 993), paso directo de TLS
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Conceptos clave:
- **`HostSNI(\`*\`)`** coincide con cualquier nombre de host (para protocolos que no envían SNI, como SMTP sin cifrar)
- **`tls.passthrough=true`** significa que Traefik redirige la conexión TLS sin descifrar, la aplicación gestiona TLS por si misma
- Los nombres de los puntos de entrada siguen la convención `tcp-{port}` o `udp-{port}`

### Ejemplo de TCP Plano (Base de Datos)

Para exponer una base de datos externamente sin paso directo de TLS (Traefik redirige TCP sin procesar):

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

El puerto 5432 está preconfigurado (ver abajo), por lo que no se necesita configuración con `--tcp-ports`.

> **Nota de seguridad:** Exponer una base de datos a internet es un riesgo. Use esto solo cuando los clientes remotos necesiten acceso directo. Para la mayoria de las configuraciones, mantenga la base de datos interna y conéctese a través de su aplicación.

### Puertos Preconfigurados

Los siguientes puertos TCP/UDP tienen puntos de entrada por defecto (no es necesario agregarlos vía `--tcp-ports`). Los puntos de entrada solo se generan para las familias de direcciones configuradas, los puntos de entrada IPv4 requieren `--public-ipv4`, los puntos de entrada IPv6 requieren `--public-ipv6`:

| Puerto | Protocolo | Uso Comun |
|--------|-----------|-----------|
| 80 | HTTP | Web (redirección automática a HTTPS) |
| 443 | HTTPS | Web (TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000-10010 | TCP | Rango dinámico (asignación automática) |

## Configuración de DNS

### DNS Automático (Cloudflare)

Cuando `--cf-dns-token` está configurado, `rdc config infra push` crea automáticamente los registros DNS necesarios en Cloudflare:

| Registro | Tipo | Contenido | Creado por |
|----------|------|-----------|------------|
| `server-1.example.com` | A / AAAA | IP pública de la máquina | `push-infra` |
| `*.server-1.example.com` | A / AAAA | IP pública de la máquina | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | IP pública de la máquina | `repo up` |

Los registros a nivel de máquina son creados por `push-infra` y cubren las rutas con dominio personalizado (`rediacc.domain`). Los registros comodín por repositorio son creados automáticamente por `repo up` y cubren las rutas automáticas para ese repositorio.

Esto es idempotente, los registros existentes se actualizan si la IP cambia, y se dejan sin cambios si ya son correctos.

El comodín del dominio base (`*.example.com`) debe crearse manualmente si usa etiquetas de dominio personalizadas como `rediacc.domain=erp`.

### DNS Manual

Si no usa Cloudflare o gestiona DNS manualmente, cree registros A (IPv4) y/o AAAA (IPv6):

```
# Subdominio de la máquina (para rutas con dominio personalizado como rediacc.domain=erp)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# Comodines por repositorio (para rutas automáticas como myapp.marketing.server-1.example.com)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# Comodín del dominio base (para servicios con dominio personalizado como rediacc.domain=erp)
*.example.com                  A     203.0.113.50
```

Con Cloudflare DNS configurado, los registros comodín por repositorio son creados automáticamente por `repo up`. Con múltiples máquinas, cada máquina obtiene sus propios registros DNS apuntando a su propia IP.

## Middlewares

Los middlewares de Traefik modifican las solicitudes y respuestas. Aplíquelos mediante etiquetas.

### HSTS (HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### Buffering para Subida de Archivos Grandes

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### Multiples Middlewares

Encadene middlewares separándolos por comas:

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

Para la lista completa de middlewares disponibles, consulte la [documentación de middlewares de Traefik](https://doc.traefik.io/traefik/middlewares/overview/).

## Diagnósticos

Si un servicio no es accesible, conéctese por SSH al servidor y verifique los endpoints del servidor de rutas:

### Verificación de Estado

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

Muestra el estado general, el número de routers y servicios descubiertos, y si las rutas automáticas están habilitadas.

### Rutas Descubiertas

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

Lista todos los routers HTTP, TCP y UDP con sus reglas, puntos de entrada y servicios backend.

### Asignaciones de Puertos

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

Muestra los mapeos de puertos TCP y UDP para puertos asignados dinámicamente.

### Problemas Comunes

| Problema | Causa | Solución |
|----------|-------|----------|
| Servicio no aparece en las rutas | Contenedor no ejecutándose o sin etiquetas | Verifique con `docker ps` en el daemon del repositorio; revise las etiquetas |
| Certificado no emitido | DNS no apunta al servidor o token de Cloudflare inválido | Verifique la resolución DNS; revise los permisos del token de la API de Cloudflare |
| 502 Bad Gateway | La aplicación no escucha en el puerto declarado | Verifique que la aplicación esté en ejecución y que el puerto coincida con `loadbalancer.server.port` |
| Puerto TCP no alcanzable | Puerto no registrado en la infraestructura | Ejecute `rdc config infra set --tcp-ports ...` y `push-infra` |
| Servidor de rutas con versión antigua | El binario se actualizó pero el servicio no se reinició | Ocurre automáticamente al aprovisionar; manual: `sudo systemctl restart rediacc-router` |
| Relay STUN/TURN no alcanzable | Direcciones de relay cacheadas al inicio | Recree el servicio después de cambios de DNS o IP para que recoja la nueva configuración de red |

## Ejemplo Completo

Este ejemplo despliega una aplicación web con una base de datos PostgreSQL. La aplicación es accesible públicamente en `app.example.com` con TLS; la base de datos es solo interna.

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
    # Sin etiquetas traefik, solo interno
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

Cree un registro A apuntando `app.example.com` a la IP pública de su servidor:

```
app.example.com   A   203.0.113.50
```

### Desplegar

```bash
rdc repo up --name my-app -m server-1
```

En pocos segundos, el servidor de rutas descubre el contenedor, Traefik recoge la ruta, solicita un certificado TLS y `https://app.example.com` está activo.
