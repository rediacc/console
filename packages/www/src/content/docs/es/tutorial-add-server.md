---
title: "Agregar tu primer servidor"
description: "Registra tu primer servidor en rdc, aprovisiónalo y comprende la arquitectura de rdc + renet."
category: "Tutorials"
subcategory: essentials
order: 3
language: es
sourceHash: "2b5de59f61cfb88c"
---

# Agregar tu primer servidor

Antes de agregar un servidor, conviene entender cómo funciona `rdc`. Rediacc tiene una arquitectura de dos herramientas: `rdc` en tu laptop y `renet` en el servidor.

## Ver el tutorial

![Tutorial: Agregar tu primer servidor](/assets/tutorials/tutorial-add-server.cast)

## ¿Por qué dos herramientas?

![rdc en la laptop, renet en el servidor, SSH entre ambos](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** es el CLI en tu laptop. Aquí escribes los comandos.
- **`renet`** es el orquestador en el servidor. Gestiona el cifrado, Docker y el aislamiento.

Cuando ejecutas un comando localmente, `rdc` se conecta por SSH y ejecuta `renet` en el servidor. Nunca necesitas conectarte por SSH a tus servidores manualmente. `rdc` lo hace por ti.

## Paso 1: Registrar el servidor

Indica a `rdc` los datos del servidor. Reemplaza el nombre, la IP y el usuario con los tuyos.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## Paso 2: Aprovisionarlo

La configuración instala `renet` y crea el almacén cifrado en el servidor.

```bash
time rdc config machine setup --name my-server
```

Cuando termine, tu servidor estará listo para alojar repositorios.

## Dónde vive la configuración

Verifica lo que `rdc` sabe sobre tu entorno:

```bash
time rdc config show
```

O abre el archivo JSON directamente:

```bash
vim ~/.config/rediacc/rediacc.json
```

Este único archivo contiene todo: máquinas, repos, clave SSH y credenciales de cifrado. Cópialo a otra laptop y estarás listo para operar desde esa máquina también.

---

Siguiente: [Crear tu primer repositorio](/en/docs/tutorial-create-repo).
