---
title: "Java4Shell: Unsere CPU war betroffen, unser Server hatte kein Java, und unsere Templates haben uns etwas über Pinning beigebracht"
description: "CVE-2026-114938 braucht eine AVX-512-VBMI-CPU und ein betroffenes JDK. Unser Server hatte die CPU, aber keine einzige JVM. Die eigentliche Arbeit steckte in den App-Templates, die wir ausliefern: Ein gepinnter Tag hatte dort ein JDK von 2023 eingefroren."
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
language: de
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **Kurzfassung.** Java4Shell (CVE-2026-114938) ist ein Heap-Out-of-Bounds-Write im JIT-kompilierten Base64-Decoder von OpenJDK. Er löst nur auf x86-64-CPUs mit AVX-512 VBMI aus.
>
> - Die CPU unseres Produktionsservers **hat alle vier nötigen Flags**. Allein nach dem CPU-Check sah er exponiert aus.
> - Eine Prüfung von **43 Containern**, dem Host und den gestoppten Repositories fand **keine einzige Java-Runtime**. Ein Kontrolllauf derselben Prüfung, der nach `python3` suchte, fand es überall dort, wo es sein sollte. Auf dem Server war nichts zu patchen.
> - Bei den App-Templates, die wir ausliefern, sah es anders aus. **Vier** davon starten eine JVM. **Drei** nutzen Floating Tags und wurden am 20. November upstream schon mit gepatchten JDKs neu gebaut.
> - **Eines**, Elasticsearch, war auf `8.11.0` gepinnt: ein Image von November 2023 mit gebündeltem JDK `21.0.1`. Elastic hat noch kein gefixtes Release, deshalb startet das Template Elasticsearch jetzt mit Elastics eigenem Mitigation-Flag, verifiziert auf einem laufenden Node.

## Was veröffentlicht wurde

Am 17. November haben Forscher von Calif **Java4Shell** veröffentlicht, und Oracle und OpenJDK haben am selben Tag Fixes ausgeliefert. Der Bug sitzt im hardwarebeschleunigten Base64-Decoder von HotSpot: Der AVX-512-VBMI-Pfad behandelt die letzten Zeichen falsch und kann hinter das Ende eines Heap-Puffers schreiben. Ein Angreifer aus der Ferne ohne Account kann daraus Speicherkorruption machen und, in der passenden Anwendung, Codeausführung. Der Write-up zeigt Pre-Auth-Ketten für mehrere bekannte Java-Serverprodukte.

Die Details, die für die Triage zählen:

- **Betroffen:** OpenJDK 17.0.6 und neuer, 21, 25 und 27, vor den Fix-Builds. Standard-Java 8 und Java 11 sind nicht betroffen.
- **Gefixt:** 17.0.21.1, 21.0.13.1, 25.0.5.1 und 27.0.1.1 (Temurin-Builds tragen `+2`, bei 27 `+4`). Eine Runtime, die `17.0.21` ohne das `.1` meldet, ist weiterhin verwundbar.
- **Voraussetzungen:** eine x86-64-CPU mit AVX-512 VBMI, ein JIT, der den Decoder schon kompiliert hat, und ein App-Pfad, der Base64 aus nicht vertrauenswürdigen Eingaben dekodiert. ARM ist nicht betroffen.
- **Score:** 9.2 nach CVSS 4.0, 8.1 nach CVSS 3.1. Ein eigenständiger Proof of Concept ist öffentlich. Zum Zeitpunkt des Schreibens war keine Ausnutzung in freier Wildbahn gemeldet.
- **Mitigation:** die JVM mit `-XX:-UseBASE64Intrinsics` starten. Die andere veröffentlichte Option, `-XX:UseAVX=2`, funktioniert auf x86-64 ebenfalls, lässt aber eine ARM-JVM nicht mehr starten.

Unser [letzter Patch-Lauf](/de/blog/patching-nginx2root-and-php-fork-first) endete mit einem Fork-first-Rollout von vier Apps. Dieser hier endete deutlich früher, und der interessante Teil ist der Grund dafür.

## Schritt 1: Qualifiziert sich die CPU?

Die meisten CVEs haben eine Software-Voraussetzung. Diese hat zusätzlich eine Hardware-Voraussetzung, und die lässt sich billig prüfen:

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

Alle vier. Die Maschine läuft auf einem AMD EPYC 9354P, einer aktuellen Server-CPU mit vollem AVX-512-Support. Hätte die Triage hier aufgehört, wäre die Antwort gewesen: "exponiert, heute Nacht alles mit Java patchen".

