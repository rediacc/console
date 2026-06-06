---
title: Configuration du serveur MCP
description: Connectez des agents IA à l'infrastructure Rediacc en utilisant le serveur Model Context Protocol (MCP).
category: Guides
order: 33
language: fr
sourceHash: "ce5f1392ebaa380b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

## Aperçu

La commande `rdc mcp serve` lance un serveur MCP (Model Context Protocol) local que les agents IA peuvent utiliser pour gérer votre infrastructure. Le serveur utilise le transport stdio, l'agent IA le lance en tant que sous-processus et communique via JSON-RPC.

**Prérequis :** `rdc` installé et configuré avec au moins une machine.

## Claude Code

Ajoutez au fichier `.mcp.json` de votre projet :

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

Ou avec une configuration nommée :

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Ouvrez Paramètres → MCP Servers → Add Server :

- **Name** : `rdc`
- **Command** : `rdc mcp serve`
- **Transport** : stdio

## Outils disponibles

### Outils de lecture (sans effets de bord)

| Outil | Description |
|-------|-------------|
| `machine_query` | Obtenir les informations système, les conteneurs, les services et l'utilisation des ressources d'une machine |
| `machine_containers` | Lister les conteneurs Docker avec leur état, leur santé, l'utilisation des ressources, les labels et le domaine auto-route |
| `machine_services` | Lister les services systemd gérés par rediacc (nom, état, sous-état, nombre de redémarrages, mémoire, dépôt propriétaire) |
| `machine_repos` | Lister les dépôts déployés (nom, GUID, taille, état de montage, état Docker, nombre de conteneurs, utilisation du disque, date de modification, présence du Rediaccfile) |
| `machine_health` | Effectuer une vérification de l'état d'une machine (système, conteneurs, services, stockage) |
| `machine_list` | Lister toutes les machines configurées |
| `config_repositories` | Lister les dépôts configurés avec les correspondances nom-GUID |
| `config_show_infra` | Afficher la configuration infrastructure d'une machine (domaine de base, IPs publiques, TLS, zone Cloudflare) |
| `config_providers` | Lister les fournisseurs cloud configurés pour le provisionnement des machines |
| `agent_capabilities` | Lister toutes les commandes rdc CLI disponibles avec leurs arguments et options |
| `repo_secret_list` | Lister les noms de secrets et leurs modes de distribution pour un dépôt (jamais les valeurs, jamais les empreintes). Sans effet de bord. |
| `repo_secret_get` | Obtenir l'empreinte SHA-256 d'un secret et son mode de distribution. La valeur en clair n'est jamais renvoyée par conception. Permet de vérifier qu'un secret existe ou a été tourné. |

### Outils d'écriture (destructifs)

