---
title: "Copia de seguridad y conexión de red"
description: "Configure programaciones de copias de seguridad automatizadas, gestione proveedores de almacenamiento, configure la red de infraestructura y registre puertos de servicio."
category: "Tutorials"
order: 6
language: es
sourceHash: "26db200e730fff43"
---

# Cómo configurar copias de seguridad y redes con Rediacc

Las copias de seguridad automatizadas protegen sus repositorios, y la red de infraestructura expone los servicios al mundo exterior. En este tutorial, configurará programaciones de copias de seguridad con proveedores de almacenamiento, establecerá redes públicas con certificados TLS, registrará puertos de servicio y verificará la configuración. Al finalizar, su máquina estará lista para tráfico de producción.

## Requisitos previos

- La CLI `rdc` instalada con una configuración inicializada
- Una máquina aprovisionada (ver [Tutorial: Configuración de máquina](/es/docs/tutorial-setup))

## Grabación interactiva

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

### Paso 1: Ver almacenamientos actuales

Los proveedores de almacenamiento (S3, B2, Google Drive, etc.) sirven como destinos de copia de seguridad. Verifique qué proveedores están configurados.

```bash
rdc config storages
```

Lista todos los proveedores de almacenamiento configurados importados desde configuraciones de rclone. Si está vacío, agregue primero un proveedor de almacenamiento — vea [Copia de seguridad y restauración](/es/docs/backup-restore).

### Paso 2: Configurar programación de copias

Configure copias de seguridad automatizadas que se ejecutan según una programación cron.

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
```

Puede configurar múltiples destinos con diferentes cronogramas:

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
rdc config backup-strategy set --destination azure-backup --cron "0 6 * * *" --enable
```

Esto programa copias de seguridad diarias a las 2 AM en `my-s3` y a las 6 AM en `azure-backup`. Cada destino tiene su propio cronograma. Los cronogramas se guardan en su configuración y pueden desplegarse en máquinas como temporizadores systemd.

### Paso 3: Ver programación de copias

Verifique que la programación se haya aplicado.

```bash
rdc config backup-strategy show
```

Muestra la configuración actual de copia de seguridad: destino, expresión cron y estado de activación.

### Paso 4: Configurar infraestructura

Para servicios de acceso público, la máquina necesita su IP externa, dominio base y un correo electrónico de certificado para Let's Encrypt TLS.

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Rediacc genera una configuración de proxy inverso Traefik a partir de estos ajustes.

### Paso 5: Agregar puertos TCP/UDP

Si sus servicios necesitan puertos no HTTP (por ejemplo, SMTP, DNS), regístrelos como puntos de entrada de Traefik.

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Esto crea puntos de entrada de Traefik (`tcp-25`, `udp-53`, etc.) que los servicios Docker pueden referenciar mediante etiquetas.

### Paso 6: Ver configuración de infraestructura

Verifique la configuración completa de infraestructura.

```bash
rdc config show-infra server-1
```

Muestra IPs públicas, dominio, correo electrónico de certificado y todos los puertos registrados.

### Paso 7: Desactivar programación de copias

Para detener las copias de seguridad automatizadas sin eliminar la configuración:

```bash
rdc config backup-strategy set --disable
rdc config backup-strategy show
```

La configuración se conserva y puede reactivarse posteriormente con `--enable`.

## Solución de problemas

**"Invalid cron expression"**
El formato cron es `minute hour day month weekday`. Programaciones comunes: `0 2 * * *` (diario 2 AM), `0 */6 * * *` (cada 6 horas), `0 0 * * 0` (semanal domingo medianoche).

**"Storage destination not found"**
El nombre del destino debe coincidir con un proveedor de almacenamiento configurado. Ejecute `rdc config storages` para ver los nombres disponibles. Agregue nuevos proveedores mediante la configuración de rclone.

**"Infrastructure config incomplete" al desplegar**
Los tres campos son obligatorios: `--public-ipv4`, `--base-domain` y `--cert-email`. Ejecute `rdc config show-infra <machine>` para verificar qué campos faltan.

## Próximos pasos

Ha configurado copias de seguridad automatizadas, establecido la red de infraestructura, registrado puertos de servicio y verificado la configuración. Para gestionar copias de seguridad:

- [Copia de seguridad y restauración](/es/docs/backup-restore) — referencia completa para comandos push, pull, list y sync
- [Redes](/es/docs/networking) — etiquetas Docker, certificados TLS, DNS y reenvío TCP/UDP
- [Tutorial: Configuración de máquina](/es/docs/tutorial-setup) — configuración inicial y aprovisionamiento
