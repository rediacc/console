---
title: "Automaatkäivitus ja taastamine"
description: "Kuidas automaatkäivitus toimib, perioodiline leppija, mis taastab pärast käivitamist seiskunud repositooriumeid, ning kuidas kontrollida taastamisolekut."
category: "Guides"
order: 5
language: et
sourceHash: "a009cfabc7240d87"
---

# Automaatkäivitus ja taastamine

See leht selgitab, kuidas repositooriumid käivitamisel automaatselt ühendatakse ja käivitatakse, ning kuidas perioodiline leppija toob repositooriumi taas üles, kui see langeb pärast serveri käivitamist.

Automaatkäivituse lubamiseks või keelamiseks repositooriumil vt [Teenused — Automaatkäivitus käivitamisel](/et/docs/services#autostart-on-boot).

## Kuidas automaatkäivitus toimib

Kui lubate repositooriumil automaatkäivituse, genereerib Rediacc 256-baidise juhusliku LUKS-võtmefaili ja lisab selle krüpteeritud köite LUKS-pesale 1. Võtmefail talletatakse asukohta:

```
{datastore}/.credentials/keys/{guid}.key
```

See võimaldab masinal repositooriumit parooli küsimata ühendada. LUKS-pesa 0 (teie parool) ei muutu.

Käivitamisel loeb ühekorraline systemd-teenus `rediacc-autostart.service` automaatkäivitusega repositooriumite loendi, ühendab igaühe oma võtmefaili abil, käivitab repositooriumi kohase Dockeri deemoni ja käivitab Rediaccfile'i `up()` konktsu. Seiskamisel käivitab teenus `down()`, peatab Dockeri ja sulgeb LUKS-köited.

> **Turvahoiatus:** Võtmefail annab repositooriumile juuritaseme juurdepääsu ilma paroolita. Kõigil, kellel on serverile juuripääs, on võimalik automaatkäivitusega repositooriumeid ühendada. Hinnake seda oma ohumudeli alusel enne automaatkäivituse lubamist tundlikel repositooriumitel.

## Taastamislõhe

Käivitamisel toimuv automaatkäivitus töötab täpselt üks kord käivituse kohta. Ruuteri valvekoer, mis töötab pidevalt pärast seda, taaskäivitab ainult *konteinereid juba töötavas, ühendatud repositooriumis, millel on töötav Dockeri deemon*. See ei suuda remonteerida LUKS-köidet ega taaskäivitada võrgu-kohast Dockeri deemonit, mis on peatunud.

See tähendab, et kui repositooriumi LUKS-köide lahutatakse või selle Dockeri deemon peatub pärast serveri käivitamist, ei taastu see ei käivitusteenuse ega valvekoera kaudu. Enne leppija olemasolu jäi selline repositoorium seisku kuni operaatori sekkumiseni.

## Perioodiline leppija

Systemd-taimer `rediacc-autostart-reconcile.timer` käivitub ligikaudu iga 3 minuti järel ja käivitab `renet repository reconcile`. Iga automaatkäivitusega repositooriumi puhul kontrollib leppija kolme asja:

1. Kas LUKS-köide on ühendatud?
2. Kas võrgu-kohane Dockeri deemon töötab?
3. Kas repositooriumi teenused on üleval?

Kui mõni kontroll ebaõnnestub, taastab leppija repositooriumi võtmefaili abil: ühendab köite, käivitab Dockeri deemoni ja käivitab `up()`. Parooli ei ole vaja.

Terved repositooriumid, mis on hetkel külma varukoopia käivitamise kasutuses või oma tagasilükkamise aknas, jäetakse vahele.

### Tagasilükkamine ja püsivad tõrkemarkerid

Repositoorium, mille taastamine ebaõnnestub, ei katse kohe igal tiktakil uuesti. Leppija kasutab eksponentsiaalset tagasilükkamist:

| Tõrgete arv | Ooteaeg enne järgmist katset |
|-------------|------------------------------|
| 1 | 1 minut |
| 2 | 2 minutit |
| 3 | 5 minutit |
| 4 | 15 minutit |
| 5+ | 30 minutit, seejärel 60 minutit |

Pärast 5 järjestikust tõrget kirjutab leppija püsiva markerfaili asukohta:

```
/var/lib/rediacc/reconcile/failed/{guid}
```

See fail jääb püsima pärast logide rotatsiooni. Selle olemasolu tähendab, et repositoorium vajab operaatori tähelepanu. Leppija logib tõrke veatasemele ja lõpetab selle repositooriumi automaatse taastamise katsed kuni markeri kustutamiseni.

Püsiva taastumisetõrke levinud põhjused:

- **Ebausaldusväärsed või aegunud repositooriumi litsents** — litsentsi kontroll töötab enne `up()`.
- **Puuduv võtmefail** — kui võtmefail asukohas `{datastore}/.credentials/keys/{guid}.key` on kustutatud, ei saa leppija köidet ilma paroolita ühendada.
- **Katkine Rediaccfile** — süntaksiviga või `up()` konks, mis lõpetab alati nullist erineva koodiga.

### Seos ruuteri valvekoeraga

Leppija ja ruuteri valvekoer käsitlevad erinevaid tõrketasemeid ning on loodud üksteist täiendama:

| Kiht | Mida käsitleb |
|------|---------------|
| **Ruuteri valvekoer** | Konteineritaseme taaskäivitused töötavas, ühendatud repositooriumis, millel on aktiivne Dockeri deemon |
| **Leppija (`rediacc-autostart-reconcile.timer`)** | Repositooriumitaseme taastamine: LUKS-i remontaaž, Dockeri deemoni taaskäivitamine, `up()` uuesti käivitamine |

Kui üks konteiner jookseb kokku tervislikus repositooriumis, käsitleb seda valvekoer. Kui kogu repositooriumi deemon peatub, käsitleb seda leppija.

## Taastamisoleku kontrollimine

### Taimeri ja teenuse olek

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### Leppija logid

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### Püsivad tõrkemarkerid

Loetlege püsivate tõrkemarkritega repositooriumid:

```bash
ls /var/lib/rediacc/reconcile/failed/
```

Iga failinimi on repositooriumi GUID. Kasutage `rdc config repository list` GUIDide kaardistamiseks repositooriuminimedeks.

Markeri kustutamiseks pärast aluspõhjuse lahendamist kustutage fail:

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

Leppija katsub taastamist uuesti järgmisel taimeri tiktakil.

## Seotud lehed

- [Teenused — Automaatkäivitus käivitamisel](/et/docs/services#autostart-on-boot) — automaatkäivituse lubamine ja keelamine, võtmefaili haldamine
- [Varundamine ja taastamine](/et/docs/backup-restore) — külma varukoopia koostoime töötavate teenustega
