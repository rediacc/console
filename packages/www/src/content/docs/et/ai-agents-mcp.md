---
title: MCP serveri seadistus
description: Ühendage AI-agendid Rediacc infrastruktuuriga Model Context Protocol (MCP) serveri abil.
category: Guides
order: 33
language: et
sourceHash: "ce5f1392ebaa380b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

## Ülevaade

Niisiis, `rdc mcp serve` käivitab lokaalse MCP (Model Context Protocol) serveri, mida AI-agendid saavad kasutada teie infrastruktuuri haldamiseks. Server kasutab stdio-transporti, AI-agent käivitab selle alamprotsessina ja suhtleb JSON-RPC kaudu.

**Eeltingimused:** `rdc` on installitud ja seadistatud vähemalt ühe masinaga.

## Claude Code

Lisage oma projekti `.mcp.json`-i:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

Või nimega konfiguratsiooniga:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Avage Seaded → MCP Servers → Add Server:

- **Nimi**: `rdc`
- **Käsk**: `rdc mcp serve`
- **Transport**: stdio

## Saadaolevad tööriistad

### Lugemistööriistad (ohutud, ilma kõrvalmõjudeta)

| Tööriist | Kirjeldus |
|----------|-----------|
| `machine_query` | Masina süsteemiinfo, konteinerite, teenuste ja ressursikasutuse hankimine |
| `machine_containers` | Dockeri konteinerite loetlemine koos oleku, tervise, ressursikasutuse, siltide ja automaattee domeeniga |
| `machine_services` | Rediacc-hallatavate systemd-teenuste loetlemine (nimi, olek, ala-olek, taaskäivituste arv, mälu, omav repositoorium) |
| `machine_repos` | Juurutatud repositooriumide loetlemine (nimi, GUID, suurus, ühendamise olek, Dockeri olek, konteinerite arv, kettakasutus, muutmise kuupäev, Rediaccfile'i olemasolu) |
| `machine_health` | Masina terviskontrolli käivitamine (süsteem, konteinerid, teenused, salvestus) |
| `machine_list` | Kõigi seadistatud masinate loetlemine |
| `config_repositories` | Seadistatud repositooriumide loetlemine koos nime-GUID vastavustega |
| `config_show_infra` | Masina infrastruktuuri konfiguratsiooni kuvamine (baasdomeen, avalikud IP-d, TLS, Cloudflare'i tsoon) |
| `config_providers` | Masina ettevalmistamiseks seadistatud pilveteenuse pakkujate loetlemine |
| `agent_capabilities` | Kõigi saadaolevate rdc CLI käskude loetlemine koos nende argumentide ja valikutega |
| `repo_secret_list` | Repositooriumi saladuste nimede ja edastusrežiimide loetlemine (mitte kunagi väärtused, mitte kunagi räsid). Lugemisohutu. |
| `repo_secret_get` | Saladuse SHA-256 räsi ja edastusrežiimi hankimine. Lihtteksti väärtust ei tagastata kunagi disaini põhjal. Kasutage seda saladuse olemasolu või roteerimise kontrollimiseks. |

### Kirjutamistööriistad (hävitavad)

| Tööriist | Kirjeldus |
|----------|-----------|
| `repo_create` | Uue krüpteeritud repositooriumi loomine masinal |
| `repo_up` | Repositooriumi juurutamine/uuendamine (käivitab Rediaccfile'i up, käivitab konteinerid). Kasutage `mount` esimese juurutuse jaoks või pärast tõmbamist |
| `repo_down` | Repositooriumi konteinerite peatamine. Vaikimisi EI tühista ühendamist. Kasutage `unmount`, et sulgeda ka LUKS-konteiner |
| `repo_delete` | Repositooriumi kustutamine (hävitab konteinerid, köited, krüpteeritud pildi). Mandaat arhiveeritakse taastamise jaoks |
| `repo_fork` | CoW-fork loomine uue GUID ja networkId-ga (täiesti iseseisev koopia, võrgus forki toetav) |
| `backup_push` | Repositooriumi varukoopia saatmine salvestusruumi või teisele masinale (sama GUID -- varukoopia/migratsioon, mitte fork) |
| `backup_pull` | Repositooriumi varukoopia tõmbamine salvestusruumist või masinalt. Pärast tõmbamist juurutage `repo_up`-ga (mount=true) |
| `machine_provision` | Uue masina ettevalmistamine pilveteenuse pakkujal OpenTofu abil |
| `machine_deprovision` | Pilveteenusega ettevalmistatud masina hävitamine ja konfiguratsioonist eemaldamine |
| `config_add_provider` | Pilveteenuse pakkuja konfiguratsiooni lisamine masina ettevalmistamiseks |
| `config_remove_provider` | Pilveteenuse pakkuja konfiguratsiooni eemaldamine |
| `term_exec` | Käsu käivitamine kaugmasinal SSH kaudu |

## Näidistöövood

**Masina oleku kontrollimine:**
> "Mis on minu tootmismasina olek?"

Agent kutsub `machine_query` → tagastab süsteemiinfo, töötavad konteinerid, teenused ja ressursikasutuse.

**Rakenduse juurutamine:**
> "Juuruta gitlab minu lavastusmasinale"

Agent kutsub `repo_up` koos `name: "gitlab"` ja `machine: "staging"` → juurutab repositooriumi, tagastab edu/ebaõnnestumise.

**Tõrke silumine:**
> "Minu nextcloud on aeglane, uuri, mis lahti on"

Agent kutsub `machine_health` → `machine_containers` → `term_exec` logide lugemiseks → tuvastab probleemi ja pakub lahenduse.

## Konfiguratsioonivalikud

| Valik | Vaikimisi | Kirjeldus |
|-------|-----------|-----------|
| `--config <nimi>` | (vaikimisi konfiguratsioon) | Nimega konfiguratsioon, mida kõigi käskude jaoks kasutada |
| `--timeout <ms>` | `120000` | Käsu vaikeaegumine millisekundites |
| `--allow-grand` | väljas | Lubage hävitavad toimingud grand-repositooriumidel (mitte-fork) |

## Turvalisus

MCP server rakendab kaks kaitsekihti:

### Ainult-fork-režiim (vaikimisi)

Vaikimisi töötab server **ainult-fork-režiimis**: kirjutamistööriistad (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) saavad töötada ainult fork-repositooriumidel. Agendid ei saa puutuda grand-repositooriumidesse (originaalidesse). Nii on see kavandatud.

> **Repo-saladused on disaini järgi ainult CLI kaudu.** `repo_secret_set` ja `repo_secret_unset` ei ole tahtlikult MCP tööriistadena paljastatud. Kirjutamised nõuavad eeltingimust `--current <eelmine-väärtus>` (või `--rotate-secret`, et kinnitada kontrollimata pööramine), ja see toiming vajab inimese järelevalvet. Agendid, kes peavad saladuse pööramist soovitama, peaksid kutsuma `repo_secret_get` räsi kinnitamiseks, seejärel edastama operaatori CLI-käsu kasutajale JSON-vea ümbriku välja `next.options[].run` kaudu. Täieliku mustri jaoks vaadake [AI-agendi turvalisus](/et/docs/ai-agents-safety#structured-next-action-hints) ja kasutajapoolse juhendi jaoks [Repositooriumid § Saladused](/et/docs/repositories#secrets).

Grand-repositooriumide agendi muutmise lubamiseks käivitage koos `--allow-grand`:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

Samuti saate seada keskkonnamuutuja `REDIACC_ALLOW_GRAND_REPO` ühe repo nimele, komaga eraldatud repo nimede loendile (näiteks `repo1,repo2,repo3`) või `*` kõigi repode jaoks. Kirjeid ümbritsev tühik ignoreeritakse, seega `repo1, repo2` töötab samuti. Masinataseme juurdepääs (näiteks `term connect -m <machine>` ilma repota) nõuab siiski `*`; repo nimede loend seda ei ava.

### Repo-põhised SSH-võtmed ja serveripoolne liivakast

Igal repositooriumil on oma SSH-võtmepaar. Avalik võti juurutatakse `authorized_keys`-i koos `command=` prefiksiga, mis suunab kõik SSH-seansid läbi `renet sandbox-gateway <repo-nimi>`, serveri ForceCommandi, mida ükski klient ei saa mööda hiilida, kaasa arvatud VS Code.

**Kuidas see toimib:**
1. `rdc repo create` või `rdc repo fork` genereerib repo kohta unikaalse ed25519-võtmepaari
2. Avalik võti juurutatakse kaugarvutile koos `command="renet sandbox-gateway <nimi>"`
3. Iga selle võtmega SSH-ühendus läbib lüüsi, mis rakendab:
   - **Landlock LSM**, kerneli taseme failisüsteemi piirangud repo ühendamistee jaoks
   - **OverlayFS kodu-overlay**, kirjutamised `$HOME`-i püütakse repo kaupa, lugemised langevad läbi päris koju
   - **Repo-põhine TMPDIR** aadressil `<datastore>/.interim/sandbox/<nimi>/tmp/`
   - **Dockeri juurdepääs** repo isoleeritud Dockeri sokli kaudu
   - **Privileegide langus** universaalsele kasutajale (`rediacc`)
4. Repo `.envrc` laaditakse automaatselt Dockeri ja keskkonna seadistamiseks

**Lubatud RW**: repo ühendamistee, repo-põhine liivakastiruum, kodukataloog (overlay kaudu), Dockeri sokel
**Lubatud RO**: süsteemi teed (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**Blokeeritud**: teiste repode ühendamisteed, süsteemifailid väljaspool lubamisnimekirja

**VS Code'i integratsioon**: Iga repo saab oma VS Code serveri installatsiooni aadressil `<datastore>/.interim/sandbox/<nimi>/.vscode-server/`. Mitu repot saab olla avatud samaaegselt sõltumatute liivakastitud keskkondadega, serverite jagamine repode vahel puudub.

See takistab külgsuunalist liikumist. Isegi kui agent saab kesta juurdepääsu forkile, ei saa ta lugeda ega muuta teisi repositooriume samal masinal. Masinataseme SSH (ilma repositooriumita) kasutab meeskonna võtit ja see ei ole liivakastitud.

## Arhitektuur

MCP server on olekuta. Iga tööriistakutse käivitab `rdc` isoleeritud alamprotsessina koos lippudega `--output json --yes --quiet`. See tähendab:

- Olekut ei leki tööriistakutsete vahel
- Kasutab teie olemasolevat `rdc` konfiguratsiooni ja SSH-võtmeid
- Töötab nii lokaalse kui pilvepõhise adapteriga
- Ühe käsu vead ei mõjuta teisi
