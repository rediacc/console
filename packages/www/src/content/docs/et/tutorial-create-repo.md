---
title: "Esimese repositooriumi loomine"
description: "Loo serverile krüpteeritud repositoorium ja ava see VS Code'is."
category: "Tutorials"
subcategory: essentials
order: 4
language: et
sourceHash: "1294b0494f20671b"
---

# Esimese repositooriumi loomine

Rediacc repositoorium on üksik krüpteeritud fail sinu serveris. Ühendamisel muutub see kaustaks, millel on oma Dockeri deemon ja oma rakenduse andmed: täielikult isoleeritud, täielikult teisaldatav.

Mõtle sellele kui tootmiskeskkonna USB-mälupulgale: puhkeolekus on see fail, käivitamisel server.

## Vaata juhendvideot

![Tutorial: Creating your first repository](/assets/tutorials/tutorial-create-repo.cast)

## Kettale kirjutatud fail, ühendamisel keskkond

![Encrypted file mounts as an isolated folder](/img/tutorials/tutorial-create-repo/slide-1.svg)

Kettale kirjutatud kujul on see üksik krüpteeritud kujutis. Ühendamisel saad:

- Pühendatud Dockeri deemoni (eraldi hosti omast)
- Rakenduse andmed krüpteeritud mahus
- Loopback IP-d, mis ei põrku serveri millegi muuga

Repositooriumid on teisaldatavad. Saad neid masinate vahel liigutada, varundada või koheselt forki teha. Iga repositoorium on isoleeritud kõigist teistest repositooriumitest samal serveril.

## Loo repositoorium

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

See loob 2 GB krüpteeritud repositooriumi `my-server`-is. Kontrolli seda:

```bash
time rdc repo list -m my-server
```

## Ava see VS Code'is

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code avaneb otse repositooriumi sees. Pane tähele, et tööruum on tühi. See on sinu isoleeritud keskkond. Kõik, mida siin lood, asub krüpteeritud mahus ja on nähtamatu kõigile teistele repositooriumidele samal serveril.

---

Edasi: [Esimese rakenduse juurutamine](/en/docs/tutorial-deploy-app).
