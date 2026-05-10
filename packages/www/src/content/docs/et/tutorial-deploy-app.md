---
title: "Esimese rakenduse käivitamine"
description: "Käivita konteineriseeritud rakendus sisseehitatud malli abil, kasutades renet dev up."
category: "Tutorials"
subcategory: essentials
order: 5
language: et
sourceHash: "f75b5b6a716e94bf"
---

# Esimese rakenduse juurutamine

Sul on tühi repositoorium. `rdc` sisaldab sisseehitatud malle, et saaksid tõelisi rakendusi käivitada ilma `docker-compose`-i nullist kirjutamata. Kolm sammu: vali mall, rakenda see, käivita.

## Vaata juhendvideot

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## Vali · Rakenda · Käivita

![Pick a template, apply it, run it](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## 1. samm: vali

Sirvige saadaolevaid malle:

```bash
time rdc repo template list
```

Näed valmis seadistusi levinud rakendustele: Postgres, Redis, veebiserverid ja palju muud.

## 2. samm: rakenda

Lisa mall oma repositooriumisse. Kasutame `app-postgres`:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

Repositooriumis ilmub kaks uut faili: `docker-compose.yml` ja `Rediaccfile`. Compose-fail kirjeldab konteinereid; `Rediaccfile` määrab, mis juhtub rakenduse käivitumisel ja peatamisel (selle `up`- ja `down`-elutsükli konksud).

## 3. samm: käivita

Oled juba repositooriumi liivakastis (eelmise juhendvideo VS Code ühenduse kaudu), seega kasuta `renet`-i otse:

```bash
time renet dev up
```

See ongi kõik. Sinu rakendus töötab. Kontrolli seda:

```bash
time docker ps
```

`docker ps` loetleb siin ainult selle repositooriumi konteinerid. Teistel repositooriumidel samal serveril on oma Dockeri deemonid ja need on siit täielikult nähtamatud.

---

Edasi: [Repositooriumiga töötamine](/en/docs/tutorial-work-with-repo).
