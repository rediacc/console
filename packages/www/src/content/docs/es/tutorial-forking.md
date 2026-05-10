---
title: "Fork de un repositorio"
description: "Clona un repositorio completo (app, base de datos, archivos) en segundos. Cualquier tamaño. Cero disco extra."
category: "Tutorials"
subcategory: advanced
order: 7
language: es
sourceHash: "9237f00dce2ee5ec"
---

# Fork de un repositorio

Esta es la característica estrella: clonar un entorno de producción completo (la app, la base de datos, los archivos de configuración) en segundos. Cualquier tamaño. Cero disco extra. Haz fork tantas veces como quieras.

El lema: **clona producción, no rompas nada.**

## Ver el tutorial

![Tutorial: Fork de un repositorio](/assets/tutorials/tutorial-forking.cast)

## Prepara algo que perder

Primero, dale al repo en ejecución un archivo para probar el aislamiento del fork. Abre el repo en VS Code:

```bash
rdc vscode connect -m my-server -r my-app
```

Dentro del repo, crea un archivo marcador:

```bash
time echo "Hello from production" > index.html
```

Ahora haz el fork.

## Fork

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![El repo padre se ramifica en clones independientes](/img/tutorials/tutorial-forking/slide-1.svg)

Un comando. Clonó todo (la app, la base de datos, los archivos de configuración) y ocurrió en segundos. Ejecútalo de nuevo y obtendrás otro clon independiente.

## ¿Por qué es tan rápido?

![Compartir un enlace de carpeta tiene la misma velocidad sin importar el tamaño de la carpeta](/img/tutorials/tutorial-forking/slide-2.svg)

Imagina que compartes un enlace a una carpeta. El enlace es el mismo, ya sea que la carpeta sea pequeña o enorme. La carpeta es pesada, el enlace es ligero.

![1 GB, 100 GB, 1 TB. El mismo tiempo, siempre.](/img/tutorials/tutorial-forking/slide-3.svg)

El fork funciona igual. 1 GB, 100 GB, 1 TB. El mismo tiempo, siempre.

## Qué se comparte y qué es tuyo

![Muchos espejos, un sol: base compartida, tus cambios son tuyos](/img/tutorials/tutorial-forking/slide-4.svg)

Piensa en el repo padre como el sol. No puedes sostener el sol, pero puedes sostener un espejo que lo refleja. Ese espejo es tu fork. Pinta sobre el espejo y tus dibujos son tuyos. El sol sigue igual, sin importar cuántos espejos lo enfrenten.

> No puedes sostener el sol, pero puedes sostenerlo en un espejo.

## ¿Qué pasa si el padre cambia después?

![Un fork es una fotografía congelada; el padre sigue fluyendo como un río](/img/tutorials/tutorial-forking/slide-5.svg)

Ahora piensa en un río. El agua sigue fluyendo. En cada momento es diferente. Cuando haces fork, tomas una fotografía del río, congelada en ese instante. El río sigue fluyendo. Tu fotografía no.

Si el repo padre cambia después, tu fork se queda donde estaba.

> No puedes sostener un río, pero puedes sostenerlo en una foto.

## El uso del disco se mantiene plano

![Cinco forks de un repo de 100 GB siguen siendo unos 100 GB en total](/img/tutorials/tutorial-forking/slide-6.svg)

Por eso tu disco no explota. ¿Cinco forks de un repo de 100 GB? Siguen siendo unos 100 GB en total. Solo pagas disco por lo que cambias en cada fork.

> Haz fork cinco veces si quieres. Tu disco ni lo notará.

## Lo que los forks *no* heredan: los secrets

Hay una cosa que el fork deliberadamente no hereda: los secrets. Un fork comienza sin claves de API, sin contraseñas de base de datos, sin tokens de Stripe. Por eso "clona producción, no rompas nada" realmente funciona. Tu sandbox no puede cobrar a clientes reales porque no puede hacerse pasar por ti. Lo configuramos correctamente en el tutorial de [Gestión de Secrets](/en/docs/tutorial-managing-secrets).

## Verificar el aislamiento

Lista ambos repos uno al lado del otro:

```bash
time rdc repo list -m my-server
```

Verás `my-app` y `my-app:experiment` ejecutándose al mismo tiempo.

En el repo original, revisa qué está corriendo:

```bash
time docker ps
```

Observa el tiempo de actividad. Estos son los contenedores originales. Ahora cambia al fork:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

Las mismas imágenes, pero el tiempo de actividad es nuevo. Arrancaron cuando se creó el fork.

Haz la diferencia aún más evidente. Agrega un contenedor solo al fork:

```bash
time docker run --rm -it -d nginx
time docker ps
```

Nginx está en ejecución, pero solo dentro de este fork.

Prueba algo destructivo:

```bash
time rm index.html
```

Desapareció aquí. Ahora regresa al original:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

Sin nginx. Los contenedores del fork se quedaron en el fork. Y `index.html` sigue aquí, intacto. El original nunca supo que pasó algo. Mismas imágenes, Docker daemons separados, sistemas de archivos separados.

## Limpieza

Cuando termines, simplemente elimina el fork:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

El original queda exactamente como estaba. **Fork, experimenta, rompe cosas, elimina.** Sin riesgo.

---

Siguiente: [Gestión de Secrets](/en/docs/tutorial-managing-secrets).
