---
title: "Abonnement et licences"
description: "Gérer les abonnements et les licences machine pour les déploiements locaux."
category: "Guides"
order: 7
language: fr
sourceHash: "84215f54750ac4a4"
---

# Abonnement et licences

Les machines fonctionnant dans des déploiements locaux ont besoin d'une licence d'abonnement pour appliquer les limites de ressources basées sur le plan. Le CLI livre automatiquement des blobs de licence signés aux machines distantes via SSH — aucune activation manuelle ni connexion cloud requise côté serveur.

## Aperçu

1. Connectez-vous avec `rdc subscription login` (ouvre le navigateur pour l'authentification)
2. Utilisez n'importe quelle commande machine — les licences sont gérées automatiquement

Lorsque vous exécutez une commande ciblant une machine (`rdc machine info`, `rdc repo up`, etc.), le CLI vérifie automatiquement si la machine possède une licence valide. Sinon, il en récupère une depuis le serveur de comptes et la livre via SSH.

## Connexion

```bash
rdc subscription login
```

Ouvre un navigateur pour l'authentification via le flux de code d'appareil. Après approbation, le CLI stocke un jeton API localement dans `~/.config/rediacc/api-token.json`.

| Option | Requis | Par défaut | Description |
|--------|----------|---------|-------------|
| `-t, --token <token>` | Non | - | Jeton API (ignore le flux navigateur) |
| `--server <url>` | Non | `https://account.rediacc.com` | URL du serveur de comptes |

## Vérifier le statut

```bash
# Statut au niveau du compte (plan, machines)
rdc subscription status

# Inclure les détails de licence d'une machine spécifique
rdc subscription status -m hostinger
```

Affiche les détails de l'abonnement depuis le serveur de comptes. Avec `-m`, se connecte également à la machine via SSH et affiche ses informations de licence actuelles.

## Actualisation forcée d'une licence

```bash
rdc subscription refresh -m <machine>
```

Réémet et livre de force une nouvelle licence à la machine spécifiée. Ceci n'est normalement pas nécessaire — les licences sont actualisées automatiquement toutes les 50 minutes lors de l'utilisation normale du CLI.

## Fonctionnement

1. **La connexion** stocke un jeton API sur votre poste de travail
2. **Toute commande machine** déclenche une vérification automatique de licence via SSH
3. Si la licence distante est manquante ou a plus de 50 minutes, le CLI :
   - Lit l'identifiant matériel de la machine distante via SSH
   - Appelle l'API de comptes pour émettre une nouvelle licence
   - Livre à la fois la licence machine et le blob d'abonnement à la machine distante via SSH
4. Un cache en mémoire de 50 minutes empêche les allers-retours SSH redondants au sein de la même session

Chaque activation de machine consomme un emplacement dans votre abonnement. Pour libérer un emplacement, désactivez une machine depuis le portail de comptes.

## Période de grâce et dégradation

Si une licence expire et ne peut pas être actualisée dans la période de grâce de 3 jours, les limites de ressources de la machine se dégradent vers les valeurs par défaut du plan Community. Une fois la licence actualisée (en rétablissant la connectivité et en exécutant n'importe quelle commande `rdc`), les limites du plan d'origine sont restaurées immédiatement.

## Limites de plan

### Limites de licences flottantes

| Plan | Licences flottantes |
|------|-------------|
| Community | 2 |
| Professional | 5 |
| Business | 20 |
| Enterprise | 50 |

### Limites de ressources

| Ressource | Community | Professional | Business | Enterprise |
|----------|-----------|--------------|----------|------------|
| Bridges | 0 | 1 | 2 | 10 |
| Max reserved jobs | 1 | 2 | 3 | 5 |
| Job timeout (hours) | 2 | 24 | 72 | 96 |
| Repository size (GB) | 10 | 100 | 500 | 2,048 |
| Jobs per month | 500 | 5,000 | 20,000 | 100,000 |
| Pending per user | 5 | 10 | 20 | 50 |
| Tasks per machine | 1 | 2 | 3 | 5 |

### Disponibilité des fonctionnalités

| Fonctionnalité | Community | Professional | Business | Enterprise |
|---------|-----------|--------------|----------|------------|
| Permission groups | - | Yes | Yes | Yes |
| Queue priority | - | - | Yes | Yes |
| Advanced analytics | - | - | Yes | Yes |
| Priority support | - | Yes | Yes | Yes |
| Audit log | - | Yes | Yes | Yes |
| Advanced queue | - | - | Yes | Yes |
| Custom branding | - | Yes | Yes | Yes |
| Dedicated account | - | - | - | Yes |
