---
title: "Configuracion de Maquinas"
description: "Cree un contexto, agregue maquinas, aprovisione servidores y configure la infraestructura."
category: "Guides"
order: 3
language: es
---

# Configuracion de Maquinas

Esta pagina le guia a traves de la configuracion de su primera maquina: crear un contexto, registrar un servidor, aprovisionarlo y opcionalmente configurar la infraestructura para acceso publico.

## Paso 1: Crear un Contexto Local

Un **contexto** es una configuracion con nombre que almacena sus credenciales SSH, definiciones de maquinas y mapeos de repositorios. Piense en el como un espacio de trabajo del proyecto.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Opcion | Requerido | Descripcion |
|--------|-----------|-------------|
| `--ssh-key <path>` | Si | Ruta a su clave privada SSH. La tilde (`~`) se expande automaticamente. |
| `--renet-path <path>` | No | Ruta personalizada al binario renet en las maquinas remotas. Por defecto usa la ubicacion de instalacion estandar. |

Esto crea un contexto local llamado `my-infra` y lo almacena en `~/.rediacc/config.json`.

> Puede tener multiples contextos (por ejemplo, `production`, `staging`, `dev`). Cambie entre ellos con la bandera `--context` en cualquier comando.

## Paso 2: Agregar una Maquina

Registre su servidor remoto como una maquina en el contexto:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Opcion | Requerido | Predeterminado | Descripcion |
|--------|-----------|----------------|-------------|
| `--ip <address>` | Si | - | Direccion IP o nombre de host del servidor remoto. |
| `--user <username>` | Si | - | Nombre de usuario SSH en el servidor remoto. |
| `--port <port>` | No | `22` | Puerto SSH. |
| `--datastore <path>` | No | `/mnt/rediacc` | Ruta en el servidor donde Rediacc almacena los repositorios cifrados. |

Despues de agregar la maquina, rdc ejecuta automaticamente `ssh-keyscan` para obtener las claves del host del servidor. Tambien puede ejecutar esto manualmente:

```bash
rdc context scan-keys server-1
```

Para ver todas las maquinas registradas:

```bash
rdc context machines
```

## Paso 3: Configurar la Maquina

Aprovisione el servidor remoto con todas las dependencias requeridas:

```bash
rdc context setup-machine server-1
```

Este comando:
1. Sube el binario renet al servidor mediante SFTP
2. Instala Docker, containerd y cryptsetup (si no estan presentes)
3. Crea el usuario del sistema `rediacc` (UID 7111)
4. Crea el directorio del datastore y lo prepara para repositorios cifrados

| Opcion | Requerido | Predeterminado | Descripcion |
|--------|-----------|----------------|-------------|
| `--datastore <path>` | No | `/mnt/rediacc` | Directorio del datastore en el servidor. |
| `--datastore-size <size>` | No | `95%` | Cantidad de disco disponible a asignar para el datastore. |
| `--debug` | No | `false` | Habilitar salida detallada para resolucion de problemas. |

> La configuracion solo necesita ejecutarse una vez por maquina. Es seguro volver a ejecutarla si es necesario.

## Gestion de Claves del Host

Si las claves SSH de un servidor cambian (por ejemplo, despues de una reinstalacion), actualice las claves almacenadas:

```bash
rdc context scan-keys server-1
```

Esto actualiza el campo `knownHosts` en su configuracion para esa maquina.

## Probar Conectividad SSH

Verifique que su maquina es alcanzable antes de continuar:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Esto prueba la conexion SSH y reporta:
- Estado de la conexion
- Metodo de autenticacion utilizado
- Configuracion de la clave SSH
- Entrada de hosts conocidos

Puede guardar la clave del host verificada en la configuracion de su maquina con `--save -m server-1`.

## Configuracion de Infraestructura

Para maquinas que necesitan servir trafico publicamente, configure los ajustes de infraestructura:

### Establecer Infraestructura

```bash
rdc context set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Opcion | Descripcion |
|--------|-------------|
| `--public-ipv4 <ip>` | Direccion IPv4 publica para acceso externo |
| `--public-ipv6 <ip>` | Direccion IPv6 publica para acceso externo |
| `--base-domain <domain>` | Dominio base para aplicaciones (por ejemplo, `example.com`) |
| `--cert-email <email>` | Correo electronico para certificados TLS de Let's Encrypt |
| `--cf-dns-token <token>` | Token de la API DNS de Cloudflare para desafios ACME DNS-01 |
| `--tcp-ports <ports>` | Puertos TCP adicionales separados por comas para redirigir (por ejemplo, `25,143,465,587,993`) |
| `--udp-ports <ports>` | Puertos UDP adicionales separados por comas para redirigir (por ejemplo, `53`) |

### Ver Infraestructura

```bash
rdc context show-infra server-1
```

### Enviar al Servidor

Genere y despliegue la configuracion del proxy inverso Traefik en el servidor:

```bash
rdc context push-infra server-1
```

Esto envia la configuracion del proxy basada en sus ajustes de infraestructura. Traefik gestiona la terminacion TLS, el enrutamiento y la redireccion de puertos.

## Establecer Valores Predeterminados

Configure valores predeterminados para no tener que especificarlos en cada comando:

```bash
rdc context set machine server-1    # Maquina predeterminada
rdc context set team my-team        # Equipo predeterminado (modo cloud, experimental)
```

Despues de establecer una maquina predeterminada, puede omitir `-m server-1` en los comandos:

```bash
rdc repo create my-app --size 10G   # Usa la maquina predeterminada
```

## Multiples Contextos

Gestione multiples entornos con contextos con nombre:

```bash
# Crear contextos separados
rdc context create-local production --ssh-key ~/.ssh/id_prod
rdc context create-local staging --ssh-key ~/.ssh/id_staging

# Usar un contexto especifico
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
