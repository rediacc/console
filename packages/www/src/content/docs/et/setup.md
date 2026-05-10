---
title: "Masina ülesseadmine"
description: "Loo konfiguratsioon, lisa masinad, häälesta serverid ja konfigureeri infrastruktuur."
category: "Guides"
order: 3
language: et
---

# Masina seadistamine

See leht juhendab sind esimese masina seadistamisel: konfiguratsioonifaili loomisest serveri registreerimise, selle ettevalmistamise ja soovi korral avaliku ligipääsu infrastruktuuri konfigureerimiseni.

## 1. samm: loo konfiguratsioon

**Konfiguratsioon** on nimega konfiguratsioonifail, mis salvestab sinu SSH-mandaadid, masinate definitsioonid ja repositooriumi seosed. Mõtle sellest kui projekti tööruumist.

```bash
rdc config init --name my-infra --ssh-key ~/.ssh/id_ed25519
```

| Valik | Nõutud | Kirjeldus |
|--------|----------|-------------|
| `--ssh-key <path>` | Jah | Tee sinu SSH privaatvõtmeni. Tilde (`~`) laiendatakse automaatselt. |
| `--renet-path <path>` | Ei | Kohandatud tee renet-binaarfailini kaugmasinates. Vaikimisi kasutatakse standardset paigaldusasukohta. |

See loob konfiguratsioonifaili nimega `my-infra` ja salvestab selle asukohta `~/.config/rediacc/my-infra.json`. Vaikekonfiguratsioon (kui nime ei anta) salvestatakse failina `~/.config/rediacc/rediacc.json`.

> Sul võib olla mitu konfiguratsioonifaili (nt `production`, `staging`, `dev`). Nende vahel saab lülituda iga käsu puhul lipuga `--config`.

## 2. samm: lisa masin

Registreeri kaugserver masinana konfiguratsioonis:

```bash
rdc config machine add --name server-1 --ip 203.0.113.50 --user deploy
```

| Valik | Nõutud | Vaikeväärtus | Kirjeldus |
|--------|----------|---------|-------------|
| `--ip <address>` | Jah | - | Kaugserveri IP-aadress või hostinimi |
| `--user <username>` | Jah | - | SSH-kasutajanimi kaugserveris |
| `--port <port>` | Ei | `22` | SSH-port |
| `--datastore <path>` | Ei | `/mnt/rediacc` | Tee serveris, kuhu Rediacc salvestab krüptitud repositooriume |

Pärast masina lisamist käivitab rdc automaatselt `ssh-keyscan`, et hankida serveri hostimisvõtmed. Seda saad käivitada ka käsitsi:

```bash
rdc config machine scan-keys -m server-1
```

Kõigi registreeritud masinate vaatamiseks:

```bash
rdc config machine list
```

## 3. samm: seadista masin

Valmista kaugserver ette kõigi vajalike sõltuvustega:

```bash
rdc config machine setup --name server-1
```

See käsk:
1. Laadib renet-binaarfaili serverisse üles SFTP kaudu
2. Paigaldab Docker, containerd ja cryptsetup (kui neid pole)
3. Loob `rediacc` süsteemikasutaja (UID 7111)
4. Loob andmehoidla kataloogi ja valmistab selle ette krüptitud repositooriumide jaoks

| Valik | Nõutud | Vaikeväärtus | Kirjeldus |
|--------|----------|---------|-------------|
| `--datastore <path>` | Ei | `/mnt/rediacc` | Andmehoidla kataloog serveris |
| `--datastore-size <size>` | Ei | `95%` | Kui suur osa saadaolevast kettaruumist eraldatakse andmehoidlale |
| `--debug` | Ei | `false` | Luba tõrkeotsinguks üksikasjalik väljund |

> Seadistust on vaja käivitada iga masina kohta ainult üks kord. Vajadusel on seda ohutu uuesti käivitada.

## Hostimisvõtmete haldamine

Kui serveri SSH hostimisvõti muutub (nt pärast uuesti paigaldamist), uuenda salvestatud võtmeid:

