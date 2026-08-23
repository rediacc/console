---
title: Tellimus ja litsentsid
description: >-
  Mõista, kuidas account, rdc ja renet haldavad masina kohti, repositooriumi
  litsentse ja plaani piiranguid.
category: Guides
tags:
  - account
subcategory: account
order: 7
language: et
sourceHash: "15886ad7ee04e90c"
sourceCommit: "fd9d3476b1fdf0ac6ffaa14f486f20f9642fe2d5"
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
rdc subscription login --token "$REDIACC_TOKEN"
```

Tokeni saab süstida ka otse keskkonna kaudu, et CLI saaks repositooriumilitsentse väljastada ja uuendada ilma interaktiivse sisselogimiseta:

```bash
export REDIACC_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Masina kohad ja repositooriumilitsentsid

### Masina kohad (serveri pool)

Masina kohtade jälgimine toimub serveri poolel. Kui CLI väljastab repositooriumilitsentsi, kontrollib account-server tellimuse masina kohtade kvooti. Iga iseteenindusplaan (Community, Professional, Business) sisaldab ühte masina kohta; mitme masinaga juurutused on Enterprise'i lahendus, mille suuruse lepime kokku koos meie partneritega. Koht hoitakse 5 tundi alates sellel masinal viimase repositooriumilitsentsi väljastamisest ja vabaneb automaatselt pärast tegevusetust. Kuna kohta hoitakse ainult aktiivse ettevalmistamise ajal, saab üks koht ikkagi katta mitut masinat kuu jooksul.

Lagi loetakse sinu tellimuse kirjest, mitte koodi kirjutatud plaanikonstandist, nii et kokkulepitud aktiveeringute arv hakkab kehtima kohe, kui see tellimusele märgitakse. Plaanitase määrab ainult algväärtuse.

Väljastamist ja uuendamist jõustatakse erinevalt, ja see vahe on oluline:

- **Uue litsentsi väljastamine peatub lae juures.** Kui kõik kohad on hõivatud, nurjub päring veaga `MAX_MACHINES_REACHED` ja midagi ei valmistata ette.
- **Olemasoleva litsentsi uuendamine ei blokeeru kunagi.** Masin, mis uuendab litsentsi ajal, mil kõik kohad on hõivatud, töötab edasi ja tema koht märgitakse limiiti ületavaks. Seda näed portaalis Masinate lehel, käsu `rdc subscription status` väljundis ja litsentsi oleku API väljal `overLimitCount`. Märgis kaob ise, kui masin on jälle limiidi sees.

Uuendamine on meelega leebem tee. Masin, mis uuendab juba olemasolevat litsentsi, ei lisa uut mahtu, ja sellest keeldumine peataks varundused taristul, mille eest on juba makstud. Blokeeritud jääb just mahu lisamine.

Masinas ei salvestata ühtegi masina litsentsi faili. Koha jõustamine toimub väljastamise ajal serveris.

### Repositooriumilitsents

Repositooriumilitsents on allkirjastatud litsents ühe repositooriumi jaoks ühel masinal. See on ainus litsentsifail, mis masinas salvestatakse, korraldatuna andmehoidla ja allkirjastamisvõtme kaupa:

```
/var/lib/rediacc/license/repos/{guid}/{keyId}.json
/var/lib/rediacc/license/datastores/{datastoreId}/repos/{guid}/{keyId}.json
```

Masina vaikesalvestuses olevad repositooriumid kasutavad esimest teed. Nimelises andmehoidlas olevad repositooriumid kasutavad teist, kus `{datastoreId}` on identiteet, mille see andmehoidla loomisel sai. Just see piiritlemine paneb andmehoidla kahveldamise ausalt arvestama: kahveldatud andmehoidla saab täiesti uue identiteedi, nii et selle repositooriumid alustavad tühja litsentsivaruga, annavad esimesel litsentsitud toimingul teada `missing` ja saavad omaenda litsentsid. Repositoorium, mille litsents nimetab muud andmehoidlat kui see, milles ta asub, nurjub kohe veaga `identity_mismatch`, selle asemel et automaatselt uuesti väljastada, ja just see hoiab ära litsentsifaili kõrvale kopeerimise.

