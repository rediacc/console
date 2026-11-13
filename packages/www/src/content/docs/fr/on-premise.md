---
title: "Installation On-Premise"
description: "Exécuter le serveur de compte et la distribution de la CLI sur votre propre infrastructure."
category: "Guides"
tags:
  - account
  - operations
subcategory: setup
order: 5
language: fr
sourceHash: "7216d032580dd4e1"
sourceCommit: "48fd8400c9f2754ab1653f0247fb0d77a1835c5b"
---

Rediacc peut fonctionner entièrement sur votre propre infrastructure. L'image Docker autonome inclut le serveur de compte, le portail web, le site marketing et le point de terminaison de distribution de la CLI. Aucune dépendance externe aux services hébergés de Rediacc n'est requise.

## Installer avec rdc

`rdc server install` installe le serveur de comptes comme dépôt sur une machine que la CLI atteint par SSH. Une seule commande couvre la vérification de la machine, la configuration de renet, le DNS, le TLS, la génération des clés, la licence, le démarrage et le compte propriétaire. Chaque valeur a un indicateur. Dans un terminal, une valeur manquante est demandée ; avec `--yes`, rien n'est demandé et une valeur manquante est refusée. Chaque étape est consignée, si bien qu'une relance saute ce qui est déjà fait.

Les étapes, dans l'ordre : `preflight` (sudo sans mot de passe, architecture, ports 80 et 443, espace disque, décalage d'horloge), `setup` (`rdc machine setup`, seulement si renet manque), `dns`, `tls`, `repo`, `keys`, `licence`, `image`, `up` et `owner`.

### D'abord les machines existantes

L'installation cible une machine qui existe déjà : un serveur en centre de données ou un appareil du réseau local. Une machine configurée se nomme en argument. Une machine pas encore enregistrée s'ajoute avec son adresse :

```bash
rdc server install --ip 203.0.113.10 --user admin --domain accounts.example.com
rdc server install server-1 --domain accounts.example.com --owner owner@example.com --yes
```

`--port` et `--name` fixent le port SSH et le nom d'enregistrement de la machine. Une VM cloud se crée d'abord avec `rdc machine provision` ; l'installation n'en crée jamais.

### DNS

L'installation affiche les enregistrements A et AAAA du domaine du serveur et de celui de son stockage de sauvegarde (`--store-domain`, par défaut `<nom>-store.<reste du domaine>`), puis attend que les deux pointent vers la machine. Aucun enregistrement n'est jamais écrit dans une zone. `--no-dns-wait` affiche les enregistrements et continue, ce qui convient à un nom de réseau local servi par un résolveur local.

### TLS

`--tls` choisit l'une des trois méthodes :

| Méthode | Prérequis | Remarques |
|---|---|---|
| `letsencrypt` | Ports 80 et 443 joignables depuis Internet | Défi HTTP-01. `--cert-email` reçoit les avis d'expiration ; par défaut, le propriétaire. |
| `cloudflare` | `--cf-token` | Défi DNS-01 via un jeton d'API Cloudflare. |
| `byo` | `--tls-cert` et `--tls-key` | Un certificat PEM existant couvrant les deux domaines. `--tls-ca` désigne l'autorité à laquelle le contrôle de santé fait confiance. |

```bash
rdc server install lab --domain lab.example.internal --tls byo \
  --tls-cert host.crt --tls-key host.key --tls-ca ca.crt \
  --licence free --no-dns-wait --yes
```

### Image

L'étape image tire par défaut `ghcr.io/rediacc/server:latest` sur la machine. `--image` choisit une autre référence. `--image-file` envoie une archive écrite par `docker save`, et `--local-image` enregistre l'`--image` depuis le Docker local avant de l'envoyer. Les deux évitent tout accès à un registre depuis la machine.

### Licence et offre gratuite

`--licence auto` (valeur par défaut) prend un certificat de délégation du compte connecté, ou démarre sur l'offre gratuite s'il n'y en a pas. `--licence free` démarre toujours sur l'offre gratuite. Un compte connecté avant l'existence de la commande d'installation doit refaire `rdc subscription login` pour porter le bon scope.

Pour une machine sans accès au serveur de comptes, `--cert <file>` prend un certificat de délégation obtenu ailleurs. Le certificat doit nommer la clé générée sur la machine ; l'ordre habituel est donc une installation sur l'offre gratuite, puis le certificat :

