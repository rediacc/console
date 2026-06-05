---
title: Riskivabad täiendused
description: Testi andmebaasi täiendusi riskivabalt hetkekloonitamise ja igatuunniste hetktõmmiste abil.
category: Use Cases
order: 4
language: et
sourceHash: "242617b8bede9535"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Testi kõike. Riskita midagi. Värskendu enesekindlalt.**

Kiire märkus: Rediaccil ei ole hetkel tootmisettevõtete kliente. See on kasutusalade näide, mis näitab, kuidas arhitektuuri see stsenaarium praktikas käsitletakse, mitte reaalsest juurutusest pärinev juhtum.

**Kriisistsenarium:** Andmebaasi täienduse käigus esines **oodamatu viga**, mis ei võimaldanud tagasi vanade versioonile pöörduda ega jätkata uue versiooniga. Kliendid ei pääsenud süsteemidele ligi ja 5000+ töötajat ei saanud töötada. Ainus lahendus oli süsteemi täielik taastamine, mis nõudis tundide jagu inseneride tööd, kuigi ettevõte oli ühenduseta.

## Probleem

Mehmet haldab tootmisandmebaase, mida tema tiim ei saa lubada võrgust võtta. Täna on ta täiendamas **100 TB PostgreSQL andmebaasi versioonilt 13 versiooni 14**. Tema plaan:

1. **Varukoopia tegemine** → Siiski võtab varukoopia tegemine **mitme päeva aega** andmete suuruse tõttu
2. **Täienduse läbiviimine nädalavahetusel** → Osakondi teavitatakse ühenduseta jäämisest **laupäeval 01:00-05:00**

## Kriisi mõju

* **Oodamatu viga** esineb täienduse käigus
* Andmebaasi **ei saa tagasi vanade versioonile pöörduda ega jätkata uue versiooniga**
* Isegi välised tugitöötajad ei saa probleemi lahendada

**Mõjud:**
* Kliendid **ei pääse maksmis- ja tellimuste süsteemidele ligi**
* Organisatsiooni töötajad (**5000+ inimest**) ei saa töötada
* **Mainekahju** ja kasvavad kaebused algavad

**Ajutine lahendus:**
* Viimane varukoopia laaditakse **uuele serverile** → **Riistvara maksumus kahekordistub**
* Neljapäeva ja reede andmed on **ainult elussüsteemis**, seega tekib andmete kaotus
* **Kaks andmebaasi erinevate versioonidega** luuakse → Vastuolud kasvavad

## Rediacci lahendus

Siin näete, mis muutub Rediacciga:

![Risk-Free Upgrades](/img/risk-free-upgrades.svg)

### 1. **Hetkekloonimine**
* **100 TB andmebaasi klooni luuakse sekundites**
* Täienduse teste teostatakse **ilma elussüsteemi mõjutamata**

### 2. **Igatuunnised hetktõmmised**
* **Määratakse, milline etapp on millest alates ebaõnnestunud** täiendusprotsessi käigus
* Probleemkohad **tuvastatakse eelnevalt** ja parandatakse

### 3. **Sujuv täiendus**
* Kui täiendus ebaõnnestub, **ei mõjutata elussüsteemi**
* Kui täiendus õnnestub, muutub klooni uueks elussüsteemiks

## Tulemus

**Aja ja kulude kokkuhoid:**
* Varukoopia aeg vähenes **7 päevast 10 sekundisse**

**Riskivaba täiendus:**
* Vead tuvastatakse testikeskkonnas → **Elussüsteemis probleeme pole**

**Seisakuid pole:**
* Kliendid ja töötajad **ei märganud häireid**
