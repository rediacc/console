---
title: "Reglas de Rediacc"
description: "Información esencial sobre reglas y convenciones para crear aplicaciones en la plataforma Rediacc. Cubre Rediaccfile, compose, configuración de red, almacenamiento, CRIU e implementación."
category: "Guides"
order: 5
language: es
sourceHash: "4a544ede5461d3a6"
sourceCommit: "5f353240f5e0a7f9a7f7a4139e4096a1c7c97ffd"
---

# Reglas de Rediacc

Cada repositorio de Rediacc se ejecuta dentro de un entorno aislado con su propio daemon Docker, volumen LUKS cifrado y rango de IP dedicado. Estas reglas aseguran que tu aplicación funcione correctamente dentro de esta arquitectura.

## Rediaccfile

- **Cada repositorio necesita un Rediaccfile**, un script bash con funciones de ciclo de vida.
- **Funciones del ciclo de vida**: `up()`, `down()`. Opcional: `info()`.
- `up()` inicia tus servicios. `down()` los detiene.
- `info()` proporciona información de estado (estado de contenedores, logs recientes, salud).
- Rediaccfile es cargado (sourced) por renet, tiene acceso a variables de shell, no solo a variables de entorno.

### Variables de entorno disponibles en Rediaccfile

| Variable | Ejemplo | Descripción |
|----------|---------|-------------|
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | Ruta raíz del repo montado |
| `REDIACC_NETWORK_ID` | `6336` | Identificador de aislamiento de red |
| `REDIACC_REPOSITORY` | `abc123-...` | GUID del repositorio |
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

- **Usa `renet compose`, nunca `docker compose`**, renet inyecta aislamiento de red, red de host, IPs de loopback y etiquetas de servicio.
- **NO establezcas `network_mode`** en tu archivo compose, renet fuerza `network_mode: host` en todos los servicios. Cualquier valor que establezcas será sobrescrito.
- **NO establezcas etiquetas `rediacc.*`**, renet auto-inyecta `rediacc.network_id`, `rediacc.service_ip` y `rediacc.service_name`.
- **Los mapeos de `ports:` se ignoran** en modo de red de host. Añade la etiqueta `rediacc.service_port` para el enrutamiento HTTP (los servicios sin esta etiqueta no obtienen rutas HTTP). Usa las etiquetas `rediacc.tcp_ports`/`rediacc.udp_ports` para el reenvío TCP/UDP.
- **Las políticas de reinicio (`restart: always`, `on-failure`, etc.) son seguras de usar**, renet las elimina automáticamente para compatibilidad con CRIU. El watchdog del router recupera automáticamente los contenedores detenidos según la política original guardada en `.rediacc.json`.
- **Los ajustes peligrosos están bloqueados por defecto**, `privileged: true`, `pid: host`, `ipc: host` y bind mounts a rutas del sistema son rechazados. Usa `renet compose --unsafe` para anularlo bajo tu propio riesgo.

### Variables de entorno dentro de los contenedores

Renet auto-inyecta estas en cada contenedor:

| Variable | Descripción |
|----------|-------------|
| `SERVICE_IP` | IP de loopback dedicada de este contenedor |
| `REDIACC_NETWORK_ID` | ID de aislamiento de red |

### Nombres de servicios y enrutamiento

- El **nombre del servicio** en compose se convierte en el prefijo de la URL de auto-ruta.
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}` (ej.: `https://myapp.marketing.server-1.example.com`).
- **Fork repos**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}` (ej.: `https://myapp-fork-staging.marketing.server-1.example.com`). El separador `-fork-` evita colisiones de URL con los nombres de servicio del grand repo. La URL del fork siempre usa el certificado wildcard existente del repo padre, por lo que no se necesita un nuevo certificado.
- Para dominios personalizados, use etiquetas de Traefik (nota: los dominios personalizados NO son compatibles con fork, el dominio pertenece al grand repo).

## Redes

- **Cada repositorio tiene su propio daemon Docker** en `/var/run/rediacc/docker-<networkId>.sock`.
- **Cada servicio recibe una IP de loopback única** dentro de una subred /26 (ej. `127.0.24.192/26`).
- **El enlace es automático**: Los servicios pueden enlazarse a `0.0.0.0` o `localhost`, el kernel reescribe transparentemente la dirección a la IP de loopback asignada al servicio. El enlace explícito a `${SERVICE_IP}` sigue funcionando pero ya no es necesario.
- **Los health checks pueden usar `localhost`** o `${SERVICE_IP}`. Ejemplo: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **Las conexiones entre repos están bloqueadas por el kernel**: El kernel bloquea automáticamente las conexiones a IPs de loopback fuera de la subred `/26` del repositorio. Un servicio en un repo no puede alcanzar servicios en otro repo.
- **Comunicación entre servicios**: Usa **nombres de servicio** (ej. `db`, `redis`), renet inyecta automáticamente cada nombre de servicio como un nombre de host que resuelve a la IP correcta. Los nombres DNS de Docker NO funcionan en modo host, pero los nombres de servicio vía `/etc/hosts` sí. Evita incrustar `${DB_IP}` o similares en archivos de configuración persistentes (ej. cadenas de conexión almacenadas en una base de datos), si se hace fork, la IP en bruto se arrastra y apunta al repo incorrecto. Los nombres de servicio siempre resuelven correctamente por repo.
- **Los conflictos de puertos son imposibles** entre repositorios, cada uno tiene su propio daemon Docker y rango de IP.
- **Reenvío de puertos TCP/UDP**: Agrega etiquetas para exponer puertos no HTTP:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## Almacenamiento

