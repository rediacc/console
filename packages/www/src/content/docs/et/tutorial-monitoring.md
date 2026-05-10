---
title: "Monitoorimine"
description: "Kontrolli oma serverite ja repositooriumide tervist sülearvutist rdc machine käskudega."
category: "Tutorials"
subcategory: advanced
order: 12
language: et
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# Monitoorimine

Sinu rakendus on juurutatud, elus ja varundatud. Veendu nüüd, et kõik jääb terveks. `rdc` annab sulle täieliku ülevaate igast serverist (tervis, konteinerid, repositooriumid) sinu sülearvutist.

## Vaata juhendvideot

![Tutorial: Monitoring](/assets/tutorials/tutorial-monitoring.cast)

## Kolm asja, mida saad kontrollida

![Health, containers, repos](/img/tutorials/tutorial-monitoring/slide-1.svg)

## Tervis: süsteemiteave

Alusta süsteemivaatega:

```bash
time rdc machine query --name my-server --system
```

See näitab süsteemi tööaega, kettakasutust ja salvestuse olekut. Kui midagi on valesti, räägib see sulle.

## Konteinerid

Kõigi töötavate konteinerite vaatamiseks kõigis masina repositooriumides:

```bash
time rdc machine query --name my-server --containers
```

Saad iga konteineri nime, oleku, tervise, CPU ja mälu, lisaks sellele, millisele repositooriumile see kuulub.

## Repositooriumid

Oma repositooriumide kontrollimiseks:

```bash
time rdc machine query --name my-server --repositories
```

See näitab iga repositooriumit selle suuruse, ühendamise oleku, Dockeri oleku ja kettakasutusega.

## Kõik korraga

```bash
time rdc machine query --name my-server
```

Süsteemiteave, repositooriumid, konteinerid, kõik ühes käsus. Sama `query` käsk ilma filtriteta tagastab täieliku pildi; koos `--system`, `--containers`, `--repositories`, `--services`, `--network` või `--block-devices` piirab see ainult selle jaotiseni.

## Kohalik tervise kontroll

`rdc doctor` kontrollib sinu kohalikku seadistust (Node, SSH võti, `renet`, Docker), sõltumatult konkreetsest serverist:

```bash
time rdc doctor
```

## Oled valmis

See on terve sari. Saad nüüd paigaldada, seadistada, juurutada, teha forke, minna ellu, seadistada autostarti, varundada ja monitoorida. Kõik oma terminalist, kõik oma serveritel.
