---
title: "Paigaldamine"
description: "Paigalda rdc CLI oma sülearvutisse ühe käsuga ja kontrolli seda käsuga rdc doctor."
category: "Tutorials"
subcategory: essentials
order: 1
language: et
sourceHash: "99d4ca1a4f89278e"
---

# Paigaldamine

`rdc` paigaldamine koosneb kolmest sammust: ava paigaldusleht, vali oma operatsioonisüsteem, kleebi käsk terminali. Kogu protsess võtab tavaliselt ühe kuni kaks minutit.

## Vaata juhendvideot

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## Kolm sammu

![Three steps overview](/img/tutorials/tutorial-installation/slide-1.svg)

1. Ava [paigaldusleht](/en/install).
2. Vali oma operatsioonisüsteem.
3. Kopeeri paigalduskäsk ja kleebi see terminali.

## Paigaldamine oma platvormile

Paigaldusleht genereerib sulle sobiva käsu automaatselt, kuid siin on kanooniline üherealised.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> Eesliide `time` on shellitriks, mis näitab, kaua käsu täitmine aega võttis. Kasutame seda kogu selles sarjas, et näidata iga sammu tegelikku kiirust. See on valikuline. Jäta see välja, kui sa seda ei soovi.

## Paigalduse kontrollimine

Kui skript on lõpetanud, kontrolli, et kõik `rdc` vajatav on olemas:

```bash
time rdc doctor
```

`rdc doctor` kontrollib Node'i, SSH-d ja ülejäänud `rdc` sõltuvusi ning teatab puuduvatest komponentidest.

## Miks `rdc` asub sinu sülearvutis

![rdc on your laptop, renet on the server](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` on CLI sinu sülearvutis. Server käitab eraldi komponenti nimega `renet`, mida `rdc` ettevalmistab ja juhib üle SSH. Sul ei ole kunagi vaja käsitsi serverisse SSH kaudu ühenduda. `rdc` teeb seda sinu eest.

Seadistame selle korralikult järgmises kahes juhendvideoas.

---

Edasi: [SSH võtme seadistamine](/en/docs/tutorial-ssh-keys).