![Die drei Voraussetzungen: Die CPU qualifiziert sich, der JDK-Check schlägt fehl, also wird der Eingabepfad nie erreicht](/img/blog-java4shell-preconditions.svg)

## Schritt 2: Gibt es überhaupt Java zu patchen?

Die CPU ist nur ein Glied der Kette. Das zweite Glied ist ein betroffenes JDK, also war die nächste Frage einfach: Welche Container führen überhaupt Java aus?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

Das haben wir über `rdc term connect <repo>@hostinger` für jedes Repository auf der Maschine ausgeführt. Das `find` nach `libjvm.so` fängt JVMs ab, die in einem App-Ordner gebündelt sind und nicht im `PATH` liegen, so wie es zum Beispiel Elasticsearch mit seinem JDK macht.

Das Ergebnis war leer. Kein `java`, kein `libjvm.so`, in keinem der 43 laufenden Container.

Ein leeres Ergebnis beweist nichts, solange die Prüfung nicht gezeigt hat, dass sie etwas finden kann. Also lief dieselbe Schleife noch einmal, diesmal mit der Suche nach `python3`, von dem wir wissen, dass es in den ERPNext-Containern steckt. Sie fand Python 3.14 in jedem davon. Die Prüfung funktioniert, der Server hat schlicht kein Java.

Zwei weitere Stellen haben wir geprüft, bevor wir die Frage abgeschlossen haben. Der Host selbst hatte kein Java und kein `/usr/lib/jvm`. Die Repositories, in denen nichts lief, hatten keine Java-Images auf ihren Docker-Daemons. Eines davon enthielt einen Checkout unseres eigenen Monorepos, und dessen Compose-Dateien erwähnten `cassandra:5.0` und `elasticsearch:8.11.0`. Das wies auf den nächsten Schritt.

## Schritt 3: Die Templates, die wir ausliefern

Rediacc liefert fertige App-Templates aus: pro App eine `docker-compose.yaml` plus ein Rediaccfile. Ein Server, den wir nicht betreiben, kann sie deployen. Ein Java-Image in einem Template ist also eine Exposition für jeden Kunden mit der passenden CPU, auch wenn unser eigener Server sauber ist.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

Vier Templates starten eine JVM. Bei zweien nennt die Image-Config in der Registry das JDK bereits. Bei den anderen beiden nicht, also haben wir jedes Image einmal gestartet und gefragt:

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| Template | Tag im Template | JDK heute im Image | Status |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | upstream gefixt, am 20. Nov. neu gebaut |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | upstream gefixt, am 20. Nov. neu gebaut |
| Solr | `solr:9-slim` | 17.0.21.1+2 | upstream gefixt, am 20. Nov. neu gebaut |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (gebündelt) | **verwundbar**, noch kein gefixtes Elastic-Release |

![Gepinnt gegen Floating: Das gepinnte Elasticsearch-Image behielt ein JDK von 2023, die Floating Tags wurden mit dem Fix neu gebaut](/img/blog-java4shell-pinned-vs-floating.svg)

## Die Pinning-Lektion, überarbeitet

Der letzte Post endete mit "exakte Tags pinnen". Dieser Lauf ergänzt die Regel um eine Fußnote.

Pinning ist richtig für Apps, die wir betreiben und gezielt upgraden. Der Pin macht die laufende Version sichtbar, und ein Floating Tag kann schon auf einen Fix zeigen, während der Server weiter ein altes Image betreibt, weil `docker compose up -d` kein Image zieht, das schon lokal vorhanden ist.

Bei Templates, die Leute frisch deployen, dreht sich das Bild um. Die drei Floating-Major-Tags (`5.0`, `5-community`, `9-slim`) haben das gepatchte JDK drei Tage nach dem Fix übernommen, ohne dass wir etwas ändern mussten. Der eine exakte Pin, `8.11.0`, hat Elasticsearch auf einem Image von November 2023 eingefroren, mit einem JDK, das kein Rebuild dieses Tags jemals fixen wird.

Die Regel, die wir behalten, hat also zwei Hälften. Produktions-Apps bekommen exakte Tags und ein bewusstes Upgrade. Templates bekommen ebenfalls Pins, weil Elasticsearch und Kibana dieselbe Version laufen müssen, aber jeder Template-Pin steht jetzt in unserer Pin-Registry, in der die Freshness-Gates einen Pin melden, der zurückfällt, statt ihn drei Jahre liegen zu lassen.

## Schritt 4: Die Mitigation, bewiesen auf einem echten Node