`{keyId}` on 16-kohaline hex-sõrmejälg (allkirjastava serveri Ed25519 avaliku võtme `SHA-256` esimesed 8 baiti). Repositoorium, mida haldab rohkem kui üks konto-universum (näiteks tootmine ja bench, mis mõlemad juurutavad samasse masinasse), hoiab oma `{guid}` kataloogi all ühte faili iga allkirjastamisvõtme kohta. Masina renet'i ehitus valideerib ainult faili, mida tema sisseehitatud võti või sellele ahelatud delegeerimissert suudab kontrollida; teiste universumite failid on passiivsed. Universumite vahetamine ei muuda kunagi litsentse kehtetuks: esimene toiming uues universumis väljastab selle universumi litsentsi ühe korra (`missing` tulemus väljastab automaatselt) ja mõlemad eksisteerivad seejärel koos.

Seda kasutatakse järgmistel juhtudel:

- `rdc repo create`, `rdc repo fork` ja `rdc repo commit`, valideeritakse enne ettevalmistamist (eelväljastatud ilma identiteedi tõenditeta, seejärel pärast loomist uuesti väljastatud identiteedi tõenditega, sest kontrolli hetkel repositooriumi veel ei ole)
- `rdc repo resize`, `rdc repo expand`, `rdc repo merge` ja `rdc repo promote`, **valideeritakse täielikult, sealhulgas aegumine**
- varunduse ülekandmine, **valideeritakse täielikult, sealhulgas aegumine**: `rdc repo push`, `rdc repo pull`, `rdc repo migrate` ja ajastatud varundused
- `rdc repo up`, `rdc repo up --all`, `rdc repo exec` ja repositooriumi automaatkäivitus masina taaskäivitusel, valideeritakse **nii aegumist kui ka delegeerimissertifikaadi akent vahele jättes**
- `rdc repo down`, `rdc repo delete` ja ainult lugemist nõudvad käsud, näiteks repositooriumide loetlemine, ei vaja litsentsi üldse

Allkirju, võtme sidumist, masina sidumist, repositooriumi sidumist ja kõiki delegeerimissertifikaadi piiranguid jõustatakse neil kõigil. Viimane rühm lõdvendab ainult kaht ajaakent, nii et aegunud litsents või kehtivuse kaotanud sert ei saa kunagi takistada sul oma andmete käitamist ega peatamist.

Repositooriumilitsentsid on seotud masina ja sihtrepositooriumiga. Iga litsents sisaldab masina ID-d, repositooriumi GUID-i, tellimuse ID-d, plaani piiranguid ja aegumist. Krüptitud repositooriumide puhul kontrollib Rediacc ka aluseks oleva mahu LUKS-identiteeti.

Samal masinal võivad koos eksisteerida mitu tellimust. Iga repositoorium kannab oma litsentsi oma tellimuskontekstiga.

## Klastrid

Klastreid müüakse meie partnerite kaudu Enterprise'i lepingu osana. See ei ole iseteeninduslik plaanivalik, ja alljärgnev kirjeldab, kuidas seda arvestatakse, mitte kuidas seda osta.

**Sõlm on masin.** Klastril ei ole omaenda litsentsi-identiteeti. Iga selle sõlm on tavaline masin, kuhu on paigaldatud Renet'i agent, ja seda loetakse täpselt nagu eraldiseisvat masinat.

**Ühist kogumit ei ole.** Viie sõlmega klaster ei võta ühest jagatud klastrikohast. Iga sõlm võtab oma koha esimest korda, kui sinna repositoorium paigutatakse, ja see koht järgib sama 5-tunnist hõljumist nagu kõik teised: seda hoitakse 5 tundi alates sellel sõlmel viimase repositooriumilitsentsi väljastamisest ja seejärel vabaneb see ise.

