---
title: Tellimus ja litsentsid
description: >-
  Mõista, kuidas account, rdc ja renet haldavad masina kohti, repositooriumi
  litsentse ja plaani piiranguid.
category: Guides
order: 7
language: et
sourceHash: 10e9f781881854be
sourceCommit: 2e3862505c06f97f846b7d879375434011954f95
---

# Tellimus ja litsentsid

Rediacc litsentsimisel on kolm liikuvat osa:

- `account` allkirjastab õigused ja jälgib kasutust
- `rdc` autentib, taotleb litsentse, toimetab need masinatele ja jõustab neid käitusajal
- `renet` (masinas töötav käitusaeg) valideerib paigaldatud litsentse lokaalselt ilma account-serveriga ühendust võtmata

See leht selgitab, kuidas need osad kohaliku juurutamise korral kokku sobivad.

## Mida litsentsid teevad

Litsentsid kontrollivad kaht erinevat asja:

- **Masina ligipääsu arvestust** **hõljuvate litsentside** kaudu
- **Repositooriumi käitusajaautentimist** **repositooriumilitsentside** kaudu

Need on omavahel seotud, kuid ei ole sama asi.

## Kuidas litsentsimine töötab

`account` on tõde allikas plaanide, lepinguliste alistuste, masina kohtade oleku ja igakuiste repositooriumilitsentside väljastamise kohta.

`rdc` töötab sinu tööjaamas. See logib sind account-serverisse sisse, taotleb vajalikke litsentse ja paigaldab need SSH kaudu kaugmasinatesse. Kui käivitad repositooriumi käsu, tagab `rdc`, et nõutavad litsentsid on paigas, ja valideerib need masinas käitusajal.

Tavapärane voog näeb välja järgmine:

1. Autentid käsuga `rdc subscription login`
2. Käivitad repositooriumi käsu, näiteks `rdc repo create`, `rdc repo up` või `rdc repo down`
3. Kui nõutav litsents puudub või on aegunud, taotleb `rdc` seda `account`'ilt
4. `rdc` kirjutab allkirjastatud litsentsi masinasse
5. Litsents valideeritakse masinas lokaalselt ja toiming jätkub

Vt [rdc vs renet](/en/docs/rdc-vs-renet), et mõista tööjaama ja serveri jagamist, ning [Repositooriumid](/en/docs/repositories) repositooriumi elutsükli kohta.

Automatiseerimise ja AI-agentide jaoks kasuta brauseri sisselogimise asemel ulatuspiiratud tellimustokenit:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Tokeni saab süstida ka otse keskkonna kaudu, et CLI saaks repositooriumilitsentse väljastada ja uuendada ilma interaktiivse sisselogimiseta:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Masina kohad ja repositooriumilitsentsid

### Masina kohad (serveri pool)

Masina kohtade jälgimine toimub serveri poolel. Kui CLI väljastab repositooriumilitsentsi, kontrollib account-server tellimuse masina kohtade kvooti (nt 2 masinat Community jaoks, 3 Professional jaoks). Koht hoitakse 5 tundi alates sellel masinal viimase repositooriumilitsentsi väljastamisest ja vabaneb automaatselt pärast tegevusetust. 10-kohaga Business plaan saab seega aja jooksul katta kümneid masinaid, kuna kohti hoitakse ainult aktiivse ettevalmistamise ajal.

Masinas ei salvestata ühtegi masina litsentsi faili. Koha jõustamine toimub väljastamise ajal serveris.

### Repositooriumilitsents

Repositooriumilitsents on allkirjastatud litsents ühe repositooriumi jaoks ühel masinal. See on ainus litsentsifail, mis masinas salvestatakse (`/var/lib/rediacc/license/repos/{guid}.json`).

Seda kasutatakse järgmistel juhtudel:

- `rdc repo create` ja `rdc repo fork`, valideeritakse enne ettevalmistamist (eelväljastatud ilma identiteedi tõenditeta, seejärel uuesti väljastatud identiteedi tõenditega pärast loomist)
- `rdc repo resize` ja `rdc repo expand`, täielik valideerimine koos aegumisega
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, valideeritakse **aegumist vahele jättes**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, valideeritakse **aegumist vahele jättes**
- repositooriumi automaatkäivitus masina taaskäivitusel, valideeritakse **aegumist vahele jättes**

