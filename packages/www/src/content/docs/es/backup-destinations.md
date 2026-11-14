---
title: "Destinos de backup"
description: "Envía cada estrategia de backup a más de un almacén, restaura desde el almacén que tiene el mejor snapshot y consulta una fila de estado por destino."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: es
sourceHash: "10ded4035f1e9641"
sourceCommit: "7264926d04c36ba68ec76946fc14565405acd340"
---

# Destinos de backup

Una estrategia de backup puede escribir en más de un almacén. Cada destino es un punto de recuperación independiente: tiene su propio snapshot, su propio commit y su propia fila de estado, así que un almacén que falla no estropea a otro.

Todos los almacenes pertenecen a una misma cuenta. Una config, una licencia y una factura los cubren a todos. Una máquina con sesión iniciada en dos cuentas sigue siendo rechazada, porque varios destinos significan varios almacenes dentro de una misma cuenta.

## Almacenes

Un almacén es un bucket en el que el servidor de cuentas escribe en nombre de la máquina. Toda suscripción tiene uno desde el primer día, llamado `home`: el almacén alojado que los comandos de backup han usado siempre. Un destino que no indica almacén escribe en `home`.

Además se pueden registrar dos tipos.

| Tipo | Qué es | Qué requiere el registro |
|------|--------|--------------------------|
| `hosted-r2` | Una segunda región alojada, elegida entre las que ofrece el despliegue | Un id y la región. Sin credenciales |
| `customer-s3` | Un bucket que gestiona el cliente, en S3, RustFS o cualquier servicio compatible con S3 | Un id, el endpoint HTTPS, el bucket, la región de firma (por defecto `us-east-1`), un endpoint público opcional y un par de claves de acceso |

Una máquina nunca guarda las claves de un bucket de cliente. Las claves viven selladas en el servidor de cuentas, y la máquina recibe URLs prefirmadas de corta duración para el único almacén que nombra su sesión.

### Registrar un almacén

El registro es una llamada a la API de la cuenta, no un comando de `rdc`. `POST /backups/stores` registra un almacén, `GET /backups/stores` lista los registrados y `DELETE /backups/stores/<id>` retira uno. Registrar, rotar y retirar requieren un token de API con el scope `backup:manage` creado por un propietario o administrador actual de la organización, y cada operación queda auditada. Listar requiere `backup:read`.

El servidor comprueba un almacén antes de aceptarlo.

- **Sonda de conformidad.** El servidor ejecuta las mismas comprobaciones que supera un almacén alojado. Un almacén que no aplica checksums se rechaza al registrarlo, en lugar de descubrirlo en el primer backup.
- **Sonda de borrado.** La sonda también intenta borrar. Si el almacén lo rechaza, se registra con la limpieza desactivada (véase más abajo).
- **Reglas de endpoint.** Solo HTTPS, puerto 443 y ningún endpoint en una red interna.
- **Límite de almacenes.** El número de almacenes por suscripción depende del plan, incluido `home` y sin contar los almacenes retirados.

| Plan | Almacenes |
|------|-----------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

Registrar un id que ya existe solo rota sus credenciales y nada más, y la sonda se ejecuta de nuevo. Un almacén cuyas credenciales dejan de funcionar queda marcado como suspendido por la primera concesión rechazada. `GET /backups/stores` muestra el endpoint, el bucket y los últimos caracteres del id de la clave, nunca un secreto.

Un almacén no se puede retirar mientras un destino activado todavía lo nombre, y `home` no se puede retirar.

## Indicar el almacén de un destino

Un destino indica su almacén con `--target`, que se usa junto con `--destination`:

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| Opción | Descripción |
|--------|-------------|
| `--destination <name>` | El destino que se crea o se modifica |
| `--target <storeId>` | Id del almacén registrado en el que escribe el destino (por defecto `home`). Requiere `--destination` |

Dos destinos activados de una misma estrategia no pueden nombrar el mismo almacén, y un almacén que no está registrado se rechaza mostrando la lista de ids registrados.

Cada ejecución programada toma un snapshot por destino activado, en el orden en que se declararon los destinos, cada uno con su propio límite de ancho de banda. Cada snapshot es un reflink copy-on-write nuevo, así que cada uno es un punto en el tiempo consistente por sí mismo. Un destino que falla no hace que se salte el siguiente. La unidad sigue terminando con código distinto de cero cuando algún destino ha fallado, de modo que systemd y la comprobación de ejecuciones perdidas ven el fallo.

## Restaurar desde un almacén

`rdc backup restore`, `rdc backup restore --path`, `rdc backup browse --at` y `rdc backup download --store` aceptan `--from <storeId>`:

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

Sin `--from`, la CLI pregunta al servidor de cuentas qué almacenes contienen el linaje del repositorio, ordenados con primero el almacén cuyo snapshot más reciente superó su última verificación, y los prueba en ese orden. Un almacén sin snapshots se omite. Si no se puede leer el ranking, la restauración usa `home` y lo indica.

Sin `--from`, `backup restore`, `restore --path`, `browse --at` y `download --store` empiezan por el primer almacén de ese ranking y pasan al siguiente cuando el fallo es del almacén: un error del servidor, una concesión o sesión rechazada, o un endpoint que no responde. Cada uno indica qué almacén lo atendió. Ninguno recurre a otro almacén por un fallo del propio snapshot. Un snapshot ausente, caducado o dañado se ve igual en todos los almacenes, así que se muestra el error. Un comando con `--from` lee solo ese almacén y nunca recurre a otro.

Un id de snapshot indicado sin `--from` se busca en todos los almacenes del linaje.

## Estado por destino

`rdc backup status` imprime una fila por destino junto a la tabla de programación:

| Columna | Significado |
|---------|-------------|
| Store | El id del almacén en el que escribe el destino |
| Last run | Cuándo terminó la última ejecución para ese almacén |
| Result | El resultado de esa ejecución |
| Newest snapshot | El snapshot más reciente que contiene el almacén |
| Verify | El resultado de la última verificación del almacén |
| Clean-up | `enabled`, o desactivada con el motivo |

Un almacén sobre el que la cuenta no puede informar muestra `-` en sus columnas. La comprobación de ejecuciones perdidas se hace por almacén, así que un almacén que dejó de recibir backups lanza su propia alarma mientras los demás siguen en verde.

## Qué cuenta para la cuota

Los almacenes alojados, `home` y cualquier segunda región, se miden por bytes únicos almacenados físicamente, y sus bytes cuentan para la misma cuota del plan. `rdc backup usage` los muestra.

Rediacc no almacena los bytes de un bucket de cliente y no cuentan para la cuota. Los metadatos que la cuenta guarda para él (filas de manifiesto, ejecuciones de verificación y objetos de índice) se miden igual que los de un almacén alojado.

## Almacenes con la limpieza desactivada

Un almacén cuyo borrado se rechaza conserva todos los objetos. La retención y la recolección de basura nunca borran de él. Cuando un snapshot caduca, el barrido lo marca como caducado en la cuenta, deja de ofrecerlo para restaurar y deja sus objetos en el bucket.

`rdc backup status` y el resumen de salud de los backups informan del almacén como limpieza desactivada. El bucket sigue creciendo hasta que se añaden credenciales de borrado registrando de nuevo el mismo id con claves que puedan borrar.
