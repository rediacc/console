---
title: "PCI DSS vastavus"
description: "Kuidas Rediacc vastab PCI DSS nõuetele: muutumatud varukoopiad, automaatne võrgusegmenteerimine ja juurdepääsukontroll infrastruktuuri tasemel."
category: "Legal"
order: 6
language: et
sourceHash: "05ca01c69d8bab61"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Kuula: PCI DSS v4.0.1 pole valikuline, kui käsitlead kaardiomaniku andmeid. Versioon 4.0.1 taandub ühele nõudele: infrastruktuuri tasandi isoleerimisele kõigest muust.

Viide: [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## Nõuete vastavusmaatriks

| PCI DSS nõue | Kirjeldus | Rediacc võimalus |
|---------------------|-------------|-------------------|
| **Nõue 1**, Võrgu turvakontrollid | Installige ja hoidke võrgu turvakontrolle | Hoidlapõhised iptables-reeglid blokeerivad kõik hoidlatevahelised liiklused. Igal hoidlal on oma loopback-IP-alamvõrk (/26). |
| **Nõue 2**, Turvalised konfiguratsioonid | Rakendage turvalised konfiguratsioonid kõikidele süsteemi komponentidele | Rediaccfile elutsükli haagid tagavad deterministlikud, reprodutseeritavad konfiguratsioonid. Vaikemandaate pole. LUKS-võtmed genereerib operaator. |
| **Nõue 3**, Talletatud kontoandmete kaitse | Kaitse talletatud kontoandmeid krüptimisega | LUKS2 AES-256 krüptimine kõikidel hoidlamahtudel. Krüptimine on kohustuslik, mitte valikuline. Krüptograafiline kustutamine LUKS-võtme hävitamise kaudu. |
| **Nõue 4**, Transiiditavate andmete kaitse | Kaitse kaardiomaniku andmeid edastuse ajal tugeva krüptograafiaga | Kõik kaugoperatsioonid toimuvad üle SSH. Varukoopiate transport on otsast otsani krüptitud. Krüpteerimata andmeteid pole. |
| **Nõue 6**, Turvaline arendus | Arendage ja hoidke turvalisi süsteeme ja tarkvara | CoW kloonimine loob eraldatud testkeskkondi ilma tootmise kaardiomaniku andmeid arenduskeskkonnale paljastamata. Hargnemine-testimine-edendamine töövoog. |
| **Nõue 7**, Juurdepääsu piiramine | Piirake juurdepääsu süsteemi komponentidele ja kaardiomaniku andmetele ärivajaduse alusel | Hoidlapõhised Dockeri deemoni soklid. Juurdepääs ühele hoidlale ei anna juurdepääsu teisele. SSH-võtmepõhine autentimine. |
| **Nõue 8**, Kasutajate tuvastamine ja autentimine | Tuvastage kasutajad ja autentida juurdepääs süsteemi komponentidele | SSH-võtme autentimine. API-tokenid IP-sidumise ja piiratud õigustega. Kahefaktoriline autentimine (TOTP). |
| **Nõue 9**, Füüsilise juurdepääsu piiramine | Piirake füüsilist juurdepääsu kaardiomaniku andmetele | Isehallatav: füüsiline turvalisus on teie otsese kontrolli all. LUKS-krüptimine muudab varastatud draivid loetamatuks. |
| **Nõue 10**, Logimine ja jälgimine | Logige ja jälgige kõiki juurdepääse süsteemi komponentidele ja kaardiomaniku andmetele | 70+ sündmusetüüpi (autentimine, API-tokenid, konfiguratsioon, litsentsimine, masina toimingud). Haldusarmatuurlaud ja portaal kasutaja, meeskonna, tüübi ning kuupäeva järgi filtreerimisega, pluss JSON-eksport programmiliseks kasutamiseks. Masina toimingud salvestatakse ka süsteemilogidesse kaitsesügavuse eesmärgil. |
| **Nõue 12**, Organisatsioonipoliitikad | Toetage infoturvet organisatsioonipoliitikate ja -programmidega | Isehallatav lahendus kõrvaldab kolmanda osapoole töötleja ulatuse (Nõue 12.8). Vähendab PCI DSS vastavuse piiri. |

## Võrgusegmenteerimine

PCI DSS tugineb tugevalt segmenteerimisele. Näen pidevalt meeskondade katset rakendada iptables-reegleid ebapiisavate isolatsioonide peale. See ei tööta. Edukalt auditi läbinud meeskonnad on segmenteerimise üles ehitanud arhitektuuri. Rediacc annab selle sulle vaikimisi:

- Iga hoidla töötab oma Dockeri deemonis aadressil `/var/run/rediacc/docker-<networkId>.sock`
- Hoidlatel on eraldatud loopback-IP-alamvõrgud (127.0.x.x/26, 61 kasutatavat IP-d võrgu kohta)
- Renet'i poolt jõustatud iptables-reeglid blokeerivad kõik deemoniülese liikluse
- Eri hoidlate konteinerid ei saa võrgutasandil suhelda

Maksete töötlemise hoidla töötab oma Dockeri deemonis ja oma loopback-alamvõrgus, eraldatuna võrgutasandil kõigist teistest rakendustest samal masinal. Lisafaileri reegleid ei ole vaja kirjutada.

## Ulatuse vähendamine

Isehallatav Rediacc vähendab PCI DSS vastavuse ulatust. Te ei pea käsitsi võrgusegmenteerimist konfigureerima; see on automaatne.

- Kaardiomaniku andmevoos puudub kolmanda osapoole pilveserver
- Pole SaaS-tarnijat, keda hinnata Nõude 12.8 alusel (kolmanda osapoole teenusepakkujad)
- Füüsilise turvalisuse kontrollid on teie otsese halduse all
- Krüptimisvõtmeid talletatakse ainult operaatori kohalikus konfiguratsioonis

## Täitemenetlused

Nõrk segmenteerimine ja puuduv krüptimine on kulukate PCI DSS täitemenetluste taga:

- Heartland Payment Systems (2008): ründajad liikusid külgsuunaliselt 48 andmebaasi üle nõrga võrgusegmenteerimise tõttu, paljastades 130 miljonit kaardinumbrit. [Kogukulu ületas 200 miljonit dollarit.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): ründajad liikusid HVAC-tarnija võrgujuurdepääsust kassasüsteemidesse tasase võrguarhitektuuri tõttu, kaaperdades 40 miljonit maksekaart. [Lahendati 18,5 miljoni dollariga 47 osariigi peaprokuröriga.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
