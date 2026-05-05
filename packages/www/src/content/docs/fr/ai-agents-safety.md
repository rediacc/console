---
title: Sécurité et garde-fous pour les agents IA
description: 'Comment la CLI de Rediacc empêche les assistants de codage IA de divulguer des secrets, d''écraser des identifiants ou d''escalader des privilèges. Compuertas de connaissance, rédaction, substitutions vérifiées par ascendance et un journal d''audit enchaîné par hash.'
category: Concepts
order: 35
language: fr
sourceHash: "43f8eb06d0f5f7a1"
sourceCommit: "c6db1fb9ec9979425e22578d31c3c188bc7e73f9"
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

## Prise en charge des plateformes : Linux uniquement pour les substitutions

`REDIACC_ALLOW_CONFIG_EDIT` et `REDIACC_ALLOW_GRAND_REPO` reposent tous deux sur la vérification d'ascendance pour prouver que la substitution a été définie par vous et non injectée par l'agent. La vérification lit `/proc/<pid>/environ` pour chaque processus de la chaîne. Ce fichier est défini par le noyau au moment de l'exec et ne peut pas être modifié par le processus lui-même, de sorte que l'environnement du shell parent est un témoin inviolable.

Ce fichier n'existe pas sur macOS ou Windows. Sans moyen de vérifier la légitimité, la CLI échoue en sécurité. Même si vous définissez correctement la substitution dans votre shell avant de lancer l'agent, la substitution est rejetée. Le message d'erreur vous indique exactement quoi faire :

> The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. … To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).

En pratique, les utilisateurs non-Linux n'ont aucune issue de secours hors du flux fork-first. C'est intentionnel. Les agents sont poussés à travers un bac à sable qu'ils ne peuvent pas contourner, quelle que soit la façon dont ils ont été instruits. Exécutez votre agent dans WSL, un conteneur Linux ou une VM Linux si vous avez besoin de la substitution ; sinon, travaillez sur un fork.

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

## Ce que Rediacc n'isole pas

Les garde-fous des agents décrits sur cette page protègent l'infrastructure propre à Rediacc : le fichier de configuration, le démon Docker par dépôt, les données de dépôt chiffrées par LUKS, le bac à sable SSH limité. Ils ne protègent pas les services externes pour lesquels votre dépôt détient des identifiants.

Un fork de dépôt est un reflink BTRFS du volume du parent. Tout ce qui se trouve sur disque dans le parent est identique octet pour octet dans le fork : le code, les données et les fichiers `.env` indifféremment. Si votre dépôt contient une `STRIPE_LIVE_KEY`, un `AWS_ACCESS_KEY_ID`, un token API Railway ou tout autre identifiant à longue durée de vie pour un service tiers, le fork en hérite. Un agent opérant dans le bac à sable du fork peut lire ce fichier, exfiltrer la valeur ou l'utiliser pour appeler l'API tierce. Le service tiers n'a aucun moyen de savoir que l'appel provenait d'un fork plutôt que de la production.

Voici la ligne de responsabilité partagée :

| Frontière | Propriétaire |
|---|---|
| Données du dépôt, espace de noms de montage, périmètre Docker, garde-fous des agents, journal d'audit | Rediacc |
| Rayon d'impact des services externes (Stripe, AWS, Railway, GitHub, etc.) | Développeur du dépôt |

Trois patterns comblent le fossé côté développeur :

1. **Ne stockez pas du tout les identifiants externes de production dans le dépôt.** Récupérez-les depuis un gestionnaire de secrets externe (HashiCorp Vault, AWS Secrets Manager, 1Password Connect) au démarrage du conteneur. Les conteneurs du fork récupèrent par conception des identifiants limités au bac à sable, car ils s'identifient différemment.
2. **Supprimez ou échangez les identifiants au moment du fork via le hook `up()` du Rediaccfile.** Le `up()` d'un fork s'exécute avec un GUID de dépôt différent de celui du parent. Détectez cela, puis réécrivez `.env` avec des valeurs de bac à sable, provisionnez un compte Stripe sandbox par fork, dirigez les chaînes de connexion à la base vers une instance de test par fork, et ainsi de suite. Consultez [Services](/fr/docs/services) pour la référence des hooks de cycle de vie.
3. **Restreignez le réseau sortant du fork avec un filtrage egress eBPF** afin que le fork ne puisse atteindre que localhost et les points de terminaison sandbox explicites. L'isolation réseau par dépôt de Rediacc en est la fondation ; les listes d'autorisation egress par fork ne sont pas implémentées aujourd'hui, mais la voie est ouverte.

Rediacc gère la moitié infrastructure de la sécurité des agents. La moitié services externes vit dans votre Rediaccfile.

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
