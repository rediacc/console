---
title: Proxy & Executor
description: Wie Befehle aus Browser und Thin-Client ausgeführt werden, ohne dass der Client jemals SSH-Schlüssel oder Maschinenadressen besitzt
category: Concepts
order: 4
language: de
sourceHash: "3f522a473a550b0c"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
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

## Verwandte Seiten

- [Web-Konsole](/de/docs/web-console), der Browser-Client, der auf diesem Modell aufbaut
- [Konfigurationsspeicher](/de/docs/config-storage), der Zero-Knowledge-Speicher, den die CEK schützt
