---
title: Red
description: >-
  Exponga servicios con el proxy inverso, etiquetas Docker, certificados TLS,
  DNS y redirección de puertos TCP/UDP.
category: Guides
order: 6
language: es
sourceHash: 47ee41d44be935a8
---

# Red

Esta página explica cómo los servicios ejecutándose dentro de daemons Docker aislados se hacen accesibles desde internet. Cubre el sistema de proxy inverso, las etiquetas Docker para enrutamiento, los certificados TLS, el DNS y la redirección de puertos TCP/UDP.

Para saber cómo los servicios obtienen sus IPs de loopback y el sistema de slots de `.rediacc.json`, consulte [Servicios](/es/docs/services#red-de-servicios-rediaccjson).

## Cómo Funciona

Rediacc utiliza un sistema de proxy de dos componentes para enrutar tráfico externo a los contenedores:

1. **Servidor de rutas** -- un servicio systemd que descubre contenedores en ejecución en todos los daemons Docker de los repositorios. Inspecciona las etiquetas de los contenedores y genera la configuración de enrutamiento, servida como un endpoint YAML.
2. **Traefik** -- un proxy inverso que consulta el servidor de rutas cada 5 segundos y aplica las rutas descubiertas. Gestiona el enrutamiento HTTP/HTTPS, la terminación TLS y la redirección TCP/UDP.

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

Cuando agrega las etiquetas correctas a un contenedor y lo inicia con `renet compose`, automáticamente se vuelve enrutable -- no se necesita configuración manual del proxy.

> El binario del servidor de rutas se mantiene sincronizado con la versión de su CLI. Cuando la CLI actualiza el binario renet en una máquina, el servidor de rutas se reinicia automáticamente (~1–2 segundos). Esto no causa tiempo de inactividad — Traefik continúa sirviendo tráfico con su última configuración conocida durante el reinicio y recoge la nueva configuración en la siguiente consulta. Las conexiones de clientes existentes no se ven afectadas. Los contenedores de su aplicación no se tocan.

## Etiquetas Docker

El enrutamiento se controla mediante etiquetas de contenedores Docker. Hay dos niveles:

### Nivel 1: Etiquetas `rediacc.*` (Automáticas)

Estas etiquetas son **inyectadas automáticamente** por `renet compose` al iniciar servicios. No necesita agregarlas manualmente.

| Etiqueta | Descripción | Ejemplo |
|----------|-------------|---------|
| `rediacc.service_name` | Identidad del servicio | `myapp` |
| `rediacc.service_ip` | IP de loopback asignada | `127.0.11.2` |
| `rediacc.network_id` | ID del daemon del repositorio | `2816` |
| `rediacc.tcp_ports` | Puertos TCP en los que escucha el servicio | `8080,8443` |
| `rediacc.udp_ports` | Puertos UDP en los que escucha el servicio | `53` |

Cuando un contenedor tiene solo etiquetas `rediacc.*` (sin `traefik.enable=true`), el servidor de rutas genera una **ruta automática**:

```
{service}-{networkID}.{baseDomain}
```

Por ejemplo, un servicio llamado `myapp` en un repositorio con ID de red `2816` y dominio base `example.com` obtiene:

```
myapp-2816.example.com
```

Las rutas automáticas son útiles para desarrollo y acceso interno. Para servicios en producción con dominios personalizados, use etiquetas de Nivel 2.

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

1. Infraestructura configurada en la máquina ([Configuración de Máquinas -- Configuración de Infraestructura](/es/docs/setup#configuración-de-infraestructura)):

   ```bash
   rdc context set-infra server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   rdc context push-infra server-1
   ```

2. Registros DNS apuntando su dominio a la IP pública del servidor (consulte [Configuración de DNS](#configuración-de-dns) más abajo).

### Agregar Etiquetas

Agregue etiquetas `traefik.*` a los servicios que desea exponer en su `docker-compose.yml`:

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
    # Sin etiquetas traefik — la base de datos es solo interna
```

| Etiqueta | Propósito |
|----------|-----------|
| `traefik.enable=true` | Habilita el enrutamiento personalizado de Traefik para este contenedor |
| `traefik.http.routers.{name}.rule` | Regla de enrutamiento -- típicamente `Host(\`dominio\`)` |
| `traefik.http.routers.{name}.entrypoints` | En qué puertos escuchar: `websecure` (HTTPS IPv4), `websecure-v6` (HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | Resolvedor de certificados -- use `letsencrypt` para Let's Encrypt automático |
| `traefik.http.services.{name}.loadbalancer.server.port` | El puerto en el que su aplicación escucha dentro del contenedor |

El `{name}` en las etiquetas es un identificador arbitrario -- solo necesita ser consistente entre las etiquetas de router/servicio/middleware relacionadas.

> **Nota:** Las etiquetas `rediacc.*` (`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`) se inyectan automáticamente por `renet compose`. No necesita agregarlas a su archivo compose.

## Certificados TLS

Los certificados TLS se obtienen automáticamente vía Let's Encrypt usando el desafío DNS-01 de Cloudflare. Esto se configura una vez durante la configuración de infraestructura:

```bash
rdc context set-infra server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

Cuando un servicio tiene `traefik.http.routers.{name}.tls.certresolver=letsencrypt`, Traefik automáticamente:
1. Solicita un certificado de Let's Encrypt
2. Valida la propiedad del dominio vía DNS de Cloudflare
3. Almacena el certificado localmente
4. Lo renueva antes de su vencimiento

El token de la API DNS de Cloudflare necesita el permiso `Zone:DNS:Edit` para los dominios que desea asegurar. Este enfoque funciona para cualquier dominio gestionado por Cloudflare, incluyendo certificados comodín.

## Redirección de Puertos TCP/UDP

Para protocolos no HTTP (servidores de correo, DNS, bases de datos expuestas externamente), use la redirección de puertos TCP/UDP.

### Paso 1: Registrar Puertos

Agregue los puertos requeridos durante la configuración de infraestructura:

```bash
rdc context set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc context push-infra server-1
```

Esto crea puntos de entrada de Traefik llamados `tcp-{port}` y `udp-{port}`.

### Ejemplo de TCP Plano (Base de Datos)

Para exponer una base de datos externamente sin paso directo de TLS (Traefik redirige TCP sin procesar):

```yaml
services:
  postgres:
    image: postgres:17
    network_mode: host
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

El puerto 5432 está preconfigurado (ver abajo), por lo que no se necesita configuración con `--tcp-ports`.

> **Nota de seguridad:** Exponer una base de datos a internet es un riesgo. Use esto solo cuando los clientes remotos necesiten acceso directo. Para la mayoría de las configuraciones, mantenga la base de datos interna y conéctese a través de su aplicación.

> Después de agregar o eliminar puertos, siempre vuelva a ejecutar `rdc context push-infra` para actualizar la configuración del proxy.

### Paso 2: Agregar Etiquetas TCP/UDP

Use etiquetas `traefik.tcp.*` o `traefik.udp.*` en su archivo compose:

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    network_mode: host
    labels:
      - "traefik.enable=true"

      # SMTP (puerto 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (puerto 993) — paso directo de TLS
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

Conceptos clave:
- **`HostSNI(\`*\`)`** coincide con cualquier nombre de host (para protocolos que no envían SNI, como SMTP sin cifrar)
- **`tls.passthrough=true`** significa que Traefik redirige la conexión TLS sin descifrar -- la aplicación gestiona TLS por sí misma
- Los nombres de los puntos de entrada siguen la convención `tcp-{port}` o `udp-{port}`

### Puertos Preconfigurados

Los siguientes puertos TCP/UDP tienen puntos de entrada por defecto (no es necesario agregarlos vía `--tcp-ports`):

| Puerto | Protocolo | Uso Común |
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
| 10000--10010 | TCP | Rango dinámico (asignación automática) |

## Configuración de DNS

Apunte sus dominios a las direcciones IP públicas del servidor configuradas en `set-infra`:

### Dominios Individuales de Servicio

Cree registros A (IPv4) y/o AAAA (IPv6) para cada servicio:

```
app.example.com      A     203.0.113.50
app.example.com      AAAA  2001:db8::1
gitlab.example.com   A     203.0.113.50
mail.example.com     A     203.0.113.50
```

### Comodín para Rutas Automáticas

Si usa rutas automáticas (Nivel 1), cree un registro DNS comodín:

```
*.example.com   A     203.0.113.50
*.example.com   AAAA  2001:db8::1
```

Esto enruta todos los subdominios a su servidor, y Traefik los hace coincidir con el servicio correcto basándose en la regla `Host()` o el nombre de host de la ruta automática.

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

### Múltiples Middlewares

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
| 502 Bad Gateway | La aplicación no escucha en el puerto declarado | Verifique que la aplicación se vincule a su `{SERVICE}_IP` y que el puerto coincida con `loadbalancer.server.port` |
| Puerto TCP no alcanzable | Puerto no registrado en la infraestructura | Ejecute `rdc context set-infra --tcp-ports ...` y `push-infra` |
| Servidor de rutas con versión antigua | El binario se actualizó pero el servicio no se reinició | Ocurre automáticamente al aprovisionar; manual: `sudo systemctl restart rediacc-router` |
| Relay STUN/TURN no alcanzable | Direcciones de relay cacheadas al inicio | Recree el servicio después de cambios de DNS o IP para que recoja la nueva configuración de red |

## Ejemplo Completo

Este ejemplo despliega una aplicación web con una base de datos PostgreSQL. La aplicación es accesible públicamente en `app.example.com` con TLS; la base de datos es solo interna.

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
    # Sin etiquetas traefik — solo interno
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

Cree un registro A apuntando `app.example.com` a la IP pública de su servidor:

```
app.example.com   A   203.0.113.50
```

### Desplegar

```bash
rdc repo up my-app -m server-1 --mount
```

En pocos segundos, el servidor de rutas descubre el contenedor, Traefik recoge la ruta, solicita un certificado TLS y `https://app.example.com` está activo.
