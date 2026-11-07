---
title: "Varunduse sihtkohad"
description: "Saada iga varundusstrateegia mitmesse hoidlasse, taasta hoidlast, kus on parim hetktõmmis, ja loe iga sihtkoha kohta üks olekurida."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: et
sourceHash: "10ded4035f1e9641"
sourceCommit: "7264926d04c36ba68ec76946fc14565405acd340"
---

# Varunduse sihtkohad

Varundusstrateegia võib kirjutada mitmesse hoidlasse. Iga sihtkoht on eraldi taastepunkt: tal on oma hetktõmmis, oma commit ja oma olekurida, nii et tõrkuv hoidla ei riku teist.

Kõik hoidlad kuuluvad ühele kontole. Neid kõiki katavad üks config, üks litsents ja üks arve. Kahte kontosse sisse logitud masin lükatakse endiselt tagasi, sest mitu sihtkohta tähendab mitut hoidlat ühe konto sees.

## Hoidlad

Hoidla on ämber (bucket), kuhu kontoserver kirjutab masina nimel. Igal tellimusel on esimesest päevast olemas hoidla nimega `home`: majutatud hoidla, mida varunduskäsud on alati kasutanud. Sihtkoht, mis hoidlat ei nimeta, kirjutab hoidlasse `home`.

Peale selle saab registreerida kahte liiki.

| Liik | Mis see on | Mida registreerimine nõuab |
|------|------------|----------------------------|
| `hosted-r2` | Teine majutatud regioon, valitud regioonidest, mida juurutus pakub | Id ja regioon. Mandaate pole vaja |
| `customer-s3` | Kliendi enda hallatav ämber S3-l, RustFS-il või mis tahes S3-ga ühilduval teenusel | Id, HTTPS-otspunkt, ämber, allkirjastamisregioon (vaikimisi `us-east-1`), valikuline avalik otspunkt ja üks juurdepääsuvõtmete paar |

Masin ei hoia kunagi kliendi ämbri võtmeid. Võtmed asuvad suletuna kontoserveris ja masin saab lühiealised eelallkirjastatud URL-id ainult sellele ühele hoidlale, mida tema seanss nimetab.

### Hoidla registreerimine

Registreerimine on konto API kutse, mitte `rdc` käsk. `POST /backups/stores` registreerib hoidla, `GET /backups/stores` loetleb registreeritud hoidlad ja `DELETE /backups/stores/<id>` võtab hoidla kasutusest. Registreerimine, võtmete vahetamine ja kasutusest võtmine nõuavad API tokenit skoobiga `backup:manage`, mille on loonud organisatsiooni praegune omanik või administraator, ja iga toiming auditeeritakse. Loetlemiseks on vaja `backup:read`.

Server kontrollib hoidlat enne selle vastuvõtmist.

- **Vastavussond.** Server teeb samad kontrollid, mille majutatud hoidla läbib. Hoidla, mis ei jõusta kontrollsummasid, lükatakse registreerimisel tagasi, mitte ei avastata seda alles esimese varunduse ajal.
- **Kustutussond.** Sond proovib ka kustutada. Kui hoidla keeldub, registreeritakse see keelatud puhastusega (vt allpool).
- **Otspunkti reeglid.** Ainult HTTPS, port 443 ja ükski otspunkt ei asu sisevõrgus.
- **Hoidlate piir.** Hoidlate arv tellimuse kohta sõltub paketist, `home` kaasa arvatud, kasutusest võetud hoidlaid ei loeta.

| Pakett | Hoidlad |
|--------|---------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

Olemasoleva id registreerimine vahetab ainult selle mandaadid ja sond jookseb uuesti. Hoidla, mille mandaadid lakkavad töötamast, märgitakse peatatuks esimese tagasilükatud loa korral. `GET /backups/stores` näitab otspunkti, ämbrit ja võtme id viimaseid märke, aga mitte kunagi saladust.

Hoidlat ei saa kasutusest võtta, kuni lubatud sihtkoht seda veel nimetab, ja `home` kasutusest võtta ei saa.

## Sihtkoha hoidla nimetamine

Sihtkoht nimetab oma hoidla valikuga `--target`, mida kasutatakse koos valikuga `--destination`:

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| Valik | Kirjeldus |
|-------|-----------|
| `--destination <name>` | Sihtkoht, mida luuakse või muudetakse |
| `--target <storeId>` | Registreeritud hoidla id, kuhu sihtkoht kirjutab (vaikimisi `home`). Nõuab valikut `--destination` |

