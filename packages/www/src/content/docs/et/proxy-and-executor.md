---
title: Proxy ja käitaja
description: Kuidas brauseri ja õhukese kliendi käsud töötavad ilma, et klient hoiaks kunagi SSH-võtmeid või masinate aadresse
category: Concepts
tags:
  - security
  - networking
subcategory: architecture
order: 4
language: et
sourceHash: "ca9a0c894ff59160"
sourceCommit: "e9aac9fb933462f72c9d2c3753c52a30f70b7f97"
---

# Proxy ja käitaja

Tavaliselt töötab `rdc` sinu enda masinas koos sinu konfiguratsiooni ja SSH-võtmetega ning ühendub serveritega otse. Proxy-mudel jagab selle kaheks: õhuke klient, mis ei hoia ühtegi saladust, ja **käitaja**, mis hoiab neid ja teeb töö ära. [Veebikonsooli](/et/docs/web-console) Käivita nupp ja CLI `--proxy` lipp on mõlemad õhukesed kliendid ning nad räägivad sama juhtmeprotokolli.

## Käsu kavatsus, mitte käsk ise

Õhuke klient ei hoia kunagi SSH-võtit, masina aadressi ega dekrüpteeritud konfiguratsiooni. Kui ta soovib midagi käivitada, saadab ta ainult käsu kavatsuse: identifikaatori käsu jaoks (selle asukoht CLI lepingus, näiteks `repo up`) koos parameetritega. Käitaja otsib käsu samast lepingust üles, lahendab selle vastavaks serveripoolseks funktsiooniks, lahendab sihtmasina dekrüpteeritud konfiguratsioonist ja käivitab selle oma SSH-ühenduse kaudu. Väljund voogedastatakse tagasi kliendile.

Käitaja on CLI ise, käivitatud serverina käsuga `rdc serve`. Sama binaarfail, mida operaatorid sülearvutis kasutavad, muutub selleks, mis nende nimel käske käivitab. Sellel on kaks paigutusviisi:

- **`--mode daemon`**: töötab sinu enda hallatud hostis, registreeritud pealdiseta nagu iga teine CLI (vt [Konfiguratsioonisalv](/et/docs/config-storage)), nii et see saab konfiguratsioonivõtme ise tuletada ega vaja seansipõhist andmist. See on range tase: SSH ei lahku kunagi sinu võrgust.
- **`--mode container`**: töötab sinu jaoks hallatud organisatsioonipõhises konteineris. See alustab ilma ühegi võtmeta ja ei saa midagi teha, kuni klient seansi jaoks võtme annab. See on mugavuse tase.

## CEK-i andmine

Konfiguratsioonisalv on null-teadmisega: server salvestab ainult krüpteeritud plokke ja sisukrüpteerimisvõti (CEK) eksisteerib lahtiselt ainult kliendil, kes selle avas. Konteinerirežiimis käitajale tuleb seetõttu võti *anda* ning andmine ei tohi seda vahepeal serverile paljastada.

Voog on selline: avatud brauser avab käitajaga seansi, saab seansi avaliku võtme ja pitseerib CEK-i sellele seansile X25519 abil. Pitseeritud plokk läbib kontoserverit, kuid server ei suuda seda avada, seega säilib null-teadmine läbivalt. Käitaja dekrüpteerib CEK-i ainult mällu, 30-minutilise jõudeaja aegumisega; midagi ei kirjutata kunagi kettale. Järgnevad käsupäringud viitavad antud seansile `X-Config-Session` päise kaudu.

Auditeerimise seisukohalt on oluline üks detail: sama kasutajaidentiteet käib läbi kõiki kolme etappi (seansi avamine, võtme andmine, käskude käivitamine). Kontoserver ei edasta käitajale kunagi enda mandaati. Iga etapi jaoks vermib ta lühiajalise tokeni, mis on seotud tegeliku kasutajaga, ja kontrollib iga kord uuesti selle kasutaja liikmesust. Käitaja kontrollib, milline token talle iga toimingu jaoks esitatakse. Ühe kasutaja tehtud andmist ei saa kasutada teine kasutaja.

Konfiguratsiooni `state` pool (hostikohalikud käitusandmed) ei liigu kunagi konfiguratsiooniploki sees, seega ei jõua see ka selle tee kaudu kunagi käitajani.

## Mis saab proxy kaudu töötada

