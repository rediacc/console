---
title: "Reglas de Rediacc"
description: "Información esencial sobre reglas y convenciones para crear aplicaciones en la plataforma Rediacc. Cubre Rediaccfile, compose, configuración de red, almacenamiento, CRIU e implementación."
category: "Guides"
order: 5
language: es
sourceHash: "9d81373c26d93457"
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
---

# Reglas de Rediacc

Cada repositorio de Rediacc se ejecuta dentro de un entorno aislado con su propio daemon Docker, volumen LUKS cifrado y rango de IP dedicado. Estas reglas aseguran que tu aplicación funcione correctamente dentro de esta arquitectura.

## Rediaccfile

- **Cada repositorio necesita un Rediaccfile** — un script bash con funciones de ciclo de vida.
- **Funciones del ciclo de vida**: `up()`, `down()`. Opcional: `info()`.
- `up()` inicia tus servicios. `down()` los detiene.
- `info()` proporciona información de estado (estado de contenedores, logs recientes, salud).
- Rediaccfile es cargado (sourced) por renet — tiene acceso a variables de shell, no solo a variables de entorno.

### Variables de entorno disponibles en Rediaccfile

| Variable | Ejemplo | Descripción |
|----------|---------|-------------|
| `REPOSITORY_PATH` | `/mnt/rediacc/mounts/abc123/` | Ruta raíz del repo montado |
| `REPOSITORY_NETWORK_ID` | `6336` | Identificador de aislamiento de red |
| `REPOSITORY_NAME` | `abc123-...` | GUID del repositorio |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | IP de loopback por servicio (nombre del servicio en mayúsculas) |

### Rediaccfile mínimo

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **Usa `renet compose`, nunca `docker compose`** — renet inyecta aislamiento de red, red de host, IPs de loopback y etiquetas de servicio.
- **NO establezcas `network_mode`** en tu archivo compose — renet fuerza `network_mode: host` en todos los servicios. Cualquier valor que establezcas será sobrescrito.
- **NO establezcas etiquetas `rediacc.*`** — renet auto-inyecta `rediacc.network_id`, `rediacc.service_ip` y `rediacc.service_name`.
- **Los mapeos de `ports:` se ignoran** en modo de red de host. Usa la etiqueta `rediacc.service_port` para enrutar el proxy a puertos que no sean el 80.
- **NO uses `restart: always` ni `restart: unless-stopped`** — estos entran en conflicto con checkpoint/restore de CRIU. Usa `restart: on-failure` u omítelo.
- **NO uses volúmenes nombrados de Docker** — residen fuera del repo cifrado y no se incluirán en respaldos ni forks.

### Variables de entorno dentro de los contenedores

Renet auto-inyecta estas en cada contenedor:

| Variable | Descripción |
|----------|-------------|
| `SERVICE_IP` | IP de loopback dedicada de este contenedor |
| `REPOSITORY_NETWORK_ID` | ID de aislamiento de red |

### Nombres de servicios y enrutamiento

- El **nombre del servicio** en compose se convierte en el prefijo URL de la ruta automática.
- Ejemplo: el servicio `myapp` con networkId 6336 y dominio base `example.com` se convierte en `https://myapp-6336.example.com`.
- Para dominios personalizados, usa etiquetas de Traefik (nota: los dominios personalizados NO son compatibles con forks).

## Redes

- **Cada repositorio tiene su propio daemon Docker** en `/var/run/rediacc/docker-<networkId>.sock`.
- **Cada servicio recibe una IP de loopback única** dentro de una subred /26 (ej. `127.0.24.192/26`).
- **Enlázate a `SERVICE_IP`**, no a `0.0.0.0` — la red de host significa que `0.0.0.0` entraría en conflicto con otros repos.
- **Comunicación entre servicios**: Usa IPs de loopback o la variable de entorno `SERVICE_IP`. Los nombres DNS de Docker NO funcionan en modo host.
- **Los conflictos de puertos son imposibles** entre repositorios — cada uno tiene su propio daemon Docker y rango de IP.
- **Reenvío de puertos TCP/UDP**: Agrega etiquetas para exponer puertos no HTTP:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Almacenamiento

