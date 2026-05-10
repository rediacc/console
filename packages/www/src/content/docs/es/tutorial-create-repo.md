---
title: "Crear tu primer repositorio"
description: "Crea un repositorio cifrado en tu servidor y ábrelo en VS Code."
category: "Tutorials"
subcategory: essentials
order: 4
language: es
sourceHash: "1294b0494f20671b"
---

# Crear tu primer repositorio

Un repositorio de Rediacc es un único archivo cifrado en tu servidor. Al montarse, se convierte en una carpeta con su propio Docker daemon y sus propios datos de aplicación: completamente aislado, completamente portable.

Piensa en él como un USB para producción: un archivo en reposo, un servidor en ejecución.

## Ver el tutorial

![Tutorial: Crear tu primer repositorio](/assets/tutorials/tutorial-create-repo.cast)

## Archivo en disco, entorno al montar

![El archivo cifrado se monta como una carpeta aislada](/img/tutorials/tutorial-create-repo/slide-1.svg)

La forma en disco es una imagen cifrada única. Al montarse, obtienes:

- Un Docker daemon dedicado (separado del del host)
- Datos de la aplicación dentro del volumen cifrado
- IPs de loopback que no colisionan con nada más en el servidor

Los repositorios son portables. Puedes moverlos entre máquinas, hacer copias de seguridad o hacer un fork al instante. Cada repo está aislado de todos los demás en el mismo servidor.

## Crear uno

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

Esto crea un repositorio cifrado de 2 GB en `my-server`. Verifícalo:

```bash
time rdc repo list -m my-server
```

## Abrirlo en VS Code

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code se abre directamente dentro del repositorio. Observa que el espacio de trabajo está vacío. Este es tu entorno aislado. Todo lo que crees aquí vive dentro del volumen cifrado, invisible para cualquier otro repo en el mismo servidor.

---

Siguiente: [Desplegar tu primera aplicación](/en/docs/tutorial-deploy-app).