**Klastri ülesehitamine on tasuta. Arvestus algab repositooriumide paigutamisest.** Klastri loomine, sõlmede ühendamine, hajusa salvestuskihi paigaldamine ja Kubernetese juhtimistasandi püstitamine ei maksa ühtegi kohta. Arvestus algab siis, kui repositoorium jõuab sõlmele.

**Klastri kahveldamine arvestab iga repositooriumi eraldi uuesti.** Terve klastri kahveldamine annab kahveldatud andmehoidlale uue identiteedi, nii et iga kahvli repositoorium saab esimesel puudutamisel omaenda litsentsi, sellel sõlmel, kus ta parasjagu töötab. Tavaline migreerimine on vastupidine juhtum: repositooriumi liigutamine masinate vahel viib litsentsi kaasa ja see valideerub edasi, sest tema salvestuse identiteedis ei muutunud midagi.

**Uuendamine klastris järgib ülalkirjeldatud pehme koha reeglit.** Sõlmed uuendavad oma litsentse ilma järelevalveta, nii et klaster, mis on oma aktiveeringute arvu ületanud, töötab edasi ja teatab limiiti ületavatest sõlmedest, selle asemel et lasta varundustel keset ööd nurjuda. Uue sõlme lisamine peatub siiski lae juures.

Klastri suuruse valik on vestlus, mitte linnuke kastis. Klastrite aktiveeringute arvud lepitakse kokku tellimuses ja sinu partner määrab need otse tellimusele. Vestluse alustamiseks vaata [Kontakt](/en/contact).

## Vaikepiirangud

Repositooriumi suurus sõltub õiguste tasemest:

- Community: kuni `10 GB`
- tasulised plaanid: plaani või lepingu piirang

Vaikimisi tasuliste plaanide piirangud on:

| Plaan | Hõljuvad litsentsid | Repositooriumi suurus | Igakuised repositooriumilitsentside väljastamised | Delegeerimissertifikaadi vaikimisi/max |
|------|-------------------|-----------------|-------------------------------|---|
| Community | 1 | 10 GB | 100 | 15d / 30d |
| Professional | 1 | 100 GB | 2,000+ | 60d / 120d |
| Business | 1 | 500 GB | 5,000+ | 90d / 180d |
| Enterprise | Kohandatud | 1 TB+ | 15,000+ | 120d / 365d |

Lepingupõhised piirangud võivad konkreetse kliendi puhul neid väärtusi tõsta või langetada. Delegeerimissertifikaadi kehtivus on ka kõvasti piiratud väärtusega `subscription.expiresAt + 3 day grace`, nii et igakuise arveldusega tellimused saavad sertifikaadid, mis on joondatud nende arveldustsükliga. Täielikke reegleid vaata jaotisest [Litsentsiahel ja delegeerimine - kehtivuspoliitika](/en/docs/license-chain).

## Tasuta prooviperiood ja Community tagasilangus

Uued kasutajad alustavad 14-päevase tasuta prooviperioodiga Professionali või Businessi plaanil. Krediitkaart võetakse registreerimisel, kuid esimene arve esitatakse alles siis, kui prooviperiood lõpeb, seega ei maksa tühistamine enne seda midagi. Iga klient saab ühe prooviperioodi.

Community on püsiv tasuta baastase. See ei ole enam uutele kontodele otsene registreerimisvõimalus; selle asemel langeb konto Community peale iga kord, kui tellimus lõpeb: tühistamine prooviperioodi ajal, tasulise plaani hilisem tühistamine või ebaõnnestunud makse. Community tagasilanguse puhul jääb alles üks masin, 10 GB repositooriumi kohta ja 100 seadistust kuus. Kontod, mis loodi enne prooviperioodil põhineva mudeli käivitamist, säilitavad oma senise Community juurdepääsu.

