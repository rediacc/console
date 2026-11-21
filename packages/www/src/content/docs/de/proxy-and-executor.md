---
title: Proxy & Executor
description: Wie Befehle aus Browser und Thin-Client ausgeführt werden, ohne dass der Client jemals SSH-Schlüssel oder Maschinenadressen besitzt
category: Concepts
tags:
  - security
  - networking
subcategory: architecture
order: 4
language: de
sourceHash: "7230a907205b8c84"
sourceCommit: "9f58d83e01b4d46f8ce31af467a203b4d195e801"
---

# Proxy & Executor

Normalerweise läuft `rdc` auf Ihrer eigenen Maschine mit Ihrer Konfiguration und Ihren SSH-Schlüsseln und verbindet sich direkt mit Ihren Servern. Das Proxy-Modell teilt das in zwei Teile: einen Thin-Client, der keine Geheimnisse besitzt, und einen **Executor**, der sie besitzt und die eigentliche Arbeit erledigt. Der Ausführen-Button der [Web-Konsole](/de/docs/web-console) und der `--proxy`-Flag der CLI sind beide Thin-Clients und sprechen dasselbe Protokoll.

## Befehlsabsicht statt Befehle

Ein Thin-Client besitzt niemals einen SSH-Schlüssel, eine Maschinenadresse oder eine entschlüsselte Konfiguration. Will er etwas ausführen, sendet er nur die Befehlsabsicht: eine Kennung für den Befehl (seinen Pfad im CLI-Vertrag, zum Beispiel `repo up`) plus die Parameter. Der Executor sucht den Befehl im selben Vertrag, löst ihn zur zugrunde liegenden serverseitigen Funktion auf, ermittelt die Zielmaschine aus der entschlüsselten Konfiguration und führt alles über seine eigene SSH-Verbindung aus. Die Ausgabe wird zurück an den Client gestreamt.

Der Executor ist die CLI selbst, gestartet als Server mit `rdc serve`. Dieselbe Binärdatei, die Operatoren auf einem Laptop ausführen, wird zu dem Programm, das in ihrem Auftrag Befehle ausführt. Dafür gibt es zwei mögliche Platzierungen:

- **`--mode daemon`**: läuft auf einem Host, den Sie selbst kontrollieren, headless eingebunden wie jede andere CLI (siehe [Konfigurationsspeicher](/de/docs/config-storage)), sodass er den Konfigurationsschlüssel selbstständig ableiten kann und keine Freigabe pro Sitzung braucht. Das ist die strikte Stufe: SSH verlässt Ihr Netzwerk nie.
- **`--mode container`**: läuft in einem organisationsgebundenen Container, der für Sie gehostet wird. Er startet ohne jeden Schlüssel und kann nichts tun, bis ein Client ihm einen für die Sitzung freigibt. Das ist die Komfort-Stufe.

## Die CEK-Freigabe

Der Konfigurationsspeicher ist zero-knowledge: Der Server speichert ausschließlich verschlüsselte Blobs, und der Content Encryption Key (CEK) liegt nur bei einem Client im Klartext vor, der ihn entsperrt hat. Ein Executor im Container-Modus muss den Schlüssel deshalb *zugeteilt bekommen*, und diese Zuteilung darf ihn dabei zu keinem Zeitpunkt gegenüber dem Server offenlegen.

Der Ablauf: Ein entsperrter Browser öffnet eine Sitzung mit dem Executor, erhält dessen öffentlichen Sitzungsschlüssel und versiegelt die CEK per X25519 für genau diese Sitzung. Der versiegelte Blob läuft über den Account-Server, aber der Server kann ihn nicht öffnen - die Zero-Knowledge-Eigenschaft bleibt also durchgängig gewahrt. Der Executor entschlüsselt die CEK nur im Arbeitsspeicher, mit einer Leerlauf-Ablaufzeit von 30 Minuten; auf die Festplatte wird nie geschrieben. Nachfolgende Befehlsanfragen referenzieren die zugeteilte Sitzung über den Header `X-Config-Session`.

Ein Detail ist für Audits entscheidend: Dieselbe Nutzeridentität zieht sich durch alle drei Etappen (Sitzung öffnen, Schlüssel zuteilen, Befehle ausführen). Der Account-Server leitet niemals seine eigene Anmeldeinformation an den Executor weiter. Für jede Etappe stellt er ein kurzlebiges, dem tatsächlichen Nutzer zugeordnetes Token aus und prüft dessen Mitgliedschaft jedes Mal erneut. Der Executor verifiziert jedes vorgelegte Token, bevor er handelt. Eine von einem Nutzer erteilte Zuteilung kann kein anderer Nutzer verwenden.

Die `state`-Hälfte einer Konfiguration (hostlokale Laufzeitdaten) wird niemals im Konfigurations-Blob übertragen und erreicht einen Executor deshalb auf diesem Weg ebenfalls nie.

## Was über einen Proxy laufen kann

