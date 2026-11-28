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
sourceHash: "108788436a73cee0"
sourceCommit: "154bfe13fba315a800622996a0dd85341a6ffb28"
---

## Ülevaade

Kaks MCP (Model Context Protocol) serverit võtavad oma tööriistad ühest registrist ning kaugserver pakub neist alamhulka:

| Server | Transport | Töötab | Tööriistad |
|---|---|---|---|
| Lokaalne | stdio | `rdc mcp serve`, mille käivitab agent | Kõik tööriistad |
| Kaug | Streamable HTTP | `https://mcp.<region>.rediacc.cloud/g/<grantId>` | Kaugtööriistad ehk kõik peale ainult lokaalsete tabelis olevate |

**Eeltingimused:** lokaalse serveri jaoks on `rdc` installitud ja seadistatud vähemalt ühe masinaga. Kaugserveri jaoks on vaja seadistusele antud grant'i.

## Lokaalne server

`rdc mcp serve` käivitab MCP serveri stdio kaudu. Agent käivitab selle alamprotsessina ja suhtleb sellega JSON-RPC abil.

### Claude Code

Projekti `.mcp.json` sisaldab kirjet:

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

Või nimega seadistusega:

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

### Cursor

Avage Settings → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

### Valikud

| Valik | Vaikeväärtus | Kirjeldus |
|-------|--------------|-----------|
| `--config <name>` | (vaikeseadistus) | Kõigi käskude jaoks kasutatav nimega seadistus |
| `--timeout <ms>` | `120000` | Käskude vaikimisi ajalimiit millisekundites |

## Kaugserver

Igas regioonis töötab üks MCP Worker aadressil `mcp.<region>.rediacc.cloud`. Iga agent ühendub ühe grant'i URL-iga: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Grant nimetab ühe seadistuse, aegumisaja ja ulatuse: kirjutuskaitse lipu, lubatud tööriistade nimekirja ning masinate ja repode nimemustrid (glob). Tööriistakutsed jooksevad grant'i organisatsiooni täitjal.

### Mandaadid

Mõlemad vormid tuvastavad grant'i; URL-is olev grant'i id ainult nimetab seda.

| Vorm | Kasutus | Saadetakse kujul |
|---|---|---|
| OAuth-ligipääsuluba | Interaktiivsed kliendid, näiteks claude.ai | `Authorization: Bearer <token>` |
| Agendi bearer `rmcp_<grantId>.<secret>` | Peata agendid | `Authorization: Bearer` või `x-api-key` |

Päringustringis olev mandaat lükatakse tagasi vastusega 400. Puuduv, aegunud või teise grant'i OAuth-luba saab vastuse 401 koos päisega `WWW-Authenticate: Bearer resource_metadata=...`, mis osutab grant'i kaitstud ressursi dokumendile, et OAuth-klient saaks luba uuendada või sisse logida. Tundmatu grant, vale saladus ja teise grant'i agendi bearer saavad kõik sama paljas 401.

### OAuth

Worker on OAuth 2.1 autoriseerimisserver PKCE-ga (ainult S256). Kliendid registreeruvad Client ID Metadata Document'i kaudu või dünaamilise kliendiregistreerimisega aadressil `/register`.

| Lõpp-punkt | Otstarve |
|---|---|
| `/.well-known/oauth-authorization-server` | Serveri metaandmed |
| `/.well-known/oauth-protected-resource/g/<grantId>` | Ühe grant'i kaitstud ressursi dokument |
| `/authorize` | Alustab autoriseerimist ja suunab konto lehele `/account/mcp/authorize` |
| `/oauth/token` | Koodi vahetus, uuendamine ja tühistamine |
| `/register` | Dünaamiline kliendiregistreerimine |

Klient saadab `resource=https://mcp.<region>.rediacc.cloud/g/<grantId>`. Autoriseerimine õnnestub ainult grant'ile, mille ressurss nimetab, ja luba töötab ainult oma grant'i URL-il. Suunamine aadressilt `/authorize` kannab allkirjastatud ühekordset tunnust ega sisalda saladust.

### Lubade kehtivusaeg

Luba ei kesta kunagi kauem kui selle grant.

| Luba | Kehtivusaeg |
|---|---|
| Ligipääsuluba | Lühem kahest: 1 tund või grant'i järelejäänud aeg |
| Uuenduseluba | Lühem kahest: 30 päeva või grant'i järelejäänud aeg |

Iga koodivahetus ja uuendus otsib grant'i uuesti üles. Aegunud, tühistatud või võtmevahetuse läbinud grant vastab `invalid_grant` ja tühistab OAuth-grant'i. Uuendusload roteeruvad ning sama luba kaks korda esitades tühistatakse grant.

