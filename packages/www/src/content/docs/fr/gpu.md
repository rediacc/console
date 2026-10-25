---
title: "GPU"
description: "Donner à un dépôt l'accès à un GPU grâce à une autorisation de périphérique CDI : lister les GPU de la machine, accorder et retirer des périphériques par dépôt, réserver une carte en exclusivité et travailler sous WSL."
category: "Guides"
tags:
  - gpu
  - containers
subcategory: workloads
order: 7
language: fr
sourceHash: "5a113ad69c52c63d"
---

# GPU

Un dépôt n'atteint un GPU que par une **autorisation de périphérique**. La machine publie les GPU dont elle dispose sous forme de périphériques nommés, et un opérateur accorde à un dépôt les noms qu'il peut utiliser. Un dépôt sans autorisation n'obtient aucun GPU, et un [fork](/fr/docs/repositories) démarre sans autorisation, même si son parent en a une.

Les noms suivent le Container Device Interface (CDI), la norme que Docker 25 et les versions suivantes utilisent pour décrire un périphérique et tout ce dont un conteneur a besoin pour s'en servir. Un nom CDI a la forme `<vendor>/<class>=<device>`, par exemple `nvidia.com/gpu=all`.

## Ce qu'est une autorisation CDI

Chaque dépôt exécute son propre démon Docker derrière une passerelle d'API qui refuse toutes les façons d'attacher du matériel à un conteneur : un GPU ne s'obtient donc pas avec des options de `docker run`. L'autorisation est la seule porte. Elle enregistre un nom CDI exact pour un dépôt, et la passerelle accepte alors une requête de conteneur qui nomme ce périphérique et rien d'autre.

- Une autorisation prend effet à la requête Docker suivante, sans redémarrage du démon.
- Une autorisation désigne exactement un périphérique. Accorder `nvidia.com/gpu=all` admet `nvidia.com/gpu=all` et non `nvidia.com/gpu=0`. Pour donner une seule carte à un dépôt, il faut accorder le nom de cette carte.
- À l'écriture, une autorisation est vérifiée par rapport aux spécifications de périphériques de la machine : un nom mal orthographié est refusé au lieu d'être enregistré.
- Une autorisation appartient au dépôt pour lequel elle a été faite. Les forks et les copies ont besoin de la leur.

## Préparer la machine

`rdc machine setup <machine>` détecte les GPU de la machine et consigne le résultat dans `/etc/rediacc/gpu/inventory.json`. Quand un GPU NVIDIA est présent, le setup installe aussi le NVIDIA Container Toolkit et génère la spécification CDI dans `/etc/cdi/nvidia.yaml`. Une machine sans GPU reçoit tout de même un fichier d'inventaire, avec des listes vides.

L'installation du toolkit se règle avec l'option `--install-nvidia-toolkit` de `renet setup` :

| Valeur | Comportement |
|---|---|
| `auto` | Le toolkit est installé quand un GPU NVIDIA est présent. C'est la valeur par défaut. |
| `true` | Le toolkit est installé dans tous les cas. |
| `false` | Le toolkit est ignoré, et aucune spécification NVIDIA n'est générée. |

Le setup ne configure aucun runtime de conteneur, car seul `runc` est admis. Le toolkit ne sert qu'à la spécification, régénérée à chaque setup pour suivre les changements de pilote.

Deux types de périphériques viennent de Rediacc lui-même et n'exigent aucun composant utilisateur du fabricant, car ils ne font que mapper des nœuds de périphériques :

| Type | Périphériques | Source |
|---|---|---|
| `rediacc.io/dri` | Un par nœud de rendu, comme `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | `gpu<N>` pour une carte AMD et `all` | `/dev/kfd` plus le nœud de rendu de la carte |

Les périphériques NVIDIA viennent de la spécification du toolkit : `nvidia.com/gpu=all` et un nom par carte. Le calcul AMD demande l'espace utilisateur ROCm dans l'image du conteneur, car le setup n'installe pas ROCm.

## Lister les GPU

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

Le tableau montre chaque GPU avec son nom, la version du pilote et la mémoire, la plateforme (native ou WSL), l'âge de l'inventaire et chaque nom de périphérique CDI pouvant être accordé. `-o json` affiche l'inventaire tel qu'il est enregistré sur la machine. Les autorisations en vigueur sont lues en direct sur la machine.

## Accorder et retirer

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` est un nom de dépôt, éventuellement suivi d'une machine, comme `gpu-a@wsl-gpu`. Les deux commandes se répètent avec différentes valeurs de `--device`. Après une autorisation, un conteneur de ce dépôt démarre avec le périphérique :

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

Le même conteneur est refusé dans un dépôt sans l'autorisation, et le message nomme l'autorisation manquante.

## Autorisations exclusives

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

Une autorisation exclusive réserve un périphérique à un seul dépôt. Elle est refusée quand un autre dépôt détient le même nom, et tant qu'elle existe, toute autorisation de ce nom à un autre dépôt est refusée. La vérification a lieu lors de l'octroi, sous un verrou couvrant toutes les autorisations de la machine.

Une autorisation exclusive est une réservation, pas un ordonnanceur. Deux conteneurs du même dépôt autorisé se partagent toujours la carte.

## Écritures refusées

Toute autre voie vers un GPU reste refusée, avec ou sans autorisation. La forme CDI remplace chacune d'elles.

| Refusé | À utiliser à la place |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| `runtime: nvidia` dans Compose | `devices: [nvidia.com/gpu=all]` |
| `deploy.resources.reservations.devices` dans Compose | `devices: [nvidia.com/gpu=all]` |
| `gpus: all` dans Compose | `devices: [nvidia.com/gpu=all]` |
| Périphériques bruts `/dev/dri` ou `/dev/kfd`, ou un bind sous `/dev` | `rediacc.io/dri=renderD128` ou `rediacc.io/amd=gpu0` |
| Règles cgroup de périphériques | Une autorisation CDI pour le périphérique |

Un service Compose qui utilise un périphérique autorisé ressemble à ceci :

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

Ajouter un groupe comme `video` ou `render` avec `group_add` est accepté mais n'accorde rien, car le groupe n'ouvre pas l'accès à un périphérique que le dépôt n'a pas reçu.

## WSL

Sous WSL2, le pilote Windows fournit le GPU par `/dev/dxg` et les bibliothèques de `/usr/lib/wsl/lib`. La machine annonce sa plateforme comme `wsl`, et le setup génère la spécification NVIDIA au format WSL :

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

Le pilote se trouve côté Windows : une mise à jour y est donc prise en compte au prochain `rdc machine setup`. Les commandes d'octroi, de liste et de retrait fonctionnent comme sur une machine native.

## NVIDIA natif

Sur une machine NVIDIA native, le service `nvidia-cdi-refresh` du toolkit régénère la spécification après une installation, un changement de pilote et un démarrage. Le setup le pointe vers `/etc/cdi/nvidia.yaml`, le seul répertoire de spécifications que lit le démon Docker d'un dépôt. Quand `nvidia-persistenced` tourne, son socket est rendu visible aux démons des dépôts, car la spécification le monte dans les conteneurs.
