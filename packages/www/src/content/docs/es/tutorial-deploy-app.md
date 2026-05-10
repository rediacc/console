---
title: "Desplegar tu primera aplicación"
description: "Despliega una app en contenedor a partir de una plantilla integrada usando renet dev up."
category: "Tutorials"
subcategory: essentials
order: 5
language: es
sourceHash: "f75b5b6a716e94bf"
---

# Desplegar tu primera aplicación

Tienes un repositorio vacío. `rdc` incluye plantillas integradas para que puedas levantar apps reales sin escribir un `docker-compose` desde cero. Tres pasos: elige una plantilla, aplícala y ejecútala.

## Ver el tutorial

![Tutorial: Desplegar tu primera aplicación](/assets/tutorials/tutorial-deploy-app.cast)

## Elegir · Aplicar · Ejecutar

![Elige una plantilla, aplícala y ejecútala](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## Paso 1: Elegir

Explora las plantillas disponibles:

```bash
time rdc repo template list
```

Verás configuraciones listas para apps comunes: Postgres, Redis, servidores web y más.

## Paso 2: Aplicar

Agrega la plantilla a tu repo. Usaremos `app-postgres`:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

Aparecen dos nuevos archivos en el repo: `docker-compose.yml` y `Rediaccfile`. El archivo compose describe los contenedores; el `Rediaccfile` define qué ocurre cuando la app arranca y se detiene (los hooks de ciclo de vida `up` y `down`).

## Paso 3: Ejecutar

Ya estás dentro del sandbox del repo (a través de la conexión de VS Code del tutorial anterior), así que usa `renet` directamente:

```bash
time renet dev up
```

Listo. Tu app está en ejecución. Verifícalo:

```bash
time docker ps
```

`docker ps` aquí lista solo los contenedores de este repo. Los demás repos en el mismo servidor tienen sus propios Docker daemons y son completamente invisibles desde este.

---

Siguiente: [Trabajar con tu repo](/en/docs/tutorial-work-with-repo).