Jõustamine jääb pehmeks seal, kus see kõige rohkem loeb: töötavad repositooriumid jätkavad tööd ka pärast tellimuse lõppemist (`up`, `down`, `delete`, automaatkäivitus). Edasi kehtivad aga kaks erinevat reeglit, ja just nende segiajamine paneb 60-päevase tähtajaperioodi ebajärjekindlana paistma:

- **Toimingud, mis vajavad account-serverit,** ei saa ilma aktiivse tellimuseta toimuda, sest server keeldub allkirjastamast. Need on `create`, `fork` ja iga litsentsi värskendamine või uuendamine. Kui tellimus lõpeb, ei valmistata enam midagi uut ette.
- **Toimingud, mis vajavad ainult kehtivat paigaldatud litsentsi,** töötavad edasi kuni selle litsentsi kõva aegumiseni, ilma serverita. Need on `resize` ja `expand` juba olemasolevatel repositooriumidel ning varunduse ülekandmine (`push`, `pull`, ajastatud varundused). Repositooriumi põhilitsents aegub kõvasti 60 päeva pärast tellimuse lõppkuupäeva, ja sealt tulebki 60-päevane tähtajaperiood. Kahvli litsents on palju lühiealisem, ülempiiriga 7 päeva, ja just seetõttu sõltuvad kahvlirohked masinad allpool kirjeldatud iseuuendamisest.

Nii peatab lõppenud tellimus sinu masinapargi kasvatamise kohe ja selles olevate repositooriumide kasvatamise 60 päeva hiljem.

## VM-i migratsiooni tähtajaperiood

Kui hostimispakkuja migreerib VM-i teisele füüsilisele riistvarale, muutub masina ID (see tuletatakse riistvara identifikaatoritest nagu DMI UUID, `/etc/machine-id` ja NIC MAC-aadressid). Repositooriumilitsentsid on seotud masina ID-ga, seega muudaks migratsioon tavaliselt kõik litsentsid kehtetuks.

Selle läbipaistvaks lahendamiseks sisaldavad repositooriumilitsentsid **40-päevast masina ID tähtajaperioodi**. Kui masina ID ei ühti, kuid litsents on väljastatud vähem kui 40 päeva tagasi, aktsepteeritakse litsentsi siiski. Kuna litsentsid uuendatakse iga 30 päeva tagant, seostub järgmine uuendus automaatselt uue masina ID-ga.

Praktikas:
- VM migreeritakse, masina ID muutub: repositooriumid jätkavad tööd (40-päevase akna piires)
- Järgmine `rdc` toiming uuendab litsentsi uue masina ID-ga
- Käsitsi sekkumist ei ole vaja
- Kontrolli masina ID-d ja litsentsi olekut käsuga `rdc machine status <machine> --system --licenses`

