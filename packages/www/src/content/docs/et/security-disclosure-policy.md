---
title: "Haavatavuste avalikustamise poliitika"
description: "Kuidas teatada Rediacci turvaaugast: reguleeritud ulatus, õiguslik kaitse, teavitamise viis ja oodatavad vastamisajad."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 9
language: et
sourceHash: "49a84775c19854ee"
sourceCommit: "72636750e43d473936cbb242ec9c7511fd246f65"
---

Rediacc ootab teateid oma toodete ja teenuste turvahaavatavuste kohta. Poliitika kirjeldab, mis kuulub ulatusse, kuidas teatada ja mida teataja vastutasuks eeldada võib. Masinloetav kontaktfail asub aadressil [`/.well-known/security.txt`](https://www.rediacc.com/.well-known/security.txt) (RFC 9116).

## Ulatus

Ulatusse kuulub:

- `rdc` CLI ja masinate orkestraator `renet`
- kontoserver, selle veebiportaal ja API
- Rediacci veebisaidid domeenide `rediacc.com` ja `rediacc.cloud` all
- väljalaske artefaktid: binaarfailid, konteineripildid ja paigaldusprogrammid

Ulatusest väljas on:

- leiud, mis eeldavad füüsilist ligipääsu masinale, või teataja enda kontrolli all olev kompromiteeritud lõppseade
- mahupõhine teenusetõkestusrünne, rämpspost ja töötajate sotsiaalne manipuleerimine
- automaatsete skannerite aruanded, mille mõju pole tõendatud
- kolmanda osapoole tarkvara haavatavused, mida Rediacc ainult muutmata kujul edasi levitab; need kuuluvad algprojektile, ent koopia Rediaccile on teretulnud

## Kuidas teatada

Saatke teade aadressile [security@rediacc.com](mailto:security@rediacc.com). Lisage:

- mõjutatud toode ja versioon või URL
- reprodutseerimise sammud või kontseptsioonitõend
- teataja hinnang mõjule
- kas probleem on juba avalik või seda kasutatakse ära
- kontaktaadress järelkirjavahetuseks ja soov, kas teatajat mainitakse

Eelistatud on ingliskeelsed teated. Päris kliendiandmeid teatesse ei lisata: piisab ligipääsu minimaalsest tõestusest.

## Õiguslik kaitse (safe harbour)

Rediacc ei algata ega toeta õiguslikke samme teataja vastu, kes tegutseb selle poliitika alusel heas usus, see tähendab, et teataja:

- testib ainult oma kontosid, masinaid ja andmeid või Rediacci omandis olevaid ressursse
- peatub, kui probleem on tõendatud, ega loe, muuda, kopeeri ega kustuta teistele kuuluvaid andmeid
- ei halvenda teenust teistele kasutajatele
- teatab kiiresti ja hoiab üksikasjad konfidentsiaalsena allpool nimetatud kooskõlastatud avalikustamise kuupäevani

Neis piirides jääv tegevus loetakse lubatuks ja Rediacc kinnitab seda igale kolmandale osapoolele, kes seda küsib.

## Vastamisajad

| Samm | Siht |
|------|------|
| Teate kättesaamise kinnitus | 2 tööpäeva |
| Esmane hinnang koos tõsidusastmega | 5 tööpäeva |
| Seisuteated, kuni juhtum on avatud | vähemalt iga 14 päeva järel |
| Kriitilise probleemi parandus või leevendus | 14 päeva hinnangust |
| Muude kinnitatud probleemide parandus või leevendus | 90 päeva hinnangust |

Tähtajad on eesmärgid, mitte garantiid: kui teade vajab rohkem aega, saab teataja selgituse ja uue kuupäeva.

## Kooskõlastatud avalikustamine

Üksikasjad avaldatakse koos paranduse väljalaskega, tavaliselt 90 päeva jooksul teate saamisest. Teataja, kes soovib varasemat või hilisemat avaldamist, nimetab kuupäeva teates ja pooled lepivad kuupäevas kokku. Juba aktiivselt ärakasutatavat haavatavust käsitletakse intsidendina, nagu on kirjeldatud [intsidentidele reageerimise lehel](/et/docs/security-incident-response).

## Tunnustus

Kinnitatud teatajat mainitakse väljalaskemärkmetes või turvateates teataja valitud nime või hüüdnime all. Rediacc ei korralda tasustatud veaotsingu auhinnaprogrammi.

## Seotud

- [Intsidentidele reageerimine](/et/docs/security-incident-response)
- [Konto turvalisus ja API](/et/docs/account-security)
