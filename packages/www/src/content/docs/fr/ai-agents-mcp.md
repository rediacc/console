---
title: Configuration du serveur MCP
description: Connectez des agents IA à l'infrastructure Rediacc en utilisant le serveur Model Context Protocol (MCP).
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: fr
sourceHash: "5ffb60357e13aeab"
sourceCommit: "a2b1f5471f48c44fb704157f615369df9c354832"
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

<!-- >>> translated-table: mcp-tools -->

| Outil | Destructif | Description |
|---|---|---|
| `backup_browse` | non | Lister les fichiers que contient un dépôt. |
| `backup_cancel` | non | Annuler une sauvegarde en cours sur une machine distante. |
| `backup_check` | non | Vérifier qu'un instantané stocké s'ouvre avec la phrase secrète, en restaurant un fichier. |
| `backup_immutability_show` | non | Afficher la fenêtre de suppression différée en vigueur. |
| `backup_list` | non | Lister les artefacts de sauvegarde d'une machine. |
| `backup_manifests` | non | Lister les manifestes d'instantanés de sauvegarde enregistrés sur le serveur. |
| `backup_reconcile` | oui | Remettre le registre des octets stockés d'un dépôt à ce que le stockage contient réellement (ne supprime jamais un chunk). |
| `backup_repair` | oui | Renvoyer, depuis l'ancre de cette machine, les chunks que le stockage a perdus ou qu'il détient corrompus. |
| `backup_restore` | oui | Transformer un artefact de sauvegarde en dépôt actif. |
| `backup_retention` | non | Afficher la politique de rétention des instantanés appliquée par le serveur. |
| `backup_retention_preview` | non | Afficher les instantanés que le prochain nettoyage supprimerait et l'espace qu'il libérerait. |
| `backup_run` | non | Lancer une sauvegarde immédiatement. |
| `backup_snapshot` | non | Envoyer un instantané du magasin de chunks : d'abord l'inventaire complet, puis les cellules modifiées. |
| `backup_status` | non | Afficher l'état des sauvegardes et du minuteur sur une machine distante. |
| `backup_strategy_list` | non | Lister toutes les stratégies de sauvegarde. |
| `backup_strategy_show` | non | Afficher le détail d'une stratégie de sauvegarde. |
| `backup_toc-key_sync` | non | Installer la clé de listage du dépôt sur sa machine, ou en remplacer une différente. |
| `backup_undelete` | non | Annuler la suppression différée d'un instantané avant qu'elle ne prenne effet. |
| `backup_usage` | non | Afficher le quota de stockage des sauvegardes, les octets stockés et l'usage par dépôt. |
| `backup_verify` | non | Vérifier l'ancre de sauvegarde d'un dépôt par rapport au magasin de chunks. |
| `cluster_snapshot_list` | non | Lister les instantanés de groupe du cluster. |
| `cluster_status` | non | Lister tous les clusters, ou afficher la configuration complète d'un cluster à partir de son nom. |
| `config_access_list` | non | Lister les clés d'accès de la configuration. |
| `config_prune` | non | Retirer le superflu du fichier de configuration local ~/.config/rediacc/<config>.json. |
| `config_reconcile` | non | Reconstruire le registre d'état local à partir de l'état réel des machines (renet list all). |
| `config_show` | non | Afficher le détail de la configuration actuelle. |
| `credits` | non | Afficher le solde de crédits restant de ce compte. |
| `datastore_list` | non | Lister les datastores nommés, où ils sont rattachés et ce qu'ils contiennent. |
| `datastore_snapshot_list` | non | Lister les instantanés d'un datastore. |
| `datastore_status` | non | Afficher un datastore : son backend, son rattachement, son usage, ses dépôts et ses instantanés. |
| `feedback_list` | non | Lister les rapports de retour visibles pour cette machine : id, empreinte courte, statut et dates. |
| `feedback_report` | non | Construire un rapport à partir de la dernière commande en échec (--last), d'une commande enregistrée (--command <n>) ou d'un simple message, afficher exactement ce qui serait envoyé, puis l'envoyer après confirmation. |
| `feedback_show` | non | Afficher un rapport de retour par son id (ou un préfixe unique), avec son statut, son nombre d'occurrences et ses dates. |
| `job_cancel` | oui | Annuler une tâche détachée en cours d'exécution. |
| `job_dismiss` | oui | Abandonner localement des tickets de tâche : leurs étapes dues sont abandonnées et le ticket n'apparaît plus. |
| `job_gc` | oui | Supprimer les tâches terminées et leurs journaux. |
| `job_list` | non | Lister les tâches détachées d'une machine, de la plus récente à la plus ancienne. |
| `job_logs` | non | Rejouer ou suivre le journal d'événements d'une tâche détachée. |
| `job_status` | non | Afficher l'état d'une tâche détachée. |
| `job_wait` | non | Attendre jusqu'à 50 s la fin d'une tâche. |
| `legal` | non | Afficher les liens vers les documents juridiques dans la langue de la CLI avec les liens anglais faisant foi, la version en vigueur des Conditions d'utilisation avec sa somme de contrôle et l'URL d'archive, l'acceptation enregistrée (depuis le serveur de comptes une fois connecté, depuis cette configuration en mode anonyme) et l'entité contractante. |
| `machine_access_show` | non | Afficher les clés d'accès liées à une machine et les plages que chacune y résout. |
| `machine_add` | non | Enregistrer une machine existante joignable en SSH. |
| `machine_containers` | non | Lister les conteneurs Docker d'une machine. |
| `machine_converge` | oui | Redémarrer, un dépôt à la fois, chaque démon de dépôt encore sur un ancien agencement du runtime, pour qu'il passe au courant. |
| `machine_deprovision` | oui | Détruire une machine provisionnée dans le cloud et la retirer de la configuration. |
| `machine_gpu_list` | non | Lister les GPU détectés sur une machine, les noms de périphériques CDI définis par ses spécifications et les dépôts auxquels chaque périphérique est accordé. |
| `machine_health` | non | Vérifier la santé d'une machine pour les pipelines CI/CD. |
| `machine_infra_show` | non | Afficher la configuration d'infrastructure d'une machine (domaine de base, IP publiques, ports), les paramètres TLS partagés (e-mail du certificat, jeton DNS CF) et l'ID de zone Cloudflare. |
| `machine_list` | non | Lister les machines. |
| `machine_provider_add` | non | Ajouter un fournisseur cloud. |
| `machine_provider_list` | non | Lister les fournisseurs cloud configurés pour le provisionnement de machines. |
| `machine_provider_remove` | oui | Supprimer la configuration d'un fournisseur cloud. |
| `machine_provision` | oui | Provisionner une nouvelle machine chez un fournisseur cloud avec OpenTofu. |
| `machine_prune` | oui | Retirer d'une machine les ressources de datastore orphelines et les instantanés obsolètes. |
| `machine_remove` | oui | Retirer une machine de la configuration. |
| `machine_repos` | non | Lister les dépôts déployés sur une machine. |
| `machine_restart-services` | oui | Faire passer les démons renet qui exécutent encore un binaire remplacé sur le binaire installé, une unité à la fois, en confirmant que chacune est active avant de passer à la suivante. |
| `machine_scan-keys` | non | Enregistrer les clés d'hôte SSH de la machine dans la configuration locale. |
| `machine_services` | non | Lister les services systemd gérés par Rediacc sur une machine (nom, état, sous-état, nombre de redémarrages, mémoire, dépôt résolu en nom avec l'original dans repository_guid). |
| `machine_setup` | non | Terminer l'intégration d'une machine : installer renet et la préparer à héberger des dépôts. |
| `machine_status` | non | Obtenir les détails de connexion (IP, utilisateur, port, datastore), les informations système, les conteneurs (dépôt résolu en nom, original dans repository_guid, domaine, autoRoute), les services (dépôt résolu en nom), les dépôts (nom résolu depuis le GUID, original dans guid) et l'usage des ressources d'une machine. |
| `repo_admin_fsck` | non | Valider les références de la configuration (branches/HEAD) par rapport aux objets présents sur une machine et signaler les références pendantes et les commits orphelins. |
| `repo_cat` | non | Lire sur stdout une fenêtre bornée d'un fichier d'un dépôt (les diagnostics vont sur stderr). |
| `repo_checkout` | oui | Cloner par reflink un commit immuable (ou la pointe d'une branche) dans un nouveau fork de travail inscriptible et y pointer HEAD. |
| `repo_commit` | oui | Figer un fork de travail monté en un nouveau commit immuable (comme avec git). |
| `repo_create` | oui | Créer un nouveau dépôt. |
| `repo_delete` | oui | Supprimer un dépôt et ses données. |
| `repo_diff` | non | Diff au niveau des fichiers, façon git, entre deux dépôts forkés en copy-on-write. |
| `repo_down` | oui | Arrêter les conteneurs Docker d'un dépôt (exécute Rediaccfile down). |
| `repo_exec` | oui | Exécuter une commande dans un conteneur d'un dépôt. |
| `repo_fork` | oui | Créer un fork CoW quasi instantané d'un dépôt avec un NOUVEAU GUID et un nouveau networkId (copie entièrement indépendante). |
| `repo_gc` | oui | Ramasse-miettes par accessibilité : supprimer les objets de commit immuables d'une machine qu'aucune branche ni HEAD n'atteint. |
| `repo_health` | non | Exécuter les vérifications health() du Rediaccfile d'un dépôt et sortir avec 0 (ok), 1 (avertissement) ou 2 (erreur). |
| `repo_list` | non | Lister les dépôts d'une machine. |
| `repo_log` | non | Afficher l'historique des commits accessible depuis le commit courant d'un fork de travail (ou une référence de commit), en parcourant la chaîne de parents enregistrée par 'rdc repo commit'. |
| `repo_logs` | non | Afficher les journaux applicatifs des conteneurs d'un dépôt. |
| `repo_merge` | oui | Fusionner, en respectant le cycle de vie, un commit ou fork source dans un fork de travail cible. |
| `repo_migrate` | oui | Déplacer un dépôt vers une autre machine avec un arrêt minimal : copie en deux phases (synchronisation en masse à chaud, puis arrêt bref, synchronisation du delta et démarrage sur la destination) avec bascule DNS. |
| `repo_pull` | oui | Récupérer un dépôt depuis une autre machine. |
| `repo_push` | oui | Envoyer la sauvegarde d'un dépôt vers le stockage ou directement vers une autre machine. |
| `repo_replicate` | non | Provisionner des réplicas en lecture d'un dépôt. |
| `repo_replicate_remove` | oui | Supprimer un ensemble de réplicas : effacer ses objets k8s générés (limités par étiquette), abandonner ses datastores forkés, supprimer son instantané et oublier l'état. |
| `repo_replicate_status` | non | Afficher les ensembles de réplicas gérés : réplicas, nœuds hôtes, datastores forkés, instantané et horodatages de rafraîchissement. |
| `repo_secret_get` | non | Afficher l'empreinte SHA-256 d'un secret. |
| `repo_secret_list` | non | Lister les clés et les modes des secrets (jamais les valeurs, jamais les empreintes). |
| `repo_status` | non | Obtenir l'état d'un dépôt (état du montage, démon Docker actif, nombre de conteneurs, usage disque). |
| `repo_trim` | non | Récupérer l'espace du pool de datastore à partir des dépôts montés (à chaud, sans interruption). |
| `repo_up` | oui | Déployer ou mettre à jour un dépôt (exécute Rediaccfile up via renet compose, démarre les conteneurs). |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| Outil | Destructif | Description |
|---|---|---|
| `cluster_kubeconfig` | non | Récupérer en SSH le kubeconfig du nœud de contrôle du cluster et le mettre en cache localement (0600) pour kubectl. |
| `config_audit_log` | non | Lire le journal d'audit des modifications faites via cette configuration. |
| `config_audit_verify` | non | Vérifier que la chaîne de hachage du journal d'audit n'a pas été altérée. |
| `config_current` | non | Afficher la configuration active : nom, fichier, serveur et canal résolus, état du jeton. |
| `config_list` | non | Lister tous les fichiers de configuration. |
| `machine_infra_cert_status` | non | Afficher l'inventaire des certificats en cache. |
| `server_status` | non | Afficher l'état, l'offre, le certificat et l'image d'un serveur installé. |
| `version` | non | Afficher la version de la CLI, la plateforme, le canal de mise à jour et la licence active : l'offre une fois connecté, « anonymous (FREE per repository) » sans connexion et « unknown (server unreachable) » quand le serveur de comptes est injoignable. |

<!-- <<< translated-table -->

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

## Sécurité

Le serveur MCP applique deux couches de protection :

### Mode fork uniquement (par défaut)

Par défaut, le serveur fonctionne en **mode fork uniquement** : les outils d'écriture (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) ne peuvent opérer que sur des dépôts fork. Les agents ne peuvent pas toucher aux dépôts grand (originaux). C'est voulu.

> **Les secrets par dépôt sont réservés à la CLI, par conception.** `repo_secret_set` et `repo_secret_unset` ne sont intentionnellement **pas** exposés comme outils MCP. Les écritures requièrent une précondition `--current <valeur-précédente>` (ou `--rotate-secret` pour reconnaître une rotation non vérifiée), et cette cérémonie nécessite une supervision humaine. Les agents souhaitant suggérer une rotation de secret doivent appeler `repo_secret_get` pour confirmer l'empreinte, puis relayer la commande CLI destinée à l'opérateur via le champ structuré `next.options[].run` dans l'enveloppe d'erreur JSON. Voir [Sécurité des agents IA](/en/docs/ai-agents-safety#structured-next-action-hints) pour le schéma complet, et [Dépôts § Secrets](/en/docs/repositories#secrets) pour le guide utilisateur.

Pour autoriser un agent à modifier des dépôts grand, exportez `REDIACC_ALLOW_GRAND_REPO` dans votre terminal **avant de démarrer l'agent qui héberge le serveur MCP** :

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # un seul dépôt
# ou 'repo1,repo2,repo3' (les espaces autour des entrées sont ignorés), ou '*' pour tous les dépôts
claude   # ou cursor, gemini, etc.
```

La substitution est vérifiée contre l'ascendance du processus : elle ne compte que lorsqu'elle était déjà présente dans l'environnement du processus agent lui-même, ce qui signifie que vous l'avez exportée avant que l'agent (et le serveur MCP qu'il a engendré) ne démarre. Un agent ne peut pas se conférer accès en définissant la variable en cours de session. Il n'existe pas intentionnellement de flag serveur pour cela : un flag dans les arguments du serveur MCP n'apporte aucune preuve de qui l'a mis là, tandis que la vérification d'ascendance en apporte. L'accès au niveau machine (comme `term connect <machine>` sans dépôt) nécessite toujours `*` ; une liste de noms de dépôts ne le débloque pas.

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
- Les erreurs d'une commande n'affectent pas les autres