| Outil | Description |
|-------|-------------|
| `repo_create` | Créer un nouveau dépôt chiffré sur une machine |
| `repo_up` | Déployer/mettre à jour un dépôt (exécute le Rediaccfile up, démarre les conteneurs). Utiliser `mount` pour le premier déploiement ou après un pull |
| `repo_down` | Arrêter les conteneurs d'un dépôt. Ne démonte PAS par défaut. Utiliser `unmount` pour fermer également le conteneur LUKS |
| `repo_delete` | Supprimer un dépôt (détruit les conteneurs, volumes et l'image chiffrée). Les identifiants sont archivés pour la récupération |
| `repo_fork` | Créer un fork CoW avec un nouveau GUID et networkId (copie entièrement indépendante, fork en ligne supporté) |
| `backup_push` | Pousser la sauvegarde d'un dépôt vers un stockage ou une autre machine (même GUID -- sauvegarde/migration, pas un fork) |
| `backup_pull` | Récupérer la sauvegarde d'un dépôt depuis un stockage ou une machine. Après la récupération, déployer avec `repo_up` (mount=true) |
| `machine_provision` | Provisionner une nouvelle machine chez un fournisseur cloud via OpenTofu |
| `machine_deprovision` | Détruire une machine provisionnée dans le cloud et la supprimer de la configuration |
| `config_add_provider` | Ajouter une configuration de fournisseur cloud pour le provisionnement des machines |
| `config_remove_provider` | Supprimer une configuration de fournisseur cloud |
| `term_exec` | Exécuter une commande sur une machine distante via SSH |

## Exemples de workflows

**Vérifier l'état d'une machine :**
> « Quel est l'état de ma machine de production ? »

L'agent appelle `machine_query` → renvoie les informations système, les conteneurs en cours d'exécution, les services et l'utilisation des ressources.

**Déployer une application :**
> « Déploie gitlab sur ma machine de staging »

L'agent appelle `repo_up` avec `name: "gitlab"` et `machine: "staging"` → déploie le dépôt, renvoie le succès ou l'échec.

**Déboguer un service défaillant :**
> « Mon nextcloud est lent, trouve ce qui ne va pas »

L'agent appelle `machine_health` → `machine_containers` → `term_exec` pour lire les logs → identifie le problème et propose une solution.

## Options de configuration

| Option | Défaut | Description |
|--------|--------|-------------|
| `--config <name>` | (configuration par défaut) | Configuration nommée à utiliser pour toutes les commandes |
| `--timeout <ms>` | `120000` | Délai d'expiration par défaut des commandes en millisecondes |
| `--allow-grand` | off | Autoriser les opérations destructives sur les dépôts grand (non-fork) |

## Sécurité

Le serveur MCP applique deux couches de protection :

### Mode fork uniquement (par défaut)

Par défaut, le serveur fonctionne en **mode fork uniquement** : les outils d'écriture (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) ne peuvent opérer que sur des dépôts fork. Les agents ne peuvent pas toucher aux dépôts grand (originaux). C'est voulu.

> **Les secrets par dépôt sont réservés à la CLI, par conception.** `repo_secret_set` et `repo_secret_unset` ne sont intentionnellement **pas** exposés comme outils MCP. Les écritures requièrent une précondition `--current <valeur-précédente>` (ou `--rotate-secret` pour reconnaître une rotation non vérifiée), et cette cérémonie nécessite une supervision humaine. Les agents souhaitant suggérer une rotation de secret doivent appeler `repo_secret_get` pour confirmer l'empreinte, puis relayer la commande CLI destinée à l'opérateur via le champ structuré `next.options[].run` dans l'enveloppe d'erreur JSON. Voir [Sécurité des agents IA](/en/docs/ai-agents-safety#structured-next-action-hints) pour le schéma complet, et [Dépôts § Secrets](/en/docs/repositories#secrets) pour le guide utilisateur.

Pour autoriser un agent à modifier des dépôts grand, démarrer avec `--allow-grand` :

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

Vous pouvez aussi définir la variable d'environnement `REDIACC_ALLOW_GRAND_REPO` sur un nom de dépôt unique, sur une liste de noms séparés par des virgules (par exemple `repo1,repo2,repo3`) ou sur `*` pour tous les dépôts. Les espaces autour des entrées sont ignorés, donc `repo1, repo2` fonctionne également. L'accès au niveau de la machine (comme `term connect -m <machine>` sans dépôt) nécessite toujours `*` ; une liste de noms de dépôts ne le débloque pas.

### Clés SSH par dépôt et sandbox côté serveur

Chaque dépôt possède sa propre paire de clés SSH. La clé publique est déployée dans `authorized_keys` avec un préfixe `command=` qui force toutes les sessions SSH à passer par `renet sandbox-gateway <repo-name>`, un ForceCommand côté serveur qu'aucun client ne peut contourner, y compris VS Code.

**Fonctionnement :**
1. `rdc repo create` ou `rdc repo fork` génère une paire de clés ed25519 unique par dépôt
2. La clé publique est déployée sur le serveur distant avec `command="renet sandbox-gateway <name>"`
3. Toute connexion SSH utilisant cette clé passe par la passerelle, qui applique :
   - **Landlock LSM** : restrictions du système de fichiers au niveau noyau, limitées au chemin de montage du dépôt
   - **OverlayFS home overlay** : les écritures dans `$HOME` sont capturées par dépôt, les lectures passent au répertoire home réel
   - **TMPDIR par dépôt** à `<datastore>/.interim/sandbox/<name>/tmp/`
   - **Accès Docker** via le socket Docker isolé du dépôt
   - **Abandon de privilèges** vers l'utilisateur universel (`rediacc`)
4. Le fichier `.envrc` du dépôt est chargé automatiquement pour Docker et la configuration de l'environnement

**Autorisé en lecture/écriture** : chemin de montage du dépôt, espace de travail sandbox par dépôt, répertoire home (via overlay), socket Docker
**Autorisé en lecture seule** : chemins système (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**Bloqué** : chemins de montage des autres dépôts, fichiers système hors liste d'autorisation

**Intégration VS Code** : chaque dépôt dispose de sa propre installation du serveur VS Code à `<datastore>/.interim/sandbox/<name>/.vscode-server/`. Plusieurs dépôts peuvent être ouverts simultanément avec des environnements sandbox indépendants, sans partage de serveur entre dépôts.

Ce mécanisme empêche les mouvements latéraux. Même si un agent obtient un accès shell à un fork, il ne peut ni lire ni modifier les autres dépôts sur la même machine. Le SSH au niveau machine (sans dépôt) utilise la clé d'équipe et n'est pas isolé dans un sandbox.

## Architecture

Le serveur MCP est sans état. Chaque appel d'outil lance `rdc` en tant que processus enfant isolé avec les flags `--output json --yes --quiet`. Cela signifie :

- Aucune fuite d'état entre les appels d'outils
- Utilise votre configuration `rdc` existante et vos clés SSH
- Fonctionne avec les adaptateurs local et cloud
- Les erreurs d'une commande n'affectent pas les autres
