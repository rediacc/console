---
title: "Solución de problemas"
description: "Soluciones para problemas comunes con SSH, configuración, repositorios, servicios y Docker."
category: "Guides"
order: 10
language: es
sourceHash: 4c3163007e6a3326
---

# Solución de problemas

Problemas comunes y sus soluciones. En caso de duda, comience con `rdc doctor` para ejecutar una verificación de diagnóstico completa.

## Falla la conexión SSH

- Verifique que puede conectarse manualmente: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Ejecute `rdc config scan-keys server-1` para actualizar las claves del host
- Compruebe que el puerto SSH coincida: `--port 22`
- Pruebe con un comando simple: `rdc term server-1 -c "hostname"`

## Discrepancia de clave del host

Si un servidor fue reinstalado o sus claves SSH cambiaron, verá "host key verification failed":

```bash
rdc config scan-keys server-1
```

Este comando obtiene claves de host nuevas y actualiza su configuración.

## Falla la configuración de la máquina

- Asegúrese de que el usuario SSH tenga acceso sudo sin contraseña, o configure `NOPASSWD` para los comandos requeridos
- Verifique el espacio en disco disponible en el servidor
- Ejecute con `--debug` para una salida detallada: `rdc config setup-machine server-1 --debug`

## Falla la creación de repositorio

- Verifique que la configuración se haya completado: el directorio del almacén de datos debe existir
- Compruebe el espacio en disco del servidor
- Asegúrese de que el binario de renet esté instalado (ejecute la configuración nuevamente si es necesario)

## Los servicios no se inician

- Verifique la sintaxis del Rediaccfile: debe ser Bash válido
- Asegúrese de que los archivos `docker compose` usen `network_mode: host`
- Verifique que las imágenes Docker sean accesibles (considere `docker compose pull` en `prep()`)
- Revise los registros del contenedor usando el socket Docker del repositorio:

```bash
rdc term server-1 my-app -c "docker logs <container-name>"
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
rdc term server-1 my-app -c "docker ps"

# O manualmente con el socket:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

Reemplace `2816` con el ID de red de su repositorio (se encuentra en `rediacc.json` o `rdc repo status`).

## Contenedores creados en el Docker daemon incorrecto

Si sus contenedores aparecen en el Docker daemon del sistema host en lugar del daemon aislado del repositorio, la causa más común es usar `sudo docker` dentro de un Rediaccfile.

`sudo` restablece las variables de entorno, por lo que `DOCKER_HOST` se pierde y Docker usa por defecto el socket del sistema (`/var/run/docker.sock`). Rediacc bloquea esto automáticamente, pero si lo encuentra:

- **Use `docker` directamente** — las funciones del Rediaccfile ya se ejecutan con privilegios suficientes
- Si debe usar sudo, use `sudo -E docker` para preservar las variables de entorno
- Revise su Rediaccfile en busca de comandos `sudo docker` y elimine el `sudo`

## La terminal no funciona

Si `rdc term` no logra abrir una ventana de terminal:

- Use el modo en línea con `-c` para ejecutar comandos directamente:
  ```bash
  rdc term server-1 -c "ls -la"
  ```
- Fuerce una terminal externa con `--external` si el modo en línea tiene problemas
- En Linux, asegúrese de tener instalado `gnome-terminal`, `xterm` u otro emulador de terminal

## Ejecutar diagnósticos

```bash
rdc doctor
```

Este comando verifica su entorno, la instalación de renet, la configuración de la config y el estado de autenticación. Cada verificación reporta OK, Warning o Error con una breve explicación.
