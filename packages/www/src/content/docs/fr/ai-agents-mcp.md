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
sourceHash: "844e1461f5149322"
sourceCommit: "504925af13712be329813824338192f58efb3e08"
---

## Aperçu

Deux serveurs MCP (Model Context Protocol) puisent leurs outils dans un seul registre, et le serveur distant en propose un sous-ensemble :

| Serveur | Transport | S'exécute | Outils |
|---|---|---|---|
| Local | stdio | `rdc mcp serve`, lancé par l'agent | Tous les outils |
| Distant | Streamable HTTP | `https://mcp.<region>.rediacc.cloud/g/<grantId>` | Les outils distants, soit tous sauf ceux du tableau des outils réservés au local |

**Prérequis :** `rdc` installé et configuré avec au moins une machine pour le serveur local. Pour le serveur distant, il faut un grant sur une configuration.

## Serveur local

`rdc mcp serve` démarre un serveur MCP via stdio. L'agent le lance comme sous-processus et dialogue avec lui en JSON-RPC.

### Claude Code

Le fichier `.mcp.json` du projet contient l'entrée :

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

### Cursor

Ouvrez Settings → MCP Servers → Add Server :

- **Name** : `rdc`
- **Command** : `rdc mcp serve`
- **Transport** : stdio

### Options

| Option | Par défaut | Description |
|--------|------------|-------------|
| `--config <name>` | (configuration par défaut) | Configuration nommée utilisée pour toutes les commandes |
| `--timeout <ms>` | `120000` | Délai d'expiration par défaut des commandes, en millisecondes |

## Serveur distant

Un Worker MCP tourne dans chaque région sur `mcp.<region>.rediacc.cloud`. Chaque agent se connecte à l'URL d'un grant : `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Le grant désigne une configuration, une date d'expiration et une portée : un indicateur de lecture seule, une liste d'outils autorisés, ainsi que des motifs (globs) de noms de machines et de dépôts. Les appels d'outils s'exécutent sur l'exécuteur de l'organisation du grant.

### Identifiants

Les deux formes identifient le grant ; l'identifiant de grant dans l'URL ne fait que le nommer.

| Forme | Usage | Envoyé comme |
|---|---|---|
| Jeton d'accès OAuth | Clients interactifs comme claude.ai | `Authorization: Bearer <token>` |
| Bearer d'agent `rmcp_<grantId>.<secret>` | Agents sans interface | `Authorization: Bearer` ou `x-api-key` |

Un identifiant placé dans la chaîne de requête est refusé avec un 400. Un jeton OAuth absent, expiré ou appartenant à un autre grant reçoit un 401 avec un en-tête `WWW-Authenticate: Bearer resource_metadata=...` qui pointe vers le document de ressource protégée du grant : le client OAuth renouvelle alors son jeton ou se reconnecte. Un grant inconnu, un secret erroné et un bearer d'agent d'un autre grant reçoivent tous le même 401 nu.

### OAuth

Le Worker est un serveur d'autorisation OAuth 2.1 avec PKCE (S256 uniquement). Les clients s'enregistrent via un Client ID Metadata Document ou par enregistrement dynamique de client sur `/register`.

| Endpoint | Rôle |
|---|---|
| `/.well-known/oauth-authorization-server` | Métadonnées du serveur |
| `/.well-known/oauth-protected-resource/g/<grantId>` | Document de ressource protégée d'un grant |
| `/authorize` | Démarre l'autorisation et redirige vers la page de compte `/account/mcp/authorize` |
| `/oauth/token` | Échange de code, renouvellement et révocation |
| `/register` | Enregistrement dynamique de client |

Le client envoie `resource=https://mcp.<region>.rediacc.cloud/g/<grantId>`. L'autorisation n'aboutit que pour le grant désigné par la ressource, et un jeton ne fonctionne qu'à l'URL de son grant. La redirection de `/authorize` porte un identifiant signé à usage unique et aucun secret.

### Durée de vie des jetons

Un jeton ne survit jamais à son grant.

| Jeton | Durée de vie |
|---|---|
| Jeton d'accès | La plus courte entre 1 heure et le temps restant au grant |
| Jeton de renouvellement | La plus courte entre 30 jours et le temps restant au grant |

Chaque échange de code et chaque renouvellement consulte de nouveau le grant. Un grant expiré, révoqué ou dont la clé a été renouvelée répond `invalid_grant` et révoque l'autorisation OAuth. Les jetons de renouvellement tournent, et en présenter un deux fois révoque le grant.

### Une configuration par grant

