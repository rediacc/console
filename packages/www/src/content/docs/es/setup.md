---
title: "Configuración de Máquinas"
description: "Cree un contexto, agregue máquinas, aprovisione servidores y configure la infraestructura."
category: "Guides"
order: 3
language: es
---

# Configuración de Máquinas

Esta página le guía a través de la configuración de su primera máquina: crear un contexto, registrar un servidor, aprovisionarlo y opcionalmente configurar la infraestructura para acceso público.

## Paso 1: Crear un Contexto Local

Un **contexto** es una configuración con nombre que almacena sus credenciales SSH, definiciones de máquinas y mapeos de repositorios. Piense en él como un espacio de trabajo del proyecto.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `--ssh-key <path>` | Sí | Ruta a su clave privada SSH. La tilde (`~`) se expande automáticamente. |
| `--renet-path <path>` | No | Ruta personalizada al binario renet en las máquinas remotas. Por defecto usa la ubicación de instalación estándar. |

Esto crea un contexto local llamado `my-infra` y lo almacena en `~/.rediacc/config.json`.

> Puede tener múltiples contextos (por ejemplo, `production`, `staging`, `dev`). Cambie entre ellos con la bandera `--context` en cualquier comando.

## Paso 2: Agregar una Máquina

Registre su servidor remoto como una máquina en el contexto:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Opción | Requerido | Predeterminado | Descripción |
|--------|-----------|----------------|-------------|
| `--ip <address>` | Sí | - | Dirección IP o nombre de host del servidor remoto. |
| `--user <username>` | Sí | - | Nombre de usuario SSH en el servidor remoto. |
| `--port <port>` | No | `22` | Puerto SSH. |
| `--datastore <path>` | No | `/mnt/rediacc` | Ruta en el servidor donde Rediacc almacena los repositorios cifrados. |

Después de agregar la máquina, rdc ejecuta automáticamente `ssh-keyscan` para obtener las claves del host del servidor. También puede ejecutar esto manualmente:

```bash
rdc context scan-keys server-1
```

Para ver todas las máquinas registradas:

```bash
rdc context machines
```

## Paso 3: Configurar la Máquina

Aprovisione el servidor remoto con todas las dependencias requeridas:

```bash
rdc context setup-machine server-1
```

Este comando:
1. Sube el binario renet al servidor mediante SFTP
2. Instala Docker, containerd y cryptsetup (si no están presentes)
3. Crea el usuario del sistema `rediacc` (UID 7111)
4. Crea el directorio del datastore y lo prepara para repositorios cifrados

| Opción | Requerido | Predeterminado | Descripción |
|--------|-----------|----------------|-------------|
| `--datastore <path>` | No | `/mnt/rediacc` | Directorio del datastore en el servidor. |
| `--datastore-size <size>` | No | `95%` | Cantidad de disco disponible a asignar para el datastore. |
| `--debug` | No | `false` | Habilitar salida detallada para resolución de problemas. |

> La configuración solo necesita ejecutarse una vez por máquina. Es seguro volver a ejecutarla si es necesario.

## Gestión de Claves del Host

Si las claves SSH de un servidor cambian (por ejemplo, después de una reinstalación), actualice las claves almacenadas:

```bash
rdc context scan-keys server-1
```

Esto actualiza el campo `knownHosts` en su configuración para esa máquina.

## Probar Conectividad SSH

Verifique que su máquina es alcanzable antes de continuar:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Esto prueba la conexión SSH y reporta:
- Estado de la conexión
- Método de autenticación utilizado
- Configuración de la clave SSH
- Entrada de hosts conocidos

Puede guardar la clave del host verificada en la configuración de su máquina con `--save -m server-1`.

## Configuración de Infraestructura

Para máquinas que necesitan servir tráfico públicamente, configure los ajustes de infraestructura:

### Establecer Infraestructura

```bash
rdc context set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Opción | Descripción |
|--------|-------------|
| `--public-ipv4 <ip>` | Dirección IPv4 pública para acceso externo |
| `--public-ipv6 <ip>` | Dirección IPv6 pública para acceso externo |
| `--base-domain <domain>` | Dominio base para aplicaciones (por ejemplo, `example.com`) |
| `--cert-email <email>` | Correo electrónico para certificados TLS de Let's Encrypt |
| `--cf-dns-token <token>` | Token de la API DNS de Cloudflare para desafíos ACME DNS-01 |
| `--tcp-ports <ports>` | Puertos TCP adicionales separados por comas para redirigir (por ejemplo, `25,143,465,587,993`) |
| `--udp-ports <ports>` | Puertos UDP adicionales separados por comas para redirigir (por ejemplo, `53`) |

### Ver Infraestructura

```bash
rdc context show-infra server-1
```

### Enviar al Servidor

Genere y despliegue la configuración del proxy inverso Traefik en el servidor:

```bash
rdc context push-infra server-1
```

Esto envía la configuración del proxy basada en sus ajustes de infraestructura. Traefik gestiona la terminación TLS, el enrutamiento y la redirección de puertos.

## Establecer Valores Predeterminados

Configure valores predeterminados para no tener que especificarlos en cada comando:

```bash
rdc context set machine server-1    # Máquina predeterminada
rdc context set team my-team        # Equipo predeterminado (modo cloud, experimental)
```

Después de establecer una máquina predeterminada, puede omitir `-m server-1` en los comandos:

```bash
rdc repo create my-app --size 10G   # Usa la máquina predeterminada
```

## Múltiples Contextos

Gestione múltiples entornos con contextos con nombre:

```bash
# Crear contextos separados
rdc context create-local production --ssh-key ~/.ssh/id_prod
rdc context create-local staging --ssh-key ~/.ssh/id_staging

# Usar un contexto específico
rdc repo list -m server-1 --context production
rdc repo list -m staging-1 --context staging
```

Ver todos los contextos:

```bash
rdc context list
```

Mostrar detalles del contexto actual:

```bash
rdc context show
```
