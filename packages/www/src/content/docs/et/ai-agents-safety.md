---
title: AI agendi ohutus ja turvamehhanismid
description: >-
  Kuidas Rediacc CLI takistab AI-koodiabistavatel rakendustel saladusi lekkitada,
  volitusi üle kirjutada või õigusi eskaleerida. Teadmisväravad,
  redakteerimine, päritolu-kontrollitud ülekanded ja räsiahelaga auditi logi.
category: Concepts
order: 35
language: et
---

Kui Claude Code, Cursor, Gemini CLI, Copilot CLI või mõni muu AI-koodiabistaja juhib `rdc`-d, kohtleb CLI seda klaviatuuri taga olevast inimesest erinevalt. Sellel lehel selgitatakse, mida agent saab teha, mida mitte, ja kuidas turvamehhanismid kehtivad isegi siis, kui agent üritab neist mööda rääkida.

## Kiirviide: mida agendid saavad ja ei saa teha

| Toiming | Agendi vaikeväärtus | Kuidas konkreetse kasutusjuhu jaoks avada |
|---|---|---|
| `rdc config show` (redakteeritud) | ✅ lubatud |  |
| `rdc config field get --pointer <pointer>` (redakteeritud asendaja või kokkuvõte) | ✅ lubatud |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ lubatud |  |
| `rdc config field set --pointer <pointer>` (avalik väli) | ✅ lubatud |  |
| `rdc config field set --pointer <pointer>` (tundlik väli, **korrektse `--current`-ga**) | ✅ lubatud |  |
| `rdc config edit --dump` (redakteeritud JSONC) | ✅ lubatud |  |
| `rdc config audit {log, tail, verify}` | ✅ lubatud |  |
| `rdc config field set --pointer <pointer>` (tundlik väli, ilma `--current`-ta) | 🔴 keeldutud | Esita `--current "<vana väärtus>"` |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 keeldutud | Kasuta `--digest` asemel |
| `rdc config show --reveal` | 🔴 keeldutud | Kasuta tavalist `rdc config show` |
| `rdc config edit` (interaktiivne redaktor) | 🔴 keeldutud | Inimene seab `REDIACC_ALLOW_CONFIG_EDIT=*` enne agendi käivitamist |
| `rdc config edit --apply <file>` | 🔴 keeldutud | Sama ülekate |
| `rdc config field rotate --pointer <pointer>` | 🔴 keeldutud | Sama ülekate; kasutab interaktiivset kinnitust |
| `rdc term connect -m <machine>` (otsene masina SSH) | 🔴 keeldutud | Tee esmalt repo fork ja ühenda fork'iga |

Kõik, milles agendile keeldutakse, kirjutatakse auditi logisse koos `outcome: refused` ja põhjusega.

## Kuidas agendid tuvastatakse

CLI käsitleb protsessi agendina, kui kehtib mõni järgmistest:

- Üks järgmistest on seatud väärtusele `"1"`: `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI`, või `CURSOR_TRACE_ID` on üldse seatud.
- Linuxis: mõni vanemaprotsess pärilusahelas omab ühte neist muutujatest oma keskkonnas (via `/proc/<pid>/environ`). Isegi kui agent kustutab oma muutujad käsuga `env -i` või ümbrisskriptiga, annab vanemate ahel CLI-le teada, kes selle käivitas.

Tuvastamine toimub ühe korra protsessi kohta ja vahemälustatakse. Seda ei saa keelata.

## Teadmisvärava mudel

Tundlikud muudatused järgivad `passwd(1)` konventsiooni: saladuse muutmiseks tõesta, et sa juba teadsid seda. **Sümmeetriline inimeste ja agentide jaoks.** Mõlemad läbivad sama värava. Puudub "istun klaviatuuri taga" ümbersõit.

- Soovid vahetada API tokenit, mis asub aadressil `/credentials/cfDnsApiToken`?
- CLI küsib: "mis on praegune väärtus?"
- Agent (või inimene) esitab lihtteksti `--current "$OLD"` kaudu. CLI räsistab `$OLD` SHA-256-ga ja võrdleb praegu salvestatud väärtuse kokkuvõttega. Kattuvus: kirjutamine läbi. Lahknevus: keeldutud, logitud auditisse.
- Eelneva väärtuse kontrollimata pööramiseks kasuta `--rotate-secret` (vastastikku välistatud `--current`-ga). See logitakse auditisse pööramisena.

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
          "run": "rdc repo secret get --name mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Agendid peaksid edastama `next.options[].run` sõna-sõnalt inimesele, mitte koostama ise käske.** See väldib tõrkeviisi "agent leiutab käsu, mida pole olemas" ja hoiab operaatori kontrolli tegeliku toimingu üle.

### Töötatud näide