Repositooriumilitsentsid on seotud masina ja sihtrepositooriumiga. Iga litsents sisaldab masina ID-d, repositooriumi GUID-i, tellimuse ID-d, plaani piiranguid ja aegumist. Krüptitud repositooriumide puhul kontrollib Rediacc ka aluseks oleva mahu LUKS-identiteeti.

Samal masinal võivad koos eksisteerida mitu tellimust. Iga repositoorium kannab oma litsentsi oma tellimuskontekstiga.

## Vaikepiirangud

Repositooriumi suurus sõltub õiguste tasemest:

- Community: kuni `10 GB`
- tasulised plaanid: plaani või lepingu piirang

Vaikimisi tasuliste plaanide piirangud on:

| Plaan | Hõljuvad litsentsid | Repositooriumi suurus | Igakuised repositooriumilitsentside väljastamised | Delegeerimissertifikaadi vaikimisi/max |
|------|-------------------|-----------------|-------------------------------|---|
| Community | 2 | 10 GB | 100 | 15d / 30d |
| Professional | 3 | 50 GB | 2,000+ | 60d / 120d |
| Business | 10 | 200 GB | 5,000+ | 90d / 180d |
| Enterprise | 25+ | 1 TB+ | 15,000+ | 120d / 365d |

Lepingupõhised piirangud võivad konkreetse kliendi puhul neid väärtusi tõsta või langetada. Delegeerimissertifikaadi kehtivus on ka kõvasti piiratud väärtusega `subscription.expiresAt + 3 day grace`, nii et igakuise arveldusega tellimused saavad sertifikaadid, mis on joondatud nende arveldustsükliga. Täielikke reegleid vaata jaotisest [Litsentsiahel ja delegeerimine - kehtivuspoliitika](/en/docs/license-chain).

## VM-i migratsiooni tähtajaperiood

Kui hostimispakkuja migreerib VM-i teisele füüsilisele riistvarale, muutub masina ID (see tuletatakse riistvara identifikaatoritest nagu DMI UUID, `/etc/machine-id` ja NIC MAC-aadressid). Repositooriumilitsentsid on seotud masina ID-ga, seega muudaks migratsioon tavaliselt kõik litsentsid kehtetuks.

Selle läbipaistvaks lahendamiseks sisaldavad repositooriumilitsentsid **40-päevast masina ID tähtajaperioodi**. Kui masina ID ei ühti, kuid litsents on väljastatud vähem kui 40 päeva tagasi, aktsepteeritakse litsentsi siiski. Kuna litsentsid uuendatakse iga 30 päeva tagant, seostub järgmine uuendus automaatselt uue masina ID-ga.

Praktikas:
- VM migreeritakse, masina ID muutub: repositooriumid jätkavad tööd (40-päevase akna piires)
- Järgmine `rdc` toiming uuendab litsentsi uue masina ID-ga
- Käsitsi sekkumist ei ole vaja
- Kontrolli masina ID-d ja litsentsi olekut käsuga `rdc machine query --system --licenses --name <machine>`

**Edge-kanali kasutajad** saavad 2-kordsed Community piirangud tasuta (20 GB repositooriumid, 200 väljastamist/kuus, 4 masinat). Tasulised plaanid on saadaval ainult Stable-kanalil. Üksikasju vaata jaotisest [Väljalaskekanalid](/en/docs/release-channels).

## Mis juhtub repositooriumi loomisel, käivitamisel, peatamisel ja taaskäivitamisel

### Repositooriumi loomine ja kahveldamine

Repositooriumi loomisel või kahveldamisel:

1. `rdc` tagab, et sinu tellimuse token on saadaval (käivitab vajadusel seadmekoodi autentimise)
2. `rdc` eelväljastab repositooriumilitsentsi account-serverist (server kontrollib sel hetkel masina kohtade kvooti ja igakuiseid väljastamispiiranguid)
3. Eelväljastatud repositooriumilitsents kirjutatakse masinasse ja valideeritakse lokaalselt (allkiri, masina ID, repositooriumi GUID, aegumine ja suuruse piirang)
4. Pärast edukat loomist väljastab `rdc` repositooriumilitsentsi uuesti koos repositooriumi identiteedi tõenditega (LUKS UUID või salvestuse sõrmejälg)

See account-põhine väljastamine arvestatakse sinu igakuiste **repositooriumilitsentside väljastamiste** kasutuse hulka. Iga litsents sisaldab konto omaniku e-posti ja ettevõtte nime, mis logitakse, kui renet litsentsi valideerib.

