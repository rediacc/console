---
title: "Redes y dominios"
description: "Haz que tu app sea accesible en internet con un dominio, TLS automático y un proxy inverso Traefik."
category: "Tutorials"
subcategory: advanced
order: 9
language: es
sourceHash: "9f72a61ed1ff4cb9"
---

# Redes y dominios

Tu app está en ejecución, pero todavía nadie puede acceder a ella. Este tutorial te consigue un dominio real, TLS automático mediante Let's Encrypt y un proxy Traefik que descubre tus contenedores automáticamente. Necesitas un dominio en Cloudflare y un token de API.

## Ver el tutorial

![Tutorial: Redes y dominios](/assets/tutorials/tutorial-networking.cast)

## Cuatro pasos

![Token, configurar, enviar, desplegar](/img/tutorials/tutorial-networking/slide-1.svg)

1. **Obtén** tu token de API de Cloudflare.
2. **Configura** la infraestructura en `rdc`.
3. **Envíala** a tu servidor.
4. **Despliega** el proxy.

## Paso 1: Token de API de Cloudflare

En tu panel de Cloudflare, ve a **Mi perfil → Tokens de API** y crea un token con permiso **Zone DNS Edit**. Copia el valor del token. Solo lo verás una vez.

## Paso 2: Configurar la infraestructura

Indica a `rdc` tu IP pública, dominio base, correo del certificado y el token:

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

Reemplaza la IP, el dominio, el correo y el token con los tuyos.

`--cert-email` y `--cf-dns-token` se comparten entre todas tus máquinas, así que solo los configuras una vez.

## Paso 3: Enviar al servidor

```bash
time rdc config infra push -m my-server
```

Esto crea los registros DNS en Cloudflare automáticamente y prepara la configuración del proxy en tu servidor.

## Paso 4: Desplegar el proxy

El proxy aún no está en ejecución. Despliégalo desde la plantilla integrada `proxy`, dentro de un pequeño repo llamado `infra`:

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

Listo. Traefik está en ejecución ahora. Tu app es accesible en:

```
myapp.my-app.my-server.yourdomain.com
```

Traefik descubre tus contenedores cada 5 segundos. Los certificados TLS vienen de Let's Encrypt automáticamente. No se necesita configuración manual del proxy.

---

Siguiente: [Modo producción](/en/docs/tutorial-production-mode).
