---
title: "Varukoopia ja taastamine"
description: "Tõuka repositoorium välismällu ja taasta see uuel serveril vajaduse korral."
category: "Tutorials"
subcategory: advanced
order: 11
language: et
sourceHash: "8b48f3b19352aebe"
---

# Varukoopia ja taastamine

Sinu rakendus on tootmises elus. Veendu nüüd, et sa ei kaota seda kunagi. `rdc` suudab tõugata sinu terve repositooriumi (rakendus, andmebaas, failid, konfiguratsioonid) välismällu ja tõmmata selle igal ajal tagasi. Jää ellu lunavara, riistvara rikke ja kõige muu korral.

## Vaata juhendvideot

![Tutorial: Backup and restore](/assets/tutorials/tutorial-backup-restore.cast)

## Kolm sammu

![Configure, push, restore](/img/tutorials/tutorial-backup-restore/slide-1.svg)

1. **Seadista** salvestusteenuse pakkuja.
2. **Tõuka** varukoopia.
3. **Taasta** vajaduse korral.

## 1. samm: seadista salvestus

Sul on vaja `rclone` konfiguratsioonifaili. Kui kasutad juba rclone'i, impordi see otse:

```bash
time rdc config storage import --file rclone.conf
```

See toetab S3, B2, Google Drive, Dropbox ja paljusid teisi. Kontrolli, mis on seadistatud:

```bash
time rdc config storage list
```

## 2. samm: tõuka varukoopia

```bash
time rdc repo push --name my-app -m my-server --to my-storage
```

Sinu terve repositoorium (rakendus, andmebaas, failid, kõik) on nüüd varundatud. Kuna repositoorium ise on krüpteeritud, on ka varukoopia krüpteeritud. Lisavõtme haldamine pole vajalik.

Vaata oma varukoopiad igal ajal:

```bash
time rdc repo backup list --from my-storage -m my-server
```

## Miks puudub seisakuaeg?

Rakendus jätkab tööd varukoopia üleslaadimise ajal. Kuidas on see järjepidev?

Sama loogika nagu [forkiga](/en/docs/tutorial-forking). `rdc` teeb esmalt forki, seejärel laadib forki üles. Fork talletab hetke; sinu elus rakendus jätkab tööd. Seisakuaeg puudub, vastuolud puuduvad.

## 3. samm: taasta uuel serveril

Oletame, et sinu server sureb. Seadista uus server, lisa see `rdc`-sse ja tõmba:

```bash
time rdc repo pull --name my-app -m new-server --from my-storage
```

Seejärel käivita see:

```bash
time rdc repo up --name my-app -m new-server
```

Sinu rakendus on tagasi. Samad andmed, samad konteinerid, erinev masin.

## Kiiremad varukoopiad: masinast masinasse

Saad ka tõugata otse masinate vahel, ilma pilvsalvestuseta vahel:

```bash
time rdc repo push --name my-app -m my-server --to-machine backup-server
```

> **Nõuanne.** Salvestuse üleslaadimised saadavad alati kõik. Masinast masinasse saadab ainult erinevuse. Esimene masinast masinasse tõuge võtab tavapärase aja, kuid iga järgmine on palju kiirem. Suurepärane sagedaste varukoopiate jaoks.

---

Edasi: [Monitoorimine](/en/docs/tutorial-monitoring).
