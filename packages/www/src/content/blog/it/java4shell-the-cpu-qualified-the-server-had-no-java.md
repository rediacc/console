---
title: "Java4Shell: la CPU era idonea, il server non aveva Java e i nostri template ci hanno insegnato qualcosa sul pinning"
description: "CVE-2026-114938 richiede una CPU con AVX-512 VBMI e un JDK vulnerabile. Il nostro server aveva la CPU ma nessuna JVM. Il lavoro vero stava nei template delle app che distribuiamo, dove un solo tag fissato aveva congelato un JDK del 2023."
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
language: it
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **TL;DR.** Java4Shell (CVE-2026-114938) è una scrittura heap out-of-bounds nel decoder Base64 di OpenJDK compilato dal JIT. Scatta solo su CPU x86-64 con AVX-512 VBMI.
>
> - La CPU del nostro server di produzione **ha tutti e quattro i flag richiesti**. Guardando solo la CPU, sembrava esposto.
> - Una sonda su **43 container**, sull'host e sui repository fermi non ha trovato **nessun runtime Java**. Una prova di controllo con la stessa sonda, che cercava `python3`, lo ha trovato ovunque ci si aspettava. Sul server non c'era niente da aggiornare.
> - I template delle app che distribuiamo erano un'altra storia. **Quattro** di loro avviano una JVM. **Tre** usano tag mobili e il 20 novembre erano già stati ricostruiti upstream con JDK corretti.
> - **Uno**, Elasticsearch, era fissato a `8.11.0`: un'immagine di novembre 2023 con JDK incluso `21.0.1`. Elastic non ha ancora una release corretta, quindi ora il template avvia Elasticsearch con il flag di mitigazione di Elastic stessa, verificato su un nodo in esecuzione.

## Cosa è stato divulgato

Il 17 novembre i ricercatori di Calif hanno pubblicato **Java4Shell**, e Oracle e OpenJDK hanno rilasciato le correzioni lo stesso giorno. Il bug sta nel decoder Base64 di HotSpot accelerato via hardware: il percorso AVX-512 VBMI gestisce male gli ultimi caratteri e può scrivere oltre la fine di un buffer nell'heap. Un attaccante remoto senza account può trasformarlo in corruzione di memoria e, nell'applicazione giusta, in esecuzione di codice. L'analisi mostra catene pre-auth per diversi noti prodotti server in Java.

I dettagli che contano per il triage:

- **Interessati:** OpenJDK 17.0.6 e successivi, 21, 25 e 27, prima delle build corrette. Java 8 e Java 11 standard non sono interessati.
- **Corretti:** 17.0.21.1, 21.0.13.1, 25.0.5.1 e 27.0.1.1 (le build Temurin riportano `+2`, oppure `+4` per la 27). Un runtime che riporta `17.0.21` senza il `.1` è ancora vulnerabile.
- **Precondizioni:** una CPU x86-64 con AVX-512 VBMI, un JIT che abbia già compilato il decoder e un percorso dell'app che decodifica Base64 da input non fidato. ARM non è interessato.
- **Punteggio:** 9,2 con CVSS 4.0, 8,1 con CVSS 3.1. Una proof of concept autonoma è pubblica. Al momento della stesura non risultava alcuno sfruttamento in the wild.
- **Mitigazione:** avviare la JVM con `-XX:-UseBASE64Intrinsics`. L'altra opzione pubblicata, `-XX:UseAVX=2`, funziona anch'essa su x86-64 ma su ARM impedisce l'avvio della JVM.

Il nostro [precedente giro di patch](/it/blog/patching-nginx2root-and-php-fork-first) si è chiuso con un rollout fork-first di quattro app. Questo si è chiuso molto prima, e la parte interessante è il perché.

## Passo 1: la CPU è idonea?

La maggior parte delle CVE ha una precondizione software. Questa ne ha anche una hardware, ed è economica da verificare:

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

Tutti e quattro. La macchina monta un AMD EPYC 9354P, una CPU server recente con pieno supporto AVX-512. Se il triage si fosse fermato qui, la risposta sarebbe stata "esposto, aggiornare stanotte tutto ciò che è Java".

