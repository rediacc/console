---
title: "Inicio Automático y Recuperación"
description: "Cómo funciona el inicio automático, el reconciliador periódico que recupera repositorios que se caen después del arranque, y cómo inspeccionar el estado de recuperación."
category: "Guides"
order: 5
language: es
sourceHash: "00a1796a0b0d20da"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Inicio Automático y Recuperación

Los repositorios con inicio automático habilitado se inician solos en el arranque. Si uno se cae después, el reconciliador periódico lo vuelve a poner en marcha. Sin avisos. Sin reinicio manual.

Para saber cómo habilitar o deshabilitar el inicio automático en un repositorio, consulte [Servicios: Inicio automático en el arranque](/es/docs/services#autostart-on-boot).

## Cómo funciona el inicio automático

Cuando habilita el inicio automático para un repositorio, Rediacc genera un archivo de clave LUKS aleatorio de 256 bytes y lo añade al slot LUKS 1 del volumen cifrado. El archivo de clave se almacena en:

```
{datastore}/.credentials/keys/{guid}.key
```

Esto permite que la máquina monte el repositorio sin solicitar la frase de contraseña. El slot LUKS 0 (su frase de contraseña) no se modifica.

Al arrancar, un servicio systemd de un solo disparo llamado `rediacc-autostart.service` lee la lista de repositorios con inicio automático habilitado, monta cada uno usando su archivo de clave, inicia el Docker daemon por repositorio, y ejecuta el hook `up()` del Rediaccfile. Al apagar, el servicio ejecuta `down()`, detiene Docker y cierra los volúmenes LUKS.

> **Nota de seguridad:** El archivo de clave otorga acceso root al repositorio sin la frase de contraseña. Cualquier persona con acceso root al servidor puede montar los repositorios con inicio automático habilitado. Evalúe esto según su modelo de amenazas antes de habilitar el inicio automático en repositorios sensibles.

## La brecha de recuperación

El inicio automático en el arranque se ejecuta exactamente una vez por arranque. El watchdog del router, que se ejecuta de forma continua después de eso, solo reinicia *contenedores dentro de un repositorio ya en ejecución con un Docker daemon activo*. No puede volver a montar un volumen LUKS ni reiniciar un Docker daemon por red que se haya detenido.

Esto significa que si el volumen LUKS de un repositorio se desmonta o su Docker daemon se detiene después de que el servidor ha arrancado, ni el servicio de arranque ni el watchdog lo recuperarán. Antes de que existiera el reconciliador, un repositorio en este estado permanecía caído hasta que un operador intervenía.

## Reconciliador periódico

El timer systemd `rediacc-autostart-reconcile.timer` se activa aproximadamente cada 3 minutos y ejecuta `renet repository reconcile`. Para cada repositorio con inicio automático habilitado, el reconciliador comprueba tres cosas:

1. ¿Está montado el volumen LUKS?
2. ¿Está en ejecución el Docker daemon por red?
3. ¿Están activos los servicios del repositorio?

Si alguna comprobación falla, el reconciliador recupera el repositorio usando su archivo de clave: monta el volumen, inicia el Docker daemon y ejecuta `up()`. No se requiere frase de contraseña.

Los repositorios que están sanos, actualmente en uso por una ejecución de respaldo en frío, o dentro de su ventana de back-off son omitidos.

### Back-off y marcadores de fallo persistentes

Un repositorio que falla en la recuperación no reintenta de inmediato en cada ciclo. El reconciliador utiliza back-off exponencial:

| Número de fallos | Espera antes del siguiente intento |
|------------------|------------------------------------|
| 1 | 1 minuto |
| 2 | 2 minutos |
| 3 | 5 minutos |
| 4 | 15 minutos |
| 5+ | 30 minutos, luego 60 minutos |

Tras 5 fallos consecutivos, el reconciliador escribe un archivo marcador duradero en:

```
/var/lib/rediacc/reconcile/failed/{guid}
```

Este archivo sobrevive a la rotación de registros. Su presencia significa que el repositorio requiere la atención de un operador. El reconciliador registra el fallo a nivel de error y deja de intentar la recuperación automática para ese repositorio hasta que el marcador se elimine.

Causas comunes de fallo de recuperación persistente:

- **Licencia de repositorio no confiable o expirada**: la comprobación de licencia se ejecuta antes de `up()`.
- **Archivo de clave faltante**: si el archivo de clave en `{datastore}/.credentials/keys/{guid}.key` fue eliminado, el reconciliador no puede montar el volumen sin una frase de contraseña.
- **Rediaccfile defectuoso**: un error de sintaxis o un hook `up()` que siempre termina con código no cero.

### Relación con el watchdog del router

El reconciliador y el watchdog del router manejan diferentes niveles de fallo y están diseñados para complementarse:

| Capa | Lo que gestiona |
|------|----------------|
| **Watchdog del router** | Reinicios a nivel de contenedor dentro de un repositorio en ejecución, montado, con un Docker daemon activo |
| **Reconciliador (`rediacc-autostart-reconcile.timer`)** | Recuperación a nivel de repositorio: volver a montar LUKS, reiniciar el Docker daemon, volver a ejecutar `up()` |

Si un solo contenedor falla dentro de un repositorio sano, el watchdog lo gestiona. Si el daemon completo del repositorio se detiene, el reconciliador lo gestiona.

## Inspeccionar el estado de recuperación

### Estado del timer y del servicio

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### Registros del reconciliador

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### Marcadores de fallo persistentes

Listar repositorios con marcadores de fallo duraderos:

```bash
ls /var/lib/rediacc/reconcile/failed/
```

Cada nombre de archivo es un GUID de repositorio. Crúcelo con `rdc config repository list` para asociar GUIDs a nombres de repositorios.

Para eliminar un marcador después de haber resuelto el problema subyacente, elimine el archivo:

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

El reconciliador intentará la recuperación de nuevo en el siguiente tick del timer.

## Páginas relacionadas

- [Servicios: Inicio automático en el arranque](/es/docs/services#autostart-on-boot): habilitar y deshabilitar el inicio automático, gestión del archivo de clave
- [Respaldo y Restauración](/es/docs/backup-restore): interacción del respaldo en frío con los servicios en ejecución
