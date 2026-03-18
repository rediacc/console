---
title: "Reglas de Rediacc"
description: "Información esencial sobre reglas y convenciones para crear aplicaciones en la plataforma Rediacc. Cubre Rediaccfile, compose, configuración de red, almacenamiento, CRIU e implementación."
category: "Guides"
order: 5
language: es
sourceHash: "091701909c0c8d32"
sourceCommit: "ebe4a9b9ea6ace2a0faee3694a632135cd61ef9b"
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
- **Las políticas de reinicio (`restart: always`, `on-failure`, etc.) son seguras de usar** — renet las elimina automáticamente para compatibilidad con CRIU. El watchdog del router recupera automáticamente los contenedores detenidos según la política original guardada en `.rediacc.json`.
- **Los ajustes peligrosos están bloqueados por defecto** — `privileged: true`, `pid: host`, `ipc: host` y bind mounts a rutas del sistema son rechazados. Usa `renet compose --unsafe` para anularlo bajo tu propio riesgo.

### Variables de entorno dentro de los contenedores

Renet auto-inyecta estas en cada contenedor:

| Variable | Descripción |
|----------|-------------|
| `SERVICE_IP` | IP de loopback dedicada de este contenedor |
| `REPOSITORY_NETWORK_ID` | ID de aislamiento de red |

### Nombres de servicios y enrutamiento

- The compose **service name** becomes the auto-route URL prefix.
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}` (e.g., `https://myapp.marketing.server-1.example.com`).
- **Fork repos**: `https://{service}-{tag}.{machine}.{baseDomain}` — uses the machine wildcard cert to avoid Let's Encrypt rate limits.
- For custom domains, use Traefik labels (but note: custom domains are NOT fork-friendly — the domain belongs to the grand repo).

## Redes

- **Cada repositorio tiene su propio daemon Docker** en `/var/run/rediacc/docker-<networkId>.sock`.
- **Cada servicio recibe una IP de loopback única** dentro de una subred /26 (ej. `127.0.24.192/26`).
- **Enlázate a `SERVICE_IP`** — cada servicio obtiene una IP de loopback única.
- **Los health checks deben usar `${SERVICE_IP}`**, no `localhost`. Ejemplo: `healthcheck: test: ["CMD", "curl", "-f", "http://${SERVICE_IP}:8080/health"]`
- **Comunicación entre servicios**: Usa IPs de loopback o la variable de entorno `SERVICE_IP`. Los nombres DNS de Docker NO funcionan en modo host.
- **Los conflictos de puertos son imposibles** entre repositorios — cada uno tiene su propio daemon Docker y rango de IP.
- **Reenvío de puertos TCP/UDP**: Agrega etiquetas para exponer puertos no HTTP:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Almacenamiento

- **Todos los datos Docker se almacenan dentro del repo cifrado** — el `data-root` de Docker está en `{mount}/.rediacc/docker/data` dentro del volumen LUKS. Los volúmenes nombrados, imágenes y capas de contenedores están todos cifrados, respaldados y se forkean automáticamente.
- **Los bind mounts a `${REPOSITORY_PATH}/...` se recomiendan** por claridad, pero los volúmenes nombrados también funcionan de forma segura.
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data        # bind mount (recomendado)
    - pgdata:/var/lib/postgresql/data      # named volume (también seguro)
  ```
- El volumen LUKS se monta en `/mnt/rediacc/mounts/<guid>/`.
- Las instantáneas BTRFS capturan todo el archivo de respaldo LUKS, incluyendo todos los datos montados con bind.
- El datastore es un archivo de pool BTRFS de tamaño fijo en el disco del sistema. Usa `rdc machine query <name> --system` para ver el espacio libre efectivo. Amplía con `rdc datastore resize`.

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
- Las políticas de reinicio son gestionadas automáticamente por renet (eliminadas para CRIU, el watchdog gestiona la recuperación).
- Evita depender del DNS de Docker — usa IPs de loopback para la comunicación entre servicios.

## Seguridad

- **El cifrado LUKS** es obligatorio para repositorios estándar. Cada repo tiene su propia clave de cifrado.
- **Las credenciales se almacenan en la configuración del CLI** (`~/.config/rediacc/rediacc.json`). Perder la configuración significa perder acceso a los volúmenes cifrados.
- **Nunca hagas commit de credenciales** en el control de versiones. Usa `env_file` y genera secretos en `up()`.
- **Aislamiento de repositorio**: El daemon Docker, la red y el almacenamiento de cada repo están completamente aislados de otros repos en la misma máquina.
- **Aislamiento de agentes**: Los agentes de IA operan en modo solo-fork por defecto. Cada repo tiene su propia clave SSH con aplicación de sandbox del lado del servidor (ForceCommand `sandbox-gateway`). Todas las conexiones están en sandbox con Landlock LSM, overlay OverlayFS del home y TMPDIR por repo. El acceso al sistema de archivos entre repos está bloqueado por el kernel.

## Despliegue

- **`rdc repo up`** ejecuta `up()` en todos los Rediaccfiles.
- **`rdc repo up --mount`** abre primero el volumen LUKS y luego ejecuta el ciclo de vida. Requerido después de `backup push` a una nueva máquina.
- **`rdc repo down`** ejecuta `down()` y detiene el daemon Docker.
- **`rdc repo down --unmount`** también cierra el volumen LUKS (bloquea el almacenamiento cifrado).
- **Forks** (`rdc repo fork`) crean un clon CoW (copy-on-write) con nuevo GUID y networkId. El fork comparte la clave de cifrado del padre.
- **Takeover** (`rdc repo takeover <fork> -m <machine>`) reemplaza los datos del repo grand con los datos de un fork. El grand mantiene su identidad (GUID, networkId, dominios, autostart, cadena de backups). Los datos de producción antiguos se conservan como un fork de backup. Úsalo para: probar una actualización en un fork, verificar, luego hacer takeover a producción. Revertir con `rdc repo takeover <backup-fork> -m <machine>`.
- **Las rutas del proxy** tardan ~3 segundos en activarse después del despliegue. La advertencia "Proxy is not running" durante `repo up` es informativa en entornos de ops/dev.

## Errores comunes

- Usar `docker compose` en lugar de `renet compose` — los contenedores no obtendrán aislamiento de red.
- Las políticas de reinicio son seguras — renet las elimina automáticamente y el watchdog gestiona la recuperación.
- Usar `privileged: true` — no es necesario, renet inyecta capacidades CRIU específicas en su lugar.
- No enlazarse a `SERVICE_IP` — causa conflictos de puertos entre repos.
- Codificar IPs de forma fija — usa la variable de entorno `SERVICE_IP`; las IPs se asignan dinámicamente por networkId.
- Olvidar `--mount` en el primer despliegue después de `backup push` — el volumen LUKS necesita apertura explícita.
- Usar `rdc term -c` como solución alternativa para comandos fallidos — reporta bugs en su lugar.
- `repo delete` realiza una limpieza completa incluyendo IPs de loopback y unidades systemd. Ejecuta `rdc machine prune <name>` para limpiar los restos de eliminaciones antiguas.
