---
title: RDC CLI petuleht
description: "Kiirviide rdc käskudele: konfiguratsioonid, hoidlad, masinad, sünkroonimine ja konteinerid. Täielik valikute kogum: lisa --help käskule."
category: Guides
order: 3
language: et
sourceHash: "bc52628ba870dfbb"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# RDC CLI petuleht

Siia pole loetletud kõiki `rdc` käske, vaid ainult need, mis igal juurutamisel ette tulevad. Täielike valikute saamiseks käivita mis tahes käsk `--help`-iga. Erijuhud ja harva kasutatavad valikud asuvad täielikul viitel.

## Hoidla elutsükkel

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc repo create --name <repo> -m <machine>` | Loo uus hoidla masinal |
| `rdc repo up --name <repo> -m <machine>` | Juuruta või uuenda hoidlat |
| `rdc repo down --name <repo> -m <machine>` | Peata hoidla |
| `rdc repo delete --name <repo> -m <machine>` | Kustuta hoidla |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Tee hoidlast fork (peaaegu kohene, BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | Võta olemasoleva hoidla omand üle |
| `rdc config repository list` | Loenda kõik hoidlad nime ja GUID-iga |

## Hoidlapõhised saladused

Ainult kirjutatavad juurutamisaegsed mandaadid. `get` tagastab ainult kontrollsumma. Väärtust ei tagastata kunagi. Täieliku juhendi leiad [Hoidlad § Saladused](/et/docs/repositories#secrets).

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Loo uus saladus (`--current ""` esmakirjutuse jaoks) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | Kirjuta olemasolev saladus üle (passwd-stiilis eeltingimus) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | Kirjuta üle eelmist väärtust kontrollimata (auditeerituna rotatsioonina) |
| `rdc repo secret list --name <repo>` | Loenda saladuste nimed + tarneviisid (kunagi mitte väärtusi ega kontrollsummasid) |
| `rdc repo secret get --name <repo> --key <KEY>` | Kuva saladuse kontrollsumma + viis (plaintext väärtust kunagi mitte) |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | Kustuta saladus |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | Kustuta eelmist väärtust kontrollimata |

> Forkid ei päri saladusi. Määra need forkile sõnaselgelt käsuga `rdc repo secret set --name <repo>:<tag>`.

## Varundamine ja taastamine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Lükka hoidla varukoopia mäluhoidlasse |
| `rdc repo push --to <storage> -m <machine>` | Lükka kõik hoidlad mäluhoidlasse |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Taasta hoidla mäluhoidlast |
| `rdc repo pull --from <storage> -m <machine>` | Taasta kõik hoidlad mäluhoidlast |
| `rdc repo push ... --bwlimit <limit>` | Piira rsync-i ribalaiust lükkamise ajal (nt `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Piira rsync-i ribalaiust tõmbamise ajal |
| `rdc repo push ... --checkpoint` | Tee konteinerite kontrollpunkt enne lükkamist |
| `rdc repo backup list --from <storage> -m <machine>` | Loenda mäluhoidlas saadaolevad varukoopiad |
| `rdc storage browse --name <storage>` | Sirvi mäluhoidla sisu |

## Hoidla migreerimine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Liiguta hoidla masinate vahel |
| `rdc repo migrate ... --provision` | Provisineeri sihtkohas enne üle kandmist |
| `rdc repo migrate ... --checkpoint` | Tee kontrollpunkt enne migreerimist |
| `rdc repo migrate ... --skip-dns` | Jäta DNS-uuendamine pärast migreerimist vahele |
| `rdc repo migrate ... --bwlimit <limit>` | Piira ülekande ribalaiust |

## Varundusstrateegiad

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Loo või uuenda nimega varundusstrateegiat |
| `rdc config backup-strategy list` | Loenda kõik defineeritud varundusstrateegiad |
| `rdc config backup-strategy show --name <name>` | Näita strateegia üksikasju |
| `rdc config backup-strategy remove --name <name>` | Eemalda strateegia |
| `rdc machine backup schedule -m <machine>` | Juuruta konfigureeritud varundusstrateegiad masinasse |

## Varundusoperatsioonid

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc machine backup schedule -m <machine>` | Juuruta seotud strateegiad systemd-taimeritena |
| `rdc machine backup schedule -m <machine> --dry-run` | Eelvaate taimeriüksused ilma juurutamata (tokenid maskeeritud) |
| `rdc machine backup now -m <machine>` | Käivita kõik seotud strateegiad kohe |
| `rdc machine backup now -m <machine> --strategy <name>` | Käivita konkreetne strateegia kohe |
| `rdc machine backup status -m <machine>` | Kuva taimeri olek ja hiljutised töötulemused |
| `rdc machine backup status -m <machine> --strategy <name>` | Kuva konkreetse strateegia olek |
| `rdc machine backup cancel -m <machine>` | Tühista töötavad varukoopiad |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Tühista konkreetne töötav varukoopia |

## Masina haldamine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc machine query --name <machine>` | Täielik masina olek (süsteem, konteinerid, teenused, hoidlad, võrk) |
| `rdc machine query --name <machine> --system` | Ainult süsteemi teave |
| `rdc machine query --name <machine> --containers` | Ainult konteinerite loend |
| `rdc machine query --name <machine> --repositories` | Ainult hoidlate loend |
| `rdc machine query --name <machine> --services` | Ainult teenuste loend |
| `rdc machine query --name <machine> --network` | Ainult võrgoteave |
| `rdc machine query --name <machine> --block-devices` | Ainult plokiseadmete teave |
| `rdc machine list` | Loenda kõik masinad konfiguratsioonis |
| `rdc config machine setup --name <machine>` | Käivita masina algne provisioneerimine |
| `rdc machine prune --name <machine>` | Eemalda kasutamata ressursid masinalt |
| `rdc machine deprovision --name <machine>` | Tühjenda masin täielikult |
| `rdc machine vault-status --name <machine>` | Kuva LUKS-võlvi olek |

## Terminal ja sünkroonimine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc term connect -m <machine>` | Ava SSH-terminal masinale |
| `rdc term connect -m <machine> -r <repo>` | Ava SSH-terminal hoidlale (seab DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Käivita käsk masinal |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Laadi üles üks või mitu kohalikku faili/kataloogi hoidlasse |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | Laadi üles üks kohalik fail sõnaselgele kaugteele |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Laadi hoidla kataloog kohalikult alla |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Laadi üks kaugfail kohalikku kataloogi |
| `rdc vscode connect -m <machine> -r <repo>` | Ava VS Code kaugühenduse SSH seanss |

## Konfigureerimine

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc config init --name <name>` | Loo nimega konfiguratsioonifail |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Lisa masin konfiguratsiooni |
| `rdc config storage import --file rclone.conf` | Impordi mälupakkujad rclone'i konfiguratsioonist |
| `rdc config storage list` | Loenda konfigureeritud mälupakkujad |
| `rdc config backup-strategy set ...` | Defineeri nimega varundussstrateegia |
| `rdc --config <name> <command>` | Kasuta nimega konfiguratsioonifaili |

## Silumine ja pääsetee

| Käsk | Kirjeldus |
|---------|-------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Loenda konteinerid hoidlas |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Hangi konteineri logid |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Käivita käsk konteineris |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Taaskäivita konteiner |