Nicht jeder Befehl ergibt remote Sinn. Jeder Befehl im Vertrag trägt ein `proxyCapable`-Flag, das der Executor serverseitig durchsetzt, unabhängig von jeder Policy-Konfiguration:

- **Nicht-interaktive Befehle der Maschinenebene** (Deploy, Backup, Status, Logs und so weiter) sind proxyfähig.
- **Befehle der Konfigurationsebene** sind es nicht: Sie bearbeiten die Konfiguration, was auf diesem Weg Sache des Browsers ist (die Web-Konsole leitet sie stattdessen an den eingebauten Konfigurationseditor weiter).
- **Interaktive Befehle** (Terminals, VS-Code-Sitzungen) sind es nicht: Über diese Verbindung gibt es kein TTY.
- **Clientseitige Transferbefehle** (`rdc repo sync`) sind es nicht: Sie bewegen Daten zwischen dem Dateisystem des *Clients* und einer Maschine, und der Executor hat keinen Zugriff auf die Dateien des Clients.

Die Web-Konsole liest dasselbe Flag, um zu entscheiden, ob ein Befehl überhaupt einen Ausführen-Button bekommt, doch der Executor lehnt nicht-proxyfähige Befehle unabhängig davon ab, was der Client sendet.

## Der Mock-Executor

In der Entwicklung, wenn kein echter Executor konfiguriert ist, beantwortet der Account-Server Befehlsanfragen selbst mit Mock-Streams und eindeutig erfundenen Daten (Ressourcennamen mit dem Präfix `mock-`). Dadurch lässt sich die gesamte Konsole durchspielen, einschließlich Formulare, Streaming und Ergebnisdarstellung, ganz ohne Maschine oder Entsperrung. Eine echte Ausführung braucht einen echten Executor.

## Einschränken, von wo der Executor sich verbindet

Der `access`-Bereich der Konfiguration enthält die erlaubten IPv4- und IPv6-Quellbereiche für SSH-Schlüssel. Die Bereiche lassen sich konfigurationsweit, pro Schlüssel und pro Maschine festlegen, sodass eine Maschine einen Schlüssel nur von den Adressen akzeptiert, von denen sich der Executor verbindet.

- `rdc config access add <key> --public-key ... --hosted-executor` registriert einen Schlüssel und hängt die beiden Bereiche des gehosteten Executors an: `104.28.0.0/16` und `2a09:bac0::/29`. Beide sind beobachtete Cloudflare-Egress-Bereiche und keine von Cloudflare veröffentlichte Liste, sie können sich daher ändern.
- `rdc machine access set <machine> --key <key>` weist einer Maschine einen Schlüssel zu; mit `--ipv4`, `--ipv6` und `--clear-ranges` lassen sich die Bereiche für diese Maschine anpassen.
- `rdc machine access push <machine>` schreibt die Zugriffszeilen auf die Maschine, `--dry-run` zeigt das Ergebnis, ohne etwas zu ändern.
- `rdc machine access show <machine>` gibt die geltenden Zugriffszeilen aus.

`machine setup` wendet die Zugriffszeilen erneut an, sodass eine neu aufgebaute Maschine ihre Einschränkungen zurückerhält.

Ein Push, der die aktuelle SSH-Sitzung aussperren würde, weil deren Adresse außerhalb der Bereiche des verwendeten Schlüssels liegt, wird mit `ACCESS_LOCKOUT` abgelehnt, und es wird nichts geschrieben. Ein Push wird mit `ACCESS_FILE_CHANGED` abgelehnt, wenn sich die Datei auf der Maschine zwischenzeitlich geändert hat; es wurde nichts angewendet, daher kann der Push gefahrlos wiederholt werden.

## Jobs, Tickets und Polling

Jeder Befehl der Maschinenebene läuft auf der Maschine als Job: eine systemd-Unit, die renet verwaltet und deren Status und Ereignisprotokoll in einem Spool auf der Maschine liegen. Eine abgebrochene Verbindung stoppt die Arbeit daher nie, und jeder Client kann den Job über seine ID wieder aufnehmen.

