---
title: "nginx2root ja PHP RCE-d: tootmisserveri paigaldamine ühe õhtuga, fork enne"
description: "Kaks kriitilist turvaparandust kahe päeva jooksul. Kontrollisime 43 konteinerit, leidsime 6 tõeliselt avatut, proovisime riskantset uuendust forkil ja paigaldasime tootmisse ilma andmekaota."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - nginx
  - php
  - case-study
featured: true
language: et
sourceHash: "94c45a97bd6b1c4e"
sourceCommit: "c3bae279da16e5441ac808ac85b812debb514694"
---

> **TL;DR.** nginx andis 18. novembril välja parandused nginx2root jaoks (CVE-2026-123007 ja neli sama perekonna RCE-d). PHP andis 19. novembril välja parandused 17 CVE-le, neist seitse kriitilist. 20. õhtul paigaldasime oma tootmisserveri.
>
> - **43 konteinerit** kontrollitud minutitega, küsides igaühelt, millist nginxi ja PHP-d see kasutab.
> - **13** jooksutasid vana versiooni. Päriselt avatud oli neist vaid **6**: kolme avaliku veebirakenduse PHP konteinerid.
> - Iga parandus tuli **ametlikust kujutisest** (image), mille olime enne allalaadimist registris üle kontrollinud.
> - Kõige riskantsemat uuendust (ERPNexti hüpe kaheksa väljalaske võrra) harjutasime enne **päris andmetega forkil**. Fork vastas ainsale küsimusele, millele väljalaskemärkmed vastust ei andnud.
> - Üks ketas sai allalaadimise ajal täis. Mahu veebis suurendamine võttis **3,9 sekundit**, seisakuta.

## Mis avalikustati

**nginx2root** on viiest kaugkoodi käivitamise (RCE) veast koosnev komplekt avatud lähtekoodiga nginxis. Peamine neist, CVE-2026-123007, on täisarvu alatäitumine HTTP/2 voojuhtimises, hinnanguga 9,2 CVSS 4.0 skaalal. See mõjutab kõiki nginxi versioone alates 1.9.5-st (2015) kuni 1.31.8-ni, kus HTTP/2 on sisse lülitatud. Ülejäänud neli vajavad HTTP/3 puhverserveri taga, meiliproksit koos `auth_http`-ga või DNS-lahendajat koos `mirror`-iga. Parandatud väljalasked: **1.31.9** (mainline) ja **1.30.7** (stable). Avalik kontseptsioonitõend (proof of concept) ilmus samal päeval.

**PHP väljalase** tuli päev hiljem: 8.5.13, 8.4.28, 8.3.37 ja 8.2.36. Kõige hullemad vead on sessioonide käsitlemises ja ajavööndi vahemälus ning need võivad lõppeda koodi käivitamisega. Teine rühm mõjutab ainult PHP-FPM-i: päringute smugeldamine (request smuggling), XSS olekulehel ja lokaalne õiguste tõstmine.

Selle loo server on `hostinger`, sama tootmismasin, mis esines meie [PocketOS-i testis](/et/blog/i-tested-rediacc-against-the-pocketos-incident). Seal töötavad meiliserver koos veebimeiliga, Nextcloud, turundusstäkk, ERPNext, GitLab, jälgitavuse (observability) stäkk ja mõned demod. Iga rakendus elab oma Rediacc repositooriumis: krüpteeritud mahus, millel on oma Dockeri deemon ja oma privaatne IP-vahemik.

## Samm 1: leia, mis on haavatav, siis mis on avatud

Kujutiste sildid (tag) valetavad vaikimisega. `nextcloud:35-apache` ei ütle midagi seal sees oleva PHP kohta ja Debiani pakett näitab `nginx/1.26.3` nii enne kui pärast turvaparandust. Seetõttu ei lugenud me silte, vaid küsisime igalt töötavalt konteinerilt otse.

```bash
for repo in nextcloud mail mautic erpnext gitlab marketing observability demo-stackoverflow; do
  rdc term connect "$repo@hostinger" -c 'for c in $(docker ps --format "{{.Names}}"); do
    echo "$c: $(docker exec "$c" sh -c "nginx -v 2>&1; php -v 2>/dev/null | head -1")"
  done'
done
```

