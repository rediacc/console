---
title: Référence de la sortie JSON
description: >-
  Référence complète du format de sortie JSON du CLI rdc, schéma de l'enveloppe,
  gestion des erreurs et commandes de découverte pour les agents.
category: Reference
order: 51
language: fr
sourceHash: "9f8d61df26b59757"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Toutes les commandes `rdc` produisent du JSON structuré. Redirigez-le vers un script ou transmettez-le directement à un agent.

## Activer la sortie JSON

### Option explicite

```bash
rdc machine query --name prod-1 --output json
rdc machine query --name prod-1 -o json
```

### Détection automatique

Lorsque `rdc` s'exécute dans un environnement non-TTY (tube, sous-shell ou lancé par un agent IA), la sortie bascule automatiquement en JSON. Aucune option n'est nécessaire.

```bash
# These all produce JSON automatically
result=$(rdc machine query --name prod-1)
echo '{}' | rdc agent exec "machine query"
```

## Enveloppe JSON

Chaque réponse JSON utilise une enveloppe cohérente :

```json
{
  "success": true,
  "command": "machine query",
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
| `command` | `string` | Le chemin complet de la commande (p. ex., `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | Données spécifiques à la commande en cas de succès, `null` en cas d'erreur |
| `errors` | `array \| null` | Objets d'erreur en cas d'échec, `null` en cas de succès |
| `warnings` | `string[]` | Avertissements non fatals collectés pendant l'exécution |
| `metrics` | `object` | Métadonnées d'exécution |

## Réponses d'erreur

Les commandes en échec renvoient des erreurs structurées avec des indications de récupération :

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
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
| `code` | `string` | Code d'erreur lisible par machine (voir les constantes `ERROR_CODES` pour la liste canonique) |
| `message` | `string` | Description lisible par l'humain |
| `retryable` | `boolean` | Si réessayer la même commande peut réussir |
| `guidance` | `string` | Indication libre (legacy. Préférer `next` pour des données d'action structurées) |
| `next` | `object?` | Indication d'action suivante structurée (si présente). Voir ci-dessous |

### Indications d'action structurées via `next`

Pour certains codes d'erreur à fort impact comme `PRECONDITION_MISMATCH`, l'erreur inclut un champ `next` contenant les commandes exactes à proposer à l'utilisateur. Tous les codes d'erreur ne disposent pas de ce champ, seulement ceux pour lesquels un chemin de récupération est défini. **Les agents doivent relayer `next.options[].run` tel quel à l'utilisateur plutôt que de synthétiser leur propre commande.** Cela évite le cas de figure où l'agent invente une commande inexistante, ce qui arrive plus souvent qu'on ne le croit.

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

Schéma :

| Champ | Type | Description |
|-------|------|-------------|
| `next.summary` | `string` | Description en une ligne de ce que l'utilisateur doit décider |
| `next.options[]` | `array` | Actions concrètes ; chacune est une alternative que l'utilisateur peut choisir |
| `next.options[].description` | `string` | Explication lisible par l'humain de cette option |
| `next.options[].run` | `string` | Commande CLI exacte. À relayer verbatim à l'utilisateur |

### Erreurs réessayables

Ces types d'erreur sont marqués `retryable: true` :

- **NETWORK_ERROR**, Échec de connexion SSH ou réseau
- **RATE_LIMITED**, Trop de requêtes, attendez et réessayez
- **API_ERROR**, Défaillance transitoire du backend

Les erreurs non réessayables (authentification, non trouvé, arguments invalides) nécessitent une action corrective avant de réessayer.

## Filtrer la sortie

Utilisez `--fields` pour limiter la sortie à des clés spécifiques et réduire l'utilisation de tokens :

```bash
rdc machine containers --name prod-1 -o json --fields name,status,repository
```

## Sortie de simulation

Les commandes destructives prennent en charge `--dry-run` pour prévisualiser ce qui se passerait :

```bash
rdc repo delete --name mail -m prod-1 --dry-run -o json
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

Le sous-commande `rdc agent` offre aux agents IA une façon structurée de découvrir les opérations disponibles au moment de l'exécution.

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
        "name": "machine query",
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
rdc agent schema --command "machine query"
```

Renvoie le schéma complet d'une seule commande : chaque argument et option avec son type et sa valeur par défaut.

### Exécuter via JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

Accepte du JSON sur stdin, associe les clés aux arguments et options de la commande, et exécute avec sortie JSON forcée. Utile quand vous préférez ne pas construire de chaînes de commandes shell pour les appels agent-CLI.

## Exemples d'analyse

### Shell (jq)

```bash
status=$(rdc machine query --name prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
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

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