**Edge-kanali kontod** töötavad Community plaanil 2-kordsete piirangutega (20 GB repositooriumid, 200 seadistust/kuus, 2 masinat). Tasulised plaanid on saadaval ainult Stable-kanalil. Üksikasju vaata jaotisest [Väljalaskekanalid](/en/docs/release-channels).

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
rdc subscription login --token "$REDIACC_TOKEN"
```

Mitteinteraktiivsetes keskkondades on `REDIACC_TOKEN` seadistamine lihtsaim valik. Token peaks olema ulatuspiiratud ainult nende tellimuse ja repositooriumilitsentsi toimingute jaoks, mida agent vajab.

Kuva account-põhine tellimuse olek:

```bash
rdc subscription status
```

Kuva masina aktiveerimise üksikasjad ühe masina kohta:

```bash
rdc subscription status -m hostinger
```

Kuva paigaldatud repositooriumilitsentsi üksikasjad ühe masina kohta:

```bash
rdc subscription status -m hostinger
```

Uuenda repositooriumi litsentsi masinas:

```bash
rdc subscription refresh -m hostinger --repo my-app
```

`--repo` viide peab lahenema sinu kohalikus `rdc` konfiguratsioonis. Masinas avastatud, kuid kohalikust konfiguratsioonist puuduv repositoorium lükatakse tagasi: see kuvatakse tõrkena ega klassifitseerita automaatselt.

Esmakordsel kasutamisel võib litsentsitud repositooriumi või varunduse toiming, mis ei leia kasutatavat repositooriumilitsentsi, käivitada account-autoriseerimise ülemineku automaatselt. CLI kuvab autoriseerimise URL-i, üritab interaktiivsetes terminalides brauserit avada ja kordab toimingut üks kord pärast eduka autoriseerimise ja väljastamise toimumist.

Mitteinteraktiivsetes keskkondades CLI ei oota brauseri kinnitust. Selle asemel palutakse sul esitada ulatuspiiratud token käsuga `rdc subscription login --token ...` või `REDIACC_TOKEN`.

Masina esmakordse seadistamise kohta vaata [Masina seadistamine](/en/docs/setup).

## Litsentsi iseuuendamine

Kõik eelnev eeldab, et sa istud klaviatuuri taga. Ajastatud varundused seda ei tee, ja just selle jaoks iseuuendamine olemas ongi.

Ajastatud varundus valideeritakse rangel tasemel, seega vajab see aegumata litsentsi. Kahvli litsentsi ülempiir on 7 päeva. Sinu masinatel ei ole disaini poolest ühtegi konto mandaati, nii et enne iseuuendamist jäi kahvli varundus lihtsalt nädal pärast selle loomist seisma, vaikselt, kell kolm öösel.

### Kuidas masin end ilma tokenita uuendab

Iga litsents, mille Rediacc väljastab või uuendab, kannab välja `renewalUrl` ehk selle account-serveri uuenduslõpp-punkti täisaadressi, kes litsentsi allkirjastas. Masin loeb selle aadressi omaenda paigaldatud litsentsist, nii et talle ei pea kunagi ütlema, kus tema account-server asub.

Seejärel esitab masin paigaldatud litsentsi tagasi sellele lõpp-punktile. Litsents ise ongi mandaat: see on allkirjastatud, server kontrollib allkirja ja ühtegi API-tokenit ei ole kusagil vaja. Server tagastab värske litsentsi uute kehtivusakendega ning masin paigaldab selle ja valideerib uuesti, enne kui loeb uuenduse tehtuks.

Uuendamine on kogu masinat hõlmav toiming:

```bash
sudo renet license renew
```

Repositooriumid rühmitatakse neid allkirjastanud serveri kaupa, nii et kaht konto-universumit teenindav masin võtab kummagagi ühendust ühe korra. Lukufail hoiab ära kahe uuenduse samaaegse käivitumise ja `--jitter` hajutab masinapargi, mis muidu ärkaks kõik täistunnil.

Server keeldub uuendamisest kolmel juhul ja igaüks neist tähendab midagi muud:

| Keeldumine | Mida see tähendab |
|---|---|
| Tellimus on lõppenud, peatatud või tähtajaperiood on möödas | Arveldus. Uuendamine jätkub ise, kui tellimus on jälle aktiivne |
| Delegeerimissert on aegunud või tühistatud | Kohapealne seadistus. Uuenda sert oma kohapealses serveris, seejärel uuenevad masinad tavapäraselt |
| Masina identiteet ei ühti enam ja 40-päevane tähtajaperiood on möödas | Litsents kuulub masinale, kes see masin ei ole. Väljasta uuesti praegusest masina kontekstist |

Keeldumine ei peata kunagi tervet käiku. Üks lõppenud repositoorium ei blokeeri sama masina teiste repositooriumide uuendamist.

### Ajastatud varundused uuendavad end ise

Iga varundusüksus, mille Rediacc kirjutab, käivitab kõigepealt uuenduse:

```
ExecStartPre=-<renet> license renew --jitter 45s
```

Ees olev `-` märgib selle meelega parima võimaliku pingutusena. Keeldutud uuendus, võrgutõrge või vanem Renet'i agent, kes käsku veel ei tunne, ei tohi kunagi varundust ennast maha võtta. Varundus käivitub ja litsents uuendatakse käigu pealt siis, kui see on võimalik.

### Kui varundus on blokeeritud

Kui litsentsimine varundusest tõesti keeldub, salvestab masin selle. See märgis on ainus signaal, et järelevalveta varundused on andmete kopeerimise lõpetanud, seega tuuakse see selgelt esile:

```bash
rdc machine status <machine> --licenses
```

Veerus `backups` on kirjas `BLOCKED` koos põhjusega, ja sama teave trükitakse tabeli alla veateatena, et see kolmekümne repositooriumi seas kaduma ei läheks. Veerg `renewed` näitab, kuidas viimane järelevalveta uuendus läks, sealhulgas serveri keeldumiskoodi, kui see oli, ja just see ütleb sulle, kas lahendus on arvelduse või kohapealse serdi küsimus.

Edukas uuendamine kustutab märgise, samuti varundus, mis oma litsentsikontrolli läbib. Käsitsi ei ole midagi kinnitada ega lähtestada.

## Võrguühenduseta käitumine ja aegumine

Litsentsi valideerimine toimub masinas lokaalselt. See ei nõua elusat ühendust account-serveriga.

See tähendab:

- töötav keskkond ei vaja iga käsu puhul elusat account-ühendust
- kõik repositooriumid saavad alati käivituda, peatuda ja kustutada ka aegunud litsentside korral, kasutajad ei satu kunagi oma repositooriumide haldamisest välja
- ettevalmistustoimingud (`create`, `fork`) nõuavad eelväljastatud repositooriumilitsentsi ning kasvu toimingud (`resize`, `expand`) nõuavad kehtivat repositooriumilitsentsi
- tõeliselt aegunud repositooriumilitsentsid tuleb enne suuruse muutmist/laiendamist välja vahetada, kas `rdc` kaudu oma tööjaamast või nii, et masin uuendab end ise
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
- `cert_expired`: nurjub kiiresti kasvutoimingutel (`create`, `fork`, `resize`) ja varunduse ülekandel (`push`, `pull`); `repo up` ja automaatkäivitus töötavad jätkuvalt, vastavalt pehmele litsentsi aegumise mudelile. Uuenda delegeerimissert
- `cert_invalid`: ebaõnnestub kiiresti, delegeerimissert ei vastanud mõnele piirangule (vigane peamise võtme allkiri, tellimuse/plaani mittevastavus, suuruse ülempiir või järjestus üle `maxTotalIssuances`). Väljasta sert pärast aluspiirangu parandamist uuesti

Need kiire ebaõnnestumise juhtumid ei tarbi automaatselt account-põhiseid uuendus- või väljastamistaotlusi.

Kaks märkust selle loendi lugemiseks:

- `missing` ei ole alati probleem. See on ka tavapärane tulemus, kui värskelt kahveldatud andmehoidlas puudutatakse repositooriumi esimest korda, ja just see paneb kahvli arvestuse käima: litsents väljastatakse, koht võetakse ja toiming jätkub. `identity_mismatch` on tahtlik vastand: teisest andmehoidlast kopeeritud litsentsifail nurjub kohe, selle asemel et seda vaikselt uuesti väljastada.
- See loend kirjeldab taastumist sinu tööjaamast. End ise uuendaval masinal on omaenda tulemused, millest annab teada `rdc machine status <machine> --licenses`, mitte käsu tõrge, sest ajastatud varundusel ei ole kellelegi öelda.

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

Kui vajad kliendile suunatud kasutuse ja hiljutiste repositooriumilitsentside väljastamise ajaloo vaadet, kasuta account-portaali. Kui vajad masina poolset kontrollimist, kasuta käske `rdc subscription status -m` ja `rdc subscription status -m`.
