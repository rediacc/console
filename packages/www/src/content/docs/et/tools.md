---
title: "Tööriistad"
description: "Failide sünkroonimine, terminali ligipääs, VS Code integratsioon ja CLI uuendused."
category: "Guides"
order: 9
language: et
sourceHash: "59abc2faa1157369"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# Tööriistad

Rediacc sisaldab nelja tööriista igapäevaseks tööks oma masinate ja repositooriumidega: failide sünkroonimine SSH üle, SSH-terminal, VS Code integratsioon ja CLI uuendused. Kõik neli töötavad SSH üle. Kaugmasinale ei pea installima agenti ega deemooni. Kui soovid graafilist kasutajaliidest, siis vaata teisele leheküljele.

## Failide sünkroonimine (sync)

Edasta faile oma tööjaama ja kaugrepositooriumi vahel, kasutades rsync üle SSH.

### Failide üleslaadimine

`--local` võtab vastu ühe või mitu teed. Iga tee võib olla fail või kataloog. Failid jõuavad asukohta `<remote>/<basename>`; kataloogi sisu ühineb asukohaga `<remote>/`. Ühe faili puhul eelista `--remote-file`, et määrata failile sihtkoha tee otsesõnu.

```bash
# Kataloog (sisu ühineb kaugsisuga)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# Üks fail, mis lisatakse kaugkataloogi (basename säilitatakse)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# Üks fail, otsene sihtkoha tee
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# Mitu allikat ühes käsus
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` ja `--remote-file` on üksteist välistavad. `--remote-file` nõuab täpselt ühte `--local` teed, mis osutab failile.

`--mirror` ei saa kombineerida faili allikaga; see kustutaks kaugkataloogis kõrvutised failid.

### Failide allalaadimine

Kataloogi puhul kasuta `--remote` (vaikimisi) või ühe faili puhul `--remote-file`. Kaks lippu on üksteist välistavad.

```bash
# Kataloog
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# Üks fail - --local peab olema olemasolev kataloog
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### Sünkroonimise oleku kontrollimine

```bash
rdc repo sync status -m server-1 -r my-app
```

### Valikud

| Valik | Kirjeldus |
|--------|-------------|
| `-m, --machine <name>` | Sihtkohaks olev masin |
| `-r, --repository <name>` | Sihtkohaks olev repositoorium |
| `--local <paths...>` | Üks või mitu kohaliku faili või kataloogi teed (üleslaadimine) või kohalik sihtkataloog (allalaadimine) |
| `--remote <path>` | Kaugkataloog (suhteliselt repositooriumi ühenduspunktist) |
| `--remote-file <path>` | Kaugfaili tee ühe faili üles- või allalaadimiseks (alternatiiv `--remote`-le) |
| `--dry-run` | Kuva muutused eelvaatena ilma ülekandeta |
| `--mirror` | Peegelda allikas sihtkohta, kustuta lisafailid (ainult kataloogi allikate puhul) |
| `--verify` | Kontrolli kontrollsummasid pärast ülekannet |
| `--confirm` | Interaktiivne kinnitamine üksikasjaliku vaatega |
| `--exclude <patterns...>` | Välista failimustrid |
| `--skip-router-restart` | Jäta marsruuteri serveri taaskäivitamine toimingu järel vahele |

## SSH-terminal (term)

Ava interaktiivne SSH-seanss masinaga või repositooriumi keskkonda.

### Lühisüntaks

Kiireim viis ühenduse loomiseks:

```bash
rdc term connect -m server-1                    # Ühenda masinaga
rdc term connect -m server-1 -r my-app             # Ühenda repositooriumiga
```

### Käsu käivitamine

Käivita käsk ilma interaktiivset seanssi avamata:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

Repositooriumiga ühendamisel seadistatakse `DOCKER_HOST` automaatselt repositooriumi isoleeritud Dockeri soklile, nii et `docker ps` näitab ainult selle repositooriumi konteinereid.

### Alamkäsk connect

Alamkäsk `connect` teeb sama otseste lippudega:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Konteineri toimingud

Suhtle otse töötava konteineriga:

```bash
# Ava kest konteineri sees
rdc term connect -m server-1 -r my-app --container <container-id>