`rdc term connect <repo>` avab kesta repositooriumi enda keskkonnas, kus `DOCKER_HOST` osutab juba selle repositooriumi Dockeri deemonile. Üks tsükkel katis kogu masina.

![Triaaži lehter: 43 konteinerit, 13 nginxi või PHP-ga, 13 vana versiooniga, 6 avatud](/img/blog-cve-triage-funnel.svg)

Tulemus: 13 konteineris oli nginx või PHP ja kõik 13 olid parandusest vanemad. See kõlab nagu 13 hädaolukorda. Päriselt ei olnud.

Haavatav tähendab, et koodis on viga. Avatud tähendab, et ründaja jõuab veani päriselt ligi. Vahe on võrgutees ja sellel serveril läheb iga avalik päring sama teed.

![Liikluse tee: külastajad kasutavad HTTPS-i ja HTTP/2-t Traefikini, mis edastab lihtsa HTTP/1.1 igale rakendusele](/img/blog-cve-traffic-path.svg)

Traefik, iga repositooriumi ees olev reverse proxy, lõpetab TLS-i ja HTTP/2. Rakendustega räägib ta lihtsa HTTP/1.1 kaudu privaatsel loopback-aadressil. Kontrollisime nginxi seadistusi kahes rakenduses, mis nginxi kaasa pakuvad: ei mingit `http2`, HTTP/3, `mirror`-it ega meiliproksit. Seega nginx2root'il polnud sissepääsu.

PHP vead on teisiti. Need sõidavad tavaliste veebipäringute sees. Nextcloud, Roundcube (veebimeil) ja Mautic kõik jooksutasid PHP-d Apache'i taga, kõik olid internetile avatud ja kõik olid ühe parandusväljalaske võrra maha jäänud. Need kuus konteinerit läksid järjekorras ettepoole.

Üks detail tegi PHP pildi veidi paremaks: kõik kolm rakendust jooksutavad PHP-d Apache'i moodulina, mitte PHP-FPM-ina, nii et ainult FPM-i vead ei kehtinud. Sessiooni- ja ajavööndivead siiski kehtisid.

## Samm 2: leia ametlik parandus ja usalda registrit, mitte blogipostitusi

Meie esimesed veebiotsingud andsid enesekindlaid, vastuolulisi vastuseid. Üks artikkel väitis, et ametlik Nextcloudi kujutis sisaldab endiselt vana PHP-d. Teine väitis, et kolmanda osapoole kujutisel on parandus olemas. Kumbki ei tsiteerinud kujutist ennast.

Kujutist pole vaja alla laadida, et lugeda, mis selle sees on. Register serveerib iga kujutise konfiguratsiooni ja ametlikud PHP-põhised kujutised kirjutavad sinna `PHP_VERSION`.

```bash
curl -s "https://registry-1.docker.io/v2/library/nextcloud/blobs/<config-digest>" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.config.Env[]' | grep PHP_VERSION
# PHP_VERSION=8.5.13
```

See andis iga rakenduse kohta minutitega selge vastuse:

| Rakendus | Töötab | Ametlik parandus | PHP parandatud kujutises |
|---|---|---|---|
| Nextcloud | 35.0.2 | `nextcloud:35.0.3-apache` | 8.5.13 |
| Roundcube | 1.7.5 | `roundcube/roundcubemail:1.7.6-apache` | 8.4.28 |
| Mautic | 7.2.1 | `mautic/mautic:7.2.2-20261119-apache` | 8.3.37 |
| ERPNext | v16.52.1 | `frappe/erpnext:v16.60.0` | (nginx: teadmata) |

ERPNext oli erand. Selle nginx tuleb Debiani paketist, nii et versioonistring jääb mõlemal juhul 1.26.3 peale. Debiani parandatud ehitus on `1.26.3-3+deb13u11`, avaldatud 19. novembril. Uus ERPNexti kujutis ehitati samal õhtul. Kas parandus oli sees? Kujutise konfiguratsioon seda ei ütle. Seda näitab ainult kujutise käivitamine.

## Samm 3: harjuta riskantset uuendust forkil

Parandusväljalasked nagu Roundcube 1.7.5 kuni 1.7.6 on madala riskiga. ERPNext v16.52 kuni v16.60 on kaheksa väljalaske jagu andmebaasimigratsioone päris raamatupidamisandmetel. Selle jaoks tegime proovikäigu.

