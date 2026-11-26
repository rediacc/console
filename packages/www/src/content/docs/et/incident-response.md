---
title: "Intsidentidele reageerimine: uurimine, deklareerimine ja tõendite säilitamine"
description: "Avage hoidla või masina uurimine, lugege ühte ajatelge, kus on audit, käivitused, voogud ja failiavamised, kontrollige räsiahelaid, deklareerige intsident, et tõendid külmutada ning käivitada 24 tunni, 72 tunni ja ühe kuu tähtajad, ning juhtige kõike rdc kaudu."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: et
sourceHash: "07d8b9d09d0e2191"
sourceCommit: "d93166e47a19c588a2284e21d263cca7f8a3578d"
---

# Intsidentidele reageerimine

Intsident tähendab siin sündmust, mis leiab aset kliendi enda hoidlates. Uurimisleht, `rdc incident` käsud ning lugejad `rdc repo flows` ja `rdc repo opens` kasutavad kõik kirjeid, mida kirjeldab [digitaalne kriminalistika](/et/docs/forensics). Rediacci enda süsteemide intsidendid järgivad dokumenti [turvaintsidentidele reageerimine](/et/docs/security-incident-response).

## Ligipääs

Uurimine nõuab tasulist paketti ning omaniku või administraatori rolli. Avamisel küsitakse hiljutist uuesti autentimist ja avatud uurimine kehtib 60 minutit. Iga vaatamine kirjutatakse auditilogisse.

Rediacci tugi näeb kriminalistika andmeid ainult toeluba alusel, mille klient annab. Luba kehtib kuni 7 päeva ja selle saab igal ajal tühistada.

CLI lugemised vajavad skoopi `forensics:read`, deklareerimine ja sulgemine vajavad skoopi `incident:manage`. CLI sisselogimine kannab mõlemat omanike ja administraatorite jaoks pärast kõrgendatud kinnitust brauseris. Kui käsk vastab, et vaja on hiljutist kõrgendatud kinnitust, küsib konto portaal seda ja käsu saab uuesti käivitada.

## Ajatelg

Leht Investigate liidab ühe skoobi (hoidla või masin) üheks ajatelgeks, kus on viit liiki ridu: konsooli auditisündmused, käivitused, võrguvood, failiavamised ja anomaaliad. Muudatusi alates viimasest hetktõmmisest saab sellega võrrelda. Ajaakna liugur määrab akna ja aken hõlmab kuni 31 päeva.

Tõenditeta lõik ilmub lünga reana, mis nimetab masina ja põhjuse, mitte kunagi tühja lõiguna. Ridade kohal on väljuvate baitide diagramm minuti kaupa ja populaarseimate sihtkohtade loend.