```bash
rdc server install server-1 --domain accounts.example.com --licence free --yes
rdc server licence accounts.example.com --cert delegation-cert.json
```

`rdc server licence` fait passer un serveur de l'offre gratuite à un certificat du compte connecté, ou de `--cert`. L'étape 3 de la section sur les licences, plus bas, décrit ce que le serveur vérifie.

### Lot de récupération

Toutes les clés sont générées sur la machine et écrites uniquement dans le `secrets.env` du dépôt. Dans un terminal, l'installation se termine par l'affichage unique d'un lot de récupération : la paire de clés déléguée, la clé du serveur de configuration de compte et les identifiants du stockage d'objets. Le lot n'est jamais journalisé ni inclus dans `--output json`. Sans terminal, il n'est pas affiché, et la ligne de fin mentionne `rdc server backup`.

```bash
rdc server backup accounts.example.com --out elite-recovery.env
```

`--out` écrit le fichier en mode 0600 ; sans lui, le lot part sur stdout. `--bws-project <id>` à l'installation copie aussi les clés dans un projet Bitwarden Secrets Manager, et `--rotate` remplace une valeur stockée différente. Sans `--bws-project`, aucune clé ne quitte la machine.

### État

```bash
rdc server status accounts.example.com
```

L'état affiche la santé, l'offre, le certificat et l'image du serveur. `--machine` et `--repo` désignent la cible quand l'appareil n'a aucun enregistrement d'installation pour le domaine.

### Mises à jour

| Composant | Commande |
|---|---|
| CLI | `rdc update` |
| renet sur la machine | `rdc machine setup <machine>` |
| Image et modèle du serveur | `rdc server upgrade <domain>` |

`rdc server upgrade` fork le dépôt comme point de retour, place la nouvelle image, réapplique le modèle quand celui qui est intégré est plus récent, puis redémarre. Il accepte `--image`, `--image-file` et `--local-image` comme l'installation, de sorte qu'une machine isolée se met à jour depuis une archive d'image enregistrée.

## Image Docker

Récupérez l'image autonome :

```bash
docker pull ghcr.io/rediacc/server:stable
```

Lancez avec les paramètres par défaut :

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

L'image expose :
- L'API de compte sur `/account/api/v1/`
- Le portail web sur `/account/`
- Le site marketing sur `/`
- Les artefacts CLI sur `/releases/`
- Les binaires Renet sur `/bin/`

## Installation de la CLI depuis votre serveur

Installez la CLI directement depuis votre serveur on-premise. Le script d'installation détecte automatiquement le canal de mise à jour et configure la CLI pour vérifier les mises à jour sur votre serveur.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

Cette commande unique :
1. Télécharge le binaire CLI depuis le point de terminaison `/releases/` de votre serveur
2. Interroge `/account/api/v1/.well-known/server-info` pour découvrir le canal de mise à jour
3. Écrit la configuration par défaut (`rediacc.json`) avec l'URL de votre serveur, le canal de mise à jour et les clés de chiffrement sous ses champs `account.*`
4. Configure `rdc update` pour vérifier les mises à jour futures sur votre serveur

Aucune variable `REDIACC_CHANNEL` n'est nécessaire. Le script d'installation lit le canal depuis la configuration de votre serveur automatiquement.

## Configuration de la CLI avec des configs nommés

Pour les utilisateurs qui se connectent à plusieurs serveurs (on-premise, production, edge), les configs nommés maintiennent chaque environnement isolé :

```bash
# Créer un config pour votre serveur on-premise
rdc config init myserver --server https://account.example.com

# Se connecter avec ce config
rdc --config myserver subscription login

# Toutes les commandes avec --config utilisent le serveur on-premise
rdc --config myserver machine status prod-1
```

Chaque config nommé stocke sa propre URL de serveur de compte (sous `account.*`) et son propre jeton d'API de compte, conservé à côté du config sous `api-token-<name>.json`. Changer de config change tout le contexte serveur.

## Environnements isolés du réseau

Pour les environnements sans accès à internet, définissez à la fois l'URL du serveur et une URL de publication personnalisée :

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

La CLI consultera `account.example.com/releases/cli/stable/manifest.json` pour les mises à jour au lieu du CDN public de publications.

Si le serveur est complètement hors ligne, installez la CLI via npm depuis l'archive groupée :

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Référence des variables d'environnement

