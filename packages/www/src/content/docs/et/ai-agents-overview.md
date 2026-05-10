---
title: Tehisintellekti agentide integreerimise ülevaade
description: Kuidas AI-koodiabistavad rakendused nagu Claude Code, Cursor ja Cline integreeruvad Rediacc infrastruktuuriga autonoomse juurutamise ja haldamise jaoks.
category: Guides
order: 30
language: et
---

AI-koodiabistavad rakendused saavad `rdc` CLI kaudu Rediacc infrastruktuuri autonoomselt hallata. See juhend käsitleb integreerimislähenemisi ja esmaste sammude tegemist.

## Miks isehostatav + AI agendid

Rediacc arhitektuur on loodud agentidega hästi toimima:

- **CLI-esmane**: Kõik toimingud on `rdc` käsud, graafilist liidest pole vaja
- **SSH-põhine**: Protokoll, mida agendid treeningandmetest kõige paremini tunnevad
- **JSON-väljund**: Kõik käsud toetavad `--output json` ühtse ümbrikuga
- **Dockeri isoleerimine**: Iga repositoorium saab oma daemoni ja võrgunimeruumi
- **Skriptitav**: `--yes` jätab kinnitused vahele, `--dry-run` näitab eelvaate hävitavatest toimingutest

## Integreerimislähenemised

### 1. AGENTS.md / CLAUDE.md mall

Kiireim viis alustamiseks. Kopeeri meie [AGENTS.md mall](/et/docs/agents-md-template) oma projekti juurekausta:

- `CLAUDE.md` Claude Code'i jaoks
- `.cursorrules` Cursori jaoks
- `.windsurfrules` Windsurf'i jaoks

See annab agendile täieliku konteksti saadaolevate käskude, arhitektuuri ja konventsioonide kohta.

### 2. JSON-väljundi konveier

Kui agendid kutsuvad `rdc` alamshell'is, lülitub väljund automaatselt JSON-ile (mitte-TTY tuvastus). Iga JSON-vastus kasutab ühtset ümbrikku:

```json
{
  "success": true,
  "command": "machine query",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

Veastavused sisaldavad välju `retryable` ja `guidance`:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. Agendi võimaluste avastamine

Alamkäsk `rdc agent` pakub struktureeritud introspektion:

```bash
# Loetleb kõik käsud argumentide ja valikutega
rdc agent capabilities

# Näitab konkreetse käsu üksikasjalikku skeemi
rdc agent schema --command "machine query"

# Täidab käsu JSON-sisendiga
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Agentidele mõeldud põhilipud

| Lipp | Eesmärk |
|------|---------|
| `--output json` / `-o json` | Masintöötlemiseks sobiv JSON-väljund |
| `--yes` / `-y` | Jätab interaktiivsed kinnitused vahele |
| `--quiet` / `-q` | Peidab informatiivsed stderr-väljundid |
| `--fields name,status` | Piirab väljundit konkreetsete väljadega |
| `--dry-run` | Näitab hävitavate toimingute eelvaate ilma neid täitmata |

## Ohutus ja turvamehhanismid

CLI kohtleb AI agente klaviatuuri taga istuvast inimesest erinevalt. Tundlikud toimingud nõuavad eelteadmiste tõendamist (lipp `--current`), interaktiivsed redigeerimisvoood lükatakse vaikimisi tagasi ja iga tagasilükkamine logitakse auditisse. Viide [AI agendi ohutus ja turvamehhanismid](/et/docs/ai-agents-safety) katab täieliku tulemüüri tabeli, teadmisvärava mudeli, `REDIACC_ALLOW_CONFIG_EDIT` ulatuse ülekattena ja räsiahelaga auditi logi.

## Järgmised sammud

- [AI agendi ohutus ja turvamehhanismid](/et/docs/ai-agents-safety), mida agendid saavad ja ei saa teha, teadmisvärav, auditi logi
- [Claude Code seadistusjuhend](/et/docs/ai-agents-claude-code), samm-sammult Claude Code'i seadistamine
- [Cursor seadistusjuhend](/et/docs/ai-agents-cursor), Cursori IDE integreerimine
- [JSON-väljundi viide](/et/docs/ai-agents-json-output), täielik JSON-väljundi dokumentatsioon
- [AGENTS.md mall](/et/docs/agents-md-template), kopeerimiseks valmis agendi seadistuse mall
