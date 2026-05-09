---
title: Cursori seadistusjuhend
description: Konfigureerige Cursor IDE töötama Rediacc infrastruktuuriga .cursorrules ja terminali integratsiooni abil.
category: Guides
order: 32
language: et
---

Cursor integreerub Rediacciga terminali käskude ja `.cursorrules` konfiguratsioonifaili kaudu.

## Kiirseadistus

1. Installige CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Kopeerige [AGENTS.md mall](/et/docs/agents-md-template) oma projekti juurkausta nimena `.cursorrules`
3. Avage projekt Cursoris

Cursor loeb käivitamisel `.cursorrules`-i ja kasutab seda AI-assisteeritud arenduse kontekstina.

## .cursorrules konfiguratsioon

Looge projekti juurkausta `.cursorrules` Rediacc infrastruktuuri kontekstiga. Täieliku versiooni jaoks vaadake [AGENTS.md malli](/et/docs/agents-md-template).

Kaasatavad põhisektsioonid:

- CLI tööriista nimi (`rdc`) ja installimine
- Levinud käsud koos lipuga `--output json`
- Arhitektuuri ülevaade (repositooriumi eraldatus, Dockeri deemonid)
- Terminoloogia reeglid (adapterid, mitte režiimid)

## Terminali integratsioon

Cursor saab `rdc` käske käivitada integreeritud terminali kaudu. Levinud mustrid:

### Oleku kontrollimine

Küsige Cursorilt: *"Kontrolli minu tootmisserveri olekut"*

Cursor käivitab terminalis:
```bash
rdc machine query --name prod-1 -o json
```

### Muudatuste juurutamine

Küsige Cursorilt: *"Juuruta uuendatud nextcloud'i konfiguratsioon"*

Cursor käivitab terminalis:
```bash
rdc repo up --name nextcloud -m prod-1 --yes
```

### Logide vaatamine

Küsige Cursorilt: *"Näita mulle hiljutisi mail-konteineri logisid"*

Cursor käivitab terminalis:
```bash
rdc term connect -m prod-1 -r mail -c "docker logs mail-postfix --tail 100"
```

## Tööruumi seaded

Meeskonna projektide jaoks lisage Rediacc-spetsiifilised Cursori seaded faili `.cursor/settings.json`:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## Näpunäited

- Cursori Composer-režiim sobib hästi mitmeetapiliste infrastruktuuriülesannete jaoks
- Kasutage Cursori vestluses `@terminal`, et viidata hiljutisele terminaliväljundile
- Käsk `rdc agent capabilities` annab Cursorile täieliku käsuviite
- Kombineerige `.cursorrules` failiga `CLAUDE.md` maksimaalse ühilduvuse tagamiseks eri AI-tööriistade vahel
