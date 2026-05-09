---
title: "Modo producción"
description: "Ejecuta tu app desconectada de tu laptop y sobrevive a los reinicios del servidor con el arranque automático."
category: "Tutorials"
subcategory: advanced
order: 10
language: es
sourceHash: "0e070fcd877900ab"
---

# Modo producción

Hasta ahora has estado ejecutando la app con `renet dev up` desde dentro del repo. Eso es ideal para desarrollo. Para producción, gestionas todo desde tu laptop con `rdc`. Cierra tu laptop y la app sigue ejecutándose.

## Ver el tutorial

![Tutorial: Modo producción](/assets/tutorials/tutorial-production-mode.cast)

## Desarrollo vs producción

La diferencia es simple:

- `renet dev up` se ejecuta **dentro del repo**. Necesitas estar conectado.
- `rdc repo up` se ejecuta **desde tu laptop**. No necesitas conexión después de eso.

Tres acciones te llevan del desarrollo a la producción:

![Detener, arrancar, autoarranque](/img/tutorials/tutorial-production-mode/slide-1.svg)

## Paso 1: Detener la sesión de desarrollo

Conéctate al repo y detenlo:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## Paso 2: Arrancar en modo producción

Desde la terminal de tu laptop:

```bash
time rdc repo up --name my-app -m my-server
```

Listo. Tu app está en ejecución y puedes cerrar tu laptop. El `Rediaccfile` se encarga de todo. `rdc repo up` llama a la misma función `up` que usaba `renet dev up`. El mismo `Rediaccfile`, una forma diferente de invocarlo.

## Paso 3: Sobrevivir a los reinicios del servidor

Asegúrate de que tu app vuelva automáticamente cuando el servidor se reinicie:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Verifica qué repos tienen el arranque automático habilitado:

```bash
time rdc repo autostart list -m my-server
```

## Detener en producción

Cuando necesites detener tu app:

```bash
time rdc repo down --name my-app -m my-server
```

Un comando para arrancar, un comando para detener. Todo desde tu laptop.

---

Siguiente: [Backup y restauración](/en/docs/tutorial-backup-restore).