### Repositooriumi käivitamine, peatamine ja kustutamine

`rdc` valideerib masinas paigaldatud repositooriumilitsentsi, kuid **jätab aegumise kontrolli vahele**. Allkiri, masina ID, repositooriumi GUID ja identiteet kontrollitakse siiski. Kasutajad ei satu kunagi oma repositooriumide haldamisest välja, isegi aegunud tellimuse korral.

### Repositooriumi suuruse muutmine ja laiendamine

`rdc` teostab täieliku repositooriumilitsentsi valideerimise, sealhulgas aegumise ja suuruse piirangute kontrolli.

### Masina taaskäivitus ja automaatkäivitus

Automaatkäivitus kasutab samu reegleid nagu `rdc repo up`: aegumine jäetakse vahele, seega repositooriumid käivituvad alati vabalt.

Repositooriumilitsentsid kasutavad pikaajalist kehtivusmudelit:

- `refreshRecommendedAt` on pehme uuenduspunkt
- `hardExpiresAt` on blokeeriv punkt

Kui repositooriumilitsents on aegunud, kuid pole veel jõudnud kõva aegumiseni, saab käitamine jätkuda. Kui kõva aegumine saabub, peab `rdc` suuruse muutmise ja laiendamise toimingute jaoks seda uuendama.

### Muud repositooriumi toimingud

Toimingud nagu repositooriumide loetlemine, repositooriumi info vaatamine ja ühendamine ei nõua litsentsi valideerimist.

## Oleku kontrollimine ja litsentside uuendamine

Inimkasutaja sisselogimine:

```bash
rdc subscription login
```

Automatiseerimise või AI-agendi sisselogimine:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Mitteinteraktiivsetes keskkondades on `REDIACC_SUBSCRIPTION_TOKEN` seadistamine lihtsaim valik. Token peaks olema ulatuspiiratud ainult nende tellimuse ja repositooriumilitsentsi toimingute jaoks, mida agent vajab.

Kuva account-põhine tellimuse olek:

```bash
rdc subscription status
```

Kuva masina aktiveerimise üksikasjad ühe masina kohta:

```bash
rdc subscription activation status -m hostinger
```

Kuva paigaldatud repositooriumilitsentsi üksikasjad ühe masina kohta:

```bash
rdc subscription repo status -m hostinger
```

Uuenda repositooriumilitsentse partiina masinas:

```bash
rdc subscription refresh repos -m hostinger
```

Masinas avastatud, kuid kohalikust `rdc` konfiguratsioonist puuduvad repositooriumid lükatakse partiina uuendamise ajal tagasi. Need kuvatakse tõrgetena ega klassifitseerita automaatselt.

Tee repositooriumilitsentsi jõuluuendus olemasoleva repositooriumi jaoks:

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

Esmakordsel kasutamisel võib litsentsitud repositooriumi või varunduse toiming, mis ei leia kasutatavat repositooriumilitsentsi, käivitada account-autoriseerimise ülemineku automaatselt. CLI kuvab autoriseerimise URL-i, üritab interaktiivsetes terminalides brauserit avada ja kordab toimingut üks kord pärast eduka autoriseerimise ja väljastamise toimumist.

Mitteinteraktiivsetes keskkondades CLI ei oota brauseri kinnitust. Selle asemel palutakse sul esitada ulatuspiiratud token käsuga `rdc subscription login --token ...` või `REDIACC_SUBSCRIPTION_TOKEN`.

Masina esmakordse seadistamise kohta vaata [Masina seadistamine](/en/docs/setup).

## Võrguühenduseta käitumine ja aegumine

Litsentsi valideerimine toimub masinas lokaalselt. See ei nõua elusat ühendust account-serveriga.

See tähendab:

- töötav keskkond ei vaja iga käsu puhul elusat account-ühendust
- kõik repositooriumid saavad alati käivituda, peatuda ja kustutada ka aegunud litsentside korral, kasutajad ei satu kunagi oma repositooriumide haldamisest välja
- ettevalmistustoimingud (`create`, `fork`) nõuavad eelväljastatud repositooriumilitsentsi ning kasvu toimingud (`resize`, `expand`) nõuavad kehtivat repositooriumilitsentsi
- tõeliselt aegunud repositooriumilitsentsid tuleb uuendada `rdc` kaudu enne suuruse muutmist/laiendamist
- litsentsi allkirjad kontrollitakse manustatud avaliku võtme vastu; allkirja kontrollimist ei saa keelata

