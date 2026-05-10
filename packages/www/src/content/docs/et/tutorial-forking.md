---
title: "Repositooriumi hargnemine"
description: "Klooni terve repositoorium (rakendus, andmebaas, failid) sekunditega. Ükskõik milline suurus. Null lisakettaruumi."
category: "Tutorials"
subcategory: advanced
order: 7
language: et
sourceHash: "9237f00dce2ee5ec"
---

# Repositooriumi forki tegemine

See on võtmetähtsusega funktsioon: klooni terve tootmiskeskkond (rakendus, andmebaas, konfiguratsioonifailid) sekunditega. Suvaline suurus. Null lisaruumi kettal. Tee forki nii palju kordi kui soovid.

Moto: **klooni tootmine, rikku mitte midagi.**

## Vaata juhendvideot

![Tutorial: Forking a repository](/assets/tutorials/tutorial-forking.cast)

## Seadista midagi kaotada

Esmalt loo töötavas rakenduses fail, et saaksid tõestada forki isolatsiooni. Ava repositoorium VS Code'is:

```bash
rdc vscode connect -m my-server -r my-app
```

Loo repositooriumi sees markerifail:

```bash
time echo "Hello from production" > index.html
```

Nüüd tee fork.

## Fork

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Parent fans out into independent clones](/img/tutorials/tutorial-forking/slide-1.svg)

Üks käsk. See kloonib kõik (rakenduse, andmebaasi, konfiguratsioonifailid) sekunditega. Käivita uuesti ja saad veel ühe sõltumatu klooni.

## Miks on see nii kiire?

![Sharing a folder link is the same speed regardless of the folder's size](/img/tutorials/tutorial-forking/slide-2.svg)

Kujuta ette kausta lingi jagamist. Link on sama olenemata sellest, kas kaust on väike või suur. Kaust on raske, link on kerge.

![1 GB, 100 GB, 1 TB. Same time, every time.](/img/tutorials/tutorial-forking/slide-3.svg)

Forki tegemine toimib samamoodi. 1 GB, 100 GB, 1 TB. Sama aeg, iga kord.

## Mis on jagatud, mis on sinu

![Many mirrors, one sun: shared base, your changes are yours](/img/tutorials/tutorial-forking/slide-4.svg)

Mõtle vanemrepositooriumist kui päikesest. Sa ei saa päikest kinni hoida, kuid saad hoida peeglit, mis seda peegeldab. See peegel on sinu fork. Maali peeglile ja sinu joonistused on sinu omad. Päike jääb samaks, olenemata sellest, kui palju peegleid selle poole vaatab.

> Sa ei saa päikest kinni hoida, kuid saad seda hoida peeglis.

## Mis juhtub, kui vanem muutub hiljem?

![A fork is a frozen photograph; the parent keeps flowing like a river](/img/tutorials/tutorial-forking/slide-5.svg)

Nüüd mõtle jõele. Vesi voolab edasi. Iga hetk on see erinev. Forki tehes teed jõest foto, mis on sellel hetkel külmutatud. Jõgi voolab edasi. Sinu foto ei voola.

Kui vanemrepositoorium muutub hiljem, jääb sinu fork sinna, kus ta oli.

> Sa ei saa jõge kinni hoida, kuid saad seda hoida fotol.

## Kettakasutus jääb tasaseks

![Five forks of a 100 GB repo, still about 100 GB total](/img/tutorials/tutorial-forking/slide-6.svg)

Seepärast sinu ketas ei plahvata. Viis forki 100 GB repositooriumist? Kokku ikka umbes 100 GB. Maksad kettaruumi ainult selle eest, mida igas forkis muudad.

> Tee fork viis korda kui soovid. Sinu ketas ei märkagi.

## Mida forkid *ei* päri: saladusi

On üks asi, mida fork tahtlikult ei järgi: saladused. Fork algab ilma API võtmete, andmebaasi paroolide ja Stripe tokeniteta. Seepärast töötab "klooni tootmine, rikku mitte midagi" tegelikkuses. Sinu liivakast ei saa reaalsetelt klientidelt arveid väljastada, sest see ei saa sind imiteerida. Seadistame selle korralikult juhendvideol [Saladuste haldamine](/en/docs/tutorial-managing-secrets).

## Kontrolli isolatsiooni

Loetlege mõlemad repositooriumid kõrvuti:

```bash
time rdc repo list -m my-server
```

Näed `my-app` ja `my-app:experiment` töötamas üheaegselt.

Algses repositooriumis kontrolli, mis töötab:

```bash
time docker ps
```

Pane tähele tööaega. Need on algsed konteinerid. Nüüd lülitu forkile:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

Samad kujutised, kuid tööaeg on värske. Need käivitusid forki tegemisel.

Tee erinevus veelgi ilmselgemaks. Lisa ainult forkile konteiner:

```bash
time docker run --rm -it -d nginx
time docker ps
```

Nginx töötab, kuid ainult selles forkis.

Proovi midagi hävitavat:

```bash
time rm index.html
```

Siin kadus. Nüüd hüppa tagasi originaalile:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

Nginxi pole. Forki konteinerid jäid forki. Ja `index.html` on siin ikka alles, puutumata. Originaal ei teadnud, et midagi juhtus. Samad kujutised, eraldi Dockeri deemonid, eraldi failisüsteemid.

## Puhastamine

Kui oled lõpetanud, kustuta lihtsalt fork:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

Originaal jääb täpselt selliseks, nagu ta oli. **Tee fork, katse, riku asju, kustuta.** Riskita.

---

Edasi: [Saladuste haldamine](/en/docs/tutorial-managing-secrets).