| Variable | Utilisée par | Objet |
|---|---|---|
| `REDIACC_SERVER_URL` | Script d'installation | URL du serveur de compte. Découvre automatiquement le canal et les clés de chiffrement. |
| `REDIACC_RELEASES_URL` | Script d'installation, mise à jour CLI | Point de terminaison de publications personnalisé pour les binaires CLI. Par défaut : `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Script d'installation | Remplace le canal de mise à jour. Détecte automatiquement depuis le serveur si non défini. |
| `REDIACC_ACCOUNT_SERVER` | CLI en exécution | Remplace l'URL du serveur de compte pour toutes les commandes CLI. |
| `REDIACC_UPDATE_CHANNEL` | CLI en exécution | Remplace le canal de mise à jour pour `rdc update`. |

## Configuration du serveur

L'image Docker on-premise utilise la même variable `ENVIRONMENT` que le service hébergé. Définissez-la dans votre environnement Docker ou votre configuration d'orchestration :

- `ENVIRONMENT=production` (par défaut) : limites de ressources standard ; les CLI qui se connectent à ce serveur utilisent par défaut le canal de mise à jour **stable**. Le nom `production` est un identifiant de déploiement hérité. Les modes `production` et `edge` sont tous deux de qualité production.
- `ENVIRONMENT=edge` : limites Community 2X ; les CLI utilisent par défaut le canal de mise à jour **edge**

Consultez [Canaux de publication](/fr/docs/release-channels) pour plus de détails sur ce que chaque environnement fournit.

## Ce que le serveur communique à la CLI

Lorsque la CLI se connecte à votre serveur, elle interroge `/.well-known/server-info` pour découvrir :

- **Clé publique de chiffrement E2E** : pour le stockage de configuration zéro-connaissance
- **Version minimale de la CLI** : bloque les CLI obsolètes de se connecter
- **Canal de mise à jour** : indique à la CLI quel canal de publication utiliser pour les mises à jour
- **Environnement** : quel profil de déploiement le serveur exécute (limites standard vs. edge-avec-limites-2X)

Cette auto-configuration signifie que les utilisateurs n'ont besoin que de l'URL du serveur. Tout le reste est découvert automatiquement.

## Licences pour les déploiements isolés du réseau

