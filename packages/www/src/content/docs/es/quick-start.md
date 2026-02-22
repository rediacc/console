---
title: Inicio rápido
description: Ejecute un servicio en contenedores en su servidor en 5 minutos.
category: Guides
order: -1
language: es
---

# Inicio rápido

Si no tienes claro que herramienta usar, consulta [rdc vs renet](/es/docs/rdc-vs-renet).
Despliegue un entorno de contenedores cifrado y aislado en su propio servidor en 5 minutos. Esta guía utiliza el **modo local** — sin cuentas en la nube ni dependencias de SaaS.

## Requisitos previos

- Una estación de trabajo con Linux o macOS
- Un servidor remoto (Ubuntu 24.04+, Debian 12+ o Fedora 43+) con acceso SSH y privilegios sudo
- Un par de claves SSH (por ejemplo, `~/.ssh/id_ed25519`)

## 1. Instalar la CLI

```bash
curl -fsSL https://get.rediacc.com | sh
```

## 2. Crear un contexto

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

## 3. Agregar su servidor

```bash
rdc context add-machine server-1 --ip <your-server-ip> --user <your-ssh-user>
```

## 4. Aprovisionar el servidor

```bash
rdc context setup-machine server-1
```

Esto instala Docker, cryptsetup y el binario renet en su servidor.

## 5. Crear un repositorio cifrado

```bash
rdc repo create my-app -m server-1 --size 5G
```

## 6. Desplegar servicios

Monte el repositorio, cree su `docker-compose.yml` y `Rediaccfile` dentro de él, luego inicie:

```bash
rdc repo up my-app -m server-1 --mount
```

## 7. Verificar

```bash
rdc machine containers server-1
```

Debería ver sus contenedores en ejecución.

## ¿Qué es Rediacc?

Rediacc despliega servicios en contenedores en servidores remotos que usted controla. Todo se cifra en reposo usando LUKS, cada repositorio obtiene su propio daemon Docker aislado, y toda la orquestación ocurre a través de SSH desde su estación de trabajo.

Sin cuentas en la nube. Sin dependencias de SaaS. Sus datos permanecen en sus servidores.

## Próximos pasos

- **[Arquitectura](/es/docs/architecture)** — Comprenda cómo funciona Rediacc: modos, modelo de seguridad, aislamiento Docker
- **[Configuración del servidor](/es/docs/setup)** — Guía detallada de configuración: contextos, máquinas, configuración de infraestructura
- **[Repositorios](/es/docs/repositories)** — Crear, gestionar, redimensionar, bifurcar y validar repositorios
- **[Servicios](/es/docs/services)** — Rediaccfiles, redes de servicios, despliegue, inicio automático
- **[Copia de seguridad y restauración](/es/docs/backup-restore)** — Respaldar en almacenamiento externo y programar copias de seguridad automáticas
- **[Monitoreo](/es/docs/monitoring)** — Salud del servidor, contenedores, servicios, diagnósticos
- **[Herramientas](/es/docs/tools)** — Sincronización de archivos, terminal SSH, integración con VS Code
- **[Guía de migración](/es/docs/migration)** — Incorporar proyectos existentes a repositorios Rediacc
- **[Solución de problemas](/es/docs/troubleshooting)** — Soluciones para problemas comunes
- **[Referencia de la CLI](/es/docs/cli-application)** — Referencia completa de comandos
