---
title: Intégration des agents IA - Vue d'ensemble
description: "Comment Claude Code, Cursor et Cline gèrent l'infrastructure Rediacc via rdc : sortie JSON, introspection des agents et garde-fous de sécurité."
category: Guides
order: 30
language: fr
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

De fait, `rdc` est conçu pour les agents dès sa conception. Claude Code, Cursor, Cline : tout assistant IA qui appelle `rdc` dans un sous-shell obtient une sortie JSON structurée, des erreurs lisibles par machine et les garde-fous nécessaires à la gestion autonome de l'infrastructure Rediacc. Voici comment fonctionne l'intégration.

## Pourquoi l'auto-hébergement + agents IA

L'architecture de Rediacc est naturellement compatible avec les agents :

- **CLI d'abord** : Chaque opération est une commande `rdc`, aucune interface graphique requise
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

Déposez-le à la racine et l'agent dispose de la référence complète des commandes, du contexte d'architecture et des conventions dont il a besoin pour travailler sans tâtonner.

### 2. Pipeline de sortie JSON

Lorsque les agents appellent `rdc` dans un sous-shell, la sortie bascule automatiquement en JSON (détection non-TTY). Chaque réponse JSON utilise une enveloppe cohérente :

```json
{
  "success": true,
  "command": "machine query",
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
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. Découverte des capacités de l'agent

La sous-commande `rdc agent` fournit une introspection structurée :

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema --command "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Options clés pour les agents

| Option | Objectif |
|--------|----------|
| `--output json` / `-o json` | Sortie JSON lisible par machine |
| `--yes` / `-y` | Ignorer les confirmations interactives |
| `--quiet` / `-q` | Supprimer la sortie informative sur stderr |
| `--fields name,status` | Limiter la sortie à des champs spécifiques |
| `--dry-run` | Prévisualiser les opérations destructives sans exécuter |

## Sécurité et garde-fous

Le CLI ne traite pas les agents comme un humain devant un terminal. Les opérations sensibles requièrent la preuve que l'état courant est déjà connu (l'option `--current`), les flux nécessitant un éditeur interactif sont refusés par défaut, et chaque refus est consigné dans le journal d'audit. La référence [Sécurité et garde-fous des agents IA](/fr/docs/ai-agents-safety) couvre la table de blocage complète, le modèle de validation des connaissances, la portée `REDIACC_ALLOW_CONFIG_EDIT` et le journal d'audit chaîné par hachage.

## Prochaines étapes

- [Sécurité et garde-fous des agents IA](/fr/docs/ai-agents-safety), Ce que les agents peuvent et ne peuvent pas faire, validation des connaissances, journal d'audit
- [Guide de configuration de Claude Code](/fr/docs/ai-agents-claude-code), Configuration étape par étape de Claude Code
- [Guide de configuration de Cursor](/fr/docs/ai-agents-cursor), Intégration avec l'IDE Cursor
- [Référence de la sortie JSON](/fr/docs/ai-agents-json-output), Documentation complète de la sortie JSON
- [Modèle AGENTS.md](/fr/docs/agents-md-template), Modèle de configuration d'agent prêt à copier-coller
