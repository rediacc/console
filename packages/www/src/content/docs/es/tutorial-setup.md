---
title: "Configuración de máquina"
description: "Cree un perfil de configuración, registre una máquina remota, verifique la conectividad SSH y configure los ajustes de infraestructura."
category: "Tutorials"
order: 2
language: es
sourceHash: "c85a5f51a95e07bb"
---

# Cómo configurar una máquina con Rediacc

Cada implementación de Rediacc comienza con un perfil de configuración y una máquina registrada. En este tutorial, creará una configuración, registrará un servidor remoto, verificará la conectividad SSH, ejecutará diagnósticos del entorno y configurará la red de infraestructura. Al finalizar, su máquina estará lista para implementaciones de repositorios.

## Requisitos previos

- La CLI `rdc` instalada
- Un servidor remoto (o VM local) accesible vía SSH
- Una clave privada SSH que pueda autenticarse en el servidor

## Grabación interactiva

![Tutorial: Configuración de máquina](/assets/tutorials/setup-tutorial.cast)

### Paso 1: Crear una nueva configuración

Un perfil de configuración almacena definiciones de máquinas, credenciales SSH y ajustes de infraestructura. Cree uno para este entorno.

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Esto crea un archivo de configuración con nombre en `~/.config/rediacc/tutorial-demo.json`.

### Paso 2: Ver configuraciones

Verifique que el nuevo perfil aparezca en la lista de configuraciones.

```bash
rdc config list
```

Lista todas las configuraciones disponibles con su tipo de adaptador (local o cloud) y cantidad de máquinas.

### Paso 3: Agregar una máquina

Registre una máquina con su dirección IP y usuario SSH. La CLI obtiene y almacena automáticamente las claves de host del servidor mediante `ssh-keyscan`.

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

### Paso 4: Ver máquinas

Confirme que la máquina se registró correctamente.

```bash
rdc config machines --config tutorial-demo
```

Muestra todas las máquinas en la configuración actual con sus detalles de conexión.

### Paso 5: Establecer máquina predeterminada

Establecer una máquina predeterminada evita repetir `-m bridge-vm` en cada comando.

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

### Paso 6: Probar conectividad

Antes de implementar cualquier cosa, verifique que la máquina sea accesible por SSH.

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Ambos comandos se ejecutan en la máquina remota y devuelven resultado inmediatamente. Si alguno falla, verifique que su clave SSH sea correcta y que el servidor sea accesible.

### Paso 7: Ejecutar diagnósticos

```bash
rdc doctor
```

Verifica su entorno local: versión de CLI, Docker, binario de renet, estado de configuración, clave SSH y requisitos de virtualización. Cada verificación reporta **OK**, **Warning** o **Error**.

### Paso 8: Configurar infraestructura

Para servicios de acceso público, la máquina necesita configuración de red — su IP externa, un dominio base y un correo de certificado para TLS.

```bash
rdc config set-infra bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Verifique la configuración:

```bash
rdc config show-infra bridge-vm
```

Implemente la configuración de proxy Traefik generada en el servidor con `rdc config push-infra bridge-vm`.

## Solución de problemas

**"SSH key not found" o "Permission denied (publickey)"**
Verifique que la ruta de clave pasada a `config init` exista y coincida con `authorized_keys` del servidor. Compruebe los permisos: el archivo de clave privada debe ser `600` (`chmod 600 ~/.ssh/id_ed25519`).

**"Connection refused" en comandos SSH**
Confirme que el servidor esté ejecutándose y que la IP sea correcta. Verifique que el puerto 22 esté abierto: `nc -zv <ip> 22`. Si usa un puerto no estándar, pase `--port` al agregar la máquina.

**"Host key verification failed"**
La clave de host almacenada no coincide con la clave actual del servidor. Esto ocurre después de una reconstrucción del servidor o reasignación de IP. Ejecute `rdc config scan-keys <machine>` para actualizar la clave.

## Próximos pasos

Ha creado un perfil de configuración, registrado una máquina, verificado la conectividad y configurado la red de infraestructura. Para implementar aplicaciones:

- [Configuración de máquina](/es/docs/setup) — referencia completa para todos los comandos de configuración y setup
- [Tutorial: Ciclo de vida del repositorio](/es/docs/tutorial-repos) — crear, implementar y gestionar repositorios
- [Inicio rápido](/es/docs/quick-start) — implementar una aplicación contenedorizada de principio a fin
