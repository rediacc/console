---
title: "Kubernetes"
description: "Ejecuta Kubernetes con la mentalidad de repo de Rediacc: bifurca o mueve un clúster en ejecución, incluidos sus datos, a otra máquina o centro de datos con un cutover corto."
category: "Guides"
tags:
  - containers
  - migration
subcategory: workloads
order: 6
language: es
sourceHash: "22eef465dfd46ccf"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

# Kubernetes

Rediacc integra Kubernetes en el producto sin renunciar a la mentalidad de repo sobre la que se construye el resto de la plataforma. La afirmación diferenciadora es directa: puedes **bifurcar o mover un clúster en ejecución, incluidos sus datos, a otra máquina o centro de datos con un cutover corto**. Esto no es una migración de detener-y-restaurar ni magia de cero inactividad. Las cargas de trabajo se reinician en el destino, el cutover se mide en segundos y los datos viajan con ellas.

Kubernetes funciona con [k3s](https://k3s.io/), una distribución de Kubernetes certificada, embebida en renet de la misma forma que los demás binarios del lado del servidor.

## El Modelo de Objetos

Rediacc invierte la imagen habitual de "el clúster lo envuelve todo" para que la mentalidad de repo siga aplicándose:

- **Un clúster es el contenedor.** Una máquina aloja repos Docker (sin cambios) y/o clústeres. Un clúster de un solo nodo en una máquina conserva la historia de "un archivo mueve todo el sistema" a nivel de clúster. El estado del clúster (el directorio de datos de k3s: su datastore embebido y containerd) vive en archivos de imagen copy-on-write respaldados por el datastore, uno por nodo, con el `--data-dir` de k3s vinculado dentro del montaje de la imagen.
- **Un repo de Kubernetes es un namespace.** `rdc repo create <repo> -m <name>` crea un repo cuyo hogar en tiempo de ejecución es el namespace de Kubernetes `<repo>` dentro de ese clúster.
- **Los volúmenes persistentes son unidades copy-on-write separadas.** Los PV son imágenes RBD en Ceph, o pequeños archivos de imagen del datastore mediante un aprovisionador de PV local de renet en el backend local. Nunca son directorios dentro de una imagen de clúster opaca: el sistema de archivos interno no tiene reflinks, por lo que las bifurcaciones independientes por repo requieren imágenes de PV independientes.

Esta separación es lo que hace físicamente posibles ambas promesas a la vez: **bifurcaciones de namespace siempre copy-on-write** (los datos de cada repo se clonan de forma independiente) y **portabilidad de clúster completo** (las imágenes del clúster más cada imagen de PV se mueven juntas).

| Concepto | Repo Docker | Repo Kubernetes |
|---|---|---|
| Hogar en tiempo de ejecución | Daemon Docker aislado | Namespace en un clúster |
| Env inyectado | `DOCKER_HOST` | `KUBECONFIG` |
| Wrapper de despliegue | `renet compose` | `renet kube` |
| Unidad de datos | Una imagen LUKS | Imágenes del clúster más imágenes por PV |
| Unidad de bifurcación | La imagen del repo | El namespace más sus clones de PV |
| Clonación de todo el lugar | (el repo es el lugar) | `rdc cluster fork` / `rdc cluster migrate` |

## Declarar y Crear un Clúster

Un clúster es un conjunto con nombre de pools de nodos en una red privada. Decláralo primero en la configuración, luego aprovisiónalo.

```bash
# Declarar un clúster con pools (nada se aprovisiona todavía)
rdc cluster create prod --declare-only \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# Aprovisionar los miembros del pool, arrancar renet en cada uno, instalar componentes (Ceph primero)
rdc cluster create prod
```

Los roles de pool son `ceph`, `k8s-server`, `k8s-agent` e `hyperconverged` (opt-in explícito, ya que los objetivos de memoria de Ceph y los umbrales de desalojo del kubelet compiten por RAM). Cada pool lleva la asimetría de hardware como parámetros de tamaño y disco por pool: nodos Ceph intensivos en disco, nodos Kubernetes intensivos en CPU/RAM.

Los miembros del pool se materializan en `resources.machines` como `<cluster>-<pool>-<n>` con una referencia inversa, de modo que **cada comando `-m` existente funciona con ellos**: `rdc machine status`, `rdc term connect`, los comandos de repo y las estrategias de copia de seguridad ven los nodos del clúster como máquinas ordinarias.

Los proveedores de nube aprovisionan mediante [OpenTofu](https://opentofu.org/), siguiendo el mismo registro `ProviderMapping` que usa `rdc machine provision`, extendido con un bloque de red privada (VLAN o VPC, la MTU a establecer, la nomenclatura de la NIC privada). El KVM local es la vía de prueba siempre disponible mediante `rdc ops`.

```bash
# Inspeccionar clústeres
rdc cluster status                 # listar todos los clústeres
rdc cluster status prod     # configuración completa de un clúster

# Aumentar o reducir un pool (agrega/elimina máquinas, une/drena nodos)
rdc cluster scale prod --pool k8s --count 5


# Desmontar los miembros aprovisionados y eliminar el clúster de la configuración
rdc cluster destroy prod
```

### Obtener un kubeconfig

El kubeconfig nunca se almacena en tu archivo de configuración (es grande y rota). Se obtiene bajo demanda por SSH y se cachea localmente con permisos `0600`, siguiendo el mismo patrón de estado lateral que los directorios de trabajo de OpenTofu y la caché de certificados.

```bash
rdc cluster kubeconfig prod
# Imprime: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Repositorios de Kubernetes

La bandera de destino decide el tiempo de ejecución. No hay bandera de tipo.

```bash
# Repo Docker (sin cambios): un daemon Docker aislado en una máquina
rdc repo create shop -m server-1 --size 10G

# Repo Kubernetes: namespace "shop" más su almacenamiento, dentro de un clúster
rdc repo create shop --datastore prod --size 10G
```

Los verbos de repo son la única superficie para el trabajo a nivel de repo. A través del embudo de resolución de destino, prácticamente todo el conjunto de comandos de repo se vuelve compatible con clústeres: `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status` y `log` aceptan todos `--cluster`. Un destino de clúster se resuelve a su nodo de control más el contexto KUBECONFIG fijado al namespace del repo, el análogo de resolver una máquina a `DOCKER_HOST` más un directorio de trabajo.

```bash
rdc repo sync upload shop --local ./config
rdc cluster kubeconfig prod           # exportar KUBECONFIG, luego usar kubectl directamente
```

Los nodos del clúster también se materializan en `resources.machines`, por lo que puedes conectarte por SSH a un nodo específico con el `rdc term connect <cluster>-<pool>-<n>` habitual.

### Rediaccfile de doble tiempo de ejecución

La portabilidad entre Docker y Kubernetes se apoya en una convención, no en una conversión automática de manifiestos. Un repo que ofrece tanto una ruta `renet compose` como una ruta `renet kube` bajo las mismas funciones `up()` y `down()` migra libremente en ambas direcciones, porque las convenciones del directorio de datos son idénticas. renet inyecta `DOCKER_HOST` en un destino de máquina y `KUBECONFIG` en un destino de clúster; `up()` lee cuál está establecido y actúa en consecuencia.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # tiempo de ejecución Kubernetes
  else
    renet compose -- up -d             # tiempo de ejecución Docker
  fi
}
```

Un repo al que le falta el tiempo de ejecución de destino recibe un rechazo claro **después** de la etapa de transferencia de datos: las imágenes se mueven, y el paso de despliegue te indica que el repo no declara una ruta de Kubernetes (o Docker), en lugar de corromper el estado.

## Bifurcar un Repositorio

`rdc repo fork` en un repo de Kubernetes siempre copia datos, siempre al instante. No hay bandera `--full` ni variantes.

```bash
rdc repo fork shop --tag joseph
```

Esto crea el namespace `shop-joseph` en el mismo clúster, clona cada volumen de forma copy-on-write (un clon RBD en Ceph, un reflink de los archivos de imagen de PV en el backend local) y despliega las cargas de trabajo allí. La URL de la bifurcación está activa al instante bajo el certificado comodín del padre, por lo que no se emite ningún certificado o registro DNS nuevo.

Escalada de destino:

- `--to-cluster <name>` bifurca hacia otro clúster existente. Mismo backend Ceph: el clon RBD permanece copy-on-write. Backend diferente: la maquinaria de push mueve las imágenes.
- `--provider <p>` aprovisiona primero un nuevo clúster, con especificaciones de pool que por defecto reflejan la forma del clúster de origen (las banderas la anulan).

Medido en el laboratorio de pruebas KVM, una bifurcación de namespace se completa en aproximadamente uno a cinco segundos con la carga de trabajo del padre intacta y los dos namespaces divergiendo de forma independiente.

## Bifurcar o Mover un Clúster Completo

Las operaciones de clúster completo residen en el grupo `rdc cluster`, porque actúan sobre un objeto diferente (todo el lugar con todos sus repos) y no pueden expresarse mediante un comando que toma un único nombre de repo. Esta es la historia insignia.

```bash
# Clonar un clúster completo, incluidos los datos de sus repos, en un clúster nuevo
rdc cluster fork prod --to spare --tag staging

# Mover un clúster completo, incluidos los datos de sus repos, a otra máquina o centro de datos
rdc cluster migrate prod --to spare
```

Ambos coordinan un copy-on-write de las imágenes del clúster más cada imagen de PV de repo, y luego reescriben la identidad del nodo para que el clon o el clúster reubicado arranque saludable en sus nuevas direcciones. Dado que k3s almacena el estado del plano de control en su datastore embebido, la imagen del clúster en sí misma es la instantánea: el orden de consistencia es primero el plano de control, luego los PV, luego los agentes.

Las cifras honestas, medidas de extremo a extremo en el laboratorio de pruebas KVM:

| Operación | Qué hace | Medido |
|---|---|---|
| Bifurcación de namespace | Clonar el namespace de un repo más sus PV in situ | ~1 a 5 s |
| Bifurcación RBD de una sola imagen | Copiar un clon de PV respaldado por Ceph de forma copy-on-write | ~5 s |
| Bifurcación de un clúster completo de 2 nodos | Drenar, reflinkar el plano de control y el agente, reescribir la identidad a nuevas IPs, padre intacto | ~46 s |
| Migración de clúster entre máquinas | Precopia en caliente más el cutover de detener-y-reiniciar | ~16 s de cutover |

El comportamiento predeterminado es **consistente ante fallos e íntegro referencialmente**: la misma semántica que un ciclo de apagado/encendido, que es lo que ven las cargas de trabajo. Las instantáneas consistentes a nivel de aplicación están disponibles cuando los sistemas de archivos de la carga de trabajo se congelan durante la copia. Esto deliberadamente **no** se presenta como cero inactividad. Nadie más ofrece "bifurcar un clúster en ejecución incluidos sus datos" en absoluto; el planteamiento honesto es un cutover corto y medido en lugar de un absoluto de marketing.

## Almacenamiento: ceph-csi y Volúmenes Persistentes

Ceph es aprovisionado por el flujo cephadm de renet en el pool `ceph`, **fuera** de cualquier clúster de Kubernetes, y los clústeres lo consumen mediante manifiestos ceph-csi generados por plantillas de renet. Cada instancia de clúster (y cada bifurcación) obtiene su propio espacio de nombres RBD/RADOS, que es la primitiva de aislamiento por inquilino. El almacenamiento está por debajo de todos los clústeres, por lo que también respalda los repos Docker sencillos y el backend del datastore, y una bifurcación de clúster clona imágenes RBD por debajo de Kubernetes en lugar de bifurcar su propio backend de almacenamiento.

En el backend local (sin Ceph), un aprovisionador de PV local de renet respalda cada PV con un pequeño archivo de imagen copy-on-write en el datastore, clonado por reflink en cada bifurcación. Consulta [Referencia del Servidor](/es/docs/server-reference) para el diseño en disco y los comandos de renet.

## Elegir una Distribución

La distro es una abstracción con una interfaz pequeña y real (install, join, kubeconfig, healthcheck, upgrade, etc.):

- **k3s** es la predeterminada y la única distribución embebida. Es Apache-2.0, certificada por la CNCF, un único binario reubicable, y tanto su Traefik incluido como ServiceLB están deshabilitados en favor del proxy de Rediacc. Su `--data-dir` se vincula al inicio, que es exactamente lo que necesitan la bifurcación y la migración de clústeres cuando cambia la ruta de montaje de la imagen. k3s está marcada como `repoEmbeddable`.
- **external** es traer tu propio kubeconfig. Solo `getKubeconfig` y `healthcheck` hacen trabajo real; los verbos de ciclo de vida devuelven resultados de primera clase de "no aplicable" en lugar de errores.
- **RKE2** es el tercer backend planeado para clientes FIPS/CIS, no forma parte de este lanzamiento.

La bifurcación y la migración de clústeres se niegan a ejecutarse en una distribución no `repoEmbeddable` con un error claro en lugar de corromper el estado, porque embeber el estado del clúster en imágenes del datastore requiere un data-dir que se vincule al inicio.

## Registro

Dos problemas de imágenes distintos, dos herramientas:

- **Dolor upstream** (límites de tasa de Docker Hub, pulls denegados, sin conexión): una caché pull-through [zot](https://zotregistry.dev/) embebida se ejecuta en el pool de control con `sync.onDemand` contra múltiples upstreams (docker.io, ghcr.io, quay.io). Está embebida en renet de la misma forma que los demás binarios, y reemplaza el registro de pruebas de ops para que cada ejecución la ejerza.
- **Distribución intra-clúster**: el mirror de registro embebido de k3s permite que los nodos compartan imágenes ya extraídas de igual a igual.

El cableado es transparente y no requiere reinicio mediante el `certs.d/hosts.toml` de containerd y el `registries.yaml` de k3s. El almacén de containerd por repo dentro de la imagen del clúster sigue siendo la fuente de verdad que bifurcaciones y migraciones mueven; el registro es una caché frente a internet, nunca estado.

## Redes y URLs

Las URLs de los repos de Kubernetes siguen el esquema plano, con la identidad del namespace plegada en la etiqueta más a la izquierda y el clúster como la segunda etiqueta estable:

```
{service}--{repo}.{cluster}.{machine}.{base}          Repo Kubernetes (namespace = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    bifurcación (namespace = repo-tag)
```

Cada namespace y cada bifurcación hereda el certificado comodín y el registro DNS del padre, por lo que las URLs de bifurcación están activas al instante y solo se emiten certificados nuevos cuando se crea un clúster o repo nuevo. El router descubre los servicios de Kubernetes sondeando el clúster en busca de Services anotados con `rediacc.*`, el análogo de Kubernetes a leer etiquetas de Docker. Consulta [Redes](/es/docs/networking) para el modelo de enrutamiento y [Arquitectura](/es/docs/architecture) para los backends de almacenamiento.

## Atribución

Rediacc transporta varios binarios de terceros (k3s, zot y los demás que renet embebe). Imprime sus versiones, identificadores de licencia SPDX y URLs de archivo fuente en cualquier momento:

```bash
rdc credits
rdc credits --licenses    # texto completo de THIRD_PARTY_LICENSES incluido con los lanzamientos
```
