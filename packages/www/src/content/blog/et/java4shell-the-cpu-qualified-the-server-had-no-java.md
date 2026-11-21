---
title: "Java4Shell: meie protsessor sobis, serveris polnud Javat ja mallid õpetasid kinnitamisest"
description: "CVE-2026-114938 vajab AVX-512 VBMI protsessorit ja haavatavat JDK-d. Meie serveri protsessor sobis, aga JVM-e polnud ühtegi. Päris töö oli rakendusmallides, mida me tarnime: üks kinnitatud silt oli külmutanud 2023. aasta JDK."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - java
  - docker
  - case-study
featured: true
language: et
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **TL;DR.** Java4Shell (CVE-2026-114938) on OpenJDK JIT-kompileeritud Base64 dekooderi viga, mis kirjutab hunnikumälus (heap) üle piiri. See käivitub ainult x86-64 protsessoritel, millel on AVX-512 VBMI.
>
> - Meie tootmisserveri protsessoril **on kõik neli nõutud lippu** (flag). Ainult protsessori põhjal nägi server avatud välja.
> - **43 konteineri**, hosti ja peatatud repositooriumide kontroll ei leidnud **ühtegi Java runtime'i**. Sama kontrolli kontrollkäik, mis otsis `python3`-e, leidis selle kõikjalt, kus see olema pidi. Serveris polnud midagi parandada.
> - Rakendusmallidega, mida me tarnime, oli lugu teine. **Neli** neist käivitavad JVM-i. **Kolm** kasutavad ujuvaid silte (tag) ja need ehitati 20. novembril upstreamis juba parandatud JDK-dega uuesti.
> - **Üks**, Elasticsearch, oli kinnitatud versioonile `8.11.0`: 2023. aasta novembri kujutis (image) koos komplekteeritud JDK-ga `21.0.1`. Elasticul pole parandatud väljalaset veel, seega käivitab mall Elasticsearchi nüüd Elastici enda leevenduslipuga, mida kontrollisime töötaval sõlmel.

## Mis avalikustati

17. novembril avaldasid Calif'i uurijad **Java4Shelli**, ja Oracle ning OpenJDK andsid samal päeval välja parandused. Viga asub HotSpoti riistvaraliselt kiirendatud Base64 dekooderis: AVX-512 VBMI tee käsitleb viimaseid märke valesti ja võib kirjutada üle hunnikupuhvri lõpu. Kaugründaja, kellel pole kontot, saab sellest mälukahjustuse ja sobivas rakenduses ka koodi käivitamise. Ülevaates on autentimiseta ahelad mitme tuntud Java serveritoote vastu.

Triaaži jaoks olulised üksikasjad:

- **Mõjutatud:** OpenJDK 17.0.6 ja uuemad, 21, 25 ja 27, enne parandusega ehitusi. Tavaline Java 8 ja Java 11 ei ole mõjutatud.
- **Parandatud:** 17.0.21.1, 21.0.13.1, 25.0.5.1 ja 27.0.1.1 (Temurini ehitustel on `+2`, versioonil 27 `+4`). Runtime, mis teatab `17.0.21` ilma `.1`-ta, on endiselt haavatav.
- **Eeltingimused:** x86-64 protsessor AVX-512 VBMI-ga, JIT, mis on dekooderi juba kompileerinud, ja rakenduse tee, mis dekodeerib Base64 usaldamatut sisendit. ARM ei ole mõjutatud.
- **Hinnang:** 9,2 CVSS 4.0 järgi, 8,1 CVSS 3.1 järgi. Iseseisev kontseptsioonitõend (proof of concept) on avalik. Kirjutamise ajal polnud ründamisest looduses teatatud.
- **Leevendus:** käivita JVM lipuga `-XX:-UseBASE64Intrinsics`. Teine avaldatud võimalus, `-XX:UseAVX=2`, töötab samuti x86-64 peal, aga ARM-i JVM keeldub selle korral käivitumast.

Meie [eelmine paigaldusring](/et/blog/patching-nginx2root-and-php-fork-first) lõppes nelja rakenduse fork-enne väljalaskega. See ring lõppes palju varem ja huvitav on just see, miks.

## Samm 1: kas protsessor sobib?

Enamikul CVE-dest on tarkvaraline eeltingimus. Sellel on ka riistvaraline ja seda on odav kontrollida:

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

Kõik neli. Masinas töötab AMD EPYC 9354P, uus serveriprotsessor täieliku AVX-512 toega. Kui triaaž oleks siin lõppenud, oleks vastus olnud "avatud, paigalda täna õhtul kogu Java".

