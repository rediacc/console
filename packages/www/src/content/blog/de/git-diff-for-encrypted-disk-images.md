---
title: >-
  git diff für verschlüsselte Disk-Images: Forks vergleichen, ohne sie zu
  entschlüsseln
description: >-
  rdc repo diff vergleicht verschlüsselte Images auf Blockebene und meldet
  A/M/D/R. Kein Schlüssel wird angefasst. Die Kosten richten sich nach den
  geänderten Blöcken, nicht nach der Repository-Größe.
author: Rediacc
publishedDate: 2026-05-28T00:00:00.000Z
category: guide
tags:
  - luks
  - btrfs
  - ext4
  - fiemap
  - cli
featured: false
language: de
sourceHash: 1b08ca130594e2e4
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
translatedFrom: en
---

> **Kurzfassung.** `rdc repo diff` zeigt den Datei-Unterschied zwischen zwei geforkten Repositories in der `git status --short`-Grammatik (A/M/D/R), und entschlüsselt dabei keines der beiden.
>
> - Es vergleicht die zwei LUKS-Image-Dateien auf Blockebene mit dem FIEMAP-ioctl, das nur Extent-Map-Metadaten liest. Kein Schlüssel wird geladen, kein Klartext gelesen.
> - aes-xts ist längenerhaltend und verschlüsselt jeden 512-Byte-Sektor unabhängig. Ein geänderter Klartext-Sektor ist ein geänderter Ciphertext-Sektor am gleichen Offset (verschoben um den 16 MiB LUKS-Daten-Offset). Den Offset abziehen, Gerätebereiche über die ext4-Extent-Map auf Dateinamen abbilden, und schon hat man eine Dateiliste.
> - Die Kosten richten sich nach der Anzahl der geänderten Blöcke, nicht nach der Repository-Größe. Ein 1-GB-Fork und ein 100-GB-Fork werden in gleich vielen Millisekunden verglichen, weil der Vergleich rein auf Metadaten basiert.

Ein Fork in Rediacc ist `cp --reflink=always` auf das LUKS-Image eines Repos. Sofort, und unabhängig von der Größe. Ein 100-GB-Repo forkt genauso schnell wie ein 1-GB-Repo. Das klingt nach Marketing, ist aber einfach die Art, wie Reflinks funktionieren: btrfs kopiert die Extent-Map und teilt die darunterliegenden Blöcke. Wir verlassen uns stark darauf. Forks sind die Test-Sandbox, der Wegwerf-Branch, die Staging-Kopie, die man nach Abschluss einfach löscht.

Was fehlte, war eine günstige Antwort auf die offensichtliche nächste Frage: Was hat dieser Fork eigentlich verändert? Der naive Weg: Den Fork einbinden, den LUKS-Container entsperren, das innere ext4 durchlaufen, jede Datei gegen den Parent hashen. Das skaliert mit der Repository-Größe, sowohl bei Lesevorgängen als auch bei der Entschlüsselung. Es braucht die Schlüssel aktiv auf dem Diff-Pfad. Und es wirft das Einzige weg, was die Storage-Schicht bereits kostenlos weiß: welche Blöcke divergiert sind. `rdc repo diff` nimmt den anderen Weg. Es skaliert mit geänderten Blöcken. Es lädt keinen Schlüssel. Es ermittelt seine Dateiliste durch Vergleich zweier verschlüsselter Images.

## Der Stack, den man vergleicht

Ich möchte genau beschreiben, was "zwei Repositories" auf der Festplatte bedeutet. Der gesamte Trick hängt davon ab. Von unten nach oben: eine SSD, der Host-Storage, ein btrfs-Pool. Darauf liegt eine LUKS2-Image-Datei pro Repo. Entsperren ergibt ein dm-crypt-Gerät. Darin lebt das ext4-Dateisystem, das die Container verwenden. Ein Repo ist eine Datei auf dem btrfs-Pool.

Ein Fork ist ein Reflink dieser Datei. Direkt nach dem Fork sind die zwei Image-Dateien byte-identisch. Sie teilen jeden physischen Block. Parent und Fork sind keine zwei Kopien der Daten. Sie sind zwei Extent-Maps, die auf dieselben Blöcke zeigen. Wenn man innerhalb des Forks schreibt, alloziert die Storage-Schicht einen neuen Block für den geänderten Bereich. Nur die Extent-Map dieses Forks wird neu geschrieben. Die Blöcke des Parents bleiben unberührt.

