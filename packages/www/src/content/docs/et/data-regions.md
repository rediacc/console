---
title: "Andmeregioonid"
description: "Kus teie andmeid hoitakse ja kuidas töötab regionaalne andmeresidentsus."
category: "Concepts"
tags:
  - compliance
  - account
subcategory: platform
order: 3
language: et
sourceHash: "271ee8a4a502eb02"
sourceCommit: "abc292b1b7ca5096423e098c12a9b23bdabda16b"
---

Rediacci konto loomisel valite andmeregiooni. Kõik teie andmed jäävad sellesse regiooni. See valik on püsiv ega ole pärast registreerumist muudetav. Migratsiooniviis puudub. Valige regioon selle alusel, kus teie andmed seaduslikult asuda peavad, mitte kus teie serverid täna asuvad.

## Saadaolevad regioonid

| Regioon | Asukoht | Domeen |
|---|---|---|
| **Euroopa (EU)** | Frankfurt, Saksamaa | `eu.rediacc.cloud` |
| **Ameerika Ühendriigid (US)** | Virginia, USA | `us.rediacc.cloud` |
| **Aasia ja Vaikse ookeani piirkond** | Tõkio, Jaapan | `asia.rediacc.cloud` |

Toode töötab nendel `rediacc.cloud` domeenidel. Kogu dokumentatsioon ja turundusveebisait asuvad aadressil `www.rediacc.com`, mis suunab sind regioonivalija kaudu õigesse regiooni.

Registreerimisel pakub valija sinu asukoha põhjal regiooni, mille saad kinnitada või muuta. Sisselogimisel suunab see sind pärast lühikest tagasiloendust, mille saad tühistada või muuta, sinu regiooni. Kui sinu ettevõttel on oma juurutus, viib valija valik „Enterprise'i klient?“ sind sinna ettevõtte e-posti domeeni alusel. Saadetakse ainult domeen, mitte kunagi täielik aadress.

## Mis jääb teie regiooni

Järgmist tüüpi andmeid salvestatakse ja töödeldakse ainult teie valitud regioonis:

- **Kontoandmed**: e-post, nimi, organisatsioon, meeskonnaliikmesused
- **Arveldus- ja tellimiskirjed**: plaan, aktiveerimised, litsentsi väljastamised
- **Krüpteeritud konfiguratsiooniplokid**: nullteadmiste krüpteering, kliendipoolne. Server ei suuda neid dekrüpteerida.
- **Tehingulised e-kirjad**: parooli lähtestamine, maagialingid, teavitused. Saadetakse regionaalsest e-posti lõpp-punktist.

## Mis on globaalne

Need ei ole regioonispetsiifilised:

- **CLI väljalaskeartefaktid**: avalikud binaarfailid globaalsel CDN-il
- **Turundusveebisait ja dokumentatsioon**: `www.rediacc.com`, teenindatakse globaalselt servavasukohtadest
- **Stripe'i maksete töötlemine**: haldab Stripe'i enda infrastruktuur nende andmetöötluslepingu alusel

## Regionaalne infrastruktuur

| Komponent | EU | US | Aasia |
|---|---|---|---|
| Andmebaas (D1) | Ida-Euroopa (EEUR) | Ida-Põhja-Ameerika (ENAM) | Aasia ja Vaikse ookeani piirkond (APAC) |
| Konfiguratsioonitalletus (R2) | EL-i jurisdiktsioon | USA | Aasia ja Vaikse ookeani piirkond |
| E-post (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Frankfurt (eu-central-1) |

Iga regioon töötab sõltumatu infrastruktuuriga. Regioonidevahelisi päringuid ega andmevooge regioonide vahel ei toimu.

## EL-i andmegarantiid

Kui te allute Euroopa andmeresidentsuse nõuetele, pakub EL-i regioon konkreetseid garantiisid:

- **D1 andmebaas**: töötab Ida-Euroopas (EEUR asukohaviide)
- **R2 konfiguratsioonitalletus**: kasutab EL-i jurisdiktsioonilist jõustamist (lepinguline garantii, mitte ainult asukohaviide)
- **E-post**: saadetakse Frankfurdist (eu-central-1)
- **EL-Jaapan vastastikune piisavusotsus (2019)**: võimaldab nõuetele vastavaid andmevooge Aasia regiooni infrastruktuuri jaoks

Üksikasjaliku GDPR-i kaardistuse jaoks vaadake [GDPR-i vastavust](/et/docs/legal-gdpr).

## Nullteadmiste krüpteering

R2-sse salvestatud konfiguratsiooniplokid krüpteeritakse kliendipoolselt enne üleslaadimist, kasutades X25519 võtmevahetust ja AES-256-GCM. Server hoiab ainult šifriteksti. Ei Rediacc ega ükski infrastruktuuriteenuse pakkuja ei suuda teie konfiguratsiooiandmeid lugeda.

Võtmed tuletatakse pääsvõtmest PRF-laiendusega. Server salvestab serveripoolse saladuse, mis osaleb võtme tuletamisel, kuid ei pääsvõti üksi ega serverisaladus üksi ei suuda andmeid dekrüpteerida.

Krüpteerimisarhitektuuri üksikasjade kohta vaadake [Konfiguratsioonitalletus](/et/docs/config-storage).

## Kuidas valida

- **Valige teile lähim regioon** väiksema latentsuse jaoks.
- **Valige regioon, mida teie organisatsioon nõuab** vastavuse tagamiseks. Kui teie ettevõte nõuab EL-i andmeresidentsust, valige EU.
- **Valik on püsiv.** Pärast registreerumist ei saa te oma kontot teise regiooni kolida.

## Vastavusametnike jaoks

Regionaalse arhitektuuri tehnilised omadused:

- **Eraldi andmebaasid regiooni kohta**: igal regioonil on oma Cloudflare D1 andmebaas. Regioonidevahelisi päringuid pole.
- **Eraldi talletus regiooni kohta**: igal regioonil on oma R2 ämber. EU kasutab jurisdiktsioonilist jõustamist.
- **E-posti edastus AWS SES kaudu**: tehingulised e-kirjad saadetakse AWS SES-i kaudu. EU ja US kasutavad pühendatud regionaalseid lõpp-punkte; Aasia ja Vaikse ookeani piirkond suunatakse läbi EU lõpp-punkti (eu-central-1).
- **Üks kasutaja, üks regioon**: kasutajakonto eksisteerib täpselt ühes regioonis. See ei saa ulatuda mitmesse regiooni.
- **Veebikonksu isoleerimine**: Stripe'i veebikonksu sündmused võtavad vastu kõik regionaalsed töötlejad, kuid töötlevad ainult selle regiooni, mis omab kliendikirjet.
- **Nullteadmiste konfiguratsioonikrüpteering**: server ei suuda konfiguratsiooiandmeid lugeda. Krüpteerimisvõtmed ei lahku kunagi kliendiseadmest.

Andmesuveräänsuse vastavuse laiema ülevaate jaoks vaadake [Andmesuveräänsus](/et/docs/legal-data-sovereignty).
