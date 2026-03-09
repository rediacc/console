---
title: Guide de configuration de Claude Code
description: Guide étape par étape pour configurer Claude Code pour la gestion autonome de l'infrastructure Rediacc.
category: Guides
order: 31
language: fr
sourceHash: "faa990e37ee96a23"
---

Claude Code fonctionne nativement avec Rediacc via le CLI `rdc`. Ce guide couvre la configuration, les permissions et les flux de travail courants.

## Configuration rapide

1. Installez le CLI : `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copiez le [modèle AGENTS.md](/fr/docs/agents-md-template) à la racine de votre projet sous le nom `CLAUDE.md`
3. Lancez Claude Code dans le répertoire du projet

Claude Code lit `CLAUDE.md` au démarrage et l'utilise comme contexte persistant pour toutes les interactions.

## Configuration de CLAUDE.md

Placez ceci à la racine de votre projet. Consultez le [modèle AGENTS.md](/fr/docs/agents-md-template) complet pour une version intégrale. Sections clés :

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine info <machine> -o json
- Deploy: rdc repo up <repo> -m <machine> --yes
- Containers: rdc machine containers <machine> -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Permissions des outils

Claude Code demandera la permission d'exécuter les commandes `rdc`. Vous pouvez préautoriser les opérations courantes en les ajoutant à la configuration de Claude Code :

- Autoriser `rdc machine info *` — vérifications d'état en lecture seule
- Autoriser `rdc machine containers *` — listage des conteneurs
- Autoriser `rdc machine health *` — vérifications de santé
- Autoriser `rdc config repositories` — listage des dépôts

Pour les opérations destructives (`rdc repo up`, `rdc repo delete`), Claude Code demandera toujours une confirmation sauf si vous les autorisez explicitement.

## Exemples de flux de travail

### Vérifier l'état de l'infrastructure

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine info prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Déployer un dépôt

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail -m prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail -m prod-1 --yes
→ Deploys the repository
```

### Diagnostiquer des problèmes de conteneurs

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine containers prod-1 -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### Synchronisation de fichiers

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload -m prod-1 -r mail -l ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload -m prod-1 -r mail -l ./config
→ Syncs the files
```

## Conseils

- Claude Code détecte automatiquement le non-TTY et bascule en sortie JSON — pas besoin de spécifier `-o json` dans la plupart des cas
- Utilisez `rdc agent capabilities` pour que Claude Code découvre toutes les commandes disponibles
- Utilisez `rdc agent schema "command name"` pour des informations détaillées sur les arguments et options
- L'option `--fields` aide à réduire l'utilisation de la fenêtre de contexte quand vous n'avez besoin que de données spécifiques
