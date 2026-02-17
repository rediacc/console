---
title: "Post-Instalacion"
description: "Configuracion de inicio automatico, estructura del contexto y resolucion de problemas para Rediacc."
category: "Guides"
order: 3
language: es
---

# Post-Instalacion

Despues de completar la [Guia Paso a Paso](/es/docs/guide), esta pagina cubre la configuracion de inicio automatico, la comprension del archivo de configuracion de contexto y la resolucion de problemas comunes.

## Inicio Automatico al Arranque

Por defecto, los repositorios deben montarse e iniciarse manualmente despues de reiniciar el servidor. El **inicio automatico** configura los repositorios para montarse automaticamente, iniciar Docker y ejecutar el `up()` del Rediaccfile cuando el servidor arranca.

### Como Funciona

Cuando habilita el inicio automatico para un repositorio:

1. Se genera un archivo de clave LUKS aleatorio de 256 bytes y se agrega al slot 1 de LUKS del repositorio (el slot 0 permanece como la frase de contrasena del usuario).
2. El archivo de clave se almacena en `{datastore}/.credentials/keys/{guid}.key` con permisos `0600` (solo root).
3. Se instala un servicio systemd (`rediacc-autostart`) que se ejecuta al arranque para montar todos los repositorios habilitados e iniciar sus servicios.

Al apagar o reiniciar el sistema, el servicio detiene graciosamente todos los servicios (`down()` del Rediaccfile), detiene los daemons Docker y cierra los volumenes LUKS.

> **Nota de seguridad:** Habilitar el inicio automatico almacena un archivo de clave LUKS en el disco del servidor. Cualquier persona con acceso root al servidor puede montar el repositorio sin la frase de contrasena. Este es un compromiso entre conveniencia (arranque automatico) y seguridad (requerir entrada manual de la frase de contrasena). Evalue esto segun su modelo de amenazas.

### Habilitar Inicio Automatico

```bash
rdc repo autostart enable my-app -m server-1
```

Se le solicitara la frase de contrasena del repositorio. Esto es necesario para autorizar la adicion del archivo de clave al volumen LUKS.

### Habilitar Inicio Automatico para Todos los Repositorios

```bash
rdc repo autostart enable-all -m server-1
```

### Deshabilitar Inicio Automatico

```bash
rdc repo autostart disable my-app -m server-1
```

Esto elimina el archivo de clave y destruye el slot 1 de LUKS. El repositorio ya no se montara automaticamente al arranque.

### Listar Estado del Inicio Automatico

```bash
rdc repo autostart list -m server-1
```

Muestra que repositorios tienen el inicio automatico habilitado y si el servicio systemd esta instalado.

## Comprender la Configuracion del Contexto

Toda la configuracion del contexto se almacena en `~/.rediacc/config.json`. Aqui hay un ejemplo anotado de como se ve este archivo despues de completar la guia:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**Campos clave:**

| Campo | Descripcion |
|-------|-------------|
| `mode` | `"local"` para modo local, `"s3"` para contextos respaldados por S3. |
| `apiUrl` | `"local://"` indica modo local (sin API remota). |
| `ssh.privateKeyPath` | Ruta a la clave privada SSH utilizada para todas las conexiones de maquinas. |
| `machines.<name>.knownHosts` | Claves de host SSH de `ssh-keyscan`, utilizadas para verificar la identidad del servidor. |
| `repositories.<name>.repositoryGuid` | UUID que identifica la imagen de disco cifrada en el servidor. |
| `repositories.<name>.credential` | Frase de contrasena de cifrado LUKS. **No se almacena en el servidor.** |
| `repositories.<name>.networkId` | ID de red que determina la subred IP (2816 + n*64). Asignado automaticamente. |

> Este archivo contiene datos sensibles (rutas de claves SSH, credenciales LUKS). Se almacena con permisos `0600` (solo lectura/escritura para el propietario). No lo comparta ni lo incluya en control de versiones.

## Resolucion de Problemas

### La Conexion SSH Falla

- Verifique que puede conectarse manualmente: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Ejecute `rdc context scan-keys server-1` para actualizar las claves del host
- Compruebe que el puerto SSH coincide: `--port 22`

### La Configuracion de la Maquina Falla

- Asegurese de que el usuario tenga acceso sudo sin contrasena, o configure `NOPASSWD` para los comandos requeridos
- Verifique el espacio de disco disponible en el servidor
- Ejecute con `--debug` para salida detallada: `rdc context setup-machine server-1 --debug`

### La Creacion del Repositorio Falla

- Verifique que la configuracion se completo: el directorio del datastore debe existir
- Compruebe el espacio de disco en el servidor
- Asegurese de que el binario renet este instalado (ejecute la configuracion nuevamente si es necesario)

### Los Servicios No Inician

- Verifique la sintaxis del Rediaccfile: debe ser Bash valido
- Asegurese de que los archivos de `docker compose` usen `network_mode: host`
- Verifique que las imagenes Docker sean accesibles (considere `docker compose pull` en `prep()`)
- Revise los registros de contenedores: conectese por SSH al servidor y use `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`

### Errores de Permiso Denegado

- Las operaciones de repositorio requieren root en el servidor (renet se ejecuta mediante `sudo`)
- Verifique que su usuario este en el grupo `sudo`
- Compruebe que el directorio del datastore tenga los permisos correctos

### Ejecutar Diagnosticos

Use el comando doctor integrado para diagnosticar problemas:

```bash
rdc doctor
```

Este verifica su entorno, la instalacion de renet, la configuracion del contexto y el estado de autenticacion.
