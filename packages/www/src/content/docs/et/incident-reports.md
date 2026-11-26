---
title: "Intsidendiaruanded: etapiviisilised, allkirjastatud ja kontrollitavad"
description: "Koostage kliendi hoidlas toimunud intsidendi varajane hoiatus, teade ja lõpparuanne JSON-i, STIX 2.1 või PDF-vormingus. Iga aruanne on Ed25519-ga allkirjastatud, sisaldab QR-kontrollilinki ning seostab oma väljad NIS2, vormingu 2025/302 ja GDPR artikli 33 lõikega 3."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 11
language: et
sourceHash: "d7f6e084c5c1d0d9"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Intsidendiaruanded

Deklareeritud intsident ([intsidentidele reageerimine](/et/docs/incident-response)) annab kolm etapiviisilist aruannet, mille klient esitab järelevalveasutusele. Rediacc koostab dokumendid tõendite põhjal. Kas intsident on oluline või teatamisele kuuluv, jääb kliendi hinnangu küsimuseks ja iga aruanne ütleb seda.

## Etapid

Iga etapp lisab allpool loetletud sektsioonid ja kannab edasi eelmise etapi omad, nii et sektsioon, mida ükski etapp ei vaja, jäetakse välja, mitte tühjaks.

| Etapp | Tähtaeg | Lisab |
|---|---|---|
| Varajane hoiatus | 24 tundi pärast teadasaamist | Päis, ajatelg, kompromiteerimisnäitajad, kahtlustatav pahatahtlik ja piiriülene mõju |
| Teade | 72 tundi pärast teadasaamist | Esialgne hinnang, andmemõju (kategooriad, ligikaudsed arvud, liikmesriigid) ja ATT&CK tehnikad |
| Lõplik | Üks kalendrikuu pärast teadet | Algpõhjus ja leevendusmeetmed |

Lõpparuanne järgneb teatele, seega koostatakse teade esimesena.

Iga aruande fakt ütleb, kuidas seda teatakse: tõendites täheldatud, kliendi sisestatud või tuletatud. Tuletatud fakt kannab kindlust ja detektori põhjendust. Hinnang, andmekategooriad, liikmesriigid, kahtlustatav põhjus, võetud meetmed, kontaktpunkt ja tehnikad on sisendid, mille klient sisestab intsidendi lehel enne koostamist.

## Vormingud

| Vorming | Kasutus |
|---|---|
| JSON | Kanooniline, kontrollitav vorm |
| STIX 2.1 | Näitajate kimp ohuteabe tööriistade jaoks |
| PDF | Loetav dokument manustatud Noto Sansiga (ladina, kirillitsa ja türgi) või Noto Sans Arabicuga; jaapani, korea ja hiina aruanded lükatakse tagasi, kuni nende fondid on kinnitatud. Iga lehe jaluses on lahtiütlus, QR-kood ja aruande räsi |

Intsidendi lehel on igal etapil iga vormingu jaoks allalaadimisnupp. Käsurealt:

```bash
rdc incident export <id> --stage early-warning
rdc incident export <id> --stage notification --format stix
rdc incident export <id> --stage final --format pdf --out ./reports
```

Vaikevorming on JSON. `--format` kehtib ainult koos `--stage`-ga. Fail kirjutatakse oma aruande tunnuse all.

## Allkirjastamine ja kontrollimine

Iga aruanne allkirjastatakse Ed25519 aruandevõtmega ning aruande tunnus, etapp ja räsi on avalikus registris. Allkiri katab aruande kanoonilise sisu, nii et iga muudatus pärast allkirjastamist avastatakse.

Aruannet kontrollitakse kolmes kohas:

- Kontrollileht aadressil `/account/verify/report/<id>`, mille avab PDF-i QR-kood. Kontroll töötab brauseris avaldatud aruandevõtme vastu ja midagi ei laadita üles. JSON-faili kontrollitakse täielikult. PDF-i ei saa brauseris uuesti räsida, seega kinnitab leht, et PDF kannab aruande räsi, ja viitab täieliku kontrolli jaoks JSON-failile.
- Käsurida JSON-aruande jaoks:

```bash
rdc forensics verify --report ./reports/<report-id>.json
```

Käsk lõpeb koodiga 1, kui sisu või allkiri ei sobi. PDF-i kontrollitakse JSON-aruande kaudu, millest see tehti.

- Aruandesisene tõendite tempel, mis salvestab akna Verify evidence tulemuse: kes kontrollis, millise versiooniga ja millal.

## Väljade vastavus

Iga aruande väli seostatakse režiimidega, mille alusel klient teatab, nii et sisu saab üle kanda uuesti trükkimata. Vastavus hõlmab kolme režiimi: NIS2 art 23 lg 4, rakendusmääruse (EL) 2025/302 intsidenditeate vorming ja GDPR art 33 lg 3. Näited:

| Aruande väli | NIS2 | GDPR |
|---|---|---|
| Teadasaamise aeg | Art. 23(4)(a) | Art. 33(1) |
| Kronoloogia | Art. 23(4)(d) | Art. 33(3)(a) |
| Kontaktpunkt | Art. 23(4) | Art. 33(3)(b) |

Väli, millel pole režiimis vastet, ütleb põhjuse, mitte ei jää välja. GDPR art 33 lg 3 teatel pole näiteks viitenumbrit ega sulgemisaega.

## Mida aruanne ei väida

Igas etapis trükitakse kaks väidet:

- Voogude kirjed tõendavad mahtu ja sihtkohta, mitte sisu.
- Kas intsident on oluline või teatamisele kuuluv, on kliendi hinnang.

Rediacc ei esita kliendi nimel järelevalveasutusele midagi.