- **Todos los datos Docker se almacenan dentro del repo cifrado**, el `data-root` de Docker está en `{mount}/.rediacc/docker/data` dentro del volumen LUKS. Los volúmenes nombrados, imágenes y capas de contenedores están todos cifrados, respaldados y se forkean automáticamente.
- **Los bind mounts a `${REDIACC_WORKING_DIR}/...` se recomiendan** por claridad, pero los volúmenes nombrados también funcionan de forma segura.
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # bind mount (recomendado)
    - pgdata:/var/lib/postgresql/data      # named volume (también seguro)
  ```
- El volumen LUKS se monta en `/mnt/rediacc/mounts/<guid>/`.
- Las instantáneas BTRFS capturan todo el archivo de respaldo LUKS, incluyendo todos los datos montados con bind.
- El datastore es un archivo de pool BTRFS de tamaño fijo en el disco del sistema. Usa `rdc machine query --name <name> --system` para ver el espacio libre efectivo. Amplía con `rdc datastore resize`.

## CRIU (Migración en vivo)

- **Activación por etiqueta**: Añada `rediacc.checkpoint=true` a los contenedores que desee checkpointear. Los contenedores sin esta etiqueta (bases de datos, cachés) se inician desde cero y se recuperan mediante sus propios mecanismos (WAL, LDF, AOF).
- **`repo down --checkpoint`** guarda el estado del proceso antes de detenerse, el siguiente `repo up` restaura automáticamente. **Este es el flujo principal en la misma máquina**, verificado y funcional.
- **`backup push --checkpoint`** captura el estado de memoria de procesos en ejecución más el estado del disco para contenedores etiquetados, y después transfiere el volumen a otra máquina. La restauración en la máquina destino se realiza con `repo up`.
- **`repo fork --checkpoint`** captura el estado del proceso antes del fork y CoW-clona el checkpoint junto con el fork. ⚠️ En la misma máquina, el `repo up` posterior sobre el fork **actualmente falla** con `criu failed: type RESTORE errno 0` mientras el padre sigue en ejecución. Se trata de bugs upstream de CRIU [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514). Use `repo down --checkpoint` para guardar y restaurar in situ, o `backup push --checkpoint` para migración entre máquinas.
- **`repo up`** detecta automáticamente datos de checkpoint y restaura si los encuentra. Use `--skip-checkpoint` para forzar un inicio limpio.
- **Restauración con reconocimiento de dependencias**: Usa `depends_on` de compose para iniciar bases de datos primero (esperando a que estén saludables) y después restaurar mediante CRIU los contenedores de aplicación.
- **Las conexiones TCP quedan obsoletas tras la restauración**, las aplicaciones deben gestionar `ECONNRESET` y reconectar. CRIU no preserva el estado de las conexiones TCP activas a través de la restauración en ningún flujo soportado.
- **El modo experimental de Docker** se activa automáticamente en los daemons por repositorio.
- **CRIU se instala** durante `rdc config machine setup`.
- **`/etc/criu/runc.conf`** se configura con `tcp-established` por defecto.
- **La configuración de seguridad se inyecta automáticamente para contenedores etiquetados**, `renet compose` añade lo siguiente a contenedores con `rediacc.checkpoint=true`:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` (conjunto mínimo para CRIU en kernel 5.9+)
  - `security_opt`: `apparmor=unconfined` (el soporte de AppArmor en CRIU aún no es estable)
  - `userns_mode: host` (CRIU requiere acceso al namespace init para `/proc/pid/map_files`)
- Los contenedores sin la etiqueta ejecutan con una postura de seguridad más limpia (sin capabilities extra).
- El perfil seccomp predeterminado de Docker se mantiene, CRIU usa `PTRACE_O_SUSPEND_SECCOMP` (kernel 4.3+) para suspender temporalmente los filtros durante checkpoint/restore.
- **NO configure las capabilities de CRIU manualmente** en su archivo compose, renet se encarga según la etiqueta.
- Consulta la [plantilla heartbeat](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) para una implementación de referencia compatible con CRIU.

### Patrones de aplicación compatibles con CRIU

- Maneja `ECONNRESET` en todas las conexiones persistentes (pools de base de datos, websockets, colas de mensajes).
- Usa bibliotecas de pool de conexiones que soporten reconexión automática.
- Agrega `process.on("uncaughtException")` como red de seguridad para errores de sockets obsoletos de objetos internos de bibliotecas.
- Las políticas de reinicio son gestionadas automáticamente por renet (eliminadas para CRIU, el watchdog gestiona la recuperación).
- Evita depender del DNS de Docker, usa IPs de loopback para la comunicación entre servicios.

