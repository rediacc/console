---
title: "GDPR-i vastavus"
description: "Kuidas Rediacc'i ise majutatud arhitektuur vastab GDPR-i nõuetele andmekaitse ja privaatsuse valdkonnas."
category: "Legal"
order: 1
language: et
---

Isikuandmete kaitse üldmäärus (GDPR) on Euroopa Liidu andmekaitseõigus, mis jõustus 2018. aasta mais. See reguleerib, kuidas organisatsioonid koguvad, töötlevad ja salvestavad EL-i üksikisikute isikuandmeid.

Täistekst: [Määrus (EL) 2016/679](https://gdpr-info.eu/)

## Artiklite kaardistamine

Alljärgnev tabel kaardistab konkreetsed GDPR-i artiklid Rediacc'i tehniliste võimalustega.

| Artikkel | Nõue | Rediacc'i võimekus |
|---------|-------------|-------------------|
| [Art. 5](https://gdpr-info.eu/art-5-gdpr/), Põhimõtted | Andmete minimeerimine, terviklus, konfidentsiaalsus | CoW-kloonid (`cp --reflink=always`) dubleerivad andmeid samal masinal ilma võrguülekandeta. LUKS2 AES-256 krüptib kõik puhkeolekus andmed. |
| [Art. 17](https://gdpr-info.eu/art-17-gdpr/), Õigus andmete kustutamisele | Kustutada isikuandmed taotluse alusel | `rdc repo destroy` kustutab LUKS-mahu krüptograafiliselt. Hargi kustutamine eemaldab kloonitud koopia täielikult. |
| [Art. 25](https://gdpr-info.eu/art-25-gdpr/), Lõimitud andmekaitse | Privaatsus vaikimisi | Krüptimine on kohustuslik, mitte vabatahtlik. Iga hoidla saab eraldatud Docker-deemoni ja võrgu. Hoidlate vahel andmeid ei jagata. Konfiguratsioonihoidla kasutab null-teadmise krüptimist: konfiguratsioonid krüptitakse kliendi poolel AES-256-GCM-iga enne üleslaadimist, seega server ei saa ühtegi avateksti lugeda. |
| [Art. 28](https://gdpr-info.eu/art-28-gdpr/), Volitatud töötleja | Kolmanda osapoole andmetöötluse kohustused | Ise majutatud: Rediacc töötab teie infrastruktuuril. Andmed ei lahku teie masinast hargi, klooni ega varukoopia operatsioonide ajal. Ükski SaaS-komponent ei töötle isikuandmeid. |
| [Art. 30](https://gdpr-info.eu/art-30-gdpr/), Töötlemistegevuste register | Pidada töötlemistegevuste arvestust | Auditlogi jälgib üle 70 sündmusetüübi: autentimine, API-žetoonid, konfiguratsioonihoidla toimingud, litsentsid ja CLI-masina toimingud (hoidla elutsükkel, varukoopia, sünkroonimine, terminal). Eksport haldusarmatuurlaua, portaali tegevuslehe või `rdc audit` CLI kaudu. |
| [Art. 32](https://gdpr-info.eu/art-32-gdpr/), Töötlemise turvalisus | Asjakohased tehnilised meetmed | LUKS2 AES-256 krüptimine puhkeolekus, võrgueraldus iptablesi ja eraldatud Docker-deemonite kaudu, loopback-IP-alamvõrgud (/26) hoidla kohta. Konfiguratsioonihoidla kasutab kolmekihilist krüptimist: ajapõhised SDK-võtmed, jagatud võtme CEK-tuletamine (pääsuvõti ja serveri saladus) ning organisatsiooni paroolilause krüptimine. |
| [Art. 33](https://gdpr-info.eu/art-33-gdpr/), Rikkumisest teatamine | 72-tunnine teavitamine koos kohtuekspertiisi rajaga | Auditlogid pakuvad kõigi toimingute kohtuekspertiisi rada. Ise majutatud arhitektuur piirab kahjustuse ulatuse üksikute hoidlatega. |

## Andmete elukoht

CoW-kloonid ei lahku kunagi lähtemasinast. Käsk `rdc repo fork` loob failisüsteemi tasandi koopia refnkkide abil. Andmeid võrgu kaudu ei edastata.

Masinate vahel toimuvatel toimingutel edastab `rdc repo backup push/pull` andmeid SSH kaudu. Varukoopia sihtkoht saab LUKS-krüptitud mahud, mida ei saa ilma operaatori volitusteta lugeda.

## Keskkonna kloonimine ja andmete maskeerimine

Tootmiskeskkondade kloonimiseks arendus- või testimisotstarbel käivitab Rediaccfile `up()` elutsükli konks pärast hargi loomist saniteerimiskriptid: eemaldab isikuandmed andmebaasidest, asendab päris e-posti aadressid testaadressidega, eemaldab API-žetoonid ja seansiandmed, anonümiseerib logifailid. Arenduskeskkond saab tootmisstruktuuri ilma tootmisidentiteetideta, rahuldades andmete minimeerimise põhimõtte ([Art. 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/)).

## Null-teadmise konfiguratsioonihoidla

Vabatahtlik konfiguratsioonihoidla võimaldab CLI-konfiguratsioonide sünkroonimist seadmete vahel. See on loodud nii, et serveril puudub igasugune teadmine konfiguratsiooni sisust:

- **Kliendipoolne krüptimine**: konfiguratsioonid krüptitakse AES-256-GCM-iga enne üleslaadimist. Krüptimisvõti (CEK) tuletatakse pääsuvõtme PRF-saladusest ja serveri hallatavast saladusest HKDF-i ja domeenieraldusega. Kumbki osapool ei suuda võtit üksi tuletada.
- **Server näeb ainult läbipaistmatuid plokke**: SSH-võtmed, volitused, IP-aadressid, võrgutopoloogia. Ükski neist ei ole serverile nähtav. Ainult metaandmed (konfiguratsiooni ID-d, versioonid, ajatemplid) salvestatakse avatekstina.
- **Liikmete juurdepääs X25519 kaudu**: kui meeskonnaliige lisatakse, krüptitakse CEK nende X25519 avaliku võtmega ja server edastab selle. Server ei näe CEK-i kunagi avatekstina.
- **Vahetu tühistamine**: liikme eemaldamine kustutab tema mähitud CEK-i ja tühistab žetoonid. Tulevased konfiguratsioonid kasutavad uusi SDK-epohhe, millele eemaldatud liikmel puudub juurdepääs.
- **Pöörlevad žetoonid**: CLI autentimine kasutab ühekordse kasutuse pöörlevaid žetoone (3-päringu armuaken), mis on esmakasutusel IP-ga seotud ja aeguvad automaatselt 24 tunni järel.

Isegi täieliku serveri kompromiteerimise korral ei saa konfiguratsiooni sisu avaldada. Serveril ei ole kunagi võtit.

Lisateabe saamiseks vaadake [Konfiguratsiooni salvestust](/en/docs/config-storage).

## Andmete vastutav töötleja ja volitatud töötleja

Kuna Rediacc on ise majutatud tarkvara, on teie organisatsioon nii andmete vastutav töötleja kui ka volitatud töötleja. Rediacc (ettevõttena) ei pääse teie andmetele ligi, ei töötle ega salvesta neid. Ise majutatud toote puhul ei ole Rediacc'iga vaja sõlmida andmetöötluslepingut, kuna isikuandmeid Rediacc'i infrastruktuuri ei voogla.

Konfiguratsioonihoidla on ainus komponent, mis puudutab Rediacc'i servereid (sünkroonimiseks), kuid selle null-teadmise disain tähendab, et server salvestab ainult krüptitud plokke, mida ta ei suuda dekrüpteerida.