Ühe strateegia kaks lubatud sihtkohta ei tohi nimetada sama hoidlat ja registreerimata hoidla lükatakse tagasi koos registreeritud id-de loendiga.

Iga ajastatud käivitus teeb ühe hetktõmmise lubatud sihtkoha kohta, sihtkohtade deklareerimise järjekorras, igaühel oma ribalaiuse piir. Iga hetktõmmis on värske copy-on-write reflink, seega on igaüks iseenesest järjepidev ajahetk. Tõrkuv sihtkoht ei jäta järgmist vahele. Üksus lõpetab siiski nullist erineva koodiga, kui mõni sihtkoht tõrkus, nii et systemd ja vahelejäänud käivituste kontroll näevad tõrget.

## Taastamine hoidlast

Käsud `rdc backup restore`, `rdc backup restore --path`, `rdc backup browse --at` ja `rdc backup download --store` aktsepteerivad valikut `--from <storeId>`:

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

Ilma valikuta `--from` küsib CLI kontoserverilt, millised hoidlad hoiavad repositooriumi päritolu. Need järjestatakse nii, et esimesena on hoidla, mille uusim hetktõmmis läbis viimase kontrolli, ja CLI proovib neid selles järjekorras. Hoidla, kus hetktõmmist pole, jäetakse vahele. Kui järjestust ei õnnestu lugeda, kasutab taastamine hoidlat `home` ja ütleb seda.

Ilma valikuta `--from` alustavad `backup restore`, `restore --path`, `browse --at` ja `download --store` selle järjestuse esimesest hoidlast ning liiguvad järgmisse hoidlasse, kui tõrge on hoidla poolel: serveri viga, tagasi lükatud luba või seanss või otspunkt, mis ei vasta. Iga käsk ütleb, milline hoidla teda teenindas. Ükski neist ei lülitu teisele hoidlale hetktõmmise enda vea pärast. Puuduv, aegunud või riknenud hetktõmmis näeb igas hoidlas ühesugune välja, seega näidatakse viga. Käsk, millele on antud `--from`, loeb ainult seda hoidlat ega lülitu kunagi teisele.

Hetktõmmise id, mis on antud ilma valikuta `--from`, otsitakse kõigist päritoluliini hoidlatest.

## Olek sihtkoha kaupa

`rdc backup status` trükib ajakavatabeli kõrvale ühe rea sihtkoha kohta:

| Veerg | Tähendus |
|-------|----------|
| Store | Hoidla id, kuhu sihtkoht kirjutab |
| Last run | Millal selle hoidla viimane käivitus lõppes |
| Result | Selle käivituse tulemus |
| Newest snapshot | Uusim hetktõmmis, mida hoidla hoiab |
| Verify | Hoidla viimase kontrolli tulemus |
| Clean-up | `enabled` või keelatud koos põhjusega |

Hoidla, mille kohta konto aru anda ei saa, näitab oma veergudes `-`. Vahelejäänud käivituste kontroll toimub hoidla kaupa, nii et hoidla, mis lakkas varukoopiaid saamast, tõstab oma alarmi, samal ajal kui teised jäävad roheliseks.

## Mis loetakse kvooti

Majutatud hoidlad, `home` ja iga teine regioon, mõõdetakse füüsiliselt salvestatud unikaalsete baitide järgi ja nende baidid loetakse samasse paketi kvooti. `rdc backup usage` näitab neid.

Kliendi ämbri baite Rediacc ei salvesta ja neid kvooti ei loeta. Metaandmeid, mida konto selle jaoks hoiab (manifestiread, kontrollkäivitused ja indeksiobjektid), mõõdetakse nagu majutatud hoidla omi.

## Hoidlad keelatud puhastusega

Hoidla, mille kustutamine on keelatud, säilitab iga objekti. Säilitus ja prügikoristus ei kustuta sealt kunagi midagi. Kui hetktõmmis aegub, märgib pühkimine selle kontol aegunuks, lõpetab selle pakkumise taastamiseks ja jätab selle objektid ämbrisse.

`rdc backup status` ja varunduse tervisekokkuvõte teatavad hoidlast kui keelatud puhastusega hoidlast. Ämber kasvab edasi, kuni kustutusmandaadid lisatakse, registreerides sama id uuesti võtmetega, millel on kustutusõigus.