- **Das Attach-Fenster.** Der Executor streamt die Ereignisse eines Jobs bis zu 20 Sekunden lang und sendet bei ruhigem Stream alle 10 Sekunden eine Heartbeat-Zeile. Ein Job, der innerhalb des Fensters endet, liefert sein Ergebnis in derselben Anfrage. Ein längerer Job liefert ein Ergebnis mit `state: running` und der Job-ID, nach einer `job`-Zeile mit der Maschine und allen überlappenden Jobs.
- **Polling.** Der Client fragt danach per `GET /v1/jobs/<id>/poll` die Ereignisse nach der zuletzt gesehenen Zeile samt Status des Jobs ab und wartet zwischen leeren Antworten länger. `POST /v1/jobs/<id>/cancel` bricht den Job ab. Beide Routen wenden dieselbe Richtlinie an wie der Befehl, der den Job gestartet hat, und das Polling, das als Erstes einen Endzustand sieht, schreibt das Audit-Ereignis genau einmal.
- **Tickets.** Jeder Aufruf schreibt außerdem ein Ticket in das Konfigurationsverzeichnis der CLI (`jobs/<config>.jsonl`). `rdc job wait <id>` wartet auf einen Job und endet mit dessen Exit-Code; `rdc job list`, `status`, `logs`, `cancel` und `gc` verwalten den Rest. Strg+C während des Mitverfolgens löst die Verbindung, ohne abzubrechen, und beendet mit 130. Ein Mitverfolgen, dessen Verbindung nicht wiederhergestellt werden konnte, endet mit 16 und behält das Ticket.
- **Schritte.** Arbeit, die auf einen Job folgt, etwa ein Ergebnis in der Konfiguration zu vermerken oder eine Liste auszugeben, ist ein Schritt, der im Ticket und im Spool steht. Ein Schritt läuft einmal, dort, wo der Job zuerst als beendet erkannt wird: im Befehl selbst, in `rdc job wait`, im Hinweis des nächsten Befehls oder im Polling des Executors. Der Anspruch wird auf der Maschine erhoben, sodass zwei Beobachter nie denselben Schritt ausführen.
- **Überschneidungen.** Ein Start, der sich mit einem laufenden Job auf demselben Repository oder derselben Maschine überschneidet, gibt eine Warnung mit dem Befehl aus, der sich an den laufenden Job anhängt. Lehnt die Überschneidungsrichtlinie den Start ab, endet der Befehl mit 15 (`BUSY`), und die Ablehnung nennt die überlappenden Jobs in `overlaps`.
- **Schritte, solange der Client fort ist.** Ein Erfolgsschritt läuft nur, wenn der Job `succeeded` ist, ein Fehlschlagschritt wie ein Rollback nur, wenn er `failed` ist oder abgebrochen wurde. Endet ein Job innerhalb des Attach-Fensters, behält der Executor das Attach auch nach dem Trennen seines Clients bei und führt die Schritte aus; so schließt ein kurzer Befehl, dessen Client die Antwort verloren hat, seine Schritte trotzdem ab. Schritte laufen nur für einen Beobachter, dessen Konfiguration der Konfiguration entspricht, die den Job gestartet hat (der Executor, der das Attach hält, führt sie unter dieser Konfiguration aus, daher passt das Gate); jede andere Konfiguration zeigt `N steps pending for config <name>`. Der Hinweis des nächsten Befehls führt offene Schritte bis zu 20 Sekunden nach dessen eigener Ausgabe aus, und nur in einem interaktiven Textlauf. Unter `-o json`, `-q` oder MCP führt er nichts aus und gibt `steps pending: rdc job wait <id>` auf stderr aus. Solange kein Beobachter das Ende des Jobs gesehen hat, läuft der Dienst weiter, die Schritte warten jedoch: DNS-Namen, Zertifikatsabgleich und URL-Liste nach `repo up`, die Backup-Zeitpläne nach Fork, Migration oder Restore sowie der Basiseintrag, der den nächsten Push zum Delta macht. `rdc job list` zeigt `steps pending`, bis sie gelaufen sind.
- **Ausnahmen.** Interaktive Befehle (`term connect`, `repo tunnel`, `vscode connect`, `repo exec -i` und `repo logs -f`), clientseitige Übertragungen (`repo sync upload`, `download` und `status` sowie `backup upload` und `download`), die `job`-Befehle, `serve`, `vscode serve status` und `stop` sowie Befehle ohne renet-Aufruf wie `cluster kubeconfig` und `machine access push` laufen nicht als Jobs. Die lokalen OpenTofu-Abschnitte von `machine provision` und `deprovision` laufen wie bisher auf dem Client. Jeder andere Befehl der Maschinenebene ist ein Job.
- **Aufbewahrung.** Ein beendeter reiner Lese-Job wird eine Stunde lang aufbewahrt, jeder andere beendete Job sieben Tage. Ein Job mit einem Schritt, den niemand beansprucht hat, bleibt unabhängig von seiner Klasse sieben Tage erhalten, und ein laufender Job wird nie entfernt. Der Spool hält höchstens 2000 beendete Jobs und 256 MiB, dabei gehen die ältesten beendeten Jobs zuerst; die Obergrenzen überspringen einen Job mit unbeanspruchtem Schritt, bis seine sieben Tage um sind. Die Bereinigung läuft beim Start eines Jobs, höchstens einmal pro Stunde. Die systemd-Unit des Jobs wird beim ersten Statusabruf oder Bereinigungslauf gestoppt, der den Job als beendet sieht.

## Verwandte Seiten

- [Web-Konsole](/de/docs/web-console), der Browser-Client, der auf diesem Modell aufbaut
- [Konfigurationsspeicher](/de/docs/config-storage), der Zero-Knowledge-Speicher, den die CEK schützt
