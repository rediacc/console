---
title: "Tootmisrežiim"
description: "Käita rakendust sülearvutist eraldatult ja jää ellu serveri taaskäivituste korral autostart-i abil."
category: "Tutorials"
subcategory: advanced
order: 10
language: et
sourceHash: "0e070fcd877900ab"
---

# Tootmisrežiim

Seni oled rakendust käitanud `renet dev up` abil repositooriumi seest. See sobib suurepäraselt arendustöö jaoks. Tootmises haldad kõike sülearvutist `rdc`-ga. Sulge sülearvuti ja rakendus jätkab tööd.

## Vaata juhendvideot

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## Arendus vs tootmine

Erinevus on lihtne:

- `renet dev up` töötab **repositooriumi sees**. Peab olema ühendatud.
- `rdc repo up` töötab **sinu sülearvutist**. Pärast seda pole ühendust vaja.

Kolm toimingut viivad sind arendusest tootmiseni:

![Stop, start, autostart](/img/tutorials/tutorial-production-mode/slide-1.svg)

## 1. samm: peata arendusseanss

Ühenda repositooriumiga ja lõpeta töö:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## 2. samm: käivita tootmisrežiimis

Oma sülearvuti terminalist:

```bash
time rdc repo up --name my-app -m my-server
```

See ongi kõik. Sinu rakendus töötab ja saad sülearvuti sulgeda. `Rediaccfile` haldab kõike. `rdc repo up` kutsub sama `up` funktsiooni, mida `renet dev up` kasutas. Sama `Rediaccfile`, erinev käivitusviis.

## 3. samm: jää ellu serveri taaskäivituste korral

Veendu, et sinu rakendus tuleb serveri taaskäivitumisel automaatselt tagasi:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Kontrolli, millel repositooriumidel on autostart lubatud:

```bash
time rdc repo autostart list -m my-server
```

## Peatamine tootmises

Kui pead rakenduse peatama:

```bash
time rdc repo down --name my-app -m my-server
```

Üks käsk üles, üks käsk alla. Kõik sülearvutist.

---

Edasi: [Varukoopia ja taastamine](/en/docs/tutorial-backup-restore).
