---
title: AI agendi ohutus ja turvamehhanismid
description: >-
  Kuidas Rediacc takistab tehisintellektil põhinevatel kodeerimisabilistel
  saladusi lekitada, mandaate üle kirjutada või õigusi laiendada. Üks otsus
  igale liidesele, sõnaselge nõusolek JA poliitika lagi, teadmisvärav,
  redakteerimine ja auditilogi, mis on serveris räsiahelaga organisatsiooni ja päeva kaupa ning CLI-s kohalikus failis.
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: et
sourceHash: "43350a2e682cebcc"
sourceCommit: "cc655e698ed2c42faef5311e268425c04997f243"
---

Niisiis suunad AI-koodiabistaja oma infrastruktuuri peale. Kui Claude Code, Cursor, Gemini CLI, Copilot CLI või mõni muu sarnane tööriist juhib `rdc`-d, kohtleb CLI seda klaviatuuri taga olevast inimesest erinevalt. Sellel lehel selgitatakse, mida agent saab teha, mida mitte, ja kuidas turvamehhanismid kehtivad isegi siis, kui agent üritab neist mööda rääkida.

## Kiirviide: mida agendid saavad ja ei saa teha

| Toiming | Agendi vaikeväärtus | Kuidas konkreetse kasutusjuhu jaoks avada |
|---|---|---|
| `rdc config show` (redakteeritud) | ✅ lubatud |  |
| `rdc config field get --pointer <pointer>` (redakteeritud asendaja või kokkuvõte) | ✅ lubatud |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ lubatud |  |
| `rdc config field set --pointer <pointer>` (avalik väli) | ✅ lubatud |  |
| `rdc config field set --pointer <pointer>` (tundlik väli, **korrektse `--current`-ga**) | ✅ lubatud |  |
| `rdc config edit --dump --redacted` (redakteeritud JSONC) | ✅ lubatud |  |
| `rdc config audit {log, tail, verify}` | ✅ lubatud |  |
| `rdc config field set --pointer <pointer>` (tundlik väli, ilma `--current`-ta) | 🔴 keeldutud | Esita `--current "<vana väärtus>"` |
| `rdc repo secret set <repo> --rotate-secret` (pööramine ilma `--current`-ita) | 🔴 keeldutud | Esita `--current` või inimene teeb pööramise terminalis |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 keeldutud | Kasuta `--digest` asemel |
| `rdc config show --reveal` | 🔴 keeldutud | Kasuta tavalist `rdc config show` |
| `rdc config edit` (interaktiivne redaktor) | 🔴 keeldutud, ülekatet pole | Vaata `--dump --redacted` abil, muuda ühte välja käsuga `config field set --current` |
| `rdc config edit --apply <file>` | 🔴 keeldutud, ülekatet pole | Sama; kogu dokumendi muudatused rakendab inimene terminalis |
| `rdc config edit --reveal` | 🔴 keeldutud, ülekatet pole | Sama |
| `rdc config field rotate --pointer <pointer>` | 🔴 keeldutud | Inimene käivitab selle interaktiivses terminalis |
| Grand (tootmis) repo muutmine | 🔴 keeldutud | Inimese sõnaselge nõusolek selle repo jaoks, poliitika raames, mis lubab grand-repode muutmist ([allpool](#one-decision-opt-in-and-policy-ceiling)) |
| Klastri või andmehoidla elutsükli toimingud | 🔴 keeldutud | Inimese sõnaselge nõusolek selle klastri jaoks, poliitika raames, mis lubab klastritoiminguid |
| `rdc term connect <machine>` (otsene masina SSH) | 🔴 keeldutud | Tee esmalt repo fork ja ühenda fork'iga |

Kõik, milles agendile keeldutakse, kirjutatakse auditi logisse koos `outcome: refused` ja põhjusega. Kogu konfiguratsioonidokumendi muutmiseks pole agendil üldse teed: konfiguratsioon kannab iga repo LUKS-mandaati ja agent, kes saaks selle ümber kirjutada, saaks kustutada ka mandaadi, ilma milleta krüpteeritud köidet avada ei saa.

## Kuidas agendid tuvastatakse

CLI käsitleb protsessi agendina, kui kehtib mõni järgmistest:

- Üks järgmistest on seatud väärtusele `"1"`: `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI`, või `CURSOR_TRACE_ID` on üldse seatud.
- Linuxis: mõni vanemaprotsess pärilusahelas omab ühte neist muutujatest oma keskkonnas (via `/proc/<pid>/environ`). Isegi kui agent kustutab oma muutujad käsuga `env -i` või ümbrisskriptiga, annab vanemate ahel CLI-le teada, kes selle käivitas.

Tuvastamine käib üks kord protsessi kohta ja see salvestatakse vahemällu. Seda ei saa keelata. Kaug-MCP luba märgib oma kutsed täitjal agendikutseteks, tuvastamist ei vajata.

## Üks otsus: sõnaselge nõusolek JA poliitika lagi

Iga liides, mis käivitab `rdc` käsu (CLI, kohalik MCP server, kaug-MCP server, `rdc --proxy` ja veebikonsool), küsib sama otsusefunktsiooni käest, seega keelavad ja lubavad kõik sama. See rakendab kaht tingimust ning agent tegutseb ainult seal, kus mõlemad kehtivad:

1. **Poliitika lagi.** Organisatsiooni poliitika, mida meeskonna poliitika kitsendab, otsustab, milliseid käske, masinaid ja repoisid helistaja tohib kasutada ning kas grand-repode muutmine (`allowGrandRepos`) ja klastritoimingud (`allowClusterOps`) on üldse lubatud. Konfiguratsioon ilma poliitikakirjeta langeb tagasi rollipõhisele vaikeväärtusele: omanikud ja administraatorid tohivad tegutseda, liikmed mitte. Poliitika on eraldi pitseeritud kirje, mida kirjutavad ainult omanikud ja administraatorid ([Turvamudel](/et/docs/security-model#policy)); ükski agent ega CLI käsk ei saa seda muuta.
2. **Inimese sõnaselge nõusolek.** Lae sees vajab agent ikkagi inimest, kes nimetab grand-repo või klastri, mida ta tohib muuta:
   - **Kohalikud agendid** (CLI ja kohalik MCP): inimene ekspordib terminalis enne agendi käivitamist `REDIACC_ALLOW_GRAND_REPO` (repode nimed või `*`) või `REDIACC_ALLOW_CLUSTER_OPS` (klastrite nimed või `*`). CLI kontrollib protsessi pärilusahelat, seega ei lähe arvesse muutuja, mille agent seansi keskel seab ([kuidas seda igal OS-il kontrollitakse](#how-a-local-opt-in-is-verified-on-each-os)).
   - **Kaugagendid** (kaug-MCP): nõusolekud on osa loast, mille inimene loob konto liideses ([Kaugserver](/et/docs/ai-agents-mcp#remote-server)).

Nõusolek ei laienda kunagi lage: repo, mille poliitika sulgeb, jääb suletuks, olenemata sellest, mida keskkond või luba ütleb. Forkid ei vaja nõusolekut. Repot, mida CLI ei suuda tuvastada, loetakse grand-repoks.

**Hävitavad muudatused küsivad enne.** Kui agent on grand-repo hävitavaks muutmiseks (näiteks `repo delete`) volitatud, on vastus `needs_confirmation`. MCP klient näitab kasutajale kinnitusviipa; klient, millel seda pole, saab `confirm` argumendi, mille ta saadab tagasi pärast kasutajalt küsimist. CLI-s käivitab inimene käsu uuesti valikuga `--confirm-grand <repo>`.

Iga vastus kannab stabiilset koodi (`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`), nii et skript või agent hargneb koodi, mitte teate järgi ([JSON-väljund](/et/docs/ai-agents-json-output)).

## Teadmisvärava mudel

Tundlikud muudatused järgivad `passwd(1)` konventsiooni: saladuse muutmiseks tõesta, et sa juba teadsid seda. **Sümmeetriline inimeste ja agentide jaoks.** Mõlemad läbivad sama värava. Puudub "istun klaviatuuri taga" ümbersõit.

- Soovid vahetada API tokenit, mis asub aadressil `/credentials/cfDnsApiToken`?
- CLI küsib: "mis on praegune väärtus?"
- Agent (või inimene) esitab lihtteksti `--current "$OLD"` kaudu. CLI räsistab `$OLD` SHA-256-ga ja võrdleb praegu salvestatud väärtuse kokkuvõttega. Kattuvus: kirjutamine läbi. Lahknevus: keeldutud, logitud auditisse.
- Pööramiseks ilma eelmist väärtust kontrollimata anna `--rotate-secret` (välistab `--current`-i). See auditeeritakse selgelt pööramisena ja loeb ainult interaktiivses terminalis olevale inimesele: agent või skript, millel pole stdin-il terminali, vajab ikkagi `--current`-i.

Mudel sulgeb kolm ründepinda:

1. **Vaikne pööramine**: kutsuja (agent või inimene), kellel pole juurdepääsu `$OLD`-le, ei saa asendada seda enda valitud väärtusega.
2. **Eksfiltreermine katsetamise teel**: kokkuvõtte vastus ei sisalda kunagi lihtteksti; isegi rikutud auditi logis kuvatakse `expected abc12345…, got deadbeef…`, mitte aluseks olevaid väärtusi.
3. **Tootmiskonfiguratsioonile juhuslik kirjutamine**: nõuab iga kord tahtlikku `--current`-i, isegi TTY-s. Tabab vea "tahtsin seada STRIPE_TEST, aga olen tootmise shellis".

### Struktureeritud järgmise toimingu vihjed

Kui eeltingimus ebaõnnestub, kannab JSON-ümbrik (`--output json`) struktureeritud välja `errors[].next`, mis ütleb agentidele täpselt, mida soovitada inimesele teha:

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Agendid peaksid `next.options[].run` edastama inimesele sõna-sõnalt, mitte oma käske välja mõtlema.** See väldib tõrget, kus agent mõtleb välja käsu, mida pole olemas, ja hoiab operaatori tegeliku toimingu üle kontrolli. Pööramisvariant on mõeldud inimesele terminalis; agendile endale see keelatakse.

### Töötatud näide

```bash
# Avastab redakteerimise asendaja lühikokkuvõtte (ohutu agentide jaoks).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Katse üle kirjutada ilma tõendita: keeldutud.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# Praeguse lihtteksti esitamine: lubatud.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Kui agendil ei olnud `$OLD_CF_TOKEN` kunagi, ei saa ta eeltingimust täita ja pööramisest keeldutakse. Kes väärtust teab, saab selle ikkagi teha: andes oma shellist `--current` või käsuga `rdc config field rotate` interaktiivses terminalis.

## Vaikimisi redakteerimine

Iga `rdc` käsk, mis loeb tundlikku olekut: `config show`, `config field get`, `config machine list`, `config edit --dump --redacted`: tagastab salaväljade jaoks **redakteerimise asendajad**, mitte lihtteksti:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Asendaja 8-kohaline kuueteistkümnendarvu sufiks on `sha256(canonicalize(value))` esimesed 8 märki: piisab kahe erineva väärtuse esmapilgul eristamiseks, kuid mitte ümberpööramiseks. Agent saab asendajat kasutada väärtuse muutumise jälgimiseks ilma seda kunagi nägemata.

`--reveal` tühistab redakteerimise inimestele interaktiivsel TTY-l. Agentidele keeldutakse olenemata TTY olekust. Iga grant kirjutab auditi kande `reveal_granted`; iga keeldumine kirjutab kande `refused` koos toimiva agendi signaalidega.

## Kuidas kohalikku sõnaselget nõusolekut igal OS-il kontrollitakse

`REDIACC_ALLOW_GRAND_REPO` ja `REDIACC_ALLOW_CLUSTER_OPS` mõlemad sõltuvad pärilusahela kontrollimisest, et tõendada, et nõusoleku seadis inimene, mitte ei süstinud agent. Kontroll töötab Linuxis, macOS-is ja Windowsis, kuid tunnistaja, mida see loeb, erineb platvormiti, nagu ka garantii tugevus:

| Platvorm | Tunnistaja | Tugevus |
|---|---|---|
| Linux | `/proc/<pid>/environ` iga protsessi jaoks ahelas ülespoole | Exec-ajahetkese hetktõmmis, kerneli poolt serveeritud. Protsess ei saa tagantjärele muuta, millega see käivitati. |
| macOS | `kern.procargs2` sysctl, loetakse väikese abiprogrammi poolt, mis on sisse ehitatud `rdc`-sse | Sama exec-ajahetkese hetktõmmise omadus nagu Linuxis. Loetav oma protsesside jaoks ilma root-õigusteta. |
| Windows | Iga esivanema protsessi live-keskkonna plokk (PEB), loetud sama abiprogrammiga, PID-taaskasutuse kaitsega | Nõrgem: Windows ei säilita exec-ajahetkese hetktõmmist, nii et kontroll loeb praegust mälu. Esivanemate all korrupteerimine on endiselt muutumatu normaal agendi käskude poolt, kuid tunnistaja pole kerneli-külmutatud nagu Linuxis ja macOS-is. |

macOS-il ja Windowsil käivitab CLI lugemiseks oma komplektis oleva `renet` binaarfaili; abiprogramm teatab, milliseid jälgitavaid muutujaid iga esivanem kannab, ja kogu otsustusloogika jääb CLI-sse. Kui abiprogramm puudub, on aegunud või ebaõnnestub mis tahes põhjusel, ei saa CLI nõusolekut kontrollida ja **ebaõnnestub turvaliselt suletuna**: nõusolek lükatakse tagasi ja viga ütleb, et kontroll polnud saadaval, mitte et midagi oleks valesti tehtud. Töötav paigaldus ei näita seda teadet kunagi; `rdc` uuesti paigaldamine taastab abiprogrammi.

Mis jääb tõeks igal platvormil: nõusolek peab agendi protsessi keskkonnas juba olemas olema, kui see käivitub. See eksporditakse terminalis ja alles siis käivitatakse agent. Agent, kes seab muutuja seansi keskel, lükatakse tagasi.

## Auditi logi

Iga muudatus, iga keeldumine, iga `--reveal` grant kirjutab JSONL-rea faili `~/.config/rediacc/audit.log.jsonl` (õigus `0600`, rotatsioon 10 MB juures). Iga rida on räsiaheldatud: selle väli `prevHash` on `sha256("<eelmine rida>")`. Mis tahes rea rikkumine katkestab ahela kõigil järgnevatel ridadel.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### Vaatamine

```bash
# Loetleb hiljutised kanded
rdc config audit log --since 24h

# Filtreerib pointeri glob'i järgi
rdc config audit log --path '/credentials/*'

# Ainult agendist pärinevad kanded
rdc config audit log --actor agent

# Voogedastab uued kanded reaalajas (peatamiseks Ctrl+C)
rdc config audit tail

# Kontrollib, kas räsiahel on terve
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   VÕI
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### Mida auditi logis kunagi ei esine

- Salaväljade lihttekstväärtused
- Paroolid, tokenid, SSH-võtmed
- Vana/uue väärtuse `--current` eeltingimuse lahknevused (ainult 8-kohaline kokkuvõtte eesliide)

Logi on ohutu jagamiseks turvaülevaatajaga või veaportaalis esitamiseks.

## Käitumusliku mudeli piirid

Agendi turvamehhanismid on **käitumuslikud, mitte krüptograafilised**. Sihikindel või suunatud agent, mis töötab sama UID-ga kui konfiguratsioonifail, saab alati teha `cat ~/.config/rediacc/rediacc.json` ja lugeda lihtteksti, kuna fail on protsessile loetav.

Tõeliseks krüptograafiliseks jõustamiseks kasuta [krüpteeritud konfiguratsioonisalve](/et/docs/config-storage): saladused elavad serveripoolel, iga tundlik väli kannab välja kohast HMAC-sidet ja konto töötaja keeldub kirjutustest, mille `--current` eeltingimus ei kata selle salvestatut räsiga. Server ei näe kunagi lihtteksti (null-teadmine), kuid ta jõustab värava.

Kohalike failide puhul on lihtne tee turvaline tee. Kaugmälu puhul on ka ümbersõidutee krüptograafiliselt raske.

## Mida Rediacc ei isoleeri

Sellel lehel olevad agendi turvamehhanismid kaitsevad Rediacc oma infrastruktuuri: konfiguratsioonifaili, repo-kohast Dockeri daemoni, LUKS-krüpteeritud repositooriumi andmeid, ulatustatud SSH-liivakasti. Need ei kaitse väliseid teenuseid, mille volitused su repositoorium hoiab.

Repositooriumi fork on vanema köite BTRFS-reflink. Kõik, mis asub vanemaga kettal, on fork'is bait-identsne: kood, andmed ja `.env`-failid ühesuguselt. Kui su repositoorium sisaldab `STRIPE_LIVE_KEY`-d, `AWS_ACCESS_KEY_ID`-d, Railway API-tokenit või mis tahes muud pikaajalise kolmanda osapoole teenuse volitust, pärib fork selle. Fork'i liivakastis tegutsev agent saab seda faili lugeda, väärtust eksfiltreerida või kasutada kolmanda osapoole API kutsumiseks. Kolmanda osapoole teenusel pole võimalust teada, et kõne tuli fork'ist, mitte tootmisest.

See on jagatud vastutuse piir:

| Piir | Omanik |
|---|---|
| Repositooriumi andmed, ühenduspunkt-nimeruum, Dockeri ulatus, agendi turvamehhanismid, auditi logi, juurutusaegne saladuste süstimine | Rediacc |
| Rakenduse kood, mis neid saladusi kasutab, ja kõik ehitusajal pilti lisatud volitused | Repositooriumi arendaja |

Peamine leevendus on sisseehitatud: **[repo-kohased saladused](/et/docs/repositories#secrets)** on salvestatud eraldiseisvasse tasandisse krüpteeritud repositooriumi pildist ja neid ei kopeerita fork-piiri üle. Fork'i konteinerid käivituvad tühja saladuste kaardiga ja identifitseerivad end väliste süsteemide jaoks erinevate põhisubjektidena kui vanem. Sea need käsuga `rdc repo secret set` (env-režiim compose interpoleerimiseks, faili-režiim tmpfs `secrets:` plokkideks). Muudatuste värav on sümmeetriline. Nii inimesed kui agendid peavad olemasoleva väärtuse üle kirjutamiseks või kustutamiseks esitama `--current` (passwd-stiilis eeltingimus); `--rotate-secret` (logitud pööramine) on alternatiiv terminalis olevale inimesele.

**Repo-vaheline isoleerimine on jõustatud.** Pahatahtlik või hooletu compose-fail repo B-s ei saa viidata repo A saladuste kataloogile. Renet'i compose-validaator keeldub kõvakoodiliselt igast `secrets: file:`, `configs: file:` või `env_file:` teest, mis viitab väljapoole praeguse repo `${REDIACC_NETWORK_ID}` kataloogi, ja keeldumine EI ole `--unsafe`-ga ületatav. Kaitsemehaanikate kihistamine: Landlock-liivakast Rediaccfile bash-alamprotsessi ümber piirab failisüsteemi lugemist ainult praeguse võrgu saladuste kataloogiga, nii et `cat /var/run/rediacc/net-<other>/secrets/X` pahatahtlikust Rediaccfile'ist ebaõnnestub EACCES-iga kerneli tasemel. Sama kehtib Docker API kohta: iga repo Dockeri sokkelt teenindab renet'i poliitikaproksi, mis keeldub `403`-ga `--privileged`-ist, hosti `pid`-ist, `ipc`-st ja `uts`-ist, seadmetaotlustest ning sidumistest, mis ulatuvad teise repo käituskeskkonna või andmeteni. Seega ei saa konteiner, millel on `${DOCKER_SOCKET}`, API kaudu teise reponi jõuda, ning kontrollitakse mitte ainult compose-faili. Sidumisreeglit saab laiendada ainult operaator, nimetatud hosti kataloogide jaoks, root'ile kuuluva loaga, kuhu ükski konteiner kirjutada ei saa.

Kaks täiendavat mustrit sulgevad äärjuhtumid:

1. **Ära lisa tootmisvolitusi repositooriumi failisüsteemi.** `.env`-fail, mis on pildile commititud, või volitused, mis on säilitatud mahule `up()` käigus, reflingatakse fork'ile. Repo-kohaste saladuste funktsioon kaitseb ainult saladuste tasandis hoitavaid väärtusi. See ei saa tagantjärele kaitsta baite, mis juba asuvad LUKS-pildis. Olemasolevate repo-de puhul baked-in `.env`-failidega tõsta need käsitsi repo-kohastesse saladustesse.
2. **Piira fork'i väljaminevat võrku eBPF-egress-filtreerimisega**, nii et fork saab jõuda ainult localhost'i ja eksplitsiitsete liivakasti lõpp-punktideni. Rediacc repo-kohane võrgueristamine on alus; fork-kohased egress-allowlist'id pole täna ehitatud, kuid tee on avatud.

Rediacc hoolitseb juurutusaegse süstimise, fork-vahelise eristamise ja repo-vahelise eristamise eest. "Ära lisa pildile" pool on sinu kanda.

## Kiiretseptid

### Lase agendil töötada ühe grand-repoga

```bash
# Inimesena, enne agendi käivitamist:
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # või cursor, gemini jne.
```

Agent saab nüüd muuta `gitlab`-i seal, kus poliitika lubab grand-repode muutmist, ega ühtegi teist grand-repot. Hävitav muudatus, näiteks `repo delete gitlab`, küsib ikkagi kinnitust.

### Pööra pilvetoken ilma vana väärtust teadmata

```bash
# Inimesena, interaktiivses terminalis:
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

Pööramine ilma `--current`-ita jääb inimese käsutusse. Agent, kes teab praegust väärtust, kasutab selle asemel käsku `rdc config field set --current`.

### Avasta, milliseid välju agendil on lubatud puudutada

```bash
rdc config field list --sensitive --output json
```

Tagastab iga pointeri malli, selle liigi (`secret` / `credential` / `pii` / `identifier`) ja kas see on sidutud serveripoolse HMAC-ümbrikusse.

## Vt ka

- [Tehisintellekti agentide integreerimise ülevaade](/et/docs/ai-agents-overview): kõrgetasemeline tutvustus
- [MCP server](/et/docs/ai-agents-mcp): kohalik ja kaug-MCP, load ja nende sõnaselged nõusolekud
- [Turvamudel](/et/docs/security-model): poliitikakirje ja see, kes seda kirjutada tohib
- [Claude Code seadistus](/et/docs/ai-agents-claude-code): integratsiooni mall
- [JSON-väljundi ümbrik](/et/docs/ai-agents-json-output): masintöötlemiseks sobivad vastused
- [Krüpteeritud konfiguratsioonisalv](/et/docs/config-storage): serveripoolne krüptograafiline jõustamine
- [Konto turvalisus](/et/docs/account-security): operaatorikeskne turvahoiak
