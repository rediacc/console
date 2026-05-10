---
title: Claude Code'i ülesseadmise juhend
description: Üksikasjalik samm-sammuline juhend Claude Code'i häälestamiseks Rediacc infrastruktuuri autonoomseks haldamiseks.
category: Guides
order: 31
language: et
---

Claude Code töötab Rediacciga natiivselt `rdc` CLI kaudu. See juhend käsitleb seadistust, lubasid ja levinud töövoogusid.

> **Turvalisus ennekõike**: Enne agendi ühendamist millega, mis puutub kokku saladustega, lugege [AI-agendi turvalisus ja kaitsemehhanismid](/et/docs/ai-agents-safety). `rdc` all töötav Claude Code tuvastatakse agendina. Tundlikud muutmised nõuavad kas `--current <eelmine-väärtus>` (passwd-stiilis eeltingimus) või `--rotate-secret` (kinnitatud pööramine, auditeeritud). Sümmeetriline nii inimestele kui agentidele. Interaktiivne redaktor, `--reveal` ja otsene masina SSH keeldutakse vaikimisi, välja arvatud juhul, kui avate need sõnaselgelt `REDIACC_ALLOW_CONFIG_EDIT` kaudu. Kui eeltingimus ebaõnnestub, annab JSON-ümbriku väli `errors[].next.options[].run` agendile täpse CLI-käsu, mida soovitada kasutajale käivitada. Edastage see sõna-sõnalt.

## Kiirseadistus

1. Installige CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Kopeerige [AGENTS.md mall](/et/docs/agents-md-template) oma projekti juurkausta nimena `CLAUDE.md`
3. Käivitage Claude Code projekti kaustas

Claude Code loeb käivitamisel `CLAUDE.md`-d ja kasutab seda püsiva kontekstina kõigi suhtluste jaoks.

## CLAUDE.md konfiguratsioon

Paigutage see oma projekti juurkausta. Täieliku versiooni jaoks vaadake [AGENTS.md malli](/et/docs/agents-md-template). Põhisektsioonid:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine query --name <machine> -o json
- Deploy: rdc repo up --name <repo> -m <machine> --yes
- Containers: rdc machine containers --name <machine> -o json
- Health: rdc machine health --name <machine> -o json
- SSH: rdc term connect -m <machine> [-r <repo>]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Tööriistaload

Claude Code küsib luba `rdc` käskude käivitamiseks. Saate levinud toimingud eelnevalt lubada, lisades oma Claude Code'i seadetesse:

- Lubage `rdc machine query *`, kirjutuskaitstud olekukontrollid
- Lubage `rdc machine containers *`, konteinerite loetlemine
- Lubage `rdc machine health *`, terviskontrollid
- Lubage `rdc config repository list`, repositooriumide loetlemine

Hävitavate toimingute puhul (`rdc repo up`, `rdc repo delete`) küsib Claude Code alati kinnitust, välja arvatud juhul, kui lubate need sõnaselgelt.

## Näidistöövood

### Infrastruktuuri oleku kontrollimine

```
Teie: "Mis on prod-1 olek?"

Claude Code käivitab: rdc machine query --name prod-1 -o json
→ Kuvab masina oleku, repositooriumid, konteinerid, teenused
```

### Repositooriumi juurutamine

```
Teie: "Juuruta mail-repo prod-1-le"

Claude Code käivitab: rdc repo up --name mail -m prod-1 --dry-run -o json
→ Näitab, mis juhtuks
Claude Code käivitab: rdc repo up --name mail -m prod-1 --yes
→ Juurutab repositooriumi
```

### Konteineri probleemide diagnoosimine

```
Teie: "Miks on nextcloud'i konteiner ebaterve?"

Claude Code käivitab: rdc machine containers --name prod-1 -o json --fields name,status,repository
→ Loetleb konteinerite olekud
Claude Code käivitab: rdc term connect -m prod-1 -c "docker logs nextcloud-app --tail 50"
→ Kontrollib hiljutisi logisid
```

### Failide sünkroonimine

```
Teie: "Laadi kohalik konfiguratsioon mail-repo-sse üles"

Claude Code käivitab: rdc repo sync upload -m prod-1 -r mail -l ./config --dry-run
→ Näitab, milliseid faile sünkroonitaks
Claude Code käivitab: rdc repo sync upload -m prod-1 -r mail -l ./config
→ Sünkroonib failid
```

## Näpunäited

- Claude Code tuvastab automaatselt mitte-TTY-keskkonna ja lülitub JSON-väljundile, enamikul juhtudel ei ole vaja `-o json` täpsustada
- Kasutage `rdc agent capabilities`, et lasta Claude Code'il avastada kõik saadaolevad käsud
- Kasutage `rdc agent schema "käsu nimi"` üksikasjalike argumentide ja valikute info jaoks
- Lipp `--fields` aitab kontekstiakna kasutust vähendada, kui vajate ainult konkreetseid andmeid