## Seguridad

- **El cifrado LUKS** es obligatorio para repositorios estándar. Cada repo tiene su propia clave de cifrado.
- **Las credenciales se almacenan en la configuración del CLI** (`~/.config/rediacc/rediacc.json`). Perder la configuración significa perder acceso a los volúmenes cifrados.
- **Nunca hagas commit de credenciales** en el control de versiones. Usa `env_file` y genera secretos en `up()`.
- **Aislamiento de repositorio**: El daemon Docker, la red y el almacenamiento de cada repo están completamente aislados de otros repos en la misma máquina.
- **Aislamiento de agentes**: Los agentes de IA operan en modo solo-fork por defecto. Cada repo tiene su propia clave SSH con aplicación de sandbox del lado del servidor (ForceCommand `sandbox-gateway`). Todas las conexiones están en sandbox con Landlock LSM, overlay OverlayFS del home y TMPDIR por repo. El acceso al sistema de archivos entre repos está bloqueado por el kernel.
- **`sudo` está deshabilitado dentro del sandbox de un repositorio por diseño.** El aislamiento del sistema de archivos con Landlock exige `NoNewPrivs`, que impide cualquier elevación de privilegios, por lo que `sudo` fallará con `no new privileges flag is set`. El usuario propietario del repo ya cuenta con los permisos necesarios para todo lo que haya dentro del montaje del repo y del socket de Docker. Para operaciones realmente privilegiadas (instalar paquetes del host, ajustar el kernel), ejecútelas fuera del sandbox o desde una función `up()` de un Rediaccfile ejecutada por la ruta de infraestructura.
- **La red bridge de Docker está deshabilitada en cada daemon por repositorio.** El `daemon.json` de cada repo lleva `"bridge": "none"` e `"iptables": false`, por lo que un simple `docker run <imagen>` crea un contenedor con solo una interfaz de loopback y sin conectividad saliente. Esto no es un bug, así es como se impone el aislamiento entre repos: los ganchos eBPF a nivel de kernel que bloquean que un repo alcance las IPs de loopback de otro repo solo se aplican a contenedores que viven en el namespace de red del host. Para servicios de producción use `renet compose`, que inyecta `network_mode: host` automáticamente. Para contenedores ad-hoc en una shell, pase `--network host` explícitamente.

## Despliegue

- **`rdc repo up`** monta automáticamente el volumen LUKS si no está montado, luego ejecuta `up()` en todos los Rediaccfiles.
- **`rdc repo down`** ejecuta `down()` y detiene el daemon Docker.
- **`rdc repo down --unmount`** también cierra el volumen LUKS (bloquea el almacenamiento cifrado).
- **Forks** (`rdc repo fork`) crean un clon CoW (copy-on-write) con un nuevo GUID y networkId, en **tiempo constante independientemente del tamaño del repo**. El reflink de BTRFS duplica los metadatos de la imagen, no los datos, por lo que un repo de 100 GB se forkea en los mismos pocos segundos que un repo de 1 GB. El fork comparte la clave de cifrado del padre.
- **Takeover** (`rdc repo takeover <fork> -m <machine>`) reemplaza los datos del repo grand con los datos de un fork. El grand mantiene su identidad (GUID, networkId, dominios, autostart, cadena de backups). Los datos de producción antiguos se conservan como un fork de backup. Úsalo para: probar una actualización en un fork, verificar, luego hacer takeover a producción. Revertir con `rdc repo takeover <backup-fork> -m <machine>`.
- **Las rutas del proxy** tardan ~3 segundos en activarse después del despliegue. La advertencia "Proxy is not running" durante `repo up` es informativa en entornos de ops/dev.
- **`rdc repo up` y `rdc repo fork --up` imprimen el patrón de URL** al final del despliegue para los servicios etiquetados con `rediacc.service_port`. Reemplaza `{service}` con tu nombre de servicio expuesto para obtener la URL exacta. Los servicios sin `rediacc.service_port` (bases de datos, workers) no obtienen rutas y no se muestran.

## Errores comunes

- Usar `docker compose` en lugar de `renet compose`, los contenedores no obtendrán aislamiento de red.
- Las políticas de reinicio son seguras, renet las elimina automáticamente y el watchdog gestiona la recuperación.
- Usar `privileged: true`, no es necesario, renet inyecta capacidades CRIU específicas en su lugar.
- Codificar IPs en bruto en archivos de configuración persistentes - usa nombres de servicio para las conexiones para mantener la aislación del fork intacta.
- Usar `rdc term connect -c` como solución alternativa para comandos fallidos, reporta bugs en su lugar.
- `repo delete` realiza una limpieza completa incluyendo IPs de loopback y unidades systemd. Ejecuta `rdc machine prune <name>` para limpiar los restos de eliminaciones antiguas.