Mitte iga käsk pole kaugkäivituseks mõistlik. Iga käsk lepingus kannab `proxyCapable` lippu ja käitaja jõustab seda serveripoolselt, sõltumata mistahes poliitikaseadistusest:

- **Masinatasandi, mitteinteraktiivsed käsud** (deploy, backup, staatus, logid jms) on proxy-toega.
- **Konfiguratsioonitasandi käsud** ei ole: need muudavad konfiguratsiooni, mis sellel teel on brauseri ülesanne (veebikonsool suunab need selle asemel oma konfiguratsiooniredaktorisse).
- **Interaktiivsed käsud** (terminalid, VS Code seansid) ei ole: sellel juhtmel puudub TTY.
- **Kliendipoolsed ülekandekäsud** (`rdc repo sync`) ei ole: need liigutavad andmeid *kliendi* failisüsteemi ja masina vahel, käitajal pole ligipääsu kliendi failidele.

Veebikonsool loeb sama lippu, et otsustada, kas käsk saab üldse Käivita nupu, kuid käitaja keeldub mittetoetatud käskudest sõltumata sellest, mida klient saadab.

## Mock-käitaja

Arenduse ajal, kui ühtegi päris käitajat pole konfigureeritud, vastab kontoserver käsupäringutele ise mock-voogude ja selgelt võltsandmetega (ressursside nimed eesliitega `mock-`). See võimaldab kogu konsooli testida, sealhulgas vorme, voogedastust ja tulemuste kuvamist, ilma masina või avamiseta. Päris käivitamiseks on vaja päris käitajat.

## Piirang, kust käitaja ühendub

Konfiguratsiooni `access`-hoidla sisaldab SSH-võtmete lubatud IPv4 ja IPv6 lähtevahemikke. Vahemikke saab määrata kogu konfiguratsioonile, võtmele ja masinale, nii et masin aktsepteerib võtit ainult nendelt aadressidelt, kust tema käitaja ühendub.

- `rdc config access add <key> --public-key ... --hosted-executor` registreerib võtme ja lisab hostitava käitaja kaks vahemikku: `104.28.0.0/16` ja `2a09:bac0::/29`. Mõlemad on jälgitud Cloudflare'i väljuva liikluse vahemikud, mitte Cloudflare'i avaldatud loend, seega võivad need muutuda.
- `rdc machine access set <machine> --key <key>` määrab masinale võtme; `--ipv4`, `--ipv6` ja `--clear-ranges` kohandavad selle masina vahemikke.
- `rdc machine access push <machine>` kirjutab juurdepääsuread masinasse ning `--dry-run` näitab tulemust midagi muutmata.
- `rdc machine access show <machine>` kuvab kehtivad juurdepääsuread.

`machine setup` rakendab juurdepääsuread uuesti, nii et uuesti üles seatud masin saab oma piirangud tagasi.

Push, mis lukustaks praeguse SSH-seansi välja, kuna selle aadress jääb kasutatava võtme vahemikest välja, lükatakse tagasi veaga `ACCESS_LOCKOUT` ja midagi ei kirjutata. Push lükatakse tagasi veaga `ACCESS_FILE_CHANGED`, kui fail on masinas vahepeal muutunud; midagi ei rakendatud, seega võib pushi turvaliselt uuesti proovida.

## Tööd, piletid ja päring

Iga masinatasandi käsk töötab masinas tööna: renet haldab systemd üksust, mille olek ja sündmuste logi on masinas spoolis. Katkenud ühendus ei peata seetõttu tööd kunagi ning iga klient saab töö tema ID järgi uuesti üles võtta.