```bash
# Avastab redakteerimise asendaja lühikokkuvõtte (ohutu agentide jaoks).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Katse üle kirjutada ilma tõendita: keeldutud.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Praeguse lihtteksti esitamine: lubatud.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Kui agendil polnud kunagi `$OLD_CF_TOKEN`, ei saa ta eeltingimust täita ja pööramine lükatakse tagasi. Kasutaja, kellel see on, saab seda siiski teha kas redaktori kaudu või `--current` kasutades oma shellist.

## Vaikimisi redakteerimine

Iga `rdc` käsk, mis loeb tundlikku olekut: `config show`, `config field get`, `config machine list`, `config edit --dump`: tagastab salaväljade jaoks **redakteerimise asendajad**, mitte lihtteksti:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Asendaja 8-kohaline kuueteistkümnendarvu sufiks on `sha256(canonicalize(value))` esimesed 8 märki: piisab kahe erineva väärtuse esmapilgul eristamiseks, kuid mitte ümberpööramiseks. Agent saab asendajat kasutada väärtuse muutumise jälgimiseks ilma seda kunagi nägemata.

`--reveal` tühistab redakteerimise inimestele interaktiivsel TTY-l. Agentidele keeldutakse olenemata TTY olekust. Iga grant kirjutab auditi kande `reveal_granted`; iga keeldumine kirjutab kande `refused` koos toimiva agendi signaalidega.

## `REDIACC_ALLOW_CONFIG_EDIT` ülekate

Mõned toimingud: interaktiivne redaktor, `--apply`, `field rotate`: on mõeldud inimestele ja neil pole agendile ohutut teed. Kui soovid aktiivselt, et agent ühe neist teeks, sea:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # täielik ümbersõit
# või
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (komaga eraldatud ulatuse glob-mustrid: * metamärgid lubatud segmendi kaupa)
```

...ja agent pärib selle.

**Oluline detail**: ülekate peab ilmuma protsessis, mis asub pärilusahelas agendist **ülalpool**. Kui agent seab selle oma keskkonnas (või käivitatud alamshell'is), keeldub CLI ja teatab sellest:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

Mõju: agent ei saa seansi keskel `export REDIACC_ALLOW_CONFIG_EDIT='*'` käivitades turvamehhanismist mööda rääkida. Ainult vanemprotsess (sina, oma terminalis, enne agendi käivitamist) saab selle ukse avada.

## Platvormi tugi: ainult Linux ülekannete jaoks

`REDIACC_ALLOW_CONFIG_EDIT` ja `REDIACC_ALLOW_GRAND_REPO` mõlemad sõltuvad pärilusahela kontrollimisest, et tõendada, et ülekate seati sinu poolt, mitte agendi poolt. Kontroll loeb `/proc/<pid>/environ` iga protsessi jaoks ahelas ülespoole. See fail seatakse kerneli poolt exec-ajal ja protsess ise ei saa seda muuta, seega on vanema shelli keskkond võltsimiskindel tunnistaja.

See fail pole macOS-il ega Windowsil olemas. Kuna legitiimsust pole võimalik kontrollida, sulgeb CLI vaikimisi turvalise oleku. Isegi kui seadistad ülekatte oma shellis õigesti enne agendi käivitamist, lükatakse ülekate tagasi. Veateade ütleb täpselt, mida teha:

> The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. … To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).

Praktikas pole mitte-Linuxi kasutajatele ümbersõitu fork-esmase töövoo alt. See on tahtlik. Agendid suunatakse läbi liivakasti, mille taha nad ei saa jõuda, olenemata sellest, kuidas neid käsutati. Kui vajad ülekannet, käivita oma agent WSL-is, Linuxi konteineris või Linuxi VM-is; vastasel juhul tööta fork'il.

## Auditi logi

Iga muudatus, iga keeldumine, iga `--reveal` grant kirjutab JSONL-rea faili `~/.config/rediacc/audit.log.jsonl` (õigus `0600`, rotatsioon 10 MB juures). Iga rida on räsiaheldatud: selle väli `prevHash` on `sha256("<eelmine rida>")`. Mis tahes rea rikkumine katkestab ahela kõigil järgnevatel ridadel.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
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

Tõeliseks krüptograafiliseks jõustamiseks kasuta [krüpteeritud konfiguratsioonisalve](/et/docs/config-storage): saladused elavad serveripoolel, iga tundlik väli kannab välja kohast HMAC-sidet ja konto töötaja keeldub kirjutustest, mille `--current` eeltingimus ei kata selle salvestatut räsiga. Server ei näe kunagi lihtteksti: null-teadmine: kuid ta jõustab värava.

Kohalike failide tee on "lihtne tee on turvaline". Kaugmälu tee on "raske tee on ka raske".

## Mida Rediacc ei isoleeri

Sellel lehel olevad agendi turvamehhanismid kaitsevad Rediacc oma infrastruktuuri: konfiguratsioonifaili, repo-kohast Dockeri daemoni, LUKS-krüpteeritud repositooriumi andmeid, ulatustatud SSH-liivakasti. Need ei kaitse väliseid teenuseid, mille volitused su repositoorium hoiab.

Repositooriumi fork on vanema köite BTRFS-reflink. Kõik, mis asub vanemaga kettal, on fork'is bait-identsne: kood, andmed ja `.env`-failid ühesuguselt. Kui su repositoorium sisaldab `STRIPE_LIVE_KEY`-d, `AWS_ACCESS_KEY_ID`-d, Railway API-tokenit või mis tahes muud pikaajalise kolmanda osapoole teenuse volitust, pärib fork selle. Fork'i liivakastis tegutsev agent saab seda faili lugeda, väärtust eksfiltreerida või kasutada kolmanda osapoole API kutsumiseks. Kolmanda osapoole teenusel pole võimalust teada, et kõne tuli fork'ist, mitte tootmisest.

