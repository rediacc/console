---
title: MCP serveri seadistus
description: Ühendage AI-agendid Rediacc infrastruktuuriga Model Context Protocol (MCP) serveri abil.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: et
sourceHash: "5ffb60357e13aeab"
sourceCommit: "a2b1f5471f48c44fb704157f615369df9c354832"
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

<!-- >>> translated-table: mcp-tools -->

| Tööriist | Hävitav | Kirjeldus |
|---|---|---|
| `backup_browse` | ei | Loetleb repositooriumi sisalduvad failid. |
| `backup_cancel` | ei | Tühistab kaugmasinas käimasoleva varundamise. |
| `backup_check` | ei | Tõestab, et salvestatud hetktõmmis avaneb parooliga, taastades ühe faili. |
| `backup_immutability_show` | ei | Näitab kehtivat edasilükatud kustutamise akent. |
| `backup_list` | ei | Loetleb masinas olevad varundusartefaktid. |
| `backup_manifests` | ei | Loetleb serverisse registreeritud varundushetktõmmiste manifestid. |
| `backup_reconcile` | jah | Lähtestab repositooriumi salvestatud baitide registri sellele, mida hoidla tegelikult sisaldab (ei kustuta kunagi ühtegi tükki). |
| `backup_repair` | jah | Laadib selle masina ankrust uuesti üles tükid, mille hoidla on kaotanud või mida see hoiab valesti. |
| `backup_restore` | jah | Muudab varundusartefakti toimivaks repositooriumiks. |
| `backup_retention` | ei | Näitab serveri jõustatavat hetktõmmiste säilituspoliitikat. |
| `backup_retention_preview` | ei | Näitab, milliseid hetktõmmiseid järgmine puhastus kustutaks ja kui palju ruumi see vabastaks. |
| `backup_run` | ei | Käivitab varunduse kohe. |
| `backup_snapshot` | ei | Laadib üles tükihoidla hetktõmmise: kõigepealt täisinventuur, seejärel muutunud lahtrid. |
| `backup_status` | ei | Näitab kaugmasina varunduse olekut ja taimeri seisundit. |
| `backup_strategy_list` | ei | Loetleb kõik varundusstrateegiad. |
| `backup_strategy_show` | ei | Näitab varundusstrateegia üksikasju. |
| `backup_toc-key_sync` | ei | Paigaldab repositooriumi loendivõtme selle masinasse või asendab erineva. |
| `backup_undelete` | ei | Tühistab edasilükatud hetktõmmise kustutamise enne, kui see jõustub. |
| `backup_usage` | ei | Näitab varunduse salvestuskvooti, salvestatud baite ja kasutust repositooriumi kaupa. |
| `backup_verify` | ei | Kontrollib repositooriumi varundusankrut tükihoidla suhtes. |
| `cluster_snapshot_list` | ei | Loetleb klastri rühmahetktõmmised. |
| `cluster_status` | ei | Loetleb kõik klastrid või klastri nime andmisel näitab selle klastri täielikku konfiguratsiooni. |
| `config_access_list` | ei | Loetleb konfiguratsiooni juurdepääsuvõtmed. |
| `config_prune` | ei | Eemaldab kohalikust konfiguratsioonifailist ~/.config/rediacc/<config>.json üleliigse. |
| `config_reconcile` | ei | Ehitab kohaliku olekuhoidla uuesti masinate tegelikust seisust (renet list all). |
| `config_show` | ei | Näitab aktiivse konfiguratsiooni üksikasju. |
| `credits` | ei | Näitab selle konto allesjäänud krediidisaldot. |
| `datastore_list` | ei | Loetleb nimega andmehoidlad, kuhu need on ühendatud ja mida need sisaldavad. |
| `datastore_snapshot_list` | ei | Loetleb andmehoidla hetktõmmised. |
| `datastore_status` | ei | Näitab ühte andmehoidlat: selle taustaprogrammi, ühendust, kasutust, repositooriume ja hetktõmmiseid. |
| `feedback_list` | ei | Loetleb sellele masinale nähtavad tagasisideraportid: id, lühike sõrmejälg, olek ja kuupäevad. |
| `feedback_report` | ei | Koostab raporti viimasest ebaõnnestunud käsust (--last), salvestatud käsust (--command <n>) või ainult sõnumist, prindib täpselt selle, mis saadetaks, ja saadab pärast kinnitust. |
| `feedback_show` | ei | Näitab ühte tagasisideraportit selle id järgi (või kordumatu eesliite järgi), koos oleku, esinemiste arvu ja kuupäevadega. |
| `job_cancel` | jah | Tühistab käimasoleva eraldiseisva töö. |
| `job_dismiss` | jah | Loobub tööde piletitest kohapeal: nende ootel sammud jäetakse ära ja pilet ei ilmu enam. |
| `job_gc` | jah | Eemaldab lõppenud tööd ja nende logid. |
| `job_list` | ei | Loetleb masina eraldiseisvad tööd, uuemad ees. |
| `job_logs` | ei | Esitab eraldiseisva töö sündmuselogi uuesti või jälgib seda reaalajas. |
| `job_status` | ei | Näitab eraldiseisva töö olekut. |
| `job_wait` | ei | Ootab kuni 50 s, kuni töö lõpeb. |
| `legal` | ei | Prindib juriidiliste dokumentide lingid CLI keeles koos siduvate ingliskeelsete linkidega, kehtiva kasutustingimuste versiooni kontrollsumma ja arhiivi URL-iga, registreeritud nõusoleku (sisselogituna kontoserverist, anonüümselt sellest konfiguratsioonist) ja lepingupartneri. |
| `machine_access_show` | ei | Näitab masinaga seotud juurdepääsuvõtmeid ja vahemikke, mille igaüks seal lahendab. |
| `machine_add` | ei | Registreerib olemasoleva masina, millele pääseb SSH kaudu ligi. |
| `machine_containers` | ei | Loetleb masina Dockeri konteinerid. |
| `machine_converge` | jah | Taaskäivitab ükshaaval iga repositooriumi deemoni, mis töötab veel vanemal käitusküljenduse versioonil, et see läheks üle praegusele. |
| `machine_deprovision` | jah | Hävitab pilves loodud masina ja eemaldab selle konfiguratsioonist. |
| `machine_gpu_list` | ei | Loetleb masinas tuvastatud GPU-d, nende kirjelduste määratletud CDI seadmenimed ja repositooriumid, millele iga seade on antud. |
| `machine_health` | ei | Kontrollib masina tervist CI/CD torujuhtmete jaoks. |
| `machine_infra_show` | ei | Näitab masina infrastruktuurikonfiguratsiooni (baasdomeen, avalikud IP-d, pordid), jagatud TLS-seadeid (sertifikaadi e-post, CF DNS-žetoon) ja Cloudflare'i tsooni ID-d. |
| `machine_list` | ei | Loetleb masinad. |
| `machine_provider_add` | ei | Lisab pilveteenuse pakkuja. |
| `machine_provider_list` | ei | Loetleb masinate loomiseks seadistatud pilveteenuse pakkujad. |
| `machine_provider_remove` | jah | Eemaldab pilveteenuse pakkuja konfiguratsiooni. |
| `machine_provision` | jah | Loob OpenTofu abil pilveteenuse pakkujas uue masina. |
| `machine_prune` | jah | Eemaldab masinast orvuks jäänud andmehoidla ressursid ja aegunud hetktõmmised. |
| `machine_remove` | jah | Eemaldab masina konfiguratsioonist. |
| `machine_repos` | ei | Loetleb masinasse juurutatud repositooriumid. |
| `machine_restart-services` | jah | Viib renet-deemonid, mis veel käitavad asendatud binaarfaili, ükshaaval üle paigaldatud binaarfailile ja kinnitab enne järgmist, et iga üksus on aktiivne. |
| `machine_scan-keys` | ei | Salvestab masina SSH hostivõtmed kohalikku konfiguratsiooni. |
| `machine_services` | ei | Loetleb masinas Rediacci hallatavad systemd teenused (nimi, olek, alamolek, taaskäivituste arv, mälu, repositoorium nimeks lahendatud, algupärane väljas repository_guid). |
| `machine_setup` | ei | Lõpetab masina kasutuselevõtu: paigaldab renet'i ja valmistab masina ette repositooriumide majutamiseks. |
| `machine_status` | ei | Toob masina ühenduse üksikasjad (IP, kasutaja, port, andmehoidla), süsteemiinfo, konteinerid (repositoorium nimeks lahendatud, algupärane väljas repository_guid, domeen, autoRoute), teenused (repositoorium nimeks lahendatud), repositooriumid (nimi GUID-ist lahendatud, algupärane väljas guid) ja ressursikasutuse. |
| `repo_admin_fsck` | ei | Valideerib konfiguratsiooni viited (harud/HEAD) masinas olevate objektide vastu ning teatab rippuvatest viidetest ja orvuks jäänud commit'idest. |
| `repo_cat` | ei | Loeb repositooriumi failist piiratud akna stdout'i (diagnostika läheb stderr'i). |
| `repo_checkout` | jah | Kloonib reflinkiga muutumatu commit'i (või haru tipu) uude kirjutatavasse töö-forki ja suunab HEAD'i sellele. |
| `repo_commit` | jah | Külmutab haakitud töö-fork'i uueks muutumatuks commit'iks (git'i moodi). |
| `repo_create` | jah | Loob uue repositooriumi. |
| `repo_delete` | jah | Kustutab repositooriumi ja selle andmed. |
| `repo_diff` | ei | Git'i stiilis failitaseme diff kahe copy-on-write fork-repositooriumi vahel. |
| `repo_down` | jah | Peatab repositooriumi Dockeri konteinerid (käivitab Rediaccfile down). |
| `repo_exec` | jah | Käivitab käsu repositooriumi konteineris. |
| `repo_fork` | jah | Loob repositooriumist peaaegu hetkelise CoW fork'i UUE GUID-i ja networkId-ga (täiesti sõltumatu koopia). |
| `repo_gc` | jah | Ulatuvuspõhine prügikoristus: kustutab masinas muutumatud commit-objektid, milleni ükski haru/HEAD ei ulatu. |
| `repo_health` | ei | Käivitab repositooriumi Rediaccfile health() kontrollid ja lõpetab koodiga 0 (korras), 1 (hoiatus) või 2 (viga). |
| `repo_list` | ei | Loetleb masina repositooriumid. |
| `repo_log` | ei | Prindib commit'ide ajaloo, mis on kättesaadav töö-fork'i praegusest commit'ist (või commit'i viitest), järgides 'rdc repo commit' salvestatud vanemate ahelat. |
| `repo_logs` | ei | Näitab repositooriumi konteinerite rakenduse logisid. |
| `repo_merge` | jah | Ühendab elutsükli suhtes ohutult lähte-commit'i või -fork'i sihttöö-fork'i. |
| `repo_migrate` | jah | Viib repositooriumi minimaalse seisakuga teise masinasse: kaheetapiline kopeerimine (hulgisünkroonimine töö ajal, seejärel lühike peatus, deltasünkroonimine ja käivitamine sihtkohas) koos DNS-i ümberlülitusega. |
| `repo_pull` | jah | Tõmbab repositooriumi teisest masinast. |
| `repo_push` | jah | Saadab repositooriumi varukoopia hoidlasse või otse teise masinasse. |
| `repo_replicate` | ei | Loob repositooriumist lugemisreplikad. |
| `repo_replicate_remove` | jah | Eemaldab replikakomplekti: kustutab selle loodud k8s-objektid (sildiga piiratud), loobub selle fork-andmehoidlatest, eemaldab selle hetktõmmise ja unustab oleku. |
| `repo_replicate_status` | ei | Näitab hallatavaid replikakomplekte: replikad, majutavad sõlmed, fork-andmehoidlad, hetktõmmis ja värskendusajad. |
| `repo_secret_get` | ei | Näitab saladuse SHA-256 räsi. |
| `repo_secret_list` | ei | Loetleb saladuste võtmed ja režiimid (mitte kunagi väärtusi ega räsisid). |
| `repo_status` | ei | Toob repositooriumi oleku (haakimise olek, Dockeri deemon töötab, konteinerite arv, kettakasutus). |
| `repo_trim` | ei | Vabastab haagitud repositooriumidest andmehoidla kogumi ruumi (võrgus, ilma seisakuta). |
| `repo_up` | jah | Juurutab või uuendab repositooriumi (käivitab Rediaccfile up renet compose'i kaudu, käivitab konteinerid). |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| Tööriist | Hävitav | Kirjeldus |
|---|---|---|
| `cluster_kubeconfig` | ei | Toob SSH kaudu klastri juhtsõlmest kubeconfigi ja salvestab selle kohalikku vahemällu (0600) kubectl'i jaoks. |
| `config_audit_log` | ei | Loeb selle konfiguratsiooni kaudu tehtud muudatuste auditilogi. |
| `config_audit_verify` | ei | Kontrollib, et auditilogi räsiahelat ei ole muudetud. |
| `config_current` | ei | Näitab aktiivset konfiguratsiooni: nimi, fail, lahendatud server ja kanal, žetooni olek. |
| `config_list` | ei | Loetleb kõik konfiguratsioonifailid. |
| `machine_infra_cert_status` | ei | Näitab vahemällu salvestatud sertifikaatide inventuuri. |
| `server_status` | ei | Näitab paigaldatud serveri tervist, taset, sertifikaati ja tõmmist. |
| `version` | ei | Prindib CLI versiooni, platvormi, uuenduskanali ja aktiivse litsentsi: sisselogituna paketi, sisselogimata "anonymous (FREE per repository)" ja "unknown (server unreachable)", kui kontoserverini ei jõua. |

<!-- <<< translated-table -->

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
| `--config <name>` | (vaikekonfiguratsioon) | Nimega konfiguratsioon, mida kasutada kõigi käskude jaoks |
| `--timeout <ms>` | `120000` | Käsu vaikeaegumine millisekundites |

## Turvalisus

MCP server rakendab kaks kaitsekihti:

### Ainult-fork-režiim (vaikimisi)

Vaikimisi töötab server **ainult-fork-režiimis**: kirjutamistööriistad (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) saavad töötada ainult fork-repositooriumidel. Agendid ei saa puutuda grand-repositooriumidesse (originaalidesse). Nii on see kavandatud.

> **Repo-saladused on disaini järgi ainult CLI kaudu.** `repo_secret_set` ja `repo_secret_unset` ei ole tahtlikult MCP tööriistadena paljastatud. Kirjutamised nõuavad eeltingimust `--current <eelmine-väärtus>` (või `--rotate-secret`, et kinnitada kontrollimata pööramine), ja see toiming vajab inimese järelevalvet. Agendid, kes peavad saladuse pööramist soovitama, peaksid kutsuma `repo_secret_get` räsi kinnitamiseks, seejärel edastama operaatori CLI-käsu kasutajale JSON-vea ümbriku välja `next.options[].run` kaudu. Täieliku mustri jaoks vaadake [AI-agendi turvalisus](/et/docs/ai-agents-safety#structured-next-action-hints) ja kasutajapoolse juhendi jaoks [Repositooriumid § Saladused](/et/docs/repositories#secrets).

Grand-repositooriumide agendi muutmise lubamiseks ekspordi `REDIACC_ALLOW_GRAND_REPO` oma terminalis **enne agendi käivitamist, mis majutab MCP serveri**:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # üks repo
# või 'repo1,repo2,repo3' (kirjete ümbritsev tühik ignoreeritakse) või '*' kõigi repode jaoks
claude   # või cursor, gemini jne.
```

Ülekate kontrollitakse protsessi päritolu suhtes: see arvestatakse ainult siis, kui see oli juba agendi protsessi keskkonnas, mis tähendab, et sa eksportisid selle enne agendi (ja MCP serveri, mille see käivitas) käivitamist. Agent ei saa end juurdepääsu anda, seades muutuja seansi keskel. Tahtlikult pole serveriflagi: lipp MCP serveri argumentides ei näita, kes selle sinna pani, samal ajal kui päritolu kontroll näitab. Masinataseme juurdepääs (näiteks `term connect <machine>` ilma repota) nõuab siiski `*`; repo nimede loend seda ei ava.

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
- Ühe käsu vead ei mõjuta teisi