### Üks seadistus grant'i kohta

Grant teenindab ainult seda ühte seadistust, mille ta nimetab. Kutse `tools/call`, mille argument nimetab teist seadistust (`config` või selle mõni kirjapilt), lükatakse tagasi koodiga `REDIACC_GRANT_SCOPE`, enne kui midagi jookseb. Mitme seadistusega kasutaja autoriseerib iga seadistuse jaoks ühe grant'i. Tööriist, mis pole grant'i lubatud nimekirjas, või kirjutustööriist kirjutuskaitstud grant'i all puudub `tools/list` vastusest ja lükatakse kutsumisel tagasi.

### Regioonid

Grant'i id algab tema regiooniga, näiteks `eu_`. Päring aadressile `/g/<grantId>` teise regiooni Worker'is saab vastuse 421 õige URL-iga:

```json
{
  "code": "REDIACC_WRONG_REGION",
  "message": "This grant lives in the us region. Use https://mcp.us.rediacc.cloud/g/us_...",
  "region": "us",
  "mcpUrl": "https://mcp.us.rediacc.cloud/g/us_..."
}
```

Grant'i ei aktsepteerita kunagi OAuth-ressursi, loa sihtrühma ega autoriseerimise sihina väljaspool tema regiooni.

### Grant'i olekud ja piirangud

Grant, mis on aegunud, tühistatud või kaotanud oma võtme seadistushoidla võtmevahetuse tõttu, vastab endiselt käskudele `initialize` ja `tools/list`. Iga `tools/call` tagastab siis `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` või `REDIACC_KEY_ROTATED` koos `reauthUrl`-iga, mille kasutaja avab uuesti autoriseerimiseks.

Iga grant lubab 60 kutset minutis ja 5 samaaegset kutset. Kutse, mis ületab kumbagi piiri, tagastab `REDIACC_RATE_LIMITED` koos `retryAfterSeconds`-iga.

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
| `backup_toc-key_sync` | jah | Paigaldab repositooriumi loendivõtme selle masinasse või asendab erineva. |
| `backup_undelete` | ei | Tühistab edasilükatud hetktõmmise kustutamise enne, kui see jõustub. |
| `backup_usage` | ei | Näitab varunduse salvestuskvooti, salvestatud baite ja kasutust repositooriumi kaupa. |
| `backup_verify` | ei | Kontrollib repositooriumi varundusankrut tükihoidla suhtes. |
| `cluster_snapshot_list` | ei | Loetleb klastri rühmahetktõmmised. |
| `cluster_status` | ei | Loetleb kõik klastrid või klastri nime andmisel näitab selle klastri täielikku konfiguratsiooni. |
| `config_access_list` | ei | Loetleb konfiguratsiooni juurdepääsuvõtmed. |
| `config_prune` | jah | Eemaldab kohalikust konfiguratsioonifailist `~/.config/rediacc/<config>.json` üleliigse. |
| `config_reconcile` | ei | Ehitab kohaliku olekuhoidla uuesti masinate tegelikust seisust (renet list all). |
| `config_show` | ei | Näitab aktiivse konfiguratsiooni üksikasju. |
| `credits` | ei | Näitab selle konto allesjäänud krediidisaldot. |
| `datastore_list` | ei | Loetleb nimega andmehoidlad, kuhu need on ühendatud ja mida need sisaldavad. |
| `datastore_snapshot_list` | ei | Loetleb andmehoidla hetktõmmised. |
| `datastore_status` | ei | Näitab ühte andmehoidlat: selle taustaprogrammi, ühendust, kasutust, repositooriume ja hetktõmmiseid. |
| `feedback_list` | ei | Loetleb sellele masinale nähtavad tagasisideraportid: id, lühike sõrmejälg, olek ja kuupäevad. |
| `feedback_report` | ei | Koostab raporti viimasest ebaõnnestunud käsust (--last), salvestatud käsust (`--command <n>`) või ainult sõnumist, prindib täpselt selle, mis saadetaks, ja saadab pärast kinnitust. |
| `feedback_show` | ei | Näitab ühte tagasisideraportit selle id järgi (või kordumatu eesliite järgi), koos oleku, esinemiste arvu ja kuupäevadega. |
| `incident_status` | ei | Loetleb organisatsiooni intsidendid või näitab ühte koos selle ulatuse, ajaakna, masinasammude ning varajase hoiatuse, teavitamise ja lõpparuande tähtaegade kelladega. |
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
| `repo_flows` | ei | Loetleb repositooriumi kohta ajaaknas salvestatud võrguvood: aeg, protsess, sihtkoht, väljuvad ja sissetulevad baidid ning sihtkoha ASN ja riik, kui need on teada. |
| `repo_fork` | jah | Loob repositooriumist peaaegu hetkelise CoW fork'i UUE GUID-i ja networkId-ga (täiesti sõltumatu koopia). |
| `repo_gc` | jah | Ulatuvuspõhine prügikoristus: kustutab masinas muutumatud commit-objektid, milleni ükski haru/HEAD ei ulatu. |
| `repo_health` | ei | Käivitab repositooriumi Rediaccfile health() kontrollid ja lõpetab koodiga 0 (korras), 1 (hoiatus) või 2 (viga). |
| `repo_list` | ei | Loetleb masina repositooriumid. |
| `repo_log` | ei | Prindib commit'ide ajaloo, mis on kättesaadav töö-fork'i praegusest commit'ist (või commit'i viitest), järgides 'rdc repo commit' salvestatud vanemate ahelat. |
| `repo_logs` | ei | Näitab repositooriumi konteinerite rakenduse logisid. |
| `repo_merge` | jah | Ühendab elutsükli suhtes ohutult lähte-commit'i või -fork'i sihttöö-fork'i. |
| `repo_migrate` | jah | Viib repositooriumi minimaalse seisakuga teise masinasse: kaheetapiline kopeerimine (hulgisünkroonimine töö ajal, seejärel lühike peatus, deltasünkroonimine ja käivitamine sihtkohas) koos DNS-i ümberlülitusega. |
| `repo_opens` | ei | Loetleb repositooriumi kohta ajaaknas salvestatud failiavamised: aeg, protsess ja tee, tundlikud teed märgitud. |
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
| `forensics_verify` | ei | Arvutab uuesti välja auditi päevafailide räsiahela ja tõendikataloogi (rdc incident ekspordikataloogi) allkirjastatud kohtuekspertiisi partiiahelad ning loetleb iga lünga ja muudatuse. |
| `incident_export` | ei | Kirjutab intsidendi ajaakna kataloogi: intsidendi kirje koos selle kelladega, ühendatud ajajoone, väljuvate baitide koondid, ahela toore manifesti ja selles loetletud toorfailid manifesti võtmete all. |
| `machine_infra_cert_status` | ei | Näitab vahemällu salvestatud sertifikaatide inventuuri. |
| `server_status` | ei | Näitab paigaldatud serveri tervist, taset, sertifikaati ja tõmmist. |
| `version` | ei | Prindib CLI versiooni, platvormi, uuenduskanali ja aktiivse litsentsi: sisselogituna paketi, sisselogimata "anonymous (FREE per repository)" ja "unknown (server unreachable)", kui kontoserverini ei jõua. |