## Taastumiskäitumine

Automaatne taastumine on tahtlikult piiratud:

- `missing`: `rdc` võib vajadusel autoriseerida account-ligipääsu, uuendada repositooriumilitsentse partiina ja korrata üks kord
- `expired`: `rdc` võib repositooriumilitsentse partiina uuendada ja korrata üks kord
- `machine_mismatch`: ebaõnnestub kiiresti ja palub sul väljastada praegusest masina kontekstist uuesti
- `repository_mismatch`: ebaõnnestub kiiresti ja palub sul repositooriumilitsentse otsesõnu uuendada
- `sequence_regression`: ebaõnnestub kiiresti kui repositooriumilitsentsi terviklikkuse/oleku probleem
- `invalid_signature`: ebaõnnestub kiiresti kui repositooriumilitsentsi terviklikkuse/oleku probleem
- `identity_mismatch`: ebaõnnestub kiiresti, repositooriumi identiteet ei ühti paigaldatud litsentsiga

Need kiire ebaõnnestumise juhtumid ei tarbi automaatselt account-põhiseid uuendus- või väljastamistaotlusi.

## Delegeerimissertifikaadid kohapealse paigalduse jaoks

Kohapealse ja suletud võrgu juurutuste jaoks väljastab ülemine account-server **delegeerimissertifikaadi**, mis volitab sinu kohapealse paigalduse allkirjastama litsentse oma Ed25519 võtmega. Sertifikaat piirab kohapealse paigalduse oma plaani piirangutega ja loob rikkumiskindla ahela.

Peamised punktid tellimuse omanikele:

- **Üks aktiivne sertifikaat ühe tellimuse kohta.** Iga kohalik paigaldus jõustab kuupõhised ja masina kvoodid oma kohaliku arvestuse alusel, seega mitu paigaldust korrutaks tegelikku kvooti ilma võimaliku vastavusse viimiseta. Kliendid, kes vajavad tootmist + testimist + DR-i, peavad ostma ühe tellimuse iga paigalduse kohta.
- **Tasemepõhine vaikekehtivus** (15d / 60d / 90d / 120d) ja ülemmäärad (30d / 120d / 180d / 365d) - vaata piirangute tabelit eespool.
- **Iseteenindusvõimalus kliendiportaalist.** Organisatsiooni omanikud ja administraatorid saavad luua, uuendada ja tühistada delegeerimissertifikaate aadressil `/account/delegation-certs`. Leht on nähtav kõigile klientidele sõltumata plaani tasemest - erinevad on ainult piirangud.
- **Automaatne uuendamine** on toetatud ühe klõpsuga alglaadimise kaudu, mis loob `delegation:renew` ulatusega API tokeni, mida kohalik paigaldus kasutab ülemise uuendamise päringute jaoks.
- **Suletud võrgu uuendamine** on toetatud allkirjastatud uuendustaotluse manifesti kaudu, mille kohaliku paigalduse administraator laadib alla, edastab võrguühenduseta ülemisele, kes töötleb seda uue sertifikaadi väljastamiseks.

Operatiivse seadistamise kohta vaata [Kohalik paigaldamine - litsentsimine suletud võrgu juurutuste jaoks](/en/docs/on-premise), ja krüptograafilise disaini kohta [Litsentsiahel ja delegeerimine](/en/docs/license-chain).

## Igakuised repositooriumilitsentside väljastamised

See mõõdik loendab edukaid account-põhiseid repositooriumilitsentside väljastamistoiminguid jooksval UTC kalendrikuul.

See sisaldab:

- esmakordset repositooriumilitsentsi väljastamist
- edukat repositooriumilitsentsi uuendamist, mis tagastab uuesti allkirjastatud litsentsi

See ei sisalda:

- muutumata partiikandeid
- ebaõnnestunud väljastamiskatseid
- jälgimata repositooriume, mis lükati tagasi enne väljastamist

Kui vajad kliendile suunatud kasutuse ja hiljutiste repositooriumilitsentside väljastamise ajaloo vaadet, kasuta account-portaali. Kui vajad masina poolset kontrollimist, kasuta käske `rdc subscription activation status -m` ja `rdc subscription repo status -m`.
