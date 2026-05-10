---
title: "Saladuste haldamine"
description: "Pane juurutusaegne mandaat kohta, kuhu forkid ei pääse. Kirjutamiseks mõeldud kujunduse järgi."
category: "Tutorials"
subcategory: advanced
order: 8
language: et
sourceHash: "0b4d72c80b489e12"
---

# Saladuste haldamine

Tõelistel rakendustel on vaja tõelisi mandaate: Stripe'i live-võti, andmebaasi parool, API token. Vale koht nende panemiseks on repositoorium, sest fork pärib kõike, mis on krüpteeritud kujutise sees. Äkki võtab sinu liivakast reaalsetelt klientidelt raha.

Õige koht on `rdc repo secret`. Kaks edastusrežiimi, kirjutamiseks mõeldud kujunduse järgi ja fork algab tühiselt.

## Vaata juhendvideot

![Tutorial: Managing secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## Lõks: `.env` repositooriumis

![A .env file inside the repo image gets cloned by every fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

Enamik tiime paneb `.env` repositooriumisse. See on ilmne samm.

Siis teevad nad forki.

Fork on baidi haaval koopia vanemkujutisest. Mis iganes on `.env`-s, on ka forki `.env`-s. Forki konteinerid käivituvad. Need loevad sama Stripe'i võtit. Need kutsuvad sama Stripe'i API-t tootmise mandaatidega. Stripe'i vaatepunktist on see kõne *sina*.

See on halb päev.

## Seadista saladus

Lahendus on `rdc repo secret`. Seadista üks `env`-režiimis. See jõuab konteineris keskkondmuutujana:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Kaks asja, mida märgata:

- `--mode env`. Väärtus jõuab keskkondmuutujana.
- `--current ""`. Tühi string. Deklareerime, et see on täiesti uus saladus ilma eelneva väärtuseta.

Seadista teine, `file`-režiimis, kõige tundliku jaoks:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

`file`-režiim ei pane väärtust kunagi konteineri keskkonda. See kirjutab selle hoopis faili `/run/secrets/stripe_key`, kasutades Dockeri standardmehhanismi.

Loetlege, mis sul on:

```bash
time rdc repo secret list --name my-app
```

Näed nimesid ja režiime. **Mitte väärtusi.** Loend ei näita kunagi väärtusi.

## Ühenda compose'iga

Ava `docker-compose.yml`. Viita mõlemale režiimile:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

`${REDIACC_SECRET_DB_HOST}` on `env`-režiim: `renet`-i compose-ümbris laiendab seda sinu saladuste hoidlast juurutusajal.

`secrets:`-blokk on `file`-režiim, kasutades Dockeri standardmehhanismi. Hosti tee kasutab `${REDIACC_NETWORK_ID}`, et sama compose töötaks nii vanemate kui forkide puhul. Igal forkil on oma võrgu ID.

Juuruta:

```bash
time rdc repo up --name my-app -m my-server
```

## Kontrolli konteineris

Mõlemad režiimid peaksid nüüd konteineris olemas olema. Kontrolli env-režiimi saladust:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`. Env-režiimi saladus jõudis konteineri keskkonda.

Nüüd file-režiimi oma:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`. Fail on ühendatud Dockeri standardsete saladuste mehhanismi kaudu.

## Sa ei saa seda kunagi tagasi lugeda

![Write-only model: get returns a digest, never the value](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Nüüd osa, mis inimesi üllatab:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

Saad räsi. **Mitte väärtuse.** Puudub lipp, mis paneks selle väärtuse tagastama. Puudub käsk, mis annaks sulle lihtteksti tagasi.

See on GitHub Actionsi mudel: ainult kirjutamiseks. Saad tõestada, et tead, mis saladus on, andes `--current <väärtus>` ja vaadates eeltingimuse läbimist. Sa ei saa paluda Rediaccil sulle öelda, mis see on.

Väärtus kadunud? **Ära piilu. Roteeeri.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` jätab eeltingimuse vahele. Auditilogi märgib selle rotatsioonina: kõva, tahtlik.

Kui mäletad vana väärtust, tõesta seda hoopis:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

See on turvalisem tee. See tabab "olen vales terminalis" vea.

## Forki lõppmäng

![After fork, the secrets list is empty](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

Mäletad lõksu? Tee repositooriumist fork ja vaata:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Tühi.**

Forkil pole Stripe'i võtit. Andmebaasi parooli pole. API tokenit pole. Forki konteinerid ei saa interpoleerida `${REDIACC_SECRET_STRIPE_KEY}`. Faili asukohas `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` ei ole olemas.

Fork ei saa sind imiteerida.

Kui soovid saladusi forkis testimiseks, seadista need forkile selgelt liivakasti väärtustega:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Nüüd suhtleb fork Stripe'i liivakastiga. Tootmise mandaadid ei lahkunud kunagi tootmisest.

## Kokkuvõte

- `rdc repo secret` paneb sinu mandaadid väljapoole repositooriumi kujutist.
- Fork ei pääse neile ligi.
- `get` tagastab räsi, mitte kunagi väärtuse.
- Roteeeri, kui unustad. Ära piilu.

Saladused, mida fork ei saa järgida.

---

Edasi: [Võrgustik ja domeenid](/en/docs/tutorial-networking).
