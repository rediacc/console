---
title: Référence de la sortie JSON
description: Référence complète du format de sortie JSON du CLI rdc, schéma de l'enveloppe, gestion des erreurs et commandes de découverte pour les agents.
category: Reference
order: 51
language: fr
sourceHash: "a516c49fdaf9a901"
---

Toutes les commandes `rdc` prennent en charge la sortie JSON structurée pour la consommation programmatique par les agents IA et les scripts.

## Activer la sortie JSON

### Option explicite

```bash
rdc machine info prod-1 --output json
rdc machine info prod-1 -o json
```

### Détection automatique

Lorsque `rdc` s'exécute dans un environnement non-TTY (tube, sous-shell ou lancé par un agent IA), la sortie bascule automatiquement en JSON. Aucune option n'est nécessaire.

```bash
# These all produce JSON automatically
result=$(rdc machine info prod-1)
echo '{}' | rdc agent exec "machine info"
```

## Enveloppe JSON

Chaque réponse JSON utilise une enveloppe cohérente :

```json
{
  "success": true,
  "command": "machine info",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `success` | `boolean` | Si la commande s'est terminée avec succès |
| `command` | `string` | Le chemin complet de la commande (p. ex., `"machine info"`, `"repo up"`) |
| `data` | `object \| array \| null` | Données spécifiques à la commande en cas de succès, `null` en cas d'erreur |
| `errors` | `array \| null` | Objets d'erreur en cas d'échec, `null` en cas de succès |
| `warnings` | `string[]` | Avertissements non fatals collectés pendant l'exécution |
| `metrics` | `object` | Métadonnées d'exécution |

## Réponses d'erreur

Les commandes en échec renvoient des erreurs structurées avec des indications de récupération :

```json
{
  "success": false,
  "command": "machine info",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### Champs d'erreur

| Champ | Type | Description |
|-------|------|-------------|
| `code` | `string` | Code d'erreur lisible par machine |
| `message` | `string` | Description lisible par l'humain |
| `retryable` | `boolean` | Si réessayer la même commande peut réussir |
| `guidance` | `string` | Action suggérée pour résoudre l'erreur |

### Erreurs réessayables

Ces types d'erreur sont marqués `retryable: true` :

- **NETWORK_ERROR** — Échec de connexion SSH ou réseau
- **RATE_LIMITED** — Trop de requêtes, attendez et réessayez
- **API_ERROR** — Défaillance transitoire du backend

Les erreurs non réessayables (authentification, non trouvé, arguments invalides) nécessitent une action corrective avant de réessayer.

## Filtrer la sortie

Utilisez `--fields` pour limiter la sortie à des clés spécifiques. Cela réduit l'utilisation de tokens quand seules des données spécifiques sont nécessaires :

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## Sortie de simulation

Les commandes destructives prennent en charge `--dry-run` pour prévisualiser ce qui se passerait :

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

Commandes prenant en charge `--dry-run` : `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Commandes de découverte pour les agents

Le sous-commande `rdc agent` fournit une introspection structurée pour que les agents IA découvrent les opérations disponibles au moment de l'exécution.

### Lister toutes les commandes

```bash
rdc agent capabilities
```

Renvoie l'arbre complet des commandes avec les arguments, les options et les descriptions :

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine info",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### Obtenir le schéma d'une commande

```bash
rdc agent schema "machine info"
```

Renvoie le schéma détaillé d'une seule commande, incluant tous les arguments et options avec leurs types et valeurs par défaut.

### Exécuter via JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine info"
```

Accepte du JSON sur stdin, associe les clés aux arguments et options de la commande, et exécute avec sortie JSON forcée. Utile pour la communication structurée agent-CLI sans construire de chaînes de commandes shell.

## Exemples d'analyse

### Shell (jq)

```bash
status=$(rdc machine info prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "info", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'info', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