"Zwei Repositories vergleichen" reduziert sich also auf "zwei Dateien vergleichen, die die meisten ihrer Extents teilen." Der Kernel kann das bereits beantworten. Kein einziges Byte einer der Dateien muss gelesen werden.

## FIEMAP: den Kernel fragen, was sich geändert hat, ohne es zu lesen

Das FIEMAP-ioctl gibt die Extent-Map einer Datei zurück: eine Liste von (logischer Offset, physischer Offset, Länge)-Tupeln. Jedes Tupel gibt an, wo ein Teil der Datei auf der Festplatte liegt. Es sind reine Dateisystem-Metadaten. Es werden keine Dateidaten gelesen. Für ein verschlüsseltes Image wird kein Schlüssel benötigt. Der Ciphertext sind einfach Bytes, die der Kernel nie interpretieren muss.

Die zwei Extent-Maps werden verglichen. Jeder logische Bereich, in dem beide Forks auf denselben physischen Block zeigen, ist geteilt. Geteilt bedeutet identisch, weil es buchstäblich derselbe Block auf dem Gerät ist. Die Bereiche, in denen der Fork seinen eigenen privaten Block hat, sind die Schreibvorgänge. Das sind die geänderten Blöcke. Man bekommt sie aus den Metadaten, die die Storage-Schicht sowieso führt.

Daher kommt die Kosten-Geschichte. Der FIEMAP-Vergleich liest Extent-Records, keine Daten. Seine Arbeit skaliert mit der Anzahl der geänderten Extents, nicht mit der Repository-Größe. Der 1-GB-Fork und der 100-GB-Fork liefern dieselbe kurze Liste privater Extents. Gleiche Millisekunden, wenn sie dieselben Dateien geändert haben. Ehrlicher Vorbehalt: Die Extent-Walk-Zeit skaliert mit der Image-Fragmentierung, nicht mit der Größe. Ein Copy-on-Write-Image unter starken zufälligen Schreibvorgängen häuft Extents an. Der vollständige `filefrag`-Walk dauerte 3,19 Sekunden auf dem am stärksten fragmentierten Produktions-Image, das ich gemessen habe. Siehe den Fragmentierungs-Benchmark-Beitrag. Das ist die Obergrenze auf der Metadaten-Seite. Es ist ein Hintergrund-Scan, kein Datenlesen.

## Von einem geänderten Block zu einem Dateinamen durch zwei verschlüsselte Schichten

Eine Liste geänderter Byte-Bereiche im verschlüsselten Image ist noch nicht nützlich. Die Bereiche sind Positionen im Ciphertext. Die gesuchten Namen befinden sich zwei Schichten höher, im inneren ext4. Die Brücke zwischen ihnen ist Adress-Arithmetik, keine Entschlüsselung.

LUKS verschlüsselt mit aes-xts. Es ist längenerhaltend und verschlüsselt jeden 512-Byte-Sektor eigenständig. Ein geänderter Klartext-Sektor erzeugt einen geänderten Ciphertext-Sektor am gleichen Offset. Der einzige Versatz ist der LUKS-Daten-Offset. Das sind die 16 MiB aus Header und Keyslots vor dem verschlüsselten Payload. Diesen Offset von jedem geänderten Image-Bereich abziehen. Jetzt hat man den entsprechenden Bereich auf dem dm-crypt-Gerät. Das ist das Blockgerät, auf dem das innere ext4 sitzt. Kein Schlüssel wurde verwendet. Es ist Subtraktion.

Jetzt Gerätebereiche auf Dateien abbilden. ext4 führt pro Inode ebenfalls eine Extent-Map. Gleiche (logisch, physisch, Länge)-Struktur. Man erreicht sie über FIEMAP auf dem eingehängten inneren Dateisystem. Die Inodes einmal durchlaufen, um einen Block-zu-Datei-Index aufzubauen. Dann jeden geänderten Gerätebereich in diesem Index nachschlagen. Ein Bereich, der mit den Daten-Extents von Inode 1234 überlappt, gehört zum Pfad dieses Inodes. Das ist die Datei, die sich geändert hat.

