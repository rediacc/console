---
title: "rdc vs renet"
description: "Quand utiliser rdc et quand utiliser renet."
category: "Guides"
order: 1
language: fr
sourceHash: "cb2c174b8cf1a078"
---

# rdc vs renet

Rediacc utilise deux binaires:

- `rdc` est la CLI orientee utilisateur que vous lancez sur votre poste.
- `renet` est le binaire distant, bas niveau, qui tourne sur les serveurs.

Pour presque toutes les operations quotidiennes, utilisez `rdc`.

## Modele Mental

Considerez `rdc` comme le plan de controle et `renet` comme le plan de donnees.

`rdc`:
- Lit votre contexte local et vos associations de machines
- Se connecte aux serveurs via SSH
- Provisionne/met a jour `renet` si necessaire
- Execute pour vous la bonne operation distante

`renet`:
- S'execute avec des privileges eleves sur le serveur
- Gere datastore, volumes LUKS, montages et daemons Docker isoles
- Effectue des operations bas niveau sur le systeme et les repositories

## Que Utiliser en Pratique

### Utiliser `rdc` (par defaut)

Utilisez `rdc` pour les workflows normaux:

```bash
rdc context setup-machine server-1
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount
rdc repo down my-app -m server-1
rdc machine status server-1
```

### Utiliser `renet` (avance / cote distant)

Utilisez directement `renet` uniquement lorsque vous avez volontairement besoin d'un controle bas niveau, par exemple:

- Debogage d'urgence directement sur le serveur
- Maintenance et reprise au niveau hote
- Verification d'internals non exposes par les commandes `rdc`

La plupart des utilisateurs n'ont pas besoin d'appeler `renet` directement en usage courant.

### Experimental: `rdc ops` (VMs locales)

`rdc ops` encapsule `renet ops` pour gerer des clusters de VMs locales sur votre poste:

```bash
rdc ops setup    # Installer les prerequis (KVM ou QEMU)
rdc ops up --basic  # Provisionner un cluster minimal
rdc ops status   # Verifier le statut des VMs
rdc ops ssh 1    # SSH dans la VM bridge
rdc ops down     # Detruire le cluster
```

Ces commandes executent `renet` localement (pas via SSH). Voir [VMs Experimentales](/fr/docs/experimental-vms) pour la documentation complete.

## Note Rediaccfile

Vous pouvez voir `renet compose -- ...` dans un `Rediaccfile`. C'est normal: les fonctions Rediaccfile s'executent cote distant, la ou `renet` est disponible.

Depuis votre poste, vous continuez generalement a demarrer/arreter les workloads avec `rdc repo up` et `rdc repo down`.