Un grant ne sert que la configuration qu'il désigne. Un `tools/call` dont un argument désigne une autre configuration (`config` ou une variante d'écriture) est refusé avec `REDIACC_GRANT_SCOPE` avant toute exécution. Un utilisateur qui possède plusieurs configurations autorise un grant par configuration. Un outil absent de la liste autorisée du grant, ou un outil d'écriture sous un grant en lecture seule, n'apparaît pas dans `tools/list` et est refusé s'il est appelé.

### Régions

Un identifiant de grant commence par sa région, par exemple `eu_`. Une requête vers `/g/<grantId>` sur le Worker d'une autre région reçoit un 421 avec la bonne URL :

```json
{
  "code": "REDIACC_WRONG_REGION",
  "message": "This grant lives in the us region. Use https://mcp.us.rediacc.cloud/g/us_...",
  "region": "us",
  "mcpUrl": "https://mcp.us.rediacc.cloud/g/us_..."
}
```

Un grant n'est jamais accepté comme ressource OAuth, audience de jeton ou cible d'autorisation en dehors de sa région.

### États d'un grant et limites

Un grant expiré, révoqué, ou qui a perdu sa clé lors d'une rotation de clé du stockage de configuration répond toujours à `initialize` et `tools/list`. Chaque `tools/call` renvoie alors `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` ou `REDIACC_KEY_ROTATED` avec une `reauthUrl` que l'utilisateur ouvre pour autoriser à nouveau.

Chaque grant autorise 60 appels par minute et 5 appels simultanés. Un appel au-delà de l'une des deux limites renvoie `REDIACC_RATE_LIMITED` avec `retryAfterSeconds`.

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
| `forensics_verify` | non | Recalculer la chaîne de hachage des fichiers journaliers d'audit et les chaînes de lots forensiques signés d'un répertoire de preuves (un répertoire d'export de rdc incident), puis lister chaque trou et chaque modification. |
| `incident_export` | non | Écrire la fenêtre de l'incident dans un répertoire : l'enregistrement de l'incident avec ses horloges, la chronologie fusionnée, les agrégats d'octets sortants, le manifeste brut de la chaîne et les fichiers bruts qu'il liste, sous leurs clés de manifeste. |
| `machine_infra_cert_status` | non | Afficher l'inventaire des certificats en cache. |
| `server_status` | non | Afficher l'état, l'offre, le certificat et l'image d'un serveur installé. |
| `version` | non | Afficher la version de la CLI, la plateforme, le canal de mise à jour et la licence active : l'offre une fois connecté, « anonymous (FREE per repository) » sans connexion et « unknown (server unreachable) » quand le serveur de comptes est injoignable. |

<!-- <<< translated-table -->

## Exemples de workflows

**Vérifier l'état d'une machine :**
> « Quel est l'état de ma machine de production ? »

L'agent appelle `machine_status` et obtient les détails de connexion, les informations système, les conteneurs, les services, les dépôts et l'utilisation des ressources.

**Déployer une application :**
> « Déploie gitlab sur ma machine de staging »

L'agent appelle `repo_up` avec `name: "gitlab"` et `machine: "staging"`, ce qui déploie le dépôt et renvoie un succès ou un échec.

**Suivre une longue tâche :**
> « Restaure la sauvegarde de cette nuit de nextcloud »

L'agent appelle `backup_restore`. Une commande qui dépasse son délai renvoie un identifiant de tâche, puis l'agent appelle `job_wait` (jusqu'à 50 s par appel) et `job_logs` jusqu'à la fin de la tâche.

**Déboguer un service défaillant :**
> « Mon nextcloud est lent, trouve ce qui ne va pas »

L'agent appelle `machine_health`, puis `machine_containers` et `repo_logs`, et propose un correctif.

## Sécurité

Le serveur MCP local applique deux niveaux de protection. Les limites du serveur distant sont décrites dans [Serveur distant](#serveur-distant).

### Mode fork uniquement (par défaut)

Par défaut, le serveur s'exécute en **mode fork uniquement** : les outils d'écriture (`repo_up`, `repo_down`, `repo_delete`, `repo_exec`, `repo_push`, `repo_pull`) ne peuvent agir que sur des dépôts fork. Les agents ne peuvent pas toucher aux dépôts grand (originaux). C'est voulu.

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

Le serveur MCP local est sans état. Chaque appel d'outil lance `rdc` comme processus enfant isolé avec les options `--output json --yes --quiet`. Cela signifie :

- Aucune fuite d'état entre les appels d'outils
- Utilise votre configuration `rdc` existante et vos clés SSH
- Les erreurs d'une commande n'affectent pas les autres