Ich möchte klar sagen, was das niemals tut. Es leitet niemals Klartext aus dem geänderten Image ab. Es liest Dateisystemstruktur an bekannten Offsets. Das tut es sowohl auf der verschlüsselten als auch auf der entschlüsselten Seite. Dann verbindet es beide über Adressen. Der Block-Filter sagt, welche Gerätebereiche sich verändert haben. Die ext4-Extent-Map sagt, welche Datei jeden Bereich besitzt. Keiner der Schritte prüft den Inhalt eines geänderten Blocks, um zu entscheiden, ob er sich geändert hat.

## Hinzufügungen, Löschungen und Umbenennungen: der Inode-Identitäts-Walk

Modifikationen ergeben sich direkt aus dem Block-Vergleich. Hinzufügungen, Löschungen und Umbenennungen brauchen eine weitere Beobachtung. Der Reflink liefert sie kostenlos: Ein Fork bewahrt Inode-Nummern. Das Reflinken des gesamten Images klont das gesamte innere Dateisystem byte-genau, bevor irgendetwas divergiert. Ein Inode, der im Parent existierte, hat dieselbe Nummer im Fork.

Das macht Identität zu einem Mengenvergleich. Ein Inode auf beiden Seiten mit einem anderen Pfad ist eine Umbenennung. Ein Inode nur auf der neuen Seite ist eine Hinzufügung. Ein Inode nur auf der alten Seite ist eine Löschung. Eine Umbenennung wird durch Geräte-Extent-Überlappung bestätigt. Die Datenblöcke der umbenannten Datei liegen auf beiden Forks an denselben Geräte-Offsets. Die zwei Forks teilen ein Koordinatensystem. Diese Überlappung schließt auch aus, dass eine Inode-Nummer für unzusammenhängende Daten wiederverwendet wird. Eine reine Umbenennung erscheint dann mit den Datenblöcken der Datei unverändert. Nur der Verzeichniseintrag wurde verschoben.

Hier ist das Standard-Name-Status-Format, dieselbe A/M/D/R-Grammatik, die man bereits von `git status --short` kennt:

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Eine geänderte Datei in einem 1-GB-Repository. Gemeldet aus einem Block-Vergleich, der keine Dateidaten gelesen hat. Nichts wurde entsperrt.

Das Standardverhalten tut für die Korrektheit noch etwas mehr. Der Block-Filter ist ein Obermenge. Ein btrfs-Extent kann mehr als die tatsächlich geänderten Bytes abdecken. Ein Schreibvorgang in eine Datei kann also eine Nachbardatei markieren, die einen Extent teilt. Um das Melden einer nicht geänderten Datei zu vermeiden, bestätigt das Standardverhalten jeden block-markierten Kandidaten. Es hasht nur diese Datei auf beiden Seiten. Es hasht die Kandidaten, nicht das Repo. Die Bestätigungskosten richten sich also nach dem Change-Set. `--fast` vertraut dem Block-Filter und überspringt die Bestätigung. Damit erhält man die Antwort schnell, mit der Toleranz gelegentlicher Falsch-Positive.

## Warum ein KI-Agent das braucht

Der Grund, warum dieser Befehl überhaupt existiert, ist der Agent-Workflow. Ich sah immer wieder, wie Agenten die Produktion forkten, Änderungen ausführten und dann keine saubere Möglichkeit hatten zu berichten, was sie tatsächlich berührt hatten. Ein KI-Agent kann die Produktion sofort forken. Er führt eine riskante Änderung im isolierten Fork durch. Dann muss er genau wissen, was er berührt hat, bevor er irgendetwas zurückbefördert. Fork ist der Branch. Diff ist das Review.

Der Agent liest nicht den Name-Status, er liest `--json`:

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

Die strukturierte Ausgabe gibt dem Agenten ein präzises Change-Set. Welche Pfade er geändert, erstellt oder gelöscht hat. Mit `--stat` die Änderungsgröße pro Datei in Bytes und Blöcken. Ein Agent, der seinen Diff sieht, bevor er befördert, ist einer, dem man die Nähe zur Produktion erlauben kann. Der Strahlungsradius ist inspizierbar, nicht behauptet. Andere Modi dienen demselben Review-Loop. `--name-only` für eine reine Pfadliste. `--content <path>` für ein Unified-Text-Diff einer Datei (nur Text; eine Binärdatei meldet `Binary files differ`). `--stat`, wenn der Agent wissen muss, was sich wie viel geändert hat.

