---
title: RDC CLI petuleht
description: "Kiirviide rdc käskudele: konfiguratsioonid, hoidlad, masinad, sünkroonimine ja konteinerid. Täielik valikute kogum: lisa --help käskule."
category: Guides
order: 3
language: et
sourceHash: "ee96cb869dcc2639"
sourceCommit: "b8e332b73573133a282b5c508bc049af1fbeb581"
---

# RDC CLI petuleht

Siia pole loetletud kõiki `rdc` käske, vaid ainult need, mis igal juurutamisel ette tulevad. Täielike valikute saamiseks käivita mis tahes käsk `--help`-iga. Erijuhud ja harva kasutatavad valikud asuvad täielikul viitel.

## Hoidla elutsükkel

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc repo create <repo> -m <machine>` | Loo uus hoidla masinal |
| `rdc repo up <repo>@<machine>` | Juuruta või uuenda hoidlat |
| `rdc repo down <repo>@<machine>` | Peata hoidla |
| `rdc repo delete <repo>@<machine>` | Kustuta hoidla |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Tee hoidlast fork (peaaegu kohene, BTRFS reflink) |
| `rdc repo promote <repo>:<tag>` | Tõsta valideeritud fork emahoidla nime all tootmisse |
| `rdc repo list` | Loenda kõik hoidlad nime ja GUID-iga |

## Hoidlapõhised saladused

Ainult kirjutatavad juurutamisaegsed mandaadid. `get` tagastab ainult kontrollsumma. Väärtust ei tagastata kunagi. Täieliku juhendi leiad [Hoidlad § Saladused](/et/docs/repositories#secrets).

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Loo uus saladus (`--current ""` esmakirjutuse jaoks) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Kirjuta olemasolev saladus üle (passwd-stiilis eeltingimus) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Kirjuta üle eelmist väärtust kontrollimata (auditeerituna rotatsioonina) |
| `rdc repo secret list <repo>` | Loenda saladuste nimed + tarneviisid (kunagi mitte väärtusi ega kontrollsummasid) |
| `rdc repo secret get <repo> --key <KEY>` | Kuva saladuse kontrollsumma + viis (plaintext väärtust kunagi mitte) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Kustuta saladus |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Kustuta eelmist väärtust kontrollimata |

> Forkid ei päri saladusi. Määra need forkile sõnaselgelt käsuga `rdc repo secret set <repo>:<tag>`.

## Varundamine ja taastamine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc repo push <repo>@<machine> --to <storage>` | Lükka hoidla varukoopia mäluhoidlasse |
| `rdc repo pull <repo>@<machine> --from <storage>` | Taasta hoidla mäluhoidlast |
| `rdc repo push ... --bwlimit <limit>` | Piira rsync-i ribalaiust lükkamise ajal (nt `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Piira rsync-i ribalaiust tõmbamise ajal |
| `rdc repo push ... --checkpoint` | Tee konteinerite kontrollpunkt enne lükkamist |
| `rdc backup list --storage <storage>` | Loenda mäluhoidlas saadaolevad varukoopiad |
| `rdc backup snapshot <repo>` | Laadi üles tükksalvestuse tõmmis: kõigepealt kogu sisu, siis ainult muutunud rakud |
| `rdc backup snapshot <repo> --dry-run` | Planeeri tõmmis ilma üles laadimata; näitab, mis liiguks |
| `rdc backup verify <repo>` | Kinnita hoidla varunduse ankur tükksalvestuse vastu |
| `rdc backup usage` | Näita tükksalvestuses hoitud baite sinu kvoodi suhtes |
| `rdc backup manifests <repo>` | Loenda serverisse salvestatud tõmmiste sisukirjeldused |
| `rdc storage browse <storage>` | Sirvi mäluhoidla sisu |

## Hoidla migreerimine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Liiguta hoidla masinate vahel |
| `rdc repo migrate ... --provision` | Provisineeri sihtkohas enne üle kandmist |
| `rdc repo migrate ... --checkpoint` | Tee kontrollpunkt enne migreerimist |
| `rdc repo migrate ... --skip-dns` | Jäta DNS-uuendamine pärast migreerimist vahele |
| `rdc repo migrate ... --bwlimit <limit>` | Piira ülekande ribalaiust |

## Varundusstrateegiad

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Loo või uuenda nimega varundusstrateegiat |
| `rdc backup strategy list` | Loenda kõik defineeritud varundusstrateegiad |
| `rdc backup strategy show <name>` | Näita strateegia üksikasju |
| `rdc backup strategy remove <name>` | Eemalda strateegia |
| `rdc backup schedule -m <machine>` | Juuruta konfigureeritud varundusstrateegiad masinasse |

## Varundusoperatsioonid

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc backup schedule -m <machine>` | Juuruta seotud strateegiad systemd-taimeritena |
| `rdc backup schedule -m <machine> --dry-run` | Eelvaate taimeriüksused ilma juurutamata (tokenid maskeeritud) |
| `rdc backup run -m <machine>` | Käivita kõik seotud strateegiad kohe |
| `rdc backup run <name> -m <machine>` | Käivita konkreetne strateegia kohe |
| `rdc backup status -m <machine>` | Kuva taimeri olek ja hiljutised töötulemused |
| `rdc backup status <name> -m <machine>` | Kuva konkreetse strateegia olek |
| `rdc backup cancel -m <machine>` | Tühista töötavad varukoopiad |
| `rdc backup cancel <name> -m <machine>` | Tühista konkreetne töötav varukoopia |

## Masina haldamine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc machine status <machine>` | Täielik masina olek (süsteem, konteinerid, teenused, hoidlad, võrk) |
| `rdc machine status <machine> --system` | Ainult süsteemi teave |
| `rdc machine status <machine> --containers` | Ainult konteinerite loend |
| `rdc machine status <machine> --repositories` | Ainult hoidlate loend |
| `rdc machine status <machine> --services` | Ainult teenuste loend |
| `rdc machine status <machine> --network` | Ainult võrgoteave |
| `rdc machine status <machine> --block-devices` | Ainult plokiseadmete teave |
| `rdc machine list` | Loenda kõik masinad konfiguratsioonis |
| `rdc machine setup <machine>` | Käivita masina algne provisioneerimine |
| `rdc machine prune <machine>` | Eemalda kasutamata ressursid masinalt |
| `rdc machine deprovision <machine>` | Tühjenda masin täielikult |

## Terminal ja sünkroonimine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc term connect <machine>` | Ava SSH-terminal masinale |
| `rdc term connect <repo>@<machine>` | Ava SSH-terminal hoidlale (seab DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | Käivita käsk masinal |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Laadi üles üks või mitu kohalikku faili/kataloogi hoidlasse |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Laadi üles üks kohalik fail sõnaselgele kaugteele |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Laadi hoidla kataloog kohalikult alla |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Laadi üks kaugfail kohalikku kataloogi |
| `rdc vscode connect <repo>@<machine>` | Ava VS Code kaugühenduse SSH seanss |

## Konfigureerimine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc config init <name>` | Loo nimega konfiguratsioonifail |
| `rdc machine add <machine> --ip <host> --user <user>` | Lisa masin konfiguratsiooni |
| `rdc storage import rclone.conf` | Impordi mälupakkujad rclone'i konfiguratsioonist |
| `rdc storage list` | Loenda konfigureeritud mälupakkujad |
| `rdc backup strategy set ...` | Defineeri nimega varundussstrateegia |
| `rdc --config <name> <command>` | Kasuta nimega konfiguratsioonifaili |

## Silumine ja pääsetee

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc term connect <repo>@<machine> -c "docker ps"` | Loenda konteinerid hoidlas |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Hangi konteineri logid |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Käivita käsk konteineris |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Taaskäivita konteiner |
