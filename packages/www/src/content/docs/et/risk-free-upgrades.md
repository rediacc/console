---
title: Riskivabad uuendused
description: Testige andmebaaside uuendusi riskivabalt, kasutades kohest kloonimist ja tunnipõhiseid hetktõmmiseid.
category: Use Cases
order: 4
language: et
---

> **Testige kõike. Riskige mitte millegagi. Uuendage enesekindlalt.**

**Märkus:** See on **kasutuskaasuse näide**, mis demonstreerib, kuidas Rediacc saab selle probleemi lahendada. Idufirmana esindavad need stsenaariumid potentsiaalseid rakendusi, mitte lõpetatud juhtumiuuringuid.

**Kriisistsenaariumil:** Andmebaasi uuendamise ajal ilmnes **ootamatu viga**, mis takistas naasmist vana versiooni juurde või edenemist uuele. Kliendid ei pääsenud süsteemidele ligi ja üle 5000 töötaja ei suutnud töötada.

## Probleem

Mehmet on kogenud süsteemiadministraator, kes haldab suuremahulisi andmebaase. Ta otsustab **uuendada 100 TB suurust PostgreSQL andmebaasi versioonilt 13 versioonile 14**. Tema plaan:

1. **Tehke varukoopia** → Kuid varundamine võtab **mitu päeva** andmete suuruse tõttu
2. **Tehke uuendus nädalavahetusel** → Osakondadele teatatakse seiskumisest **laupäeval 01:00-05:00**

## Kriisi mõju

* Uuendamise ajal ilmneb **ootamatu viga**
* Andmebaas **ei suuda naasta vana versioonini ega edeneda uuele versioonile**
* Isegi välised tugimeeskonnad ei suuda probleemi lahendada

**Mõjud:**
* Kliendid **ei pääse makse- ja tellimussüsteemidele ligi**
* Organisatsiooni töötajad (**üle 5000 inimese**) ei suuda töötada
* **Mainekahju** ja kasvavad kaebused algavad

**Ajutine lahendus:**
* Viimane varukoopia laaditakse **uude serverisse** → **Riistvara kulu kahekordistub**
* Neljapäeva ja reede andmed on **ainult elukeskkonnas**, seega tekib andmekadu
* **Kaks erineva versiooniga andmebaasi** luuakse → Vastuolud suurenevad

## Rediacci lahendus

Mehmet lahendab probleemi põhjalikult Rediacciga:

![Riskivabad uuendused](/img/risk-free-upgrades.svg)

### 1. **Kohene kloonimine**
* **100 TB andmebaasi klooni luuakse sekundite jooksul**
* Uuendamise teste tehakse **ilma elussüsteemi mõjutamata**

### 2. **Tunnipõhised hetktõmmised**
* Määratakse kindlaks, **millisest sammust ja millest alates on uuendamisprotsess ebaõnnestunud**
* Probleemsed toimingud **tuvastatakse ette** ja parandatakse

### 3. **Sujuv uuendamine**
* Kui uuendamine ebaõnnestub, **ei mõjutata eluskeskkonda**
* Kui uuendamine õnnestub, saab uus eluskeskkond viimaseks klooniks

## Tulemus

**Aja ja kulude kokkuhoid:**
* Varundamisaeg vähenes **7 päevalt 10 sekundile**

**Riskivaba uuendamine:**
* Vead tuvastati ette testkeskkonnas → **Elussüsteemis probleeme polnud**

**Null seisakuaega:**
* Kliendid ja töötajad **ei tundnud mingit katkestust**
