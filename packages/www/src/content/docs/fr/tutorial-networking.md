---
title: "Réseau et domaines"
description: "Rendez votre application accessible sur internet avec un domaine, TLS automatique et un reverse proxy Traefik."
category: "Tutorials"
subcategory: advanced
order: 9
language: fr
sourceHash: "9f72a61ed1ff4cb9"
---

# Réseau et domaines

Votre application tourne, mais personne ne peut encore y accéder. Ce tutoriel vous procure un vrai domaine, TLS automatique via Let's Encrypt et un proxy Traefik qui découvre automatiquement vos conteneurs. Vous avez besoin d'un domaine sur Cloudflare et d'un token API.

## Regarder le tutoriel

![Tutorial: Networking and domains](/assets/tutorials/tutorial-networking.cast)

## Quatre étapes

![Token, configurer, pousser, déployer](/img/tutorials/tutorial-networking/slide-1.svg)

1. **Obtenir** votre token API Cloudflare.
2. **Configurer** l'infrastructure sur `rdc`.
3. **Pousser** la configuration vers votre serveur.
4. **Déployer** le proxy.

## Étape 1 : Token API Cloudflare

Dans votre tableau de bord Cloudflare, allez dans **Mon profil → Tokens API** et créez un token avec la permission **Zone DNS Edit**. Copiez la valeur du token. Vous ne la verrez qu'une seule fois.

## Étape 2 : Configurer l'infrastructure

Indiquez à `rdc` votre IP publique, le domaine de base, l'adresse email pour le certificat et le token :

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

Remplacez l'IP, le domaine, l'email et le token par les vôtres.

`--cert-email` et `--cf-dns-token` sont partagés entre toutes vos machines, donc vous ne les définissez qu'une seule fois.

## Étape 3 : Pousser vers le serveur

```bash
time rdc config infra push -m my-server
```

Cela crée automatiquement les enregistrements DNS sur Cloudflare et prépare la configuration du proxy sur votre serveur.

## Étape 4 : Déployer le proxy

Le proxy lui-même ne tourne pas encore. Déployez-le depuis le modèle intégré `proxy`, dans un petit dépôt nommé `infra` :

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

C'est tout. Traefik tourne maintenant. Votre application est accessible à :

```
myapp.my-app.my-server.yourdomain.com
```

Traefik découvre vos conteneurs toutes les 5 secondes. Les certificats TLS proviennent de Let's Encrypt automatiquement. Aucune configuration manuelle du proxy n'est nécessaire.

---

Suivant : [Mode production](/en/docs/tutorial-production-mode).