![Le tre precondizioni: la CPU è idonea, il controllo sul JDK fallisce, quindi il percorso dell'input non viene mai raggiunto](/img/blog-java4shell-preconditions.svg)

## Passo 2: c'è del Java da aggiornare?

La CPU è solo un anello della catena. Il secondo anello è un JDK vulnerabile, quindi la domanda successiva era semplice: quali container eseguono Java?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

L'abbiamo eseguito con `rdc term connect <repo>@hostinger` per ogni repository della macchina. Il `find` di `libjvm.so` trova le JVM incluse dentro la cartella di un'app e non nel `PATH`, che è per esempio il modo in cui Elasticsearch distribuisce il suo JDK.

Il risultato era vuoto. Nessun `java`, nessun `libjvm.so`, in nessuno dei 43 container in esecuzione.

Un risultato vuoto non prova nulla finché la sonda non ha dimostrato di saper trovare qualcosa. Quindi lo stesso ciclo è stato rieseguito, questa volta cercando `python3`, che sappiamo essere presente nei container di ERPNext. Ha trovato Python 3.14 in ognuno. La sonda funziona: semplicemente il server non ha Java.

Prima di chiudere la questione abbiamo controllato altri due posti. L'host non aveva Java né `/usr/lib/jvm`. I repository senza nulla in esecuzione non avevano immagini Java nei loro daemon Docker. Uno di loro conteneva un checkout del nostro monorepo, e i suoi file compose citavano `cassandra:5.0` e `elasticsearch:8.11.0`. Questo ci ha portato al passo successivo.

## Passo 3: i template che distribuiamo

Rediacc distribuisce template di app già pronti: un `docker-compose.yaml` più un Rediaccfile per ogni app. Può installarli anche un server che non gestiamo noi. Quindi un'immagine Java in un template è un'esposizione per ogni cliente con la CPU giusta, anche quando il nostro server è pulito.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

Quattro template avviano una JVM. Per due di loro la config dell'immagine nel registry nomina già il JDK. Per gli altri due no, quindi abbiamo eseguito ogni immagine una volta e chiesto direttamente:

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| Template | Tag nel template | JDK dentro oggi | Stato |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | corretto upstream, ricostruito il 20 nov |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | corretto upstream, ricostruito il 20 nov |
| Solr | `solr:9-slim` | 17.0.21.1+2 | corretto upstream, ricostruito il 20 nov |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (incluso) | **vulnerabile**, nessuna release corretta di Elastic al momento |

![Fissato contro mobile: l'immagine Elasticsearch fissata ha tenuto un JDK del 2023, i tag mobili sono stati ricostruiti con la correzione](/img/blog-java4shell-pinned-vs-floating.svg)

## La lezione sul pinning, rivista

Il post precedente si chiudeva con "fissare tag esatti". Questo giro aggiunge una nota a piè di pagina a quella regola.

Fissare la versione è giusto per le app che gestiamo e aggiorniamo di proposito. Il pin rende visibile la versione in esecuzione, mentre un tag mobile può puntare a una correzione mentre il server continua a eseguire una vecchia immagine, perché `docker compose up -d` non scarica un'immagine che ha già.

Per i template che le persone distribuiscono da zero, il quadro si ribalta. I tre tag mobili di versione major (`5.0`, `5-community`, `9-slim`) hanno ricevuto il JDK corretto tre giorni dopo la correzione, senza alcuna modifica da parte nostra. L'unico pin esatto, `8.11.0`, ha congelato Elasticsearch su un'immagine costruita a novembre 2023, con un JDK che nessuna ricostruzione di quel tag correggerà.

Quindi la regola che teniamo ha due metà. Le app in produzione hanno tag esatti e un upgrade deliberato. Anche i template hanno pin, perché Elasticsearch e Kibana devono eseguire la stessa versione, ma ora ogni pin dei template è elencato nel nostro pin registry, dove i gate di freschezza segnalano un pin che resta indietro invece di lasciarlo lì per tre anni.

## Passo 4: la mitigazione, provata su un nodo vero

Elastic ha annunciato che la correzione arriverà come aggiornamento del JDK incluso nelle prossime release 8.19.26, 9.4.10, 9.5.7 e 9.6.0. Finché una di queste non esiste, l'indicazione ufficiale è il flag della JVM. Nel template, è una parola in più in `ES_JAVA_OPTS`:

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![Cosa cambia il flag: il JIT mantiene il decoder Java semplice invece dell'intrinsic AVX-512](/img/blog-java4shell-intrinsic-flag.svg)

Un flag in un file compose è solo un'affermazione finché la JVM non lo conferma. Abbiamo verificato due volte. Prima il JDK incluso, con e senza il flag:

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

Poi un vero cluster a nodo singolo avviato con le opzioni del template. È partito in stato green e la sua stessa API elencava il flag tra gli argomenti della JVM:

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## Cosa è andato storto

**Il controllo sulla CPU ha quasi deciso la risposta.** È la precondizione più visibile, richiede un solo comando e diceva "esposto". Solo il secondo controllo, quello su una JVM vera, ha trasformato un'emergenza di mezzanotte in una modifica a un template.

**Una suite di test è stata eseguita dove non doveva.** Per verificare la modifica al template, abbiamo eseguito la suite del ciclo di vita del pacchetto dei template su una workstation. Quella suite è pensata per un repository Rediacc con licenza, non per un host Docker nudo, e ha passato più di dieci minuti ad avviare altri template. Ha anche mostrato che un template non correlato scriveva il proprio segreto generato nella sua cartella sorgente, un file che nessuno vorrebbe in un commit. Ora quel template scrive il segreto fuori dall'albero dei sorgenti, e la suite si rifiuta di partire senza il repository di cui ha bisogno.

**Non c'era niente da forkare.** Il nostro solito passo di sicurezza, un fork del repository di produzione prima di ogni modifica, questa volta non aveva un bersaglio. La modifica stava in un file di template in git, quindi la rete di sicurezza era un commit rivedibile e un test di avvio dal vivo, non uno snapshot.

## Le scelte, e perché

| Opzione che avevamo | Cosa abbiamo scelto | Perché |
|---|---|---|
| Trattare il controllo sulla CPU come la risposta | Cercare una JVM vera | La CPU diceva esposto; senza JVM non c'era nulla da sfruttare. |
| Fidarsi di una sonda vuota | Eseguire un controllo che deve trovare qualcosa | Il risultato vuoto di una sonda rotta sembra identico a quello di un server pulito. |
| Leggere la versione del JDK dal registry | Eseguire ogni immagine una volta | Due delle quattro immagini non registrano la versione del JDK nella loro config. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | Più mirato: spegne una routine, non ogni accelerazione AVX-512, e una JVM su ARM parte comunque. |
| Portare subito Elasticsearch all'ultima 8.19 | Tenere 8.11.0, aggiungere il flag, aggiornare quando esce la release corretta | Le release più recenti disponibili oggi includono ancora un JDK vulnerabile, e Kibana deve muoversi nello stesso passo. |
| Pin esatti ovunque | Pin esatti più un gate di freschezza su ogni pin dei template | Un pin senza allarme ha congelato un JDK del 2023; il gate mantiene il pin e aggiunge l'allarme. |

## La checklist che teniamo

1. Controllare ogni precondizione, non solo la prima che coincide.
2. Cercare il runtime stesso (`java`, `libjvm.so`), non solo il nome di un prodotto.
3. Provare ogni sonda vuota con un controllo.
4. Passare in rassegna ciò che distribuiamo, non solo ciò che eseguiamo.
5. Leggere la versione dentro l'immagine; eseguire l'immagine quando la config tace.
6. Preferire la mitigazione più mirata e confermarla nel processo in esecuzione.
7. Seguire la release corretta del vendor e rimuovere la mitigazione quando arriva.

Come nel giro precedente, il lavoro è stato svolto da un agente IA (Claude Code) tramite `rdc`, con l'accesso alla produzione concesso dall'operatore prima dell'inizio della sessione. Questa volta la produzione non è cambiata affatto: ogni passo sul server è stato una lettura, e l'unica correzione è finita in un template, tramite git, con un test dal vivo alle spalle.
