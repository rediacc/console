---
title: Hoja de referencia de RDC CLI
description: >-
  Referencia rápida de todos los comandos rdc, configuraciones, repositorios,
  máquinas, sincronización, contenedores y más.
category: Guides
order: 3
language: es
sourceHash: "12956297c1157cd2"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# Hoja de referencia de RDC CLI

Referencia rápida de los comandos `rdc` más comunes. Ejecuta cualquier comando con `--help` para ver todas las opciones.

## Ciclo de vida del repositorio

| Comando | Descripción |
|---------|-------------|
| `rdc repo create --name <repo> -m <machine>` | Crear un nuevo repositorio en una máquina |
| `rdc repo up --name <repo> -m <machine>` | Desplegar o actualizar un repositorio |
| `rdc repo down --name <repo> -m <machine>` | Detener un repositorio |
| `rdc repo delete --name <repo> -m <machine>` | Eliminar un repositorio |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Bifurcar un repositorio (casi instantáneo, BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | Tomar propiedad de un repositorio existente |
| `rdc config repository list` | Listar todos los repositorios con nombre y GUID |

## Copia de seguridad y restauración

| Comando | Descripción |
|---------|-------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Subir una copia de seguridad del repositorio al almacenamiento |
| `rdc repo push --to <storage> -m <machine>` | Subir todos los repositorios al almacenamiento |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Restaurar un repositorio desde el almacenamiento |
| `rdc repo pull --from <storage> -m <machine>` | Restaurar todos los repositorios desde el almacenamiento |
| `rdc repo push ... --bwlimit <limit>` | Limitar el ancho de banda de rsync al subir (p. ej. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Limitar el ancho de banda de rsync al bajar |
| `rdc repo push ... --checkpoint` | Guardar punto de control de contenedores antes de subir |
| `rdc repo backup list --from <storage> -m <machine>` | Listar las copias de seguridad disponibles en el almacenamiento |
| `rdc storage browse --name <storage>` | Explorar el contenido del almacenamiento |

## Migración de repositorios

| Comando | Descripción |
|---------|-------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Mover un repositorio entre máquinas |
| `rdc repo migrate ... --provision` | Aprovisionar el destino antes de transferir |
| `rdc repo migrate ... --checkpoint` | Guardar punto de control antes de migrar |
| `rdc repo migrate ... --skip-dns` | Omitir la actualización de DNS tras la migración |
| `rdc repo migrate ... --bwlimit <limit>` | Limitar el ancho de banda de transferencia |

## Estrategias de copia de seguridad

| Comando | Descripción |
|---------|-------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Crear o actualizar una estrategia de copia de seguridad con nombre |
| `rdc config backup-strategy list` | Listar todas las estrategias definidas |
| `rdc config backup-strategy show --name <name>` | Mostrar los detalles de una estrategia |
| `rdc config backup-strategy remove --name <name>` | Eliminar una estrategia |
| `rdc machine backup schedule -m <machine>` | Desplegar estrategias de copia de seguridad configuradas en una máquina |

## Operaciones de copia de seguridad

| Comando | Descripción |
|---------|-------------|
| `rdc machine backup schedule -m <machine>` | Desplegar las estrategias vinculadas como temporizadores de systemd |
| `rdc machine backup schedule -m <machine> --dry-run` | Previsualizar las unidades de temporizador sin desplegar (tokens enmascarados) |
| `rdc machine backup now -m <machine>` | Ejecutar inmediatamente todas las estrategias vinculadas |
| `rdc machine backup now -m <machine> --strategy <name>` | Ejecutar inmediatamente una estrategia específica |
| `rdc machine backup status -m <machine>` | Mostrar el estado del temporizador y los resultados de los trabajos recientes |
| `rdc machine backup status -m <machine> --strategy <name>` | Mostrar el estado de una estrategia específica |
| `rdc machine backup cancel -m <machine>` | Cancelar las copias de seguridad en ejecución |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Cancelar una copia de seguridad en ejecución específica |

## Gestión de máquinas

| Comando | Descripción |
|---------|-------------|
| `rdc machine query --name <machine>` | Estado completo de la máquina (sistema, contenedores, servicios, repos, red) |
| `rdc machine query --name <machine> --system` | Solo información del sistema |
| `rdc machine query --name <machine> --containers` | Solo lista de contenedores |
| `rdc machine query --name <machine> --repositories` | Solo lista de repositorios |
| `rdc machine query --name <machine> --services` | Solo lista de servicios |
| `rdc machine query --name <machine> --network` | Solo información de red |
| `rdc machine query --name <machine> --block-devices` | Solo información de dispositivos de bloque |
| `rdc machine list` | Listar todas las máquinas en la configuración |
| `rdc config machine setup --name <machine>` | Ejecutar el aprovisionamiento inicial de la máquina |
| `rdc machine prune --name <machine>` | Eliminar recursos no utilizados de la máquina |
| `rdc machine deprovision --name <machine>` | Desaprovisionar completamente una máquina |
| `rdc machine vault-status --name <machine>` | Mostrar el estado del vault de LUKS |

## Terminal y sincronización

| Comando | Descripción |
|---------|-------------|
| `rdc term connect -m <machine>` | Abrir terminal SSH a la máquina |
| `rdc term connect -m <machine> -r <repo>` | Abrir terminal SSH al repositorio (establece DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Ejecutar un comando en la máquina |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Subir un archivo, directorio o varios orígenes al repositorio |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Descargar un directorio del repositorio localmente |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Descargar un archivo remoto a un directorio local |
| `rdc vscode connect -m <machine> -r <repo>` | Abrir sesión VS Code Remote SSH |

## Configuración

| Comando | Descripción |
|---------|-------------|
| `rdc config init --name <name>` | Crear un archivo de configuración con nombre |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Agregar una máquina a la configuración |
| `rdc config storage import --file rclone.conf` | Importar proveedores de almacenamiento desde la configuración de rclone |
| `rdc config storage list` | Listar los proveedores de almacenamiento configurados |
| `rdc config backup-strategy set ...` | Definir una estrategia de copia de seguridad con nombre |
| `rdc --config <name> <command>` | Usar un archivo de configuración con nombre |

## Depuración y acceso directo

| Comando | Descripción |
|---------|-------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Listar contenedores en un repositorio |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Obtener los logs de un contenedor |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Ejecutar un comando en un contenedor |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Reiniciar un contenedor |