- **Todos los datos persistentes deben usar bind mounts con `${REPOSITORY_PATH}/...`.**
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data
    - ${REPOSITORY_PATH}/config:/etc/myapp
  ```
- Los volúmenes nombrados de Docker residen fuera del repo LUKS — **no están cifrados**, **no tienen respaldo** y **no se incluyen en forks**.
- El volumen LUKS se monta en `/mnt/rediacc/mounts/<guid>/`.
- Las instantáneas BTRFS capturan todo el archivo de respaldo LUKS, incluyendo todos los datos montados con bind.

## CRIU (Migración en vivo)

- **`backup push --checkpoint`** captura la memoria de procesos en ejecución + estado del disco.
- **`repo up --mount --checkpoint`** restaura contenedores desde el checkpoint (sin inicio limpio).
- **Las conexiones TCP se vuelven obsoletas después de la restauración** — las aplicaciones deben manejar `ECONNRESET` y reconectarse.
- **El modo experimental de Docker** se habilita automáticamente en los daemons por repositorio.
- **CRIU se instala** durante `rdc config machine setup`.
- **`/etc/criu/runc.conf`** se configura con `tcp-established` para la preservación de conexiones TCP.
- **Los ajustes de seguridad de contenedores son auto-inyectados por renet** — `renet compose` agrega automáticamente lo siguiente a cada contenedor para compatibilidad con CRIU:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (conjunto mínimo para CRIU en kernel 5.9+)
  - `security_opt`: `apparmor=unconfined` (el soporte de AppArmor de CRIU aún no es estable upstream)
  - `userns_mode: host` (CRIU requiere acceso al namespace init para `/proc/pid/map_files`)
- El perfil seccomp predeterminado de Docker se preserva — CRIU usa `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+) para suspender temporalmente los filtros durante checkpoint/restore.
- **NO establezcas estos manualmente** en tu archivo compose — renet se encarga. Establecerlos tú mismo arriesga duplicados o conflictos.
- Consulta la [plantilla heartbeat](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) para una implementación de referencia compatible con CRIU.

### Patrones de aplicación compatibles con CRIU

- Maneja `ECONNRESET` en todas las conexiones persistentes (pools de base de datos, websockets, colas de mensajes).
- Usa bibliotecas de pool de conexiones que soporten reconexión automática.
- Agrega `process.on("uncaughtException")` como red de seguridad para errores de sockets obsoletos de objetos internos de bibliotecas.
- Evita `restart: always` — interfiere con la restauración de CRIU.
- Evita depender del DNS de Docker — usa IPs de loopback para la comunicación entre servicios.

## Seguridad

- **El cifrado LUKS** es obligatorio para repositorios estándar. Cada repo tiene su propia clave de cifrado.
- **Las credenciales se almacenan en la configuración del CLI** (`~/.config/rediacc/rediacc.json`). Perder la configuración significa perder acceso a los volúmenes cifrados.
- **Nunca hagas commit de credenciales** en el control de versiones. Usa `env_file` y genera secretos en `up()`.
- **Aislamiento de repositorio**: El daemon Docker, la red y el almacenamiento de cada repo están completamente aislados de otros repos en la misma máquina.
- **Aislamiento de agentes**: Los agentes de IA operan en modo solo-fork por defecto; solo pueden modificar repositorios fork, no repositorios grand (originales). Los comandos ejecutados mediante `term_exec` o `rdc term` con contexto de repositorio se aíslan a nivel del kernel mediante Landlock LSM, lo que evita el acceso al sistema de archivos entre repositorios.

## Despliegue

- **`rdc repo up`** ejecuta `up()` en todos los Rediaccfiles.
- **`rdc repo up --mount`** abre primero el volumen LUKS y luego ejecuta el ciclo de vida. Requerido después de `backup push` a una nueva máquina.
- **`rdc repo down`** ejecuta `down()` y detiene el daemon Docker.
- **`rdc repo down --unmount`** también cierra el volumen LUKS (bloquea el almacenamiento cifrado).
- **Forks** (`rdc repo fork`) crean un clon CoW (copy-on-write) con nuevo GUID y networkId. El fork comparte la clave de cifrado del padre.
- **Las rutas del proxy** tardan ~3 segundos en activarse después del despliegue. La advertencia "Proxy is not running" durante `repo up` es informativa en entornos de ops/dev.

## Errores comunes

- Usar `docker compose` en lugar de `renet compose` — los contenedores no obtendrán aislamiento de red.
- Usar `restart: always` — impide la restauración de CRIU e interfiere con `repo down`.
- Usar volúmenes nombrados de Docker — los datos no están cifrados, no tienen respaldo, no se incluyen en forks.
- Enlazarse a `0.0.0.0` — causa conflictos de puertos entre repos en modo de red de host.
- Codificar IPs de forma fija — usa la variable de entorno `SERVICE_IP`; las IPs se asignan dinámicamente por networkId.
- Olvidar `--mount` en el primer despliegue después de `backup push` — el volumen LUKS necesita apertura explícita.
- Usar `rdc term -c` como solución alternativa para comandos fallidos — reporta bugs en su lugar.
