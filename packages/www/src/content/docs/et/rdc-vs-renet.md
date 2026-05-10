---
title: "rdc vs renet: võrdlus"
description: "Millal kasutada rdc-d ja millal renet'i: kahe tööriista erinevused."
category: "Concepts"
order: 1
language: et
---

# rdc vs renet

Rediacc'il on kaks binaari. Siin on selgitus, millal kumbagi kasutada.

| | rdc | renet |
|---|-----|-------|
| **Töötab** | Sinu tööjaamast | Kaugserveris |
| **Ühendub** | SSH kaudu | Käivitub lokaalselt root-õigustega |
| **Kasutab** | Kõik | Ainult edasijõudnute silumisel |
| **Paigaldamine** | Sa paigaldad selle | `rdc` provisioonib selle automaatselt |

> Igapäevaseks tööks kasuta `rdc`-d. `renet`'i otse on harva vaja.

## Kuidas need koos töötavad

`rdc` ühendub sinu serveriga üle SSH ja käivitab sinu eest `renet`-käsud. Sa trükid ühe käsu oma tööjaamasse ja `rdc` hoolitseb ülejäänu eest:

1. Loeb sinu kohaliku konfiguratsiooni (`~/.config/rediacc/rediacc.json`)
2. Ühendub serveriga üle SSH
3. Uuendab `renet`-binaari vajaduse korral
4. Käivitab vastava `renet`-toimingu serveris
5. Tagastab tulemuse sinu terminali

## Kasuta `rdc`-d tavaliseks tööks

Kõik levinud ülesanded käivad `rdc` kaudu sinu tööjaamast:

```bash
# Seadista uus server
rdc config machine setup --name server-1

# Loo ja käivita hoidla
rdc repo create --name my-app -m server-1 --size 10G
rdc repo up --name my-app -m server-1

# Peata hoidla
rdc repo down --name my-app -m server-1

# Kontrolli masina tervist
rdc machine health --name server-1
```

Täieliku läbikäigu leiad [Kiirjuhendist](/et/docs/quick-start).

## Kasuta `renet`'i serveripoolseks silumiseks

`renet`'i on otseselt vaja ainult siis, kui SSH-d serverisse:

- Hädaolukorra silumisel, kui `rdc` ei saa ühendust
- Süsteemi sisekamise kontrollimisel, mis pole `rdc` kaudu saadaval
- Madala taseme taasteoperatsioonidel

Kõik `renet`-käsud vajavad root-õigusi (`sudo`). Täieliku `renet`-käskude loendi leiad [Serveri viitest](/et/docs/server-reference).

## Eksperimentaalne: `rdc ops` (kohalikud VM-id)

`rdc ops` mähib `renet ops` kohalike VM-klastrite haldamiseks sinu tööjaamast:

```bash
rdc ops setup              # Paigalda eeltingimused (KVM või QEMU)
rdc ops up --basic         # Käivita minimaalne klaster
rdc ops status             # Kontrolli VM-i olekut
rdc ops ssh --vm-id 1  # SSH silla VM-i
rdc ops ssh --vm-id 1 -c hostname  # Käivita käsk silla VM-is
rdc ops down               # Hävita klaster
```

> Nõuab lokaalset adapterit. Pilveadapteriga pole saadaval.

Need käsud käivitavad `renet`'i lokaalselt (mitte üle SSH). Täieliku dokumentatsiooni leiad [Eksperimentaalsete VM-ide](/et/docs/experimental-vms) lehelt.

## Rediaccfile märkus

Võid näha `renet compose -- ...` sees `Rediaccfile`'is. See on normaalne -- Rediaccfile funktsioonid käivituvad serveris, kus `renet` on saadaval.

Oma tööjaamast käivita ja peata töökoormuseid käskudega `rdc repo up` ja `rdc repo down`.