![Kolm eeltingimust: protsessor sobib, JDK kontroll ebaõnnestub, seega sisendi teeni ei jõuta kunagi](/img/blog-java4shell-preconditions.svg)

## Samm 2: kas on üldse Javat, mida parandada?

Protsessor on ahelas vaid üks lüli. Teine lüli on haavatav JDK, nii et järgmine küsimus oli lihtne: millised konteinerid üldse Javat jooksutavad?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

Jooksutasime seda käsuga `rdc term connect <repo>@hostinger` iga masinas oleva repositooriumi jaoks. `find` faili `libjvm.so` leidmiseks tabab JVM-id, mis on rakenduse kausta sisse komplekteeritud ja pole `PATH`-is, nii tarnib oma JDK-d näiteks Elasticsearch.

Tulemus oli tühi. Ei `java`-t ega `libjvm.so`-d ühegi 43 töötava konteineri sees.

Tühi tulemus ei tõesta midagi enne, kui kontroll on näidanud, et oskab midagi leida. Seega jooksis sama tsükkel uuesti, seekord otsides `python3`-e, mis on teadaolevalt ERPNexti konteinerites. See leidis Python 3.14 igaühest. Kontroll töötab, lihtsalt serveris pole Javat.

Enne küsimuse sulgemist kontrollisime veel kahte kohta. Hostil endal polnud Javat ega kausta `/usr/lib/jvm`. Repositooriumidel, kus midagi ei töötanud, polnud nende Dockeri deemonites ühtegi Java kujutist. Ühes neist oli meie enda monorepo checkout ja selle compose-failides mainiti `cassandra:5.0` ja `elasticsearch:8.11.0`. See viis järgmise sammuni.

## Samm 3: mallid, mida me tarnime

Rediacc tarnib valmis rakendusmalle: iga rakenduse kohta `docker-compose.yaml` ja Rediaccfile. Neid saab paigaldada server, mida meie ei jooksuta. Seega on Java kujutis mallis ohuks igale kliendile, kellel on sobiv protsessor, isegi kui meie enda server on puhas.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

Neli malli käivitavad JVM-i. Kahe puhul nimetab kujutise konfiguratsioon registris JDK juba ära. Ülejäänud kahe puhul mitte, seega käivitasime iga kujutise korra ja küsisime:

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| Mall | Silt mallis | JDK sees täna | Olek |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | parandatud upstreamis, uuesti ehitatud 20. nov |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | parandatud upstreamis, uuesti ehitatud 20. nov |
| Solr | `solr:9-slim` | 17.0.21.1+2 | parandatud upstreamis, uuesti ehitatud 20. nov |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (komplekteeritud) | **haavatav**, Elasticul pole parandatud väljalaset veel |

![Kinnitatud versus ujuv: kinnitatud Elasticsearchi kujutis jättis alles 2023. aasta JDK, ujuvad sildid ehitati parandusega uuesti](/img/blog-java4shell-pinned-vs-floating.svg)

## Kinnitamise õppetund, üle vaadatud

Eelmine postitus lõppes sõnadega "kinnita täpsed sildid". See ring lisab sellele reeglile joonealuse märkuse.

Kinnitamine on õige rakenduste puhul, mida me jooksutame ja uuendame teadlikult. Kinnitus teeb töötava versiooni nähtavaks ja ujuv silt võib osutada parandusele, samal ajal kui server jooksutab endiselt vana kujutist, sest `docker compose up -d` ei tõmba kujutist, mis tal juba olemas on.

Mallide puhul, mida inimesed paigaldavad nullist, pöördub pilt ümber. Kolm ujuvat suurversioonisilti (`5.0`, `5-community`, `9-slim`) said parandatud JDK kätte kolm päeva pärast parandust, ilma et meie poolel midagi muutunuks. Ainus täpne kinnitus, `8.11.0`, külmutas Elasticsearchi 2023. aasta novembris ehitatud kujutisele, mille JDK-d ei paranda ükski selle sildi uuesti ehitus.

Seega on reegel, mida me hoiame, kahe poolega. Tootmisrakendused saavad täpsed sildid ja teadliku uuenduse. Mallid saavad samuti kinnitused, sest Elasticsearch ja Kibana peavad jooksma sama versiooniga, aga iga malli kinnitus on nüüd kirjas meie kinnituste registris, kus värskusekontrollid (freshness gate) märgivad maha jäänud kinnituse, selle asemel et lasta sel kolm aastat seista.