See on jagatud vastutuse piir:

| Piir | Omanik |
|---|---|
| Repositooriumi andmed, ühenduspunkt-nimeruum, Dockeri ulatus, agendi turvamehhanismid, auditi logi, juurutusaegne saladuste süstimine | Rediacc |
| Rakenduse kood, mis neid saladusi kasutab, ja kõik ehitusajal pilti lisatud volitused | Repositooriumi arendaja |

Peamine leevendus on sisseehitatud: **[repo-kohased saladused](/et/docs/repositories#secrets)** on salvestatud eraldiseisvasse tasandisse krüpteeritud repositooriumi pildist ja neid ei kopeerita fork-piiri üle. Fork'i konteinerid käivituvad tühja saladuste kaardiga ja identifitseerivad end väliste süsteemide jaoks erinevate põhisubjektidena kui vanem. Sea need käsuga `rdc repo secret set` (env-režiim compose interpoleerimiseks, faili-režiim tmpfs `secrets:` plokkideks). Muudatuste värav on sümmeetriline. Nii inimesed kui agendid peavad olemasoleva väärtuse üle kirjutamiseks või kustutamiseks esitama `--current` (passwd-stiilis eeltingimus) või `--rotate-secret` (logitud pööramine).

**Repo-vaheline isoleerimine on jõustatud.** Pahatahtlik või hooletu compose-fail repo B-s ei saa viidata repo A saladuste kataloogile. Renet'i compose-validaator keeldub kõvakoodiliselt igast `secrets: file:`, `configs: file:` või `env_file:` teest, mis viitab väljapoole praeguse repo `${REDIACC_NETWORK_ID}` kataloogi, ja keeldumine EI ole `--unsafe`-ga ületatav. Kaitsemehaanikate kihistamine: Landlock-liivakast Rediaccfile bash-alamprotsessi ümber piirab failisüsteemi lugemist ainult praeguse võrgu saladuste kataloogiga, nii et `cat /var/run/rediacc/secrets/<other>/X` pahatahtlikust Rediaccfile'ist ebaõnnestub EACCES-iga kerneli tasemel.

Kaks täiendavat mustrit sulgevad äärjuhtumid:

1. **Ära lisa tootmisvolitusi repositooriumi failisüsteemi.** `.env`-fail, mis on pildile commititud, või volitused, mis on säilitatud mahule `up()` käigus, reflingatakse fork'ile. Repo-kohaste saladuste funktsioon kaitseb ainult saladuste tasandis hoitavaid väärtusi. See ei saa tagantjärele kaitsta baite, mis juba asuvad LUKS-pildis. Olemasolevate repo-de puhul baked-in `.env`-failidega tõsta need käsitsi repo-kohastesse saladustesse.
2. **Piira fork'i väljaminevat võrku eBPF-egress-filtreerimisega**, nii et fork saab jõuda ainult localhost'i ja eksplitsiitsete liivakasti lõpp-punktideni. Rediacc repo-kohane võrgueristamine on alus; fork-kohased egress-allowlist'id pole täna ehitatud, kuid tee on avatud.

Rediacc hoolitseb juurutusaegse süstimise, fork-vahelise eristamise ja repo-vahelise eristamise eest. "Ära lisa pildile" pool on sinu kanda.

## Kiiretseptid

### Luba agendil pöörata üht pilvekontot

```bash
# Sina, enne agendi käivitamist:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # või cursor, gemini jne.
```

Nüüd saab agent teha `config field rotate /credentials/cfDnsApiToken --new …`, kuid ikka ei saa redigeerida `/credentials/ssh/privateKey` ega avada interaktiivset redaktorit.

### Luba agendil teha üks lai konfiguratsiooniredakteerimise seanss

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

Agent saab avada `rdc config edit`, kasutada `--reveal` ja käivitada `field rotate`. Iga toiming logitakse ikka auditisse koos `actor.kind: agent` ja signaaliga `CLAUDECODE`.

### Avasta, milliseid välju agendil on lubatud puudutada

```bash
rdc config field list --sensitive --output json
```

Tagastab iga pointeri malli, selle liigi (`secret` / `credential` / `pii` / `identifier`) ja kas see on sidutud serveripoolse HMAC-ümbrikusse.

## Vt ka

- [Tehisintellekti agentide integreerimise ülevaade](/et/docs/ai-agents-overview): kõrgetasemeline tutvustus
- [Claude Code seadistus](/et/docs/ai-agents-claude-code): integratsiooni mall
- [JSON-väljundi ümbrik](/et/docs/ai-agents-json-output): masintöötlemiseks sobivad vastused
- [Krüpteeritud konfiguratsioonisalv](/et/docs/config-storage): serveripoolne krüptograafiline jõustamine
- [Konto turvalisus](/et/docs/account-security): operaatorikeskne turvahoiak
