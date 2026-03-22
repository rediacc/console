---
title: Suscripción y licencias
description: Entender cómo account, rdc y renet gestionan los slots de máquina, las licencias de repositorio y los límites del plan.
category: Guides
order: 7
language: es
sourceHash: "fcc4e06609545bf7"
---

# Suscripción y licencias

El licenciamiento de Rediacc tiene tres partes móviles:

- `account` firma los derechos y rastrea el uso
- `rdc` autentica, solicita licencias, las entrega a las máquinas y las aplica en tiempo de ejecución
- `renet` (el entorno de ejecución en la máquina) valida las licencias instaladas localmente sin llamar al servidor de cuentas

Esta página explica cómo encajan estas piezas en las implementaciones locales.

## Qué hace el licenciamiento

El licenciamiento controla dos cosas diferentes:

- **Contabilidad de acceso a máquinas** a través de **Licencias flotantes**
- **Autorización de tiempo de ejecución de repositorios** a través de **licencias de repositorio**

Estos están relacionados, pero no son el mismo artefacto.

## Cómo funciona el licenciamiento

`account` es la fuente de verdad para planes, anulaciones de contratos, estado de activación de máquinas e issuances mensuales de licencias de repositorio.

`rdc` se ejecuta en tu estación de trabajo. Te autentica en el servidor de cuentas, solicita las licencias que necesita y las instala en máquinas remotas a través de SSH. Cuando ejecutas un comando de repositorio, `rdc` se asegura de que las licencias requeridas estén en su lugar y las valida en la máquina en tiempo de ejecución.

El flujo normal se ve así:

1. Te autenticas con `rdc subscription login`
2. Ejecutas un comando de repositorio como `rdc repo create`, `rdc repo up` o `rdc repo down`
3. Si la licencia requerida falta o ha expirado, `rdc` la solicita a `account`
4. `rdc` escribe la licencia firmada en la máquina
5. La licencia se valida localmente en la máquina y la operación continúa

Consulta [rdc vs renet](/es/docs/rdc-vs-renet) para la división estación de trabajo/servidor, y [Repositorios](/es/docs/repositories) para el ciclo de vida del repositorio en sí.

Para automatización y agentes de IA, usa un token de suscripción con alcance limitado en lugar del inicio de sesión del navegador:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

También puedes inyectar el token directamente a través del entorno para que el CLI pueda emitir y renovar licencias de repositorio sin ningún paso de inicio de sesión interactivo:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Licencias de máquina vs. Licencias de repositorio

### Activación de máquina

La activación de máquina cumple un doble papel:

- **En el lado del servidor**: contabilidad de slots de máquinas flotantes, verificaciones de activación a nivel de máquina, vinculación de la emisión de repositorios respaldada por la cuenta a una máquina específica
- **En disco**: `rdc` escribe un blob de suscripción firmado en `/var/lib/rediacc/license/machine.json` durante la activación. Este blob se valida localmente para operaciones de aprovisionamiento (`rdc repo create`, `rdc repo fork`). La licencia de máquina es válida por 1 hora desde la última activación.

### Licencia de repositorio

Una licencia de repositorio es una licencia firmada para un repositorio en una máquina.

Se usa para:

- `rdc repo resize` y `rdc repo expand` — validación completa incluyendo expiración
- `rdc repo up`, `rdc repo down`, `rdc repo delete` — validado con **expiración omitida**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync` — validado con **expiración omitida**
- autoarranque del repositorio al reiniciar la máquina — validado con **expiración omitida**

Las licencias de repositorio están vinculadas a la máquina y al repositorio de destino, y Rediacc refuerza ese vínculo con metadatos de identidad del repositorio. Para repositorios cifrados, eso incluye la identidad LUKS del volumen subyacente.

En la práctica:

- la activación de máquina responde: "¿puede esta máquina aprovisionar nuevos repositorios?"
- la licencia de repositorio responde: "¿puede este repositorio específico ejecutarse en esta máquina específica?"

## Límites predeterminados

El tamaño del repositorio depende del nivel de derechos:

- Community: hasta `10 GB`
- planes de pago: límite del plan o contrato

Límites predeterminados de los planes de pago:

| Plan | Licencias flotantes | Tamaño del repositorio | Issuances mensuales de licencias de repositorio |
|------|---------------------|------------------------|--------------------------------------------------|
| Community | 2 | 10 GB | 500 |
| Professional | 5 | 100 GB | 5.000 |
| Business | 20 | 500 GB | 20.000 |
| Enterprise | 50 | 2048 GB | 100.000 |

Los límites específicos del contrato pueden aumentar o disminuir estos valores para un cliente específico.

## Qué ocurre durante la creación, arranque, parada y reinicio del repositorio

### Crear y bifurcar repositorio

Cuando creas o bifurcas un repositorio:

1. `rdc` se asegura de que tu token de suscripción esté disponible (activa la autenticación por código de dispositivo si es necesario)
2. `rdc` activa la máquina y escribe el blob de suscripción firmado en la máquina remota
3. La licencia de máquina se valida localmente (debe estar dentro de 1 hora desde la activación)
4. Después de la creación exitosa, `rdc` emite la licencia de repositorio para el nuevo repositorio

Esa emisión respaldada por la cuenta cuenta para tu uso mensual de **issuances de licencias de repositorio**.

### Arrancar, parar y eliminar repositorio

`rdc` valida la licencia de repositorio instalada en la máquina pero **omite la verificación de expiración**. La firma, el ID de máquina, el GUID del repositorio y la identidad se siguen verificando. Los usuarios nunca quedan bloqueados de operar sus repositorios, incluso con una suscripción expirada.

### Redimensionar y expandir repositorio

`rdc` realiza una validación completa de la licencia de repositorio incluyendo expiración y límites de tamaño.

### Reinicio de máquina y autoarranque

El autoarranque usa las mismas reglas que `rdc repo up` — la expiración se omite, por lo que los repositorios siempre se reinician libremente.

Las licencias de repositorio usan un modelo de validez de larga duración:

- `refreshRecommendedAt` es el punto de actualización suave
- `hardExpiresAt` es el punto de bloqueo

Si la licencia del repositorio está desactualizada pero todavía antes de la expiración definitiva, el tiempo de ejecución puede continuar. Una vez que alcanza la expiración definitiva, `rdc` debe actualizarla para operaciones de resize/expand.

### Otras operaciones de repositorio

Las operaciones como listar repositorios, inspeccionar información del repositorio y montar no requieren ninguna validación de licencia.

## Comprobar el estado y renovar licencias

Inicio de sesión humano:

```bash
rdc subscription login
```

Inicio de sesión para automatización o agente de IA:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Para entornos no interactivos, establecer `REDIACC_SUBSCRIPTION_TOKEN` es la opción más sencilla. El token debe tener alcance limitado solo para las operaciones de suscripción y licencias de repositorio que necesita el agente.

Mostrar el estado de suscripción respaldado por la cuenta:

```bash
rdc subscription status
```

Mostrar los detalles de activación de máquina para una máquina:

```bash
rdc subscription activation status -m hostinger
```

Mostrar los detalles de licencia de repositorio instalados en una máquina:

```bash
rdc subscription repo status -m hostinger
```

Renovar la activación de máquina y actualizar licencias de repositorio en lote:

```bash
rdc subscription refresh -m hostinger
```

Los repositorios descubiertos en la máquina pero que faltan en la configuración local de `rdc` se rechazan durante la actualización en lote. Se reportan como fallos y no se clasifican automáticamente.

Forzar una renovación de licencia de repositorio para un repositorio existente:

```bash
rdc subscription refresh repo my-app -m hostinger
```

En el primer uso, una operación de repositorio o copia de seguridad con licencia que no encuentra una licencia de repositorio utilizable puede activar automáticamente una transferencia de autorización de cuenta. El CLI imprime una URL de autorización, intenta abrir el navegador en terminales interactivas y reintenta la operación una vez después de que la autorización y la emisión tengan éxito.

En entornos no interactivos, el CLI no espera la aprobación del navegador. En cambio, te indica que proporciones un token con alcance limitado con `rdc subscription login --token ...` o `REDIACC_SUBSCRIPTION_TOKEN`.

Para la configuración inicial de la máquina, consulta [Configuración de máquina](/es/docs/setup).

## Comportamiento sin conexión y expiración

La validación de licencias ocurre localmente en la máquina — no requiere conectividad en vivo con el servidor de cuentas.

Eso significa:

- un entorno en ejecución no necesita conectividad en vivo con la cuenta en cada comando
- todos los repositorios siempre pueden iniciarse, detenerse y eliminarse incluso con licencias expiradas — los usuarios nunca quedan bloqueados de operar sus propios repositorios
- las operaciones de aprovisionamiento (`create`, `fork`) requieren una licencia de máquina válida, y las operaciones de crecimiento (`resize`, `expand`) requieren una licencia de repositorio válida
- las licencias de repositorio verdaderamente expiradas deben actualizarse a través de `rdc` antes de resize/expand

La activación de máquina y las licencias de tiempo de ejecución de repositorio son superficies separadas. Una máquina puede estar inactiva en el estado de cuenta mientras algunos repositorios aún tienen licencias de repositorio instaladas válidas. Cuando eso ocurre, inspecciona ambas superficies por separado en lugar de asumir que significan lo mismo.

## Comportamiento de recuperación

La recuperación automática es intencionalmente estrecha:

- `missing`: `rdc` puede autorizar el acceso a la cuenta si es necesario, actualizar licencias de repositorio en lote y reintentar una vez
- `expired`: `rdc` puede actualizar licencias de repositorio en lote y reintentar una vez
- `machine_mismatch`: falla rápidamente y te indica que vuelvas a emitir desde el contexto de máquina actual
- `repository_mismatch`: falla rápidamente y te indica que actualices las licencias de repositorio explícitamente
- `sequence_regression`: falla rápidamente como un problema de integridad/estado de la licencia de repositorio
- `invalid_signature`: falla rápidamente como un problema de integridad/estado de la licencia de repositorio
- `identity_mismatch`: falla rápidamente — la identidad del repositorio no coincide con la licencia instalada

Estos casos de fallo rápido no consumen automáticamente llamadas de actualización o emisión respaldadas por la cuenta.

## Issuances mensuales de licencias de repositorio

Esta métrica cuenta la actividad exitosa de issuance de licencias de repositorio respaldadas por la cuenta en el mes del calendario UTC actual.

Incluye:

- issuance de licencia de repositorio por primera vez
- renovación exitosa de licencia de repositorio que devuelve una licencia recién firmada

No incluye:

- entradas de lote sin cambios
- intentos de issuance fallidos
- repositorios no rastreados rechazados antes de la issuance

Si necesitas una vista de uso e historial reciente de issuance de licencias de repositorio orientada al cliente, usa el portal de cuentas. Si necesitas inspección en el lado de la máquina, usa `rdc subscription activation status -m` y `rdc subscription repo status -m`.