![Fork-enne väljalase: külmutatud fork, testfork, uuendus ja kontroll, siis tootmine](/img/blog-cve-fork-first-rollout.svg)

Rediacc fork on repositooriumi täielik koopia koos andmetega, tehtud copy-on-write kloonina. See võtab sekundeid, sõltumata suurusest, ja koopia saab oma Dockeri deemoni, IP-vahemiku ja URL-i. Midagi selles ei saa tootmist mõjutada.

```bash
rdc repo fork erpnext@hostinger --tag cve-test
rdc repo up erpnext:cve-test@hostinger --no-start   # mount only, start nothing yet
```

Enne forki käivitamist muutsime selle compose-faili: uus kujutise silt ning ajastaja ja mõlemad tööjärjekorrad pandi keelatud profiili alla. Päris ERPNexti andmete koopia koos töötava ajastajaga saadaks päris e-kirju päris klientidele. Nende väljalülitatuna sai fork lehti serveerida ja migratsioone käivitada, aga midagi muud mitte.

```bash
docker run --rm --entrypoint dpkg-query frappe/erpnext:v16.60.0 -W nginx
# nginx  1.26.3-3+deb13u11
```

Siin oligi vastus: uus kujutis sisaldas Debiani parandatud nginxi. Seejärel tegi fork täieliku uuenduse: `bench --site all migrate` lõppes puhtalt tootmisandmebaasi koopial, rakendus vastas oma tervisekontrolli lõpp-punktis `pong` ja sisselogimisleht laadis forki enda URL-il.

Kui kujutis oleks endiselt vana paketti kandnud, oli plaan lihtne: peatada, fork kustutada ja oodata järgmist ehitust. Tootmine oleks jäänud puutumata, mitte taaskäivitunud uuenduse pärast, mis midagi ei parandanud.

## Samm 4: tootmine, üks rakendus korraga

Iga rakendus läbis sama lühikese rutiini:

1. **Hetktõmmis (snapshot).** `rdc repo fork <app> --tag pre-cve-20261120 --immutable` teeb külmutatud kirjutuskaitstud koopia. Seda ei saa haakida ega käivitada, seega ei saa seda keegi kunagi muuta.
2. **Kinnita silt.** Muuda compose-fail täpselt parandatud sildi peale.
3. **Tõmba, siis paiguta.** `docker pull`, siis `rdc repo up <app> -y`.
4. **Käivita rakenduse enda uuendussamm**, kui see on olemas.
5. **Kontrolli** seestpoolt (versioon, migratsioonid) ja väljastpoolt (avalik URL).

| Rakendus | Mis juhtus | Konteinerid taas üleval |
|---|---|---|
| Nextcloud | Kujutise entrypoint käivitas `occ upgrade` 35.0.2 kuni 35.0.3, umbes minut hooldusrežiimis | 66 s |
| Roundcube | Lihtne kujutise vahetus, skeemikontroll ei leidnud midagi teha | 24 s |
| Mautic | Ketas sai esimesel tõmbamisel täis (vt allpool), siis `doctrine:migrations:migrate` | 6 s |
| ERPNext | Samad sammud mis proovikäigul, ajastaja sisse jäetud, `bench migrate` väljumiskood 0 | 17 s |

Viimane kontroll näitas igas PHP konteineris PHP 8.5.13, 8.4.28 ja 8.3.37, ERPNextis nginxi `deb13u11` ning kõik 43 konteinerit töötasid ilma ühegi ebaõnnestunud tervisekontrollita.

## Mis läks valesti

**Ujuv silt peitis aegunud kujutise.** Nextcloud kasutas silti `nextcloud:35-apache`. See silt osutas juba parandatud kujutisele, aga `docker compose up -d` ei tõmba kujutist, mis tal juba olemas on, nii et server oleks vana PHP-d jooksutanud igavesti. Sildi `35.0.3-apache` kinnitamine teeb töötava versiooni compose-failis nähtavaks ja sunnib iga uuendusega tegelikku muutust.

**Ketas sai allalaadimise ajal täis.** Mautici kujutis on 2,1 GB ja selle repositooriumis oli vaba 1,4 GB. Tõmme ebaõnnestus veaga `no space left on device` enne, kui töötavaid konteinereid puudutati. Lahendus oli üks käsk, tehtud ajal, mil Mautic teenindas liiklust edasi:

```bash
rdc repo expand mautic@hostinger --size 12G
# Repository expanded (3.9s)
```

Maht kasvas veebis 8 GB-lt 12 GB-ni ja tõmme läks läbi. Masina suuruspoliitika oskab nüüd repositooriumi automaatselt kasvatada enne, kui see täis saab.

**Külmutatud hetktõmmiseid ei kasutatud kunagi.** Iga uuendus õnnestus, nii et neli `pre-cve` koopiat lihtsalt seisid. Turvavõrk ongi selleks, aga kaks ausat märkust. Need tehti rakenduste töötamise ajal, seega on andmebaasifailid neis krahhikindlad (crash-consistent), samas seisus nagu pärast voolukatkestust, mitte puhta seiskamise järel. Ja tagasipööramine, mida pole kunagi harjutatud, on plaan, mitte garantii. Järgmine kord testime ühte taastamist, kuni hetktõmmis on veel värske.

**Ühel rakendusel pole parandatud väljalaset veel.** Teine rakendus toob oma nginxi kaasa tarnija kujutises ja see tarnija pole nginx 1.31.9 veel välja andnud. Ülaltoodud liiklustee hoiab HTTP/2 sellest eemal, nii et ootame tarnija väljalaset, mitte ei ehita kujutist käsitsi.

## Valikud ja miks

| Valikuvariant | Mida valisime | Miks |
|---|---|---|
| Lülitada HTTP/2 kiireks leevenduseks välja | Paigaldada uute kujutistega | HTTP/2 lõppes juba Traefikis, nii et leevendus ei andnud midagi juurde. Paigaldamine eemaldab vea, mitte ei peida seda. |
| Usaldada versioonistringi | Kontrollida kujutise sees olevat paketti | Debian porteerib parandused tagasi, muutmata `nginx -v` väljundit. Päris ehituse näitab ainult `dpkg-query`. |
| Usaldada artikleid selle kohta, milline kujutis on parandatud | Lugeda kujutise konfiguratsiooni registrist | Artiklid läksid omavahel vastuollu. Register on allikas. |
| Ujuvad sildid nagu `35-apache` | Täpsed sildid nagu `35.0.3-apache` | Ujuv silt võib osutada parandusele, samal ajal kui server jooksutab endiselt vana kujutist. |
| Uuendada kohapeal, vea korral tagasi pöörata | Suurte hüpete puhul fork enne, väikeste puhul hetktõmmis enne | Forkil harjutamine maksab sekundeid ja leiab probleemi enne kasutajaid. Täielik proovikäik ühe sammu parandusväljalaske jaoks on liig. |
| Jagada liiklus kanaari (canary) abil (`rdc repo canary`) | Harjutada forkil | Kanaar käitab uut versiooni päris andmetel, mis sobib tagasiühilduva skeemiga rakendustele. Kaheksa väljalaske migratsioon pole selline. |
| Puhastada täis ketas käsitsi | Suurendada mahtu veebis | Failide kustutamine Dockeri andmekausta all on riskantne. Suurendamine on üks käsk ega vaja taaskäivitust. |

## Kontrollnimekiri, mida hoiame

1. Küsi igalt konteinerilt, mida see jooksutab. Ära loe silte.
2. Eralda haavatav avatust, jälgides päris võrgutedd.
3. Paigalda avatud konteinerid täna, ülejäänud sel nädalal.
4. Loe parandus registrist, mitte artiklitest.
5. Paketipõhise parandusega kontrolli paketi ehitust kujutise sees.
6. Tee hetktõmmis enne iga muudatust. Harjuta forkil, kui uuendus migreerib andmeid.
7. Kinnita täpsed sildid.
8. Kontrolli seest- ja väljastpoolt, siis puhasta forkid ära.

Kogu töö, turvateadete lugemisest viimase kontrollini, juhtis AI-agent (Claude Code), mis töötas `rdc` kaudu ja kellele operaator oli tootmisjuurdepääsu andnud enne seanssi. Fork-enne rutiin tegi selle mugavaks: agent tegi oma katsed koopiatel ja tootmine nägi ainult samme, mis olid juba toiminud.
