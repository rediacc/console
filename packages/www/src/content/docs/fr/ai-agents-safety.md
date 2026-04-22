---
title: Sécurité et garde-fous pour les agents IA
description: 'Comment la CLI de Rediacc empêche les assistants de codage IA de divulguer des secrets, d''écraser des identifiants ou d''escalader des privilèges: compuertas de connaissance, rédaction, substitutions vérifiées par ascendance et un journal d''audit enchaîné par hash.'
category: Concepts
order: 35
language: fr
sourceHash: "6a4f4ccd6ae806ee"
sourceCommit: "4bef9a170fb07db00a4ee2ef504aa27706bcd15a"
---

Lorsque Claude Code, Cursor, Gemini CLI, Copilot CLI ou tout autre assistant de codage IA pilote `rdc`, la CLI le traite différemment d'un humain au clavier. Cette page explique ce que l'agent peut faire, ce qu'il ne peut pas faire, et comment les garde-fous tiennent même lorsque l'agent essaie de les contourner.

## Référence rapide: ce que les agents peuvent et ne peuvent pas faire

| Opération | Comportement par défaut de l'agent | Comment débloquer pour un cas d'usage spécifique |
|---|---|---|
| `rdc config show` (expurgé) | ✅ allowed |  |
| `rdc config field get --pointer <pointer>` (stub expurgé ou digest) | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (champ public) | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (champ sensible, **avec `--current` correct**) | ✅ allowed |  |
| `rdc config edit --dump` (JSONC expurgé) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (champ sensible, sans `--current`) | 🔴 refused | Fournir `--current "<ancienne valeur>"` |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Utiliser `--digest` à la place |
| `rdc config show --reveal` | 🔴 refused | Utiliser `rdc config show` sans option |
| `rdc config edit` (éditeur interactif) | 🔴 refused | L'humain définit `REDIACC_ALLOW_CONFIG_EDIT=*` avant de lancer l'agent |
| `rdc config edit --apply <file>` | 🔴 refused | Même substitution |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | Même substitution ; utilise une confirmation interactive |
| `rdc term connect -m <machine>` (SSH direct vers la machine) | 🔴 refused | Forker d'abord un dépôt et se connecter au fork |

Tout ce qui est refusé à un agent est consigné dans le journal d'audit avec `outcome: refused` et une raison.

## Comment les agents sont détectés

La CLI traite un processus comme un agent lorsque l'une de ces conditions est vraie :

- L'une des variables `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` est définie à `"1"`, ou `CURSOR_TRACE_ID` est définie du tout.
- Sur Linux : tout processus parent dans la chaîne d'ascendance possède l'une de ces variables dans son environnement (via `/proc/<pid>/environ`). Même si l'agent supprime ses propres variables avec `env -i` ou un script enveloppant, la chaîne parente indique toujours à la CLI qui l'a démarré.

La détection s'exécute une fois par processus et est mise en cache. Elle ne peut pas être désactivée.

## Le modèle de compuerta de connaissance

Les mutations sensibles suivent la convention `passwd(1)` : pour modifier un secret, prouvez que vous le connaissiez déjà.

- Vous voulez faire tourner un token API stocké à `/credentials/cfDnsApiToken` ?
- La CLI demande : « quelle est la valeur actuelle ? »
- L'agent fournit le texte brut via `--current "$OLD"`. La CLI applique SHA-256 à `$OLD` et compare avec le digest de la valeur actuellement stockée. Correspondance → l'écriture passe. Discordance → refusé, audité.

Le modèle est simple mais ferme trois surfaces d'attaque :

1. **Rotation silencieuse** : un agent sans accès préalable à `$OLD` ne peut pas le remplacer par une valeur de son choix.
2. **Exfiltration par sondage** : la réponse du digest ne contient jamais de texte brut ; même un journal d'audit compromis affiche `expected abc12345…, got deadbeef…`, pas les valeurs sous-jacentes.
3. **Écrasement accidentel de la configuration utilisateur** : nécessite un `--current` délibéré à chaque fois ; pas de remplacement automatique sur `set`.

### Exemple concret

```bash
# Obtenir le digest court du stub de rédaction (sûr pour les agents).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Tentative d'écrasement sans preuve: refusé.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Fournir le texte brut actuel: autorisé.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Si l'agent n'a jamais eu `$OLD_CF_TOKEN`, il ne peut pas satisfaire la précondition et la rotation est refusée. L'utilisateur qui *l'a* peut toujours le faire via l'éditeur ou en passant `--current` depuis son shell.

## Rédaction par défaut

Chaque commande `rdc` qui lit un état sensible: `config show`, `config field get`, `config machine list`, `config edit --dump`: renvoie des **stubs de rédaction** pour les champs secrets, pas du texte brut :

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Le suffixe hexadécimal de 8 caractères du stub correspond aux 8 premiers caractères de `sha256(canonicalize(value))`: assez pour distinguer deux valeurs différentes d'un coup d'œil, pas assez pour les inverser. Un agent peut utiliser un stub pour suivre si une valeur a changé sans jamais la voir.

`--reveal` lève la rédaction pour les humains sur un TTY interactif. Les agents sont refusés quel que soit l'état du TTY. Chaque autorisation écrit une entrée d'audit `reveal_granted` ; chaque refus écrit une entrée `refused` avec les signaux d'agent de l'acteur attachés.

## La substitution `REDIACC_ALLOW_CONFIG_EDIT`

Certaines opérations: l'éditeur interactif, `--apply`, `field rotate`: existent pour les humains et n'ont pas de chemin sûr pour les agents. Si vous voulez activement qu'un agent en effectue une, vous définissez :

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # contournement total
# ou
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (globs de portée séparés par des virgules: wildcards * autorisés par segment)
```

