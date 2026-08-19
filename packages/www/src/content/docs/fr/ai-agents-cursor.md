---
title: Guide de configuration de Cursor
description: Configurez l'IDE Cursor pour travailler avec l'infrastructure Rediacc en utilisant .cursorrules et l'intégration du terminal.
category: Guides
tags:
  - ai-agents
  - cli
order: 32
language: fr
sourceHash: "e0fb319a9e477324"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

En bref : `.cursorrules` charge le contexte Rediacc dans l'IA de Cursor ; le terminal lui permet d'exécuter des commandes `rdc` sur vos machines réelles.

## Configuration rapide

1. Installez le CLI : `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copiez le [modèle AGENTS.md](/fr/docs/agents-md-template) à la racine de votre projet sous le nom `.cursorrules`
3. Ouvrez le projet dans Cursor

Cursor lit `.cursorrules` au démarrage. À noter : les limites de fenêtre de contexte s'appliquent, aussi gardez le fichier centré sur vos machines et dépôts réels plutôt que sur des modèles génériques.

## Configuration de .cursorrules

Créez `.cursorrules` à la racine de votre projet avec le contexte d'infrastructure Rediacc. Consultez le [modèle AGENTS.md](/fr/docs/agents-md-template) complet pour une version intégrale.

Les sections clés à inclure :

- Nom de l'outil CLI (`rdc`) et installation
- Commandes courantes avec l'option `--output json`
- Vue d'ensemble de l'architecture (isolation des dépôts, daemons Docker)
- Règles de terminologie (adaptateurs, pas de modes)

## Intégration avec le terminal

Cursor peut exécuter des commandes `rdc` via son terminal intégré. Schémas courants :

### Vérifier l'état

Demandez à Cursor : *"Vérifie l'état de mon serveur de production"*

Cursor exécute dans le terminal :
```bash
rdc machine status prod-1 -o json
```

### Déployer des modifications

Demandez à Cursor : *"Déploie la configuration mise à jour de nextcloud"*

Cursor exécute dans le terminal :
```bash
rdc repo up nextcloud@prod-1 --yes
```

### Voir les journaux

Demandez à Cursor : *"Montre-moi les journaux récents du conteneur de messagerie"*

Cursor exécute dans le terminal :
```bash
rdc repo logs mail@prod-1 -c mail-postfix --lines 100
```

## Paramètres de l'espace de travail

Pour les projets d'équipe, ajoutez les paramètres Cursor spécifiques à Rediacc dans `.cursor/settings.json` :

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## Conseils

- Le mode Composer de Cursor fonctionne bien pour les tâches d'infrastructure en plusieurs étapes
- Utilisez `@terminal` dans le chat de Cursor pour référencer la sortie récente du terminal
- La commande `rdc --help-all` fournit à Cursor une référence complète des commandes
- Combinez `.cursorrules` avec un fichier `CLAUDE.md` pour une compatibilité maximale entre les outils IA
