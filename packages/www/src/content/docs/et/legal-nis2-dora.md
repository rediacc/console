---
title: "NIS2 ja DORA"
description: "Kuidas Rediacc käsitleb EL-i NIS2 küberturvalisuse direktiivi ja DORA digitaalse tegevuskerksuse nõudeid."
category: "Legal"
order: 8
language: et
---

NIS2 ja DORA on EL-i määrused, mis seavad kriitilistele infrastruktuuridele ja finantssektori organisatsioonidele küberturvalisuse ja tegevuskerksuse nõuded. Mõlemad jõustusid 2025. aastal ja kehtivad laialdaselt EL-i tööstusharudes.

## NIS2 direktiiv

Võrgu- ja infoturbe direktiiv 2 (NIS2) kehtestab küberturvalisuse nõuded "olulistele" ja "tähtsatele" üksustele sektorites, mis hõlmavad energeetikat, transporti, tervishoidu, digitaalset infrastruktuuri ja avalikku haldust.

Täistekst: [Direktiiv (EL) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### NIS2 nõuete kaardistamine

| NIS2 nõue | Rediacc'i võimekus |
|-----------------|-------------------|
| Riskijuhtimise meetmed (Art. 21) | LUKS2 krüptimine puhkeolekus, võrgueraldus hoidla kaupa, ainult SSH-põhine juurdepääs, auditeerimine (üle 70 sündmusetüübi, sealhulgas masina toimingud) |
| Intsidentide käsitlemine (Art. 21(2)(b)) | Üle 70 sündmusetüübi (autentimine, žetoonid, konfiguratsioon, litsentsid, masina toimingud) pakuvad kohtuekspertiisi rada. Hoidlapõhine eraldus piirab kahjustuse ulatust. |
| Tegevuse järjepidevus (Art. 21(2)(c)) | `rdc repo backup push/pull` mitme sihtkoha krüptitud varukoopiaga. CoW-hetktõmmised koheseks tagasipöördumiseks. |
| Tarneahela turvalisus (Art. 21(2)(d)) | Ise majutamine kõrvaldab SaaS-tarneahela riski. Ükski kolmanda osapoole pilveteenuse pakkuja ei töötle teie andmeid. |
| Võrguturbe (Art. 21(2)(e)) | Hoidlapõhised Docker-deemonid, iptablesi reeglid, loopback-IP-eraldus (/26 alamvõrgud). |
| Krüptimine (Art. 21(2)(h)) | LUKS2 AES-256 kohustuslik krüptimine. Null-teadmise konfiguratsioonihoidla AES-256-GCM-iga. |
| Juurdepääsukontroll (Art. 21(2)(i)) | SSH-võtme autentimine, ulatusega piiratud API-žetoonid IP-sidumisega, kahefaktoriline autentimine (TOTP). |
| Intsidentidest teatamine, 24-tunnine varajane hoiatus (Art. 23) | Auditlogimine võimaldab kiiret intsidendi tuvastamist ja ulatuse määramist. |

### Tarneahela risk

Tarneahela turvalisus on NIS2 keskne mure (Art. 21(2)(d)). Organisatsioonid peavad hindama ja haldama IKT-teenuste pakkujate ja tarnijate riske.

Ise majutatud Rediacc eemaldab suurima tarneahela ründepinna: ükski kolmanda osapoole SaaS-teenus ei käitle teie andmeid, ükski pilveteenuse pakkuja ei oma loogilist juurdepääsu teie infrastruktuurile ning ükski jagatud üürnikukeskkond ei loo kokkupuudet teiste klientide turvaolukorraga. SaaS-müüjate lekked on põhjustanud laiahaardelist kahju tuhandetele organisatsioonidele. [Blackbaudi 2020. aasta lunavararünnak avaldas andmeid üle 13 000 klientorganisatsiooni kohta, makstes 49,5 miljonit dollarit kokkulepetes.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (digitaalse tegevuskerksuse seadus)

DORA kehtestab EL-i finantssektori IKT-riskijuhtimise, intsidentidest teatamise, kerksuse testimise ja kolmandate osapoolte riskijuhtimise nõuded. See kehtib pankadele, kindlustusseltsidele, investeerimisettevõtetele, krüptovarade teenusepakkujatele ja nende kriitilistele IKT-kolmandate osapoolte pakkujatele.

Täistekst: [Määrus (EL) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### DORA nõuete kaardistamine

| DORA nõue | Rediacc'i võimekus |
|-----------------|-------------------|
| IKT-riskijuhtimise raamistik (Art. 6) | Krüptimine, eraldus, auditlogimine ja varukoopia moodustavad tehniliste kontrollide kihi. |
| Kaitse ja ennetamine (Art. 9) | LUKS2 AES-256 krüptimine puhkeolekus. Võrgueraldus takistab lateraalliikumist. Ainult SSH-põhine juurdepääs. |
| Tuvastamine (Art. 10) | Üle 70 sündmusetüübi, sealhulgas masina toimingud (hoidla elutsükkel, varukoopia, sünkroonimine, terminal). Haldusarmatuurlaud ja portaal kasutaja- ja meeskonnapõhise filtreerimisega. Masina toimingud ka süsteemilogides sügavama kaitse tagamiseks. |
| Reageerimine ja taastumine (Art. 11) | CoW-hetktõmmised koheseks tagasipöördumiseks. `rdc repo backup push/pull` mitme sihtkoha taastumiseks. Hargipõhine katastroofist taastumise testimine. |
| IKT kolmanda osapoole risk (Art. 28-30) | Ise majutamine kõrvaldab "kriitilise IKT kolmanda osapoole pakkuja" klassifikatsiooni täielikult. |
| Digitaalse tegevuskerksuse testimine (Art. 24-27) | CoW-kloonimine võimaldab ohupõhist läbitungimistestimist tootmislaadsetes keskkondades ilma andmete avaldumiseta. Klooni, testi, hävita. |

### Kolmanda osapoole IKT-pakkuja risk

DORA kõige koormavamad nõuded puudutavad kriitiliste IKT kolmandate osapoolte pakkujate haldamist (Art. 28-30). Finantsasutused peavad pidama IKT-pakkujate registreid, teostama riskihindamisi, läbirääkima konkreetsete lepingutingimuste üle ja planeerima väljumisstrateegiaid.

Ise majutatud Rediacc väldib seda täielikult. Registreerimiseks, hindamiseks ega jälgimiseks pole ühtegi IKT kolmanda osapoole pakkujat. Finantsasutus kontrollib oma infrastruktuuri otse.

### Kerksuse testimine

DORA nõuab digitaalse tegevuskerksuse testimist, sealhulgas ohupõhist läbitungimistestimist (TLPT) suurte asutuste jaoks (Art. 26). CoW-kloonimine lahendab selle otseselt:

1. Tootmiskeskkonna hargimine (kohene, samal masinal, andmeedastust ei toimu)
2. Läbitungimistestide läbiviimine hargi vastu
3. Hargi hävitamine pärast lõpetamist

Tootmist ei puututa kunagi, kuid testkeskkond on täpne koopia. Andmed ei lahku masinast.
