---
title: "Gestión de Secrets"
description: "Coloca las credenciales de despliegue en un lugar al que los forks no pueden acceder. Solo escritura por diseño."
category: "Tutorials"
subcategory: advanced
order: 8
language: es
sourceHash: "0b4d72c80b489e12"
---

# Gestión de Secrets

Las apps reales necesitan credenciales reales: una clave live de Stripe, una contraseña de base de datos, un token de API. El lugar equivocado para ponerlas es el repo, porque un fork hereda todo lo que hay dentro de la imagen cifrada. De repente tu sandbox está cobrando a clientes reales.

El lugar correcto es `rdc repo secret`. Dos modos de entrega, solo escritura por diseño, y el fork comienza sin nada.

## Ver el tutorial

![Tutorial: Gestión de Secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## La trampa: `.env` en el repo

![Un archivo .env dentro de la imagen del repo es clonado por cada fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

La mayoría de los equipos ponen `.env` en el repo. Es el movimiento obvio.

Luego hacen un fork.

El fork es una copia byte a byte de la imagen del padre. Lo que esté en `.env` también está en el `.env` del fork. Los contenedores del fork arrancan. Leen la misma clave de Stripe. Llaman a la misma API de Stripe con credenciales de producción. Desde el lado de Stripe, esa llamada eres *tú*.

Ese es un mal día.

## Establecer un secret

La solución es `rdc repo secret`. Establece uno en modo `env`. El valor llega como variable de entorno en el contenedor:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Dos cosas que notar:

- `--mode env`. El valor llega como variable de entorno.
- `--current ""`. Cadena vacía. Estamos declarando que este es un secret nuevo sin valor previo.

Establece otro, en modo `file`, para cualquier cosa sensible:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

El modo `file` nunca pone el valor en el entorno del contenedor. Lo escribe en `/run/secrets/stripe_key` usando el mecanismo estándar de Docker.

Lista lo que tienes:

```bash
time rdc repo secret list --name my-app
```

Ves nombres y modos. **Sin valores.** La lista nunca muestra valores.

## Conéctalo al compose

Abre `docker-compose.yml`. Referencia ambos modos:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

`${REDIACC_SECRET_DB_HOST}` es el modo `env`: el wrapper de compose de `renet` lo expande desde tu almacén de secrets al momento del despliegue.

El bloque `secrets:` es el modo `file`, usando el mecanismo estándar de Docker. La ruta del host usa `${REDIACC_NETWORK_ID}` para que el mismo compose funcione tanto para repos padre como para forks. Cada fork tiene su propio network ID.

Despliega:

```bash
time rdc repo up --name my-app -m my-server
```

## Verificar en el contenedor

Ambos modos deberían estar dentro del contenedor ahora. Comprueba el secret en modo env:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`. El secret en modo env llegó al entorno del contenedor.

Ahora el de modo file:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`. El archivo está montado a través del mecanismo estándar de secrets de Docker.

## Nunca puedes leerlo de vuelta

![Modelo solo-escritura: get devuelve un digest, nunca el valor](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Ahora la parte que sorprende a la gente:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

Obtienes un digest. **No el valor.** No hay ningún flag que haga que devuelva el valor. No existe ningún comando que te dé el texto en claro de vuelta.

Ese es el modelo de GitHub Actions: solo escritura. Puedes demostrar que conoces un secret pasando `--current <valor>` y viendo que la precondición se cumple. No puedes pedirle a Rediacc que te diga cuál es.

¿Perdiste el valor? **No intentes leerlo. Rótalo.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` omite la precondición. El log de auditoría lo marca como una rotación: explícito, deliberado.

Si recuerdas el valor anterior, demuéstralo en cambio:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

Ese es el camino más seguro. Captura el error de "estoy en la terminal equivocada".

## El remate del fork

![Después del fork, la lista de secrets está vacía](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

¿Recuerdas la trampa? Haz fork del repo y mira:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Vacío.**

El fork no tiene clave de Stripe. Sin contraseña de base de datos. Sin token de API. Los contenedores del fork no pueden interpolar `${REDIACC_SECRET_STRIPE_KEY}`. El archivo en `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` no existe.

El fork no puede hacerse pasar por ti.

Si quieres secrets en el fork para pruebas, establécelos explícitamente en el fork con valores de sandbox:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Ahora el fork habla con el sandbox de Stripe. Las credenciales de producción nunca salieron de producción.

## Resumen

- `rdc repo secret` coloca tus credenciales fuera de la imagen del repo.
- El fork no puede acceder a ellas.
- `get` devuelve un digest, nunca el valor.
- Rota cuando olvidas. No intentes leerlo.

Secrets que el fork no puede seguir.

---

Siguiente: [Redes y dominios](/en/docs/tutorial-networking).
