---
title: Hoja de referencia de RDC CLI
description: "Referencia rápida de rdc: configuraciones, repositorios, máquinas, sincronización y contenedores. Conjunto completo de opciones: agregar --help a cualquier comando."
category: Guides
order: 3
language: es
sourceHash: "c9f10ececc124587"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Hoja de referencia de RDC CLI

No se enumeran todos los comandos de `rdc` aquí, solo los que aparecen en cada despliegue. Para ver el conjunto completo de opciones, ejecuta cualquier comando de rdc con `--help`. Los casos especiales y las opciones raramente utilizadas se encuentran en la referencia completa.

## Ciclo de vida del repositorio

| Comando | Descripción |
|---------|-------------|
| `rdc repo create <repo> -m <machine>` | Crear un nuevo repositorio en una máquina |
| `rdc repo up <repo>@<machine>` | Desplegar o actualizar un repositorio |
| `rdc repo down <repo>@<machine>` | Detener un repositorio |
| `rdc repo delete <repo>@<machine>` | Eliminar un repositorio |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Bifurcar un repositorio (casi instantáneo, BTRFS reflink) |
| `rdc repo promote <repo>:<tag>` | Tomar propiedad de un repositorio existente |
| `rdc repo list` | Listar todos los repositorios con nombre y GUID |

## Secretos por repositorio

Credenciales de solo escritura en tiempo de despliegue. `get` devuelve solo el resumen. El valor nunca se devuelve. Consulta [Repositorios § Secretos](/en/docs/repositories#secrets) para la guía completa.

| Comando | Descripción |
|---------|-------------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Crear un nuevo secreto (`--current ""` para la primera escritura) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Sobrescribir un secreto existente (precondición de estilo contraseña) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Sobrescribir sin verificar el valor anterior (auditado como rotación) |
| `rdc repo secret list <repo>` | Listar nombres de secretos y modos de entrega (nunca valores, nunca resúmenes) |
| `rdc repo secret get <repo> --key <KEY>` | Mostrar resumen del secreto y modo (nunca valor en texto plano) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Eliminar un secreto |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Eliminar sin verificar el valor anterior |

> Los forks no heredan secretos. Establécelos en el fork explícitamente con `rdc repo secret set <repo>:<tag>`.

## Copia de seguridad y restauración

| Comando | Descripción |
|---------|-------------|
| `rdc repo push <repo>@<machine> --to <storage>` | Subir una copia de seguridad del repositorio al almacenamiento |
| `rdc repo push --to <storage> -m <machine>` | Subir todos los repositorios al almacenamiento |
| `rdc repo pull <repo>@<machine> --from <storage>` | Restaurar un repositorio desde el almacenamiento |
| `rdc repo pull --from <storage> -m <machine>` | Restaurar todos los repositorios desde el almacenamiento |
| `rdc repo push ... --bwlimit <limit>` | Limitar el ancho de banda de rsync al subir (p. ej. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limitar el ancho de banda de rsync al bajar |
| `rdc repo push ... --checkpoint` | Guardar punto de control de contenedores antes de subir |
| `rdc backup list --storage <storage> -m <machine>` | Listar las copias de seguridad disponibles en el almacenamiento |
| `rdc storage browse <storage>` | Explorar el contenido del almacenamiento |

## Migración de repositorios

| Comando | Descripción |
|---------|-------------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Mover un repositorio entre máquinas |
| `rdc repo migrate ... --provision` | Aprovisionar el destino antes de transferir |
| `rdc repo migrate ... --checkpoint` | Guardar punto de control antes de migrar |
| `rdc repo migrate ... --skip-dns` | Omitir la actualización de DNS tras la migración |
| `rdc repo migrate ... --bwlimit <limit>` | Limitar el ancho de banda de transferencia |

## Estrategias de copia de seguridad

| Comando | Descripción |
|---------|-------------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Crear o actualizar una estrategia de copia de seguridad con nombre |
| `rdc backup strategy list` | Listar todas las estrategias definidas |
| `rdc backup strategy show <name>` | Mostrar los detalles de una estrategia |
| `rdc backup strategy remove <name>` | Eliminar una estrategia |
| `rdc backup schedule -m <machine>` | Desplegar estrategias de copia de seguridad configuradas en una máquina |

## Operaciones de copia de seguridad

| Comando | Descripción |
|---------|-------------|
| `rdc backup schedule -m <machine>` | Desplegar las estrategias vinculadas como temporizadores de systemd |
| `rdc backup schedule -m <machine> --dry-run` | Previsualizar las unidades de temporizador sin desplegar (tokens enmascarados) |
| `rdc backup run -m <machine>` | Ejecutar inmediatamente todas las estrategias vinculadas |
| `rdc backup run <name> -m <machine>` | Ejecutar inmediatamente una estrategia específica |
| `rdc backup status -m <machine>` | Mostrar el estado del temporizador y los resultados de los trabajos recientes |
| `rdc backup status <name> -m <machine>` | Mostrar el estado de una estrategia específica |
| `rdc backup cancel -m <machine>` | Cancelar las copias de seguridad en ejecución |
| `rdc backup cancel <name> -m <machine>` | Cancelar una copia de seguridad en ejecución específica |

## Gestión de máquinas

| Comando | Descripción |
|---------|-------------|
| `rdc machine status <machine>` | Estado completo de la máquina (sistema, contenedores, servicios, repos, red) |
| `rdc machine status <machine> --system` | Solo información del sistema |
| `rdc machine status <machine> --containers` | Solo lista de contenedores |
| `rdc machine status <machine> --repositories` | Solo lista de repositorios |
| `rdc machine status <machine> --services` | Solo lista de servicios |
| `rdc machine status <machine> --network` | Solo información de red |
| `rdc machine status <machine> --block-devices` | Solo información de dispositivos de bloque |
| `rdc machine list` | Listar todas las máquinas en la configuración |
| `rdc machine setup <machine>` | Ejecutar el aprovisionamiento inicial de la máquina |
| `rdc machine prune <machine>` | Eliminar recursos no utilizados de la máquina |
| `rdc machine deprovision <machine>` | Desaprovisionar completamente una máquina |

## Terminal y sincronización

| Comando | Descripción |
|---------|-------------|
| `rdc term connect <machine>` | Abrir terminal SSH a la máquina |
| `rdc term connect <repo>@<machine>` | Abrir terminal SSH al repositorio (establece DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | Ejecutar un comando en la máquina |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Subir uno o más archivos o directorios locales al repositorio |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Subir un único archivo local a una ruta remota específica |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Descargar un directorio del repositorio localmente |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Descargar un archivo remoto a un directorio local |
| `rdc vscode connect <repo>@<machine>` | Abrir sesión VS Code Remote SSH |

## Configuración

| Comando | Descripción |
|---------|-------------|
| `rdc config init <name>` | Crear un archivo de configuración con nombre |
| `rdc machine add <machine> --ip <host> --user <user>` | Agregar una máquina a la configuración |
| `rdc storage import rclone.conf` | Importar proveedores de almacenamiento desde la configuración de rclone |
| `rdc storage list` | Listar los proveedores de almacenamiento configurados |
| `rdc backup strategy set ...` | Definir una estrategia de copia de seguridad con nombre |
| `rdc --config <name> <command>` | Usar un archivo de configuración con nombre |

## Depuración y acceso directo

| Comando | Descripción |
|---------|-------------|
| `rdc term connect <repo>@<machine> -c "docker ps"` | Listar contenedores en un repositorio |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Obtener los logs de un contenedor |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Ejecutar un comando en un contenedor |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Reiniciar un contenedor |
