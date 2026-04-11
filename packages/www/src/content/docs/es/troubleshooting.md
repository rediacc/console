---
title: "Solución de problemas"
description: "Soluciones para problemas comunes con SSH, configuración, repositorios, servicios y Docker."
category: "Guides"
order: 10
language: es
sourceHash: "756725b9a8fb168f"
sourceCommit: "7874d5e2f0ca1262eb80ee7de79f20320d0ae2d7"
---

# Solución de problemas

Problemas comunes y sus soluciones. En caso de duda, comience con `rdc doctor` para ejecutar una verificación de diagnóstico completa.

## Falla la conexión SSH

- Verifique que puede conectarse manualmente: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Ejecute `rdc config machine scan-keys server-1` para actualizar las claves del host
- Compruebe que el puerto SSH coincida: `--port 22`
- Pruebe con un comando simple: `rdc term connect -m server-1 -c "hostname"`

## Discrepancia de clave del host

Si un servidor fue reinstalado o sus claves SSH cambiaron, verá "host key verification failed":

```bash
rdc config machine scan-keys -m server-1
```

Este comando obtiene claves de host nuevas y actualiza su configuración.

## Falla la configuración de la máquina

- Asegúrese de que el usuario SSH tenga acceso sudo sin contraseña, o configure `NOPASSWD` para los comandos requeridos
- Verifique el espacio en disco disponible en el servidor
- Ejecute con `--debug` para una salida detallada: `rdc config machine setup server-1 --debug`

## Falla la creación de repositorio

- Verifique que la configuración se haya completado: el directorio del almacén de datos debe existir
- Compruebe el espacio en disco del servidor
- Asegúrese de que el binario de renet esté instalado (ejecute la configuración nuevamente si es necesario)

## Los servicios no se inician

- Verifique la sintaxis del Rediaccfile: debe ser Bash válido
- Asegúrese de que su Rediaccfile use `renet compose --` (no `docker compose`)
- Verifique que las imágenes Docker sean accesibles (considere `renet compose -- pull` en `up()`)
- Revise los registros del contenedor usando el socket Docker del repositorio:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

O vea todos los contenedores:

```bash
rdc machine containers server-1
```

## Errores de permiso denegado

- Las operaciones de repositorio requieren root en el servidor (renet se ejecuta mediante `sudo`)
- Verifique que su usuario SSH esté en el grupo `sudo`
- Compruebe que el directorio del almacén de datos tenga los permisos correctos

## Problemas con el socket de Docker

Cada repositorio tiene su propio Docker daemon. Al ejecutar comandos Docker manualmente, debe especificar el socket correcto:

```bash
# Usando rdc term (configurado automáticamente):
rdc term connect -m server-1 -r my-app -c "docker ps"

# O manualmente con el socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Reemplace `2816` con el ID de red de su repositorio (se encuentra en `rediacc.json` o `rdc repo status`).

## `docker run` no tiene red, `apt update` falla, `curl` se queda colgado

Dentro de la shell de un repositorio, ejecutar un contenedor sin `--network host` le da un contenedor aislado con solo una interfaz de loopback, sin DNS y sin conectividad saliente. Comandos como `apt update`, `pip install`, `curl https://...` o cualquier descarga de red fallarán inmediatamente con errores de DNS.

Esto es intencional. El modelo de red de Rediacc es **red de host para cada servicio**, impuesto por `renet compose`. Un bridge de Docker predeterminado con NAT evitaría el aislamiento de loopback a nivel de kernel que impide que un repo alcance los servicios de otro repo, por lo que el daemon de Docker por repositorio está configurado con `"bridge": "none"` e `"iptables": false`. No hay un bridge enrutable al que un simple contenedor `docker run` pueda conectarse.

**Para obtener acceso de red en un contenedor ad-hoc, use la red de host:**

```bash
# Inside a repository shell (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# Now apt update, curl, pip install all work.
```

**Para servicios de producción, use un Rediaccfile con `renet compose`** en lugar de un `docker run` directo. `renet compose` inyecta `network_mode: host`, las etiquetas de IP de servicio y las etiquetas de enrutamiento de Traefik automáticamente. Consulte [Servicios](/es/docs/services) para más detalles.

## VS Code Permission Denied en archivos del sandbox

Al conectarse con `rdc vscode connect -m <machine> -r <repo>`, es posible que haya visto errores como `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` después de una sesión previa de VS Code. Esto era causado por propiedad mixta de archivos dentro del directorio del sandbox, que contenía archivos escritos tanto por su usuario SSH como por el usuario interno `rediacc`.

Las versiones modernas de renet solucionan esto de la siguiente forma:

- Creando el workspace del sandbox por repositorio (`/mnt/rediacc/.interim/sandbox/<repo>/`) con grupo `rediacc` y el bit set-group-ID (modo `2775`), de modo que todo archivo escrito debajo hereda el grupo correcto.
- Aplicando la umask `002` dentro del runtime del sandbox para que los archivos nuevos se creen con permisos de escritura para el grupo (`0664`/`0775`).
- Normalizando al arrancar un subárbol `.vscode-server/` existente, de modo que los archivos obsoletos anteriores al arreglo se reparan automáticamente.

Si aún ve errores de permisos, reinicie una vez el daemon de Docker del repo con `sudo systemctl restart rediacc-docker-<network-id>` desde una shell en la máquina para que se ejecute la pasada de normalización, y después reintente `rdc vscode connect`.

## El daemon no arranca tras una actualización de renet

Antes de cada arranque, `renet daemon start-foreground` reescribe `daemon.json` y `containerd.toml` en el directorio de configuración del repositorio a partir de las plantillas actuales, por lo que un repositorio cuya configuración fue generada por una versión antigua de renet recoge automáticamente el nuevo formato. No es necesario ejecutar ningún comando de migración, y tampoco hay que regenerar manualmente la unidad systemd. Basta con reiniciar el servicio:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

Si la unidad sigue fallando, revise el journal para obtener un error específico:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## Contenedores creados en el Docker daemon incorrecto

Si sus contenedores aparecen en el Docker daemon del sistema host en lugar del daemon aislado del repositorio, la causa más común es usar `sudo docker` dentro de un Rediaccfile.

`sudo` restablece las variables de entorno, por lo que `DOCKER_HOST` se pierde y Docker usa por defecto el socket del sistema (`/var/run/docker.sock`). Rediacc bloquea esto automáticamente, pero si lo encuentra:

- **Use `docker` directamente**, las funciones del Rediaccfile ya se ejecutan con privilegios suficientes
- Si debe usar sudo, use `sudo -E docker` para preservar las variables de entorno
- Revise su Rediaccfile en busca de comandos `sudo docker` y elimine el `sudo`

## La terminal no funciona

Si `rdc term` no logra abrir una ventana de terminal:

- Use el modo en línea con `-c` para ejecutar comandos directamente:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- Fuerce una terminal externa con `--external` si el modo en línea tiene problemas
- En Linux, asegúrese de tener instalado `gnome-terminal`, `xterm` u otro emulador de terminal

## Ejecutar diagnósticos

```bash
rdc doctor
```

Este comando verifica su entorno, la instalación de renet, la configuración de la config y el estado de autenticación. Cada verificación reporta OK, Warning o Error con una breve explicación.
