---
title: Intégration des agents IA - Vue d'ensemble
description: Comment les assistants de programmation IA comme Claude Code, Cursor et Cline s'intègrent à l'infrastructure Rediacc pour le déploiement et la gestion autonomes.
category: Guides
order: 30
language: fr
---

Les assistants de programmation IA peuvent gérer l'infrastructure Rediacc de manière autonome via le CLI `rdc`. Ce guide couvre les approches d'intégration et comment démarrer.

## Pourquoi l'auto-hébergement + agents IA

L'architecture de Rediacc est naturellement compatible avec les agents :

- **CLI d'abord** : Chaque opération est une commande `rdc` — aucune GUI requise
- **Basé sur SSH** : Le protocole que les agents connaissent le mieux grâce aux données d'entraînement
- **Sortie JSON** : Toutes les commandes prennent en charge `--output json` avec une enveloppe cohérente
- **Isolation Docker** : Chaque dépôt dispose de son propre daemon et espace de noms réseau
- **Scriptable** : `--yes` ignore les confirmations, `--dry-run` prévisualise les opérations destructives

## Approches d'intégration

### 1. Modèle AGENTS.md / CLAUDE.md

Le moyen le plus rapide de commencer. Copiez notre [modèle AGENTS.md](/fr/docs/agents-md-template) à la racine de votre projet :

- `CLAUDE.md` pour Claude Code
- `.cursorrules` pour Cursor
- `.windsurfrules` pour Windsurf

Cela donne à l'agent un contexte complet sur les commandes disponibles, l'architecture et les conventions.

### 2. Pipeline de sortie JSON

Lorsque les agents appellent `rdc` dans un sous-shell, la sortie bascule automatiquement en JSON (détection non-TTY). Chaque réponse JSON utilise une enveloppe cohérente :

```json
{
  "success": true,
  "command": "machine info",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

Les réponses d'erreur incluent les champs `retryable` et `guidance` :

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
  }]
}
```

### 3. Découverte des capacités de l'agent

Le sous-commande `rdc agent` fournit une introspection structurée :

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine info"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine info"
```

## Options clés pour les agents

| Option | Objectif |
|--------|----------|
| `--output json` / `-o json` | Sortie JSON lisible par machine |
| `--yes` / `-y` | Ignorer les confirmations interactives |
| `--quiet` / `-q` | Supprimer la sortie informative sur stderr |
| `--fields name,status` | Limiter la sortie à des champs spécifiques |
| `--dry-run` | Prévisualiser les opérations destructives sans exécuter |

## Prochaines étapes

- [Guide de configuration de Claude Code](/fr/docs/ai-agents-claude-code) — Configuration étape par étape de Claude Code
- [Guide de configuration de Cursor](/fr/docs/ai-agents-cursor) — Intégration avec l'IDE Cursor
- [Référence de la sortie JSON](/fr/docs/ai-agents-json-output) — Documentation complète de la sortie JSON
- [Modèle AGENTS.md](/fr/docs/agents-md-template) — Modèle de configuration d'agent prêt à copier-coller
