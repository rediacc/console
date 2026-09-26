---
title: Konfiguratsioonisalv
description: Kliendipoolselt krüpteeritud konfiguratsioonisünkroonimine passkey, peaparooli ja taastekoodiga avamisega
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: et
sourceHash: "ccced160d151eeeb"
sourceCommit: "6cfcb0017e6db164abaf81c7e0a10d0d8086370b"
---

# Konfiguratsioonisalv

Konfiguratsioonisalv sünkroonib CLI konfiguratsiooni seadmete vahel. Konfiguratsioonid krüpteeritakse seadmes sisukrüpteerimisvõtmega (CEK), mida server kunagi ei oma. Jaotis [Turvalisus](#security) kirjeldab täpselt, mille eest see kaitseb ja mille eest mitte.

## Avamismeetodid (võtmepesad)

Igal salvel on üks CEK, mis on iga avamismeetodi jaoks eraldi mähitud (sarnaselt LUKS-i võtmepesadele). Iga üksik pesa avab sama võtme ning pesasid saab lisada või eemaldada ilma andmeid uuesti krüpteerimata:

| Meetod | Mis see on | Märkused |
|--------|-----------|-------|
| **Passkey** | WebAuthn passkey PRF-laiendusega | Kõige tugevam valik; riistvarapõhine |
| **Peaparool** | Sinu valitud parool, venitatud PBKDF2-SHA256-ga (600 000 iteratsiooni) | Toimib ka ilma PRF-toega riistvarata; võimaldab ka pealdiseta CLI registreerimist |
| **Taastekood** | Genereeritud `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` kood | Näidatakse täpselt üks kord loomisel; hoia see turvalises kohas |

Iga meetod läbib sama protsessi: pesa annab saladuse, mis kombineeritakse serveripoolse saladusega CEK-i lahtimähkimiseks. Kummastki poolest üksi ei piisa ja pesa saladus ei jõua kunagi serverisse. Peaparooli pesa on kolmest kõige nõrgem: serveril on olemas kõik, mida on vaja parooli oletuste offline-testimiseks, seega peab parool olema tugev. Passkey ja taastekoodi pesadel sellist nõrkust ei ole.

Pesasid hallatakse portaalis Konfiguratsioonisalve lehel. Organisatsioonid, kes soovivad ainult riistvarapõhist avamist, saavad lubada **nõua passkey** poliitika, mis keeldub mitte-passkey pesadest ja tühistab need kogu salve jaoks.

Avamine on seadmepõhine: sa avad salve uuel seadmel üks kord ja pärast seda toimivad igapäevased CLI toimingud (push/pull) ilma passkey'i puudutamata või parooli sisestamata.

## Eeltingimused

- **Kahefaktoriline autentimine** on kontol lubatud
- **Passkey** meetodi jaoks: PRF-toega passkey-pakkuja, näiteks FIDO2 turvavõti (nt YubiKey), iCloud Keychain, Google Password Manager, 1Password või Dashlane
- **Brauser**: Chrome 133+, Edge 133+, Firefox 130+ või Safari 17+

PRF-nõue kehtib ainult passkey-pesa kohta. Peaparooli ja taastekoodi meetodid toimivad igas toetatud brauseris.

## Seadistamine

1. Naviseeri külgribal **Konfiguratsioonisalv** ja klõpsa **Seadista konfiguratsioonisalv**
2. Nõuete kontrollnimekiri kontrollib brauserit, 2FA-d ja seansi olekut
3. Vali esimene lukust avamise viis ja klõpsa **Loo konfiguratsioonihoidla**:
   - **Pääsuvõti**, kui su teenusepakkuja toetab PRF-i: puudutad turvavõtit kaks korda, üks kord registreerimiseks ja teist korda krüpteerimisvõtmete tuletamiseks.
   - **Ülemparool**, mis töötab igas brauseris, ka PRF-i toeta pääsuvõtme pakkujatega nagu Bitwarden.
   - Soovi korral **taastekood**, mida näidatakse ainult üks kord ja mis tuleb enne hoidla loomist salvestada.
4. Seadistus on valmis. CLI hoiab lukust avamise saladust sinu operatsioonisüsteemi võtmehoidlas.

Pääsuvõtme saab hiljem lisada Config Storage lehelt. Hoia alles vähemalt kaks lukust avamise viisi, et kaotatud või toeta autentija sind välja ei lukustaks.

## PRF-pakkuja ühilduvus

| Pakkuja | PRF tugi | Platvormid |
|----------|:-----------:|-----------|
| YubiKey / FIDO2 turvavõtmed | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Platvormideülene |
| Bitwarden laiendus | ❌ | Kasuta selle asemel peaparooli |
| Windows Hello | ❌ | Pole toetatud |

## Pealdiseta CLI registreerimine

Brauserita masin (server, CI-käitaja, käitaja teenus) saab liituda olemasoleva salvega peaparooli meetodi abil:

```bash
rdc config remote enable --password
```

Nõuded:

- **Peaparooli pesa** on portaali kaudu juba loodud (brauser hoiab võtit loomise ajal, seega see samm ise ei saa olla pealdiseta)
- **API-token `config:enroll` õigusega** kutse autentimiseks

Registreerimine on lugemistoiming: CLI toob pesa avalikud KDF-parameetrid ja mähitud võtme, tuletab parooli saladuse lokaalselt ning mähib CEK-i seadmes lahti. See annab seadmele õiguse konfiguratsiooni dekrüpteerida ja sünkroonida; see ei muuda salve.

## Lubamine ja võrguühenduseta lugemine

`rdc config remote enable` ühendab aktiivse konfiguratsiooni salvega. Kui salv on tühi, **lubamine täidab selle sinu praeguse kohaliku konfiguratsiooniga**: kohalikud ressursid saadetakse (push) salve esimese versioonina ja seejärel tuuakse (pull) tagasi, et tõestada ringtee toimimist. Kui salves on juba sisu, lepitab lubamine seda selle asemel, et üle kirjutada (see katkestab tegeliku lahknevuse korral, kui sa ei kasuta `--force`).

Pärast lubamist hoiab konfiguratsioon täielikku **lugemise vahemälu**, mis on puhkeolekus krüpteeritud sama mehhanismiga nagu iga kohalik konfiguratsioon, nii et salv jääb kasutatavaks ka siis, kui kontoserver pole kättesaadav:

- **Lugemine toimib võrguühenduseta.** Vahemälus olev sisu edastatakse koos aegumishoiatusega stderr-is, märgistatuna vahemällu salvestatud versiooni ja ajatempliga (`cachedVersion` / `cachedAt`).
- **Kirjutamine nõuab serverit ja ebaõnnestub turvaliselt.** Võrguühenduseta kirjutusjärjekorda ei ole: kirjutamine, mis ei jõua serverini, lõpeb veaga, mis nimetab serverit. Kui kirjutuskäsk õnnestus, on muudatus serveris.
- **Samaaegsed muudatused kahest masinast** lahendatakse pull-replay-repush põhimõttel: server võtab vastu ainult pushi, mis on asendatava versiooni peal, ja kaotanud push mängitakse värske koopia peal uuesti läbi, nii et samaaegne muudatus mujal ei kirjuta sinu oma üle.
- **Kohalikku konfiguratsiooni** (ilma `remote` plokita) see kõik ei mõjuta ja see töötab täielikult võrguühenduseta.

## Mis sünkroonitakse

Konfiguratsiooni kõik sisu sünkroonitakse, sealhulgas iga repositooriumi võrgu ID, välja arvatud järgmised seadmepõhised väljad: `schemaVersion`, `version`, `remote`, `encryption`, `renetPath`, `credentials.masterPasswordVerifier` ning sisselogimisväljad `account.accountServer` ja `account.e2ePublicKey`. Sisse- ja väljalogimine toimub seadmepõhiselt.

## Versioonid ja taastamine

Server hoiab iga konfiguratsiooni viimast 50 versiooni.

```bash
rdc config remote versions
rdc config remote restore <version>
```

Taastamine avaldab vana sisu uue versioonina praeguse peal; versiooninumber ei liigu kunagi tagasi. Iga seade saab taastatud sisu järgmisel tõmbamisel (pull) ja taastamine registreeritakse auditilogisse.

## Võtme pööramine

Salve CEK-i pööramine mähib selle uude põlvkonda:

- **Taastekoodid muutuvad pööramisel alati kehtetuks**, genereeri ja salvesta pärast seda uus
- **Peaparooli pesa** säilib ainult siis, kui parool sisestatakse pööramisviisardis uuesti
- Vana põlvkonda jäänud pesa märgitakse aegunuks, mitte ei ebaõnnestu arusaamatu dekrüpteerimisveaga
- Teiste liikmete konfiguratsioonitokenid tühistatakse ning seadmele, mis hoiab veel vana võtit, kuvatakse juhis uuesti aktiveerida käsuga `rdc config remote enable`

## Liikmete haldamine

Konfiguratsioonisalv on organisatsioonipõhine. Liikmeid hallatakse veebiportaali kaudu:

- **Liikmete vaatamine**: Konfiguratsioonisalv → Liikmed
- **Liikme lisamine**: Praegu ainult CLI kaudu (veebi UI planeeritud)
- **Liikme eemaldamine**: Klõpsa eemaldamise nuppu Liikmete lehel (nõuab 2FA + uuesti autentimist)

Turvamehhanismid takistavad viimase aktiivse liikme eemaldamist või enda eemaldamist.

Salves olevad konfiguratsioonid on lisaks piiritletud meeskonna kaupa, kuid see piiritlus on **serveripoolne juurdepääsukontroll, mitte krüptograafiline isolatsioon**: üks organisatsiooniülene CEK krüpteerib kõigi meeskondade konfiguratsioonid ning server jõustab, milliseid meeskondi liige tohib lugeda.

## Turvalisus

**Mis on kaitstud.** Salvestatud konfiguratsioonid on konfidentsiaalsed serveri salvestuse kompromiteerimise ja passiivse operaatori vastu. Iga blob on seotud oma salve, konfiguratsiooni, meeskonna ja versiooniga, seega ei saa server vahetada ühe konfiguratsiooni blobi teise vastu ega muuta seda avastamatult.

**Mis ei ole kaitstud.** Operaator, kes serveerib pahatahtlikku portaalikoodi, saab lugeda võtit brauseris. Operaator võib ka jätta seadmele, mis pole kunagi uuemat versiooni näinud, selle uusima versiooni edastamata.

| Server saab | Server ei saa |
|---|---|
| Näha konfiguratsioonide ID-sid, meeskondi, versiooninumbreid, ajatempleid, blobi suurusi, mitut välja konfiguratsioon kommiteerib ja iga välja tüüpi, ning kliendi IP-aadresse | Näha masina, repositooriumi ega salve nimesid (need on varjatud) ega ühtegi konfiguratsiooni väärtust |
| Keelduda, viivitada või kustutada konfiguratsioone ja nende ajalugu | Serveerida ühe konfiguratsiooni sisu teise omana või seda muuta ilma, et seade seda tuvastaks |
| Serveerida vana versiooni seadmele, mis pole kunagi uuemat näinud | Serveerida CLI-le versiooni, mis on vanem kui see, mida ta juba nägi: CLI keeldub sellest |
| Testida peaparooli oletusi offline | Avada passkey või taastekoodi pesa |

Muud kaitsemeetmed:

- **Jagatud võti**: dekrüpteerimiseks on vaja nii pesa saladust (seadmes) kui ka serveri saladust
- **Kustutamine nõuab teadmist**: kommiteeritud väärtuse eemaldamine konfiguratsioonist nõuab tõestust, et väärtus oli teada, nii et osalise juurdepääsuga agent ei saa vaikimisi välju kustutada
- **Pöörlevad tokenid**: iga päring pöörab konfiguratsioonitokenit; token on seotud selle esimese kasutamise IP-aadressiga ja aegub 7 päeva pärast
- **Tühistamine**: liikme eemaldamine kustutab korraga tema võtmepesad ja tokenid; see, mida ta juba oli tõmmanud, jääb tema seadmesse, ning CEK-i pööramine takistab tal säilinud võtmega hilisemaid versioone avamast

## Tõrkeotsing

| Viga | Põhjus | Lahendus |
|-------|-------|-----|
| PRF pole toetatud | Autentikaatoril puudub PRF-laiendus | Kasuta YubiKey, iCloud Keychain, 1Password või Dashlane, või lisa peaparooli pesa |
| X25519 pole toetatud | Brauseri versioon on liiga vana | Uuenda Chrome 133+, Edge 133+, Firefox 130+ või Safari 17+ |
| Juba konfigureeritud | Salv on sinu organisatsiooni jaoks olemas | Külasta /account/config-storage haldamiseks |
| Konfiguratsioonisalv pole seadistatud | Serveril puudub blob-salvestus | Võta ühendust administraatoriga R2/RustFS seadistamiseks |
| Token aegunud | Tegevust pole olnud 7 päeva või seade vahetas võrku | Uueneb automaatselt sisselogimise kaudu; kui sisselogimist pole salvestatud, käivita `rdc subscription login` või `rdc config remote enable` |
| Konfiguratsioon tuli tagasi vanema versiooniga | Server tagastas vanema koopia kui see, mida seade juba nägi | Kohalikult ei muutunud midagi; proovi uuesti ja anna sellest teada, kui see kordub |
| Viimast liiget ei saa eemaldada | Salv lukustaks end jäädavalt | Lisa esmalt teine liige |
| Aegunud pesa | Pesa pärineb enne viimast võtme pööramist | Lisa pesa uuesti (taastekoodid tuleb pärast iga pööramist uuesti genereerida) |

## Seotud

- [Veebikonsool](/et/docs/web-console), salve avamine brauseris käskude käivitamiseks
- [Proxy ja käitaja](/et/docs/proxy-and-executor), kuidas avatud võti käitajale antakse