# Vaata konteineri logisid
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# Jälgi logisid reaalajas
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# Vaata konteineri statistikat
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# Käivita käsk konteineris
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
```

| Valik | Kirjeldus |
|--------|-------------|
| `--container <id>` | Sihtiks olev Dockeri konteineri ID |
| `--container-action <action>` | Toiming: `terminal` (vaikimisi), `logs`, `stats`, `exec` |
| `--log-lines <n>` | Kuvatavate logiridade arv (vaikimisi: 50) |
| `--follow` | Jälgi logisid pidevalt |
| `--external` | Kasuta välist terminali SSH-sisese asemel |

## VS Code integratsioon (vscode)

Ava kaugne SSH-seanss VS Code'is, eelkonfigureeritud õigete SSH seadetega.

### Repositooriumiga ühendamine

```bash
rdc vscode connect -r my-app -m server-1
```

See käsk:
1. Tuvastab sinu VS Code paigalduse
2. Konfigureerib SSH-ühenduse failis `~/.ssh/config`
3. Säilitab SSH-võtme seansiks
4. Avab VS Code'i kaugneva SSH-ühendusega repositooriumi teele

### Konfigureeritud ühenduste loetlemine

```bash
rdc vscode list
```

### Ühenduste puhastamine

```bash
rdc vscode cleanup
```

Eemaldab VS Code'i SSH-konfiguratsioonid, mida enam ei vajata.

### Konfiguratsiooni kontrollimine

```bash
rdc vscode check
```

Kontrollib VS Code'i paigaldust, Remote SSH laiendust ja aktiivseid ühendusi.

> **Eeltingimus:** Paigalda VS Code'is laiendus [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh).

### VS Code brauseris

Kohalikku VS Code'i pole? Käivita redaktor repositooriumi liivakastist ja ava see mistahes brauseris:

```bash
rdc vscode connect -r my-app -m server-1 --browser
```

See käsk:
1. Paigaldab avatud lähtekoodiga redaktoriserveri masinale ühe korra (kirjutuskaitstud jagatud tee, kontrollsummaga kinnitatud)
2. Käivitab selle repositooriumi liivakastis, nii et failipuu, integreeritud terminal ja kõik alamprotsessid näevad täpselt seda, mida repositoorium näeb
3. Avab SSH-tunneli kohalikule pordile ja käivitab sinu brauseri seanssipõhise tokeniga URL-iga

Server jätkab tööd pärast tunneli sulgemist; uuesti ühendades kasutatakse seda uuesti. Halda seda käskudega:

```bash
rdc vscode serve status -r my-app -m server-1
rdc vscode serve stop -r my-app -m server-1
```

| Valik | Kirjeldus |
|--------|-------------|
| `--no-open` | Prindi URL brauseri avamise asemel |
| `--url-only` | Prindi täpselt üks URL-rida stdout-i (skriptimiseks) ja hoia tunnel avatuna |
| `--local <port>` | Vali kohaliku tunneli port |
| `--server-provider <id>` | Redaktoriserveri teostus: `openvscode` (vaikimisi) või `code-server` |
| `--server-archive <file>` | Paigalda eellaaditud tarballi kaudu masinalt (internetiühendust pole vaja) |

Töötab Linux, macOS, Windows või tahvelarvutist. Ainus kohalik nõue on brauser.

## CLI uuendused (update)

Hoia `rdc` CLI ajakohane.

### Uuenduste kontrollimine

```bash
rdc update --check-only
```

### Uuenduse rakendamine

```bash
rdc update
```

Uuendused laaditakse alla ja rakendatakse paigal. CLI valib automaatselt sinu platvormile (Linux, macOS või Windows) sobiva binaarfaili. Uus versioon jõustub järgmisel käivitamisel.

### Tagasipööramine

```bash
rdc update --rollback
```

Pöördub tagasi eelmisele paigaldatud versioonile. Saadaval ainult pärast uuenduse rakendamist.

### Uuenduse olek

```bash
rdc update --status
```

Kuvab praeguse versiooni, uuenduskanali ja automaatse uuendamise konfiguratsiooni.

#### Väljalaskekanalid

```bash
rdc update --channel edge      # Pidevalt juurutatavad tootmisuuendused
rdc update --channel stable    # Edutatud edge'ist pärast 7-päevast leotamist (vaikimisi)
rdc update --status            # Kuva praegune kanal ja versiooni info
```
