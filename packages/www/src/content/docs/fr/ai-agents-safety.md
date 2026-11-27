---
title: Sécurité et garde-fous pour les agents IA
description: >-
  Comment Rediacc empêche les assistants de programmation IA de divulguer des
  secrets, d'écraser des identifiants ou d'élever leurs privilèges. Une seule
  décision pour toutes les surfaces, adhésion explicite ET plafond de politique,
  barrières de connaissance, expurgation et journal d'audit chaîné par hachage par organisation et par jour sur le serveur, et dans un fichier local pour la CLI.
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: fr
sourceHash: "43350a2e682cebcc"
sourceCommit: "cc655e698ed2c42faef5311e268425c04997f243"
---

Vous pointez un assistant de codage IA vers votre infrastructure. Lorsque Claude Code, Cursor, Gemini CLI, Copilot CLI ou tout outil similaire pilote `rdc`, la CLI le détecte et applique un ensemble de règles différent de celui applicable à un humain au clavier. Cette page explique ce que l'agent peut faire, ce qu'il ne peut pas faire, et comment les garde-fous tiennent même lorsqu'il cherche à les contourner.

## Référence rapide: ce que les agents peuvent et ne peuvent pas faire

| Opération | Comportement par défaut de l'agent | Comment débloquer pour un cas d'usage spécifique |
|---|---|---|
| `rdc config show` (expurgé) | ✅ allowed |  |
| `rdc config field get --pointer <pointer>` (stub expurgé ou digest) | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (champ public) | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (champ sensible, **avec `--current` correct**) | ✅ allowed |  |
| `rdc config edit --dump --redacted` (JSONC expurgé) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (champ sensible, sans `--current`) | 🔴 refused | Fournir `--current "<ancienne valeur>"` |
| `rdc repo secret set <repo> --rotate-secret` (rotation sans `--current`) | 🔴 refused | Fournir `--current`, ou un humain effectue la rotation dans un terminal |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Utiliser `--digest` à la place |
| `rdc config show --reveal` | 🔴 refused | Utiliser `rdc config show` sans option |
| `rdc config edit` (éditeur interactif) | 🔴 refused, sans dérogation | Consulter avec `--dump --redacted`, modifier un seul champ avec `config field set --current` |
| `rdc config edit --apply <file>` | 🔴 refused, sans dérogation | Idem ; un humain dans un terminal applique les modifications du document entier |
| `rdc config edit --reveal` | 🔴 refused, sans dérogation | Idem |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | Un humain l'exécute dans un terminal interactif |
| Modifier un dépôt grand (production) | 🔴 refused | Adhésion explicite d'un humain pour ce dépôt, dans le cadre d'une politique qui autorise les modifications de dépôts grand ([ci-dessous](#one-decision-opt-in-and-policy-ceiling)) |
| Opérations de cycle de vie d'un cluster ou d'un datastore | 🔴 refused | Adhésion explicite d'un humain pour ce cluster, dans le cadre d'une politique qui autorise les opérations de cluster |
| `rdc term connect <machine>` (SSH direct vers la machine) | 🔴 refused | Forker d'abord un dépôt et se connecter au fork |

Tout ce qui est refusé à un agent est consigné dans le journal d'audit avec `outcome: refused` et une raison. La modification du document de configuration entier n'offre aucune voie à un agent : la configuration contient l'identifiant LUKS de chaque dépôt, et un agent capable de la réécrire pourrait aussi supprimer un identifiant sans lequel le volume chiffré ne peut pas être ouvert.

## Comment les agents sont détectés

La CLI traite un processus comme un agent lorsque l'une de ces conditions est vraie :

- L'une des variables `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` est définie à `"1"`, ou `CURSOR_TRACE_ID` est définie du tout.
- Sur Linux : tout processus parent dans la chaîne d'ascendance possède l'une de ces variables dans son environnement (via `/proc/<pid>/environ`). Même si l'agent supprime ses propres variables avec `env -i` ou un script enveloppant, la chaîne parente indique toujours à la CLI qui l'a démarré.

La détection s'exécute une fois par processus et est mise en cache. Elle ne peut pas être désactivée. Une délégation MCP distante marque ses appels comme des appels d'agent sur l'exécuteur, sans aucune détection.

## Une seule décision : adhésion explicite ET plafond de politique

Chaque surface qui exécute une commande `rdc` (le CLI, le serveur MCP local, le serveur MCP distant, `rdc --proxy` et la console web) interroge la même fonction de décision, si bien que toutes refusent et autorisent les mêmes choses. Elle applique deux conditions, et un agent n'agit que là où les deux sont remplies :

1. **Le plafond de politique.** La politique de l'organisation, restreinte par celle de l'équipe, décide quelles commandes, machines et dépôts un appelant peut utiliser, et si les modifications de dépôts grand (`allowGrandRepos`) et les opérations de cluster (`allowClusterOps`) sont autorisées. Une configuration sans enregistrement de politique retombe sur une valeur par défaut selon le rôle : les propriétaires et les administrateurs peuvent agir, les membres non. La politique est un enregistrement scellé distinct que seuls les propriétaires et les administrateurs écrivent ([Modèle de sécurité](/fr/docs/security-model#policy)) ; aucun agent et aucune commande du CLI ne peut la modifier.
2. **L'adhésion explicite de l'humain.** À l'intérieur du plafond, un agent a encore besoin qu'un humain désigne le dépôt grand ou le cluster qu'il peut modifier :
   - **Agents locaux** (CLI et MCP local) : l'humain exporte `REDIACC_ALLOW_GRAND_REPO` (noms de dépôts, ou `*`) ou `REDIACC_ALLOW_CLUSTER_OPS` (noms de clusters, ou `*`) dans le terminal avant de démarrer l'agent. Le CLI vérifie l'ascendance des processus, donc une variable que l'agent définit en cours de session ne compte pas ([comment c'est vérifié sur chaque système d'exploitation](#how-a-local-opt-in-is-verified-on-each-os)).
   - **Agents distants** (MCP distant) : les adhésions font partie de la délégation que l'humain crée dans l'interface du compte ([Serveur distant](/fr/docs/ai-agents-mcp#remote-server)).

Une adhésion n'élargit jamais le plafond : un dépôt que la politique ferme reste fermé, quoi que disent l'environnement ou la délégation. Les forks n'ont pas besoin d'adhésion. Un dépôt que le CLI ne sait pas identifier compte comme grand.

**Les modifications destructrices demandent d'abord.** Quand un agent est autorisé à effectuer une modification destructrice sur un dépôt grand (`repo delete`, par exemple), la réponse est `needs_confirmation`. Un client MCP affiche à l'utilisateur une demande de confirmation ; un client qui n'en a pas reçoit un argument `confirm` à renvoyer après avoir interrogé l'utilisateur. Dans le CLI, l'humain relance la commande avec `--confirm-grand <repo>`.

Chaque réponse porte un code stable (`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`), de sorte qu'un script ou un agent se fie au code plutôt qu'au message ([Sortie JSON](/fr/docs/ai-agents-json-output)).

## Le modèle de la porte de connaissance

Les mutations sensibles suivent la convention `passwd(1)` : pour modifier un secret, prouvez que vous le connaissiez déjà. **Symétrique pour les humains et les agents.** Les deux passent par la même porte. Il n'existe aucun contournement au prétexte « je suis au clavier ».

- Vous voulez faire tourner un token API stocké à `/credentials/cfDnsApiToken` ?
- La CLI demande : « quelle est la valeur actuelle ? »
- L'agent (ou l'humain) fournit le texte brut via `--current "$OLD"`. La CLI applique SHA-256 à `$OLD` et compare avec le digest de la valeur actuellement stockée. Correspondance → l'écriture passe. Discordance → refusé, audité.
- Pour effectuer une rotation sans vérifier la valeur précédente, passez `--rotate-secret` (mutuellement exclusif avec `--current`). Elle est auditée explicitement comme une rotation, et ne compte que pour un humain dans un terminal interactif : un agent, ou un script sans terminal sur stdin, a toujours besoin de `--current`.

Le modèle ferme trois surfaces d'attaque :

1. **Rotation silencieuse** : un appelant (agent ou humain) sans accès préalable à `$OLD` ne peut pas le remplacer par une valeur de son choix.
2. **Exfiltration par sondage** : la réponse du digest ne contient jamais de texte brut ; même un journal d'audit compromis affiche `expected abc12345…, got deadbeef…`, pas les valeurs sous-jacentes.
3. **Écrasement accidentel de la configuration de production** : nécessite un `--current` délibéré à chaque fois, même sur un TTY. Évite l'erreur classique « je voulais définir STRIPE_TEST mais je suis dans le shell de prod ».

### Indications structurées sur l'action suivante

Lorsque la précondition échoue, l'enveloppe JSON (`--output json`) contient un champ structuré `errors[].next` indiquant aux agents exactement ce qu'ils doivent suggérer à l'humain :

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Les agents doivent transmettre `next.options[].run` tel quel à l'humain plutôt que d'inventer leurs propres commandes.** Cela évite le cas où l'agent invente une commande qui n'existe pas, et laisse l'opérateur maître de l'action réelle. L'option de rotation est destinée à l'humain, dans un terminal ; elle est refusée à l'agent lui-même.

### Exemple concret

```bash
# Obtenir le digest court du stub de rédaction (sûr pour les agents).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Tentative d'écrasement sans preuve: refusé.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# Fournir le texte brut actuel: autorisé.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Si l'agent n'a jamais eu `$OLD_CF_TOKEN`, il ne peut pas satisfaire la précondition et la rotation est refusée. Celui qui connaît la valeur peut tout de même l'effectuer : en passant `--current` depuis son shell, ou avec `rdc config field rotate` dans un terminal interactif.

## Rédaction par défaut

Chaque commande `rdc` qui lit un état sensible: `config show`, `config field get`, `config machine list`, `config edit --dump --redacted`: renvoie des **stubs de rédaction** pour les champs secrets, pas du texte brut :

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Le suffixe hexadécimal de 8 caractères du stub correspond aux 8 premiers caractères de `sha256(canonicalize(value))`: assez pour distinguer deux valeurs différentes d'un coup d'œil, pas assez pour les inverser. Un agent peut utiliser un stub pour suivre si une valeur a changé sans jamais la voir.

`--reveal` lève la rédaction pour les humains sur un TTY interactif. Les agents sont refusés quel que soit l'état du TTY. Chaque autorisation écrit une entrée d'audit `reveal_granted` ; chaque refus écrit une entrée `refused` avec les signaux d'agent de l'acteur attachés.

## Comment une adhésion explicite locale est vérifiée sur chaque système d'exploitation

`REDIACC_ALLOW_GRAND_REPO` et `REDIACC_ALLOW_CLUSTER_OPS` reposent toutes deux sur la vérification de l'ascendance pour prouver que l'adhésion a été définie par l'humain et non injectée par l'agent. La vérification fonctionne sous Linux, macOS et Windows, mais le témoin qu'elle lit diffère selon la plateforme, tout comme la solidité de la garantie :

| Plateforme | Témoin | Force |
|---|---|---|
| Linux | `/proc/<pid>/environ` pour chaque processus de la chaîne | Snapshot au moment de l'exec, servi par le noyau. Un processus ne peut pas modifier rétroactivement ce avec quoi il a été démarré. |
| macOS | `kern.procargs2` sysctl, lu par un petit assistant intégré dans `rdc` | Même propriété de snapshot au moment de l'exec que Linux. Lisible pour vos propres processus sans avoir besoin de root. |
| Windows | Le bloc d'environnement live de chaque processus ancêtre (PEB), lu par le même assistant, avec des garde-fous contre la réutilisation de PID | Plus faible : Windows ne conserve pas de snapshot au moment de l'exec, la vérification lit donc la mémoire courante. Les ancêtres ne peuvent toujours pas être réécrits par rien qu'un agent ne lance normalement, mais le témoin n'est pas gelé au niveau du noyau comme sur Linux et macOS. |

Sous macOS et Windows, le CLI lance son binaire `renet` intégré pour effectuer la lecture ; l'assistant indique lesquelles des variables surveillées chaque ancêtre porte, et toute la logique de décision reste dans le CLI. Si l'assistant est absent, obsolète ou échoue pour une raison quelconque, le CLI ne peut pas vérifier l'adhésion et **échoue en mode fermé** : l'adhésion est rejetée et l'erreur indique que la vérification n'était pas disponible, non que quelque chose a été mal fait. Une installation qui fonctionne n'affiche jamais ce message ; réinstaller `rdc` rétablit l'assistant.

Ce qui reste vrai sur toutes les plateformes : l'adhésion doit déjà être présente dans l'environnement du processus de l'agent au démarrage de celui-ci. Elle s'exporte dans le terminal, puis l'agent est lancé. Un agent qui définit la variable en cours de session est refusé.

## Journal d'audit

Chaque mutation, chaque refus, chaque autorisation `--reveal` écrit une ligne JSONL dans `~/.config/rediacc/audit.log.jsonl` (mode `0600`, pivoté à 10 Mo). Chaque ligne est enchaînée par hachage : son champ `prevHash` est `sha256("<ligne précédente>")`. Altérer une ligne brise la chaîne sur toutes les lignes suivantes.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
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

# Vérifier que la chaîne de hachage est intacte
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

Pour une application cryptographique réelle, utilisez le [magasin de configuration chiffré](/fr/docs/config-storage) : les secrets résident côté serveur, chaque champ sensible porte un engagement HMAC par champ, et le worker de compte refuse les écritures dont la précondition `--current` ne correspond pas par hachage à ce qu'il a stocké. Le serveur ne voit jamais le texte brut (zero-knowledge), mais il applique bien la porte.

Fichiers locaux : le chemin facile est le chemin sûr. Magasin distant : le chemin de contournement est également cryptographiquement difficile.

## Ce que Rediacc n'isole pas

Les garde-fous des agents décrits sur cette page protègent l'infrastructure propre à Rediacc : le fichier de configuration, le démon Docker par dépôt, les données de dépôt chiffrées par LUKS, le bac à sable SSH limité. Ils ne protègent pas les services externes pour lesquels votre dépôt détient des identifiants.

Un fork de dépôt est un reflink BTRFS du volume du parent. Tout ce qui se trouve sur disque dans le parent est identique octet pour octet dans le fork : le code, les données et les fichiers `.env` indifféremment. Si votre dépôt contient une `STRIPE_LIVE_KEY`, un `AWS_ACCESS_KEY_ID`, un token API Railway ou tout autre identifiant à longue durée de vie pour un service tiers, le fork en hérite. Un agent opérant dans le bac à sable du fork peut lire ce fichier, exfiltrer la valeur ou l'utiliser pour appeler l'API tierce. Le service tiers n'a aucun moyen de savoir que l'appel provenait d'un fork plutôt que de la production.

Voici la ligne de responsabilité partagée :

| Frontière | Propriétaire |
|---|---|
| Données du dépôt, espace de noms de montage, périmètre Docker, garde-fous des agents, journal d'audit, injection de secrets au déploiement | Rediacc |
| Le code applicatif qui utilise ces secrets et tout identifiant gravé dans l'image lors de la compilation | Développeur du dépôt |

La principale atténuation est intégrée : les **[secrets par dépôt](/fr/docs/repositories#secrets)** sont stockés dans un plan séparé de l'image de dépôt chiffrée et ne sont pas copiés à travers la limite du fork. Les conteneurs d'un fork démarrent avec une carte de secrets vide et s'identifient comme un principal externe différent de celui du parent. Définissez-les avec `rdc repo secret set` (mode env pour l'interpolation compose, mode fichier pour les blocs `secrets:` tmpfs). La porte de mutation est symétrique. Les humains et les agents doivent également fournir `--current` (précondition de style passwd) pour écraser ou supprimer une valeur existante ; `--rotate-secret` (rotation auditée) est l'alternative pour un humain dans un terminal.

**L'isolation inter-dépôts est imposée.** Un fichier compose malveillant ou négligent dans le dépôt B ne peut pas référencer le répertoire de secrets du dépôt A. Le validateur compose de renet rejette catégoriquement tout chemin `secrets: file:`, `configs: file:` ou `env_file:` qui pointe en dehors du répertoire `${REDIACC_NETWORK_ID}` du dépôt courant, et ce rejet n'est PAS contournable par `--unsafe`. Défense en profondeur : le bac à sable Landlock autour du sous-processus bash du Rediaccfile restreint les lectures du système de fichiers au seul répertoire de secrets du réseau courant, de sorte qu'un `cat /var/run/rediacc/net-<other>/secrets/X` depuis un Rediaccfile malveillant échoue avec EACCES au niveau du noyau. Il en va de même sur l'API Docker : le socket Docker de chaque dépôt est servi par un proxy de politiques renet qui refuse par un `403` `--privileged`, `pid`, `ipc` et `uts` de l'hôte, les demandes de périphériques et les binds qui atteignent l'environnement d'exécution ou les données d'un autre dépôt. Un conteneur qui détient `${DOCKER_SOCKET}` ne peut donc pas passer par l'API pour atteindre un autre dépôt, et la vérification ne porte pas que sur un fichier compose. Seul l'opérateur peut élargir la règle des binds, pour des répertoires hôte nommés, au moyen d'une autorisation appartenant à root où aucun conteneur ne peut écrire.

Deux patterns supplémentaires comblent les cas limites :

1. **Ne gravez pas les identifiants de production dans le système de fichiers du dépôt lui-même.** Un fichier `.env` validé dans l'image, ou un identifiant persisté dans un volume pendant `up()`, est reflinkié dans le fork. La fonctionnalité de secrets par dépôt ne protège que les valeurs que vous conservez dans le plan des secrets. Elle ne peut pas protéger rétroactivement les octets qui se trouvent déjà à l'intérieur de l'image LUKS. Pour les dépôts existants avec des fichiers `.env` intégrés, migrez-les manuellement vers les secrets par dépôt.
2. **Restreignez le réseau sortant du fork avec un filtrage egress eBPF** afin que le fork ne puisse atteindre que localhost et les points de terminaison sandbox explicites. L'isolation réseau par dépôt de Rediacc en est la fondation ; les listes d'autorisation egress par fork ne sont pas implémentées aujourd'hui, mais la voie est ouverte.

Rediacc gère l'injection au déploiement, l'isolation inter-fork et l'isolation inter-dépôts. La moitié « ne gravez pas dans l'image » vous revient.

## Recettes rapides

### Laisser un agent travailler sur un dépôt grand

```bash
# En tant qu'humain, avant de démarrer l'agent :
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # ou cursor, gemini, etc.
```

L'agent peut désormais modifier `gitlab`, là où la politique autorise les modifications de dépôts grand, et aucun autre dépôt grand. Une modification destructrice, comme `repo delete gitlab`, demande toujours une confirmation.

### Faire la rotation d'un jeton cloud sans connaître l'ancienne valeur

```bash
# En tant qu'humain, dans un terminal interactif :
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

La rotation sans `--current` reste du ressort de l'humain. Un agent qui connaît la valeur actuelle utilise plutôt `rdc config field set --current`.

### Découvrir quels champs un agent est autorisé à toucher

```bash
rdc config field list --sensitive --output json
```

Renvoie chaque modèle de pointeur, son type (`secret` / `credential` / `pii` / `identifier`), et s'il est engagé dans l'enveloppe HMAC côté serveur.

## Voir aussi

- [Aperçu de l'intégration des agents IA](/fr/docs/ai-agents-overview): la vue d'ensemble
- [Serveur MCP](/fr/docs/ai-agents-mcp) : MCP local et distant, délégations et leurs adhésions explicites
- [Modèle de sécurité](/fr/docs/security-model) : l'enregistrement de politique et qui peut l'écrire
- [Configuration de Claude Code](/fr/docs/ai-agents-claude-code): modèle d'intégration
- [Enveloppe de sortie JSON](/fr/docs/ai-agents-json-output): réponses lisibles par machine
- [Magasin de configuration chiffré](/fr/docs/config-storage): application cryptographique côté serveur
- [Sécurité du compte](/fr/docs/account-security): posture de sécurité côté opérateur
