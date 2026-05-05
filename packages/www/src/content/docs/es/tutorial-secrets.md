---
title: "Gestión de secretos"
description: "Establece secretos por repositorio, conéctalos a compose, verifica que llegan al contenedor, rótalos y confirma que los forks no heredan ninguno."
category: "Tutorials"
order: 7
language: es
sourceHash: "fb8bc967ed22fc10"
---

# Cómo gestionar secretos por repositorio con Rediacc

Las aplicaciones reales necesitan credenciales: una clave Stripe live, una contraseña de base de datos, un token de API. El sitio incorrecto para ponerlas es dentro del repositorio. Un fork hereda todo lo que vive en la imagen cifrada, y los contenedores del fork arrancan identificándose como el padre frente a servicios externos. El sitio correcto es `rdc repo secret`. Los valores aterrizan fuera de la imagen cifrada, así que los forks empiezan con un mapa de secretos vacío.

En este tutorial estableces ambos modos de secreto, los conectas a un archivo compose, verificas que llegan al contenedor, rotas uno y confirmas que un fork no hereda nada.

## Requisitos previos

- La CLI `rdc` instalada con una configuración inicializada
- Una máquina aprovisionada y un repositorio creado (ver [Tutorial: Ciclo de vida del repositorio](/es/docs/tutorial-repos))
- Un `Rediaccfile` y `docker-compose.yml` que puedas editar

## Paso 1: Establecer un secreto

Hay dos modos de entrega disponibles. `env` exporta el valor como `REDIACC_SECRET_<KEY>` para la interpolación `${...}` de compose. `file` escribe el valor en un archivo tmpfs del lado del host en `/var/run/rediacc/secrets/<networkID>/<KEY>` para usar con el bloque `secrets:` de Docker compose. Usa `file` para cualquier cosa sensible. Los valores en modo env aparecen en `docker inspect` y en `/proc/<pid>/environ`.

Para la primera escritura de una clave nueva, pasa `--current ""` (vacío) para reconocer que no hay valor previo.

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## Paso 2: Listar lo que hay

```bash
rdc repo secret list --name my-app
```

La salida es JSON con el nombre y modo de cada secreto. Los valores nunca aparecen en el listado. Ni siquiera se buscan en disco.

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## Paso 3: Conectar a compose

Ambos modos se referencian desde el mismo `docker-compose.yml`:

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

El `stripe_key` en minúsculas en el servicio es el nombre de archivo `/run/secrets/<name>` dentro del contenedor. El `STRIPE_KEY` en mayúsculas en la ruta del host coincide con el `--key` que estableciste. `${REDIACC_NETWORK_ID}` es interpolado por `renet compose` automáticamente. Eso es importante porque el ID de red es por fork, así que el mismo archivo compose funciona en el padre y en cualquier fork (donde, como verás en el paso 6, el archivo simplemente no existirá).

> **Aislamiento entre repositorios aplicado.** El validador compose de renet rechaza cualquier ruta `secrets: file:` (o `configs: file:`, o `env_file:`) que apunte al ID de red de otro repositorio. El token literal `${REDIACC_NETWORK_ID}` (o el entero de tu propia red) es la única forma aceptada, y `--unsafe` NO lo anula. La sandbox Landlock alrededor del subproceso bash del Rediaccfile también acota lecturas del sistema de archivos al directorio de secretos de tu propia red. Así que incluso un `cat /var/run/rediacc/secrets/<otro>/X` malicioso desde un Rediaccfile falla con EACCES en la capa del kernel. No necesitas activarlo; la protección está activa por defecto.

## Paso 4: Desplegar y verificar

```bash
rdc repo up --name my-app -m server-1
```

Después del despliegue, ejecuta dentro del contenedor para confirmar que ambos modos llegaron:

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# sk_test_xxx
```

Si quieres inspeccionar el archivo tmpfs del lado del host directamente:

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## Paso 5: Rotar sin conocer el valor previo

Puedes leer un digest con `rdc repo secret get`, pero nunca el valor en texto plano. Ese es el modelo write-only. Si necesitas verificar que un valor almacenado coincide con lo que tienes, pásalo vía `--current` y observa la precondición pasar o fallar:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

Si has olvidado el valor previo por completo (tu gestor de contraseñas lo perdió, o heredaste el repositorio), usa `--rotate-secret` para saltarte la precondición. El log de auditoría registra esto fuertemente como una rotación:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` y `--rotate-secret` son mutuamente excluyentes. Elige uno.

## Paso 6: Confirmar que los forks no heredan nada

El propósito principal: forkea el repositorio y comprueba la lista de secretos del fork:

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

Vacío. Los contenedores del fork no pueden interpolar `${REDIACC_SECRET_DB_HOST}` (la variable está sin establecer, así que cadena vacía), y el archivo en `/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY` simplemente no existe. Si el `repo up` del fork intenta montarlo vía el bloque `secrets:` de compose, el despliegue fallará con un error claro. Exactamente el modo de fallo que quieres, porque significa que la sandbox no puede pretender ser producción frente a servicios externos.

Para usar secretos en el fork, establécelos en el fork explícitamente con valores acotados al sandbox:

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Ahora el fork habla con una base de datos de prueba y una cuenta sandbox de Stripe. Las credenciales de producción del padre nunca salen del padre.

## Limpieza

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## Ver también

- [Repositorios § Secretos](/es/docs/repositories#secrets). La referencia completa
- [Hoja de trucos CLI RDC § Secretos por repositorio](/es/docs/rdc-cheat-sheet#per-repo-secrets). Referencia rápida de comandos
- [Seguridad de agentes IA](/es/docs/ai-agents-safety). El gate de mutación simétrico y los hints estructurados de acción `next` en los sobres de error
- [Servicios § Usar secretos por repositorio en compose](/es/docs/services#using-per-repo-secrets-in-compose). Referencia del patrón compose
