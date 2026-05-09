---
title: "Monitoreo"
description: "Comprueba el estado de tus servidores y repos desde tu laptop con los comandos rdc machine."
category: "Tutorials"
subcategory: advanced
order: 12
language: es
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# Monitoreo

Tu app está desplegada, en producción y con backup. Ahora asegúrate de que todo se mantenga saludable. `rdc` te da una imagen completa de cualquier servidor (salud, contenedores, repos) desde tu laptop.

## Ver el tutorial

![Tutorial: Monitoreo](/assets/tutorials/tutorial-monitoring.cast)

## Tres cosas que puedes revisar

![Salud, contenedores, repos](/img/tutorials/tutorial-monitoring/slide-1.svg)

## Salud: información del sistema

Comienza con la vista del sistema:

```bash
time rdc machine query --name my-server --system
```

Muestra el tiempo de actividad del sistema, el uso del disco y el estado del almacenamiento. Si algo está mal, te lo indica.

## Contenedores

Para ver todos los contenedores en ejecución en cada repo de la máquina:

```bash
time rdc machine query --name my-server --containers
```

Obtienes nombre, estado, salud, CPU y memoria por cada contenedor, además de qué repo lo pertenece.

## Repos

Para revisar tus repositorios:

```bash
time rdc machine query --name my-server --repositories
```

Muestra cada repo con su tamaño, estado de montaje, estado de Docker y uso del disco.

## Todo de una vez

```bash
time rdc machine query --name my-server
```

Información del sistema, repos y contenedores, todo en un comando. El mismo comando `query` sin filtros devuelve la imagen completa; con `--system`, `--containers`, `--repositories`, `--services`, `--network` o `--block-devices` se limita a esa sección.

## Verificación local

`rdc doctor` comprueba tu configuración local (Node, clave SSH, `renet`, Docker), independientemente de cualquier servidor específico:

```bash
time rdc doctor
```

## Terminaste

Esa es la serie completa. Ahora puedes instalar, configurar, desplegar, hacer fork, publicar en producción, habilitar el arranque automático, hacer backup y monitorear. Todo desde tu terminal, todo en tus propios servidores.