Elastic hat angekündigt, dass der Fix als Update des gebündelten JDK in den kommenden Releases 8.19.26, 9.4.10, 9.5.7 und 9.6.0 erscheint. Bis eines davon existiert, ist das JVM-Flag die offizielle Empfehlung. Im Template ist das ein Wort mehr in `ES_JAVA_OPTS`:

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![Was das Flag ändert: Der JIT behält den einfachen Java-Decoder statt des AVX-512-Intrinsic](/img/blog-java4shell-intrinsic-flag.svg)

Ein Flag in einer Compose-Datei ist nur eine Behauptung, bis die JVM es bestätigt. Wir haben zweimal geprüft. Zuerst das gebündelte JDK selbst, mit und ohne Flag:

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

Dann ein echter Single-Node-Cluster, gestartet mit den Optionen des Templates. Er kam grün hoch, und seine eigene API listete das Flag unter den JVM-Argumenten:

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## Was schiefgelaufen ist

**Der CPU-Check hätte beinahe die Antwort bestimmt.** Er ist die sichtbarste Voraussetzung, er braucht einen Befehl, und er sagte "exponiert". Erst der zweite Check, auf eine tatsächliche JVM, hat aus einem nächtlichen Notfall eine Template-Änderung gemacht.

**Eine Test-Suite lief dort, wo sie nicht laufen sollte.** Um die Template-Änderung zu prüfen, haben wir die Lifecycle-Suite des Template-Pakets auf einer Workstation gestartet. Diese Suite ist für ein lizenziertes Rediacc-Repository gedacht, nicht für einen nackten Docker-Host, und sie hat über zehn Minuten damit verbracht, andere Templates zu starten. Sie hat außerdem gezeigt, dass ein unbeteiligtes Template sein generiertes Secret in den eigenen Quellordner geschrieben hat, eine Datei, die niemand in einem Commit haben will. Dieses Template schreibt das Secret jetzt außerhalb des Quellbaums, und die Suite weigert sich zu starten, wenn das benötigte Repository fehlt.

**Es gab nichts zu forken.** Unser üblicher Sicherheitsschritt, ein Fork des Produktions-Repositorys vor jeder Änderung, hatte diesmal kein Ziel. Die Änderung lag in einer Template-Datei in git, das Sicherheitsnetz war also ein reviewbarer Commit und ein Live-Boot-Test, kein Snapshot.

## Die Entscheidungen und warum

| Option, die wir hatten | Was wir gewählt haben | Warum |
|---|---|---|
| Den CPU-Check als Antwort behandeln | Nach einer tatsächlichen JVM suchen | Die CPU sagte exponiert, ohne JVM gab es nichts auszunutzen. |
| Einer leeren Prüfung trauen | Eine Kontrolle laufen lassen, die etwas finden muss | Ein leeres Ergebnis einer kaputten Prüfung sieht genauso aus wie ein sauberer Server. |
| Die JDK-Version aus der Registry lesen | Jedes Image einmal starten | Zwei der vier Images tragen die JDK-Version nicht in ihrer Config ein. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | Enger gefasst: Es schaltet eine Routine ab, nicht jeden AVX-512-Speedup, und eine ARM-JVM startet weiterhin. |
| Elasticsearch jetzt auf das neueste 8.19 heben | 8.11.0 behalten, das Flag setzen, beim gefixten Release heben | Die heute neuesten Releases bündeln noch ein betroffenes JDK, und Kibana muss im selben Schritt mitziehen. |
| Überall exakte Pins | Exakte Pins plus ein Freshness-Gate auf jedem Template-Pin | Ein Pin ohne Alarm hat ein JDK von 2023 eingefroren. Das Gate behält den Pin und ergänzt den Alarm. |

## Die Checkliste, die wir behalten

1. Jede Voraussetzung prüfen, nicht nur die erste, die passt.
2. Nach der Runtime selbst suchen (`java`, `libjvm.so`), nicht nur nach einem Produktnamen.
3. Jede leere Prüfung mit einer Kontrolle beweisen.
4. Durchsuchen, was wir ausliefern, nicht nur, was wir betreiben.
5. Die Version im Image lesen. Das Image starten, wenn die Config schweigt.
6. Die engste Mitigation bevorzugen und im laufenden Prozess bestätigen.
7. Das gefixte Release des Herstellers verfolgen und die Mitigation entfernen, sobald es da ist.

Wie beim letzten Lauf hat ein KI-Agent (Claude Code) die Arbeit über `rdc` erledigt, mit Produktionszugriff, den der Operator vor Sitzungsbeginn freigegeben hatte. Diesmal hat sich Produktion überhaupt nicht verändert: Jeder Schritt auf dem Server war lesend, und der eine Fix ging über git in ein Template, mit einem Live-Test dahinter.