Samad lugemised on kättesaadavad käsurealt:

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` ja `--until` võtavad ISO 8601 ajahetke või praegusest tagasi arvestatud ajavahemiku nagu `90m`, `24h` või `7d`. Vaikeaken on viimased 24 tundi. Voo read näitavad aega, protsessi, sihtkohta, väljuvaid ja sissetulevaid baite ning ASN-i ja riiki, kui need on teada. Avamise read näitavad aega, protsessi ja teed, tundlikud teed märgituna.

## Tõendite kontrollimine

Verify evidence arvutab brauseris uuesti akna auditi päevafailide räsiahela ja kriminalistika kirjete allkirjastatud partiiahelad ning loetleb iga lünga ja muudatuse. Partiide allkirju kontrollitakse spuulivõtmetega, mille kontoserver on iga masina jaoks kinnitanud. Tõendite sees olevat võtit ei usaldata kunagi. Tulemus templitakse eksporditud aruannetesse.

Üle 2 GiB tõendid on brauseri jaoks liiga suured. Sama moodul töötab käsurealt:

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

Käsk lõpeb koodiga 1, kui leitakse mõni lünk või muudatus. `--machine-key <machine>=<64 hex characters>` annab kataloogist väljastpoolt tuleva võtme ja seda võib korrata. Masin, millel pole välist võtit, ebaõnnestub.

## Intsidendi deklareerimine

Deklareerimine külmutab tõendid. Esmalt tehakse kontokirje ja seejärel valmistatakse hoidla uurimiseks ette:

1. Intsident registreeritakse koos selle aknaga, deklareerija ja ajaga, millal organisatsioon sellest teada sai.
2. Kõrvaldamise hoid katab akna ja ämbri lukustusreeglid laienevad sellele, nii et FIFO ei saa neid päevi eemaldada.
3. Hoidla hargitakse kriminalistilise hetktõmmisena sildiga `incident-<id>`.
4. Hoidla jäädvustustase lülitub tasemele Full.

Kolm tähtaega algavad teadasaamise hetkest, mille võib seada deklareerimisest varasemaks, kuid mitte kunagi hilisemaks: varajane hoiatus on tähtaegne 24 tundi pärast teadasaamist, teade 72 tundi pärast ning lõpparuanne üks kalendrikuu pärast teadet (loetud teate tähtajast, kuni teade on registreeritud). Leht näitab iga tähtaega kui ootel, tähtaeg 6 tunni jooksul, hilinenud või tehtud.

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

Ebaõnnestunud masinasamm jätab kirje ja selle hoiu paika, lõpeb koodiga 1 ning nimetab käsu, mis käivitab uuesti ainult ebaõnnestunud sammud:

```bash
rdc incident declare mail --resume <id>
```

`--resume` säilitab algse deklareerimise akna ja teadasaamise aja, mistõttu `--since`, `--until` ja `--aware-at` ei ole sellega kombineeritavad.

## Tõendite eksportimine

`rdc incident export` kirjutab intsidendi akna kataloogi: intsidendi kirje koos tähtaegadega, liidetud ajatelje, väljuvate baitide koondid, toore ahelamanifesti ja toored failid, mida see loetleb. Kui manifest loetleb auditi päevafaile või kriminalistika päisefaile, kontrollitakse ahelad vahepeal ja tulemus läheb faili `verification.json`. Käsk lõpeb koodiga 1, kui tõendid näitavad lünka või muudatust.

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

Lipuga `--stage` kirjutab sama käsk selle asemel allkirjastatud aruande. Vt [intsidendiaruanded](/et/docs/incident-reports).

## Intsidendi sulgemine

```bash
rdc incident close <id>
```

Midagi ei vabastata kohe. Kõrvaldamise hoid ja ämbri lukustusreeglid lõpevad 30 päeva pärast sulgemist.

## Küsi tehisintellektilt

Uurimislehel on assistent, mis vastab avatud skoobi ja akna kohta käivatele küsimustele. See loeb ainult seda skoopi ja akent, avatud uurimisest väljastatud ühekordse piletiga, mida saab sisse lunastada 15 minutit. Küsimus ja read, mida see loeb, lähevad organisatsiooni enda tehisintellekti pakkujale. Assistent võib käivitada ülaltoodud `rdc` käske samade õiguste reeglite järgi nagu iga teine käsk.

## Käsud

| Käsk | Eesmärk |
|---|---|
| `rdc repo flows <ref>` | Hoidla võrguvood aknas |
| `rdc repo opens <ref>` | Hoidla tundlike failide avamised aknas |
| `rdc forensics level <ref> <level>` | Jäädvustustaseme määramine |
| `rdc forensics verify` | Tõenditekataloogi või allkirjastatud aruande kontrollimine |
| `rdc incident declare <ref>` | Intsidendi registreerimine, hoidla hargitamine ja lülitumine tasemele Full |
| `rdc incident status [id]` | Intsidentide loetlemine või ühe näitamine koos tähtaegadega |
| `rdc incident export <id>` | Tõendiakna kirjutamine või allkirjastatud aruanne lipuga `--stage` |
| `rdc incident close <id>` | Intsidendi sulgemine |