## Warum DR-Tests das brauchen

Dasselbe Primitiv beantwortet eine DR-Frage, die ohne Risiko früher schwer zu stellen war. Die Produktion forken. Ein Backup in den Fork wiederherstellen. Den Fork gegen die Produktion vergleichen. Der Diff sagt, ob die Wiederherstellung den erwarteten Dateisatz reproduziert hat. Das geht, ohne die Produktion herunterzunehmen. Und es entschlüsselt auf dem Diff-Pfad nichts.

Das ist eine Probe, die planmäßig durchgeführt werden kann. Die Wiederherstellung landet in einem isolierten Fork. Der Diff meldet das Delta in Git-Grammatik. Eine saubere Probe: Das geänderte Set entspricht dem, was das Backup enthalten sollte. Man validiert die Wiederherstellung gegen die Live-Produktion. Die Kopie kostet nichts in der Erstellung und nichts im Verwerfen.

## Ehrliche Grenzen

Der Inhaltsdiff ist nur Text. `--content` erzeugt ein Unified-Diff für Textdateien. Für alles andere meldet es `Binary files differ`, genauso wie git. Ein zeilenorientiertes Diff eines verschlüsselt-dann-komprimierten Blobs ist Rauschen.

Es vergleicht verwandte Forks, keine beliebigen Repositories. Der gesamte Mechanismus beruht auf einem gemeinsamen Koordinatensystem. Geteilte Extents beweisen Gleichheit. Bewahrte Inode-Nummern verankern Identität. Ein gemeinsamer Daten-Offset verbindet alles. Zwei Repos, die nie aus einem gemeinsamen Vorfahren geforkt wurden, teilen nichts davon. Es gibt kein günstiges Diff zwischen ihnen. Das ist ein Feature, kein Fehler. Genauso wie `git diff` zwischen zwei unzusammenhängenden Historien nicht aussagekräftig ist.

Rename-Erkennung basiert auf Inodes. Sie ist exakt für Umbenennungen, die ein Dateisystem tatsächlich als Umbenennungen aufzeichnet. Ein Löschen und Neuerstellen von identischem Inhalt unter einem neuen Namen? Zwei Operationen in der Inode-Tabelle. Es wird also als eine Löschung und eine Hinzufügung gemeldet, nicht als Umbenennung. Die Inhalts-Ähnlichkeitsheuristik von git würde das als Umbenennung einstufen. Der Inode-Walk nicht. Das ist die korrekte Antwort darüber, was das Dateisystem getan hat. Auch wenn es nicht die Antwort darüber ist, was ein Mensch beabsichtigt hatte.

Und der Metadaten-Walk skaliert mit der Fragmentierung. Bei einem stark fragmentierten Image dauert die Extent-Enumeration Sekunden, nicht Millisekunden. Es ist immer noch unabhängig von der Repository-Größe. Es ist immer noch frei von Datenlesen. Aber es ist nicht buchstäblich sofort auf den am stärksten fragmentierten Images.

## Das Fazit

`rdc repo diff` bringt die Ergonomie von Versionskontrolle auf verschlüsselte, laufende Infrastruktur. Die Schnittstelle ist bewusst an git angelehnt. A/M/D/R, Unified-Diffs, `--stat`. Nichts Neues zu lernen. Wer `git status --short` lesen kann, kann einen Diff zwischen zwei LUKS-Images lesen. Die Technik darunter ist das, was wirklich interessiert. Sie besteht aus zwei Verweigerungen. Sie entschlüsselt nie. aes-xts ermöglicht es einem Block-Level-FIEMAP-Vergleich, jeden geänderten Sektor per Adresse zu lokalisieren. Und sie zahlt nie für Daten, die sich nicht geändert haben. Die Storage-Schicht hat bereits aufgezeichnet, welche Blöcke divergiert sind. Fork ist der Branch. Diff ist das Review. Das Review kostet, was die Änderung kostet, nicht was das Repo wiegt.
