---
title: Configuration du serveur MCP
description: Connectez des agents IA à l'infrastructure Rediacc en utilisant le serveur Model Context Protocol (MCP).
category: Guides
order: 33
language: fr
sourceHash: "1b6cd5ba5d8d0ffe"
---

## Aperçu

La commande `rdc mcp serve` lance un serveur MCP (Model Context Protocol) local que les agents IA peuvent utiliser pour gérer votre infrastructure. Le serveur utilise le transport stdio — l'agent IA le lance en tant que sous-processus et communique via JSON-RPC.

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
| `machine_info` | Obtenir les informations système, les conteneurs, les services et l'utilisation des ressources |
| `machine_containers` | Lister les conteneurs Docker en cours d'exécution sur une machine |
| `machine_services` | Lister les services systemd sur une machine |
| `machine_repos` | Lister les dépôts déployés sur une machine |
| `machine_health` | Exécuter un bilan de santé (système, conteneurs, services, stockage) |
| `config_repositories` | Lister les dépôts configurés avec les correspondances nom-GUID |
| `agent_capabilities` | Lister toutes les commandes CLI rdc disponibles |

### Outils d'écriture (destructifs)

| Outil | Description |
|-------|-------------|
| `repo_up` | Déployer/mettre à jour un dépôt sur une machine |
| `repo_down` | Arrêter un dépôt sur une machine |
| `term_exec` | Exécuter une commande sur une machine distante via SSH |

## Exemples de workflows

**Vérifier l'état d'une machine :**
> « Quel est l'état de ma machine de production ? »

L'agent appelle `machine_info` → renvoie les informations système, les conteneurs en cours d'exécution, les services et l'utilisation des ressources.

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

## Architecture

Le serveur MCP est sans état. Chaque appel d'outil lance `rdc` en tant que processus enfant isolé avec les flags `--output json --yes --quiet`. Cela signifie :

- Aucune fuite d'état entre les appels d'outils
- Utilise votre configuration `rdc` existante et vos clés SSH
- Fonctionne avec les adaptateurs local et cloud
- Les erreurs d'une commande n'affectent pas les autres
