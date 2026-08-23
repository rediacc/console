---
title: "Kubernetes"
description: "Exécutez Kubernetes avec la mentalité du dépôt Rediacc : forkez ou déplacez un cluster en cours d'exécution, données comprises, vers une autre machine ou un autre datacenter avec une bascule courte."
category: "Guides"
tags:
  - containers
  - migration
subcategory: workloads
order: 6
language: fr
sourceHash: "22eef465dfd46ccf"
sourceCommit: "4401262fffbf29b9480dee8ecd209013e4b87f60"
---

# Kubernetes

Rediacc intègre Kubernetes au produit sans abandonner la mentalité du dépôt sur laquelle repose le reste de la plateforme. L'affirmation qui fait la différence est directe : vous pouvez **forker ou déplacer un cluster en cours d'exécution, données comprises, vers une autre machine ou un autre datacenter avec une bascule courte**. Ce n'est ni une migration à base d'arrêt-restauration, ni une magie zéro-downtime. Les workloads redémarrent sur la destination, la bascule se mesure en secondes, et les données suivent.

Kubernetes est propulsé par [k3s](https://k3s.io/), une distribution Kubernetes certifiée, embarquée dans renet de la même façon que les autres binaires côté serveur.

## Le modèle d'objet

Rediacc inverse l'image habituelle « le cluster englobe tout » pour que la mentalité du dépôt continue de s'appliquer :

- **Un cluster est le conteneur.** Une machine héberge des dépôts Docker (inchangés) et/ou des clusters. Un cluster à un seul nœud sur une machine conserve, au niveau du cluster, l'histoire du « un seul fichier déplace tout le système ». L'état du cluster (le répertoire de données k3s : son datastore embarqué et containerd) vit dans des fichiers image copy-on-write adossés au datastore, un par nœud, avec le `--data-dir` de k3s lié à l'intérieur du mount de l'image.
- **Un dépôt Kubernetes est un namespace.** `rdc repo create <repo> -m <name>` crée un dépôt dont le foyer d'exécution est le namespace Kubernetes `<repo>` à l'intérieur de ce cluster.
- **Les volumes persistants sont des unités copy-on-write séparées.** Les PV sont des images RBD sur Ceph, ou de petits fichiers image du datastore via un provisioner de PV local sur le backend local. Ce ne sont jamais des répertoires à l'intérieur d'une seule image de cluster opaque : le système de fichiers interne n'a pas de reflinks, donc des forks de dépôt indépendants exigent des images de PV indépendantes.

Cette séparation est ce qui rend les deux promesses physiquement possibles à la fois : des **forks de namespace toujours copy-on-write** (les données de chaque dépôt se clonent indépendamment) et une **portabilité du cluster entier** (les images du cluster plus chaque image de PV se déplacent ensemble).

| Concept | Dépôt Docker | Dépôt Kubernetes |
|---|---|---|
| Foyer d'exécution | Daemon Docker isolé | Namespace dans un cluster |
| Env injecté | `DOCKER_HOST` | `KUBECONFIG` |
| Wrapper de déploiement | `renet compose` | `renet kube` |
| Unité de données | Une image LUKS | Images du cluster plus images par PV |
| Unité de fork | L'image du dépôt | Le namespace plus ses clones de PV |
| Clone du lieu entier | (le dépôt est le lieu) | `rdc cluster fork` / `rdc cluster migrate` |

## Déclarer et créer un cluster

Un cluster est un ensemble nommé de pools de nœuds sur un réseau privé. Déclarez-le d'abord en configuration, puis provisionnez-le.

```bash
# Déclarer un cluster avec des pools (rien n'est encore provisionné)
rdc cluster create prod --declare-only \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# Provisionner les membres des pools, bootstrapper renet sur chacun, installer les composants (Ceph en premier)
rdc cluster create prod
```

Les rôles de pool sont `ceph`, `k8s-server`, `k8s-agent`, et `hyperconverged` (opt-in explicite, car les cibles mémoire de Ceph et les seuils d'éviction du kubelet se disputent la RAM). Chaque pool porte l'asymétrie matérielle sous forme de taille et de paramètres disque par pool : des nœuds Ceph riches en disque, des nœuds Kubernetes riches en CPU/RAM.

Les membres d'un pool se matérialisent dans `resources.machines` sous la forme `<cluster>-<pool>-<n>` avec une référence retour, si bien que **toutes les commandes `-m` existantes fonctionnent sur eux** : `rdc machine status`, `rdc term connect`, les commandes repo, et les stratégies de sauvegarde voient tous les nœuds de cluster comme des machines ordinaires.

Les fournisseurs cloud provisionnent via [OpenTofu](https://opentofu.org/), en suivant le même registre `ProviderMapping` que `rdc machine provision` utilise, étendu avec un bloc réseau privé (VLAN ou VPC, le MTU à appliquer, le nommage de la carte réseau privée). Le KVM local est le chemin de test toujours disponible via `rdc ops`.

```bash
# Inspecter les clusters
rdc cluster status                 # lister tous les clusters
rdc cluster status prod     # configuration complète d'un cluster

# Agrandir ou réduire un pool (ajoute/retire des machines, fait rejoindre/évacuer des nœuds)
rdc cluster scale prod --pool k8s --count 5


# Détruire les membres provisionnés et retirer le cluster de la configuration
rdc cluster destroy prod
```

### Obtenir un kubeconfig

Le kubeconfig n'est jamais stocké dans votre fichier de configuration (il est volumineux et tourne). Il est récupéré à la demande via SSH et mis en cache localement avec les permissions `0600`, suivant le même schéma d'état annexe que les workdirs OpenTofu et le cache de certificats.

```bash
rdc cluster kubeconfig prod
# Affiche : export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Dépôts Kubernetes

Le drapeau de cible décide du runtime. Il n'y a pas de drapeau de type.

```bash
# Dépôt Docker (inchangé) : un daemon Docker isolé sur une machine
rdc repo create shop -m server-1 --size 10G

# Dépôt Kubernetes : namespace "shop" plus son stockage, dans un cluster
rdc repo create shop --datastore prod --size 10G
```

Les verbes repo constituent la surface unique pour le travail au niveau du dépôt. Grâce à l'entonnoir de résolution de cible, à peu près tout l'ensemble des commandes repo devient compatible cluster : `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status`, et `log` acceptent tous `--cluster`. Une cible cluster se résout vers son nœud de contrôle plus le contexte KUBECONFIG figé sur le namespace du dépôt, l'analogue de la résolution d'une machine vers `DOCKER_HOST` plus un répertoire de travail.

```bash
rdc repo sync upload shop --local ./config
rdc cluster kubeconfig prod           # exporter KUBECONFIG, puis utiliser kubectl directement
```

Les nœuds de cluster se matérialisent aussi dans `resources.machines`, vous pouvez donc vous connecter en SSH à un nœud spécifique avec la commande ordinaire `rdc term connect <cluster>-<pool>-<n>`.

### Rediaccfile à double runtime

La portabilité entre Docker et Kubernetes repose sur une convention, pas sur une conversion automatique de manifeste. Un dépôt qui fournit à la fois un chemin `renet compose` et un chemin `renet kube` sous les mêmes fonctions `up()` et `down()` migre librement dans les deux sens, parce que les conventions de répertoire de données sont identiques. renet injecte `DOCKER_HOST` sur une cible machine et `KUBECONFIG` sur une cible cluster ; `up()` lit lequel des deux est défini et se comporte en conséquence.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Runtime Kubernetes
  else
    renet compose -- up -d             # Runtime Docker
  fi
}
```

Un dépôt qui ne déclare pas le runtime cible reçoit un refus clair **après** l'étape de transfert des données : les images se déplacent, et l'étape de déploiement vous indique que le dépôt ne déclare pas de chemin Kubernetes (ou Docker), plutôt que de corrompre l'état.

## Forker un dépôt

`rdc repo fork` sur un dépôt Kubernetes copie toujours les données, toujours instantanément. Il n'y a pas de drapeau `--full` ni de variantes.

```bash
rdc repo fork shop --tag joseph
```

Ceci crée le namespace `shop-joseph` dans le même cluster, clone chaque volume en copy-on-write (un clone RBD sur Ceph, un reflink des fichiers image de PV sur le backend local), et y déploie les workloads. L'URL du fork est disponible instantanément sous le certificat wildcard du parent, donc aucun nouveau certificat ni enregistrement DNS n'est émis.

Escalade de destination :

- `--to-cluster <name>` forke vers un autre cluster existant. Même backend Ceph : le clone RBD reste copy-on-write. Backend différent : la mécanique de push déplace les images.
- `--provider <p>` provisionne d'abord un nouveau cluster, avec des spécifications de pool par défaut reflétant la forme du cluster source (les drapeaux prennent le dessus).

Mesuré dans le laboratoire de test KVM, un fork de namespace se termine en environ une à cinq secondes, le workload parent restant intact et les deux namespaces divergeant indépendamment.

## Forker ou déplacer un cluster entier

Les opérations sur cluster entier vivent dans le groupe `rdc cluster`, parce qu'elles agissent sur un objet différent (le lieu entier avec tous ses dépôts) et ne peuvent pas s'exprimer via une commande qui prend un seul nom de dépôt. C'est l'histoire phare.

```bash
# Cloner un cluster entier, données de ses dépôts incluses, dans un nouveau cluster
rdc cluster fork prod --to spare --tag staging

# Déplacer un cluster entier, données de ses dépôts incluses, vers une autre machine ou un autre datacenter
rdc cluster migrate prod --to spare
```

Les deux coordonnent un copy-on-write des images du cluster plus chaque image de PV de dépôt, puis réécrivent l'identité des nœuds pour que le clone ou le cluster relocalisé démarre sainement sur ses nouvelles adresses. Comme k3s stocke l'état du plan de contrôle dans son datastore embarqué, l'image du cluster est elle-même l'instantané : l'ordre de cohérence est le plan de contrôle d'abord, puis les PV, puis les agents.

Les chiffres honnêtes, mesurés de bout en bout dans le laboratoire de test KVM :

| Opération | Ce qu'elle fait | Mesuré |
|---|---|---|
| Fork de namespace | Clone le namespace d'un dépôt plus ses PV sur place | ~1 à 5 s |
| Fork d'une seule image RBD | Copy-on-write d'un clone de PV adossé à Ceph | ~5 s |
| Fork d'un cluster entier à 2 nœuds | Draine, reflink le plan de contrôle et l'agent, réécrit l'identité vers de nouvelles IPs, le parent reste intact | ~46 s |
| Migration de cluster inter-machines | Pré-copie à chaud plus la bascule d'arrêt-redémarrage | ~16 s de bascule |

La cohérence par défaut est **crash-consistante et référentiellement intacte** : la même sémantique qu'un cycle d'alimentation, ce qui est ce que voient les workloads. Des instantanés application-consistants sont disponibles quand les systèmes de fichiers du workload sont gelés pendant la copie. Ceci est délibérément **non** présenté comme du zéro-downtime. Personne d'autre ne propose « forker un cluster en cours d'exécution, données comprises » du tout ; le cadrage honnête est une bascule courte et mesurée plutôt qu'un absolu marketing.

## Stockage : ceph-csi et volumes persistants

Ceph est provisionné par le flux cephadm de renet sur le pool `ceph`, **en dehors** de tout cluster Kubernetes, et les clusters le consomment via des manifestes ceph-csi générés par renet. Chaque instance de cluster (et chaque fork) obtient son propre namespace RBD/RADOS, qui est la primitive d'isolation par tenant. Le stockage se trouve sous tous les clusters, il alimente donc aussi les simples dépôts Docker et le backend datastore, et un fork de cluster clone les images RBD en dessous de Kubernetes plutôt que de forker son propre backend de stockage.

Sur le backend local (sans Ceph), un provisioner de PV local de renet adosse chaque PV à un petit fichier image copy-on-write dans le datastore, cloné en reflink au moment du fork. Consultez [Référence serveur](/fr/docs/server-reference) pour la disposition sur disque et les commandes renet.

## Choisir une distribution

La distribution est une abstraction dotée d'une petite interface réelle (install, join, kubeconfig, healthcheck, upgrade, et ainsi de suite) :

- **k3s** est la distribution par défaut et la seule embarquée. Elle est Apache-2.0, certifiée CNCF, un seul binaire relocalisable, et son Traefik et son ServiceLB embarqués sont tous deux désactivés au profit du proxy Rediacc. Son `--data-dir` se lie au démarrage, ce qui est exactement ce dont le fork et la migration de cluster ont besoin quand le chemin de mount de l'image change. k3s est marqué `repoEmbeddable`.
- **external** consiste à apporter son propre kubeconfig. Seuls `getKubeconfig` et `healthcheck` font un vrai travail ; les verbes de cycle de vie retournent des résultats « non applicable » de premier ordre plutôt que des erreurs.
- **RKE2** est le troisième backend prévu pour les clients FIPS/CIS, non inclus dans cette version.

Le fork et la migration de cluster refusent de s'exécuter sur une distribution non `repoEmbeddable` avec une erreur claire plutôt que de corrompre l'état, parce qu'embarquer l'état du cluster dans des images de datastore exige un data-dir qui se lie au démarrage.

## Registre

Deux problèmes d'image distincts, deux outils :

- **Douleur en amont** (limites de débit Docker Hub, pulls refusés, hors ligne) : un cache pull-through [zot](https://zotregistry.dev/) embarqué tourne sur le pool de contrôle avec `sync.onDemand` contre plusieurs sources en amont (docker.io, ghcr.io, quay.io). Il est embarqué dans renet de la même façon que les autres binaires, et il remplace le registre de test des ops afin que chaque run l'exerce.
- **Distribution intra-cluster** : le miroir de registre embarqué de k3s permet aux nœuds de partager les images déjà tirées de pair à pair.

Le câblage est transparent et sans redémarrage grâce à `certs.d/hosts.toml` de containerd et au `registries.yaml` de k3s. Le magasin containerd par dépôt à l'intérieur de l'image de cluster reste la source de vérité que les forks et migrations utilisent ; le registre n'est qu'un cache devant internet, jamais de l'état.

## Réseau et URLs

Les URLs des dépôts Kubernetes suivent le schéma plat, avec l'identité du namespace repliée dans le label le plus à gauche et le cluster comme second label stable :

```
{service}--{repo}.{cluster}.{machine}.{base}          Dépôt Kubernetes (namespace = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    fork (namespace = repo-tag)
```

Chaque namespace et chaque fork hérite du certificat wildcard et de l'enregistrement DNS du parent, donc les URLs de fork sont disponibles instantanément et de nouveaux certificats ne sont émis que lorsqu'un nouveau cluster ou dépôt est créé. Le routeur découvre les services Kubernetes en interrogeant le cluster pour les Services annotés `rediacc.*`, l'analogue Kubernetes de la lecture des labels Docker. Consultez [Réseau](/fr/docs/networking) pour le modèle de routage et [Architecture](/fr/docs/architecture) pour les backends de stockage.

## Attribution

Rediacc transporte plusieurs binaires tiers (k3s, zot, et les autres que renet embarque). Affichez leurs versions, identifiants de licence SPDX, et URLs d'archive source à tout moment :

```bash
rdc credits
rdc credits --licenses    # texte complet THIRD_PARTY_LICENSES fourni avec les releases
```
