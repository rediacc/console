---
title: "Repositooriumiga töötamine"
description: "Tunnelda port brauserisse, käivita käske liivakastis ja sünkroniseeri faile sülearvuti ja repositooriumi vahel."
category: "Tutorials"
subcategory: essentials
order: 6
language: et
sourceHash: "3d56eb69e72c1a5a"
---

# Repositooriumiga töötamine

Sinu rakendus töötab, kuid seni oled seda näinud ainult läbi `docker ps`. Kolm käsku katavad igapäevase töövoo: **tunnel** rakenduse vaatamiseks brauseris, **term** käskude käivitamiseks liivakastis ja **sync** failide liigutamiseks sülearvuti ja repositooriumi vahel.

## Vaata juhendvideot

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## Igapäevased kolm

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: ava rakendus brauseris.
2. **Term**: käivita käsk liivakastis.
3. **Sync**: liiguta faile sisse ja välja.

## Tunnel: vaata rakendust brauseris

Rakendus töötab serveris, mitte sinu sülearvutis. Suuna konteineri port üle SSH:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Ava `localhost` brauseris. Sinu rakendus on kohe seal. Vajuta `Ctrl+C`, kui oled lõpetanud.

Teise konteineri jaoks vaheta `-c` välja ja vali port:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: käivita käske repositooriumi sees

Jäta VS Code vahele, kui vajad lihtsalt shelli:

```bash
rdc term connect -m my-server -r my-app
```

Oled nüüd repositooriumi liivakastis. Proovi seda:

```bash
time docker ps
```

Näed ainult `my-app` konteinereid, sama vaadet, mida näeksid VS Code'is.

Ühekordseteks käskudeks kasuta `-c` ja jäta interaktiivne shell vahele:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: liiguta faile sülearvuti ja repositooriumi vahel

Tõuka kaust sülearvutist repositooriumisse:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Tõmba failid tagasi:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Kui oled ebakindel, vaata esmalt eelvaadet. `--dry-run` näitab, mis muutuks, ilma midagi tegelikult kopeerimata:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Kolm käsku katavad igapäevase tsükli.

---

Edasi: [Repositooriumi forki tegemine](/en/docs/tutorial-forking).
