---
title: "NIS2 ja DORA"
description: "Kuidas Rediacc käsitleb EL-i NIS2 küberturvalisuse direktiivi ja DORA digitaalse tegevuskerksuse nõudeid."
category: "Legal"
tags:
  - compliance
subcategory: regulations
order: 8
language: et
sourceHash: "e1cdb4848a2124ae"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

NIS2 ja DORA on EL-i määrused, mis seavad kriitilistele infrastruktuuridele ja finantssektori organisatsioonidele küberturvalisuse ja tegevuskerksuse nõuded. Mõlemad jõustusid 2025. aastal ja kehtivad laialdaselt EL-i tööstusharudes.

## NIS2 direktiiv

Võrgu- ja infoturbe direktiiv 2 (NIS2) kehtestab küberturvalisuse nõuded "olulistele" ja "tähtsatele" üksustele sektorites, mis hõlmavad energeetikat, transporti, tervishoidu, digitaalset infrastruktuuri ja avalikku haldust.

Täistekst: [Direktiiv (EL) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### NIS2 nõuete kaardistamine

| NIS2 nõue | Rediacc'i võimekus |
|-----------------|-------------------|
| Riskijuhtimise meetmed (Art. 21) | LUKS2 krüptimine puhkeolekus, võrgueraldus hoidla kaupa, ainult SSH-põhine juurdepääs, auditeerimine (üle 70 sündmusetüübi, sealhulgas masina toimingud) |
| Intsidentide käsitlemine (Art. 21(2)(b)) | Hoidlapõhised võrgu voo kirjed kliendi valitud detailsusega (sihtkoht, port ja protokoll; kõrgematel tasemetel protsess, DNS-nimi ja tundlike failide avamised) saadetakse allkirjastatud, räsiaheldatud partiidena ämbrisse, kuhu kliendi administraatorid kirjutada ei saa, ainult tasulistel plaanidel. Üks uurimise ajajoon hoidla kohta kontrollib ahelat brauseris ning Declare incident käivitab tähtaja kellad. Voo kirjed näitavad mahtu ja sihtkohta, mitte sisu. Free- ja Community-plaanid ei salvesta midagi. Hoidlapõhine eraldus piirab kahjustuse ulatust. Üle 70 auditisündmuse tüübi (autentimine, žetoonid, konfiguratsioon, litsentsid, masina toimingud) salvestavad, kes mida tegi. |
| Tegevuse järjepidevus (Art. 21(2)(c)) | `rdc repo push/pull` mitme sihtkoha krüptitud varukoopiaga. CoW-hetktõmmised koheseks tagasipöördumiseks. |
| Tarneahela turvalisus (Art. 21(2)(d)) | Ise majutamine kõrvaldab SaaS-tarneahela riski. Ükski kolmanda osapoole pilveteenuse pakkuja ei töötle teie andmeid. |
| Võrguturbe (Art. 21(2)(e)) | Hoidlapõhised Docker-deemonid, iptablesi reeglid, loopback-IP-eraldus (/26 alamvõrgud). |
| Krüptimine (Art. 21(2)(h)) | LUKS2 AES-256 kohustuslik krüptimine. Null-teadmise konfiguratsioonihoidla AES-256-GCM-iga. |
| Juurdepääsukontroll (Art. 21(2)(i)) | SSH-võtme autentimine, ulatusega piiratud API-žetoonid IP-sidumisega, kahefaktoriline autentimine (TOTP). |
| Intsidentidest teatamine, 24-tunnine varajane hoiatus (Art. 23) | Declare incident salvestab teadlikuks saamise hetke ja käivitab sellest kolm kella: 24 tundi varajase hoiatuse jaoks, 72 tundi intsidendi teavituse jaoks ja üks kalendrikuu pärast teavitust lõpparuande jaoks (Art. 23(4)). Iga etapp valmistatakse ette allkirjastatud aruandena PDF-, JSON- ja STIX 2.1 -vormingus, koos väljakaardiga, mis seob iga aruandevälja direktiiviga. Otsus, kas intsident on oluline, ja mida CSIRT-ile või pädevale asutusele saadetakse, jääb kliendi hinnangule ja esitamisele. |

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
| Tuvastamine (Art. 10) | Anomaaliadetektorid töötavad masinas (ka võrguühenduseta) ja serveris saadetud voo kirjete peal ning tõstatavad ebatavalise liikluse korral turvateate. Detektorid märgivad kõrvalekaldeid hoidla õpitud baasjoonest; need ei tõesta rikkumist ja katavad ainult hoidlaid, kus jäädvustamine on tasulisel plaanil sisse lülitatud. Üle 70 auditisündmuse tüübi (hoidla elutsükkel, varukoopia, sünkroonimine, terminal) jäävad kättesaadavaks kasutaja- ja meeskonnapõhise filtreerimisega haldusarmatuurlaual ja portaalis ning süsteemilogides sügavama kaitse tagamiseks. |
| Reageerimine ja taastumine (Art. 11) | CoW-hetktõmmised koheseks tagasipöördumiseks. `rdc repo push/pull` mitme sihtkoha taastumiseks. Hargipõhine katastroofist taastumise testimine. |
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
