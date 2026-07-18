---
title: "Väljalaskekanalid"
description: "Kuidas Edge ja Stable erinevad ning millist kanalit kasutada."
category: "Concepts"
order: 2
language: et
sourceHash: "6669b5b089f94a39"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

Rediacc saadab uuendusi kahe kanali kaudu: **Stable** ja **Edge**. Need töötavad eraldi infrastruktuuril ja toovad kaasa erinevad kompromissid.

## Stable kanal

Stable on vaikimisi. Väljalase jõuab sellele alles pärast seda, kui on 7 päeva Edge'il istunud ilma teatatud probleemideta.

- Soovitatav, kui eelistad konservatiivset uuendussagedust ja soovid juurdepääsu tasuliste plaanidele
- Juurutatakse pärast 7 päeva testimist Edge'il
- Kriitilised paigad saab otse lükata, kui vajalik
- Domeenid: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Edge kanal

Edge saab iga muudatuse kohe pärast seda, kui see ühineb põhaharuga. See on tarkvara viimane versioon, pidevalt juurutatav.

- Pidevalt juurutatav tootmine, väljastatuna iga ühendamisega põhiharuga
- 2X Community plaani piirangud (vt allolevat tabelit)
- Edge'il pole tasulisi plaane; kontod töötavad Community plaanil.
- Eraldi kontod Stable'ist. Andmed ei liiku kanalite vahel.
- Domeenid: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Võrdlus

| | Stable | Edge |
|---|---|---|
| **Juurutamise sagedus** | Pärast 7-päevast leotust | Iga ühendamine põhiharuga |
| **Stabiilsus** | Testitud 7 päeva | Tootmine, pidevalt juurutatav |
| **Community plaani piirangud** | 10 GB hoidlad, 100 seadistust/kuu, 1 masin | 20 GB hoidlad, 200 seadistust/kuu, 2 masinat |
| **Tasulised plaanid** | Saadaval (Professional, Business, Enterprise) | Pole saadaval |
| **Kontod** | Sõltumatud | Sõltumatud (eraldi Stable'ist) |
| **Parim kasutus** | Tootmine, tasulised töökoormustered | Tootmine, kõrvaalprojektid, varajane juurdepääs |

## Edge 2X piirangud

Kui käitad Edge't Community plaanil, kahekordistuvad su ressursipiirangud:

| Ressurss | Stable Community | Edge Community |
|---|---|---|
| Hoidla suurus | 10 GB | 20 GB |
| Litsentsi väljastamisi kuus | 100 | 200 |
| Masina aktiveerimisi | 1 | 2 |

Kui vajad kõrgemaid piiranguid või tasulise plaani funktsioone, loo konto Stable kanalil ja uuenda seal.

## Eraldi kontod

Edge ja Stable töötavad eraldi infrastruktuuril eraldi andmebaasidega. Edge'il loodud konto ei eksisteeri Stable'is ja vastupidi. Kanalite vahel pole migreerimisteed. Kui alustad Edge'ist ja soovid hiljem tasulist plaani, pead looma uue konto Stable'is.

## Kuidas edendamine toimib

1. Iga ühinemine põhiharuga juurutatakse Edge'ile kohe.
2. Pärast 7 päeva ilma probleemideta edendatakse Edge automaatselt Stable'iks.
3. Kriitilised paigad saab lükata mõlemale kanalile samaaegselt.

See tähendab, et Stable on alati kõige rohkem 7 päeva Edge'ist maas. Leotusperiood tabab regressioone enne, kui need levivad Edge'ist Stable'ile.

## Millist kanalit valida?

**Vali Stable, kui:**
- Eelistad konservatiivset uuendussagedust 7-päevase leotusaknaga
- Vajad tasulisi plaane (Professional, Business, Enterprise)
- Eelistad maksimaalset töökindlust uusimate funktsioonide ees

**Vali Edge, kui:**
- Soovid proovida uusi funktsioone varakult
- Hindad platvormi
- Soovid щедraid tasuta piiranguid kõrvaalprojektide jaoks
- Oled mugav uuema, vähem testitud koodiga

## Paigaldamine

Mõlemalt kanalilt paigaldamiseks mõeldud käskude kohta, sealhulgas paketihaldurite konfigureerimine ja Dockeri sildid, vt [Paigaldamine](/et/docs/installation).

## CLI kanali haldamine

CLI kasutab automaatselt paigaldamise või sisselogimise ajal seadistatud kanalit. Kanalite vahel lülitumiseks:

```bash
rdc update --channel edge      # Lülitu Edge'ile
rdc update --channel stable    # Lülitu Stable'ile
```

Kui käivitad `rdc subscription login` ja valid Edge'i piirkonna, seadistab CLI automaatselt Edge'i uuenduskanali. Käsitsi `--channel` lippu pole vaja.