```bash
rdc config machine scan-keys -m server-1
```

See uuendab sinu konfiguratsioonis selle masina `knownHosts` välja.

## SSH ühenduvuse testimine

Pärast masina lisamist veendu, et sellega on võimalik ühenduda:

```bash
rdc term connect -m server-1 -c "hostname"
```

See avab masinaga SSH-ühenduse ja käivitab käsu. Kui see õnnestub, on sinu SSH-konfiguratsioon korrektne.

Üksikasjalikuma diagnostika saamiseks käivita:

```bash
rdc doctor
```

> **Ainult pilveadapter**: käsk `rdc machine test-connection` pakub üksikasjalikku SSH-diagnostikat, kuid nõuab pilveadapterit. Kohaliku adapteri puhul kasuta otse `rdc term` või `ssh`.

## Infrastruktuuri konfiguratsioon

Masinate jaoks, mis peavad liiklust avalikult teenindama, konfigureeri infrastruktuuriseaded:

### Infrastruktuuri seadistamine

```bash
rdc config infra set -m server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Valik | Ulatus | Kirjeldus |
|--------|-------|-------------|
| `--public-ipv4 <ip>` | Masin | Avalik IPv4-aadress; puhverserveri sisenemispunktid luuakse ainult konfigureeritud aadressiperekondade jaoks |
| `--public-ipv6 <ip>` | Masin | Avalik IPv6-aadress; puhverserveri sisenemispunktid luuakse ainult konfigureeritud aadressiperekondade jaoks |
| `--base-domain <domain>` | Masin | Rakenduste alusdomeen (nt `example.com`) |
| `--cert-email <email>` | Konfiguratsioon | E-post Let's Encrypt TLS-sertifikaatide jaoks (jagatud masinate vahel) |
| `--cf-dns-token <token>` | Konfiguratsioon | Cloudflare DNS-i API token ACME DNS-01 väljakutsete jaoks (jagatud masinate vahel) |
| `--tcp-ports <ports>` | Masin | Komaga eraldatud lisatavad TCP-pordid edasisaatmiseks (nt `25,143,465,587,993`) |
| `--udp-ports <ports>` | Masin | Komaga eraldatud lisatavad UDP-pordid edasisaatmiseks (nt `53`) |

Masina ulatusega valikud salvestatakse iga masina kohta eraldi. Konfiguratsiooni ulatusega valikud (`--cert-email`, `--cf-dns-token`) on jagatud kõigi konfiguratsiooni masinate vahel; seadista need üks kord ja need kehtivad kõikjal.

### Infrastruktuuri vaatamine

```bash
rdc config infra show -m server-1
```

### Serverisse lükkamine

Genereeri ja rakenda Traefiki pöördpuhverserveri konfiguratsioon serverisse:

```bash
rdc config infra push -m server-1
```

See käsk:
1. Rakendab renet-binaarfaili kaugmasinasse
2. Konfigureerib Traefiki pöördpuhverserveri, ruuteri ja systemd-teenused
3. Loob Cloudflare'i DNS-kirjed masina alamdomeeni jaoks (`server-1.example.com` ja `*.server-1.example.com`), kui `--cf-dns-token` on seadistatud

DNS-samm on automaatne ja idempotentne: see loob puuduvad kirjed, uuendab muutunud IP-dega kirjeid ja jätab juba korrektse olekuga kirjed vahele. Kui Cloudflare'i tokenit pole seadistatud, jäetakse DNS vahele koos hoiatusega. Repositooriumipõhised metamärgi DNS-kirjed (automaatmarsruutide jaoks) luuakse automaatselt, kui käivitad `rdc repo up`.

## Pilveettevalmistamine

Selle asemel et luua VM-e käsitsi, saad konfigureerida pilvepakkuja ja lasta `rdc`-l masinaid automaatselt ette valmistada [OpenTofu](https://opentofu.org/) abil.

### Eeltingimused

Paigalda OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Veendu, et sinu SSH-konfiguratsioonis on `rdc`-ga registreeritud võti:

```bash
# Loeb võtmefaili ja lisab sisu /credentials/ssh alla.
rdc config ssh set --key ~/.ssh/id_ed25519
```

### Pilvepakkuja lisamine

```bash
rdc config provider add --name my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| Valik | Nõutud | Kirjeldus |
|--------|----------|-------------|
| `--provider <source>` | Jah* | Tuntud pakkuja allikas (nt `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Jah* | Kohandatud OpenTofu pakkuja allikas (tundmatute pakkujate jaoks) |
| `--token <token>` | Jah | Pilvepakkuja API token |
| `--region <region>` | Ei | Uute masinate vaikeregioon |
| `--type <type>` | Ei | Vaikimisi eksemplari tüüp/suurus |
| `--image <image>` | Ei | Vaikimisi operatsioonisüsteemi kujutis |
| `--ssh-user <user>` | Ei | SSH-kasutajanimi (vaikimisi: `root`) |

\* Nõutud on kas `--provider` või `--source`. Kasuta `--provider` tuntud pakkujate jaoks (sisseehitatud vaikeväärtused). Kasuta `--source` koos lisalippudega `--resource`, `--ipv4-output`, `--ssh-key-attr` kohandatud pakkujate jaoks.

### Masina ettevalmistamine

```bash
rdc machine provision --name prod-2 --provider my-linode
```

See üks käsk:
1. Loob VM-i pilvepakkujas OpenTofu kaudu
2. Ootab SSH-ühenduvust
3. Registreerib masina sinu konfiguratsioonis
4. Paigaldab reneti ja kõik sõltuvused
5. Konfigureerib Traefiki puhverserveri ja Cloudflare'i DNS-i (tuvastab automaatselt alusdomeeni kõrvalmasinatest või kasuta `--base-domain` otse)

| Valik | Kirjeldus |
|--------|-------------|
| `--provider <name>` | Pilvepakkuja nimi (allikast `add-provider`) |
| `--region <region>` | Asenda pakkuja vaikeregioon |
| `--type <type>` | Asenda vaikimisi eksemplari tüüp |
| `--image <image>` | Asenda vaikimisi operatsioonisüsteemi kujutis |
| `--base-domain <domain>` | Infrastruktuuri alusdomeen. Tuvastab automaatselt kõrvalmasinatest, kui pole määratud |
| `--no-infra` | Jäta infrastruktuuri konfiguratsioon (puhverserver ja DNS) täielikult vahele |
| `--debug` | Näita üksikasjalikku ettevalmistuse väljundit |

### Masina ettevalmistuse tühistamine

```bash
rdc machine deprovision --name prod-2
```

Hävitab VM-i OpenTofu kaudu ja eemaldab selle sinu konfiguratsioonist. Nõuab kinnitust, välja arvatud juhul kui kasutatakse `--force`. Töötab ainult masinatega, mis on loodud käsuga `machine provision`.

### Pakkujate loetlemine

```bash
rdc config provider list
```

## Vaikeväärtuste seadistamine

Seadista vaikeväärtused, et neid poleks vaja igal käsul täpsustada:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Vaikemasin
rdc config set --key team --value my-team                   # Vaikemeeskond (pilveadapter, eksperimentaalne)
```

Pärast vaikemaskina seadistamist saad käskudest `-m server-1` ära jätta:

```bash
rdc repo create --name my-app -m my-server --size 10G
```

## Mitu konfiguratsiooni

Halda mitut keskkonda nimega konfiguratsioonifailidega:

```bash
# Loo eraldi konfiguratsioonid
rdc config init --name production --ssh-key ~/.ssh/id_prod
rdc config init --name staging --ssh-key ~/.ssh/id_staging

# Kasuta konkreetset konfiguratsiooni
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

Kõigi konfiguratsioonide vaatamine:

```bash
rdc config list
```

Praeguse konfiguratsiooni üksikasjade kuvamine:

```bash
rdc config show
```