## Samm 4: leevendus, tõestatud päris sõlmel

Elastic on teatanud, et parandus tuleb komplekteeritud JDK uuendusena eelseisvates väljalasetes 8.19.26, 9.4.10, 9.5.7 ja 9.6.0. Kuni ühtegi neist pole, on ametlik juhis JVM-i lipp. Mallis on see üks sõna juurde muutujas `ES_JAVA_OPTS`:

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![Mida lipp muudab: JIT jätab alles lihtsa Java dekooderi AVX-512 intrinsiku asemel](/img/blog-java4shell-intrinsic-flag.svg)

Lipp compose-failis on vaid väide, kuni JVM seda kinnitab. Kontrollisime kaks korda. Esiteks komplekteeritud JDK ennast, lipuga ja ilma:

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

Seejärel käivitasime päris ühesõlmelise klastri malli valikutega. See tuli üles rohelisena ja selle enda API loetles lipu JVM-i argumentide hulgas:

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## Mis läks valesti

**Protsessori kontroll otsustas peaaegu vastuse ära.** See on kõige nähtavam eeltingimus, võtab ühe käsu ja ütles "avatud". Alles teine kontroll, päris JVM-i otsimine, muutis südaööhädaolukorra malli muudatuseks.

**Testikomplekt jooksis seal, kus ei oleks pidanud.** Malli muudatuse kontrollimiseks jooksutasime tööjaamas mallipaketi elutsükli testikomplekti. See komplekt on mõeldud litsentsitud Rediacc repositooriumile, mitte paljale Dockeri hostile, ja see kulutas üle kümne minuti teiste mallide käivitamisele. Samuti selgus, et üks mitteseotud mall kirjutas oma genereeritud saladuse oma lähtekausta, faili, mida keegi commiti ei tahaks. See mall kirjutab nüüd saladuse väljapoole lähtepuud ja komplekt keeldub käivitumast ilma repositooriumita, mida ta vajab.

**Forkida polnud midagi.** Meie tavaline turvasamm, tootmisrepositooriumi fork enne igat muudatust, jäi seekord sihtmärgita. Muudatus oli malli failis gitis, seega oli turvavõrguks üle vaadatav commit ja päris käivitustest, mitte hetktõmmis (snapshot).

## Valikud ja miks

| Valikuvariant | Mida valisime | Miks |
|---|---|---|
| Võtta protsessori kontrolli vastuseks | Otsida päris JVM-i | Protsessor ütles avatud, aga ilma JVM-ita polnud midagi ära kasutada. |
| Usaldada tühja kontrolli | Käivitada kontrollkäik, mis peab midagi leidma | Katkise kontrolli tühi tulemus näeb välja sama mis puhas server. |
| Lugeda JDK versioon registrist | Käivitada iga kujutis korra | Kahe neljast kujutisest konfiguratsioon JDK versiooni ei salvesta. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | Kitsam: lülitab välja ühe rutiini, mitte iga AVX-512 kiirenduse, ja ARM-i JVM käivitub endiselt. |
| Tõsta Elasticsearch kohe uusimale 8.19-le | Hoida 8.11.0, lisada lipp, tõsta, kui parandatud väljalase ilmub | Täna väljas olevad uusimad väljalasked komplekteerivad endiselt haavatava JDK ja Kibana peab liikuma samas sammus. |
| Täpsed kinnitused kõikjal | Täpsed kinnitused pluss värskusekontroll igale malli kinnitusele | Häireta kinnitus külmutas 2023. aasta JDK, kontroll hoiab kinnituse ja lisab häire. |

## Kontrollnimekiri, mida hoiame

1. Kontrolli kõiki eeltingimusi, mitte ainult esimest, mis sobib.
2. Otsi runtime'i ennast (`java`, `libjvm.so`), mitte ainult toote nime.
3. Tõesta iga tühi kontroll kontrollkäiguga.
4. Käi läbi see, mida tarnime, mitte ainult see, mida jooksutame.
5. Loe versioon kujutise seest, käivita kujutis, kui konfiguratsioon vaikib.
6. Eelista kitsaimat leevendust ja kinnita seda töötavas protsessis.
7. Jälgi tarnija parandatud väljalaset ja eemalda leevendus, kui see ilmub.

Nagu eelmisel ringil, tegi töö AI-agent (Claude Code) `rdc` kaudu, tootmisjuurdepääsuga, mille operaator andis enne seanssi. Seekord ei muutunud tootmine üldse: iga samm serveris oli lugemine ja ainus parandus läks malli, gitis, päris testiga selja taga.