- **Haakimisaken.** Täitja voogedastab töö sündmusi kuni 20 sekundit ning saadab vaikse voo ajal iga 10 sekundi järel südamelöögirea. Aknas lõppev töö tagastab tulemuse samas päringus. Pikem töö tagastab tulemuse väärtusega `state: running` ja töö ID-ga pärast `job`-rida, mis kannab masinat ja kattuvaid töid.
- **Päring.** Seejärel küsib klient aadressilt `GET /v1/jobs/<id>/poll` viimati nähtud reast järgnevad sündmused koos töö olekuga ning pikendab päringute vahet, kuni vastused on tühjad. `POST /v1/jobs/<id>/cancel` tühistab töö. Mõlemad teed rakendavad sama poliitikat kui töö käivitanud käsk ning päring, mis esimesena lõppseisundi näeb, kirjutab auditisündmuse ainult ühe korra.
- **Piletid.** Iga käivitus kirjutab lisaks pileti CLI seadistuskataloogi (`jobs/<config>.jsonl`). `rdc job wait <id>` ootab tööd ja lõpeb selle väljumiskoodiga; `rdc job list`, `status`, `logs`, `cancel` ja `gc` haldavad ülejäänut. Ctrl-C jälgimise ajal eraldub tühistamata ja väljub koodiga 130. Jälgimine, mille ühendust ei õnnestunud taastada, väljub koodiga 16 ja jätab pileti alles.
- **Sammud.** Töö järel tehtav, näiteks tulemuse kirjutamine seadistusse või loendi kuvamine, on samm, mis on kirja pandud piletisse ja spoolis. Samm käivitub üks kord seal, kus töö lõppemist esimesena nähakse: käsk ise, `rdc job wait`, järgmise käsu trükitud teade või täitja päring. Nõue esitatakse masinas, mistõttu kaks jälgijat ei käivita kunagi sama sammu.
- **Kattuvused.** Käivitus, mis kattub sama hoidla või sama masina käimasoleva tööga, trükib hoiatuse käsuga, mis haakub käimasoleva tööga. Kui kattumispoliitika keeldub käivitusest, lõpeb käsk koodiga 15 (`BUSY`) ja keeldumine nimetab kattuvad tööd väljas `overlaps`.
- **Sammud kliendi äraoleku ajal.** Edusamm käivitub ainult siis, kui töö on `succeeded`, ja tõrkesamm, näiteks tagasivõtmine, ainult siis, kui töö on `failed` või tühistatud. Kui töö lõpeb haakimisaknas, hoiab täitja haakimist alles ka pärast kliendi lahtiühendamist ja käivitab sammud, nii et lühike käsk, mille klient vastuse kaotas, lõpetab oma sammud ikkagi. Sammud käivituvad ainult kliendil, kelle seadistus vastab tööd käivitanud seadistusele; iga muu seadistus näitab `N steps pending for config <name>`. Järgmise käsu teade käivitab ootel sammud kuni 20 sekundit selle käsu enda väljundi järel ja ainult interaktiivses tekstikäivituses. Valikuga `-o json`, `-q` või MCP kaudu ei käivita see midagi ja trükib stderr-i `steps pending: rdc job wait <id>`. Kuni ükski jälgija pole töö lõppemist näinud, teenus töötab edasi, kuid sammud ootavad: DNS-nimed, sertifikaatide sünkroonimine ja URL-ide loend pärast `repo up`, forki, migreerimise või taastamise varundusgraafikud ning baaskirje, mis teeb järgmisest push'ist deltapush'i. `rdc job list` näitab `steps pending`, kuni need on käivitunud.
- **Erandid.** Interaktiivsed käsud (`term connect`, `repo tunnel`, `vscode connect`, `repo exec -i` ja `repo logs -f`), kliendipoolsed ülekanded (`repo sync upload`, `download` ja `status` ning `backup upload` ja `download`), `job`-käsud, `serve`, `vscode serve status` ja `stop` ning käsud, mis ei tee ühtegi renet-kutset, näiteks `cluster kubeconfig` ja `machine access push`, ei tööta töödena. Käskude `machine provision` ja `deprovision` kohalikud OpenTofu etapid töötavad kliendil nagu varem. Iga muu masinatasandi käsk on töö.
- **Säilitus.** Lõppenud kirjutuskaitstud tööd hoitakse ühe tunni ja iga muud lõppenud tööd seitse päeva. Tööd, mille sammu keegi pole nõudnud, hoitakse seitse päeva olenemata klassist, ja käimasolevat tööd ei eemaldata kunagi. Spool mahutab kuni 2000 lõppenud tööd ja 256 MiB, vanimad lõppenud tööd lähevad esimesena. Puhastus käib töö käivitamisel, kuni kord tunnis. Töö systemd-üksus peatatakse esimesel olekulugemisel või puhastuskäigul, mis näeb tööd lõppenuna.

## Seotud

- [Veebikonsool](/et/docs/web-console), sellel mudelil põhinev brauseriklient
- [Konfiguratsioonisalv](/et/docs/config-storage), null-teadmisega salv, mida CEK kaitseb
