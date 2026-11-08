---
title: "Väljalaskekanalid"
description: "Kuidas Edge ja Stable erinevad ning millist kanalit kasutada."
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: et
sourceHash: "29d62173c5cf044a"
sourceCommit: "abc292b1b7ca5096423e098c12a9b23bdabda16b"
---

Rediacc toimetab CLI uuendused kahe kanali kaudu: **Stable** ja **Edge**. Mõlemad ühenduvad sama tootega, seega on konto, plaan ja piirangud mõlemal kanalil samad. Kanalid erinevad ainult selle poolest, kui kiiresti väljalase sinuni jõuab.

## Stable kanal

Stable on vaikimisi. Väljalase jõuab sellele alles pärast seda, kui on 7 päeva Edge'il istunud ilma teatatud probleemideta.

- Soovitatav, kui eelistad konservatiivset uuendussagedust
- Juurutatakse pärast 7 päeva testimist Edge'il
- Kriitilised paigad saab otse lükata, kui vajalik

## Edge kanal

Edge saab iga muudatuse kohe pärast seda, kui see ühineb põhaharuga. See on tarkvara viimane versioon, pidevalt juurutatav.

- Avaldatakse iga põhiharuga ühendamise järel
- Samad kontod, plaanid ja piirangud mis Stable'il
- Sobib uute funktsioonide varakult proovimiseks

## Üks toode, kaks kanalit

Sinu konto asub sinu andmeregioonis aadressil `eu.rediacc.cloud`, `us.rediacc.cloud` või `asia.rediacc.cloud`, olenemata kanalist. Kanali vahetamine ei mõjuta kontot, andmeid ega tellimust. Regioonide kohta vaata lehte [Andmeregioonid](/et/docs/data-regions).

## Võrdlus

| | Stable | Edge |
|---|---|---|
| **Juurutamise sagedus** | Pärast 7-päevast leotust | Iga ühendamine põhiharuga |
| **Stabiilsus** | Testitud 7 päeva | Tootmine, pidevalt juurutatav |
| **Plaanid ja piirangud** | Samad | Samad |
| **Konto ja andmed** | Ühised | Ühised |
| **Sobib** | Tootmiseks, tasulistele töökoormustele | Varajaseks ligipääsuks, hindamiseks |

## Kuidas edendamine toimib

1. Iga ühinemine põhiharuga juurutatakse Edge'ile kohe.
2. Pärast 7 päeva ilma probleemideta edendatakse Edge automaatselt Stable'iks.
3. Kriitilised paigad saab lükata mõlemale kanalile samaaegselt.

See tähendab, et Stable on alati kõige rohkem 7 päeva Edge'ist maas. Leotusperiood tabab regressioone enne, kui need levivad Edge'ist Stable'ile.

## Millist kanalit valida?

**Vali Stable, kui:**
- Eelistad konservatiivset uuendussagedust 7-päevase leotusaknaga
- Eelistad maksimaalset töökindlust uusimate funktsioonide ees

**Vali Edge, kui:**
- Soovid proovida uusi funktsioone varakult
- Hindad platvormi
- Oled mugav uuema, vähem testitud koodiga

## Paigaldamine

Mõlemalt kanalilt paigaldamiseks mõeldud käskude kohta, sealhulgas paketihaldurite konfigureerimine ja Dockeri sildid, vt [Paigaldamine](/et/docs/installation).

## CLI kanali haldamine

CLI kasutab paigaldamisel seadistatud kanalit. Kanali vahetamiseks:

```bash
rdc update --channel edge      # Lülitu Edge'ile
rdc update --channel stable    # Lülitu Stable'ile
```