<!-- <<< translated-table -->

## Näidistöövood

**Masina oleku kontrollimine:**
> „Mis seisus on minu tootmismasin?"

Agent kutsub `machine_status` ja saab ühenduse üksikasjad, süsteemiteabe, konteinerid, teenused, repod ja ressursikasutuse.

**Rakenduse juurutamine:**
> „Juuruta gitlab minu staging-masinas"

Agent kutsub `repo_up` argumentidega `name: "gitlab"` ja `machine: "staging"`, mis juurutab repo ja tagastab õnnestumise või vea.

**Pika töö jälgimine:**
> „Taasta nextcloudi eilne öine varukoopia"

Agent kutsub `backup_restore`. Käsk, mis ületab oma ajaakna, tagastab töö käepideme, ja agent kutsub `job_wait` (kuni 50 s ühe kutse kohta) ning `job_logs`, kuni töö lõpeb.

**Vigase teenuse silumine:**
> „Mu nextcloud on aeglane, uuri välja, mis viga on"

Agent kutsub `machine_health`, seejärel `machine_containers` ja `repo_logs`, ning pakub lahenduse.

## Turvalisus

Lokaalne MCP server rakendab kahte kaitsekihti. Kaugserveri piirangud on jaotises [Kaugserver](#remote-server).

### Ainult-fork-režiim (vaikimisi)

Vaikimisi töötab server **ainult-fork-režiimis**: kirjutustööriistad (`repo_up`, `repo_down`, `repo_delete`, `repo_exec`, `repo_push`, `repo_pull`) saavad töötada ainult fork-repodega. Agendid ei saa grand-repodele (originaalidele) kätt külge panna. Disaini järgi.

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

Lokaalne MCP server on olekuta. Iga tööriistakutse käivitab `rdc` isoleeritud alamprotsessina lippudega `--output json --yes --quiet`. See tähendab:

- Olekut ei leki tööriistakutsete vahel
- Kasutab teie olemasolevat `rdc` konfiguratsiooni ja SSH-võtmeid
- Ühe käsu vead ei mõjuta teisi
