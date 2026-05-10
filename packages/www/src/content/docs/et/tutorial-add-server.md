---
title: "Esimese serveri lisamine"
description: "Registreeri oma esimene server rdc-s, valmista see ette ja mõista rdc + renet arhitektuuri."
category: "Tutorials"
subcategory: essentials
order: 3
language: et
sourceHash: "2b5de59f61cfb88c"
---

# Esimese serveri lisamine

Enne serveri lisamist on kasulik mõista, kuidas `rdc` töötab. Rediaccil on kahe tööriistaga arhitektuur: `rdc` sinu sülearvutis ja `renet` serveris.

## Vaata juhendvideot

![Tutorial: Adding your first server](/assets/tutorials/tutorial-add-server.cast)

## Miks kaks tööriista?

![rdc on laptop, renet on server, SSH between](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** on CLI sinu sülearvutis. Siin sisestad käsud.
- **`renet`** on orkestreerimistööriist serveris. See haldab krüpteerimist, Dockerit ja isolatsiooni.

Kui käivitad käsu kohalikult, ühendub `rdc` üle SSH ja täidab `renet`-i serveris. Sa ei pea kunagi käsitsi serverisse SSH kaudu ühenduma. `rdc` teeb seda sinu eest.

## 1. samm: registreeri server

Teavita `rdc`-d serverist. Asenda nimi, IP ja kasutajanimi enda omaga.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## 2. samm: valmista see ette

Seadistus paigaldab `renet`-i ja loob serverile krüpteeritud andmehoidla.

```bash
time rdc config machine setup --name my-server
```

Kui see on lõpetanud, on sinu server repositooriumite majutamiseks valmis.

## Kus konfiguratsioon asub

Kontrolli, mida `rdc` sinu seadistuse kohta teab:

```bash
time rdc config show
```

Või ava JSON-fail otse:

```bash
vim ~/.config/rediacc/rediacc.json
```

See üksik fail sisaldab kõike: masinaid, repositooriume, SSH võtit ja krüpteerimise mandaate. Kopeeri see teisele sülearvutile ja oled sealt kohe töövalmis.

---

Edasi: [Esimese repositooriumi loomine](/en/docs/tutorial-create-repo).