…et l'agent l'hérite.

**Détail crucial** : la substitution doit apparaître dans un processus **au-dessus** de l'agent dans la chaîne d'ascendance. Si l'agent la définit dans son propre environnement (ou dans un sous-shell qu'il a engendré), la CLI refuse et vous le signale :

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

L'effet : un agent ne peut pas se frayer un chemin au-delà d'un garde-fou en exécutant `export REDIACC_ALLOW_CONFIG_EDIT='*'` en cours de session. Seul un processus parent (vous, dans votre terminal, avant de lancer l'agent) peut ouvrir cette porte.

## Journal d'audit

Chaque mutation, chaque refus, chaque autorisation `--reveal` écrit une ligne JSONL dans `~/.config/rediacc/audit.log.jsonl` (mode `0600`, pivoté à 10 Mo). Chaque ligne est enchaînée par hash : son champ `prevHash` est `sha256("<ligne précédente>")`. Altérer une ligne brise la chaîne sur toutes les lignes suivantes.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### Inspection

```bash
# Lister les entrées récentes
rdc config audit log --since 24h

# Filtrer par glob de pointeur
rdc config audit log --path '/credentials/*'

# Uniquement les entrées initiées par des agents
rdc config audit log --actor agent

# Diffuser les nouvelles entrées en direct (Ctrl+C pour arrêter)
rdc config audit tail

# Vérifier que la chaîne de hash est intacte
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   OU
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### Ce qui n'apparaît jamais dans le journal d'audit

- Valeurs de secrets en texte brut
- Phrases de passe, tokens, clés SSH
- Les valeurs ancien/nouveau lors d'un échec de précondition `--current` (uniquement le préfixe de digest de 8 caractères)

Le journal peut être partagé en toute sécurité avec un auditeur de sécurité ou joint à un rapport de bug.

## Limites du modèle comportemental

Les garde-fous de l'agent sont **comportementaux, pas cryptographiques**. Un agent déterminé ou dirigé s'exécutant sous le même UID que le fichier de configuration peut toujours faire `cat ~/.config/rediacc/rediacc.json` et lire le texte brut, car le fichier est lisible par le processus.

Pour une application cryptographique réelle, utilisez le [magasin de configuration chiffré](/fr/docs/config-storage) : les secrets résident côté serveur, chaque champ sensible porte un engagement HMAC par champ, et le worker de compte refuse les écritures dont la précondition `--current` ne correspond pas par hash à ce qu'il a stocké. Le serveur ne voit jamais le texte brut: zero-knowledge: mais il applique bien la compuerta.

Le chemin du fichier local est « le chemin facile est sûr ». Le chemin du magasin distant est « le chemin difficile est difficile aussi ».

## Recettes rapides

### Permettre à un agent de faire tourner un seul token cloud

```bash
# En tant que vous, avant de démarrer l'agent :
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # ou cursor, gemini, etc.
```

L'agent peut maintenant exécuter `config field rotate /credentials/cfDnsApiToken --new …` mais ne peut toujours pas modifier `/credentials/ssh/privateKey` ni ouvrir l'éditeur interactif.

### Permettre à un agent d'effectuer une session de modification de configuration large

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

L'agent peut ouvrir `rdc config edit`, utiliser `--reveal` et exécuter `field rotate`. Chaque action est toujours journalisée dans l'audit avec `actor.kind: agent` et le signal `CLAUDECODE`.

### Découvrir quels champs un agent est autorisé à toucher

```bash
rdc config field list --sensitive --output json
```

Renvoie chaque modèle de pointeur, son type (`secret` / `credential` / `pii` / `identifier`), et s'il est engagé dans l'enveloppe HMAC côté serveur.

## Voir aussi

- [Aperçu de l'intégration des agents IA](/fr/docs/ai-agents-overview): la vue d'ensemble
- [Configuration de Claude Code](/fr/docs/ai-agents-claude-code): modèle d'intégration
- [Enveloppe de sortie JSON](/fr/docs/ai-agents-json-output): réponses lisibles par machine
- [Magasin de configuration chiffré](/fr/docs/config-storage): application cryptographique côté serveur
- [Sécurité du compte](/fr/docs/account-security): posture de sécurité côté opérateur