Les serveurs on-premise isolés et auto-hébergés émettent des licences localement via un **certificat de délégation** signé par la clé maître en amont. Le certificat contraint le serveur on-premise à ses limites de plan et crée une chaîne inviolable. Consultez [Chaîne de licence et délégation](/fr/docs/license-chain) pour la conception cryptographique (intégrité de la chaîne, détection de fork, preuves d'audit).

Cette section couvre la configuration opérationnelle : génération des clés, demande du certificat, configuration du renouvellement automatique et le flux de renouvellement hors ligne (isolé).

### Un abonnement, une installation on-premise

Un abonnement peut avoir **au plus un certificat de délégation actif à la fois**. Chaque installation on-premise applique les limites mensuelles et par machine contre son propre registre d'émission local, de sorte que plusieurs certificats actifs multiplieraient le quota effectif sans aucune réconciliation possible.

Si vous avez besoin d'environnements séparés (production, staging, DR, multi-région), achetez un abonnement par installation. L'application de l'unicité codifie ce contrat : une tentative de création d'un second certificat actif retourne `409 DELEGATION_CERT_ALREADY_ACTIVE` avec l'identifiant du certificat existant et des instructions pour renouveler (recommandé, préserve la chaîne) ou révoquer-et-créer (réinitialise la chaîne).

### 1. Générer la paire de clés Ed25519 on-premise

Le serveur on-premise utilise une paire de clés Ed25519 séparée pour signer les licences. Le certificat de délégation de l'amont autorise cette clé publique spécifique.

```bash
# Générer une nouvelle paire de clés
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# Convertir en base64 (le format attendu par l'on-premise dans les variables d'env)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

Stockez la clé privée avec vos autres secrets (par exemple, un secret Docker ou un Kubernetes Secret). Elle ne quitte jamais le serveur on-premise.

### 2. Demander un certificat de délégation à l'amont

Vous pouvez demander le certificat depuis le portail de compte amont de trois façons :

**Option A : Libre-service client (recommandé).** Connectez-vous au portail amont en tant que propriétaire ou administrateur d'organisation et accédez à **/account/delegation-certs**. Cliquez sur **Create New**, collez la clé publique on-premise (base64 SPKI), choisissez une validité (ou acceptez le défaut par plan) et téléchargez le fichier `.json` résultant.

**Option B : Admin (inter-client).** Le support Rediacc ou l'administrateur système amont peut appeler `POST /admin/delegation-certs` avec les mêmes paramètres.

**Option C : CLI `rdc` (prévu).** Une future commande CLI encapsulera le flux du portail.

Le `.json` retourné ressemble à :

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

La validité du certificat est régie par la politique de validité (valeurs par défaut et plafonds par plan, remplacement par abonnement, plafonné à la fin de l'abonnement + 3 jours de grâce). La réponse inclut également `effectiveDays` et `reason` pour vous permettre de comprendre comment cette valeur a été déterminée. Consultez [Chaîne de licence - Politique de validité](/fr/docs/license-chain) pour les règles complètes.

### 3. Installer le certificat sur le serveur on-premise

Le serveur lit son certificat de délégation dans un seul fichier de son volume de données, `/data/delegation-cert.json` (`DELEGATION_CERT_PATH`). Rien d'autre ne porte de certificat : il n'existe pas de variable d'environnement pour cela. `rdc server install` y dépose le certificat téléchargé, et `rdc server licence` le remplace ensuite :

```bash
rdc server install <domain> --cert delegation-cert.json
rdc server licence <domain> --cert delegation-cert.json
rdc server status <domain>
```

Les deux commandes remettent le certificat au serveur en marche par sa boîte de dépôt de certificats (`data/web/cert-inbox/new.json`). Le serveur le vérifie et répond par `applied.json` ou `rejected.json`, et la commande confirme l'identifiant du nouveau certificat avec `rdc server status` (les mêmes données `cert-status` qu'à l'étape 6). `rdc server upgrade` utilise la même boîte. Une étape de la mise à niveau déplace un `DELEGATION_CERT_BASE64` resté dans `secrets.env` vers la boîte, de sorte qu'une machine installée avant l'existence de la boîte conserve son certificat.

Le serveur charge le certificat au démarrage et le confronte à la clé avec laquelle il signe les licences : l'empreinte de la clé de signature doit être égale à celle du `delegatedPublicKey` du certificat, car des licences signées avec une clé que le certificat n'autorise pas seraient invalidables sur toutes les machines. Gardez la paire de clés de signature et le `delegatedPublicKey` du certificat synchronisés.

Un certificat que le serveur refuse au démarrage (signature invalide, mauvaise clé, `UPSTREAM_PUBLIC_KEY` absente ou fichier mal formé) ne l'arrête pas. Le serveur démarre au niveau gratuit et déplace le fichier fautif vers `delegation-cert.rejected.json`, à côté de l'original. La signature des licences de dépôt répond `503 DELEGATION_CERT_REFUSED` tant qu'aucun certificat valide n'est en place, et `rdc server status` affiche `cert REFUSED (reason)`. Lancez `rdc server licence` avec un certificat valide pour réparer. Un certificat expiré se charge toujours : il se dégrade en douceur au lieu d'être refusé.

### 4. Configurer la vérification amont et le renouvellement automatique (optionnel mais recommandé)

Si votre on-premise dispose d'un accès HTTPS sortant vers l'amont, configurez le renouvellement automatique pour que le certificat se rafraîchisse avant expiration sans intervention manuelle :

```bash
# Requis pour que /onprem/cert-upload vérifie les certificats uploadés contre la clé maître amont.
# Échoue rapidement au démarrage si UPSTREAM_API_KEY est défini sans cela.
UPSTREAM_PUBLIC_KEY="<clé publique SPKI Ed25519 maître amont, base64>"

# Requis pour la boucle de renouvellement automatique. Créé via le portail :
#   Propriétaire/admin d'org → /account/delegation-certs → "Get auto-renew token"
# C'est le SEUL moyen d'obtenir un jeton api à portée delegation:renew.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# Ajustement optionnel (valeurs par défaut affichées).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

La boucle de renouvellement automatique on-premise s'exécute une fois au démarrage puis à l'intervalle configuré. Elle utilise un **seuil adaptatif** (`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`) afin qu'un certificat COMMUNITY de 15 jours se renouvelle à 5 jours restants au lieu de déclencher le renouvellement dès le premier jour. Un certificat BUSINESS de 90 jours se renouvelle à 14 jours restants (le plafond configuré par l'environnement s'applique).

En cas d'échec du renouvellement, le certificat reste en service jusqu'à expiration naturelle. L'échec est soumis à un recul d'une heure et est enregistré dans `${DELEGATION_CERT_PATH}.status.json` et exposé via `GET /onprem/cert-status`.

### 5. Renouvellement isolé (sans HTTPS sortant)

Si votre on-premise ne peut pas atteindre l'amont, utilisez le flux de transfert manuel :

1. **Téléchargez une demande de renouvellement depuis le portail admin on-premise.** En tant que root système on-premise, appelez `GET /onprem/renewal-request`. Cela retourne un manifeste JSON contenant la tête de chaîne locale, la clé publique déléguée et une signature Ed25519 inviolable de votre clé privée on-premise.
2. **Transmettez le manifeste à l'amont** via USB, email chiffré ou tout autre canal hors bande. Le manifeste est petit (quelques Ko) et ne contient aucun secret.
3. **Traitez le manifeste à l'amont.** Le propriétaire/admin d'organisation ouvre **/account/delegation-certs** → **Upload renewal request** → sélectionne le fichier manifeste. L'amont vérifie la signature du manifeste contre la `delegatedPublicKey` du certificat actif (prouve qu'il provient d'un détenteur de la clé privée on-premise), vérifie l'anti-rejeu (les manifestes de plus de 7 jours sont rejetés), puis émet un nouveau certificat.
4. **Téléchargez le nouveau certificat** depuis le portail amont en tant que fichier `.json`.
5. **Transmettez le certificat en retour** vers l'on-premise.
6. **Uploadez vers l'on-premise** via le portail admin local (`POST /onprem/cert-upload`). L'on-premise vérifie le nouveau certificat contre `UPSTREAM_PUBLIC_KEY` et valide que le `genesisSequence` du certificat lie toujours à une entrée dans le registre d'émission local (l'avancement de la chaîne pendant le transit est pris en charge - la chaîne s'étend naturellement).

Ce flux complet ne nécessite jamais d'egress réseau depuis l'on-premise.

#### Modes d'échec du manifeste

| Code | Cause | Solution |
|---|---|---|
| `NO_ACTIVE_CERT` | L'amont n'a pas de certificat actif pour cet abonnement | Émettre un nouveau certificat via le flux de création plutôt que de renouveler |
| `DELEGATED_KEY_MISMATCH` | La `delegatedPublicKey` du manifeste diffère du certificat actif | Le manifeste peut être un rejeu depuis une installation on-prem différente |
| `MANIFEST_SIGNATURE_INVALID` | La signature ne se vérifie pas contre la clé publique déléguée | Le manifeste a été altéré en transit, ou généré sur un autre on-prem |
| `MANIFEST_EXPIRED` | Le manifeste a plus de 7 jours | Générez une nouvelle demande de renouvellement depuis l'on-premise |

#### Modes d'échec de l'upload du certificat

`POST /onprem/cert-upload` répond `{uploaded: true, bootstrap, certId}` en cas de succès. Un certificat refusé renvoie `{error, code}` : `error` porte le détail et `code` correspond à l'un des motifs ci-dessous. Chaque certificat appliqué ou rejeté est journalisé et envoyé par e-mail au propriétaire de la machine.

`rdc server licence` dépose le certificat dans la boîte de dépôt de la machine (`data/web/cert-inbox`) via SSH, puis relit `applied.json` ou `rejected.json`. Il confirme ensuite le nouvel identifiant du certificat via `cert-status`. Un rejet porte les mêmes motifs, plus `not-a-regular-file` et `too-large`, émis par la boîte de dépôt elle-même.

| Code | HTTP | Cause |
|---|---|---|
| `malformed` | 400 | Le fichier envoyé n'est pas un certificat valide |
| `bad-signature` | 400 | Le certificat n'est pas signé par la `UPSTREAM_PUBLIC_KEY` configurée |
| `wrong-key` | 400 | Le certificat a été émis pour une autre clé que celle de cette installation on-premise |
| `expired` | 400 | Le certificat a déjà dépassé sa date `validUntil` |
| `not-newer` | 409 | Le certificat n'est pas plus récent que celui en vigueur |
| `other-subscription` | 409 | Le certificat appartient à un autre abonnement |
| `chain-ahead` | 409 | Le `genesisSequence` du certificat est en avance sur la tête de chaîne locale |
| `chain-fork` | 409 | Le hash de chaîne à la `genesisSequence` du certificat ne correspond pas au registre local |
| `no-upstream-key` | 500 | `UPSTREAM_PUBLIC_KEY` n'est pas configurée |
| `write-failed` | 500 | Le certificat n'a pas pu être écrit sur le disque |
| `adoption-failed` | 500 | Le serveur n'a pas pu charger le certificat écrit |

### 6. Statut et surveillance

Interrogez l'état du certificat local on-premise à tout moment :

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <session admin>"
```

Retourne le `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry` du certificat chargé, plus le bloc `autoRenew` (`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`). Intégrez cela dans votre pile de surveillance pour alerter sur un `lastSuccessAt` obsolète ou un `lastError` non nul.

Pour la sauvegarde et l'audit, l'administrateur on-premise peut également télécharger le certificat signé actuellement chargé via `GET /onprem/cert-current` (nécessite une session élevée).

### Référence des variables d'environnement du certificat de délégation

| Variable | Requise ? | Objet |
|---|---|---|
| `ON_PREMISE_MODE` | Oui | Mettre à `true` pour activer le sous-ensemble de routes on-premise |
| `ON_PREMISE_PRIVATE_KEY` | Oui | Clé privée Ed25519 PKCS8 en base64 pour la signature déléguée |
| `ON_PREMISE_PUBLIC_KEY` | Oui | Clé publique Ed25519 SPKI en base64 (doit correspondre à la `delegatedPublicKey` du certificat) |
| `DELEGATION_CERT_PATH` | Optionnel | Chemin système vers le fichier JSON du certificat signé. Par défaut `/data/delegation-cert.json` sur le volume de données. Remplacez le certificat avec `rdc server licence`, pas à la main. |
| `UPSTREAM_PUBLIC_KEY` | Requis si `UPSTREAM_API_KEY` est défini, ou pour le fonctionnement de `/onprem/cert-upload` | SPKI base64 de la clé publique maître amont. Échec rapide au démarrage si manquant. |
| `UPSTREAM_URL` | Pour le renouvellement automatique | URL de base du serveur de compte amont, ex. `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | Pour le renouvellement automatique | Un jeton api à portée `delegation:renew`. À créer via le portail - voir Étape 4. |
| `AUTO_RENEW_INTERVAL_HOURS` | Optionnel | Par défaut 24. Fréquence de vérification du besoin de renouvellement du certificat. |
| `RENEW_THRESHOLD_DAYS` | Optionnel | Par défaut 14. Agit comme un plafond sur le seuil adaptatif 1/3 de validité. |

### Résumé du modèle de menace

Le modèle de certificat de délégation protège contre :

- **Licences falsifiées** : l'on-premise ne peut signer qu'à l'intérieur des limites de son plan ; renet rejette tout ce qui dépasse les limites du certificat.
- **Partage de certificat entre déployements** : la divergence de chaîne est détectée au renouvellement (retourne `CHAIN_FORK_DETECTED`).
- **Contournement de quota via multi-installation** : appliqué à l'amont par unicité (un certificat par abonnement).
- **Rollback de chaîne** : renet stocke la séquence la plus élevée vue par abonnement et rejette tout blob avec une séquence inférieure.
- **Identifiants amont compromis** : le jeton `delegation:renew` de bootstrap ne peut être créé qu'à travers le point de terminaison dédié du portail et est restreint par l'admin. Le jeton accorde uniquement le renouvellement - il ne peut lire ni modifier aucune autre ressource.
- **Attaques par rejeu sur les manifestes** : les manifestes de plus de 7 jours sont rejetés.

Ce que le modèle ne protège **pas** contre :

- **Clé privée on-premise compromise** : une clé privée compromise permet à un attaquant de signer des licences jusqu'au `validUntil` du certificat. Mitigation : faire tourner la paire de clés (révoquer l'ancien certificat et en créer un nouveau avec une nouvelle clé) et considérer toutes les licences signées par l'ancienne clé comme suspectes.
- **Clé maître amont compromise** : c'est la racine de confiance. Les procédures de rotation sont hors du scope de ce document.
